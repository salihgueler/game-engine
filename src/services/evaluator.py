"""Question evaluation services using Strands Agents for general knowledge and container sandbox for coding."""
import json
import logging
import os
import time

from strands import Agent
from strands.models import BedrockModel

from src.extensions import db
from src.models.models import GlobalConfig
from src.services.sandbox.runner import run_code

logger = logging.getLogger(__name__)


def _get_config_flag(key, default="false"):
    """Get a global config boolean flag."""
    cfg = db.session.query(GlobalConfig).filter_by(key=key).first()
    return (cfg.value.lower() == "true") if cfg else (default.lower() == "true")


def _get_bedrock_model():
    """Create a Bedrock model instance."""
    region = os.environ.get("AWS_REGION", "eu-west-1")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-20250514-v1:0")
    return BedrockModel(model_id=model_id, region_name=region)


def evaluate_multiple_choice(question, player_answer):
    """Evaluate a multiple choice answer against the correct answer."""
    # Check auto-pass
    if _get_config_flag(GlobalConfig.AUTO_PASS_ALL):
        return {"correct": True, "grade": "Correct", "message": "Auto-pass enabled."}

    correct = question.correct_answer.strip().lower()
    answer = player_answer.strip().lower()
    is_correct = correct == answer

    result = {
        "correct": is_correct,
        "grade": "Correct" if is_correct else "Wrong",
        "message": "Correct!" if is_correct else "Incorrect answer.",
    }

    # Optionally show correct answer
    if not is_correct and _get_config_flag(GlobalConfig.SHOW_CORRECT_ON_WRONG):
        result["correct_answer"] = question.correct_answer

    # Update stats
    if is_correct:
        question.times_correct += 1
    else:
        question.times_incorrect += 1
    db.session.commit()

    return result


def evaluate_general_knowledge(question, player_answer):
    """Evaluate a general knowledge answer using LLM-based grading via Strands Agent."""
    # Check auto-pass
    if _get_config_flag(GlobalConfig.AUTO_PASS_ALL):
        return {"correct": True, "grade": "Good", "confidence": 100, "message": "Auto-pass enabled."}

    try:
        model = _get_bedrock_model()

        system_prompt = """You are a quiz answer evaluator. You will be given a question, the expected correct answer, and a player's answer.
Evaluate the player's answer and respond with ONLY a JSON object (no markdown, no extra text) with these fields:
- "confidence": a number 0-100 representing how correct the answer is
- "explanation": a brief explanation of your evaluation

Rules:
- Do NOT penalise short answers. A brief correct answer is just as valid as a long one.
- Focus on factual correctness, not verbosity.
- Be generous with spelling variations and synonyms.
- If the core meaning matches, give high confidence."""

        agent = Agent(model=model, system_prompt=system_prompt, callback_handler=None)

        prompt = f"""Question: {question.description}
Expected Answer: {question.correct_answer}
Player Answer: {player_answer}

Evaluate the player's answer. Return ONLY a JSON object with "confidence" (0-100) and "explanation"."""

        result = agent(prompt)
        response_text = result.message["content"][0]["text"]

        # Parse LLM response
        try:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
            if json_match:
                evaluation = json.loads(json_match.group())
            else:
                evaluation = json.loads(response_text)
        except (json.JSONDecodeError, AttributeError):
            evaluation = {"confidence": 0, "explanation": "Could not parse evaluation."}

        confidence = evaluation.get("confidence", 0)

        # Grade based on confidence thresholds
        if confidence < 1:
            grade = "Wrong"
            is_correct = False
        elif confidence < 50:
            grade = "Low Confidence"
            is_correct = False
        elif confidence <= 70:
            grade = "OK Answer"
            is_correct = True
        else:
            grade = "Good"
            is_correct = True

        result_data = {
            "correct": is_correct,
            "grade": grade,
            "confidence": confidence,
            "message": evaluation.get("explanation", ""),
        }

        if not is_correct and _get_config_flag(GlobalConfig.SHOW_CORRECT_ON_WRONG):
            result_data["correct_answer"] = question.correct_answer

        # Update stats
        if is_correct:
            question.times_correct += 1
        else:
            question.times_incorrect += 1
        db.session.commit()

        return result_data

    except Exception as e:
        logger.error(f"LLM evaluation failed: {e}")
        return {"correct": False, "grade": "Error", "confidence": 0, "message": f"Evaluation error: {str(e)}"}


def evaluate_coding(question, player_code):
    """Evaluate coding answer using container-based sandbox execution."""
    # Check auto-pass
    if _get_config_flag(GlobalConfig.AUTO_PASS_ALL):
        return {"correct": True, "grade": "Correct", "message": "Auto-pass enabled.", "hint_passed": True, "hidden_passed": True}

    language = (question.code_programming_language or "python").lower().strip()

    logger.info(
        "Coding evaluation started: question_id=%s, language=%s, code_length=%d",
        question.id, language, len(player_code),
    )
    eval_start = time.monotonic()

    try:
        hint_passed = False
        hidden_passed = False

        # Test with sample input/output
        if question.code_sample_input and question.code_sample_output:
            logger.info("Running hint test: question_id=%s", question.id)
            hint_passed = _run_sandbox_test(language, player_code, question.code_sample_input, question.code_sample_output)
            logger.info("Hint test result: question_id=%s, passed=%s", question.id, hint_passed)

        # Test with hidden input/output
        if question.code_hidden_input and question.code_hidden_output:
            logger.info("Running hidden test: question_id=%s", question.id)
            hidden_passed = _run_sandbox_test(language, player_code, question.code_hidden_input, question.code_hidden_output)
            logger.info("Hidden test result: question_id=%s, passed=%s", question.id, hidden_passed)

        is_correct = hint_passed and hidden_passed
        elapsed = time.monotonic() - eval_start

        result_data = {
            "correct": is_correct,
            "grade": "Correct" if is_correct else "Wrong",
            "message": "All tests passed!" if is_correct else "One or more tests failed.",
            "hint_passed": hint_passed,
            "hidden_passed": hidden_passed,
        }

        if not is_correct and _get_config_flag(GlobalConfig.SHOW_CORRECT_ON_WRONG):
            result_data["correct_answer"] = question.correct_answer

        # Update stats
        if is_correct:
            question.times_correct += 1
        else:
            question.times_incorrect += 1
        db.session.commit()

        logger.info(
            "Coding evaluation complete: question_id=%s, language=%s, correct=%s, hint_passed=%s, hidden_passed=%s, duration=%.2fs",
            question.id, language, is_correct, hint_passed, hidden_passed, elapsed,
        )

        return result_data

    except Exception as e:
        elapsed = time.monotonic() - eval_start
        logger.error("Coding evaluation failed: question_id=%s, language=%s, duration=%.2fs, error=%s", question.id, language, elapsed, e)
        return {"correct": False, "grade": "Error", "message": f"Sandbox error: {str(e)}", "hint_passed": False, "hidden_passed": False}


def _run_sandbox_test(language, player_code, test_input, expected_output):
    """Run player code in a sandboxed container and compare output."""
    # Wrap the player code with input injection based on language
    wrapped_code = _wrap_code(language, player_code, test_input)

    result = run_code(language, wrapped_code)

    if not result["success"]:
        logger.info(
            "Sandbox execution failed: language=%s, timed_out=%s, stderr=%.500s",
            language, result["timed_out"], result["stderr"],
        )
        return False

    actual = result["stdout"].strip()
    expected = expected_output.strip()
    matched = _normalize_compare(actual, expected)

    if not matched:
        logger.info(
            "Output mismatch: language=%s, expected=%.200s, actual=%.200s",
            language, expected, actual,
        )

    return matched


def _wrap_code(language, player_code, test_input):
    """Wrap player code with input injection for the target language."""
    if language in ("python",):
        return f"""import json

inputs = {test_input}
for k, v in inputs.items():
    globals()[k] = v

{player_code}

print(result)
"""
    elif language in ("java",):
        # Sanitise smart/curly quotes that break javac
        player_code = player_code.replace("\u201c", '"').replace("\u201d", '"')
        player_code = player_code.replace("\u2018", "'").replace("\u2019", "'")

        main_method = (
            f"    public static void main(String[] args) {{\n"
            f"        String input = {json.dumps(test_input)};\n"
            f"        System.out.println(solve(input));\n"
            f"    }}"
        )

        if "class Solution" in player_code:
            # Player provided a full class — inject main before the last }
            last_brace = player_code.rfind("}")
            return (
                "import java.util.*;\n\n"
                + player_code[:last_brace]
                + "\n" + main_method + "\n"
                + player_code[last_brace:]
            )

        return f"""import java.util.*;

public class Solution {{
    {player_code}

{main_method}
}}
"""
    elif language in ("typescript",):
        return f"""const inputs = {test_input};
Object.assign(globalThis, inputs);

{player_code}

console.log(typeof result === "object" ? JSON.stringify(result) : result);
"""
    else:
        return player_code


def _normalize_compare(actual, expected):
    """Normalize and compare code outputs (handles set ordering, whitespace, etc.)."""
    import ast

    def normalize(s):
        s = s.strip().replace(" ", "")
        try:
            val = ast.literal_eval(s)
            if isinstance(val, set):
                return frozenset(val)
            return val
        except (ValueError, SyntaxError):
            return s.lower()

    return normalize(actual) == normalize(expected)

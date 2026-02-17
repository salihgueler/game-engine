"""Question evaluation services using Strands Agents and AgentCore Code Interpreter."""
import json
import logging
import os

from strands import Agent, tool
from strands.models import BedrockModel

from src.extensions import db
from src.models.models import GlobalConfig

logger = logging.getLogger(__name__)


def _get_config_flag(key, default="false"):
    """Get a global config boolean flag."""
    cfg = db.session.query(GlobalConfig).filter_by(key=key).first()
    return (cfg.value.lower() == "true") if cfg else (default.lower() == "true")


def _get_bedrock_model():
    """Create a Bedrock model instance."""
    region = os.environ.get("AWS_REGION", "us-west-2")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
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
    """Evaluate coding answer using AgentCore Code Interpreter sandbox."""
    # Check auto-pass
    if _get_config_flag(GlobalConfig.AUTO_PASS_ALL):
        return {"correct": True, "grade": "Correct", "message": "Auto-pass enabled.", "hint_passed": True, "hidden_passed": True}

    region = os.environ.get("AWS_REGION", "us-west-2")

    try:
        from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

        code_client = CodeInterpreter(region)
        code_client.start()

        hint_passed = False
        hidden_passed = False

        try:
            # Test with hint input/output
            if question.code_sample_input and question.code_sample_output:
                hint_passed = _run_code_test(code_client, player_code, question.code_sample_input, question.code_sample_output)

            # Test with hidden input/output
            if question.code_hidden_input and question.code_hidden_output:
                hidden_passed = _run_code_test(code_client, player_code, question.code_hidden_input, question.code_hidden_output)
        finally:
            code_client.stop()

        is_correct = hint_passed and hidden_passed

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

        return result_data

    except Exception as e:
        logger.error(f"Coding evaluation failed: {e}")
        return {"correct": False, "grade": "Error", "message": f"Sandbox error: {str(e)}", "hint_passed": False, "hidden_passed": False}


def _run_code_test(code_client, player_code, test_input, expected_output):
    """Run player code in sandbox with given input and check against expected output."""
    # Build the execution code: set up inputs, run player code, capture result
    exec_code = f"""
import json

# Set up input variables
inputs = {test_input}
for k, v in inputs.items():
    globals()[k] = v

# Player code
{player_code}

# Output the result
print("RESULT:" + str(result))
"""
    try:
        response = code_client.invoke("executeCode", {
            "language": "python",
            "code": exec_code,
        })

        # Extract output from stream
        output_text = ""
        for event in response.get("stream", []):
            result_data = event.get("result", {})
            for content in result_data.get("content", []):
                if content.get("type") == "text":
                    output_text += content.get("text", "")

        # Check if result matches expected output
        if "RESULT:" in output_text:
            actual = output_text.split("RESULT:")[-1].strip()
            expected = expected_output.strip()
            return _normalize_compare(actual, expected)

        return False
    except Exception as e:
        logger.error(f"Code test execution failed: {e}")
        return False


def _normalize_compare(actual, expected):
    """Normalize and compare code outputs (handles set ordering, whitespace, etc.)."""
    def normalize(s):
        s = s.strip().replace(" ", "")
        # Try to evaluate as Python literal for set/list comparison
        try:
            import ast
            val = ast.literal_eval(s)
            if isinstance(val, set):
                return frozenset(val)
            return val
        except (ValueError, SyntaxError):
            return s.lower()

    return normalize(actual) == normalize(expected)

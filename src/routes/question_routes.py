"""Question CRUD and evaluation routes — questions are independent entities."""
import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from src.extensions import db, limiter
from src.models.models import Question, QuestionCategory, QuestionDifficulty, GamePlayer, GamePlayerAnswer
from src.schemas import AnswerSubmit, QuestionCreate, QuestionImport, QuestionUpdate
from src.services.auth import cognito_token_required, player_token_required, _either_token_required
from src.services.audit import log_action
from src.services.evaluator import evaluate_coding, evaluate_general_knowledge, evaluate_multiple_choice

question_bp = Blueprint("questions", __name__, url_prefix="/api/questions")


def _serialize_question_admin(q):
    """Full serialization for admin endpoints — includes correct answers and hidden test data."""
    data = {
        "id": q.id,
        "question_number": q.question_number,
        "category": q.category.value,
        "difficulty": q.difficulty.value,
        "description": q.description,
        "correct_answer": q.correct_answer,
        "hint": q.hint,
        "question_banks": [{"id": b.id, "name": b.name} for b in q.question_banks],
        "times_passed": q.times_passed,
        "times_hint_used": q.times_hint_used,
        "times_incorrect": q.times_incorrect,
        "times_correct": q.times_correct,
        "created_at": q.created_at.isoformat(),
        "updated_at": q.updated_at.isoformat(),
    }
    if q.category == QuestionCategory.MultipleChoice and q.options:
        try:
            data["options"] = json.loads(q.options)
        except json.JSONDecodeError:
            data["options"] = []
    if q.category == QuestionCategory.Coding:
        data["code_programming_language"] = q.code_programming_language
        data["code_sample_input"] = q.code_sample_input
        data["code_sample_output"] = q.code_sample_output
        data["code_hidden_input"] = q.code_hidden_input
        data["code_hidden_output"] = q.code_hidden_output
    return data


def _serialize_question_player(q):
    """Player-safe serialization — no correct answers, no hidden test cases."""
    data = {
        "id": q.id,
        "question_number": q.question_number,
        "category": q.category.value,
        "difficulty": q.difficulty.value,
        "description": q.description,
        "hint": q.hint,
        "question_banks": [{"id": b.id, "name": b.name} for b in q.question_banks],
        "created_at": q.created_at.isoformat(),
        "updated_at": q.updated_at.isoformat(),
    }
    if q.category == QuestionCategory.MultipleChoice and q.options:
        try:
            data["options"] = json.loads(q.options)
        except json.JSONDecodeError:
            data["options"] = []
    if q.category == QuestionCategory.Coding:
        data["code_programming_language"] = q.code_programming_language
        data["code_sample_input"] = q.code_sample_input
        data["code_sample_output"] = q.code_sample_output
    return data


def _is_admin_request():
    """Check if the current request was authenticated with a Cognito admin token."""
    return hasattr(request, "cognito_user") and request.cognito_user is not None


def _serialize_question(q):
    """Auto-select serializer based on whether the request is from an admin."""
    if _is_admin_request():
        return _serialize_question_admin(q)
    return _serialize_question_player(q)


def _next_question_number():
    """Get the next global sequential question number."""
    last = Question.query.order_by(Question.question_number.desc()).first()
    return (last.question_number + 1) if last else 1


@question_bp.route("", methods=["GET"])
@_either_token_required
def list_questions():
    """List all questions. Supports optional filtering by programming language and difficulty.
    ---
    tags:
      - Questions
    security:
      - Bearer: []
    parameters:
      - name: language
        in: query
        type: string
        required: false
        description: Filter by programming language (e.g. Python, Java)
      - name: difficulty
        in: query
        type: string
        required: false
        enum: [Easy, Moderate, Hard]
        description: Filter by difficulty level
    responses:
      200:
        description: List of questions, optionally filtered
        schema:
          type: array
          items:
            $ref: '#/definitions/Question'
    definitions:
      Question:
        type: object
        properties:
          id:
            type: integer
          question_number:
            type: integer
            description: Globally unique sequential question number
          category:
            type: string
            enum: [Coding, General, MultipleChoice]
          difficulty:
            type: string
            enum: [Easy, Moderate, Hard]
          description:
            type: string
          correct_answer:
            type: string
          hint:
            type: string
          question_banks:
            type: array
            description: Banks this question is assigned to
            items:
              type: object
              properties:
                id:
                  type: integer
                name:
                  type: string
          options:
            type: array
            items:
              type: string
            description: Multiple choice options (only for MultipleChoice category)
          code_programming_language:
            type: string
            description: Programming language (only for Coding category)
          code_sample_input:
            type: string
            description: Sample input (only for Coding category)
          code_sample_output:
            type: string
            description: Expected sample output (only for Coding category)
          code_hidden_input:
            type: string
            description: Hidden test input (only for Coding category)
          code_hidden_output:
            type: string
            description: Expected hidden test output (only for Coding category)
          times_passed:
            type: integer
          times_hint_used:
            type: integer
          times_incorrect:
            type: integer
          times_correct:
            type: integer
          created_at:
            type: string
            format: date-time
          updated_at:
            type: string
            format: date-time
    """
    query = Question.query

    language = request.args.get("language")
    if language:
        query = query.filter(Question.code_programming_language.ilike(language))

    difficulty = request.args.get("difficulty")
    if difficulty:
        try:
            diff_enum = QuestionDifficulty(difficulty)
            query = query.filter(Question.difficulty == diff_enum)
        except ValueError:
            pass

    questions = query.order_by(Question.question_number).all()
    return jsonify([_serialize_question(q) for q in questions])


@question_bp.route("", methods=["POST"])
@cognito_token_required
def create_question():
    """Create a new standalone question. The question is not assigned to any bank. Use the bank assignment endpoint to add it to banks.
    ---
    tags:
      - Questions
    security:
      - Bearer: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - category
            - difficulty
            - description
            - correct_answer
          properties:
            category:
              type: string
              enum: [Coding, General, MultipleChoice]
            difficulty:
              type: string
              enum: [Easy, Moderate, Hard]
            description:
              type: string
              description: The question text/prompt
            correct_answer:
              type: string
            hint:
              type: string
            options:
              type: array
              items:
                type: string
              description: Required for MultipleChoice questions
            code_programming_language:
              type: string
              description: Programming language for Coding questions
            code_sample_input:
              type: string
              description: Sample input for Coding questions
            code_sample_output:
              type: string
              description: Expected output for sample input
            code_hidden_input:
              type: string
              description: Hidden test input for Coding questions
            code_hidden_output:
              type: string
              description: Expected output for hidden test input
    responses:
      201:
        description: Question created
        schema:
          $ref: '#/definitions/Question'
      400:
        description: Validation error
    """
    try:
        data = QuestionCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    q = Question(
        question_number=_next_question_number(),
        category=QuestionCategory(data.category),
        difficulty=QuestionDifficulty(data.difficulty),
        description=data.description,
        correct_answer=data.correct_answer,
        hint=data.hint,
        options=json.dumps(data.options) if data.options else None,
        code_programming_language=data.code_programming_language,
        code_sample_input=data.code_sample_input,
        code_sample_output=data.code_sample_output,
        code_hidden_input=data.code_hidden_input,
        code_hidden_output=data.code_hidden_output,
    )
    db.session.add(q)
    db.session.commit()
    log_action("create", "question", q.id, {"category": data.category, "difficulty": data.difficulty})
    return jsonify(_serialize_question(q)), 201


@question_bp.route("/<int:question_id>", methods=["GET"])
@_either_token_required
def get_question(question_id):
    """Get a question by ID. Response includes the list of banks this question belongs to.
    ---
    tags:
      - Questions
    security:
      - Bearer: []
    parameters:
      - name: question_id
        in: path
        type: integer
        required: true
        description: Question ID
    responses:
      200:
        description: Question details
        schema:
          $ref: '#/definitions/Question'
      404:
        description: Question not found
    """
    q = Question.query.get_or_404(question_id)
    return jsonify(_serialize_question(q))


@question_bp.route("/<int:question_id>", methods=["PUT"])
@cognito_token_required
def update_question(question_id):
    """Update a question. Only provided fields are updated.
    ---
    tags:
      - Questions
    security:
      - Bearer: []
    parameters:
      - name: question_id
        in: path
        type: integer
        required: true
        description: Question ID
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            category:
              type: string
              enum: [Coding, General, MultipleChoice]
            difficulty:
              type: string
              enum: [Easy, Moderate, Hard]
            description:
              type: string
            correct_answer:
              type: string
            hint:
              type: string
            options:
              type: array
              items:
                type: string
            code_programming_language:
              type: string
            code_sample_input:
              type: string
            code_sample_output:
              type: string
            code_hidden_input:
              type: string
            code_hidden_output:
              type: string
    responses:
      200:
        description: Question updated
        schema:
          $ref: '#/definitions/Question'
      400:
        description: Validation error
      404:
        description: Question not found
    """
    q = Question.query.get_or_404(question_id)
    try:
        data = QuestionUpdate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    if data.category:
        q.category = QuestionCategory(data.category)
    if data.difficulty:
        q.difficulty = QuestionDifficulty(data.difficulty)
    if data.description is not None:
        q.description = data.description
    if data.correct_answer is not None:
        q.correct_answer = data.correct_answer
    if data.hint is not None:
        q.hint = data.hint
    if data.options is not None:
        q.options = json.dumps(data.options)
    if data.code_programming_language is not None:
        q.code_programming_language = data.code_programming_language
    if data.code_sample_input is not None:
        q.code_sample_input = data.code_sample_input
    if data.code_sample_output is not None:
        q.code_sample_output = data.code_sample_output
    if data.code_hidden_input is not None:
        q.code_hidden_input = data.code_hidden_input
    if data.code_hidden_output is not None:
        q.code_hidden_output = data.code_hidden_output

    db.session.commit()
    log_action("update", "question", question_id)
    return jsonify(_serialize_question(q))


@question_bp.route("/<int:question_id>", methods=["DELETE"])
@cognito_token_required
def delete_question(question_id):
    """Delete a question. This also removes it from all banks it was assigned to.
    ---
    tags:
      - Questions
    security:
      - Bearer: []
    parameters:
      - name: question_id
        in: path
        type: integer
        required: true
        description: Question ID
    responses:
      200:
        description: Question deleted
        schema:
          type: object
          properties:
            message:
              type: string
              example: Deleted
      404:
        description: Question not found
    """
    q = Question.query.get_or_404(question_id)
    db.session.delete(q)
    db.session.commit()
    log_action("delete", "question", question_id)
    return jsonify({"message": "Deleted"})


@question_bp.route("", methods=["DELETE"])
@cognito_token_required
def delete_all_questions():
    """Delete all questions. This also removes all bank assignments.
    ---
    tags:
      - Questions
    security:
      - Bearer: []
    responses:
      200:
        description: All questions deleted
        schema:
          type: object
          properties:
            deleted:
              type: integer
    """
    count = Question.query.count()
    db.session.execute(db.text("DELETE FROM question_bank_questions"))
    Question.query.delete()
    db.session.commit()
    log_action("delete_all", "question", None, {"deleted_count": count})
    return jsonify({"deleted": count})


# --- Evaluation, Hints, Export/Import ---

@question_bp.route("/<int:question_id>/answer", methods=["POST"])
@_either_token_required
@limiter.limit("15 per minute")
def submit_answer(question_id):
    """Submit an answer for evaluation. The evaluation strategy depends on the question category (MultipleChoice, General, or Coding).
    Optionally accepts game_id and player_id to record the answer for server-side scoring.
    ---
    tags:
      - Questions
    security:
      - Bearer: []
    parameters:
      - name: question_id
        in: path
        type: integer
        required: true
        description: Question ID
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - answer
          properties:
            answer:
              type: string
              description: The player's answer
            game_id:
              type: integer
              description: Game ID (optional, for server-side score tracking)
            player_id:
              type: integer
              description: Player ID (optional, for server-side score tracking)
    responses:
      200:
        description: Evaluation result
        schema:
          type: object
          properties:
            correct:
              type: boolean
            message:
              type: string
      400:
        description: Validation error or unknown question category
      404:
        description: Question not found
    """
    q = Question.query.get_or_404(question_id)
    body = request.get_json() or {}

    try:
        data = AnswerSubmit(**body)
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    if q.category == QuestionCategory.MultipleChoice:
        result = evaluate_multiple_choice(q, data.answer)
    elif q.category == QuestionCategory.General:
        result = evaluate_general_knowledge(q, data.answer)
    elif q.category == QuestionCategory.Coding:
        result = evaluate_coding(q, data.answer)
    else:
        return jsonify({"error": "Unknown question category"}), 400

    # Record the answer for server-side scoring if game_id and player_id provided
    game_id = body.get("game_id")
    player_id = body.get("player_id")
    if game_id and player_id:
        gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
        if gp and not gp.completed_at:
            existing = GamePlayerAnswer.query.filter_by(
                game_player_id=gp.id, question_id=question_id
            ).first()
            if existing:
                # Update the existing answer (player retried the question)
                existing.correct = result.get("correct", False)
                existing.answered_at = datetime.now(timezone.utc)
            else:
                answer_record = GamePlayerAnswer(
                    game_player_id=gp.id,
                    question_id=question_id,
                    correct=result.get("correct", False),
                )
                db.session.add(answer_record)
            db.session.commit()

    return jsonify(result)


@question_bp.route("/<int:question_id>/hint", methods=["GET"])
@_either_token_required
def get_hint(question_id):
    """Get a hint for a question. Increments the times_hint_used counter. For MultipleChoice questions, also removes one incorrect option. For Coding questions, includes sample input/output.
    ---
    tags:
      - Questions
    security:
      - Bearer: []
    parameters:
      - name: question_id
        in: path
        type: integer
        required: true
        description: Question ID
    responses:
      200:
        description: Hint for the question
        schema:
          type: object
          properties:
            hint:
              type: string
            reduced_options:
              type: array
              items:
                type: string
              description: Remaining options after removing one wrong answer (MultipleChoice only)
            sample_input:
              type: string
              description: Sample input (Coding only)
            sample_output:
              type: string
              description: Sample output (Coding only)
      404:
        description: Question not found
    """
    q = Question.query.get_or_404(question_id)

    q.times_hint_used += 1
    db.session.commit()

    hint_data = {"hint": q.hint}

    if q.category == QuestionCategory.MultipleChoice and q.options:
        try:
            options = json.loads(q.options)
            correct = q.correct_answer.strip()
            incorrect = [o for o in options if o.strip() != correct]
            if incorrect:
                removed = incorrect[0]
                remaining = [o for o in options if o != removed]
                hint_data["reduced_options"] = remaining
                hint_data["hint"] = f"One wrong answer removed. Remaining options: {remaining}"
        except json.JSONDecodeError:
            pass
    elif q.category == QuestionCategory.Coding:
        hint_data["sample_input"] = q.code_sample_input
        hint_data["sample_output"] = q.code_sample_output

    return jsonify(hint_data)


@question_bp.route("/export", methods=["GET"])
@cognito_token_required
def export_questions():
    """Export all questions as JSON. Returns all questions regardless of bank assignment.
    ---
    tags:
      - Questions
    security:
      - Bearer: []
    responses:
      200:
        description: Exported questions
        schema:
          type: object
          properties:
            questions:
              type: array
              items:
                type: object
                properties:
                  question_number:
                    type: integer
                  category:
                    type: string
                  difficulty:
                    type: string
                  description:
                    type: string
                  correct_answer:
                    type: string
                  hint:
                    type: string
                  options:
                    type: array
                    items:
                      type: string
                  code_sample_input:
                    type: string
                  code_sample_output:
                    type: string
                  code_hidden_input:
                    type: string
                  code_hidden_output:
                    type: string
    """
    questions = Question.query.order_by(Question.question_number).all()

    export_data = {"questions": []}
    for q in questions:
        qdata = {
            "question_number": q.question_number,
            "category": q.category.value,
            "difficulty": q.difficulty.value,
            "description": q.description,
            "correct_answer": q.correct_answer,
            "hint": q.hint,
        }
        if q.options:
            try:
                qdata["options"] = json.loads(q.options)
            except json.JSONDecodeError:
                qdata["options"] = []
        if q.category == QuestionCategory.Coding:
            qdata["code_programming_language"] = q.code_programming_language
            qdata["code_sample_input"] = q.code_sample_input
            qdata["code_sample_output"] = q.code_sample_output
            qdata["code_hidden_input"] = q.code_hidden_input
            qdata["code_hidden_output"] = q.code_hidden_output
        export_data["questions"].append(qdata)

    return jsonify(export_data)


@question_bp.route("/import", methods=["POST"])
@cognito_token_required
def import_questions():
    """Import questions from JSON. Creates standalone questions that are not assigned to any bank. Use the bank assignment endpoint to add them to banks after import.
    ---
    tags:
      - Questions
    security:
      - Bearer: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - questions
          properties:
            questions:
              type: array
              items:
                type: object
                required:
                  - category
                  - difficulty
                  - description
                  - correct_answer
                properties:
                  category:
                    type: string
                    enum: [Coding, General, MultipleChoice]
                  difficulty:
                    type: string
                    enum: [Easy, Moderate, Hard]
                  description:
                    type: string
                  correct_answer:
                    type: string
                  hint:
                    type: string
                  options:
                    type: array
                    items:
                      type: string
                  code_programming_language:
                    type: string
                  code_sample_input:
                    type: string
                  code_sample_output:
                    type: string
                  code_hidden_input:
                    type: string
                  code_hidden_output:
                    type: string
    responses:
      201:
        description: Questions imported
        schema:
          type: object
          properties:
            imported:
              type: integer
              description: Number of questions imported
            questions:
              type: array
              items:
                $ref: '#/definitions/Question'
      400:
        description: Validation error
    """
    try:
        data = QuestionImport(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    imported = []
    for qdata in data.questions:
        q = Question(
            question_number=_next_question_number(),
            category=QuestionCategory(qdata.category),
            difficulty=QuestionDifficulty(qdata.difficulty),
            description=qdata.description,
            correct_answer=qdata.correct_answer,
            hint=qdata.hint,
            options=json.dumps(qdata.options) if qdata.options else None,
            code_programming_language=qdata.code_programming_language,
            code_sample_input=qdata.code_sample_input,
            code_sample_output=qdata.code_sample_output,
            code_hidden_input=qdata.code_hidden_input,
            code_hidden_output=qdata.code_hidden_output,
        )
        db.session.add(q)
        db.session.flush()
        imported.append(_serialize_question(q))

    db.session.commit()
    log_action("import", "question", None, {"imported_count": len(imported)})
    return jsonify({"imported": len(imported), "questions": imported}), 201

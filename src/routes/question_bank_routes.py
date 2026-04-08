"""Question Bank CRUD and question assignment routes."""

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from src.extensions import db
from src.models.models import Question, QuestionBank
from src.routes.question_routes import _serialize_question
from src.schemas import BankAssignQuestions, QuestionBankCreate, QuestionBankUpdate
from src.services.auth import token_required

bank_bp = Blueprint("banks", __name__, url_prefix="/api/banks")


def _serialize_bank(bank):
    return {
        "id": bank.id,
        "name": bank.name,
        "question_count": len(bank.questions),
        "created_at": bank.created_at.isoformat(),
        "updated_at": bank.updated_at.isoformat(),
    }


@bank_bp.route("", methods=["GET"])
@token_required
def list_banks():
    """List all question banks.
    ---
    tags:
      - Question Banks
    security:
      - Bearer: []
    responses:
      200:
        description: List of question banks
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              name:
                type: string
              question_count:
                type: integer
              created_at:
                type: string
                format: date-time
              updated_at:
                type: string
                format: date-time
    """
    banks = QuestionBank.query.all()
    return jsonify([_serialize_bank(b) for b in banks])


@bank_bp.route("", methods=["POST"])
@token_required
def create_bank():
    """Create a new question bank.
    ---
    tags:
      - Question Banks
    security:
      - Bearer: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - name
          properties:
            name:
              type: string
              description: Unique name for the question bank
    responses:
      201:
        description: Question bank created
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            question_count:
              type: integer
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
      400:
        description: Validation error
      409:
        description: A bank with this name already exists
    """
    try:
        data = QuestionBankCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    if QuestionBank.query.filter_by(name=data.name).first():
        return jsonify({"error": "A bank with this name already exists"}), 409

    bank = QuestionBank(name=data.name)
    db.session.add(bank)
    db.session.commit()
    return jsonify(_serialize_bank(bank)), 201


@bank_bp.route("/<int:bank_id>", methods=["GET"])
@token_required
def get_bank(bank_id):
    """Get a question bank by ID.
    ---
    tags:
      - Question Banks
    security:
      - Bearer: []
    parameters:
      - name: bank_id
        in: path
        type: integer
        required: true
        description: Question bank ID
    responses:
      200:
        description: Question bank details
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            question_count:
              type: integer
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
      404:
        description: Question bank not found
    """
    bank = QuestionBank.query.get_or_404(bank_id)
    return jsonify(_serialize_bank(bank))


@bank_bp.route("/<int:bank_id>", methods=["PUT"])
@token_required
def update_bank(bank_id):
    """Update a question bank.
    ---
    tags:
      - Question Banks
    security:
      - Bearer: []
    parameters:
      - name: bank_id
        in: path
        type: integer
        required: true
        description: Question bank ID
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              description: New name for the question bank
    responses:
      200:
        description: Question bank updated
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            question_count:
              type: integer
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
      400:
        description: Validation error
      404:
        description: Question bank not found
    """
    bank = QuestionBank.query.get_or_404(bank_id)
    try:
        data = QuestionBankUpdate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    if data.name:
        bank.name = data.name
    db.session.commit()
    return jsonify(_serialize_bank(bank))


@bank_bp.route("/<int:bank_id>", methods=["DELETE"])
@token_required
def delete_bank(bank_id):
    """Delete a question bank. Does not delete the questions themselves, only the bank and its associations.
    ---
    tags:
      - Question Banks
    security:
      - Bearer: []
    parameters:
      - name: bank_id
        in: path
        type: integer
        required: true
        description: Question bank ID
    responses:
      200:
        description: Question bank deleted
        schema:
          type: object
          properties:
            message:
              type: string
              example: Deleted
      404:
        description: Question bank not found
    """
    bank = QuestionBank.query.get_or_404(bank_id)

    # Delete events that reference this bank first
    for event in list(bank.events):
        db.session.delete(event)

    db.session.delete(bank)
    db.session.commit()
    return jsonify({"message": "Deleted"})


# --- Question assignment to banks ---

@bank_bp.route("/<int:bank_id>/questions", methods=["GET"])
@token_required
def list_bank_questions(bank_id):
    """List all questions assigned to a bank. Supports optional filtering by programming language and difficulty.
    ---
    tags:
      - Bank Questions
    security:
      - Bearer: []
    parameters:
      - name: bank_id
        in: path
        type: integer
        required: true
        description: Question bank ID
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
        description: List of questions assigned to this bank, optionally filtered
        schema:
          type: array
          items:
            $ref: '#/definitions/Question'
      404:
        description: Question bank not found
    """
    bank = QuestionBank.query.get_or_404(bank_id)
    questions = bank.questions

    language = request.args.get("language")
    difficulty = request.args.get("difficulty")

    if language:
        questions = [q for q in questions if q.code_programming_language and q.code_programming_language.lower() == language.lower()]

    if difficulty:
        questions = [q for q in questions if q.difficulty.value == difficulty]

    return jsonify([_serialize_question(q) for q in questions])


@bank_bp.route("/<int:bank_id>/questions", methods=["POST"])
@token_required
def assign_questions(bank_id):
    """Assign existing questions to a bank. Questions are independent entities and can belong to multiple banks.
    ---
    tags:
      - Bank Questions
    security:
      - Bearer: []
    parameters:
      - name: bank_id
        in: path
        type: integer
        required: true
        description: Question bank ID
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - question_ids
          properties:
            question_ids:
              type: array
              items:
                type: integer
              description: List of question IDs to assign to this bank
    responses:
      200:
        description: Assignment results
        schema:
          type: object
          properties:
            assigned:
              type: array
              items:
                type: integer
              description: IDs of newly assigned questions
            already_assigned:
              type: array
              items:
                type: integer
              description: IDs of questions already in this bank
            not_found:
              type: array
              items:
                type: integer
              description: IDs that do not match any existing question
      400:
        description: Validation error
      404:
        description: Question bank not found
    """
    bank = QuestionBank.query.get_or_404(bank_id)
    try:
        data = BankAssignQuestions(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    added = []
    already = []
    not_found = []
    for qid in data.question_ids:
        q = Question.query.get(qid)
        if not q:
            not_found.append(qid)
            continue
        if q in bank.questions:
            already.append(qid)
            continue
        bank.questions.append(q)
        added.append(qid)

    db.session.commit()
    return jsonify({
        "assigned": added,
        "already_assigned": already,
        "not_found": not_found,
    })


@bank_bp.route("/<int:bank_id>/questions", methods=["DELETE"])
@token_required
def unassign_questions(bank_id):
    """Remove questions from a bank. Does not delete the questions themselves, only removes the association.
    ---
    tags:
      - Bank Questions
    security:
      - Bearer: []
    parameters:
      - name: bank_id
        in: path
        type: integer
        required: true
        description: Question bank ID
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - question_ids
          properties:
            question_ids:
              type: array
              items:
                type: integer
              description: List of question IDs to remove from this bank
    responses:
      200:
        description: Removal results
        schema:
          type: object
          properties:
            removed:
              type: array
              items:
                type: integer
              description: IDs of questions removed from the bank
            not_in_bank:
              type: array
              items:
                type: integer
              description: IDs that were not assigned to this bank
      400:
        description: Validation error
      404:
        description: Question bank not found
    """
    bank = QuestionBank.query.get_or_404(bank_id)
    try:
        data = BankAssignQuestions(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    removed = []
    not_in_bank = []
    for qid in data.question_ids:
        q = Question.query.get(qid)
        if q and q in bank.questions:
            bank.questions.remove(q)
            removed.append(qid)
        else:
            not_in_bank.append(qid)

    db.session.commit()
    return jsonify({"removed": removed, "not_in_bank": not_in_bank})


@bank_bp.route("/<int:bank_id>/questions/export", methods=["GET"])
@token_required
def export_bank_questions(bank_id):
    """Export all questions from a bank as JSON.
    ---
    tags:
      - Bank Questions
    security:
      - Bearer: []
    parameters:
      - name: bank_id
        in: path
        type: integer
        required: true
        description: Question bank ID
    responses:
      200:
        description: Exported questions for this bank
        schema:
          type: object
          properties:
            bank_name:
              type: string
            questions:
              type: array
              items:
                $ref: '#/definitions/Question'
      404:
        description: Question bank not found
    """
    bank = QuestionBank.query.get_or_404(bank_id)
    return jsonify({
        "bank_name": bank.name,
        "questions": [_serialize_question(q) for q in bank.questions],
    })

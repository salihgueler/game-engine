"""Event CRUD routes (admin)."""

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from src.extensions import db
from src.models.models import Event, QuestionBank
from src.schemas import EventCreate, EventUpdate
from src.services.auth import cognito_token_required
from src.services.audit import log_action

event_bp = Blueprint("events", __name__, url_prefix="/api/events")


def _serialize_event(event):
    return {
        "id": event.id,
        "name": event.name,
        "access_code": event.access_code,
        "question_bank_id": event.question_bank_id,
        "question_bank_name": event.question_bank.name if event.question_bank else None,
        "theme": event.theme,
        "custom_welcome_text": event.custom_welcome_text,
        "survey_link": event.survey_link,
        "code_expiry": event.code_expiry.isoformat() if event.code_expiry else None,
        "created_at": event.created_at.isoformat(),
        "updated_at": event.updated_at.isoformat(),
    }


@event_bp.route("", methods=["GET"])
@cognito_token_required
def list_events():
    """List all events.
    ---
    tags:
      - Events
    security:
      - Bearer: []
    responses:
      200:
        description: List of events
        schema:
          type: array
          items:
            $ref: '#/definitions/Event'
    definitions:
      Event:
        type: object
        properties:
          id:
            type: integer
          name:
            type: string
          access_code:
            type: string
            description: 8-character alphanumeric code for players to join
          question_bank_id:
            type: integer
          question_bank_name:
            type: string
          theme:
            type: string
          custom_welcome_text:
            type: string
          created_at:
            type: string
            format: date-time
          updated_at:
            type: string
            format: date-time
    """
    events = Event.query.all()
    return jsonify([_serialize_event(e) for e in events])


@event_bp.route("", methods=["POST"])
@cognito_token_required
def create_event():
    """Create a new event. Requires an existing question bank.
    ---
    tags:
      - Events
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
            - theme
            - question_bank_id
          properties:
            name:
              type: string
            theme:
              type: string
            question_bank_id:
              type: integer
              description: ID of the question bank to use
            custom_welcome_text:
              type: string
    responses:
      201:
        description: Event created
        schema:
          $ref: '#/definitions/Event'
      400:
        description: Validation error or no question banks exist
      404:
        description: Question bank not found
      409:
        description: An event with this name already exists
    """
    try:
        data = EventCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    if not QuestionBank.query.first():
        return jsonify({"error": "No question banks available. Please create a Question Bank first."}), 400

    bank = QuestionBank.query.get(data.question_bank_id)
    if not bank:
        return jsonify({"error": f"Question bank with id {data.question_bank_id} not found"}), 404

    if Event.query.filter_by(name=data.name).first():
        return jsonify({"error": "An event with this name already exists"}), 409

    event = Event(
        name=data.name,
        theme=data.theme,
        question_bank_id=data.question_bank_id,
        custom_welcome_text=data.custom_welcome_text,
        survey_link=data.survey_link,
        code_expiry=data.code_expiry,
    )
    db.session.add(event)
    db.session.commit()
    log_action("create", "event", event.id, {"name": event.name})
    return jsonify(_serialize_event(event)), 201


@event_bp.route("/<int:event_id>", methods=["GET"])
@cognito_token_required
def get_event(event_id):
    """Get an event by ID.
    ---
    tags:
      - Events
    security:
      - Bearer: []
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Event details
        schema:
          $ref: '#/definitions/Event'
      404:
        description: Event not found
    """
    event = Event.query.get_or_404(event_id)
    return jsonify(_serialize_event(event))


@event_bp.route("/<int:event_id>", methods=["PUT"])
@cognito_token_required
def update_event(event_id):
    """Update an event.
    ---
    tags:
      - Events
    security:
      - Bearer: []
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            theme:
              type: string
            question_bank_id:
              type: integer
            custom_welcome_text:
              type: string
    responses:
      200:
        description: Event updated
        schema:
          $ref: '#/definitions/Event'
      400:
        description: Validation error
      404:
        description: Event or question bank not found
    """
    event = Event.query.get_or_404(event_id)
    try:
        data = EventUpdate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    if data.name is not None:
        event.name = data.name
    if data.theme is not None:
        event.theme = data.theme
    if data.question_bank_id is not None:
        bank = QuestionBank.query.get(data.question_bank_id)
        if not bank:
            return jsonify({"error": f"Question bank with id {data.question_bank_id} not found"}), 404
        event.question_bank_id = data.question_bank_id
    if data.custom_welcome_text is not None:
        event.custom_welcome_text = data.custom_welcome_text
    if data.survey_link is not None:
        event.survey_link = data.survey_link
    if data.code_expiry is not None:
        event.code_expiry = data.code_expiry

    db.session.commit()
    log_action("update", "event", event_id)
    return jsonify(_serialize_event(event))


@event_bp.route("/<int:event_id>", methods=["DELETE"])
@cognito_token_required
def delete_event(event_id):
    """Delete an event.
    ---
    tags:
      - Events
    security:
      - Bearer: []
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Event deleted
        schema:
          type: object
          properties:
            message:
              type: string
              example: Deleted
      404:
        description: Event not found
    """
    event = Event.query.get_or_404(event_id)
    event_name = event.name
    db.session.delete(event)
    db.session.commit()
    log_action("delete", "event", event_id, {"name": event_name})
    return jsonify({"message": "Deleted"})

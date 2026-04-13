"""Audit log routes — admin-only access to the audit trail."""
from flask import Blueprint, jsonify, request

from src.models.models import AuditLog
from src.services.auth import cognito_token_required

audit_bp = Blueprint("audit", __name__, url_prefix="/api/audit")


@audit_bp.route("", methods=["GET"])
@cognito_token_required
def list_audit_logs():
    """List audit log entries with optional filtering and pagination.
    ---
    tags:
      - Audit
    security:
      - Bearer: []
    parameters:
      - name: action
        in: query
        type: string
        required: false
        description: Filter by action type (e.g. create, update, delete, config_change)
      - name: resource_type
        in: query
        type: string
        required: false
        description: Filter by resource type (e.g. event, question, config)
      - name: actor
        in: query
        type: string
        required: false
        description: Filter by actor email
      - name: limit
        in: query
        type: integer
        required: false
        description: Max entries to return (default 50, max 200)
      - name: offset
        in: query
        type: integer
        required: false
        description: Offset for pagination (default 0)
    responses:
      200:
        description: List of audit log entries
    """
    query = AuditLog.query

    action_filter = request.args.get("action")
    if action_filter:
        query = query.filter(AuditLog.action == action_filter)

    resource_filter = request.args.get("resource_type")
    if resource_filter:
        query = query.filter(AuditLog.resource_type == resource_filter)

    actor_filter = request.args.get("actor")
    if actor_filter:
        query = query.filter(AuditLog.actor.ilike(f"%{actor_filter}%"))

    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    total = query.count()
    entries = (
        query
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return jsonify({
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "actor": e.actor,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "details": e.details,
            }
            for e in entries
        ],
    })

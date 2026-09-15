from flask import Blueprint, jsonify

from ..auth import require_auth, require_role
from ..db import get_db

logs_bp = Blueprint("logs", __name__)


@logs_bp.route("", methods=["GET"])
@require_auth
@require_role("admin")
def list_logs():
    conn = get_db()
    rows = conn.execute(
        "SELECT actor, action, detail, created_at FROM operation_logs ORDER BY created_at DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return jsonify({"logs": [dict(r) for r in rows]})

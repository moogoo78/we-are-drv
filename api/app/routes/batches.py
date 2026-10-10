import json
import secrets

from flask import Blueprint, g, jsonify, request

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action

batches_bp = Blueprint("batches", __name__)

EDITABLE_FIELDS = (
    "name", "start_date", "end_date", "location", "capacity", "register_start", "register_end",
    "status", "auto_close", "quiz_open", "survey_open",
)
FLAG_FIELDS = ("auto_close", "quiz_open", "survey_open")
ALLOWED_STATUS = {"upcoming", "open", "full", "closed"}


@batches_bp.route("", methods=["GET"])
def list_batches():
    conn = get_db()
    rows = conn.execute(
        """SELECT b.id, b.name, b.start_date, b.end_date, b.location, b.capacity, b.status,
                  b.register_start, b.register_end, b.auto_close, b.quiz_open, b.survey_open,
                  (SELECT COUNT(*) FROM registrations r
                     WHERE r.batch_id = b.id AND r.status IN ('pending', 'approved')) AS registered_count
           FROM batches b
           ORDER BY b.start_date DESC"""
    ).fetchall()
    conn.close()
    return jsonify({"batches": [dict(r) for r in rows]})


@batches_bp.route("", methods=["POST"])
@require_auth
@require_role("admin")
def create_batch():
    data = request.get_json(silent=True) or {}
    required = ["name", "start_date", "end_date", "location", "capacity"]
    if not all(data.get(f) for f in required):
        return jsonify({"error": "請填寫梯次名稱、日期、地點與名額"}), 400

    conn = get_db()
    cur = conn.execute(
        """INSERT INTO batches (name, start_date, end_date, location, capacity, register_start, register_end, status,
                                auto_close, material_key)
           VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, 'upcoming'), ?, ?)""",
        (
            data["name"], data["start_date"], data["end_date"], data["location"], data["capacity"],
            data.get("register_start") or None, data.get("register_end") or None, data.get("status") or None,
            1 if data.get("auto_close") in (True, 1, "1", "true", "on") else 0, secrets.token_urlsafe(12),
        ),
    )
    conn.commit()
    batch = conn.execute("SELECT * FROM batches WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    log_action(g.user["name"], "建立梯次", f'建立「{data["name"]}」')
    return jsonify({"batch": dict(batch)}), 201


@batches_bp.route("/<int:batch_id>", methods=["PATCH"])
@require_auth
@require_role("admin")
def update_batch(batch_id):
    data = request.get_json(silent=True) or {}
    conn = get_db()
    existing = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "找不到梯次"}), 404

    if "status" in data and data["status"] not in ALLOWED_STATUS:
        conn.close()
        return jsonify({"error": "無效的梯次狀態"}), 400
    fields = {k: data[k] for k in EDITABLE_FIELDS if k in data}
    for k in FLAG_FIELDS:
        if k in fields:
            fields[k] = 1 if fields[k] in (True, 1, "1", "true", "on") else 0
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE batches SET {set_clause} WHERE id = ?", (*fields.values(), batch_id))
        conn.commit()
    batch = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    conn.close()
    log_action(g.user["name"], "更新梯次", f"梯次 #{batch_id} → {json.dumps(data, ensure_ascii=False)}")
    return jsonify({"batch": dict(batch)})


@batches_bp.route("/admin", methods=["GET"])
@require_auth
def list_batches_admin():
    """後台用梯次清單（含教材下載金鑰）。"""
    conn = get_db()
    rows = conn.execute(
        """SELECT b.*,
                  (SELECT COUNT(*) FROM registrations r
                     WHERE r.batch_id = b.id AND r.status IN ('pending', 'approved')) AS registered_count
           FROM batches b ORDER BY b.start_date DESC"""
    ).fetchall()
    conn.close()
    return jsonify({"batches": [dict(r) for r in rows]})

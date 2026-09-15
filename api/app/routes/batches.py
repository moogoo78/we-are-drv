import json

from flask import Blueprint, g, jsonify, request

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action

batches_bp = Blueprint("batches", __name__)


@batches_bp.route("", methods=["GET"])
def list_batches():
    conn = get_db()
    rows = conn.execute(
        """SELECT b.id, b.name, b.start_date, b.end_date, b.location, b.capacity, b.status,
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
        """INSERT INTO batches (name, start_date, end_date, location, capacity, register_start, register_end, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, 'upcoming'))""",
        (
            data["name"], data["start_date"], data["end_date"], data["location"], data["capacity"],
            data.get("register_start"), data.get("register_end"), data.get("status"),
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

    status = data.get("status") or existing["status"]
    capacity = data.get("capacity") or existing["capacity"]
    conn.execute("UPDATE batches SET status = ?, capacity = ? WHERE id = ?", (status, capacity, batch_id))
    conn.commit()
    batch = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    conn.close()
    log_action(g.user["name"], "更新梯次", f"梯次 #{batch_id} → {json.dumps(data, ensure_ascii=False)}")
    return jsonify({"batch": dict(batch)})

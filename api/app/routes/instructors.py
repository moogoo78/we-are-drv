from flask import Blueprint, g, jsonify, request

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action

instructors_bp = Blueprint("instructors", __name__)

EDITABLE_FIELDS = ("name", "title", "phone", "email", "note")


@instructors_bp.route("", methods=["GET"])
@require_auth
def list_instructors():
    conn = get_db()
    rows = conn.execute(
        """SELECT i.id, i.name, i.title, i.phone, i.email, i.note, i.created_at,
                  COALESCE(SUM(cs.hours), 0) AS total_hours,
                  COUNT(cs.id) AS session_count
           FROM instructors i
           LEFT JOIN course_sessions cs ON cs.instructor_id = i.id
           GROUP BY i.id
           ORDER BY i.id"""
    ).fetchall()
    conn.close()
    return jsonify({"instructors": [dict(r) for r in rows]})


@instructors_bp.route("", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def create_instructor():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        return jsonify({"error": "請填寫講師姓名"}), 400

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO instructors (name, title, phone, email, note) VALUES (?, ?, ?, ?, ?)",
        (name, data.get("title") or None, data.get("phone") or None, data.get("email") or None, data.get("note") or None),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM instructors WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()

    log_action(g.user["name"], "新增講師", name)
    return jsonify({"instructor": dict(row)}), 201


@instructors_bp.route("/<int:instructor_id>", methods=["PATCH"])
@require_auth
@require_role("admin", "staff")
def update_instructor(instructor_id):
    data = request.get_json(silent=True) or {}
    conn = get_db()
    existing = conn.execute("SELECT * FROM instructors WHERE id = ?", (instructor_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "找不到講師"}), 404

    fields = {k: data[k] for k in EDITABLE_FIELDS if k in data}
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE instructors SET {set_clause} WHERE id = ?", (*fields.values(), instructor_id))
        conn.commit()
    row = conn.execute("SELECT * FROM instructors WHERE id = ?", (instructor_id,)).fetchone()
    conn.close()

    log_action(g.user["name"], "更新講師", f'#{instructor_id}（{row["name"]}）')
    return jsonify({"instructor": dict(row)})

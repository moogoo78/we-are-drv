from flask import Blueprint, g, jsonify, request

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action

courses_bp = Blueprint("courses", __name__)

EDITABLE_FIELDS = ("session_date", "start_time", "topic", "instructor_id", "hours", "material_url")

SESSION_SELECT = """SELECT cs.id, cs.batch_id, cs.session_date, cs.start_time, cs.topic, cs.hours,
                            cs.material_url, cs.instructor_id, i.name AS instructor_name
                     FROM course_sessions cs
                     LEFT JOIN instructors i ON i.id = cs.instructor_id"""


@courses_bp.route("", methods=["GET"])
@require_auth
def list_sessions():
    batch_id = request.args.get("batch_id")
    conn = get_db()
    if batch_id:
        rows = conn.execute(
            f"{SESSION_SELECT} WHERE cs.batch_id = ? ORDER BY cs.session_date, cs.start_time", (batch_id,)
        ).fetchall()
    else:
        rows = conn.execute(f"{SESSION_SELECT} ORDER BY cs.session_date, cs.start_time").fetchall()
    conn.close()
    return jsonify({"sessions": [dict(r) for r in rows]})


@courses_bp.route("", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def create_session():
    data = request.get_json(silent=True) or {}
    required = ["batch_id", "session_date", "topic"]
    if not all(data.get(f) for f in required):
        return jsonify({"error": "請填寫梯次、日期與課程名稱"}), 400

    conn = get_db()
    batch = conn.execute("SELECT id FROM batches WHERE id = ?", (data["batch_id"],)).fetchone()
    if not batch:
        conn.close()
        return jsonify({"error": "找不到指定梯次"}), 400

    cur = conn.execute(
        """INSERT INTO course_sessions (batch_id, session_date, start_time, topic, instructor_id, hours, material_url)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            data["batch_id"], data["session_date"], data.get("start_time") or None, data["topic"],
            data.get("instructor_id") or None, data.get("hours") or 2, data.get("material_url") or None,
        ),
    )
    conn.commit()
    row = conn.execute(f"{SESSION_SELECT} WHERE cs.id = ?", (cur.lastrowid,)).fetchone()
    conn.close()

    log_action(g.user["name"], "新增課程", data["topic"])
    return jsonify({"session": dict(row)}), 201


@courses_bp.route("/<int:session_id>", methods=["PATCH"])
@require_auth
@require_role("admin", "staff")
def update_session(session_id):
    data = request.get_json(silent=True) or {}
    conn = get_db()
    existing = conn.execute("SELECT * FROM course_sessions WHERE id = ?", (session_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "找不到課程"}), 404

    fields = {k: data[k] for k in EDITABLE_FIELDS if k in data}
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE course_sessions SET {set_clause} WHERE id = ?", (*fields.values(), session_id))
        conn.commit()
    row = conn.execute(f"{SESSION_SELECT} WHERE cs.id = ?", (session_id,)).fetchone()
    conn.close()

    log_action(g.user["name"], "更新課程", f'#{session_id}（{row["topic"]}）')
    return jsonify({"session": dict(row)})


@courses_bp.route("/<int:session_id>", methods=["DELETE"])
@require_auth
@require_role("admin", "staff")
def delete_session(session_id):
    conn = get_db()
    existing = conn.execute("SELECT * FROM course_sessions WHERE id = ?", (session_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "找不到課程"}), 404
    conn.execute("DELETE FROM course_sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

    log_action(g.user["name"], "刪除課程", existing["topic"])
    return "", 204

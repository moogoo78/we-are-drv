from flask import Blueprint, g, jsonify, request, send_from_directory

from ..auth import require_auth, require_role
from ..db import get_db
from ..files import remove_file, save_image, upload_path
from ..log import log_action

instructors_bp = Blueprint("instructors", __name__)

EDITABLE_FIELDS = ("name", "title", "phone", "email", "note")


@instructors_bp.route("", methods=["GET"])
@require_auth
def list_instructors():
    conn = get_db()
    rows = conn.execute(
        """SELECT i.id, i.name, i.title, i.phone, i.email, i.note, i.created_at,
                  i.signature_path IS NOT NULL AS has_signature,
                  MIN(cs.session_date) AS first_date, MAX(cs.session_date) AS last_date,
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


@instructors_bp.route("/<int:instructor_id>/sessions", methods=["GET"])
@require_auth
def instructor_sessions(instructor_id):
    """授課課程／授課日期查詢，可依日期區間篩選。"""
    conditions = ["cs.instructor_id = ?"]
    params = [instructor_id]
    if request.args.get("from"):
        conditions.append("cs.session_date >= ?")
        params.append(request.args["from"])
    if request.args.get("to"):
        conditions.append("cs.session_date <= ?")
        params.append(request.args["to"])
    conn = get_db()
    rows = conn.execute(
        f"""SELECT cs.id, cs.session_date, cs.start_time, cs.topic, cs.hours, b.id AS batch_id, b.name AS batch_name, b.location
            FROM course_sessions cs JOIN batches b ON b.id = cs.batch_id
            WHERE {" AND ".join(conditions)}
            ORDER BY cs.session_date DESC, cs.start_time""",
        params,
    ).fetchall()
    conn.close()
    sessions = [dict(r) for r in rows]
    return jsonify({"sessions": sessions, "total_hours": sum(s["hours"] or 0 for s in sessions)})


@instructors_bp.route("/<int:instructor_id>/signature", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def upload_signature(instructor_id):
    """上傳教官簽名檔（術科測驗表單使用）。"""
    file = request.files.get("signature")
    if not file or not file.filename:
        return jsonify({"error": "請選擇簽名檔"}), 400
    conn = get_db()
    existing = conn.execute("SELECT * FROM instructors WHERE id = ?", (instructor_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "找不到講師"}), 404
    filename = save_image(file, "signatures")
    if not filename:
        conn.close()
        return jsonify({"error": "簽名檔僅接受 JPG 或 PNG"}), 400
    conn.execute("UPDATE instructors SET signature_path = ? WHERE id = ?", (filename, instructor_id))
    conn.commit()
    conn.close()
    remove_file("signatures", existing["signature_path"])
    log_action(g.user["name"], "上傳簽名檔", existing["name"])
    return jsonify({"ok": True})


@instructors_bp.route("/<int:instructor_id>/signature", methods=["GET"])
@require_auth
def get_signature(instructor_id):
    conn = get_db()
    row = conn.execute("SELECT signature_path FROM instructors WHERE id = ?", (instructor_id,)).fetchone()
    conn.close()
    if not row or not row["signature_path"]:
        return "", 404
    return send_from_directory(upload_path("signatures"), row["signature_path"])

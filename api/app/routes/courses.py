from flask import Blueprint, g, jsonify, request, send_from_directory

from ..auth import require_auth, require_role
from ..db import get_db
from ..files import remove_file, save_image, save_material, upload_path
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


# ---- 課程照片 ----

@courses_bp.route("/photos", methods=["GET"])
@require_auth
def list_photos():
    batch_id = request.args.get("batch_id")
    conn = get_db()
    sql = """SELECT p.id, p.batch_id, p.file_path, p.caption, p.created_at, b.name AS batch_name
             FROM course_photos p JOIN batches b ON b.id = p.batch_id"""
    rows = conn.execute(
        sql + (" WHERE p.batch_id = ?" if batch_id else "") + " ORDER BY p.created_at DESC",
        (batch_id,) if batch_id else (),
    ).fetchall()
    conn.close()
    return jsonify({"photos": [dict(r) for r in rows]})


@courses_bp.route("/photos", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def upload_photo():
    batch_id = request.form.get("batch_id")
    files = [f for f in request.files.getlist("photo") if f and f.filename]
    if not batch_id or not files:
        return jsonify({"error": "請選擇梯次與照片"}), 400
    conn = get_db()
    batch = conn.execute("SELECT name FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if not batch:
        conn.close()
        return jsonify({"error": "找不到指定梯次"}), 400
    saved = 0
    for f in files:
        filename = save_image(f, "photos")
        if filename:
            conn.execute(
                "INSERT INTO course_photos (batch_id, file_path, caption) VALUES (?, ?, ?)",
                (batch_id, filename, request.form.get("caption") or None),
            )
            saved += 1
    conn.commit()
    conn.close()
    if not saved:
        return jsonify({"error": "照片僅接受 JPG 或 PNG"}), 400
    log_action(g.user["name"], "上傳課程照片", f'{batch["name"]} {saved} 張')
    return jsonify({"saved": saved}), 201


@courses_bp.route("/photos/<int:photo_id>", methods=["DELETE"])
@require_auth
@require_role("admin", "staff")
def delete_photo(photo_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM course_photos WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "找不到照片"}), 404
    conn.execute("DELETE FROM course_photos WHERE id = ?", (photo_id,))
    conn.commit()
    conn.close()
    remove_file("photos", row["file_path"])
    log_action(g.user["name"], "刪除課程照片", f"#{photo_id}")
    return "", 204


# ---- 課程教材 ----

@courses_bp.route("/materials", methods=["GET"])
@require_auth
def list_materials():
    batch_id = request.args.get("batch_id")
    conn = get_db()
    sql = """SELECT m.id, m.batch_id, m.instructor_id, m.title, m.file_path, m.original_name, m.visibility, m.created_at,
                    b.name AS batch_name, i.name AS instructor_name
             FROM course_materials m
             LEFT JOIN batches b ON b.id = m.batch_id
             LEFT JOIN instructors i ON i.id = m.instructor_id"""
    rows = conn.execute(
        sql + (" WHERE m.batch_id = ?" if batch_id else "") + " ORDER BY m.created_at DESC",
        (batch_id,) if batch_id else (),
    ).fetchall()
    conn.close()
    return jsonify({"materials": [dict(r) for r in rows]})


@courses_bp.route("/materials", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def upload_material():
    f = request.files.get("file")
    title = (request.form.get("title") or "").strip()
    if not f or not f.filename or not title:
        return jsonify({"error": "請填寫教材名稱並選擇檔案"}), 400
    visibility = request.form.get("visibility")
    if visibility not in ("public", "enrolled"):
        visibility = "enrolled"
    filename = save_material(f)
    if not filename:
        return jsonify({"error": "不支援的檔案格式（接受 PDF、Office、ODF、ZIP、圖片）"}), 400
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO course_materials (batch_id, instructor_id, title, file_path, original_name, visibility)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (request.form.get("batch_id") or None, request.form.get("instructor_id") or None,
         title, filename, f.filename, visibility),
    )
    conn.commit()
    conn.close()
    log_action(g.user["name"], "上傳教材", title)
    return jsonify({"id": cur.lastrowid}), 201


@courses_bp.route("/materials/<int:material_id>", methods=["DELETE"])
@require_auth
@require_role("admin", "staff")
def delete_material(material_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM course_materials WHERE id = ?", (material_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "找不到教材"}), 404
    conn.execute("DELETE FROM course_materials WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()
    remove_file("materials", row["file_path"])
    log_action(g.user["name"], "刪除教材", row["title"])
    return "", 204


@courses_bp.route("/materials/<int:material_id>/download", methods=["GET"])
@require_auth
def download_material(material_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM course_materials WHERE id = ?", (material_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "找不到教材"}), 404
    return send_from_directory(upload_path("materials"), row["file_path"], as_attachment=True,
                               download_name=row["original_name"] or row["file_path"])

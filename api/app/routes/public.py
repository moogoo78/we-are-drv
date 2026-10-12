"""前台免登入 API：縣市設定、公告、課程時程、講師、講義、課程照片、行政區里別。"""
import json

from flask import Blueprint, Response, jsonify, request, send_from_directory

from ..db import get_db
from ..files import upload_path
from ..geo import VILLAGES
from ..site import public_config

public_bp = Blueprint("public", __name__)


@public_bp.route("/site", methods=["GET"])
def site():
    return jsonify(public_config())


@public_bp.route("/site-config.js", methods=["GET"])
def site_config_js():
    """供前台頁面以 <script> 同步載入，讓 site.js 在畫面顯示前換上縣市文字。"""
    body = "window.SITE = " + json.dumps(public_config(), ensure_ascii=False) + ";\n"
    return Response(body, mimetype="application/javascript", headers={"Cache-Control": "no-cache"})


@public_bp.route("/villages", methods=["GET"])
def villages():
    return jsonify({"districts": VILLAGES, "order": list(VILLAGES)})  # JSON 鍵會被排序，另附原始順序


@public_bp.route("/announcements", methods=["GET"])
def list_announcements():
    limit = min(int(request.args.get("limit", 20) or 20), 100)
    category = request.args.get("category")
    conn = get_db()
    rows = conn.execute(
        f"""SELECT id, title, category, pinned, published_at FROM announcements
            WHERE published_at <= date('now') {"AND category = ?" if category else ""}
            ORDER BY pinned DESC, published_at DESC, id DESC LIMIT ?""",
        ((category, limit) if category else (limit,)),
    ).fetchall()
    conn.close()
    return jsonify({"announcements": [dict(r) for r in rows]})


@public_bp.route("/announcements/<int:ann_id>", methods=["GET"])
def get_announcement(ann_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM announcements WHERE id = ? AND published_at <= date('now')", (ann_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "找不到公告"}), 404
    return jsonify({"announcement": dict(row)})


@public_bp.route("/sessions", methods=["GET"])
def list_sessions():
    """課程時程查詢（含歷屆梯次）。"""
    batch_id = request.args.get("batch_id")
    conn = get_db()
    rows = conn.execute(
        f"""SELECT cs.id, cs.batch_id, b.name AS batch_name, b.location, cs.session_date, cs.start_time,
                   cs.topic, cs.hours, i.id AS instructor_id, i.name AS instructor_name, i.title AS instructor_title
            FROM course_sessions cs
            JOIN batches b ON b.id = cs.batch_id
            LEFT JOIN instructors i ON i.id = cs.instructor_id
            {"WHERE cs.batch_id = ?" if batch_id else ""}
            ORDER BY b.start_date DESC, cs.session_date, cs.start_time""",
        (batch_id,) if batch_id else (),
    ).fetchall()
    conn.close()
    return jsonify({"sessions": [dict(r) for r in rows]})


@public_bp.route("/instructors", methods=["GET"])
def list_instructors():
    """講師查詢：僅公開姓名、專長與授課課程。"""
    conn = get_db()
    instructors = [dict(r) for r in conn.execute("SELECT id, name, title FROM instructors ORDER BY id").fetchall()]
    topics = conn.execute(
        """SELECT DISTINCT instructor_id, topic FROM course_sessions WHERE instructor_id IS NOT NULL ORDER BY topic"""
    ).fetchall()
    conn.close()
    by_instructor = {}
    for t in topics:
        by_instructor.setdefault(t["instructor_id"], []).append(t["topic"])
    for i in instructors:
        i["topics"] = by_instructor.get(i["id"], [])
    return jsonify({"instructors": instructors})


def _material_rows(conn, where, params):
    return conn.execute(
        f"""SELECT m.id, m.title, m.original_name, m.visibility, m.created_at, m.batch_id,
                   b.name AS batch_name, i.name AS instructor_name
            FROM course_materials m
            LEFT JOIN batches b ON b.id = m.batch_id
            LEFT JOIN instructors i ON i.id = m.instructor_id
            WHERE {where} ORDER BY m.created_at DESC""",
        params,
    ).fetchall()


@public_bp.route("/materials", methods=["GET"])
def list_materials():
    """公開講義；帶 batch_id + key（報名成功後取得的 QR Code 連結）可取得該梯次學員教材。"""
    batch_id = request.args.get("batch_id")
    key = request.args.get("key")
    conn = get_db()
    public = [dict(r) for r in _material_rows(conn, "m.visibility = 'public'", ())]
    enrolled = []
    batch_name = None
    if batch_id and key:
        batch = conn.execute("SELECT id, name, material_key FROM batches WHERE id = ?", (batch_id,)).fetchone()
        if not batch or batch["material_key"] != key:
            conn.close()
            return jsonify({"error": "教材連結無效，請確認 QR Code 是否正確"}), 403
        batch_name = batch["name"]
        enrolled = [dict(r) for r in _material_rows(conn, "m.visibility = 'enrolled' AND m.batch_id = ?", (batch_id,))]
    conn.close()
    return jsonify({"public": public, "enrolled": enrolled, "batch_name": batch_name})


@public_bp.route("/materials/<int:material_id>/download", methods=["GET"])
def download_material(material_id):
    conn = get_db()
    row = conn.execute(
        """SELECT m.*, b.material_key FROM course_materials m
           LEFT JOIN batches b ON b.id = m.batch_id WHERE m.id = ?""",
        (material_id,),
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "找不到教材"}), 404
    if row["visibility"] != "public" and (not row["material_key"] or request.args.get("key") != row["material_key"]):
        return jsonify({"error": "此教材僅限該梯次學員下載"}), 403
    return send_from_directory(upload_path("materials"), row["file_path"], as_attachment=True,
                               download_name=row["original_name"] or row["file_path"])


@public_bp.route("/photos", methods=["GET"])
def list_photos():
    """課程實況照片。"""
    batch_id = request.args.get("batch_id")
    conn = get_db()
    rows = conn.execute(
        f"""SELECT p.id, p.batch_id, b.name AS batch_name, p.caption, p.created_at
            FROM course_photos p JOIN batches b ON b.id = p.batch_id
            {"WHERE p.batch_id = ?" if batch_id else ""}
            ORDER BY b.start_date DESC, p.created_at DESC""",
        (batch_id,) if batch_id else (),
    ).fetchall()
    conn.close()
    return jsonify({"photos": [dict(r) for r in rows]})


@public_bp.route("/photos/<int:photo_id>", methods=["GET"])
def get_photo(photo_id):
    conn = get_db()
    row = conn.execute("SELECT file_path FROM course_photos WHERE id = ?", (photo_id,)).fetchone()
    conn.close()
    if not row:
        return "", 404
    return send_from_directory(upload_path("photos"), row["file_path"])

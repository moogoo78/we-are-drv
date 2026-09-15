import json
import os
import secrets
import sqlite3
import time

from flask import Blueprint, g, jsonify, request, send_from_directory

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action

registrations_bp = Blueprint("registrations", __name__)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

REQUIRED_FIELDS = [
    "batch_id", "name", "id_number", "birth_date", "sex", "phone", "email",
    "district", "address", "support_pref", "meal_pref",
]

ALLOWED_STATUS = {"pending", "approved", "rejected", "waitlist", "needs_more_info"}


def parse_certs(v):
    if not v:
        return []
    try:
        parsed = json.loads(v)
        return parsed if isinstance(parsed, list) else [str(v)]
    except (ValueError, TypeError):
        return [str(v)]


def registration_to_dict(row):
    reg = dict(row)
    reg["existing_certs"] = json.loads(reg.get("existing_certs") or "[]")
    reg["agree_consent"] = bool(reg.get("agree_consent"))
    return reg


@registrations_bp.route("", methods=["POST"])
def create_registration():
    b = request.form
    missing = [f for f in REQUIRED_FIELDS if not b.get(f)]
    if missing:
        return jsonify({"error": f"缺少必填欄位：{', '.join(missing)}"}), 400
    if b.get("agree_consent") != "true":
        return jsonify({"error": "請同意個人資料蒐集告知事項"}), 400

    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify({"error": "請上傳證件照"}), 400
    if photo.mimetype not in ("image/jpeg", "image/png"):
        return jsonify({"error": "僅接受 JPG 或 PNG 格式的證件照"}), 400

    conn = get_db()
    try:
        batch = conn.execute("SELECT * FROM batches WHERE id = ?", (b["batch_id"],)).fetchone()
        if not batch:
            return jsonify({"error": "找不到指定梯次"}), 400
        if batch["status"] != "open":
            return jsonify({"error": "此梯次目前未開放報名"}), 400

        dupe = conn.execute(
            "SELECT id FROM registrations WHERE batch_id = ? AND id_number = ?",
            (b["batch_id"], b["id_number"]),
        ).fetchone()
        if dupe:
            return jsonify({"error": "此身分證字號已於本梯次報名過"}), 409

        ext = ".png" if photo.mimetype == "image/png" else ".jpg"
        filename = f"{int(time.time() * 1000)}-{secrets.token_hex(4)}{ext}"
        photo.save(os.path.join(UPLOAD_DIR, filename))

        try:
            cur = conn.execute(
                """INSERT INTO registrations
                    (batch_id, name, id_number, birth_date, sex, phone, email, district, address,
                     occupation, unit_village, support_pref, meal_pref, other_needs, existing_certs,
                     cert_number, photo_path, agree_consent)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    b["batch_id"], b["name"], b["id_number"], b["birth_date"], b["sex"], b["phone"], b["email"],
                    b["district"], b["address"], b.get("occupation") or None, b.get("unit_village") or None,
                    b["support_pref"], b["meal_pref"], b.get("other_needs") or None,
                    json.dumps(parse_certs(b.get("existing_certs")), ensure_ascii=False),
                    b.get("cert_number") or None, filename,
                ),
            )
        except sqlite3.IntegrityError:
            os.remove(os.path.join(UPLOAD_DIR, filename))
            return jsonify({"error": "此身分證字號已於本梯次報名過"}), 409

        reg_id = cur.lastrowid
        reg_no = f"B{b['batch_id']}-{reg_id:06d}"
        conn.execute("UPDATE registrations SET reg_no = ? WHERE id = ?", (reg_no, reg_id))
        conn.commit()
        return jsonify({"reg_no": reg_no, "status": "pending"}), 201
    finally:
        conn.close()


@registrations_bp.route("/lookup", methods=["GET"])
def lookup():
    id_number = request.args.get("id_number")
    birth_date = request.args.get("birth_date")
    if not id_number or not birth_date:
        return jsonify({"error": "請輸入身分證字號與出生年月日"}), 400

    conn = get_db()
    rows = conn.execute(
        """SELECT r.reg_no, r.status, r.review_note, r.created_at, r.reviewed_at, r.meal_pref,
                  b.name AS batch_name, b.start_date, b.end_date, b.location
           FROM registrations r JOIN batches b ON b.id = r.batch_id
           WHERE r.id_number = ? AND r.birth_date = ?
           ORDER BY r.created_at DESC""",
        (id_number, birth_date),
    ).fetchall()
    conn.close()

    if not rows:
        return jsonify({"error": "查無報名紀錄，請確認輸入資料是否正確"}), 404
    return jsonify({"registrations": [dict(r) for r in rows]})


@registrations_bp.route("", methods=["GET"])
@require_auth
def list_registrations():
    batch_id = request.args.get("batch_id")
    status = request.args.get("status")
    q = request.args.get("q")
    page = max(int(request.args.get("page", 1) or 1), 1)
    page_size = min(int(request.args.get("page_size", 20) or 20), 100)
    offset = (page - 1) * page_size

    conditions = []
    params = []
    if batch_id:
        conditions.append("r.batch_id = ?")
        params.append(batch_id)
    if status:
        conditions.append("r.status = ?")
        params.append(status)
    if q:
        conditions.append("(r.name LIKE ? OR r.id_number LIKE ? OR r.reg_no LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like]
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    conn = get_db()
    rows = conn.execute(
        f"""SELECT r.id, r.reg_no, r.name, r.id_number, r.sex, r.phone, r.status, r.created_at,
                   b.name AS batch_name
            FROM registrations r JOIN batches b ON b.id = r.batch_id
            {where}
            ORDER BY r.created_at DESC
            LIMIT ? OFFSET ?""",
        (*params, page_size, offset),
    ).fetchall()
    total = conn.execute(f"SELECT COUNT(*) AS n FROM registrations r {where}", params).fetchone()["n"]
    conn.close()

    return jsonify({
        "registrations": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@registrations_bp.route("/<int:reg_id>", methods=["GET"])
@require_auth
def get_registration(reg_id):
    conn = get_db()
    row = conn.execute(
        """SELECT r.*, b.name AS batch_name FROM registrations r
           JOIN batches b ON b.id = r.batch_id WHERE r.id = ?""",
        (reg_id,),
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "找不到報名資料"}), 404
    return jsonify({"registration": registration_to_dict(row)})


@registrations_bp.route("/<int:reg_id>", methods=["PATCH"])
@require_auth
@require_role("admin", "staff")
def review_registration(reg_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ALLOWED_STATUS:
        return jsonify({"error": "無效的審核狀態"}), 400

    conn = get_db()
    existing = conn.execute("SELECT * FROM registrations WHERE id = ?", (reg_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "找不到報名資料"}), 404

    conn.execute(
        """UPDATE registrations SET status = ?, review_note = ?, reviewed_by = ?, reviewed_at = datetime('now')
           WHERE id = ?""",
        (status, data.get("review_note"), g.user["name"], reg_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM registrations WHERE id = ?", (reg_id,)).fetchone()
    conn.close()

    log_action(g.user["name"], "審核報名", f'{row["reg_no"]}（{row["name"]}） → {status}')
    return jsonify({"registration": registration_to_dict(row)})


@registrations_bp.route("/<int:reg_id>/photo", methods=["GET"])
@require_auth
def get_photo(reg_id):
    conn = get_db()
    row = conn.execute("SELECT photo_path FROM registrations WHERE id = ?", (reg_id,)).fetchone()
    conn.close()
    if not row or not row["photo_path"]:
        return "", 404
    return send_from_directory(UPLOAD_DIR, row["photo_path"])

import json
import os
import secrets
import sqlite3
import time

from flask import Blueprint, g, jsonify, request, send_from_directory

from ..auth import require_auth, require_role
from ..db import get_db
from ..geo import KEELUNG_VILLAGES, is_valid_village
from ..log import log_action
from ..members import json_list

registrations_bp = Blueprint("registrations", __name__)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

REQUIRED_FIELDS = [
    "batch_id", "name", "id_number", "birth_date", "sex", "phone", "email",
    "district", "address", "meal_pref",
]

OPTIONAL_TEXT_FIELDS = [
    "occupation", "unit_village", "other_needs", "cert_number", "home_phone", "education",
    "job_title", "emergency_name", "emergency_relation", "emergency_phone",
]

TRAINING_FIELDS = ("checked_in", "written_score", "written_passed", "practical_passed")

ALLOWED_STATUS = {"pending", "approved", "rejected", "waitlist", "needs_more_info"}


def registration_to_dict(row):
    reg = dict(row)
    reg["existing_certs"] = json_list(reg.get("existing_certs"))
    reg["specialty"] = json_list(reg.get("specialty"))
    reg["agree_consent"] = bool(reg.get("agree_consent"))
    return reg


def close_batch_if_full(conn, batch_id):
    """梯次設定「額滿自動關閉」時，報名人數達名額即改為已額滿。"""
    batch = conn.execute("SELECT capacity, status, auto_close FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if not batch or not batch["auto_close"] or batch["status"] != "open":
        return
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM registrations WHERE batch_id = ? AND status IN ('pending', 'approved')",
        (batch_id,),
    ).fetchone()["n"]
    if n >= batch["capacity"]:
        conn.execute("UPDATE batches SET status = 'full' WHERE id = ?", (batch_id,))


@registrations_bp.route("", methods=["POST"])
def create_registration():
    b = request.form
    missing = [f for f in REQUIRED_FIELDS if not b.get(f)]
    if missing:
        return jsonify({"error": f"缺少必填欄位：{', '.join(missing)}"}), 400
    if b.get("agree_consent") != "true":
        return jsonify({"error": "請同意個人資料蒐集告知事項"}), 400
    if b["district"] not in KEELUNG_VILLAGES:
        return jsonify({"error": "請選擇正確的行政區"}), 400
    village = b.get("village") or None
    if village and not is_valid_village(b["district"], village):
        return jsonify({"error": "里別與行政區不符"}), 400

    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify({"error": "請上傳證件照"}), 400
    if photo.mimetype not in ("image/jpeg", "image/png"):
        return jsonify({"error": "僅接受 JPG 或 PNG 格式的證件照"}), 400
    photo.stream.seek(0, os.SEEK_END)
    too_big = photo.stream.tell() > 5 * 1024 * 1024
    photo.stream.seek(0)
    if too_big:
        return jsonify({"error": "證件照檔案過大，請確認在 5MB 以內"}), 400

    conn = get_db()
    try:
        batch = conn.execute("SELECT * FROM batches WHERE id = ?", (b["batch_id"],)).fetchone()
        if not batch:
            return jsonify({"error": "找不到指定梯次"}), 400
        if batch["status"] != "open":
            return jsonify({"error": "此梯次目前未開放報名"}), 400

        dupe = conn.execute(
            "SELECT id FROM registrations WHERE batch_id = ? AND id_number = ?",
            (b["batch_id"], b["id_number"].strip().upper()),
        ).fetchone()
        if dupe:
            return jsonify({"error": "此身分證字號已於本梯次報名過"}), 409

        ext = ".png" if photo.mimetype == "image/png" else ".jpg"
        filename = f"{int(time.time() * 1000)}-{secrets.token_hex(4)}{ext}"
        photo.save(os.path.join(UPLOAD_DIR, filename))

        try:
            values = {
                "batch_id": b["batch_id"],
                "id_number": b["id_number"].strip().upper(),
                **{f: b[f] for f in REQUIRED_FIELDS if f not in ("batch_id", "id_number")},
                **{f: (b.get(f) or "").strip() or None for f in OPTIONAL_TEXT_FIELDS},
                "village": village,
                "support_pref": "願意" if b.get("support_pref") in ("願意", "true") else "未表示",
                "existing_certs": json.dumps(json_list(b.get("existing_certs")), ensure_ascii=False),
                "specialty": json.dumps(json_list(b.get("specialty")), ensure_ascii=False),
                "photo_path": filename,
                "agree_consent": 1,
            }
            cur = conn.execute(
                f"INSERT INTO registrations ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
                tuple(values.values()),
            )
        except sqlite3.IntegrityError:
            os.remove(os.path.join(UPLOAD_DIR, filename))
            return jsonify({"error": "此身分證字號已於本梯次報名過"}), 409

        reg_id = cur.lastrowid
        reg_no = f"B{b['batch_id']}-{reg_id:06d}"
        conn.execute("UPDATE registrations SET reg_no = ? WHERE id = ?", (reg_no, reg_id))
        close_batch_if_full(conn, b["batch_id"])
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
        (id_number.strip().upper(), birth_date),
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
    district = request.args.get("district")
    page = max(int(request.args.get("page", 1) or 1), 1)
    page_size = min(int(request.args.get("page_size", 20) or 20), 500)
    offset = (page - 1) * page_size

    conditions = []
    params = []
    if batch_id:
        conditions.append("r.batch_id = ?")
        params.append(batch_id)
    if status:
        conditions.append("r.status = ?")
        params.append(status)
    if district:
        conditions.append("r.district = ?")
        params.append(district)
    if q:
        conditions.append("(r.name LIKE ? OR r.id_number LIKE ? OR r.reg_no LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like]
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    conn = get_db()
    rows = conn.execute(
        f"""SELECT r.id, r.reg_no, r.name, r.id_number, r.sex, r.phone, r.email, r.status, r.created_at,
                   r.district, r.village, r.checked_in, r.written_score, r.written_passed, r.practical_passed,
                   r.notified_at, r.batch_id, b.name AS batch_name
            FROM registrations r JOIN batches b ON b.id = r.batch_id
            {where}
            ORDER BY r.created_at DESC, r.id DESC
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


def _bool_or_none(v):
    if v is None or v == "":
        return None
    return 1 if v in (True, 1, "1", "true") else 0


@registrations_bp.route("/<int:reg_id>/training", methods=["PATCH"])
@require_auth
@require_role("admin", "staff")
def update_training(reg_id):
    """登錄報到、學科成績、術科合格等培訓紀錄。"""
    data = request.get_json(silent=True) or {}
    fields = {}
    for k in TRAINING_FIELDS:
        if k not in data:
            continue
        if k == "written_score":
            try:
                fields[k] = None if data[k] in (None, "") else int(data[k])
            except (TypeError, ValueError):
                return jsonify({"error": "學科成績需為數字"}), 400
        elif k == "checked_in":
            fields[k] = _bool_or_none(data[k]) or 0
        else:
            fields[k] = _bool_or_none(data[k])
    if not fields:
        return jsonify({"error": "沒有要更新的欄位"}), 400

    conn = get_db()
    existing = conn.execute("SELECT * FROM registrations WHERE id = ?", (reg_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "找不到報名資料"}), 404
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE registrations SET {set_clause} WHERE id = ?", (*fields.values(), reg_id))
    conn.commit()
    row = conn.execute("SELECT * FROM registrations WHERE id = ?", (reg_id,)).fetchone()
    conn.close()

    log_action(g.user["name"], "登錄培訓紀錄", f'{row["reg_no"]}（{row["name"]}） {json.dumps(fields, ensure_ascii=False)}')
    return jsonify({"registration": registration_to_dict(row)})

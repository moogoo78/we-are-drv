"""「我的防災士」學員專區：以身分證字號＋出生年月日＋手機登入。"""
import json
import re
import sqlite3

from flask import Blueprint, g, jsonify, request

from ..auth import require_student, sign_student_token
from ..db import get_db
from ..geo import is_valid_village
from ..members import json_list
from .. import survey_def

student_bp = Blueprint("student", __name__)

PROFILE_FIELDS = (
    "phone", "email", "address", "village", "occupation", "unit_village", "home_phone", "education",
    "job_title", "emergency_name", "emergency_relation", "emergency_phone",
)


def digits(s):
    return re.sub(r"\D", "", s or "")


def _own_registration(conn, reg_id):
    return conn.execute(
        """SELECT r.*, b.name AS batch_name, b.start_date, b.end_date, b.location, b.quiz_open,
                  b.survey_open, b.material_key
           FROM registrations r JOIN batches b ON b.id = r.batch_id
           WHERE r.id = ? AND r.id_number = ?""",
        (reg_id, g.student["sub"]),
    ).fetchone()


def _setting(conn, key, default):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


@student_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    id_number = (data.get("id_number") or "").strip().upper()
    birth_date = (data.get("birth_date") or "").strip()
    phone = digits(data.get("phone"))
    if not id_number or not birth_date or not phone:
        return jsonify({"error": "請輸入身分證字號、出生年月日與報名時填寫的手機號碼"}), 400
    conn = get_db()
    rows = conn.execute(
        "SELECT name, phone FROM registrations WHERE id_number = ? AND birth_date = ? ORDER BY created_at DESC",
        (id_number, birth_date),
    ).fetchall()
    conn.close()
    match = next((r for r in rows if digits(r["phone"]) == phone), None)
    if not match:
        return jsonify({"error": "查無符合的報名資料，請確認輸入內容"}), 401
    return jsonify({"token": sign_student_token(id_number, match["name"]), "name": match["name"]})


@student_bp.route("/overview", methods=["GET"])
@require_student
def overview():
    conn = get_db()
    regs = conn.execute(
        """SELECT r.*, b.name AS batch_name, b.start_date, b.end_date, b.location, b.quiz_open, b.survey_open,
                  b.material_key,
                  (SELECT passed FROM quiz_attempts q WHERE q.registration_id = r.id) AS quiz_passed,
                  (SELECT COUNT(*) FROM quiz_attempts q WHERE q.registration_id = r.id) AS quiz_submitted,
                  (SELECT COUNT(*) FROM survey_responses s WHERE s.registration_id = r.id) AS survey_submitted
           FROM registrations r JOIN batches b ON b.id = r.batch_id
           WHERE r.id_number = ? ORDER BY b.start_date DESC""",
        (g.student["sub"],),
    ).fetchall()
    certs = conn.execute(
        """SELECT c.id, c.cert_no, c.apply_status, c.delivery_method, c.pickup_status, c.issued_at,
                  c.mailed_at, c.collected_at, r.id AS registration_id, b.name AS batch_name
           FROM certificates c JOIN registrations r ON r.id = c.registration_id
           JOIN batches b ON b.id = r.batch_id
           WHERE r.id_number = ? ORDER BY c.id DESC""",
        (g.student["sub"],),
    ).fetchall()
    apps = conn.execute(
        """SELECT a.id, a.kind, a.reason, a.status, a.admin_note, a.created_at, a.handled_at,
                  r.id AS registration_id, r.name, r.checked_in, b.name AS batch_name, b.start_date, b.end_date,
                  b.location,
                  (SELECT COALESCE(SUM(hours), 0) FROM course_sessions cs WHERE cs.batch_id = b.id) AS total_hours
           FROM applications a JOIN registrations r ON r.id = a.registration_id
           JOIN batches b ON b.id = r.batch_id
           WHERE r.id_number = ? ORDER BY a.created_at DESC""",
        (g.student["sub"],),
    ).fetchall()
    conn.close()

    registrations = []
    for r in regs:
        approved = r["status"] == "approved"
        registrations.append({
            "id": r["id"],
            "reg_no": r["reg_no"],
            "batch_id": r["batch_id"],
            "batch_name": r["batch_name"],
            "start_date": r["start_date"],
            "end_date": r["end_date"],
            "location": r["location"],
            "status": r["status"],
            "review_note": r["review_note"],
            "created_at": r["created_at"],
            "checked_in": bool(r["checked_in"]),
            # 學科／術科只公布合格與否
            "written_passed": r["written_passed"],
            "practical_passed": r["practical_passed"],
            "quiz_available": bool(approved and r["quiz_open"] and not r["quiz_submitted"]),
            "quiz_submitted": bool(r["quiz_submitted"]),
            "survey_available": bool(approved and r["survey_open"] and not r["survey_submitted"]),
            "survey_submitted": bool(r["survey_submitted"]),
            "material_key": r["material_key"] if approved else None,
        })
    latest = regs[0] if regs else None
    profile = None
    if latest:
        profile = {k: latest[k] for k in ("name", "id_number", "birth_date", "sex", "district", *PROFILE_FIELDS)}
        profile["specialty"] = json_list(latest["specialty"])
        profile["support_pref"] = latest["support_pref"]
    return jsonify({
        "profile": profile,
        "registrations": registrations,
        "certificates": [dict(c) for c in certs],
        "applications": [dict(a) for a in apps],
    })


@student_bp.route("/profile", methods=["PATCH"])
@require_student
def update_profile():
    """學員基本資料管理：更新聯絡資訊（套用至本人所有報名紀錄與防災士名冊）。"""
    data = request.get_json(silent=True) or {}
    fields = {k: (str(data[k]).strip() or None) for k in PROFILE_FIELDS if k in data}
    for required in ("phone", "email", "address"):
        if required in fields and not fields[required]:
            return jsonify({"error": "手機、Email、地址為必填"}), 400
    if "specialty" in data:
        fields["specialty"] = json.dumps(json_list(data["specialty"]), ensure_ascii=False)
    if "support_pref" in data:
        fields["support_pref"] = "願意" if data["support_pref"] in (True, "願意", "true") else "未表示"
    if not fields:
        return jsonify({"error": "沒有要更新的欄位"}), 400

    conn = get_db()
    latest = conn.execute(
        "SELECT district FROM registrations WHERE id_number = ? ORDER BY created_at DESC", (g.student["sub"],)
    ).fetchone()
    if fields.get("village") and not is_valid_village(latest["district"], fields["village"]):
        conn.close()
        return jsonify({"error": "里別與行政區不符"}), 400
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE registrations SET {set_clause} WHERE id_number = ?", (*fields.values(), g.student["sub"]))

    member_map = {"phone": "phone", "email": "email", "address": "address", "village": "village",
                  "occupation": "occupation", "unit_village": "unit", "specialty": "specialty"}
    member_fields = {member_map[k]: v for k, v in fields.items() if k in member_map}
    if "support_pref" in fields:
        member_fields["support_willing"] = 1 if fields["support_pref"] == "願意" else 0
    if member_fields:
        set_clause = ", ".join(f"{k} = ?" for k in member_fields)
        conn.execute(f"UPDATE members SET {set_clause} WHERE id_number = ?", (*member_fields.values(), g.student["sub"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---- 線上測驗 ----

@student_bp.route("/quiz/<int:reg_id>", methods=["GET"])
@require_student
def get_quiz(reg_id):
    conn = get_db()
    reg = _own_registration(conn, reg_id)
    if not reg or reg["status"] != "approved":
        conn.close()
        return jsonify({"error": "找不到可參加測驗的梯次"}), 404
    if conn.execute("SELECT 1 FROM quiz_attempts WHERE registration_id = ?", (reg_id,)).fetchone():
        conn.close()
        return jsonify({"error": "您已完成本梯次學科測驗"}), 409
    if not reg["quiz_open"]:
        conn.close()
        return jsonify({"error": "本梯次線上測驗尚未開放"}), 403
    rows = conn.execute(
        "SELECT id, qtype, question, options, points FROM quiz_questions WHERE active = 1 ORDER BY qtype DESC, id"
    ).fetchall()
    conn.close()
    questions = [{**dict(r), "options": json.loads(r["options"] or "[]")} for r in rows]
    return jsonify({"batch_name": reg["batch_name"], "questions": questions})


@student_bp.route("/quiz/<int:reg_id>", methods=["POST"])
@require_student
def submit_quiz(reg_id):
    answers = (request.get_json(silent=True) or {}).get("answers") or {}
    conn = get_db()
    reg = _own_registration(conn, reg_id)
    if not reg or reg["status"] != "approved" or not reg["quiz_open"]:
        conn.close()
        return jsonify({"error": "目前無法作答"}), 403
    rows = conn.execute("SELECT id, answer, points FROM quiz_questions WHERE active = 1").fetchall()
    if not rows:
        conn.close()
        return jsonify({"error": "題庫尚未建立"}), 400
    total = sum(r["points"] for r in rows)
    earned = sum(r["points"] for r in rows if str(answers.get(str(r["id"]), "")).strip().upper() == r["answer"].upper())
    score = round(earned * 100 / total) if total else 0
    passed = 1 if score >= int(_setting(conn, "quiz_pass_score", "60")) else 0
    try:
        conn.execute(
            "INSERT INTO quiz_attempts (registration_id, answers, score, passed) VALUES (?, ?, ?, ?)",
            (reg_id, json.dumps(answers, ensure_ascii=False), score, passed),
        )
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "您已完成本梯次學科測驗"}), 409
    conn.execute(
        "UPDATE registrations SET written_score = ?, written_passed = ? WHERE id = ?", (score, passed, reg_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"passed": bool(passed)})


# ---- 課後問卷 ----

@student_bp.route("/survey", methods=["GET"])
def survey_definition():
    return jsonify({"questions": survey_def.QUESTIONS})


@student_bp.route("/survey/<int:reg_id>", methods=["POST"])
@require_student
def submit_survey(reg_id):
    answers = (request.get_json(silent=True) or {}).get("answers")
    err = survey_def.validate(answers)
    if err:
        return jsonify({"error": err}), 400
    conn = get_db()
    reg = _own_registration(conn, reg_id)
    if not reg or reg["status"] != "approved" or not reg["survey_open"]:
        conn.close()
        return jsonify({"error": "目前無法填寫問卷"}), 403
    if conn.execute("SELECT 1 FROM survey_responses WHERE registration_id = ?", (reg_id,)).fetchone():
        conn.close()
        return jsonify({"error": "您已填寫過本梯次問卷"}), 409
    conn.execute(
        "INSERT INTO survey_responses (registration_id, answers) VALUES (?, ?)",
        (reg_id, json.dumps(answers, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


# ---- 證照遺失補發／參訓證明申請 ----

@student_bp.route("/applications", methods=["POST"])
@require_student
def create_application():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    if kind not in ("reissue", "attendance_proof"):
        return jsonify({"error": "無效的申請類型"}), 400
    try:
        reg_id = int(data.get("registration_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "請選擇梯次"}), 400
    conn = get_db()
    reg = _own_registration(conn, reg_id)
    if not reg or reg["status"] != "approved":
        conn.close()
        return jsonify({"error": "僅錄取梯次可提出申請"}), 400
    if kind == "reissue":
        cert = conn.execute(
            "SELECT apply_status FROM certificates WHERE registration_id = ?", (reg_id,)
        ).fetchone()
        if not cert or cert["apply_status"] != "issued":
            conn.close()
            return jsonify({"error": "此梯次尚未核發證照，無法申請補發"}), 400
    dupe = conn.execute(
        "SELECT 1 FROM applications WHERE registration_id = ? AND kind = ? AND status IN ('pending', 'processing')",
        (reg_id, kind),
    ).fetchone()
    if dupe:
        conn.close()
        return jsonify({"error": "已有處理中的相同申請"}), 409
    conn.execute(
        "INSERT INTO applications (registration_id, kind, reason) VALUES (?, ?, ?)",
        (reg_id, kind, (data.get("reason") or "").strip() or None),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201

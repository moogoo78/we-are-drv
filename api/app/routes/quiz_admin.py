"""學科測驗題庫管理與線上測驗設定。"""
import csv
import io
import json

from flask import Blueprint, g, jsonify, request

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action

quiz_bp = Blueprint("quiz_admin", __name__)

TF_ANSWERS = {"O", "X"}
CHOICE_ANSWERS = {"A", "B", "C", "D"}


def _normalize(data):
    """回傳 (欄位 dict, 錯誤訊息)。是非題答案 O/X；選擇題答案 A～D、options 為四個選項文字。"""
    qtype = data.get("qtype")
    question = (data.get("question") or "").strip()
    answer = str(data.get("answer") or "").strip().upper()
    answer = {"○": "O", "Ｏ": "O", "對": "O", "T": "O", "×": "X", "Ｘ": "X", "錯": "X", "F": "X"}.get(answer, answer)
    if qtype not in ("tf", "choice") or not question:
        return None, "請填寫題型與題目"
    options = data.get("options") or []
    if isinstance(options, str):
        options = json.loads(options or "[]")
    if qtype == "tf":
        options = []
        if answer not in TF_ANSWERS:
            return None, "是非題答案需為 O 或 X"
    else:
        options = [str(o).strip() for o in options][:4]
        if len(options) != 4 or not all(options):
            return None, "選擇題需填寫 A～D 四個選項"
        if answer not in CHOICE_ANSWERS:
            return None, "選擇題答案需為 A～D"
    try:
        points = int(data.get("points") or 2)
    except (TypeError, ValueError):
        points = 2
    return {"qtype": qtype, "question": question, "options": json.dumps(options, ensure_ascii=False),
            "answer": answer, "points": points}, None


def _question_dict(row):
    q = dict(row)
    q["options"] = json.loads(q["options"] or "[]")
    return q


@quiz_bp.route("/questions", methods=["GET"])
@require_auth
def list_questions():
    conn = get_db()
    rows = conn.execute("SELECT * FROM quiz_questions ORDER BY qtype DESC, id").fetchall()
    conn.close()
    return jsonify({"questions": [_question_dict(r) for r in rows]})


@quiz_bp.route("/questions", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def create_question():
    fields, err = _normalize(request.get_json(silent=True) or {})
    if err:
        return jsonify({"error": err}), 400
    conn = get_db()
    cur = conn.execute(
        f"INSERT INTO quiz_questions ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
        tuple(fields.values()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM quiz_questions WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    log_action(g.user["name"], "新增測驗題目", fields["question"][:30])
    return jsonify({"question": _question_dict(row)}), 201


@quiz_bp.route("/questions/<int:qid>", methods=["PATCH"])
@require_auth
@require_role("admin", "staff")
def update_question(qid):
    data = request.get_json(silent=True) or {}
    conn = get_db()
    row = conn.execute("SELECT * FROM quiz_questions WHERE id = ?", (qid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "找不到題目"}), 404
    if set(data) == {"active"}:
        conn.execute("UPDATE quiz_questions SET active = ? WHERE id = ?", (1 if data["active"] else 0, qid))
    else:
        merged = {**_question_dict(row), **data}
        fields, err = _normalize(merged)
        if err:
            conn.close()
            return jsonify({"error": err}), 400
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE quiz_questions SET {set_clause} WHERE id = ?", (*fields.values(), qid))
    conn.commit()
    row = conn.execute("SELECT * FROM quiz_questions WHERE id = ?", (qid,)).fetchone()
    conn.close()
    return jsonify({"question": _question_dict(row)})


@quiz_bp.route("/questions/<int:qid>", methods=["DELETE"])
@require_auth
@require_role("admin", "staff")
def delete_question(qid):
    conn = get_db()
    conn.execute("DELETE FROM quiz_questions WHERE id = ?", (qid,))
    conn.commit()
    conn.close()
    return "", 204


@quiz_bp.route("/questions/import", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def import_questions():
    """CSV 欄位：題型(是非/選擇),題目,選項A,選項B,選項C,選項D,答案,配分"""
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "請選擇 CSV 檔案"}), 400
    text = file.read().decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if rows and rows[0] and rows[0][0].strip() in ("題型", "qtype"):
        rows = rows[1:]
    inserted, errors = 0, []
    conn = get_db()
    for i, row in enumerate(rows, start=1):
        if not any(c.strip() for c in row):
            continue
        row = row + [""] * (8 - len(row))
        qtype = {"是非": "tf", "是非題": "tf", "tf": "tf", "選擇": "choice", "選擇題": "choice", "choice": "choice"}.get(row[0].strip())
        fields, err = _normalize({"qtype": qtype, "question": row[1], "options": row[2:6], "answer": row[6],
                                  "points": row[7]})
        if err:
            errors.append(f"第 {i} 列：{err}")
            continue
        conn.execute(
            f"INSERT INTO quiz_questions ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
            tuple(fields.values()),
        )
        inserted += 1
    conn.commit()
    conn.close()
    log_action(g.user["name"], "匯入測驗題庫", f"{inserted} 題")
    return jsonify({"inserted": inserted, "errors": errors[:50]})


@quiz_bp.route("/settings", methods=["GET"])
@require_auth
def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return jsonify({"settings": {r["key"]: r["value"] for r in rows}})


@quiz_bp.route("/settings", methods=["PATCH"])
@require_auth
@require_role("admin")
def update_settings():
    data = request.get_json(silent=True) or {}
    if "quiz_pass_score" in data:
        try:
            score = int(data["quiz_pass_score"])
            assert 0 <= score <= 100
        except (TypeError, ValueError, AssertionError):
            return jsonify({"error": "及格分數需為 0～100"}), 400
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('quiz_pass_score', ?)", (str(score),))
        conn.commit()
        conn.close()
        log_action(g.user["name"], "更新測驗設定", f"及格分數 {score}")
    return get_settings()

"""通知與提醒：依條件篩選收件人（人工確認後發送），Email 經 SMTP 寄出，簡訊匯出名單後人工發送。"""
import csv
import io
import re

from flask import Blueprint, Response, g, jsonify, request

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action
from ..mailer import send_email, smtp_configured
from ..site import SITE

notify_bp = Blueprint("notify", __name__)

SIGNATURE = f"\n\n{SITE['contact']}\n{SITE['phone_ext']}"
PREFIX = f"【{SITE['program']}】"

TEMPLATES = {
    "registered": ("報名成功通知", PREFIX + "{batch} 報名成功通知",
                   "{name} 您好：\n您已完成「{batch}」防災士培訓報名，報名序號 {reg_no}。承辦人員審核後將再通知錄取結果。"),
    "approved": ("正取通知", PREFIX + "{batch} 正取通知",
                 "{name} 您好：\n恭喜您正取「{batch}」防災士培訓，上課日期 {start_date}～{end_date}，地點：{location}。請準時出席。"),
    "waitlist": ("備取通知", PREFIX + "{batch} 備取通知",
                 "{name} 您好：\n您目前為「{batch}」備取學員，如有名額釋出將另行通知遞補。"),
    "course_reminder": ("開課提醒", PREFIX + "{batch} 開課提醒",
                        "{name} 您好：\n「{batch}」將於 {start_date} 開課，地點：{location}。請攜帶身分證件準時報到。"),
    "course_reminder_3d": ("開課前三日提醒", PREFIX + "{batch} 開課前三日提醒",
                           "{name} 您好：\n提醒您「{batch}」將於 {start_date} 開課（{start_date}～{end_date}），"
                           "地點：{location}。請攜帶身分證件準時報到，如無法出席請儘早告知承辦人員。"),
    "needs_more_info": ("補件通知", PREFIX + "報名資料補件通知",
                        "{name} 您好：\n您報名「{batch}」的資料尚需補件：{note}\n請儘速與承辦人員聯繫。"),
    "needs_more_info_reminder": ("補件提醒", PREFIX + "報名資料補件提醒",
                                 "{name} 您好：\n提醒您，報名「{batch}」的資料仍待補件：{note}\n"
                                 "逾期未補件可能影響錄取資格，請儘速與承辦人員聯繫。"),
    "cert_pickup": ("證照領取通知", PREFIX + "防災士證照領取通知",
                    "{name} 您好：\n您的防災士證書（{cert_no}）已核發，請於上班時間攜帶身分證件至本局領取。"),
    "cert_pickup_reminder": ("證照領取提醒", PREFIX + "防災士證照領取提醒",
                             "{name} 您好：\n提醒您，您的防災士證書（{cert_no}）尚未領取，請於上班時間攜帶身分證件至本局領取。"),
    "cert_mailed": ("證照寄送通知", PREFIX + "防災士證照寄送通知",
                    "{name} 您好：\n您的防災士證書（{cert_no}）已核發並以郵寄方式寄出，請留意收件。"),
    "custom": ("自訂通知", PREFIX, "{name} 您好：\n"),
}

RECIPIENT_SELECT = """SELECT r.id AS registration_id, r.name, r.email, r.phone, r.reg_no, r.review_note, r.notified_at,
                             b.name AS batch_name, b.start_date, b.end_date, b.location, c.cert_no
                      FROM registrations r JOIN batches b ON b.id = r.batch_id
                      LEFT JOIN certificates c ON c.registration_id = r.id"""


def _recipients(conn, kind, batch_id, status):
    conditions, params = [], []
    if kind in ("cert_pickup", "cert_pickup_reminder"):
        conditions.append("c.apply_status = 'issued' AND c.pickup_status = 'not_collected' AND c.delivery_method = 'pickup'")
    elif kind == "cert_mailed":
        conditions.append("c.apply_status = 'issued' AND c.pickup_status = 'shipping' AND c.delivery_method = 'mail'")
    elif kind in ("approved", "course_reminder"):
        conditions.append("r.status = 'approved'")
    elif kind == "course_reminder_3d":
        conditions.append("r.status = 'approved' AND b.start_date BETWEEN date('now') AND date('now', '+3 day')")
    elif kind == "waitlist":
        conditions.append("r.status = 'waitlist'")
    elif kind in ("needs_more_info", "needs_more_info_reminder"):
        conditions.append("r.status = 'needs_more_info'")
    elif kind == "custom" and status:
        conditions.append("r.status = ?")
        params.append(status)
    if batch_id:
        conditions.append("r.batch_id = ?")
        params.append(batch_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return [dict(r) for r in conn.execute(f"{RECIPIENT_SELECT} {where} ORDER BY r.id", params).fetchall()]


def _render(text, r):
    values = {
        "name": r["name"], "batch": r["batch_name"], "reg_no": r["reg_no"] or "", "start_date": r["start_date"],
        "end_date": r["end_date"], "location": r["location"], "note": r["review_note"] or "（請洽承辦人員）",
        "cert_no": r["cert_no"] or "",
    }
    # 只替換已知變數，其餘大括號原樣保留
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), text)


@notify_bp.route("/config", methods=["GET"])
@require_auth
def config():
    conn = get_db()
    # 開課前三日提醒：列出三日內開課的梯次
    upcoming = conn.execute(
        """SELECT id, name, start_date FROM batches
           WHERE start_date BETWEEN date('now') AND date('now', '+3 day') ORDER BY start_date"""
    ).fetchall()
    conn.close()
    return jsonify({
        "smtp": smtp_configured(),
        "templates": {k: {"label": v[0], "subject": v[1], "body": v[2] + SIGNATURE} for k, v in TEMPLATES.items()},
        "upcoming_batches": [dict(r) for r in upcoming],
    })


@notify_bp.route("/recipients", methods=["GET"])
@require_auth
def recipients():
    kind = request.args.get("kind", "custom")
    if kind not in TEMPLATES:
        return jsonify({"error": "無效的通知類型"}), 400
    conn = get_db()
    rows = _recipients(conn, kind, request.args.get("batch_id"), request.args.get("status"))
    conn.close()
    return jsonify({"recipients": rows})


@notify_bp.route("/send", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def send():
    data = request.get_json(silent=True) or {}
    channel = data.get("channel")
    category = data.get("category") if data.get("category") in TEMPLATES else "custom"
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    ids = [int(i) for i in data.get("registration_ids") or [] if str(i).isdigit()]
    if channel not in ("email", "sms") or not body or not ids:
        return jsonify({"error": "請選擇管道、收件人並填寫內容"}), 400
    if channel == "email" and not subject:
        return jsonify({"error": "請填寫 Email 主旨"}), 400

    conn = get_db()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(f"{RECIPIENT_SELECT} WHERE r.id IN ({placeholders})", ids).fetchall()
    use_smtp = channel == "email" and smtp_configured()
    counts = {"sent": 0, "queued": 0, "failed": 0}
    for r in rows:
        text = _render(body, r)
        subj = _render(subject, r) if subject else None
        recipient = r["email"] if channel == "email" else r["phone"]
        status, error = "queued", None
        if use_smtp:
            try:
                send_email(recipient, subj, text)
                status = "sent"
            except Exception as e:  # noqa: BLE001 — 個別寄送失敗不中斷其他收件人
                status, error = "failed", str(e)[:300]
        counts[status] += 1
        conn.execute(
            """INSERT INTO notifications (channel, category, registration_id, recipient_name, recipient, subject, body,
                                          status, error, created_by, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'sent' THEN datetime('now') END)""",
            (channel, category, r["registration_id"], r["name"], recipient, subj, text, status, error,
             g.user["name"], status),
        )
        if status != "failed":
            conn.execute("UPDATE registrations SET notified_at = datetime('now') WHERE id = ?", (r["registration_id"],))
    conn.commit()
    conn.close()
    log_action(g.user["name"], "發送通知", f"{TEMPLATES[category][0]}／{channel}：{len(rows)} 人")
    return jsonify(counts)


@notify_bp.route("/log", methods=["GET"])
@require_auth
def log():
    conditions, params = [], []
    for arg in ("channel", "status", "category"):
        if request.args.get(arg):
            conditions.append(f"{arg} = ?")
            params.append(request.args[arg])
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    conn = get_db()
    rows = conn.execute(f"SELECT * FROM notifications {where} ORDER BY id DESC LIMIT 300", params).fetchall()
    conn.close()
    return jsonify({"notifications": [dict(r) for r in rows]})


@notify_bp.route("/export.csv", methods=["GET"])
@require_auth
def export_csv():
    """匯出待發送名單（簡訊平台批次上傳或人工發送用）。"""
    channel = request.args.get("channel", "sms")
    conn = get_db()
    rows = conn.execute(
        "SELECT recipient_name, recipient, subject, body, created_at FROM notifications WHERE channel = ? AND status = 'queued' ORDER BY id",
        (channel,),
    ).fetchall()
    conn.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["姓名", "手機" if channel == "sms" else "Email", "主旨", "內容", "建立時間"])
    for r in rows:
        w.writerow([r["recipient_name"], r["recipient"], r["subject"] or "", r["body"], r["created_at"]])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=notify-{channel}-queued.csv"})


@notify_bp.route("/mark-sent", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def mark_sent():
    """人工發送完成後，將待發送紀錄標記為已發送。"""
    channel = (request.get_json(silent=True) or {}).get("channel", "sms")
    conn = get_db()
    cur = conn.execute(
        "UPDATE notifications SET status = 'sent', sent_at = datetime('now') WHERE channel = ? AND status = 'queued'",
        (channel,),
    )
    conn.commit()
    conn.close()
    log_action(g.user["name"], "標記通知已發送", f"{channel} {cur.rowcount} 筆")
    return jsonify({"updated": cur.rowcount})

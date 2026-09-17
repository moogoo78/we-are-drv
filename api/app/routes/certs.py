import sqlite3
from datetime import date

from flask import Blueprint, g, jsonify, request

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action

certs_bp = Blueprint("certs", __name__)

ALLOWED_PICKUP = {"not_collected", "shipping", "collected"}
ALLOWED_DELIVERY = {"pickup", "mail"}

CERT_SELECT = """SELECT c.id, c.cert_no, c.delivery_method, c.pickup_status, c.note, c.issued_at,
                         r.id AS registration_id, r.name, r.reg_no, b.name AS batch_name
                  FROM certificates c
                  JOIN registrations r ON r.id = c.registration_id
                  JOIN batches b ON b.id = r.batch_id"""


@certs_bp.route("", methods=["GET"])
@require_auth
def list_certs():
    batch_id = request.args.get("batch_id")
    q = request.args.get("q")
    conditions = []
    params = []
    if batch_id:
        conditions.append("r.batch_id = ?")
        params.append(batch_id)
    if q:
        conditions.append("(r.name LIKE ? OR c.cert_no LIKE ?)")
        like = f"%{q}%"
        params += [like, like]
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    conn = get_db()
    rows = conn.execute(f"{CERT_SELECT} {where} ORDER BY c.issued_at DESC", params).fetchall()
    conn.close()
    return jsonify({"certificates": [dict(r) for r in rows]})


@certs_bp.route("", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def issue_cert():
    data = request.get_json(silent=True) or {}
    reg_no = (data.get("reg_no") or "").strip()
    if not reg_no:
        return jsonify({"error": "請輸入報名序號"}), 400
    delivery_method = data.get("delivery_method")
    if delivery_method not in ALLOWED_DELIVERY:
        delivery_method = "pickup"

    conn = get_db()
    reg = conn.execute("SELECT * FROM registrations WHERE reg_no = ?", (reg_no,)).fetchone()
    if not reg:
        conn.close()
        return jsonify({"error": "找不到此報名序號"}), 404
    if reg["status"] != "approved":
        conn.close()
        return jsonify({"error": "僅已錄取學員可核發證照"}), 400

    existing = conn.execute("SELECT id FROM certificates WHERE registration_id = ?", (reg["id"],)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "此學員已核發過證照"}), 409

    year = date.today().year
    seq = conn.execute("SELECT COUNT(*) AS n FROM certificates WHERE cert_no LIKE ?", (f"DRV-{year}-%",)).fetchone()["n"]
    cert_no = f"DRV-{year}-{seq + 1:04d}"
    pickup_status = "shipping" if delivery_method == "mail" else "not_collected"

    try:
        cur = conn.execute(
            "INSERT INTO certificates (registration_id, cert_no, delivery_method, pickup_status) VALUES (?, ?, ?, ?)",
            (reg["id"], cert_no, delivery_method, pickup_status),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "證照核發失敗，請重新嘗試"}), 409

    row = conn.execute(f"{CERT_SELECT} WHERE c.id = ?", (cur.lastrowid,)).fetchone()
    conn.close()

    log_action(g.user["name"], "核發證照", f'{cert_no}（{reg["name"]}）')
    return jsonify({"certificate": dict(row)}), 201


@certs_bp.route("/<int:cert_id>", methods=["PATCH"])
@require_auth
@require_role("admin", "staff")
def update_cert(cert_id):
    data = request.get_json(silent=True) or {}
    pickup_status = data.get("pickup_status")
    if pickup_status is not None and pickup_status not in ALLOWED_PICKUP:
        return jsonify({"error": "無效的領取狀態"}), 400

    conn = get_db()
    existing = conn.execute("SELECT * FROM certificates WHERE id = ?", (cert_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "找不到證照資料"}), 404

    conn.execute(
        "UPDATE certificates SET pickup_status = COALESCE(?, pickup_status), note = COALESCE(?, note) WHERE id = ?",
        (pickup_status, data.get("note"), cert_id),
    )
    conn.commit()
    row = conn.execute(f"{CERT_SELECT} WHERE c.id = ?", (cert_id,)).fetchone()
    conn.close()

    log_action(g.user["name"], "更新證照", f'{row["cert_no"]} → {pickup_status or existing["pickup_status"]}')
    return jsonify({"certificate": dict(row)})

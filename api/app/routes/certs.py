import sqlite3
from datetime import date

from flask import Blueprint, g, jsonify, request

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action
from ..members import upsert_member_from_registration

certs_bp = Blueprint("certs", __name__)

ALLOWED_PICKUP = {"not_collected", "shipping", "collected"}
ALLOWED_DELIVERY = {"pickup", "mail"}
ALLOWED_APPLY = {"applying", "submitted", "issued"}

CERT_SELECT = """SELECT c.id, c.cert_no, c.delivery_method, c.pickup_status, c.apply_status, c.note,
                         c.issued_at, c.mailed_at, c.collected_at,
                         r.id AS registration_id, r.name, r.reg_no, r.phone, r.email, r.address,
                         b.id AS batch_id, b.name AS batch_name
                  FROM certificates c
                  JOIN registrations r ON r.id = c.registration_id
                  JOIN batches b ON b.id = r.batch_id"""


@certs_bp.route("", methods=["GET"])
@require_auth
def list_certs():
    conditions = []
    params = []
    for arg, col in (("batch_id", "r.batch_id"), ("apply_status", "c.apply_status"),
                     ("pickup_status", "c.pickup_status"), ("delivery_method", "c.delivery_method")):
        if request.args.get(arg):
            conditions.append(f"{col} = ?")
            params.append(request.args[arg])
    q = request.args.get("q")
    if q:
        conditions.append("(r.name LIKE ? OR c.cert_no LIKE ? OR r.reg_no LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like]
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    conn = get_db()
    rows = conn.execute(f"{CERT_SELECT} {where} ORDER BY c.issued_at DESC, c.id DESC", params).fetchall()
    conn.close()
    return jsonify({"certificates": [dict(r) for r in rows]})


@certs_bp.route("/unclaimed", methods=["GET"])
@require_auth
def unclaimed():
    """未領取提醒名單：已核發、親領且尚未領取。"""
    conn = get_db()
    rows = conn.execute(
        f"""{CERT_SELECT} WHERE c.apply_status = 'issued' AND c.pickup_status = 'not_collected'
            ORDER BY c.issued_at"""
    ).fetchall()
    conn.close()
    return jsonify({"certificates": [dict(r) for r in rows]})


@certs_bp.route("", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def create_cert():
    """為已錄取學員建立證照申請（申請中 → 已送出 → 已核發）。"""
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
        return jsonify({"error": "僅已錄取學員可申請證照"}), 400

    existing = conn.execute("SELECT id FROM certificates WHERE registration_id = ?", (reg["id"],)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "此學員已建立過證照資料"}), 409

    cert_no = (data.get("cert_no") or "").strip()
    if not cert_no:
        year = date.today().year
        seq = conn.execute("SELECT COUNT(*) AS n FROM certificates WHERE cert_no LIKE ?", (f"DRV-{year}-%",)).fetchone()["n"]
        cert_no = f"DRV-{year}-{seq + 1:04d}"
    apply_status = data.get("apply_status") if data.get("apply_status") in ALLOWED_APPLY else "applying"

    try:
        cur = conn.execute(
            """INSERT INTO certificates (registration_id, cert_no, delivery_method, pickup_status, apply_status)
               VALUES (?, ?, ?, 'not_collected', ?)""",
            (reg["id"], cert_no, delivery_method, apply_status),
        )
        if apply_status == "issued":
            upsert_member_from_registration(conn, reg["id"], cert_no)
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "證照編號重複，請重新確認"}), 409

    row = conn.execute(f"{CERT_SELECT} WHERE c.id = ?", (cur.lastrowid,)).fetchone()
    conn.close()

    log_action(g.user["name"], "建立證照申請", f'{cert_no}（{reg["name"]}）')
    return jsonify({"certificate": dict(row)}), 201


@certs_bp.route("/<int:cert_id>", methods=["PATCH"])
@require_auth
@require_role("admin", "staff")
def update_cert(cert_id):
    data = request.get_json(silent=True) or {}
    if data.get("pickup_status") is not None and data["pickup_status"] not in ALLOWED_PICKUP:
        return jsonify({"error": "無效的領取狀態"}), 400
    if data.get("apply_status") is not None and data["apply_status"] not in ALLOWED_APPLY:
        return jsonify({"error": "無效的申請狀態"}), 400
    if data.get("delivery_method") is not None and data["delivery_method"] not in ALLOWED_DELIVERY:
        return jsonify({"error": "無效的領取方式"}), 400

    conn = get_db()
    existing = conn.execute("SELECT * FROM certificates WHERE id = ?", (cert_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "找不到證照資料"}), 404

    fields = {k: data[k] for k in ("cert_no", "delivery_method", "pickup_status", "apply_status", "note") if data.get(k) is not None}
    if fields.get("pickup_status") == "shipping" and existing["pickup_status"] != "shipping":
        fields["mailed_at"] = date.today().isoformat()
    if fields.get("pickup_status") == "collected" and existing["pickup_status"] != "collected":
        fields["collected_at"] = date.today().isoformat()
    if fields.get("apply_status") == "issued" and existing["apply_status"] != "issued":
        fields["issued_at"] = date.today().isoformat()

    try:
        if fields:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(f"UPDATE certificates SET {set_clause} WHERE id = ?", (*fields.values(), cert_id))
        row = conn.execute("SELECT * FROM certificates WHERE id = ?", (cert_id,)).fetchone()
        if row["apply_status"] == "issued":
            upsert_member_from_registration(conn, row["registration_id"], row["cert_no"])
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "證照編號重複，請重新確認"}), 409
    row = conn.execute(f"{CERT_SELECT} WHERE c.id = ?", (cert_id,)).fetchone()
    conn.close()

    changes = "、".join(f"{k}={v}" for k, v in fields.items())
    log_action(g.user["name"], "更新證照", f'{row["cert_no"]}（{row["name"]}） {changes}')
    return jsonify({"certificate": dict(row)})

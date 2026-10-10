"""學員線上申請（證照遺失補發、參訓證明）的後台處理。"""
from flask import Blueprint, g, jsonify, request

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action

applications_bp = Blueprint("applications", __name__)

ALLOWED_STATUS = {"pending", "processing", "done", "rejected"}
KIND_LABEL = {"reissue": "證照遺失補發", "attendance_proof": "參訓證明"}


@applications_bp.route("", methods=["GET"])
@require_auth
def list_applications():
    conditions, params = [], []
    for arg in ("kind", "status"):
        if request.args.get(arg):
            conditions.append(f"a.{arg} = ?")
            params.append(request.args[arg])
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    conn = get_db()
    rows = conn.execute(
        f"""SELECT a.*, r.name, r.reg_no, r.phone, r.email, r.checked_in, b.name AS batch_name
            FROM applications a JOIN registrations r ON r.id = a.registration_id
            JOIN batches b ON b.id = r.batch_id
            {where} ORDER BY a.status = 'pending' DESC, a.created_at DESC""",
        params,
    ).fetchall()
    conn.close()
    return jsonify({"applications": [dict(r) for r in rows]})


@applications_bp.route("/<int:app_id>", methods=["PATCH"])
@require_auth
@require_role("admin", "staff")
def update_application(app_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ALLOWED_STATUS:
        return jsonify({"error": "無效的處理狀態"}), 400
    conn = get_db()
    row = conn.execute(
        "SELECT a.kind, r.name FROM applications a JOIN registrations r ON r.id = a.registration_id WHERE a.id = ?",
        (app_id,),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "找不到申請案件"}), 404
    conn.execute(
        """UPDATE applications SET status = ?, admin_note = COALESCE(?, admin_note), handled_by = ?,
                                   handled_at = datetime('now') WHERE id = ?""",
        (status, data.get("admin_note"), g.user["name"], app_id),
    )
    conn.commit()
    conn.close()
    log_action(g.user["name"], "處理申請案件", f'{KIND_LABEL[row["kind"]]}（{row["name"]}） → {status}')
    return jsonify({"ok": True})

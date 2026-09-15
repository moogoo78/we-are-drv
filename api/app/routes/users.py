from flask import Blueprint, g, jsonify, request
from werkzeug.security import generate_password_hash

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action

users_bp = Blueprint("users", __name__)


@users_bp.route("", methods=["GET"])
@require_auth
@require_role("admin")
def list_users():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, display_name, role, created_at FROM admin_users ORDER BY id"
    ).fetchall()
    conn.close()
    return jsonify({"users": [dict(r) for r in rows]})


@users_bp.route("", methods=["POST"])
@require_auth
@require_role("admin")
def create_user():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    display_name = data.get("display_name")
    role = data.get("role")
    if not username or not password or not display_name or role not in ("admin", "staff"):
        return jsonify({"error": "請填寫帳號、密碼、顯示名稱與角色"}), 400

    conn = get_db()
    existing = conn.execute("SELECT id FROM admin_users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "帳號已存在"}), 409

    cur = conn.execute(
        "INSERT INTO admin_users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
        (username, generate_password_hash(password), display_name, role),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, username, display_name, role, created_at FROM admin_users WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    conn.close()

    log_action(g.user["name"], "新增使用者", f"{username}（{role}）")
    return jsonify({"user": dict(row)}), 201

from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash

from ..auth import require_auth, sign_token
from ..db import get_db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "請輸入帳號與密碼"}), 400

    conn = get_db()
    user = conn.execute("SELECT * FROM admin_users WHERE username = ?", (username,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "帳號或密碼錯誤"}), 401

    token = sign_token(user)
    return jsonify(
        {
            "token": token,
            "user": {
                "username": user["username"],
                "display_name": user["display_name"],
                "role": user["role"],
            },
        }
    )


@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():
    return jsonify({"user": g.user})

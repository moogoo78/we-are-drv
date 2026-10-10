import os
import time
from functools import wraps

import jwt
from flask import g, jsonify, request

SECRET = os.environ["JWT_SECRET"]


def sign_token(user):
    payload = {
        "sub": user["id"],
        "username": user["username"],
        "role": user["role"],
        "name": user["display_name"],
        "iat": int(time.time()),
        "exp": int(time.time()) + 8 * 3600,
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def sign_student_token(id_number, name):
    payload = {
        "sub": id_number,
        "typ": "student",
        "name": name,
        "iat": int(time.time()),
        "exp": int(time.time()) + 2 * 3600,
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def _decode_bearer():
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else None
    if not token:
        return None, (jsonify({"error": "未登入"}), 401)
    try:
        return jwt.decode(token, SECRET, algorithms=["HS256"]), None
    except jwt.PyJWTError:
        return None, (jsonify({"error": "登入已逾期，請重新登入"}), 401)


def require_auth(f):
    """後台（管理員／承辦人員）登入驗證；學員 token 不可通過。"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        claims, err = _decode_bearer()
        if err:
            return err
        if claims.get("typ") == "student" or claims.get("role") not in ("admin", "staff"):
            return jsonify({"error": "權限不足"}), 403
        g.user = claims
        return f(*args, **kwargs)

    return wrapper


def require_student(f):
    """「我的防災士」學員登入驗證，g.student["sub"] 為身分證字號。"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        claims, err = _decode_bearer()
        if err:
            return err
        if claims.get("typ") != "student":
            return jsonify({"error": "請以學員身分登入"}), 403
        g.student = claims
        return f(*args, **kwargs)

    return wrapper


def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = getattr(g, "user", None)
            if not user or user.get("role") not in roles:
                return jsonify({"error": "權限不足"}), 403
            return f(*args, **kwargs)

        return wrapper

    return decorator

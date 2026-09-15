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


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else None
        if not token:
            return jsonify({"error": "未登入"}), 401
        try:
            g.user = jwt.decode(token, SECRET, algorithms=["HS256"])
        except jwt.PyJWTError:
            return jsonify({"error": "登入已逾期，請重新登入"}), 401
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

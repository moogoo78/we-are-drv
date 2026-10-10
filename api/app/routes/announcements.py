from flask import Blueprint, g, jsonify, request

from ..auth import require_auth, require_role
from ..db import get_db
from ..log import log_action

announcements_bp = Blueprint("announcements", __name__)

CATEGORIES = {"register", "batch", "change", "cert", "general"}
EDITABLE_FIELDS = ("title", "category", "content", "pinned", "published_at")


def _clean(data):
    fields = {k: data[k] for k in EDITABLE_FIELDS if k in data}
    if "category" in fields and fields["category"] not in CATEGORIES:
        fields["category"] = "general"
    if "pinned" in fields:
        fields["pinned"] = 1 if fields["pinned"] in (True, 1, "1", "true", "on") else 0
    if "published_at" in fields and not fields["published_at"]:
        del fields["published_at"]
    return fields


@announcements_bp.route("", methods=["GET"])
@require_auth
def list_all():
    conn = get_db()
    rows = conn.execute("SELECT * FROM announcements ORDER BY published_at DESC, id DESC").fetchall()
    conn.close()
    return jsonify({"announcements": [dict(r) for r in rows]})


@announcements_bp.route("", methods=["POST"])
@require_auth
@require_role("admin", "staff")
def create():
    fields = _clean(request.get_json(silent=True) or {})
    if not fields.get("title"):
        return jsonify({"error": "請填寫公告標題"}), 400
    conn = get_db()
    cur = conn.execute(
        f"INSERT INTO announcements ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
        tuple(fields.values()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM announcements WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    log_action(g.user["name"], "新增公告", fields["title"])
    return jsonify({"announcement": dict(row)}), 201


@announcements_bp.route("/<int:ann_id>", methods=["PATCH"])
@require_auth
@require_role("admin", "staff")
def update(ann_id):
    fields = _clean(request.get_json(silent=True) or {})
    conn = get_db()
    if not conn.execute("SELECT 1 FROM announcements WHERE id = ?", (ann_id,)).fetchone():
        conn.close()
        return jsonify({"error": "找不到公告"}), 404
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE announcements SET {set_clause} WHERE id = ?", (*fields.values(), ann_id))
        conn.commit()
    row = conn.execute("SELECT * FROM announcements WHERE id = ?", (ann_id,)).fetchone()
    conn.close()
    log_action(g.user["name"], "更新公告", row["title"])
    return jsonify({"announcement": dict(row)})


@announcements_bp.route("/<int:ann_id>", methods=["DELETE"])
@require_auth
@require_role("admin", "staff")
def delete(ann_id):
    conn = get_db()
    row = conn.execute("SELECT title FROM announcements WHERE id = ?", (ann_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "找不到公告"}), 404
    conn.execute("DELETE FROM announcements WHERE id = ?", (ann_id,))
    conn.commit()
    conn.close()
    log_action(g.user["name"], "刪除公告", row["title"])
    return "", 204

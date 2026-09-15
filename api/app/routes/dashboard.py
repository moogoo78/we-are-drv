from datetime import date

from flask import Blueprint, jsonify

from ..auth import require_auth
from ..db import get_db

dashboard_bp = Blueprint("dashboard", __name__)


def age_bucket(birth_date_str):
    y, m, d = (int(x) for x in birth_date_str.split("-"))
    today = date.today()
    age = today.year - y - ((today.month, today.day) < (m, d))
    if age < 30:
        return "20-29"
    if age < 40:
        return "30-39"
    if age < 50:
        return "40-49"
    if age < 60:
        return "50-59"
    return "60+"


@dashboard_bp.route("/stats", methods=["GET"])
@require_auth
def stats():
    conn = get_db()
    totals_row = conn.execute(
        """SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
             SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved,
             SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
             SUM(CASE WHEN status = 'waitlist' THEN 1 ELSE 0 END) AS waitlist,
             SUM(CASE WHEN status = 'needs_more_info' THEN 1 ELSE 0 END) AS needs_more_info
           FROM registrations"""
    ).fetchone()
    totals = {k: (totals_row[k] or 0) for k in totals_row.keys()}

    by_district = [dict(r) for r in conn.execute(
        "SELECT district, COUNT(*) AS n FROM registrations GROUP BY district ORDER BY n DESC"
    ).fetchall()]

    by_sex = [dict(r) for r in conn.execute(
        "SELECT sex, COUNT(*) AS n FROM registrations GROUP BY sex ORDER BY n DESC"
    ).fetchall()]

    by_occupation = [dict(r) for r in conn.execute(
        """SELECT COALESCE(NULLIF(occupation, ''), '未填寫') AS occupation, COUNT(*) AS n
           FROM registrations GROUP BY occupation ORDER BY n DESC"""
    ).fetchall()]

    by_batch = [dict(r) for r in conn.execute(
        """SELECT b.name, COUNT(r.id) AS n FROM batches b
           LEFT JOIN registrations r ON r.batch_id = b.id
           GROUP BY b.id, b.name ORDER BY b.id"""
    ).fetchall()]

    birth_dates = [r["birth_date"] for r in conn.execute("SELECT birth_date FROM registrations").fetchall()]
    conn.close()

    age_counts = {}
    for bd in birth_dates:
        bucket = age_bucket(bd)
        age_counts[bucket] = age_counts.get(bucket, 0) + 1
    by_age = [{"bucket": k, "n": v} for k, v in age_counts.items()]

    return jsonify({
        "totals": totals,
        "by_district": by_district,
        "by_sex": by_sex,
        "by_age": by_age,
        "by_occupation": by_occupation,
        "by_batch": by_batch,
    })

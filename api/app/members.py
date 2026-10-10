import json

from .geo import parse_district_village


def upsert_member_from_registration(conn, registration_id, cert_no):
    """結訓並核發證照後，將學員列入防災士名冊（以身分證字號為準，已存在則更新）。"""
    reg = conn.execute(
        """SELECT r.*, b.name AS batch_name, b.end_date FROM registrations r
           JOIN batches b ON b.id = r.batch_id WHERE r.id = ?""",
        (registration_id,),
    ).fetchone()
    if not reg:
        return
    district, village = reg["district"], reg["village"]
    if not village:
        _, village = parse_district_village(reg["address"])
    values = {
        "name": reg["name"],
        "sex": reg["sex"],
        "birth_date": reg["birth_date"],
        "phone": reg["phone"],
        "email": reg["email"],
        "address": reg["address"],
        "district": district,
        "village": village,
        "occupation": reg["occupation"],
        "unit": reg["unit_village"],
        "specialty": reg["specialty"] or "[]",
        "support_willing": 1 if reg["support_pref"] in ("願意", "可支援") else 0,
        "cert_no": cert_no,
        "training_name": reg["batch_name"],
        "trained_on": reg["end_date"],
        "source": "training",
        "registration_id": registration_id,
    }
    existing = conn.execute("SELECT id FROM members WHERE id_number = ?", (reg["id_number"],)).fetchone()
    if existing:
        set_clause = ", ".join(f"{k} = ?" for k in values)
        conn.execute(f"UPDATE members SET {set_clause} WHERE id = ?", (*values.values(), existing["id"]))
    else:
        values["id_number"] = reg["id_number"]
        cols = ", ".join(values)
        conn.execute(
            f"INSERT INTO members ({cols}) VALUES ({', '.join('?' for _ in values)})",
            tuple(values.values()),
        )


def json_list(v):
    if not v:
        return []
    try:
        parsed = json.loads(v)
        return parsed if isinstance(parsed, list) else [str(v)]
    except (ValueError, TypeError):
        return [s.strip() for s in str(v).split(",") if s.strip()]

from .db import get_db


def log_action(actor, action, detail=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO operation_logs (actor, action, detail) VALUES (?, ?, ?)",
        (actor, action, detail),
    )
    conn.commit()
    conn.close()

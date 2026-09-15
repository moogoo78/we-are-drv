import os
import sqlite3

from werkzeug.security import generate_password_hash

from .db import get_db

SEED_BATCHES = [
    ("第 1 梯次", "2026-06-20", "2026-06-21", "基隆市消防局訓練中心", 60, "closed"),
    ("第 2 梯次", "2026-07-12", "2026-07-13", "七堵區公所禮堂", 60, "closed"),
    ("第 3 梯次", "2026-08-01", "2026-08-02", "中正區行政中心 3 樓", 60, "full"),
    ("第 4 梯次", "2026-09-20", "2026-09-21", "基隆市消防局訓練中心", 60, "open"),
]


def init_db():
    conn = get_db()
    with open(os.path.join(os.path.dirname(__file__), "..", "db", "init.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()

    user_count = conn.execute("SELECT COUNT(*) AS n FROM admin_users").fetchone()["n"]
    if user_count == 0:
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD", "changeme123")
        try:
            conn.execute(
                "INSERT INTO admin_users (username, password_hash, display_name, role) VALUES (?, ?, ?, 'admin')",
                (username, generate_password_hash(password), "基隆市消防局"),
            )
            conn.commit()
            print(f'[migrate] seeded initial admin user "{username}"', flush=True)
        except sqlite3.IntegrityError:
            pass  # another worker process already seeded it

    batch_count = conn.execute("SELECT COUNT(*) AS n FROM batches").fetchone()["n"]
    if batch_count == 0:
        try:
            for name, start, end, location, capacity, status in SEED_BATCHES:
                conn.execute(
                    """INSERT INTO batches (name, start_date, end_date, location, capacity, status, register_start, register_end)
                       VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-1 day'), ?)""",
                    (name, start, end, location, capacity, status, end),
                )
            conn.commit()
            print("[migrate] seeded 4 initial batches", flush=True)
        except sqlite3.IntegrityError:
            conn.rollback()  # another worker process already seeded batches

    conn.close()

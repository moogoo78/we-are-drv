import os
import secrets
import sqlite3

from werkzeug.security import generate_password_hash

from .db import get_db
from .members import upsert_member_from_registration
from .site import SITE

# 既有資料庫升級時補上的欄位（新安裝時已包含在 init.sql）
ADDED_COLUMNS = {
    "registrations": [
        ("village", "TEXT"),
        ("specialty", "TEXT NOT NULL DEFAULT '[]'"),
        ("home_phone", "TEXT"),
        ("education", "TEXT"),
        ("job_title", "TEXT"),
        ("emergency_name", "TEXT"),
        ("emergency_relation", "TEXT"),
        ("emergency_phone", "TEXT"),
        ("checked_in", "INTEGER NOT NULL DEFAULT 0"),
        ("written_score", "INTEGER"),
        ("written_passed", "INTEGER"),
        ("practical_passed", "INTEGER"),
        ("notified_at", "TEXT"),
    ],
    "batches": [
        ("auto_close", "INTEGER NOT NULL DEFAULT 0"),
        ("quiz_open", "INTEGER NOT NULL DEFAULT 0"),
        ("survey_open", "INTEGER NOT NULL DEFAULT 0"),
        ("material_key", "TEXT"),
    ],
    "instructors": [
        ("signature_path", "TEXT"),
    ],
    # 升級前核發的證照視為已核發
    "certificates": [
        ("apply_status", "TEXT NOT NULL DEFAULT 'issued'"),
        ("mailed_at", "TEXT"),
        ("collected_at", "TEXT"),
    ],
}

DEFAULT_SETTINGS = {
    "quiz_pass_score": "60",
}


def add_missing_columns(conn):
    for table, columns in ADDED_COLUMNS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, decl in columns:
            if name not in existing:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                    print(f"[migrate] added column {table}.{name}", flush=True)
                except sqlite3.OperationalError:
                    pass  # another worker process already added it
    conn.commit()

SEED_BATCHES = [
    ("第 1 梯次", "2026-06-20", "2026-06-21", SITE["training_location"], 60, "closed"),
    ("第 2 梯次", "2026-07-12", "2026-07-13", SITE["training_location"], 60, "closed"),
    ("第 3 梯次", "2026-08-01", "2026-08-02", SITE["training_location"], 60, "full"),
    ("第 4 梯次", "2026-09-20", "2026-09-21", SITE["training_location"], 60, "open"),
]

SEED_INSTRUCTORS = [
    ("李國強", "CPR/AED 術科講師"),
    ("吳建民", "防災概論講師"),
    ("黃志明", "災害應變實作講師"),
]


def init_db():
    conn = get_db()
    with open(os.path.join(os.path.dirname(__file__), "..", "db", "init.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    add_missing_columns(conn)

    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

    user_count = conn.execute("SELECT COUNT(*) AS n FROM admin_users").fetchone()["n"]
    if user_count == 0:
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD", "changeme123")
        try:
            conn.execute(
                "INSERT INTO admin_users (username, password_hash, display_name, role) VALUES (?, ?, ?, 'admin')",
                (username, generate_password_hash(password), SITE["agency"]),
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
                       VALUES (?, ?, ?, ?, ?, ?, date('now', '-1 day'),
                               CASE WHEN ? = 'open' THEN date('now', '+30 day') ELSE ? END)""",
                    (name, start, end, location, capacity, status, status, end),
                )
            conn.commit()
            print("[migrate] seeded 4 initial batches", flush=True)
        except sqlite3.IntegrityError:
            conn.rollback()  # another worker process already seeded batches

    instructor_count = conn.execute("SELECT COUNT(*) AS n FROM instructors").fetchone()["n"]
    if instructor_count == 0:
        for name, title in SEED_INSTRUCTORS:
            conn.execute("INSERT INTO instructors (name, title) VALUES (?, ?)", (name, title))
        conn.commit()
        print("[migrate] seeded 3 initial instructors", flush=True)

        instructors = {
            row["name"]: row["id"]
            for row in conn.execute("SELECT id, name FROM instructors").fetchall()
        }
        batch = conn.execute("SELECT id FROM batches WHERE name = ?", ("第 4 梯次",)).fetchone()
        if batch:
            seed_sessions = [
                ("2026-09-20", "09:00", "防災概論", instructors.get("吳建民"), 2),
                ("2026-09-20", "13:00", "災害應變實作", instructors.get("黃志明"), 4),
                ("2026-09-21", "09:00", "CPR/AED 術科", instructors.get("李國強"), 3),
                ("2026-09-21", "15:00", "結業測驗", None, 1),
            ]
            for session_date, start_time, topic, instructor_id, hours in seed_sessions:
                conn.execute(
                    """INSERT INTO course_sessions (batch_id, session_date, start_time, topic, instructor_id, hours)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (batch["id"], session_date, start_time, topic, instructor_id, hours),
                )
            conn.commit()
            print("[migrate] seeded course schedule for 第 4 梯次", flush=True)

    for row in conn.execute("SELECT id FROM batches WHERE material_key IS NULL").fetchall():
        conn.execute("UPDATE batches SET material_key = ? WHERE id = ?", (secrets.token_urlsafe(12), row["id"]))
    conn.commit()

    # 已核發證照但尚未列入防災士名冊者（升級前的資料）
    missing = conn.execute(
        """SELECT c.registration_id, c.cert_no FROM certificates c
           LEFT JOIN members m ON m.registration_id = c.registration_id
           WHERE c.apply_status = 'issued' AND m.id IS NULL"""
    ).fetchall()
    for row in missing:
        upsert_member_from_registration(conn, row["registration_id"], row["cert_no"])
    if missing:
        conn.commit()
        print(f"[migrate] added {len(missing)} certified trainees to members", flush=True)

    conn.close()

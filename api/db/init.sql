-- 基隆市防災士培訓報名系統 — 資料庫 schema（SQLite）

CREATE TABLE IF NOT EXISTS admin_users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'staff')),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  location TEXT NOT NULL,
  capacity INTEGER NOT NULL,
  register_start TEXT,
  register_end TEXT,
  status TEXT NOT NULL DEFAULT 'upcoming' CHECK (status IN ('upcoming', 'open', 'full', 'closed')),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS registrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reg_no TEXT UNIQUE,
  batch_id INTEGER NOT NULL REFERENCES batches(id),
  name TEXT NOT NULL,
  id_number TEXT NOT NULL,
  birth_date TEXT NOT NULL,
  sex TEXT NOT NULL,
  phone TEXT NOT NULL,
  email TEXT NOT NULL,
  district TEXT NOT NULL,
  address TEXT NOT NULL,
  occupation TEXT,
  unit_village TEXT,
  support_pref TEXT NOT NULL,
  meal_pref TEXT NOT NULL,
  other_needs TEXT,
  existing_certs TEXT NOT NULL DEFAULT '[]',
  cert_number TEXT,
  photo_path TEXT,
  agree_consent INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'waitlist', 'needs_more_info')),
  review_note TEXT,
  reviewed_by TEXT,
  reviewed_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (batch_id, id_number)
);

CREATE TABLE IF NOT EXISTS instructors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  title TEXT,
  phone TEXT,
  email TEXT,
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS course_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES batches(id),
  session_date TEXT NOT NULL,
  start_time TEXT,
  topic TEXT NOT NULL,
  instructor_id INTEGER REFERENCES instructors(id),
  hours REAL NOT NULL DEFAULT 2,
  material_url TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS certificates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  registration_id INTEGER NOT NULL UNIQUE REFERENCES registrations(id),
  cert_no TEXT UNIQUE NOT NULL,
  delivery_method TEXT NOT NULL DEFAULT 'pickup' CHECK (delivery_method IN ('pickup', 'mail')),
  pickup_status TEXT NOT NULL DEFAULT 'not_collected' CHECK (pickup_status IN ('not_collected', 'shipping', 'collected')),
  note TEXT,
  issued_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS operation_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_registrations_batch ON registrations(batch_id);
CREATE INDEX IF NOT EXISTS idx_registrations_id_number ON registrations(id_number);
CREATE INDEX IF NOT EXISTS idx_registrations_status ON registrations(status);
CREATE INDEX IF NOT EXISTS idx_course_sessions_batch ON course_sessions(batch_id);
CREATE INDEX IF NOT EXISTS idx_course_sessions_instructor ON course_sessions(instructor_id);

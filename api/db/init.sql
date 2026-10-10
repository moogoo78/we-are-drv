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
  auto_close INTEGER NOT NULL DEFAULT 0,
  quiz_open INTEGER NOT NULL DEFAULT 0,
  survey_open INTEGER NOT NULL DEFAULT 0,
  material_key TEXT,
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
  village TEXT,
  specialty TEXT NOT NULL DEFAULT '[]',
  home_phone TEXT,
  education TEXT,
  job_title TEXT,
  emergency_name TEXT,
  emergency_relation TEXT,
  emergency_phone TEXT,
  checked_in INTEGER NOT NULL DEFAULT 0,
  written_score INTEGER,
  written_passed INTEGER,
  practical_passed INTEGER,
  notified_at TEXT,
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
  signature_path TEXT,
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
  apply_status TEXT NOT NULL DEFAULT 'applying' CHECK (apply_status IN ('applying', 'submitted', 'issued')),
  mailed_at TEXT,
  collected_at TEXT,
  issued_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS operation_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 防災士名冊：歷年匯入（消防署名單）＋ 本系統結訓發證者
CREATE TABLE IF NOT EXISTS members (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  id_number TEXT UNIQUE,
  sex TEXT,
  birth_date TEXT,
  phone TEXT,
  email TEXT,
  address TEXT,
  district TEXT,
  village TEXT,
  occupation TEXT,
  unit TEXT,
  specialty TEXT NOT NULL DEFAULT '[]',
  support_willing INTEGER NOT NULL DEFAULT 0,
  cert_no TEXT,
  training_name TEXT,
  trained_on TEXT,
  source TEXT NOT NULL DEFAULT 'import' CHECK (source IN ('import', 'training')),
  registration_id INTEGER UNIQUE REFERENCES registrations(id),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS announcements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'general' CHECK (category IN ('register', 'batch', 'change', 'cert', 'general')),
  content TEXT,
  pinned INTEGER NOT NULL DEFAULT 0,
  published_at TEXT NOT NULL DEFAULT (date('now')),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS course_photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES batches(id),
  file_path TEXT NOT NULL,
  caption TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS course_materials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER REFERENCES batches(id),
  instructor_id INTEGER REFERENCES instructors(id),
  title TEXT NOT NULL,
  file_path TEXT NOT NULL,
  original_name TEXT,
  visibility TEXT NOT NULL DEFAULT 'enrolled' CHECK (visibility IN ('public', 'enrolled')),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quiz_questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  qtype TEXT NOT NULL CHECK (qtype IN ('tf', 'choice')),
  question TEXT NOT NULL,
  options TEXT NOT NULL DEFAULT '[]',
  answer TEXT NOT NULL,
  points INTEGER NOT NULL DEFAULT 2,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  registration_id INTEGER NOT NULL UNIQUE REFERENCES registrations(id),
  answers TEXT NOT NULL,
  score INTEGER NOT NULL,
  passed INTEGER NOT NULL,
  submitted_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS survey_responses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  registration_id INTEGER NOT NULL UNIQUE REFERENCES registrations(id),
  answers TEXT NOT NULL,
  submitted_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 學員線上申請：證照遺失補發、參訓證明
CREATE TABLE IF NOT EXISTS applications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  registration_id INTEGER NOT NULL REFERENCES registrations(id),
  kind TEXT NOT NULL CHECK (kind IN ('reissue', 'attendance_proof')),
  reason TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'done', 'rejected')),
  admin_note TEXT,
  handled_by TEXT,
  handled_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 通知發送紀錄（Email 經 SMTP 寄出；簡訊目前匯出名單人工發送）
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel TEXT NOT NULL CHECK (channel IN ('email', 'sms')),
  category TEXT NOT NULL,
  registration_id INTEGER REFERENCES registrations(id),
  recipient_name TEXT,
  recipient TEXT NOT NULL,
  subject TEXT,
  body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sent', 'failed')),
  error TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  sent_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_registrations_batch ON registrations(batch_id);
CREATE INDEX IF NOT EXISTS idx_registrations_id_number ON registrations(id_number);
CREATE INDEX IF NOT EXISTS idx_registrations_status ON registrations(status);
CREATE INDEX IF NOT EXISTS idx_course_sessions_batch ON course_sessions(batch_id);
CREATE INDEX IF NOT EXISTS idx_course_sessions_instructor ON course_sessions(instructor_id);
CREATE INDEX IF NOT EXISTS idx_members_district ON members(district);
CREATE INDEX IF NOT EXISTS idx_applications_registration ON applications(registration_id);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);

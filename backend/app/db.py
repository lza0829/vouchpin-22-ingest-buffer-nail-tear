from __future__ import annotations
import sqlite3
from app.config import DB_PATH

SCHEMA = '''
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  face_value REAL NOT NULL,
  min_spend REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS coupon_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  business_day TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS redeem_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coupon_code TEXT NOT NULL UNIQUE,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL,
  business_day TEXT NOT NULL,
  event_id INTEGER NOT NULL,
  batch_id INTEGER,
  status TEXT NOT NULL DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS redeem_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  business_day TEXT NOT NULL,
  status TEXT NOT NULL,
  fact_count INTEGER NOT NULL DEFAULT 0,
  total_amount REAL NOT NULL DEFAULT 0,
  sealed_at TEXT,
  note TEXT NOT NULL DEFAULT '',
  buffer_remaining INTEGER NOT NULL DEFAULT 0,
  buffer_amount REAL NOT NULL DEFAULT 0,
  buffer_fingerprint TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS redeem_buffer (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL,
  business_day TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  enqueued_at TEXT NOT NULL DEFAULT (datetime('now')),
  flush_status TEXT NOT NULL DEFAULT 'pending',
  flush_error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_redeem_buffer_day ON redeem_buffer(business_day, flush_status, id);
'''

# 老库平滑升级：补齐批次快照列。
_BATCH_MIGRATIONS = [
    ("buffer_remaining", "ALTER TABLE redeem_batches ADD COLUMN buffer_remaining INTEGER NOT NULL DEFAULT 0"),
    ("buffer_amount", "ALTER TABLE redeem_batches ADD COLUMN buffer_amount REAL NOT NULL DEFAULT 0"),
    ("buffer_fingerprint", "ALTER TABLE redeem_batches ADD COLUMN buffer_fingerprint TEXT NOT NULL DEFAULT ''"),
]


def connect(immediate: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if immediate:
        conn.execute("BEGIN IMMEDIATE")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(redeem_batches)").fetchall()}
    for column, ddl in _BATCH_MIGRATIONS:
        if column not in existing:
            conn.execute(ddl)


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()

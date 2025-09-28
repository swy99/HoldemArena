# app/routes/init_db.py

import sqlite3

conn = sqlite3.connect("users.db")
cursor = conn.cursor()

# ✅ users 테이블
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    uid TEXT PRIMARY KEY,
    id TEXT,
    pw_hash TEXT,
    username TEXT,
    created_at TEXT,
    deleted BOOLEAN DEFAULT 0,
    deleted_at TEXT
)
""")

# ✅ linked_accounts 테이블
cursor.execute("""
CREATE TABLE IF NOT EXISTS linked_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_uid TEXT NOT NULL,
    provider TEXT NOT NULL,          -- 'google', 'apple', 'facebook', 'x'
    provider_id TEXT NOT NULL,       -- SNS 제공자의 고유 ID (ex: Google의 sub)
    email TEXT,
    picture TEXT,
    FOREIGN KEY (user_uid) REFERENCES users(uid),
    UNIQUE(user_id, provider, provider_id)
)
""")

# ✅ friends 테이블 (정렬저장)
cursor.execute("""
CREATE TABLE IF NOT EXISTS friends (
    uid1 TEXT NOT NULL,
    uid2 TEXT NOT NULL,
    PRIMARY KEY (uid1, uid2)
)
""")

# friend_requests 테이블
cursor.execute("""
CREATE TABLE IF NOT EXISTS friend_requests (
    from_uid TEXT NOT NULL,
    to_uid TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (from_uid, to_uid)
);
""")

# ✅ chat_logs 테이블
cursor.execute("""
CREATE TABLE IF NOT EXISTS chat_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,     -- ✅ 두 UID 오름차순 정렬해서 만든 room ID (예: "a1:b2")
    sender_uid TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL    -- ISO8601, 또는 필요하면 INTEGER로 변경 가능
);
""")

# chat_logs 인덱스 생성
cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_chat_logs_room_time ON chat_logs (room_id, timestamp DESC);
""")

# game_messages 테이블
cursor.execute("""
CREATE TABLE IF NOT EXISTS game_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    from_uid TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp TEXT NOT NULL
)
""")

# game_history
cursor.execute("""
CREATE TABLE IF NOT EXISTS game_history (
    game_id TEXT PRIMARY KEY,
    game_type TEXT NOT NULL,      -- 예: 'quick_play', 'ranked', ...
    created_at TEXT NOT NULL,
    duration REAL,
    players TEXT NOT NULL,     -- JSON: {"uid1": "username1", "uid2": "username2", ...}
    rankings TEXT NOT NULL     -- JSON: {"uid1": 1, "uid2": 2, ...}
)
""")

conn.commit()
conn.close()

print("✅ users.db 초기화 완료 (users, linked_accounts, friends, friend_requests, chat_logs(+index), game_messages, game_history)")

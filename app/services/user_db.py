# app/services/user_db.py

import sqlite3
from typing import List
import json
from datetime import datetime

# SQLite 연결 (DB 파일은 프로젝트 루트의 users.db)
DB_PATH = "users.db"

# ✅ UID → 유저명 (삭제된 유저는 예외 발생)
def get_username_by_uid(uid: str) -> str:
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE uid = ? AND deleted = 0", (uid,))
        row = cursor.fetchone()
    if not row:
        raise ValueError(f"UID에 해당하는 유저가 존재하지 않거나 삭제됨: {uid}")
    return row[0]

# ✅ 닉네임 → UID (삭제된 유저는 무시)
def get_uid_by_username(username: str) -> str | None:
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT uid FROM users WHERE username = ? AND deleted = 0", (username,))
        row = cursor.fetchone()
    return row[0] if row else None

# ✅ UID 여러 개 → 닉네임 (삭제된 유저 제외)
def get_usernames_by_uids(uids: list[str]) -> dict[str, str]:
    if not uids:
        return {}

    placeholders = ",".join(["?"] * len(uids))
    query = f"""
        SELECT uid, username FROM users
        WHERE uid IN ({placeholders}) AND deleted = 0
    """
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute(query, uids)
        rows = cursor.fetchall()
    return {uid: username for uid, username in rows}

# ✅ 소셜 로그인 → UID (삭제된 유저 제외)
def get_uid_by_provider(provider: str, provider_id: str) -> str | None:
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT la.user_uid
            FROM linked_accounts la
            JOIN users u ON la.user_uid = u.uid
            WHERE la.provider = ? AND la.provider_id = ? AND u.deleted = 0
        """, (provider, provider_id))
        row = cursor.fetchone()
    return row[0] if row else None

# ✅ 구글 계정으로 가입
def create_user_with_google_account(uid: str, username: str, sub: str, email: str, picture: str, created_at: str):
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (uid, id, pw_hash, username, created_at)
            VALUES (?, NULL, NULL, ?, ?)
        """, (uid, username, created_at))
        
        cursor.execute("""
            INSERT INTO linked_accounts (user_uid, provider, provider_id, email, picture)
            VALUES (?, 'google', ?, ?, ?)
        """, (uid, sub, email, picture))
    
        conn.commit()

# ✅ 유저 소프트 삭제
def soft_delete_user(uid: str):
    """
    UID에 해당하는 유저를 논리적으로 삭제 처리한다.
    실제 row를 삭제하지 않고 deleted = 1, deleted_at 설정만 한다.
    """
    deleted_at = datetime.utcnow().isoformat()
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users
            SET deleted = 1, deleted_at = ?
            WHERE uid = ?
        """, (deleted_at, uid))
        conn.commit()
    
# ✅ 유저의 friends, friend_requests 관계 삭제
def delete_user_relationships(uid: str):
    """
    유저의 friends, friend_requests 관계만 삭제
    """
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM friends WHERE uid1 = ? OR uid2 = ?", (uid, uid))
        cursor.execute("DELETE FROM friend_requests WHERE from_uid = ? OR to_uid = ?", (uid, uid))
        conn.commit()
    
# ✅ 유저의 게임 기록 불러오기
def get_game_history_for_uid(uid: str, limit: int = 20) -> List[dict]:
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT game_id, game_type, created_at, duration, players, rankings
            FROM game_history
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()

    results = []
    print(rows)
    for game_id, game_type, created_at, duration, players_json, rankings_json in rows:
        players = json.loads(players_json)
        rankings = json.loads(rankings_json)

        if uid not in rankings:
            continue

        results.append({
            "game_id": game_id,
            "game_type": game_type,
            "created_at": created_at,
            "duration": duration,
            "rank": rankings[uid],
            "username": players.get(uid, "(Unknown)"),
            "total_players": len(players),
        })

    return results
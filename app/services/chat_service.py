# app/services/chat_service.py

import sqlite3
from datetime import datetime

DB_PATH = "users.db"  # 기존 DB 경로



async def save_game_chat(game_id: str, from_uid: str, text: str):
    """
    게임 채팅 메시지를 저장한다.

    Args:
        game_id (str): 게임 ID
        from_uid (str): 보낸 사람의 UID
        text (str): 채팅 내용
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    timestamp = datetime.utcnow().isoformat()

    cursor.execute("""
        INSERT INTO game_messages (game_id, from_uid, text, timestamp)
        VALUES (?, ?, ?, ?)
    """, (game_id, from_uid, text, timestamp))

    conn.commit()
    conn.close()


async def get_recent_game_chats(game_id: str, limit: int = 20) -> list[dict]:
    """
    주어진 game_id에 대해 최근 game 채팅 기록을 불러온다.

    Args:
        game_id (str): 조회할 게임 ID
        limit (int): 불러올 최대 메시지 수 (기본 20개)

    Returns:
        list[dict]: {"from": str, "text": str, "timestamp": str} 형태의 리스트
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT from_uid, text, timestamp
        FROM game_messages
        WHERE game_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (game_id, limit))

    rows = cursor.fetchall()
    conn.close()

    messages = []
    for from_uid, text, timestamp in reversed(rows):
        messages.append({
            "from": from_uid,  # from_uid 그대로 리턴
            "text": text,
            "timestamp": timestamp,
        })
    return messages

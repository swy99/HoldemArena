# app/services/history_logger.py
import sqlite3
import json
from datetime import datetime

DB_PATH = "users.db"

def save_game_result(game_id: str, game_type: str, player_uid_name_map: dict[str, str], rankings: dict[str, int], duration: float):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    created_at = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT OR REPLACE INTO game_history (game_id, game_type, created_at, duration, players, rankings)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        game_id,
        game_type,
        created_at,
        duration,
        json.dumps(player_uid_name_map),
        json.dumps(rankings)
    ))
    conn.commit()
    conn.close()

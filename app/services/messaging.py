# app/services/messaging.py

import json
import redis
import redis.asyncio as async_redis
from pydantic import BaseModel

# Redis 클라이언트 (동기/비동기)
r = redis.Redis(decode_responses=True)
ar = async_redis.Redis(decode_responses=True)

# ================================================================
# ✅ GameManager → 상태 전파 메시지
# ================================================================

def publish_message(msg: BaseModel):
    """
    상태 메시지를 Redis Pub/Sub을 통해 전파.
    WebSocket 직접 전송은 하지 않음. 
    WebSocket 서버가 Redis 구독을 통해 전송을 담당함.
    """
    assert hasattr(msg, "game_id") and hasattr(msg, "player_id")
    r.publish("outgoing_ws", msg.json())

# ================================================================
# ✅ 게임 종료 시 Redis 정리
# ================================================================

def end_game(game_id: str):
    """
    게임 종료 시 Redis 내 유저-게임 관련 상태 제거
    """
    print(f"🪩 게임 종료 처리 시작: {game_id}")

    uids = r.hgetall(f"player_id_to_uid:{game_id}").values()
    for uid in uids:
        r.delete(f"user:{uid}:game")

    for pid in ["A", "B", "C", "D", "E", "F", "G", "H"]:
        r.delete(f"game:{game_id}:player:{pid}:uid")

    r.delete(f"game:{game_id}:gm")
    r.delete(f"uid_to_player_id:{game_id}")
    r.delete(f"player_id_to_uid:{game_id}")

    print(f"✅ 게임 종료 처리 완료: {game_id}")

# ================================================================
# ✅ WebSocket 직접 전송 (login_server의 matchmaker에서 사용)
# ================================================================

async def send_ws(ws, payload: dict):
    try:
        await ws.send_json(payload)
        print(f"[send_ws] 전송: {payload}")
    except Exception as e:
        print(f"[send_ws] 오류: {e}")

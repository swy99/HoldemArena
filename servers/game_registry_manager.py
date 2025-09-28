# servers/game_registry_manager.py

import json
from datetime import datetime
from redis.asyncio import Redis
from pydantic import BaseModel

from app.services.game_manager import GameManager
from .registry import game_registry  # dict[game_id] → GameManager
from .logger_utils import make_logger  # 위에서 정의한 색상 로거

r = Redis(decode_responses=True)

async def game_registry_manager_loop(i: int):
    redis = Redis(decode_responses=True)
    logger = make_logger("game_registry_manager", i)
    queue_name = f"game_registry_manager_queue_{i}"

    logger(f"loop started. listening on {queue_name}")

    while True:
        try:
            _, raw = await redis.blpop(queue_name)
            logger(f"got sth")
            msg = json.loads(raw)
            msg_type = msg.get("type")
            body = msg.get("body", {})

            if msg_type == "init":
                game_id = body["game_id"]
                if game_id in game_registry:
                    logger(f"⚠️게임 {game_id:.4} 이미 존재함 → 무시")
                    continue
                
                game_type = body["game_type"]
                uids = body["uids"]
                player_ids = body["player_ids"]

                gm = GameManager(
                    game_id=game_id,
                    game_type=game_type,
                    uids=uids,
                    player_ids=player_ids,
                    **body["room_settings"]
                )
                game_registry[game_id] = gm
                await set_game_info_on_redis(game_id, uids, player_ids)
                logger(f"게임 {game_id:.4} 등록 완료")
                # GameManager 등록 후 game_step_handler_queue로 초기화 메시지 전송
                step_queue = f"game_step_handler_queue_{i}"
                await redis.rpush(step_queue, json.dumps({
                    "type": "game_init",
                    "game_id": game_id
                }))
                logger(f"game_step_handler_queue에 game_init 전송 완료: {game_id:.4}")

            elif msg_type == "gc":
                game_id = body["game_id"]
                gm = game_registry.get(game_id)
                if not gm:
                    logger(f"⚠️GC 요청 받았지만 {game_id:.4} 존재하지 않음 → 무시")
                    continue
                if not gm.done:
                    logger(f"⚠️GC 요청 받았지만 {game_id:.4} 아직 완료되지 않음 → 무시")
                    continue
                await clear_game_info_from_redis(game_id)
                del game_registry[game_id]
                logger(f"게임 {game_id:.4} 정리 완료 (del)")

            else:
                logger(f"⚠️알 수 없는 메시지 {msg_type=}")

        except Exception as e:
            logger(f"❌예외 발생: {e}")



# ================================================================
# ✅ 게임 종료 시 Redis 정리
# ================================================================
        
async def set_game_info_on_redis(game_id: str, uids: list[str], player_ids: list[str]):
    # 1:1 uid ↔ pid
    await r.hmset(f"uid_to_player_id:{game_id}", mapping={u: p for u, p in zip(uids, player_ids)})
    await r.hmset(f"player_id_to_uid:{game_id}", mapping={p: u for u, p in zip(uids, player_ids)})

    # 개별 플레이어 키
    for u, p in zip(uids, player_ids):
        await r.set(f"game:{game_id}:player:{p}:uid", u)
        await r.set(f"user:{u}:game", game_id)


async def clear_game_info_from_redis(game_id: str):
    """
    게임 종료 시 Redis 내 유저-게임 관련 상태 제거
    """
    logger = make_logger("game_registry_manager", i)
    
    logger(f"🪩게임 종료 redis 정리 시작: {game_id:.4}")

    uids = await r.hgetall(f"player_id_to_uid:{game_id}").values()
    for uid in uids:
        await r.delete(f"user:{uid}:game")

    for pid in ["A", "B", "C", "D", "E", "F", "G", "H"]:
        await r.delete(f"game:{game_id}:player:{pid}:uid")

    await r.delete(f"uid_to_player_id:{game_id}")
    await r.delete(f"player_id_to_uid:{game_id}")

    logger(f"✅게임 종료 redis 정리 완료: {game_id:.4}")
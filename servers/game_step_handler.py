# servers/game_step_handler.py

import json
import os
import traceback
from redis.asyncio import Redis
from time import time
from pydantic import BaseModel
from .registry import game_registry
from .logger_utils import make_logger
from app.protocol.message_models import *

r = Redis(decode_responses=True)

async def game_step_handler_loop(i: int):
    redis = Redis(decode_responses=True)
    logger = make_logger("game_step_handler", i)
    queue = f"game_step_handler_queue_{i}"

    logger(f"loop started. listening on {queue}")

    while True:
        try:
            _, raw = await redis.blpop(queue)
            msg = json.loads(raw)

            msg_type = msg.get("type")
            game_id = msg.get("game_id")
            gm = game_registry.get(game_id)
            messages = []

            if msg_type == "game_init":
                logger(f"game_init 메시지 수신: {game_id:.4}")
                
                if gm is None:
                    logger(f"등록되지 않은 game_id={game_id:.4} → 무시")
                else:
                    messages += gm.wake()
                    await push_timeout_request(game_id)
                

            elif msg_type == "action":
                if gm is None:
                    msg = ErrorMessage(
                        type="error",
                        game_id=game_id,
                        player_id=msg["player_id"],
                        payload=ErrorPayload(message=f"no such game is not found")
                    )
                    messages += [msg]
                else:
                    if _validate_user_action(msg, gm):
                        messages += gm.handle_action(
                            player_id=msg["player_id"],
                            amount=msg["amount"],
                            client_action_count=msg["action_count"],
                            received_at=msg["received_at"],
                            is_timeout=False
                        )
                        await push_timeout_request(game_id)
                    else:
                        msg = ErrorMessage(
                            type="error",
                            game_id=game_id,
                            player_id=msg["player_id"],
                            payload=ErrorPayload(message=f"action is not valid or timeout")
                        )
                        messages+= [msg]
                        await push_timeout_request(game_id)

            elif msg_type == "timeout_possibility":
                if gm is None:
                    logger(f"없는 game_id → 무시: {game_id:.4}")
                else:
                    if time() < gm.deadline:
                        logger(f"stale timeout_msg → 무시: {game_id:.4}")
                    else:
                        if gm.is_sleeping:
                            messages += gm.wake()
                        else:
                            messages += gm.handle_action(
                                amount=0,
                                client_action_count=gm.action_count,
                                received_at=time(),
                                is_timeout=True
                            )
                            await push_timeout_request(game_id)
            
            elif msg_type == "send_state_to_user":
                messages = []
                player_id = msg["player_id"]
                if gm is None:
                    logger(f"없는 game_id → 오류: {game_id:.4}")
                    msg = ErrorMessage(
                        type="error",
                        game_id=game_id,
                        player_id=player_id,
                        payload=ErrorPayload(message=f"action is not valid or timeout")
                    )
                    messages += [msg]
                else:
                    messages += gm._get_state(player_id)

            else:
                logger(f"⚠️알 수 없는 메시지 type={msg_type}")
            
            await request_publish_messages(messages)

        except Exception as e:
            logger(f"❌[EXCEPTION] {e}")
            traceback.print_exc()


def _validate_user_action(msg, gm):
    try:
        # 필수 필드 검증
        if msg["action_count"] != gm.action_count:
            return False
        if not isinstance(msg["amount"], int):
            return False
        if not isinstance(msg["received_at"], (int, float)):
            return False

        # 시간 검증: 데드라인을 초과했는가?
        if msg["received_at"] > gm.deadline - gm.grace:
            return False

        return True
    except Exception:
        return False

async def request_publish_messages(messages: list[BaseModel]):
    """
    상태 메시지를 Redis Pub/Sub을 통해 전파.
    WebSocket 직접 전송은 하지 않음. 
    WebSocket 서버가 Redis 구독을 통해 전송을 담당함.
    """
    
    for msg in messages:
        assert hasattr(msg, "game_id") and hasattr(msg, "player_id")
        await r.publish("outgoing_ws", msg.json())

async def push_timeout_request(game_id: str):
    import json

    # 워커 인덱스 결정
    import uuid
    num_workers = int(os.getenv("NUM_WORKERS", 1))
    worker_index = int(uuid.UUID(game_id)) % num_workers
    queue_name = f"game_timeout_detector_queue_{worker_index}"

    
    # 메시지 구성
    msg = {
        "game_id": game_id
    }

    # Redis 전송
    await r.rpush(queue_name, json.dumps(msg))
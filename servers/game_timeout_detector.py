# servers/game_timeout_detector.py

import json
from redis.asyncio import Redis
import asyncio
import traceback
from time import time

from .registry import game_registry, timeouts, deadline
from .logger_utils import make_logger

async def game_timeout_detector_loop(i: int):
    redis = Redis(decode_responses=True)
    logger = make_logger("game_timeout_detector", i)
    queue = f"game_timeout_detector_queue_{i}"
    step_queue = f"game_step_handler_queue_{i}"

    logger(f"loop started. listening on {queue}")

    while True:
        # 1. 타임아웃 정렬 갱신 요청 처리
        try:
            msg = await redis.blpop(queue, timeout=0.01)
            if msg:
                _, raw = msg
                data = json.loads(raw)
                game_id = data.get("game_id")
                gm = game_registry.get(game_id)
                logger(gm.game_id)
                logger(timeouts)
                logger(deadline)
                if gm:
                    if gm in timeouts:
                        if gm.deadline == deadline[gm.game_id]:
                            logger(f"⚠️이미 deadline이 최신임: {game_id:.4} {deadline[gm.game_id]=}")
                        timeouts.remove(gm)
                        del deadline[gm.game_id]
                    timeouts.add(gm)
                    deadline[gm.game_id] = gm.deadline
                    logger(f"정렬 갱신됨: {game_id:.4} {deadline=}")
        except Exception as e:
            logger(f"❌[EXCEPTION - 정렬 처리] {e}")
            traceback.print_exc()
            
        # 2. 타임아웃 도달 검사
        try:
            now = time()
            while len(timeouts) and timeouts[0].deadline <= now:
                gm = timeouts.pop(0)
                del deadline[gm.game_id]
                if gm.done:
                    continue
                msg = {
                    "type": "timeout_possibility",
                    "game_id": gm.game_id,
                }
                await redis.rpush(step_queue, json.dumps(msg))
                logger(f"timeout_possibility 전송: {gm.game_id:.4}")
        except Exception as e:
            logger(f"❌[EXCEPTION - 타임아웃 처리] {e}")
            traceback.print_exc()
        
        await asyncio.sleep(0.01)
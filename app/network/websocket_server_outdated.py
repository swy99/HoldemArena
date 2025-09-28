# app/network/websocket_server.py

import asyncio
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from jose import jwt
import redis
import json
import pickle
import os
from time import time

from redis.asyncio import Redis
from app.services.game_manager import GameManager
from app.network.nocache import NoCacheMiddleware

# ======================= 설정 ============================
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

r = redis.Redis(decode_responses=True)
r_bin = redis.Redis(decode_responses=False)

ws_registry: dict[str, WebSocket] = {}

# ======================= JWT ============================
def verify_jwt(token: str) -> str:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload["sub"]  # sub 필드 = uid

# ======================= PubSub =========================
async def subscribe_outgoing_ws():
    redis = Redis(decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("outgoing_ws")
    print(f"[ws out] listening")

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
            if message is None:
                await asyncio.sleep(0.01)
                continue

            try:
                payload = json.loads(message["data"])
                game_id = payload["game_id"]
                player_id = payload["player_id"]
                uid = await redis.get(f"game:{game_id}:player:{player_id}:uid")
                ws = ws_registry.get(uid)
                if ws:
                    uid_game_id = await redis.get(f"user:{uid}:game")
                    if uid_game_id != game_id:
                        print(f"[ws_out] 🚫 {uid}는 현재 이 게임({game_id})에 소속되지 않음 → 메시지 스킵")
                        continue
                    tosend = json.dumps(payload)
                    print(f"[ws_out] msg({message['type']}) sent to uid(...{uid[-5:]})")
                    await ws.send_text(tosend)
                else:
                    print(f"[ws_out] WebSocket not found for uid: {uid}")
            except Exception as e:
                print(f"[ws_out] outgoing_ws 전송 실패: {e}")
    except asyncio.CancelledError:
        print("[ws_out] task cancelled")
    finally:
        await pubsub.unsubscribe("outgoing_ws")
        await pubsub.close()



async def subscribe_start_game():
    redis = Redis(decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("start_game")
    print("[start_game] listener 시작됨")

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                await asyncio.sleep(0.01)
                continue

            try:
                print(f"[start_game] msg{message}")
                payload = json.loads(message["data"])
                game_id = payload["game_id"]
                game_type = payload["game_type"]
                uids = payload["uids"]
                player_ids = payload["player_ids"]

                # GameManager 생성
                gm = GameManager(game_id, game_type, uids, player_ids, chips=[2000]*len(uids), sb=10, bb=20, save_callback=save_to_redis)

                # UID ↔ PlayerID 매핑 저장
                set_game_redis_keys_with_ttl(game_id, uids, player_ids)

                print(f"[start_game] GameManager 생성 완료: {game_id}")
            except Exception as e:
                print(f"[start_game] 오류: {e}")
    except asyncio.CancelledError:
        print("[start_game] task cancelled")
    finally:
        await pubsub.unsubscribe("start_game")
        await pubsub.close()
        
        
def set_game_redis_keys_with_ttl(game_id: str, uids: list[str], player_ids: list[str], ttl: int = 2 * 3600):
    # 1:1 uid ↔ pid
    r.hmset(f"uid_to_player_id:{game_id}", mapping={u: p for u, p in zip(uids, player_ids)})
    r.hmset(f"player_id_to_uid:{game_id}", mapping={p: u for u, p in zip(uids, player_ids)})
    r.expire(f"uid_to_player_id:{game_id}", ttl)
    r.expire(f"player_id_to_uid:{game_id}", ttl)

    # 개별 플레이어 키
    for u, p in zip(uids, player_ids):
        r.set(f"game:{game_id}:player:{p}:uid", u, ex=ttl)
        r.set(f"user:{u}:game", game_id, ex=ttl)
        
        
def save_to_redis(gm: GameManager):
    key = f"game:{gm.game_id}:gm"
    ttl_seconds = 2 * 3600
    if not r_bin.exists(key):
        r_bin.setex(key, ttl_seconds, pickle.dumps(gm))
    else:
        r_bin.set(key, pickle.dumps(gm))  # 덮어쓰기 (TTL은 유지됨)
    

# ======================= FastAPI 설정 ===================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(NoCacheMiddleware)

ws_task = None
game_task = None

@app.on_event("startup")
async def startup_event():
    global ws_task, game_task
    ws_task = asyncio.create_task(subscribe_outgoing_ws())
    game_task = asyncio.create_task(subscribe_start_game())
    asyncio.create_task(handle_game_actions())
    asyncio.create_task(handle_timeouts())

@app.on_event("shutdown")
async def shutdown_event():
    global ws_task, game_task
    if ws_task:
        ws_task.cancel()
    if game_task:
        game_task.cancel()

# ======================= WebSocket 엔드포인트 ===============
@app.websocket("/quick_play_ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    uid = verify_jwt(token)
    try:
        await websocket.accept()
        ws_registry[uid] = websocket
        print(f"[ws]✅ UID 등록됨: {uid}, 연결 상태: {ws_registry.get(uid)}")

        # ✅ 연결 시 현재 게임 상태 전송
        game_id = r.get(f"user:{uid}:game")
        if not game_id:
            raise ValueError("현재 참여 중인 게임이 없습니다.")

        player_id = r.hget(f"uid_to_player_id:{game_id}", uid)
        if not player_id:
            raise ValueError("player_id를 찾을 수 없습니다.")

        gm_data = r_bin.get(f"game:{game_id}:gm")
        if gm_data is None:
            raise ValueError("게임 상태 정보를 찾을 수 없습니다.")

        gm: GameManager = pickle.loads(gm_data)
        gm._send_state(player_id)

        # ✅ 클라이언트 액션 수신 루프
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                print(f"[ws_endpoint] {data}")

                if data.get("type") != "action":
                    continue
                if "amount" not in data:
                    raise ValueError("amount 필드가 누락되었습니다.")

                r.publish("game_actions", json.dumps({
                    "game_id": game_id,
                    "uid": uid,
                    "amount": data["amount"],
                    "action_count": data.get("action_count")  # ✅ 여기 추가
                }))

            except Exception as e:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": str(e)
                }))

    except WebSocketDisconnect:
        print(f"[WebSocket] disconnected: {uid}")
    except Exception as e:
        await websocket.send_json({"type" : "error", "errormsg" : str(e)})
        print(f"[WebSocket Error] {e}")
    finally:
        if uid and uid in ws_registry:
            del ws_registry[uid]
        await websocket.close()


# 액션 수신 및 GameManager로 위임
async def handle_game_actions():
    redis = Redis(decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("game_actions")
    print("[handler] listening for game_actions")

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                await asyncio.sleep(0.01)
                continue

            try:
                data = json.loads(message["data"])
                game_id = data["game_id"]
                uid = data["uid"]
                amount = data["amount"]

                player_id = r.hget(f"uid_to_player_id:{game_id}", uid)
                if not player_id:
                    print(f"[handler] player_id not found for uid={uid}")
                    continue

                gm_data = r_bin.get(f"game:{game_id}:gm")
                if gm_data is None:
                    print(f"[handler] GameManager not found for game_id={game_id}")
                    continue

                gm: GameManager = pickle.loads(gm_data)
                client_action_count = data.get("action_count")
                await gm.handle_action(player_id, amount, client_action_count=client_action_count)

            except Exception as e:
                print(f"[handler] game_actions 처리 실패: {e}")
    except asyncio.CancelledError:
        print("[handler] task cancelled")
    finally:
        await pubsub.unsubscribe("game_actions")
        await pubsub.close()
        
        
async def handle_timeouts():
    redis = Redis(decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("game_timeouts")
    print("[timeout handler] listening for game_timeouts")

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                await asyncio.sleep(0.01)
                continue

            try:
                data = json.loads(message["data"])
                game_id = data["game_id"]
                player_id = data["player_id"]
                deadline = data["deadline"]
                remembered_action_count = data["action_count"]

                print(f"[timeout] waiting for {player_id}: sleep({deadline - time():.2f}s)")
                await asyncio.sleep(max(0, deadline - time()))
                print(f"[timeout] woke up for {player_id}")

                gm_data = r_bin.get(f"game:{game_id}:gm")
                if gm_data is None:
                    print(f"[timeout] ❌ GameManager not found at deadline for {player_id}")
                    continue

                gm: GameManager = pickle.loads(gm_data)
                if gm.action_count != remembered_action_count:
                    print(f"[timeout] skipped for {player_id}: remembered={remembered_action_count}, current={gm.action_count}")
                    continue

                print(f"[timeout] triggering for {player_id}: action_count={remembered_action_count}")
                await gm.handle_action(player_id, 0, ignore_timeout_check=True)

            except Exception as e:
                print(f"[timeout] error: {e}")

    except asyncio.CancelledError:
        print("[timeout handler] cancelled")
    finally:
        await pubsub.unsubscribe("game_timeouts")
        await pubsub.close()

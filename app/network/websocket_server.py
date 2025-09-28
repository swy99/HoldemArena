# app/network/websocket_server.py

import asyncio
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from jose import jwt
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

r = Redis(decode_responses=True)

ws_registry: dict[str, WebSocket] = {}

# ======================= JWT ============================
def verify_jwt(token: str) -> str:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload["sub"]  # sub 필드 = uid

# ======================= PubSub =========================
async def subscribe_outgoing_ws():
    pubsub = r.pubsub()
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
                uid = await r.get(f"game:{game_id}:player:{player_id}:uid")
                ws = ws_registry.get(uid)
                if ws:
                    uid_game_id = await r.get(f"user:{uid}:game")
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

@app.on_event("startup")
async def startup_event():
    global ws_task
    ws_task = asyncio.create_task(subscribe_outgoing_ws())

@app.on_event("shutdown")
async def shutdown_event():
    global ws_task
    if ws_task:
        ws_task.cancel()

# ======================= WebSocket 엔드포인트 ===============
@app.websocket("/quick_play_ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    uid = verify_jwt(token)
    try:
        await websocket.accept()
        ws_registry[uid] = websocket
        print(f"[ws]✅ UID 등록됨: {uid}, 연결 상태: {ws_registry.get(uid)}")

        # ✅ 연결 시 현재 게임 상태 전송
        game_id = await r.get(f"user:{uid}:game")
        if not game_id:
            raise ValueError("현재 참여 중인 게임이 없습니다. 잠시 후 재접속 시 해결될 수 있습니다.")

        player_id = await r.hget(f"uid_to_player_id:{game_id}", uid)
        if not player_id:
            raise ValueError("player_id를 찾을 수 없습니다. 잠시 후 재접속 시 해결될 수 있습니다.")

        await request_send_state(game_id, player_id)

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

                await push_action(game_id, player_id, data["amount"], data.get("action_count"))

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
        try:
            await websocket.close()
        except:
            pass
        

async def request_send_state(game_id: str, player_id: str):
    # 워커 인덱스 결정
    import uuid
    num_workers = int(os.getenv("NUM_WORKERS", 1))
    worker_index = int(uuid.UUID(game_id)) % num_workers
    step_queue = f"game_step_handler_queue_{worker_index}"
       
    msg = {
        "type": "send_state_to_user",
        "game_id": game_id,
        "player_id": player_id
    }
    await r.rpush(step_queue, json.dumps(msg))
    

async def push_action(game_id: str, player_id: str, amount: int, action_count: int):    # 워커 인덱스 결정
    import uuid
    num_workers = int(os.getenv("NUM_WORKERS", 1))
    worker_index = int(uuid.UUID(game_id)) % num_workers
    step_queue = f"game_step_handler_queue_{worker_index}"
       
    msg = {
        "type": "action",
        "game_id": game_id,
        "player_id": player_id,
        "amount": amount,
        "action_count": action_count,
        "received_at": time()
    }
    await r.rpush(step_queue, json.dumps(msg))
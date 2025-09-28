# app/network/chat_server.py

import asyncio
import json
import os
import sqlite3
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import jwt
from redis.asyncio import Redis
from app.services.presence_manager import set_ws_registry, friend_online, friend_offline, subscribe_presence
from pydantic import BaseModel
from app.network.nocache import NoCacheMiddleware

from app.protocol.message_models import (
    InviteRequest, 
)

from app.services.user_db import (
    get_username_by_uid,
    get_uid_by_username,
)

from app.services.party_manager import (
    get_party_leader,
)

class FriendRequestSend(BaseModel):
    username: str
    
class FriendAddRequest(BaseModel):
    friend_username: str

class FriendRequestResponse(BaseModel):
    from_uid: str
    accept: bool

class FriendRequestResponse(BaseModel):
    from_uid: str
    accept: bool

class MarkReadRequest(BaseModel):
    friend_uid: str
    

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(NoCacheMiddleware)

redis = Redis(decode_responses=True)
DB_PATH = "users.db"

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

chat_ws_registry: dict[str, WebSocket] = {}
set_ws_registry(chat_ws_registry)

def get_uid_from_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다.")

# @app.post("/api/force_add_friend")
# async def force_add_friend(req: FriendAddRequest, authorization: str = Header(...)):
#     if not authorization.startswith("Bearer "):
#         raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")

#     token = authorization.replace("Bearer ", "")
#     my_uid = get_uid_from_token(token)

#     friend_username = req.friend_username

#     cursor = conn.cursor()
#     cursor.execute("SELECT uid FROM users WHERE username = ?", (friend_username,))
#     row = cursor.fetchone()
#     if not row:
#         raise HTTPException(status_code=404, detail="존재하지 않는 닉네임입니다.")

#     friend_uid = row[0]

#     if my_uid == friend_uid:
#         raise HTTPException(status_code=400, detail="자기 자신은 친구로 추가할 수 없습니다.")

#     uid1, uid2 = sorted([my_uid, friend_uid])

#     cursor.execute("SELECT 1 FROM friends WHERE uid1 = ? AND uid2 = ?", (uid1, uid2))
#     if cursor.fetchone():
#         raise HTTPException(status_code=400, detail="이미 친구입니다.")

#     cursor.execute("INSERT INTO friends (uid1, uid2) VALUES (?, ?)", (uid1, uid2))
#     conn.commit()

#     await redis.sadd(f"friends:{uid1}", uid2)
#     await redis.sadd(f"friends:{uid2}", uid1)

#     return {"message": "✅ 친구 추가 완료"}

@app.post("/api/send_friend_request")
async def send_friend_request(req: FriendRequestSend, authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")
    
    token = authorization.replace("Bearer ", "")
    from_uid = get_uid_from_token(token)
    
    # 유저 존재 여부 확인
    to_uid = get_uid_by_username(req.username)
    if not to_uid:
        raise HTTPException(status_code=404, detail="존재하지 않는 닉네임입니다.")
    if from_uid == to_uid:
        raise HTTPException(status_code=400, detail="자기 자신에게는 요청할 수 없습니다.")
    
    uid1, uid2 = sorted([from_uid, to_uid])
    created_at = datetime.utcnow().isoformat()

    # DB 내 중복 관계 확인 및 요청 저장
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM friends WHERE uid1 = ? AND uid2 = ?", (uid1, uid2))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="이미 친구입니다.")

        cursor.execute("SELECT 1 FROM friend_requests WHERE from_uid = ? AND to_uid = ?", (from_uid, to_uid))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="이미 요청을 보냈습니다.")

        cursor.execute("""
            INSERT INTO friend_requests (from_uid, to_uid, created_at)
            VALUES (?, ?, ?)
        """, (from_uid, to_uid, created_at))
        conn.commit()

    # 실시간 알림
    to_ws = chat_ws_registry.get(to_uid)
    print(f"[친구추가 요청 ws 검사]{to_ws}")
    if to_ws:
        cursor.execute("SELECT username FROM users WHERE uid = ?", (from_uid,))
        from_username = cursor.fetchone()[0]
        conn.close()
        try:
            await to_ws.send_json({
                "type": "friend_request",
                "uid": from_uid,
                "username": from_username
            })
        except:
            pass

    return {"message": "✅ 친구 요청 전송됨"}

@app.post("/api/respond_friend_request")
async def respond_friend_request(req: FriendRequestResponse, authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")
    
    token = authorization.replace("Bearer ", "")
    my_uid = get_uid_from_token(token)
    other_uid = req.from_uid
    accept = req.accept

    # 요청 존재 확인
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM friend_requests
        WHERE from_uid = ? AND to_uid = ?
    """, (other_uid, my_uid))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="해당 요청이 존재하지 않습니다.")

    # 요청 삭제 (accept 여부와 상관 없이 공통)
    cursor.execute("""
        DELETE FROM friend_requests
        WHERE from_uid = ? AND to_uid = ?
    """, (other_uid, my_uid))
    conn.commit()

    if accept:
        uid1, uid2 = sorted([my_uid, other_uid])
        # 이미 친구인지 체크
        cursor.execute("SELECT 1 FROM friends WHERE uid1 = ? AND uid2 = ?", (uid1, uid2))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO friends (uid1, uid2) VALUES (?, ?)", (uid1, uid2))
            conn.commit()

            # Redis에 친구 관계 반영
            await redis.sadd(f"friends:{uid1}", uid2)
            await redis.sadd(f"friends:{uid2}", uid1)

            # WebSocket 알림 (선택)
            ws = chat_ws_registry.get(other_uid)
            if ws:
                try:
                    await ws.send_json({
                        "type": "friend_accepted",
                        "uid": my_uid
                    })
                except:
                    pass
        conn.close()
        return {"message": "✅ 친구 요청 수락됨"}
    
    else:
        conn.close()
        return {"message": "❌ 친구 요청 거절됨"}
    
@app.get("/api/friend_requests")
def get_friend_requests(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")
    
    token = authorization.replace("Bearer ", "")
    my_uid = get_uid_from_token(token)

    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT from_uid FROM friend_requests
            WHERE to_uid = ?
        """, (my_uid,))
        rows = cursor.fetchall()

        if not rows:
            return []

        from_uids = [row[0] for row in rows]

        placeholders = ",".join("?" for _ in from_uids)
        query = f"SELECT uid, username FROM users WHERE uid IN ({placeholders})"
        cursor.execute(query, from_uids)
        
        return [
            {"uid": uid, "username": username}
            for uid, username in cursor.fetchall()
        ]


@app.get("/api/friends")
def get_friends(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")

    token = authorization.replace("Bearer ", "")
    uid = get_uid_from_token(token)
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT uid1, uid2 FROM friends
        WHERE uid1 = ? OR uid2 = ?
    """, (uid, uid))

    rows = cursor.fetchall()

    friend_uids = []
    for uid1, uid2 in rows:
        friend_uid = uid2 if uid1 == uid else uid1
        friend_uids.append(friend_uid)

    if not friend_uids:
        conn.close()
        return []

    placeholders = ",".join("?" for _ in friend_uids)
    query = f"SELECT uid, username FROM users WHERE uid IN ({placeholders})"
    cursor.execute(query, friend_uids)
    users = cursor.fetchall()

    friends = []
    for friend_uid, username in users:
        room_id = generate_room_id(uid, friend_uid)

        cursor.execute("""
            SELECT 1 FROM chat_logs
            WHERE room_id = ? AND sender_uid = ? AND read = 0
            LIMIT 1
        """, (room_id, friend_uid))

        has_unread = cursor.fetchone() is not None

        friends.append({
            "uid": friend_uid,
            "username": username,
            "online": friend_uid in chat_ws_registry,
            "has_unread": has_unread   # ✅ 이 부분 추가
        })
    
    conn.close()

    return friends

@app.websocket("/chat_ws")
async def chat_ws(websocket: WebSocket, token: str = Query(...)):
    uid = None
    try:
        await websocket.accept()
        uid = get_uid_from_token(token)
        chat_ws_registry[uid] = websocket
        print(f"✅ Chat WebSocket 연결됨: {uid}")

        await friend_online(uid)

        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            if data.get("type") == "friend_chat":
                await handle_friend_chat(uid, data)

    except WebSocketDisconnect:
        print(f"❌ Chat WebSocket 끊김: {uid}")
    except Exception as e:
        print(f"[Chat WebSocket Error] {e}")
    finally:
        if uid:
            chat_ws_registry.pop(uid, None)
            await friend_offline(uid)

def generate_room_id(uid1: str, uid2: str) -> str:
    return ":".join(sorted([uid1, uid2]))

async def handle_friend_chat(sender_uid: str, data: dict):
    receiver_uid = data.get("to")
    message = data.get("text")
    timestamp = datetime.utcnow().isoformat()
    room_id = generate_room_id(sender_uid, receiver_uid)
    read = 0  # 무조건 처음엔 안 읽음

    # WebSocket 연결 여부와 상관없이 무조건 read=0으로 저장
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO chat_logs (room_id, sender_uid, message, timestamp, read)
        VALUES (?, ?, ?, ?, ?)
    """, (room_id, sender_uid, message, timestamp, read))
    conn.commit()
    conn.close()

    payload = {
        "type": "friend_chat",
        "from": sender_uid,
        "text": message,
        "timestamp": timestamp
    }

    # 수신자에게 push
    receiver_ws = chat_ws_registry.get(receiver_uid)
    if receiver_ws:
        await receiver_ws.send_json(payload)

    # 자기 자신에게도 push
    sender_ws = chat_ws_registry.get(sender_uid)
    if sender_ws:
        await sender_ws.send_json(payload)

@app.get("/api/chat_logs")
def get_chat_logs(friend_uid: str, limit: int = 20, before: str = None, authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token")
    token = authorization.replace("Bearer ", "")
    my_uid = get_uid_from_token(token)

    room_id = generate_room_id(my_uid, friend_uid)

    query = """
        SELECT sender_uid, message, timestamp
        FROM chat_logs
        WHERE room_id = ?
    """
    params = [room_id]

    if before:
        query += " AND timestamp < ?"
        params.append(before)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    messages = []
    for sender_uid, message, timestamp in rows:
        messages.append({
            "from": sender_uid,
            "text": message,
            "timestamp": timestamp
        })

    return {"messages": list(reversed(messages))}  # 오래된 → 최신 순

@app.post("/api/mark_read")
async def mark_read(req: MarkReadRequest, authorization: str = Header(...)):
    my_uid = get_uid_from_token(authorization.replace("Bearer ", ""))
    friend_uid = req.friend_uid
    room_id = generate_room_id(my_uid, friend_uid)

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE chat_logs
        SET read = 1
        WHERE room_id = ?
          AND sender_uid = ?
          AND read = 0
    """, (room_id, friend_uid))
    conn.commit()
    conn.close()

    return {"message": "✅ 읽음 처리 완료"}

@app.on_event("startup")
async def startup_event():
    await preload_friends_to_redis()
    asyncio.create_task(subscribe_presence())

async def preload_friends_to_redis():
    print("🔄 친구 목록 Redis로 preload 시작...")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT uid1, uid2 FROM friends")
    rows = cursor.fetchall()
    conn.close()

    for uid1, uid2 in rows:
        await redis.sadd(f"friends:{uid1}", uid2)
        await redis.sadd(f"friends:{uid2}", uid1)

    print(f"✅ 친구 {len(rows)}건 preload 완료")

@app.post("/api/party/invite")
async def game_invite(req: InviteRequest, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    inviter_uid = get_uid_from_token(token)
    invitee_uid = get_uid_by_username(req.username)
    leader = await get_party_leader(inviter_uid)

    invitee_ws = chat_ws_registry.get(invitee_uid)
    if invitee_ws:
        await invitee_ws.send_json({
            "type": "party_invite",
            "from_uid": inviter_uid,
            "from_username": get_username_by_uid(inviter_uid),
            "leader_uid": leader
        })

    return {"message": "초대 전송됨"}
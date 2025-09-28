# app/services/presence_manager.py

import json
from redis.asyncio import Redis

# Redis 연결
redis = Redis(decode_responses=True)

# WebSocket 레지스트리 (uid -> WebSocket 객체)
chat_ws_registry = None

def set_ws_registry(registry):
    global chat_ws_registry
    chat_ws_registry = registry

# ✅ 친구들에게만 presence 알림 보내는 함수
async def friend_online(uid: str):
    print(f"[DEBUG] friend_online 호출됨: {uid}")
    await redis.publish("presence_updates", json.dumps({
        "type": "friend_online",
        "uid": uid
    }))

async def friend_offline(uid: str):
    await redis.publish("presence_updates", json.dumps({
        "type": "friend_offline",
        "uid": uid
    }))

# ✅ presence_updates 채널 구독 및 처리
async def subscribe_presence():
    pubsub = redis.pubsub()
    await pubsub.subscribe("presence_updates")
    print("✅ Redis presence_updates 구독 시작")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue

        data = json.loads(message["data"])
        print(f"[Presence] 수신: {data}")

        sender_uid = data.get("uid")
        if not sender_uid:
            continue

        try:
            # ✅ sender_uid의 친구 목록을 Redis에서 가져온다
            friend_uids = await redis.smembers(f"friends:{sender_uid}")
            if not friend_uids:
                print(f"[Presence] {sender_uid} 친구 없음")
                continue

            dead_uids = []

            for friend_uid in friend_uids:
                ws = chat_ws_registry.get(friend_uid)
                if ws:
                    try:
                        await ws.send_text(json.dumps(data))
                        print(f"[Presence] {friend_uid}에게 알림 보냄")
                    except Exception as e:
                        print(f"❌ WebSocket send 실패 ({friend_uid}): {e}")
                        dead_uids.append(friend_uid)

            for uid in dead_uids:
                chat_ws_registry.pop(uid, None)
                print(f"🗑️ 죽은 WebSocket 제거됨: {uid}")

        except Exception as e:
            print(f"[Presence Error] {e}")

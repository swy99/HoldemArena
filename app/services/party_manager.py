# app/services/party_manager.py

import asyncio
from redis.asyncio import Redis
from app.services.messaging import send_ws
from app.services.matchmaker import ws_registry
from app.services.user_db import get_usernames_by_uids

redis = Redis(decode_responses=True)

# ✅ 파티 상태 브로드캐스트
async def broadcast_party_status(uid: str):
    from app.services.party_manager import get_party_members, get_party_status
    leader = await get_party_leader(uid)
    if not leader:
        return
    members = await get_party_members(uid)
    status = await get_party_status(uid)
    for m in members:
        ws = ws_registry.get(m)
        if ws:
            await send_ws(ws, {
                "type": "party_status",
                **status
            })
            
async def broadcast_party_queue_status(leader_uid: str, is_queueing: bool):
    members = await get_party_members(leader_uid)
    message = {
        "type": "party_queue_status",
        "is_queueing": is_queueing,
    }
    for m in members:
        ws = ws_registry.get(m)
        if ws:
            await send_ws(ws, message)

# ✅ 1인 파티 생성 (없을 때만)
async def create_party_if_absent(uid: str):
    leader = await redis.get(f"party:leader:{uid}")
    if leader:
        return  # 이미 파티 있음
    await redis.sadd(f"party:members:{uid}", uid)
    await redis.set(f"party:leader:{uid}", uid)
    await broadcast_party_status(uid)

# ✅ 초대 수락 시 리더 파티에 합류
async def accept_invite(uid: str, leader_uid: str):
    await leave_party(uid)  # 기존 파티 제거 (단일 파티만 허용)
    await redis.sadd(f"party:members:{leader_uid}", uid)
    await redis.set(f"party:leader:{uid}", leader_uid)
    await broadcast_party_status(leader_uid)

# ✅ 현재 속한 파티 멤버 목록
async def get_party_members(uid: str) -> list[str]:
    leader = await redis.get(f"party:leader:{uid}")
    if not leader:
        return []
    members = await redis.smembers(f"party:members:{leader}")
    return list(members)

# ✅ 현재 속한 파티의 리더 UID
async def get_party_leader(uid: str) -> str:
    return await redis.get(f"party:leader:{uid}")

# ✅ 내가 리더인지 확인
async def is_party_leader(uid: str) -> bool:
    leader = await get_party_leader(uid)
    return leader == uid

# ✅ 파티 탈퇴 (리더가 나가면 해체)
async def leave_party(uid: str):
    leader = await redis.get(f"party:leader:{uid}")
    if not leader:
        return
    await redis.srem(f"party:members:{leader}", uid)
    await redis.delete(f"party:leader:{uid}")

    members = await redis.smembers(f"party:members:{leader}")
    if leader == uid or not members:
        # 리더가 나갔거나 멤버 없음 → 전체 해체
        for m in members:
            await redis.delete(f"party:leader:{m}")
        await redis.delete(f"party:members:{leader}")
        await redis.delete(f"party:in_queue:{leader}")
    else:
        await broadcast_party_status(leader)

# ✅ 멤버 추방 (리더만 가능)
async def kick_member(leader_uid: str, target_uid: str):
    if not await is_party_leader(leader_uid):
        raise PermissionError("파티장만 추방할 수 있습니다")
    await redis.srem(f"party:members:{leader_uid}", target_uid)
    await redis.delete(f"party:leader:{target_uid}")
    await broadcast_party_status(leader_uid)

# ✅ 파티장 위임
async def promote_to_leader(current_leader: str, new_leader: str):
    if not await is_party_leader(current_leader):
        raise PermissionError("현재 유저가 파티장이 아닙니다")
    members = await redis.smembers(f"party:members:{current_leader}")
    if new_leader not in members:
        raise ValueError("새 리더는 파티원이어야 합니다")

    pipe = redis.pipeline()
    for uid in members:
        pipe.set(f"party:leader:{uid}", new_leader)
    pipe.rename(f"party:members:{current_leader}", f"party:members:{new_leader}")
    await pipe.execute()

    await broadcast_party_status(new_leader)

# ✅ 파티 상태 조회
async def get_party_status(uid: str) -> dict:
    leader = await get_party_leader(uid)
    members = await redis.smembers(f"party:members:{leader}") if leader else []
    username_map = get_usernames_by_uids(list(members))
    return {
        "leader_uid": leader,
        "members": [{"uid": u, "username": username_map.get(u, "")} for u in members],
    }

# ✅ 큐 등록 여부 확인
async def is_party_in_queue(uid: str) -> bool:
    leader = await get_party_leader(uid)
    if not leader:
        return False
    return await redis.exists(f"party:in_queue:{leader}") == 1

# ✅ 큐 등록 상태 설정
async def set_party_in_queue(leader_uid: str, status: bool):
    if status:
        await redis.set(f"party:in_queue:{leader_uid}", "1")
    else:
        await redis.delete(f"party:in_queue:{leader_uid}")

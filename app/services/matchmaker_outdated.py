# app/services/matchmaker.py

import uuid
import asyncio
from typing import List
from app.services.messaging import send_ws
from app.services.user_db import get_username_by_uid
import json
from redis import Redis

redis = Redis()

ws_registry: dict[str, any] = {}
pending_parties: list[list[str]] = []  # 큐 등록된 파티 목록
active_matches: dict[str, dict] = {}   # 매치 성사된 그룹
accept_status: dict[str, bool] = {}

MATCH_SIZE = 3
ACCEPT_TIMEOUT = 10  # 초

# ✅ 파티 등록
async def register_party(party: List[str]):
    if any(uid in member for uid in party for member in sum(pending_parties, [])):
        return  # 중복 방지
    pending_parties.append(party)
    print(f"[Matchmaker] 파티 등록됨: {party} (총 {len(pending_parties)} 파티)")
    await try_match()

# ✅ 파티 제거
def leave_queue(uid: str):
    for party in pending_parties:
        if uid in party:
            pending_parties.remove(party)
            print(f"[Matchmaker] UID 큐 이탈로 파티 제거됨: {party}")
            return
    # 매치 도중 이탈인 경우
    for gid, group in list(active_matches.items()):
        if uid in group:
            del active_matches[gid]
            for u in group:
                accept_status.pop(u, None)
            print(f"[Matchmaker] 활성 매치 중 이탈로 그룹 제거됨: {group}")
            return

# ✅ 매치 시도
async def try_match():
    total = 0
    selected = []

    for party in pending_parties:
        if total + len(party) <= MATCH_SIZE:
            selected.append(party)
            total += len(party)
        if total == MATCH_SIZE:
            break

    if total < MATCH_SIZE:
        return

    for party in selected:
        pending_parties.remove(party)

    flat = [uid for party in selected for uid in party]
    group_id = str(uuid.uuid4())
    active_matches[group_id] = {
        "party_groups": selected,
        "flat": flat,
        "accepted": set()
    }

    print(f"[Matchmaker] 매치 그룹 생성됨: {flat}")

    for uid in flat:
        ws = ws_registry.get(uid)
        if ws:
            await send_ws(ws, {
                "type": "match_ready",
                "group_id": group_id
            })

    asyncio.create_task(start_accept_timer(group_id))


# ✅ 매치 수락 처리
async def accept_match(game_type: str, uid: str):
    group_id = next((gid for gid, g in active_matches.items() if uid in g["flat"]), None)
    if not group_id:
        print(f"[Matchmaker] 수락 대상 아님: {uid}")
        return

    match = active_matches[group_id]
    match["accepted"].add(uid)
    print(f"[Matchmaker] UID 수락: {uid}")

    if set(match["accepted"]) == set(match["flat"]):
        print(f"[Matchmaker] 전체 수락 완료 → 매치 확정 (gid={group_id})")

        del active_matches[group_id]

        for i, uid in enumerate(match["flat"]):
            ws = ws_registry.get(uid)
            if ws:
                player_id = get_username_by_uid(uid)
                await send_ws(ws, {
                    "type": "match_success",
                    "game_id": group_id,
                    "player_id": player_id,
                    "uid": uid
                })

        player_ids = [get_username_by_uid(uid) for uid in match["flat"]]
        redis.publish("start_game", json.dumps({
            "game_id": group_id,
            "game_type": game_type,
            "uids": match["flat"],
            "player_ids": player_ids
        }))


# ✅ 수락 타이머
async def start_accept_timer(group_id: str):
    await asyncio.sleep(ACCEPT_TIMEOUT)

    match = active_matches.get(group_id)
    if not match:
        return

    accepted = match["accepted"]
    not_accepted = set(match["flat"]) - accepted

    print(f"[Matchmaker] 수락 마감 (gid={group_id})")
    print(f"✅ 수락한 유저: {list(accepted)}")
    print(f"❌ 수락 안한 유저: {list(not_accepted)}")

    # 매치 취소 및 상태 정리
    del active_matches[group_id]

    for uid in match["flat"]:
        print(f"[Matchmaker] {uid} 큐에서 제거됨 (수락 실패)")
        # 큐 재등록 없음 — 전체 취소


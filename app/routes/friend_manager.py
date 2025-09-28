# app/routes/friend_manager.py

from fastapi import APIRouter, Header, HTTPException
import sqlite3
from jose import jwt
import os

router = APIRouter()

# JWT 설정
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# DB 연결
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

# JWT 검증
def get_uid_from_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다.")

# 친구 목록 조회
@router.get("/api/friends")
def get_friends(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")
    
    token = authorization.replace("Bearer ", "")
    uid = get_uid_from_token(token)

    # 친구 찾기 (uid1 < uid2 저장 기준)
    cursor.execute("""
        SELECT uid1, uid2 FROM friends
        WHERE uid1 = ? OR uid2 = ?
    """, (uid, uid))

    rows = cursor.fetchall()

    friend_uids = []
    for uid1, uid2 in rows:
        friend_uid = uid2 if uid == uid1 else uid1
        friend_uids.append(friend_uid)

    if not friend_uids:
        return []

    placeholders = ",".join("?" for _ in friend_uids)
    query = f"SELECT uid, username FROM users WHERE uid IN ({placeholders})"
    cursor.execute(query, friend_uids)

    friends = [{"uid": row[0], "username": row[1]} for row in cursor.fetchall()]
    return friends

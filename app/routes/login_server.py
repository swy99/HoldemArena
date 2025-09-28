# app/routes/login_server.py

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Query, Header, HTTPException
from fastapi import WebSocket, WebSocketDisconnect
from fastapi import status
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from jose import JWTError, jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
import httpx, jwt, sqlite3
import uuid
import re
import os
import asyncio
import requests
from random import choice
from app.services.messaging import send_ws
from app.network.nocache import NoCacheMiddleware
from dotenv import load_dotenv
import redis
load_dotenv()

from app.services.user_db import (
    get_uid_by_username, 
    get_username_by_uid, 
    get_uid_by_provider,
    create_user_with_google_account,
    soft_delete_user,
    delete_user_relationships,
    get_game_history_for_uid
)

from app.services.party_manager import (
    get_party_members,
    is_party_leader,
    leave_party,
    get_party_leader,
    get_party_status,
    create_party_if_absent,
    accept_invite,
    broadcast_party_status,
    broadcast_party_queue_status,
    promote_to_leader,
    kick_member
)
from app.services.matchmaker import (
    register_party,
    leave_queue,
    ws_registry,
    accept_match
)

from app.protocol.message_models import (
    LoginRequest, 
    GoogleRegisterRequest, 
    GoogleLoginRequest, 
    AcceptInviteRequest, 
    KickRequest, 
    PromoteRequest
)


# ✅ 정적 파일을 /static 경로에 마운트
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # app/
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI()
app.add_middleware(NoCacheMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# ✅ 루트 요청 시 index.html 반환
@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# ✅ CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT 설정
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
EXPIRE_MINUTES = int(os.getenv("EXPIRE_MINUTES", "60"))
TEMP_TOKEN_EXP_MINUTES = int(os.getenv("TEMP_TOKEN_EXP_MINUTES", "5"))

# 구글 공개키를 가져와 JWT를 검증할 때 사용
GOOGLE_ISSUER = "https://accounts.google.com"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
google_redirect_uri = "https://holdemarena.win/api/google_login/callback"
google_delete_redirect_uri = "https://holdemarena.win/api/google_login_delete/callback"

# bcrypt 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# DB 연결
DB_PATH = "users.db"

# 유틸 함수
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def validate_id(id: str):
    if not re.fullmatch(r"^[a-z0-9_-]{3,20}$", id):
        raise HTTPException(status_code=400, detail="ID는 소문자 영문/숫자/_/-만 사용 가능하며, 3~20자여야 합니다.")

def validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 최소 8자 이상이어야 합니다.")

def validate_username(username: str):
    if not (2 <= len(username) <= 20):
        raise HTTPException(status_code=400, detail="닉네임은 2~20자 사이여야 합니다.")

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code in [404, 500]:
        return HTMLResponse(
            content=render_error_page(exc.status_code, exc.detail, request),
            status_code=exc.status_code
        )
    return await http_exception_handler(request, exc)

def render_error_page(status_code: int, detail: str, request: Request) -> str:
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hold'em Arena - Error</title>
    <script src="https://cdn.tailwindcss.com/3.4.16"></script>
    <script>tailwind.config={{theme:{{extend:{{colors:{{primary:'#082616',secondary:'#C8A327'}},borderRadius:{{'none':'0px','sm':'4px',DEFAULT:'8px','md':'12px','lg':'16px','xl':'20px','2xl':'24px','3xl':'32px','full':'9999px','button':'8px'}}}}}}}}</script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Pacifico&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&family=Montserrat+Mono:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/remixicon/4.6.0/remixicon.min.css">
    <style>
        :where([class^="ri-"])::before {{ content: "\f3c2"; }}
        body {{
            font-family: 'Montserrat', sans-serif;
            background-color: #082616;
            color: #FFF8E8;
            min-height: 100vh;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(1); }}
            50% {{ transform: scale(1.05); }}
            100% {{ transform: scale(1); }}
        }}
        .animate-pulse-slow {{
            animation: pulse 3s ease-in-out infinite;
        }}
    </style>
</head>
<body class="bg-primary">
<div class="min-h-screen w-full max-w-[375px] mx-auto flex flex-col items-center justify-center px-6 py-8">
  <div class="w-full flex flex-col items-center justify-center max-w-[320px]">
    <div class="w-16 h-16 rounded-full bg-secondary/20 flex items-center justify-center mb-6 animate-pulse-slow">
      <i class="ri-error-warning-fill ri-2x text-secondary"></i>
    </div>
    <h1 class="text-2xl font-medium text-[#FFF8E8] text-center mb-3">Something went wrong</h1>
    <div class="font-['Montserrat_Mono'] text-sm text-secondary opacity-80 mb-4 text-center">
      Error Code: {status_code} - {detail.upper().replace(" ", "_")}
    </div>
    <p class="text-sm text-[#FFF8E8]/80 text-center mb-8">
      Please try again later or contact support if the issue persists.
    </p>
    <div class="w-full mb-8">
      <button id="showDetails" class="w-full flex items-center justify-between text-xs text-[#FFF8E8]/60 py-2 border-t border-b border-[#FFF8E8]/10 cursor-pointer">
        <span>Technical Details</span>
        <i class="ri-arrow-down-s-line ri-lg"></i>
      </button>
      <div id="errorDetails" class="hidden mt-3 p-3 bg-[#FFF8E8]/5 rounded text-xs text-[#FFF8E8]/70 font-['Montserrat_Mono']">
        <p>Timestamp: {datetime.utcnow().isoformat()} UTC</p>
        <p>Request URL: {request.url}</p>
        <p>Client Host: {request.client.host}</p>
        <p>Detail: {detail}</p>
      </div>
    </div>
    <div class="w-full flex flex-col gap-3">
      <button class="w-full bg-transparent border border-[#FFF8E8]/20 text-[#FFF8E8] py-3.5 px-4 !rounded-button font-medium hover:bg-[#FFF8E8]/10 active:scale-[0.98] transition-all duration-200 cursor-pointer">
        Go Back
      </button>
    </div>
  </div>
</div>
<script>
document.addEventListener('DOMContentLoaded', function() {{
  const showDetailsButton = document.getElementById('showDetails');
  const errorDetails = document.getElementById('errorDetails');
  let isDetailsShown = false;
  showDetailsButton.addEventListener('click', function() {{
    isDetailsShown = !isDetailsShown;
    if (isDetailsShown) {{
      errorDetails.classList.remove('hidden');
      showDetailsButton.querySelector('i').classList.remove('ri-arrow-down-s-line');
      showDetailsButton.querySelector('i').classList.add('ri-arrow-up-s-line');
    }} else {{
      errorDetails.classList.add('hidden');
      showDetailsButton.querySelector('i').classList.remove('ri-arrow-up-s-line');
      showDetailsButton.querySelector('i').classList.add('ri-arrow-down-s-line');
    }}
  }});
  document.querySelector('button.bg-transparent').addEventListener('click', function() {{
    window.history.back();
  }});
}});
</script>
</body>
</html>
"""

# ✅ /api/register
@app.post("/api/register")
def register(id: str = Query(...), password: str = Query(...), username: str = Query(...)):
    id = id.lower()
    validate_id(id)
    validate_password(password)
    validate_username(username)

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE id = ? OR username = ?", (id, username))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="이미 사용 중인 ID 또는 닉네임입니다.")

    uid = str(uuid.uuid4())
    pw_hash = hash_password(password)
    created_at = datetime.utcnow().isoformat()

    cursor.execute("""
    INSERT INTO users (uid, id, pw_hash, username, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (uid, id, pw_hash, username, created_at))
    conn.commit()
    conn.close()

    return {"message": "회원가입 성공"}

# ✅ /api/login
@app.post("/api/login")
def login(req: LoginRequest):
    id = req.id.lower()
    password = req.password

    validate_id(id)
    validate_password(password)

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT pw_hash FROM users WHERE id = ?", (id,))
    row = cursor.fetchone()
    if not row or not verify_password(password, row[0]):
        raise HTTPException(status_code=401, detail="로그인 실패")

    cursor.execute("SELECT uid FROM users WHERE id = ?", (id,))
    row = cursor.fetchone()
    uid = row[0]
    conn.close()

    return {"token": issue_jwt(uid)}

@app.post("/api/google_register")
def google_register(req: GoogleRegisterRequest):
    # 1. temp_token 검증
    try:
        payload = jwt.decode(req.temp_token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload["sub"]
        email = payload["email"]
        picture = payload["picture"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"temp_token 검증 실패: {str(e)}")

    # 2. 닉네임 검증 및 중복 체크
    username = req.username.strip()
    validate_username(username)
    if get_uid_by_username(username) is not None:
        raise HTTPException(status_code=400, detail="이미 사용 중인 닉네임입니다.")

    # 3. 유저 생성
    uid = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()
    create_user_with_google_account(uid, username, sub, email, picture, created_at)

    # 4. JWT 발급
    return {
        "token": issue_jwt(uid),
        "username": username
    }

@app.get("/api/google_login")
def google_login():
    return RedirectResponse(
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={google_redirect_uri}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
    )

@app.get("/api/google_login_delete")
def google_delete_login():
    return RedirectResponse(
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={google_delete_redirect_uri}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
    )
    
@app.get("/api/google_login/callback")
async def google_callback(code: str):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": google_redirect_uri,
                "grant_type": "authorization_code"
            }
        )
    res.raise_for_status()
    
    id_token = res.json()["id_token"]
    payload = jwt.decode(id_token, options={"verify_signature": False})
    provider_id = payload["sub"]
    uid = get_uid_by_provider(provider="google", provider_id=provider_id)
    
    if uid:
        token = issue_jwt(uid)
        return HTMLResponse(f"""
            <script>
                localStorage.setItem("holdemarena_token", "{token}");
                location.replace("/static/lobby.html");
            </script>
            """)
    else:
        temp_token = issue_temp_jwt(sub=provider_id, email=payload["email"], picture=payload["picture"])
        return HTMLResponse(f"""
            <script>
                localStorage.setItem("holdemarena_temp_token", "{temp_token}");
                location.href = "/static/new.html?provider=google";
            </script>
            """)
    
@app.get("/api/google_login_delete/callback")
async def google_delete_callback(code: str):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": google_delete_redirect_uri,
                "grant_type": "authorization_code"
            }
        )
    res.raise_for_status()
    
    id_token = res.json()["id_token"]
    payload = jwt.decode(id_token, options={"verify_signature": False})
    provider_id = payload["sub"]
    uid = get_uid_by_provider(provider="google", provider_id=provider_id)
    
    if uid:
        token = issue_jwt(uid)
        return HTMLResponse(f"""
            <script>
                localStorage.setItem("holdemarena_token", "{token}");
                location.replace("/static/delete.html");
            </script>
            """)
    else:
        return HTMLResponse(f"""
            Account not found
            """)

@app.post("/api/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ").strip()
    uid = get_uid_from_token(token)

    # ✅ DB 처리
    delete_user_relationships(uid)
    soft_delete_user(uid)

    # ✅ Redis 상태 정리
    r = redis.Redis(decode_responses=True)
    r_bin = redis.Redis(decode_responses=False)

    r.delete(f"party:leader:{uid}")
    r.delete(f"party:members:{uid}")
    r.delete(f"party:in_queue:{uid}")

    game_id = r.get(f"user:{uid}:game")
    if game_id:
        r.delete(f"user:{uid}:game")
        r.hdel(f"uid_to_player_id:{game_id}", uid)
        r.hdel(f"player_id_to_uid:{game_id}", uid)

    return

# ✅ /api/me
@app.get("/api/me")
def get_me(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ").strip()
    uid = get_uid_from_token(token)
    username = get_username_by_uid(uid)  # deleted=0 자동 확인됨

    return {
        "uid": uid,
        "username": username
    }

# ✅ /api/check_id
@app.get("/api/check_id")
def check_id(id: str = Query(...)):
    id = id.lower()
    validate_id(id)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE id = ? AND deleted = 0", (id,))
    res = {"available": cursor.fetchone() is None}
    conn.close()
    return res

# ✅ /api/check_username
@app.get("/api/check_username")
def check_username(username: str = Query(...)):
    validate_username(username)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE username = ? AND deleted = 0", (username,))
    res = {"available": cursor.fetchone() is None}
    conn.close()
    return res



# WebSocket 연결 저장소

# JWT
def issue_jwt(uid: str) -> str:
    # uid must be a valid uid
    expire = datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES)
    payload = {
        "sub": uid,
        "exp": expire,
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def issue_temp_jwt(**kwargs) -> str:
    temp_exp = datetime.utcnow() + timedelta(minutes=TEMP_TOKEN_EXP_MINUTES)
    payload = {
        "exp": temp_exp,
        "iat": datetime.utcnow()
    }
    for key, value in kwargs.items():
        payload[key] = value
    temp_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return temp_token


def get_uid_from_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다.")


@app.websocket("/quick_play_party_queue_ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    uid = get_uid_from_token(token)
    await websocket.accept()
    ws_registry[uid] = websocket
    game_type = "quick_play"

    # ✅ 기존 파티에 속해 있는지 먼저 확인
    leader = await get_party_leader(uid)
    if not leader:
        # 파티가 아예 없다면 1인 파티 생성
        await create_party_if_absent(uid)

    # ✅ 현재 파티 상태 push
    status = await get_party_status(uid)
    await websocket.send_json({
        "type": "party_status",
        **status
    })

    try:
        while True:
            data = await websocket.receive_json()
            print(f"[recv:{uid}] {data}")

            if data.get("type") == "accept_match":
                print(f"[Matchmaker] {uid} accepted match")
                await accept_match(game_type, uid)

    except WebSocketDisconnect:
        print(f"❌ 연결 해제됨: {uid}")
        ws_registry.pop(uid, None)

        asyncio.create_task(delayed_disconnect_cleanup(uid))

        
async def delayed_disconnect_cleanup(uid: str):
    await asyncio.sleep(5)

    if uid in ws_registry:
        print(f"[WebSocket] {uid} 재연결됨 → 파티 유지")
        return

    print(f"[WebSocket] {uid} 5초 이내 재연결 실패 → 파티/큐 제거")
    await leave_party(uid)
    leave_queue(uid)
    remaining = await get_party_members(uid)  # uid 탈퇴 후 리더 기준으로 남은 멤버
    if remaining:
        leader = await get_party_leader(uid)
        if leader:
            status = await get_party_status(leader)
            for u in remaining:
                ws = ws_registry.get(u)
                if ws:
                    await send_ws(ws, {
                        "type": "party_status",
                        **status
                    })


@app.post("/api/join_quick_play_queue")
async def join_quick_play_queue(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")
    token = authorization.replace("Bearer ", "")
    uid = get_uid_from_token(token)

    if not await is_party_leader(uid):
        raise HTTPException(status_code=403, detail="파티장만 큐 등록이 가능합니다.")

    party = await get_party_members(uid)
    if not party:
        raise HTTPException(status_code=400, detail="파티가 존재하지 않습니다.")

    # WebSocket 연결 상태 확인
    disconnected = [u for u in party if u not in ws_registry]
    if disconnected:
        raise HTTPException(status_code=400, detail=f"다음 유저가 연결되어 있지 않음: {disconnected}")

    print(f"📥 큐 등록 요청: {party}")
    await register_party(party)
    leader_uid = await get_party_leader(uid)
    if leader_uid:
        await broadcast_party_queue_status(leader_uid, True)
        
    return {"message": "파티가 큐에 등록되었습니다."}


@app.post("/api/leave_queue")
async def leave_queue_api(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")
    token = authorization.replace("Bearer ", "")
    uid = get_uid_from_token(token)

    leave_queue(uid)
    
    # ✅ 파티 전체에 큐 취소 상태 전파
    leader_uid = await get_party_leader(uid)
    if leader_uid:
        await broadcast_party_queue_status(leader_uid, False)
    
    return {"message": "큐에서 제거되었습니다."}



# # party api
# @app.post("/api/party/invite")
# async def invite_to_party(req: InviteRequest, authorization: str = Header(...)):
#     token = authorization.replace("Bearer ", "")
#     inviter_uid = get_uid_from_token(token)

#     invitee_uid = get_uid_by_username(req.username)
#     if not invitee_uid:
#         raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

#     leader = await get_party_leader(inviter_uid)

#     # WebSocket 알림
#     invitee_ws = ws_registry.get(invitee_uid)
#     if invitee_ws:
#         await send_ws(invitee_ws, {
#             "type": "party_invite",
#             "from_uid": inviter_uid,
#             "from_username": get_username_by_uid(inviter_uid),
#             "leader_uid": leader
#         })

#     return {"message": "초대 전송됨"}

@app.post("/api/party/accept")
async def accept_invite_api(req: AcceptInviteRequest, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    uid = get_uid_from_token(token)

    await accept_invite(uid, req.leader_uid)
    await broadcast_party_status(req.leader_uid)  # ✅ 상태 전파
    return {"message": "파티에 참가했습니다"}

@app.post("/api/party/leave")
async def leave_party_api(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    uid = get_uid_from_token(token)

    leader_uid = await get_party_leader(uid)
    member_uids = await get_party_members(leader_uid)

    # ✅ 내가 방장인 경우 → 남은 멤버 중 1명을 리더로 승격
    if uid == leader_uid:
        remaining_members = [u for u in member_uids if u != uid]
        if remaining_members:
            new_leader = choice(remaining_members)
            await promote_to_leader(leader_uid, new_leader)
            await leave_party(uid)
            await broadcast_party_status(new_leader)
        else:
            # 나 혼자 남은 경우 → 파티 해체
            await leave_party(uid)
            # 굳이 broadcast 필요 없음
    else:
        # ✅ 일반 멤버는 그냥 나가기만
        await leave_party(uid)
        await broadcast_party_status(leader_uid)

    return {"message": "파티를 나갔습니다"}

@app.post("/api/party/promote")
async def promote_api(req: PromoteRequest, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    uid = get_uid_from_token(token)

    if not await is_party_leader(uid):
        raise HTTPException(status_code=403, detail="파티장만 위임 가능합니다")

    await promote_to_leader(uid, req.target_uid)

    await broadcast_party_status(uid)

    return {"message": "파티장 권한 위임 완료"}

@app.post("/api/party/kick")
async def kick_party_member(req: KickRequest, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    requester_uid = get_uid_from_token(token)
    target_uid = req.target_uid

    leader_uid = await get_party_leader(requester_uid)
    if not leader_uid or leader_uid != requester_uid:
        raise HTTPException(status_code=403, detail="방장만 추방할 수 있습니다")

    if target_uid == requester_uid:
        raise HTTPException(status_code=400, detail="자기 자신은 추방할 수 없습니다")

    # ✅ 추방
    await kick_member(leader_uid, target_uid)

    # ✅ 기존 파티에 상태 전파
    await broadcast_party_status(leader_uid)

    # ✅ 1인 파티 생성 (자기 자신을 리더로)
    await create_party_if_absent(target_uid)

    # ✅ 해당 유저에게 새 파티 상태 전송
    await broadcast_party_status(target_uid)

    return {"message": "추방 완료"}

@app.get("/api/game_history")
def game_history(authorization: str = Header(...), limit: int = 20):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")
    
    token = authorization.replace("Bearer ", "")
    uid = get_uid_from_token(token)

    return get_game_history_for_uid(uid, limit=limit)
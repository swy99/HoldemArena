# modules/main.py

import sys
import subprocess
import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path

# ✅ .env 파일 로드
load_dotenv()

# ✅ .env에서 포트 읽기
PORT = int(os.getenv("PORT", 9000))        # 기본값 9000
WS_PORT = int(os.getenv("WS_PORT", 8000))   # 기본값 8000
CHAT_PORT = int(os.getenv("CHAT_PORT", 7000))

# ✅ SSL 인증서 경로 (직접 추가)
SSL_CERTFILE = os.getenv("SSL_CERTFILE")
SSL_KEYFILE = os.getenv("SSL_KEYFILE")

class Tee:
    def __init__(self, logfile_path):
        self.terminal = sys.stdout
        self.log = open(logfile_path, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

def run_login_server():
    return subprocess.Popen([
        "uvicorn", "app.routes.login_server:app",
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "--ssl-keyfile", SSL_KEYFILE,
        "--ssl-certfile", SSL_CERTFILE,
    ])

def run_websocket_server():
    return subprocess.Popen([
        "uvicorn", "app.network.websocket_server:app",
        "--host", "0.0.0.0",
        "--port", str(WS_PORT),
        "--ssl-keyfile", SSL_KEYFILE,
        "--ssl-certfile", SSL_CERTFILE,
    ])
    
def run_chat_server():
    return subprocess.Popen([
        "uvicorn", "app.network.chat_server:app",
        "--host", "0.0.0.0",
        "--port", str(CHAT_PORT),
        "--ssl-keyfile", SSL_KEYFILE,
        "--ssl-certfile", SSL_CERTFILE,
    ])

async def run_all():
    print("🚀 모든 구성 요소를 실행합니다...")

    login_proc = run_login_server()
    ws_proc = run_websocket_server()
    chat_proc = run_chat_server()
    
    try:
        # 로그인, 게임, 채팅 서버는 별도 프로세스라서 이 쓰레드는 그냥 대기만
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("🛑 종료 요청됨. 모든 프로세스를 정리합니다.")
    finally:
        login_proc.terminate()
        ws_proc.terminate()
        chat_proc.terminate()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python main.py [login | ws | chat | all]")
        sys.exit(1)

    cmd = sys.argv[1]
    

    if cmd == "login":
        # 로그 디렉토리 생성 + 파일 이름에 타임스탬프 포함
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        Path("logs").mkdir(exist_ok=True)
        sys.stdout = Tee(f"logs/{cmd}_{now}.log")
        run_login_server().wait()
    elif cmd == "ws":
        # 로그 디렉토리 생성 + 파일 이름에 타임스탬프 포함
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        Path("logs").mkdir(exist_ok=True)
        sys.stdout = Tee(f"logs/{cmd}_{now}.log")
        run_websocket_server().wait()
    elif cmd == "chat":
        # 로그 디렉토리 생성 + 파일 이름에 타임스탬프 포함
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        Path("logs").mkdir(exist_ok=True)
        sys.stdout = Tee(f"logs/{cmd}_{now}.log")
        run_chat_server().wait()
    elif cmd == "all":
        # 로그 디렉토리 생성 + 파일 이름에 타임스탬프 포함
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        Path("logs").mkdir(exist_ok=True)
        sys.stdout = Tee(f"logs/{cmd}_{now}.log")
        asyncio.run(run_all())
    else:
        print(f"❌ 알 수 없는 명령: {cmd}")
        print("사용법: python main.py [login | ws | chat | all]")
        
        
print("🔎 SSL_CERTFILE =", repr(SSL_CERTFILE))
print("🔎 SSL_KEYFILE  =", repr(SSL_KEYFILE))
print("🔎 Exists:", os.path.exists(SSL_CERTFILE), os.path.exists(SSL_KEYFILE))

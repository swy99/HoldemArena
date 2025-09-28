from datetime import datetime
import os

# ANSI 색상 코드
LOOP_COLORS = {
    "game_registry_manager": "\033[96m",  # 청록색 (#00ffff)
    "game_step_handler": "\033[38;5;208m",  # 주황색 (#ff8000에 근접)
    "game_timeout_detector": "\033[93m",  # 노란색 (#ffff00)
}
RESET_COLOR = "\033[0m"

def make_logger(loop_type: str, index: int):
    """
    루프별로 사용할 logger 함수 생성

    Example:
        logger = make_logger("game_step_handler", 2)
        logger("받은 메시지:", msg)
    """
    prefix = f"[{loop_type}_{index}]"
    color = LOOP_COLORS.get(loop_type, "")

    def log(*args):
        now = datetime.now().strftime("%H:%M:%S")
        print(f"{color}[{now}] {prefix}", *args, RESET_COLOR)

    return log
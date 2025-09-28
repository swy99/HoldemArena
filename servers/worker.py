# servers/worker.py

import asyncio
from servers.game_registry_manager import game_registry_manager_loop
from servers.game_step_handler import game_step_handler_loop
from servers.game_timeout_detector import game_timeout_detector_loop

async def worker_main(i: int):
    await asyncio.gather(
        game_registry_manager_loop(i),
        game_step_handler_loop(i),
        game_timeout_detector_loop(i),
    )

# worker_main.py

import os
import sys
import time
from multiprocessing import Process
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path

from servers.worker import worker_main  # 실제 워커 메인 루프

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

def spawn_worker(index: int, log_dir: Path):
    log_file = log_dir / f"worker_{index}.txt"
    sys.stdout = Tee(log_file)
    sys.stderr = sys.stdout

    import asyncio
    asyncio.run(worker_main(index))

if __name__ == "__main__":
    load_dotenv()
    num_workers = int(os.getenv("NUM_WORKERS", 1))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = Path("servers/logs") / timestamp
    log_dir.mkdir(parents=True, exist_ok=True)

    processes = []
    for i in range(num_workers):
        p = Process(target=spawn_worker, args=(i, log_dir))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

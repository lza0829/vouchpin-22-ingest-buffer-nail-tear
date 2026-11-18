from __future__ import annotations
import os
from pathlib import Path

PROJECT_NAME = "Vouchpin"
API_PORT = 10800
DATA_DIR = Path(os.environ.get("DATA_DIR") or (Path(__file__).resolve().parents[2] / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "clipbond.db"

# 核销缓冲队列：写入先入 redeem_buffer，后台工作线程定期 flush 到事件/事实。
# 测试与确定性场景可用 BUFFER_AUTO_FLUSH=0 关掉自动冲刷。
BUFFER_AUTO_FLUSH = os.environ.get("BUFFER_AUTO_FLUSH", "1") not in {"0", "false", "False", ""}
BUFFER_FLUSH_INTERVAL_SEC = float(os.environ.get("BUFFER_FLUSH_INTERVAL_SEC", "5"))

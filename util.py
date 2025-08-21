from __future__ import annotations
import json, os, random, sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

DATA_PATH = Path("data")
POSTED_PATH = DATA_PATH / "posted_ids.json"
JST = ZoneInfo("Asia/Tokyo")

DATA_PATH.mkdir(exist_ok=True)
if not POSTED_PATH.exists():
    POSTED_PATH.write_text("[]", encoding="utf-8")

def now_jst() -> datetime:
    return datetime.now(tz=JST)

def is_allowed_hour() -> bool:
    allow = os.getenv("POST_HOURS_JST", "").strip()
    if not allow:
        return True  # 設定なしなら常に許可
    hours = {int(h) for h in allow.split(',') if h}
    return now_jst().hour in hours

def load_posted_ids() -> set[str]:
    try:
        return set(json.loads(POSTED_PATH.read_text(encoding="utf-8")))
    except Exception:
        return set()

def add_posted_id(x: str) -> None:
    ids = list(load_posted_ids())
    ids.append(x)
    POSTED_PATH.write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")

def choose_random(items):
    return random.choice(items) if items else None

def log(*a):
    print("[BOT]", *a, file=sys.stderr)

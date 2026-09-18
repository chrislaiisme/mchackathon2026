"""JSON file-backed user profile storage.

One file per user under DATA_DIR, keyed by the Google account's `sub`. No
database -- see CLAUDE.md "資料庫" for why: identity/preferences are the only
thing that needs to survive a restart, and a handful of small JSON files
covers that for a two-day hackathon.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.shared.schemas import UserProfile

# 存放每個使用者 JSON 檔的資料夾，路徑是相對這個檔案往上三層（backend/shared → backend → repo 根目錄）
# 再進 data/users。這個資料夾已經被 .gitignore 排除，不會進 git。
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "users"


def _path_for(sub: str) -> Path:
    # 每個使用者一個檔案，檔名就是 Google 帳號的 sub（主鍵）加上 .json。
    return DATA_DIR / f"{sub}.json"


def load_user(sub: str) -> UserProfile | None:
    # 檔案不存在就代表這個使用者還沒登入過，回傳 None，不當成錯誤處理。
    path = _path_for(sub)
    if not path.exists():
        return None
    return UserProfile.model_validate_json(path.read_text(encoding="utf-8"))


def save_user(profile: UserProfile) -> None:
    # 資料夾可能還不存在（第一次寫入），先確保建立好；每次都整份覆寫，
    # 不做局部更新，因為使用者資料量很小，整份寫入最單純。
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _path_for(profile.sub).write_text(profile.model_dump_json(indent=2), encoding="utf-8")


def get_or_create_user(
    sub: str, email: str, name: str | None, picture: str | None
) -> UserProfile:
    # 先看這個使用者是不是已經登入過（檔案已存在），有的話直接回傳既有資料，
    # 不要用這次 Google 回傳的 name/picture 去覆蓋——使用者可能改過自己的偏好資料，
    # 不該被 Google 那邊的最新資料悄悄蓋掉。
    existing = load_user(sub)
    if existing is not None:
        return existing

    # 第一次登入，建立一筆新的使用者資料，偏好欄位（age_range／style_preferences）
    # 先留空，等使用者自己去填偏好調查。
    profile = UserProfile(
        sub=sub,
        email=email,
        name=name,
        picture=picture,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    save_user(profile)
    return profile

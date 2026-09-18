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

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "users"


def _path_for(sub: str) -> Path:
    return DATA_DIR / f"{sub}.json"


def load_user(sub: str) -> UserProfile | None:
    path = _path_for(sub)
    if not path.exists():
        return None
    return UserProfile.model_validate_json(path.read_text(encoding="utf-8"))


def save_user(profile: UserProfile) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _path_for(profile.sub).write_text(profile.model_dump_json(indent=2), encoding="utf-8")


def get_or_create_user(
    sub: str, email: str, name: str | None, picture: str | None
) -> UserProfile:
    existing = load_user(sub)
    if existing is not None:
        return existing

    profile = UserProfile(
        sub=sub,
        email=email,
        name=name,
        picture=picture,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    save_user(profile)
    return profile

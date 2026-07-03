"""JSON-file state (alert dedupe) and discovery cache."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path("data/state.json")
CACHE_PATH = Path("data/discovery_cache.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Alert state ──────────────────────────────────────────────────────────────

def load_state(path: Path = STATE_PATH) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def state_exists(path: Path = STATE_PATH) -> bool:
    return path.exists()


# ── Discovery cache ──────────────────────────────────────────────────────────

def load_cache(path: Path = CACHE_PATH) -> dict | None:
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_cache(events: list[dict], path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": _now_iso(), "events": events}, indent=2))


def cache_age_hours(cache: dict) -> float:
    try:
        fetched = datetime.fromisoformat(cache["fetched_at"])
        return (datetime.now(timezone.utc) - fetched).total_seconds() / 3600.0
    except Exception:  # noqa: BLE001
        return float("inf")

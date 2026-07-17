"""Local JSON high-score persistence, confined to the game directory.

No network access, no shell commands, no dynamic code execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_GAME_DIR = Path(__file__).resolve().parent.parent
_HIGHSCORES_PATH = _GAME_DIR / "highscores.json"

_MAX_ENTRIES = 10


def _sanitize_entry(entry: dict) -> dict[str, Any]:
    """Return a JSON-safe copy of entry with expected fields coerced."""
    name = str(entry.get("name", "PLAYER"))[:16]
    try:
        score = int(entry.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    try:
        area = float(entry.get("area_percent", 0.0))
    except (TypeError, ValueError):
        area = 0.0
    try:
        level = int(entry.get("level", 1))
    except (TypeError, ValueError):
        level = 1
    return {
        "name": name,
        "score": score,
        "area_percent": area,
        "level": level,
    }


def load_highscores() -> list[dict]:
    """Load the list of high-score entries from disk.

    Returns an empty list if the file does not exist or is malformed.
    Never raises for missing/corrupt data; defensive against bad JSON.
    """
    if not _HIGHSCORES_PATH.exists():
        return []
    try:
        text = _HIGHSCORES_PATH.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    result: list[dict] = []
    for item in data:
        if isinstance(item, dict):
            result.append(_sanitize_entry(item))
    return result


def save_highscore(entry: dict) -> None:
    """Insert a new high-score entry, keep the list sorted and trimmed.

    Writes only inside the game directory (_HIGHSCORES_PATH is derived from
    this file's own location, never from external/user-provided paths).
    """
    entries = load_highscores()
    entries.append(_sanitize_entry(entry))
    entries.sort(key=lambda e: e["score"], reverse=True)
    entries = entries[:_MAX_ENTRIES]

    try:
        _HIGHSCORES_PATH.write_text(
            json.dumps(entries, indent=2), encoding="utf-8"
        )
    except OSError:
        # Best-effort persistence; silently ignore write failures
        # (e.g. read-only filesystem) rather than crashing the game.
        pass

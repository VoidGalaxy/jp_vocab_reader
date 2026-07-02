from __future__ import annotations

import json
from pathlib import Path
from typing import Any


JMDICT_SAMPLE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "dictionary" / "jmdict_sample.json"
)

_jmdict_index: dict[str, str] | None = None


def _clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_jmdict_index() -> dict[str, str]:
    try:
        entries = json.loads(JMDICT_SAMPLE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(entries, list):
        return {}

    index: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        glosses = [
            gloss.strip()
            for gloss in _as_list(entry.get("glosses"))
            if isinstance(gloss, str) and gloss.strip()
        ]
        if not glosses:
            continue

        gloss_text = "; ".join(glosses)
        keys = [
            _clean_text(value)
            for field in ("kanji", "kana")
            for value in _as_list(entry.get(field))
        ]
        for key in keys:
            if key:
                index.setdefault(key, gloss_text)

    return index


def get_jmdict_index() -> dict[str, str]:
    global _jmdict_index
    if _jmdict_index is None:
        _jmdict_index = _load_jmdict_index()
    return _jmdict_index


def lookup_jmdict_gloss(
    *,
    surface: str = "",
    base_form: str = "",
    normalized_form: str = "",
    reading: str = "",
) -> str:
    index = get_jmdict_index()
    for key in (surface, base_form, normalized_form, reading):
        gloss = index.get((key or "").strip())
        if gloss:
            return gloss
    return ""

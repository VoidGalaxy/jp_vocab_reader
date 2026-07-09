from __future__ import annotations

import re
import time
from typing import Any

from app.database import get_connection, row_to_dict

JLPT_LEVEL_ORDER = ["N5", "N4", "N3", "N2", "N1"]
_JLPT_LEVEL_RANK = {level: rank for rank, level in enumerate(JLPT_LEVEL_ORDER)}
# Matches both the documented "JLPT {level} 추천 어휘" naming (used by
# scripts/build_jlpt_deck_package.py) and the "{level}어휘모음" naming
# currently used by the decks actually registered in the shared_decks table.
_JLPT_DECK_TITLE_PATTERN = re.compile(
    r"^(?:JLPT\s*(N[1-5])\s*추천\s*어휘|(N[1-5])어휘모음)"
)
_CACHE_TTL_SECONDS = 300

_index_cache: tuple[dict[str, str], dict[str, str]] | None = None
_index_built_at = 0.0


def extract_jlpt_level_from_title(title: str) -> str | None:
    match = _JLPT_DECK_TITLE_PATTERN.match(title or "")
    if not match:
        return None
    return match.group(1) or match.group(2)


def _load_jlpt_level_index() -> tuple[dict[str, str], dict[str, str]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT shared_decks.title AS deck_title,
                   shared_deck_items.surface, shared_deck_items.base_form,
                   shared_deck_items.reading, shared_deck_items.normalized_form
            FROM shared_decks
            JOIN shared_deck_items
              ON shared_deck_items.shared_deck_id = shared_decks.id
            WHERE shared_decks.visibility = 'public'
              AND (shared_decks.title LIKE ? OR shared_decks.title LIKE ?)
            """,
            ("JLPT %", "N_어휘모음"),
        ).fetchall()

    leveled_items: list[dict[str, Any]] = []
    for row in rows:
        item = row_to_dict(row)
        level = extract_jlpt_level_from_title(item.get("deck_title", ""))
        if level:
            item["level"] = level
            leveled_items.append(item)

    # Easiest level first, so when the same word appears in multiple JLPT
    # decks the first (easiest) match wins via dict.setdefault below.
    leveled_items.sort(key=lambda item: _JLPT_LEVEL_RANK.get(item["level"], 99))

    word_index: dict[str, str] = {}
    reading_index: dict[str, str] = {}
    for item in leveled_items:
        level = item["level"]
        surface = (item.get("surface") or "").strip()
        base_form = (item.get("base_form") or "").strip()
        reading = (item.get("reading") or "").strip()
        normalized_form = (item.get("normalized_form") or "").strip()

        for key in (base_form, normalized_form, surface):
            if key:
                word_index.setdefault(key, level)
        if surface and reading:
            word_index.setdefault(f"{surface}|{reading}", level)
        if reading:
            reading_index.setdefault(reading, level)

    return word_index, reading_index


def get_jlpt_level_index() -> tuple[dict[str, str], dict[str, str]]:
    global _index_cache, _index_built_at
    now = time.monotonic()
    if _index_cache is None or (now - _index_built_at) > _CACHE_TTL_SECONDS:
        _index_cache = _load_jlpt_level_index()
        _index_built_at = now
    return _index_cache


def lookup_jlpt_level(
    *,
    surface: str = "",
    base_form: str = "",
    reading: str = "",
    normalized_form: str = "",
) -> str | None:
    word_index, reading_index = get_jlpt_level_index()
    surface = (surface or "").strip()
    base_form = (base_form or "").strip()
    reading = (reading or "").strip()
    normalized_form = (normalized_form or "").strip()

    for key in (base_form, normalized_form, surface):
        if key and key in word_index:
            return word_index[key]

    if surface and reading:
        combo_key = f"{surface}|{reading}"
        if combo_key in word_index:
            return word_index[combo_key]

    if reading and reading in reading_index:
        return reading_index[reading]

    return None


def attach_jlpt_levels(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for token in tokens:
        token["jlpt_level"] = lookup_jlpt_level(
            surface=token.get("surface", ""),
            base_form=token.get("base_form", ""),
            reading=token.get("reading", ""),
            normalized_form=token.get("normalized_form", ""),
        )
    return tokens

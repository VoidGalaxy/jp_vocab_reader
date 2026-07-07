from __future__ import annotations

import os
import re


DEFAULT_MAX_MEANING_CANDIDATES = 3
MAX_MEANING_CANDIDATES_ENV = "MEANING_KO_MAX_CANDIDATES"
DEFAULT_MAX_CANDIDATE_LENGTH = 12
MAX_PER_GLOSS_CANDIDATES = 2

_ALLOWED_EXTRA_CHARS = set(" ,()·-~")
_HANGUL_SYLLABLE_RE = re.compile(r"[가-힣]")
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")
# Archaic/obsolete Hangul jamo, Hangul Compatibility Jamo, and Middle Korean
# tone marks (dots) that show up in raw Kaikki/Wiktionary entries but are not
# usable as a modern learner-facing Korean meaning.
_ARCHAIC_HANGUL_RE = re.compile(
    r"[ᄀ-ᇿꥠ-꥿ힰ-퟿〮〯ㄱ-ㆎ]"
)


def get_max_meaning_candidates() -> int:
    raw = os.getenv(MAX_MEANING_CANDIDATES_ENV, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_MAX_MEANING_CANDIDATES


def is_valid_korean_candidate(
    text: str, *, max_length: int = DEFAULT_MAX_CANDIDATE_LENGTH
) -> bool:
    candidate = (text or "").strip()
    if not candidate or len(candidate) > max_length:
        return False
    if _LATIN_LETTER_RE.search(candidate):
        return False
    if _ARCHAIC_HANGUL_RE.search(candidate):
        return False
    if not _HANGUL_SYLLABLE_RE.search(candidate):
        return False
    for char in candidate:
        if _HANGUL_SYLLABLE_RE.match(char) or char in _ALLOWED_EXTRA_CHARS:
            continue
        return False
    return True


def rank_and_limit_candidates(
    candidates: list[str], *, max_candidates: int | None = None
) -> list[str]:
    limit = (
        max_candidates if max_candidates is not None else get_max_meaning_candidates()
    )
    ranked: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = " ".join((candidate or "").strip().split())
        if not cleaned or not is_valid_korean_candidate(cleaned):
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        ranked.append(cleaned)
        if len(ranked) >= limit:
            break
    return ranked


def build_meaning_ko(
    candidates: list[str], *, max_candidates: int | None = None
) -> str:
    return ", ".join(
        rank_and_limit_candidates(candidates, max_candidates=max_candidates)
    )

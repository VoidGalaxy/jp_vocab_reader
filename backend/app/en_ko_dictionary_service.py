from __future__ import annotations

import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any

from app.dictionary_file_manager import DICTIONARY_DIR, get_en_ko_dictionary_path
from app.meaning_ranker import (
    MAX_PER_GLOSS_CANDIDATES,
    build_meaning_ko,
    get_max_meaning_candidates,
    is_valid_korean_candidate,
)


EN_KO_FULL_PATH = get_en_ko_dictionary_path()
EN_KO_SAMPLE_PATH = DICTIONARY_DIR / "en_ko_sample.json"
MAX_TRANSLATIONS_PER_GLOSS = MAX_PER_GLOSS_CANDIDATES
ENTRY_LIST_KEYS = ("entries", "items", "translations")
GZIP_MAGIC = b"\x1f\x8b"

logger = logging.getLogger(__name__)

_en_ko_index: dict[str, list[str]] | None = None
_en_ko_status: dict[str, Any] = {
    "source": "not-loaded",
    "path": "",
    "entries": 0,
    "keys": 0,
    "loaded": False,
    "reason": None,
    "errors": [],
}


def normalize_english_key(value: str) -> str:
    text = " ".join((value or "").strip().lower().split())
    text = re.sub(r"\s*\([^)]*\)", "", text).strip()
    return text


def _candidate_keys(gloss: str) -> list[str]:
    normalized = normalize_english_key(gloss)
    candidates = [normalized]
    for separator in ("; ", ", ", " / "):
        if separator in normalized:
            candidates.append(normalized.split(separator, 1)[0].strip())
    if normalized.startswith("to "):
        candidates.append(normalized[3:].strip())
    return [candidate for candidate in candidates if candidate]


def _root_entries(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ENTRY_LIST_KEYS:
            entries = value.get(key)
            if isinstance(entries, list):
                return entries
    return None


def _clean_korean(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.strip().split())
    if not is_valid_korean_candidate(text):
        return ""
    return text


def _looks_like_gzip(path: Path) -> bool:
    try:
        with path.open("rb") as input_file:
            return input_file.read(2) == GZIP_MAGIC
    except OSError:
        return False


def _read_entries(path: Path) -> tuple[list[Any] | None, str]:
    if not path.exists():
        return None, "missing"
    if zipfile.is_zipfile(path):
        return (
            None,
            "appears to be a ZIP archive; check EN_KO_DICTIONARY_URL download/extraction",
        )
    if _looks_like_gzip(path):
        return (
            None,
            "appears to be a GZIP file; check EN_KO_DICTIONARY_URL download/extraction",
        )
    try:
        raw_data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"read error: {exc}"
    except UnicodeDecodeError as exc:
        return None, f"decode error: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"json parse error: line {exc.lineno} column {exc.colno}"

    entries = _root_entries(raw_data)
    if entries is None:
        return None, "unsupported root format"
    return entries, ""


def _normalize_entry(entry: Any) -> tuple[str, list[str]] | None:
    if not isinstance(entry, dict):
        return None
    english = normalize_english_key(
        str(entry.get("english") or entry.get("word") or entry.get("headword") or "")
    )
    if not english:
        return None

    raw_translations = entry.get("korean") or entry.get("translations") or []
    if isinstance(raw_translations, str):
        raw_translations = [raw_translations]
    if not isinstance(raw_translations, list):
        return None

    translations: list[str] = []
    seen: set[str] = set()
    for value in raw_translations:
        korean = ""
        if isinstance(value, str):
            korean = _clean_korean(value)
        elif isinstance(value, dict):
            korean = _clean_korean(value.get("word") or value.get("text") or value.get("translation"))
        if korean and korean not in seen:
            translations.append(korean)
            seen.add(korean)
    if not translations:
        return None
    return english, translations


def _build_index(entries: list[Any]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for entry in entries:
        normalized = _normalize_entry(entry)
        if not normalized:
            continue
        english, translations = normalized
        bucket = index.setdefault(english, [])
        for translation in translations:
            if translation not in bucket:
                bucket.append(translation)
    return index


def _load_index() -> dict[str, list[str]]:
    global _en_ko_status
    errors: list[str] = []
    invalid_full_seen = False
    for path in (EN_KO_FULL_PATH, EN_KO_SAMPLE_PATH):
        entries, error = _read_entries(path)
        if entries is None:
            errors.append(f"{path.name}: {error}")
            if path == EN_KO_FULL_PATH and error != "missing":
                invalid_full_seen = True
                logger.warning("English-Korean full dictionary skipped: %s", error)
            else:
                logger.info("English-Korean dictionary skipped: %s (%s)", path.name, error)
            continue
        index = _build_index(entries)
        if not index:
            errors.append(f"{path.name}: no valid entries")
            logger.info("English-Korean dictionary skipped: %s (no valid entries)", path.name)
            continue
        _en_ko_status = {
            "source": "full" if path == EN_KO_FULL_PATH else "sample",
            "path": str(path),
            "entries": len(entries),
            "keys": len(index),
            "loaded": True,
            "reason": None,
            "errors": errors,
        }
        logger.info(
            "English-Korean dictionary loaded: %s (%s entries, %s keys)",
            path.name,
            len(entries),
            len(index),
        )
        return index

    _en_ko_status = {
        "source": "invalid_full" if invalid_full_seen else "fallback",
        "path": "",
        "entries": 0,
        "keys": 0,
        "loaded": False,
        "reason": errors[0] if errors else None,
        "errors": errors,
    }
    return {}


def get_en_ko_index() -> dict[str, list[str]]:
    global _en_ko_index
    if _en_ko_index is None:
        _en_ko_index = _load_index()
    return _en_ko_index


def get_en_ko_status() -> dict[str, Any]:
    get_en_ko_index()
    return dict(_en_ko_status)


def _order_glosses(glosses: list[str], *, prefer_verb_glosses: bool) -> list[str]:
    if not prefer_verb_glosses:
        return glosses
    verb_shaped = [gloss for gloss in glosses if gloss.strip().lower().startswith("to ")]
    other = [gloss for gloss in glosses if not gloss.strip().lower().startswith("to ")]
    return [*verb_shaped, *other]


def _order_translations_for_gloss(translations: list[str], gloss: str) -> list[str]:
    if not gloss.strip().lower().startswith("to "):
        return translations
    verb_shaped = [word for word in translations if word.endswith("다")]
    other = [word for word in translations if not word.endswith("다")]
    return [*verb_shaped, *other]


def translate_glosses_to_korean(
    dictionary_gloss: str, *, prefer_verb_glosses: bool = False
) -> str:
    index = get_en_ko_index()
    max_total = get_max_meaning_candidates()
    meanings: list[str] = []
    seen: set[str] = set()
    glosses = _order_glosses(dictionary_gloss.split(";"), prefer_verb_glosses=prefer_verb_glosses)
    for gloss in glosses:
        if len(meanings) >= max_total:
            break
        translations: list[str] = []
        for key in _candidate_keys(gloss):
            translations = index.get(key, [])
            if translations:
                break
        translations = _order_translations_for_gloss(translations, gloss)
        for translation in translations[:MAX_TRANSLATIONS_PER_GLOSS]:
            if translation in seen:
                continue
            meanings.append(translation)
            seen.add(translation)
            if len(meanings) >= max_total:
                break
    return build_meaning_ko(meanings, max_candidates=max_total)

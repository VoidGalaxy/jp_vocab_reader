from __future__ import annotations

import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any

from app.dictionary_file_manager import DICTIONARY_DIR, get_en_ko_dictionary_path


EN_KO_FULL_PATH = get_en_ko_dictionary_path()
EN_KO_SAMPLE_PATH = DICTIONARY_DIR / "en_ko_sample.json"
MAX_TRANSLATIONS_PER_GLOSS = 4
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
    if not text or len(text) > 40:
        return ""
    if not re.search(r"[가-힣]", text):
        return ""
    if any(mark in text for mark in ("\n", "\r")):
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


def translate_glosses_to_korean(dictionary_gloss: str) -> str:
    index = get_en_ko_index()
    meanings: list[str] = []
    seen: set[str] = set()
    for gloss in dictionary_gloss.split(";"):
        translations: list[str] = []
        for key in _candidate_keys(gloss):
            translations = index.get(key, [])
            if translations:
                break
        for translation in translations[:MAX_TRANSLATIONS_PER_GLOSS]:
            if translation not in seen:
                meanings.append(translation)
                seen.add(translation)
    return ", ".join(meanings)

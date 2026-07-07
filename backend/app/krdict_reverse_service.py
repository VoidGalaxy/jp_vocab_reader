from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Any

from app.dictionary_file_manager import DICTIONARY_DIR, get_krdict_reverse_path
from app.meaning_ranker import is_valid_korean_candidate


KRDICT_REVERSE_FULL_PATH = get_krdict_reverse_path()
KRDICT_REVERSE_SAMPLE_PATH = DICTIONARY_DIR / "krdict_reverse_sample.json"
GZIP_MAGIC = b"\x1f\x8b"

logger = logging.getLogger(__name__)

_krdict_reverse_index: dict[str, list[str]] | None = None
_krdict_reverse_status: dict[str, Any] = {
    "source": "not-loaded",
    "path": "",
    "entries": 0,
    "loaded": False,
    "reason": None,
    "errors": [],
}


def normalize_gloss_key(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _candidate_keys(gloss: str) -> list[str]:
    normalized = normalize_gloss_key(gloss)
    candidates = [normalized]
    if normalized.startswith("to "):
        candidates.append(normalized[3:].strip())
    return [candidate for candidate in candidates if candidate]


def _clean_korean(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.strip().split())
    return text if is_valid_korean_candidate(text) else ""


def _looks_like_gzip(path: Path) -> bool:
    try:
        with path.open("rb") as input_file:
            return input_file.read(2) == GZIP_MAGIC
    except OSError:
        return False


def _read_reverse_index(path: Path) -> tuple[dict[str, list[str]] | None, str]:
    if not path.exists():
        return None, "missing"
    if zipfile.is_zipfile(path):
        return None, "appears to be a ZIP archive; check krdict reverse index generation"
    if _looks_like_gzip(path):
        return None, "appears to be a GZIP file; check krdict reverse index generation"
    try:
        raw_data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"read error: {exc}"
    except UnicodeDecodeError as exc:
        return None, f"decode error: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"json parse error: line {exc.lineno} column {exc.colno}"

    if not isinstance(raw_data, dict):
        return None, "unsupported root format"

    index: dict[str, list[str]] = {}
    for raw_key, raw_value in raw_data.items():
        key = normalize_gloss_key(str(raw_key))
        if not key:
            continue
        values = [raw_value] if isinstance(raw_value, str) else raw_value
        if not isinstance(values, list):
            continue
        bucket = index.setdefault(key, [])
        for value in values:
            korean = _clean_korean(value)
            if korean and korean not in bucket:
                bucket.append(korean)
        if not bucket:
            del index[key]

    if not index:
        return None, "no valid entries"
    return index, ""


def _load_index() -> dict[str, list[str]]:
    global _krdict_reverse_status
    errors: list[str] = []
    # "fallback" means a full/sample file was present but unusable (corrupt,
    # wrong format, or empty after filtering); "none" means no reverse index
    # file was available at all.
    attempted_but_unusable = False
    for path in (KRDICT_REVERSE_FULL_PATH, KRDICT_REVERSE_SAMPLE_PATH):
        index, error = _read_reverse_index(path)
        if index is None:
            errors.append(f"{path.name}: {error}")
            if error != "missing":
                attempted_but_unusable = True
                logger.warning("krdict reverse index skipped: %s (%s)", path.name, error)
            else:
                logger.info("krdict reverse index skipped: %s (%s)", path.name, error)
            continue
        _krdict_reverse_status = {
            "source": "full" if path == KRDICT_REVERSE_FULL_PATH else "sample",
            "path": str(path),
            "entries": len(index),
            "loaded": True,
            "reason": None,
            "errors": errors,
        }
        logger.info(
            "krdict reverse index loaded: %s (%s entries)", path.name, len(index)
        )
        return index

    _krdict_reverse_status = {
        "source": "fallback" if attempted_but_unusable else "none",
        "path": "",
        "entries": 0,
        "loaded": False,
        "reason": errors[0] if errors else None,
        "errors": errors,
    }
    return {}


def get_krdict_reverse_index() -> dict[str, list[str]]:
    global _krdict_reverse_index
    if _krdict_reverse_index is None:
        _krdict_reverse_index = _load_index()
    return _krdict_reverse_index


def get_krdict_reverse_status() -> dict[str, Any]:
    get_krdict_reverse_index()
    return dict(_krdict_reverse_status)


def lookup_krdict_reverse(english_gloss: str) -> list[str]:
    index = get_krdict_reverse_index()
    if not index:
        return []
    results: list[str] = []
    seen: set[str] = set()
    for key in _candidate_keys(english_gloss):
        for word in index.get(key, []):
            if word not in seen:
                results.append(word)
                seen.add(word)
    return results

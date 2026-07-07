from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Any

from app.dictionary_file_manager import DICTIONARY_DIR, get_full_dictionary_path

JMDICT_FULL_PATH = get_full_dictionary_path()
JMDICT_SAMPLE_PATH = DICTIONARY_DIR / "jmdict_sample.json"
# Some entries interleave many languages/senses per headword (e.g. a single
# multi-language "just now" sense for 先 alone fills 8+ slots), which used to
# starve out legitimate later senses ("front"/"before"/"end") before they
# were ever looked up. Raised so those senses are reachable; downstream
# scoring (meaning_quality_filter) -- not this cap -- is what keeps
# low-ranked/irrelevant senses from being picked as the top candidate.
MAX_GLOSSES_PER_LOOKUP = 40
ENTRY_LIST_KEYS = ("entries", "words", "jmdict", "JMdict")

logger = logging.getLogger(__name__)

_jmdict_index: dict[str, list[str]] | None = None
_jmdict_status: dict[str, Any] = {
    "source": "not-loaded",
    "path": "",
    "entry_count": 0,
    "key_count": 0,
    "errors": [],
}


def _clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _root_entries(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return None
    for key in ENTRY_LIST_KEYS:
        entries = value.get(key)
        if isinstance(entries, list):
            return entries
    return None


def _extract_texts(values: Any, text_keys: tuple[str, ...]) -> list[str]:
    texts: list[str] = []
    for value in _as_list(values):
        if isinstance(value, str):
            text = value.strip()
        elif isinstance(value, dict):
            text = next(
                (
                    _clean_text(value.get(key))
                    for key in text_keys
                    if _clean_text(value.get(key))
                ),
                "",
            )
        else:
            text = ""
        if text:
            texts.append(text)
    return texts


def _extract_glosses(entry: dict[str, Any]) -> list[str]:
    glosses = _extract_texts(entry.get("glosses"), ("text",))
    for sense in _as_list(entry.get("sense")):
        if not isinstance(sense, dict):
            continue
        glosses.extend(_extract_texts(sense.get("gloss"), ("text",)))
    return dedupe_texts(glosses)


def normalize_jmdict_entry(entry: Any) -> dict[str, list[str]] | None:
    if not isinstance(entry, dict):
        return None

    kanji_terms = [
        *_extract_texts(entry.get("kanji"), ("text", "keb")),
        *_extract_texts(entry.get("k_ele"), ("keb", "text")),
    ]
    kana_terms = [
        *_extract_texts(entry.get("kana"), ("text", "reb")),
        *_extract_texts(entry.get("r_ele"), ("reb", "text")),
    ]
    glosses = _extract_glosses(entry)
    if not glosses or not (kanji_terms or kana_terms):
        return None

    return {
        "kanji": dedupe_texts(kanji_terms),
        "kana": dedupe_texts(kana_terms),
        "glosses": glosses,
    }


def dedupe_texts(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip()
        if text and text not in seen:
            deduped.append(text)
            seen.add(text)
    return deduped


def read_jmdict_entries(path: Path) -> tuple[list[Any] | None, str]:
    if not path.exists():
        return None, "missing"
    if zipfile.is_zipfile(path):
        return (
            None,
            "appears to be a ZIP archive; use zipped download support or extract JSON",
        )
    try:
        raw_data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"read error: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"json parse error: line {exc.lineno} column {exc.colno}"

    entries = _root_entries(raw_data)
    if entries is None:
        return None, "unsupported root format"
    return entries, ""


def _load_jmdict_index() -> dict[str, list[str]]:
    global _jmdict_status
    errors: list[str] = []
    invalid_full_seen = False
    for path in (JMDICT_FULL_PATH, JMDICT_SAMPLE_PATH):
        entries, error = read_jmdict_entries(path)
        if entries is None:
            errors.append(f"{path.name}: {error}")
            if path == JMDICT_FULL_PATH and error != "missing":
                invalid_full_seen = True
                logger.warning("JMdict full dictionary skipped: %s", error)
            else:
                logger.info("JMdict dictionary skipped: %s (%s)", path.name, error)
            continue
        index = build_jmdict_index(entries)
        if not index:
            errors.append(f"{path.name}: no valid entries")
            logger.info("JMdict dictionary skipped: %s (no valid entries)", path.name)
            continue
        _jmdict_status = {
            "source": "full" if path == JMDICT_FULL_PATH else "sample",
            "path": str(path),
            "entry_count": len(entries),
            "key_count": len(index),
            "errors": errors,
        }
        logger.info(
            "JMdict dictionary loaded: %s (%s entries, %s keys)",
            path.name,
            len(entries),
            len(index),
        )
        return index

    _jmdict_status = {
        "source": "invalid_full" if invalid_full_seen else "fallback",
        "path": "",
        "entry_count": 0,
        "key_count": 0,
        "errors": errors,
    }
    logger.warning("JMdict dictionary unavailable; no valid local dictionary file")
    return {}


def build_jmdict_index(entries: list[Any]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for entry in entries:
        normalized = normalize_jmdict_entry(entry)
        if not normalized:
            continue

        keys = [*normalized["kanji"], *normalized["kana"]]
        for key in keys:
            index.setdefault(key, [])
            for gloss in normalized["glosses"]:
                if gloss not in index[key]:
                    index[key].append(gloss)

    return index


def get_jmdict_index() -> dict[str, list[str]]:
    global _jmdict_index
    if _jmdict_index is None:
        _jmdict_index = _load_jmdict_index()
    return _jmdict_index


def get_jmdict_status() -> dict[str, Any]:
    get_jmdict_index()
    return dict(_jmdict_status)


def lookup_jmdict_gloss(
    *,
    surface: str = "",
    base_form: str = "",
    normalized_form: str = "",
    reading: str = "",
) -> str:
    index = get_jmdict_index()
    glosses: list[str] = []
    # base_form is the canonical JMdict headword; check it before the raw
    # inflected surface, which can otherwise coincidentally match an
    # unrelated entry (e.g. a noun sharing spelling with a verb's okurigana
    # form) and crowd out the real sense once MAX_GLOSSES_PER_LOOKUP is hit.
    for key in (base_form, normalized_form, surface, reading):
        for gloss in index.get((key or "").strip(), []):
            if gloss not in glosses:
                glosses.append(gloss)
            if len(glosses) >= MAX_GLOSSES_PER_LOOKUP:
                return "; ".join(glosses)
    return "; ".join(glosses)

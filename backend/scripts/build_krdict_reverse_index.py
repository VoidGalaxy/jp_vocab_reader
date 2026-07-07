from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Any, Iterable


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# This script builds a local reverse index (English gloss -> Korean words)
# from an already-downloaded/exported input file. It does not call the
# 국립국어원 API itself. Fetching/exporting source data from
# 한국어기초사전/우리말샘 is a separate, manual/offline step subject to their
# API terms and attribution requirements -- see docs/dictionary-data.md.

MAX_KOREAN_LENGTH = 40
MAX_ENGLISH_KEY_LENGTH = 60

ENTRY_LIST_KEYS = ("entries", "items", "words", "results")

# Korean headword/lemma field name variants seen across krdict-style exports.
KOREAN_FIELDS = ("word", "korean", "lemma", "target_code", "vocabulary")

# English translation list field name variants.
TRANSLATION_LIST_FIELDS = ("translations", "translation", "trans_word", "trans")

# Field name variants for the translated word inside a translation object.
TRANSLATION_WORD_FIELDS = ("word", "trans_word", "text", "trans")

# Field name variants for the language code/label inside a translation object.
LANGUAGE_FIELDS = ("language", "lang", "trans_lang")

# Nested sense-list field name variants (국립국어원-style API/dump shape).
SENSE_LIST_FIELDS = ("sense", "senses")

ENGLISH_LANGUAGE_LABELS = {"english", "en", "eng", "영어"}


def normalize_english(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def clean_korean(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    if "�" in value:
        return ""
    text = " ".join(value.strip().split())
    if not text or len(text) > MAX_KOREAN_LENGTH:
        return ""
    if not any("가" <= char <= "힣" for char in text):
        return ""
    return text


def open_text(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_jsonl(path: Path) -> Iterable[Any]:
    with open_text(path) as input_file:
        for line_number, line in enumerate(input_file, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                yield json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc


def iter_json_entries(path: Path) -> Iterable[Any]:
    with open_text(path) as input_file:
        raw_data = json.load(input_file)
    if isinstance(raw_data, list):
        yield from raw_data
        return
    if isinstance(raw_data, dict):
        for key in ENTRY_LIST_KEYS:
            entries = raw_data.get(key)
            if isinstance(entries, list):
                yield from entries
                return
        yield raw_data
        return
    raise ValueError("unsupported krdict raw JSON root (expected a list or an object with an entry list)")


def iter_entries(path: Path) -> Iterable[Any]:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if ".jsonl" in suffixes:
        yield from iter_jsonl(path)
    else:
        yield from iter_json_entries(path)


def is_english_language(value: Any) -> bool:
    # No language annotation at all (plain string translations, as in the
    # simple {"word": ..., "translations": [...]} shape) is assumed English.
    if value is None:
        return True
    if not isinstance(value, str):
        return True
    return value.strip().lower() in ENGLISH_LANGUAGE_LABELS


def find_korean_lemma(entry: dict[str, Any]) -> str:
    for field_name in KOREAN_FIELDS:
        korean = clean_korean(entry.get(field_name))
        if korean:
            return korean
    return ""


def extract_translation_word(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        language = None
        for field_name in LANGUAGE_FIELDS:
            if field_name in item:
                language = item.get(field_name)
                break
        if not is_english_language(language):
            return None
        for field_name in TRANSLATION_WORD_FIELDS:
            value = item.get(field_name)
            if isinstance(value, str) and value.strip():
                return value
    return None


def collect_translation_items(entry: dict[str, Any]) -> list[Any]:
    items: list[Any] = []
    for field_name in TRANSLATION_LIST_FIELDS:
        value = entry.get(field_name)
        if isinstance(value, list):
            items.extend(value)
        elif isinstance(value, str):
            items.append(value)

    for sense_field_name in SENSE_LIST_FIELDS:
        senses = entry.get(sense_field_name)
        if not isinstance(senses, list):
            continue
        for sense in senses:
            if not isinstance(sense, dict):
                continue
            for field_name in TRANSLATION_LIST_FIELDS:
                value = sense.get(field_name)
                if isinstance(value, list):
                    items.extend(value)
                elif isinstance(value, str):
                    items.append(value)

    return items


def collect_english_keys(entry: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for item in collect_translation_items(entry):
        word = extract_translation_word(item)
        normalized = normalize_english(word)
        if not normalized or len(normalized) > MAX_ENGLISH_KEY_LENGTH:
            continue
        candidates = [normalized]
        if normalized.startswith("to "):
            stripped = normalized[3:].strip()
            if stripped:
                candidates.append(stripped)
        for candidate in candidates:
            if candidate not in keys:
                keys.append(candidate)
    return keys


def extract_reverse_entry(entry: Any) -> tuple[str, list[str]] | None:
    if not isinstance(entry, dict):
        return None

    korean = find_korean_lemma(entry)
    if not korean:
        return None

    english_keys = collect_english_keys(entry)
    if not english_keys:
        return None

    return korean, english_keys


def build_reverse_index(input_path: Path) -> tuple[int, int, dict[str, list[str]]]:
    raw_count = 0
    skipped_count = 0
    index: dict[str, list[str]] = {}
    for entry in iter_entries(input_path):
        raw_count += 1
        extracted = extract_reverse_entry(entry)
        if not extracted:
            skipped_count += 1
            continue
        korean, english_keys = extracted
        for english_key in english_keys:
            bucket = index.setdefault(english_key, [])
            if korean not in bucket:
                bucket.append(korean)
    return raw_count, skipped_count, index


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a krdict-style reverse index (English gloss -> Korean words) "
            "from an already-exported JSON, JSONL, or gzipped JSONL input file. "
            "Does not call any external API."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input JSON (list or {entries: [...]}), .jsonl, or .jsonl.gz path.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path, for example data/dictionary/krdict_reverse_full.json.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        raw_count, skipped_count, index = build_reverse_index(input_path)
    except json.JSONDecodeError as exc:
        print(f"Error: input is not valid JSON ({input_path}): {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: could not parse input ({input_path}): {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: could not read input ({input_path}): {exc}", file=sys.stderr)
        return 1

    korean_candidates_total = sum(len(values) for values in index.values())

    if not index:
        print(
            "Error: no reverse-index entries could be extracted from "
            f"{input_path}. Checked Korean fields {KOREAN_FIELDS} and English "
            f"translation fields {TRANSLATION_LIST_FIELDS} (including a nested "
            f"{SENSE_LIST_FIELDS} structure). Confirm the input matches one of "
            "the formats documented in docs/dictionary-data.md.",
            file=sys.stderr,
        )
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Raw entries processed: {raw_count}")
    print(f"Reverse keys: {len(index)}")
    print(f"Korean candidates total: {korean_candidates_total}")
    print(f"Skipped: {skipped_count}")
    print(f"Wrote: {output_path}")
    if output_path.name == "krdict_reverse_full.json":
        print("Reminder: krdict_reverse_full.json is intentionally ignored by Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

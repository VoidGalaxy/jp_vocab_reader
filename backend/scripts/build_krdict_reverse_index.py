from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Any, Iterable


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Skeleton only: this script builds a local reverse index
# (English gloss -> Korean words) from an already-downloaded input file.
# It does not call the 국립국어원 API itself. Fetching/exporting source data
# from 한국어기초사전/우리말샘 is a separate, manual/offline step subject to
# their API terms and attribution requirements -- see docs/dictionary-data.md.

MAX_TRANSLATION_LENGTH = 40
ENTRY_LIST_KEYS = ("entries", "items", "words", "results")
ENGLISH_KEY_FIELDS = ("english", "gloss", "word", "headword", "en")
KOREAN_VALUE_FIELDS = ("korean", "translations", "meanings", "words", "ko")


def normalize_english(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def clean_korean(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.strip().split())
    if not text or len(text) > MAX_TRANSLATION_LENGTH:
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
    raise ValueError("unsupported krdict raw JSON root")


def iter_entries(path: Path) -> Iterable[Any]:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if ".jsonl" in suffixes:
        yield from iter_jsonl(path)
    else:
        yield from iter_json_entries(path)


def find_first_str(entry: dict[str, Any], field_names: tuple[str, ...]) -> str:
    for field_name in field_names:
        value = entry.get(field_name)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def collect_korean_values(entry: dict[str, Any]) -> list[str]:
    for field_name in KOREAN_VALUE_FIELDS:
        raw_value = entry.get(field_name)
        if isinstance(raw_value, str):
            raw_value = [raw_value]
        if not isinstance(raw_value, list):
            continue
        cleaned: list[str] = []
        for item in raw_value:
            if isinstance(item, str):
                korean = clean_korean(item)
            elif isinstance(item, dict):
                korean = clean_korean(
                    item.get("word") or item.get("text") or item.get("translation")
                )
            else:
                korean = ""
            if korean and korean not in cleaned:
                cleaned.append(korean)
        if cleaned:
            return cleaned
    return []


def extract_reverse_entry(entry: Any) -> tuple[str, list[str]] | None:
    if not isinstance(entry, dict):
        return None

    english = normalize_english(find_first_str(entry, ENGLISH_KEY_FIELDS))
    if not english:
        return None

    korean_values = collect_korean_values(entry)
    if not korean_values:
        return None

    return english, korean_values


def build_reverse_index(input_path: Path) -> tuple[int, dict[str, list[str]]]:
    raw_count = 0
    index: dict[str, list[str]] = {}
    for entry in iter_entries(input_path):
        raw_count += 1
        extracted = extract_reverse_entry(entry)
        if not extracted:
            continue
        english, korean_values = extracted
        bucket = index.setdefault(english, [])
        for korean in korean_values:
            if korean not in bucket:
                bucket.append(korean)
    return raw_count, index


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a krdict-style reverse index (English gloss -> Korean words) "
            "from an already-exported JSON or JSONL input file. Does not call "
            "any external API."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input JSON (list or {entries: [...]}) or JSONL path.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path, for example data/dictionary/krdict_reverse_full.json.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    raw_count, index = build_reverse_index(input_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Input entries: {raw_count}")
    print(f"Output keys: {len(index)}")
    print(f"Wrote: {output_path}")
    if output_path.name == "krdict_reverse_full.json":
        print("Reminder: krdict_reverse_full.json is intentionally ignored by Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

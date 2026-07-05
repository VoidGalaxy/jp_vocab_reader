from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Any, Iterable


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MAX_TRANSLATION_LENGTH = 40
ENTRY_LIST_KEYS = ("entries", "items", "words")


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
    if any(mark in text for mark in ("。", "！", "？", ".", "!", "?")) and len(text) > 12:
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
    raise ValueError("unsupported Kaikki JSON root")


def iter_entries(path: Path) -> Iterable[Any]:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if ".jsonl" in suffixes:
        yield from iter_jsonl(path)
    else:
        yield from iter_json_entries(path)


def collect_translation_values(value: Any) -> list[str]:
    translations: list[str] = []
    if not isinstance(value, list):
        return translations
    for item in value:
        if isinstance(item, str):
            korean = clean_korean(item)
        elif isinstance(item, dict):
            lang_code = str(item.get("lang_code") or item.get("code") or "").lower()
            lang = str(item.get("lang") or "").lower()
            if lang_code not in {"ko", "kor"} and "korean" not in lang:
                continue
            korean = clean_korean(
                item.get("word")
                or item.get("text")
                or item.get("translation")
                or item.get("sense")
            )
        else:
            korean = ""
        if korean:
            translations.append(korean)
    return translations


def extract_korean_translations(entry: Any) -> tuple[str, list[str]] | None:
    if not isinstance(entry, dict):
        return None
    language = str(entry.get("lang_code") or entry.get("lang") or "").lower()
    if language and language not in {"en", "english"}:
        return None

    english = normalize_english(entry.get("word") or entry.get("headword"))
    if not english:
        return None

    translations: list[str] = []
    translations.extend(collect_translation_values(entry.get("translations")))
    senses = entry.get("senses")
    if isinstance(senses, list):
        for sense in senses:
            if isinstance(sense, dict):
                translations.extend(collect_translation_values(sense.get("translations")))

    deduped: list[str] = []
    seen: set[str] = set()
    for translation in translations:
        if translation not in seen:
            deduped.append(translation)
            seen.add(translation)
    if not deduped:
        return None
    return english, deduped


def build_dictionary(input_path: Path) -> tuple[int, dict[str, list[str]]]:
    raw_count = 0
    dictionary: dict[str, list[str]] = {}
    for entry in iter_entries(input_path):
        raw_count += 1
        extracted = extract_korean_translations(entry)
        if not extracted:
            continue
        english, translations = extracted
        bucket = dictionary.setdefault(english, [])
        for translation in translations:
            if translation not in bucket:
                bucket.append(translation)
    return raw_count, dictionary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an English-Korean subset from a Kaikki/Wiktionary dump."
    )
    parser.add_argument("--input", required=True, help="Kaikki raw JSON or JSONL path.")
    parser.add_argument(
        "--output",
        required=True,
        help="Output path, for example data/dictionary/en_ko_full.json.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    raw_count, dictionary = build_dictionary(input_path)
    output_entries = [
        {"english": english, "korean": translations}
        for english, translations in sorted(dictionary.items())
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output_entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Input entries: {raw_count}")
    print(f"Output entries: {len(output_entries)}")
    print(f"Wrote: {output_path}")
    if output_path.name == "en_ko_full.json":
        print("Reminder: en_ko_full.json is intentionally ignored by Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

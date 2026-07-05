from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.jmdict_service import normalize_jmdict_entry, read_jmdict_entries  # noqa: E402


def dedupe_entries(entries: list[dict[str, list[str]]]) -> list[dict[str, list[str]]]:
    deduped: list[dict[str, list[str]]] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = set()
    for entry in entries:
        key = (
            tuple(entry["kanji"]),
            tuple(entry["kana"]),
            tuple(entry["glosses"]),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def normalize_entries(raw_entries: list[Any]) -> list[dict[str, list[str]]]:
    normalized_entries: list[dict[str, list[str]]] = []
    for raw_entry in raw_entries:
        entry = normalize_jmdict_entry(raw_entry)
        if not entry:
            continue
        normalized_entries.append(
            {
                "kanji": entry["kanji"],
                "kana": entry["kana"],
                "glosses": entry["glosses"],
            }
        )
    return dedupe_entries(normalized_entries)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize a JMdict JSON file into the app dictionary format."
    )
    parser.add_argument("--input", required=True, help="Raw JMdict JSON path.")
    parser.add_argument(
        "--output",
        required=True,
        help="Output path, for example data/dictionary/jmdict_full.json.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    raw_entries, error = read_jmdict_entries(input_path)
    if raw_entries is None:
        print(f"Input is not readable as supported JMdict JSON: {error}")
        return 1

    normalized_entries = normalize_entries(raw_entries)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(normalized_entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Input entries: {len(raw_entries)}")
    print(f"Output entries: {len(normalized_entries)}")
    print(f"Wrote: {output_path}")
    if output_path.name == "jmdict_full.json":
        print("Reminder: jmdict_full.json is intentionally ignored by Git.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

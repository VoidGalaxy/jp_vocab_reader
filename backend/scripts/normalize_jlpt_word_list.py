from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Various external JLPT word-list exports use different header names for the
# same field. This is the only place that needs to know those aliases --
# everything downstream (build_jlpt_quality_draft.py,
# build_jlpt_deck_from_reviewed_csv.py) only ever sees the standard columns.
COLUMN_ALIASES: dict[str, list[str]] = {
    "level": ["level", "jlpt_level"],
    "surface": ["surface", "word", "expression", "kanji", "vocab"],
    "reading": ["reading", "kana", "furigana"],
    "source_meaning_en": ["meaning_en", "english", "meaning", "gloss"],
    "source_meaning_ko": ["meaning_ko", "korean"],
    "source_note": ["tags", "note"],
}

OUTPUT_FIELDS = (
    "level",
    "surface",
    "reading",
    "source_meaning_en",
    "source_meaning_ko",
    "source_note",
)


def build_header_lookup(fieldnames: list[str]) -> dict[str, str]:
    return {name.strip().lower(): name for name in fieldnames if name}


def resolve_column_map(fieldnames: list[str]) -> dict[str, str]:
    header_lookup = build_header_lookup(fieldnames)
    column_map: dict[str, str] = {}
    for output_field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            source_header = header_lookup.get(alias)
            if source_header:
                column_map[output_field] = source_header
                break
    return column_map


def normalize_rows(
    reader: csv.DictReader, column_map: dict[str, str], level: str
) -> tuple[list[dict[str, str]], int, int]:
    rows: list[dict[str, str]] = []
    skipped_blank = 0
    skipped_level = 0

    for raw_row in reader:
        surface = (raw_row.get(column_map.get("surface", ""), "") or "").strip()
        if not surface:
            skipped_blank += 1
            continue

        row_level = (raw_row.get(column_map.get("level", ""), "") or "").strip().upper()
        if row_level and row_level != level.upper():
            skipped_level += 1
            continue

        rows.append(
            {
                "level": row_level or level.upper(),
                "surface": surface,
                "reading": (raw_row.get(column_map.get("reading", ""), "") or "").strip(),
                "source_meaning_en": (
                    raw_row.get(column_map.get("source_meaning_en", ""), "") or ""
                ).strip(),
                "source_meaning_ko": (
                    raw_row.get(column_map.get("source_meaning_ko", ""), "") or ""
                ).strip(),
                "source_note": (
                    raw_row.get(column_map.get("source_note", ""), "") or ""
                ).strip(),
            }
        )

    return rows, skipped_blank, skipped_level


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize an externally-sourced JLPT word-list CSV (various "
            "column naming conventions) into the standard "
            "level,surface,reading,source_meaning_en,source_meaning_ko,"
            "source_note shape used by the rest of the JLPT deck pipeline. "
            "Does not call any dictionary/analyze service -- see "
            "build_jlpt_quality_draft.py for that step."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="External CSV path")
    parser.add_argument(
        "--output", required=True, type=Path, help="Normalized CSV output path"
    )
    parser.add_argument(
        "--level", required=True, help="Level label to tag/filter rows with, e.g. N5"
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"input file not found: {args.input}")
        return 1

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        column_map = resolve_column_map(fieldnames)
        if "surface" not in column_map:
            print(
                "could not find a surface/word/expression/kanji/vocab column "
                f"in {args.input} (columns found: {fieldnames})"
            )
            return 1

        rows, skipped_blank, skipped_level = normalize_rows(reader, column_map, args.level)

    print(f"matched columns: {column_map}")
    if skipped_blank:
        print(f"skipped {skipped_blank} row(s) with no surface")
    if skipped_level:
        print(f"skipped {skipped_level} row(s) with a different level")
    if not rows:
        print("no rows to write")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {args.output} ({len(rows)} row(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

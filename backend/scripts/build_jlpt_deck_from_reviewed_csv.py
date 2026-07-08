from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analyzer import analyzer, katakana_to_hiragana  # noqa: E402


# Required columns for a *reviewed* CSV. meaning_ko here is a human-approved
# final value, not a hint -- unlike build_jlpt_deck_package.py's
# meaning_hint_ko, it is used as-is and never re-derived from the dictionary
# pipeline. Extra columns (e.g. leftover source_meaning_en/warnings from the
# quality draft) are tolerated and ignored.
REQUIRED_FIELDS = (
    "level",
    "surface",
    "reading",
    "meaning_ko",
    "example_sentence",
    "example_translation_ko",
    "note_ko",
)

# Leftover-review markers that must never reach a published shared deck.
# Mirrors the marker checks in validate_jlpt_reviewed_csv.py -- this is a
# last-line-of-defense guard, not a replacement for running that script.
UNREVIEWED_MARKERS = ("확인 필요", "TODO", "MEANING_NEEDS_REVIEW", "source English")

DECK_NAME_TEMPLATE = "JLPT {level} 추천 어휘"
# Not an official JLPT word list -- the new-format JLPT does not publish one.
# Keep this wording in sync with docs/jlpt-decks.md and
# build_jlpt_deck_package.py; avoid "공식"/"official" phrasing anywhere.
DECK_DESCRIPTION = (
    "공식 JLPT 어휘 목록이 아니라, 공개 학습 자료와 내부 사전 데이터를 바탕으로 "
    "구성한 레벨별 추천 어휘 덱입니다. 시험 대비와 원문 읽기 입문용으로 활용하세요."
)
MAX_NOTE_LENGTH = 80
MAX_CONTEXT_LENGTH = 200


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def enrich_from_analyzer(surface: str) -> dict[str, str]:
    # Only used for structural fields (base_form/normalized_form/
    # part_of_speech/dictionary_gloss) that a reviewed CSV doesn't carry --
    # meaning_ko itself is never overridden here, it comes from the reviewed
    # CSV as-is.
    tokens, raw_tokens = analyzer.analyze_with_raw(surface, deck_id=None)
    if tokens:
        token = tokens[0]
        return {
            "base_form": str(token.get("base_form") or surface),
            "part_of_speech": str(token.get("part_of_speech") or ""),
            "normalized_form": str(token.get("normalized_form") or surface),
            "dictionary_gloss": str(token.get("dictionary_gloss") or ""),
        }
    if raw_tokens:
        raw = raw_tokens[0]
        return {
            "base_form": str(raw.get("base_form") or surface),
            "part_of_speech": "",
            "normalized_form": str(raw.get("base_form") or surface),
            "dictionary_gloss": "",
        }
    return {
        "base_form": surface,
        "part_of_speech": "",
        "normalized_form": surface,
        "dictionary_gloss": "",
    }


def read_reviewed_rows(input_path: Path, level: str) -> list[dict[str, str]]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing_columns = [field for field in REQUIRED_FIELDS if field not in fieldnames]
        if missing_columns:
            raise ValueError(
                f"CSV is missing required column(s): {', '.join(missing_columns)}"
            )
        rows = [
            {key: (value or "").strip() for key, value in row.items()}
            for row in reader
        ]

    matched: list[dict[str, str]] = []
    skipped_level = 0
    skipped_blank_surface = 0
    skipped_blank_meaning = 0
    for row in rows:
        if not row.get("surface"):
            skipped_blank_surface += 1
            continue
        row_level = row.get("level", "").strip().upper()
        if row_level and row_level != level.upper():
            skipped_level += 1
            continue
        if not row.get("meaning_ko"):
            skipped_blank_meaning += 1
            continue
        matched.append(row)

    if skipped_level:
        print(f"skipped {skipped_level} row(s) with a different level")
    if skipped_blank_surface:
        print(f"skipped {skipped_blank_surface} row(s) with no surface")
    if skipped_blank_meaning:
        print(
            f"skipped {skipped_blank_meaning} row(s) with no meaning_ko "
            "(not reviewed/approved yet)"
        )
    return matched


def find_unreviewed_rows(rows: list[dict[str, str]]) -> list[str]:
    """Return one message per row that still carries a leftover-review
    marker in meaning_ko or note_ko, e.g. "확인 필요: ..." or "source
    English: ...". Empty list means the CSV looks fully reviewed."""
    problems: list[str] = []
    for row in rows:
        text = f"{row.get('meaning_ko', '')} {row.get('note_ko', '')}"
        matched = [marker for marker in UNREVIEWED_MARKERS if marker.lower() in text.lower()]
        if matched:
            problems.append(
                f"surface={row.get('surface', '')!r} meaning_ko={row.get('meaning_ko', '')!r} "
                f"-- unreviewed marker(s): {', '.join(matched)}"
            )
    return problems


def build_vocab_item(row: dict[str, str]) -> dict[str, object]:
    surface = row["surface"]
    enriched = enrich_from_analyzer(surface)

    reading = katakana_to_hiragana(row.get("reading", ""))
    meaning_ko = row.get("meaning_ko", "")

    example_sentence = row.get("example_sentence", "")
    example_translation = row.get("example_translation_ko", "")
    note = row.get("note_ko", "")[:MAX_NOTE_LENGTH]

    context_parts = []
    if example_translation:
        context_parts.append(f"해석: {example_translation}")
    if note:
        context_parts.append(f"참고: {note}")
    context_explanation_ko = " / ".join(context_parts)[:MAX_CONTEXT_LENGTH]

    return {
        "surface": surface,
        "base_form": enriched["base_form"] or surface,
        "reading": reading,
        "part_of_speech": enriched["part_of_speech"],
        "normalized_form": enriched["normalized_form"] or surface,
        "meaning_ko": meaning_ko,
        "dictionary_gloss": enriched["dictionary_gloss"],
        "context_explanation_ko": context_explanation_ko,
        "example_sentence": example_sentence,
        "quality_tag": "normal",
    }


def build_deck_package(level: str, rows: list[dict[str, str]]) -> dict[str, object]:
    vocab_items = [build_vocab_item(row) for row in rows]
    return {
        "package_type": "jp_vocab_reader_deck",
        "package_version": 1,
        "exported_at": now_iso(),
        "app": {
            "name": "JP Vocab Reader",
            "format": "deck_package",
        },
        "deck": {
            "name": DECK_NAME_TEMPLATE.format(level=level.upper()),
            "description": DECK_DESCRIPTION,
        },
        "vocab_items": vocab_items,
        "custom_terms": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a JLPT-level 'recommended vocabulary' deck package JSON "
            "from a human-reviewed CSV (meaning_ko trusted as-is, not "
            "re-derived). This is NOT an official JLPT word list -- see "
            "docs/jlpt-decks.md."
        )
    )
    parser.add_argument("--level", required=True, help="Level label, e.g. N5")
    parser.add_argument("--input", required=True, type=Path, help="Reviewed CSV path")
    parser.add_argument(
        "--output", required=True, type=Path, help="Deck package JSON output path"
    )
    parser.add_argument(
        "--allow-unreviewed",
        action="store_true",
        default=False,
        help=(
            "Allow building the package even if rows still carry leftover "
            "review markers (확인 필요/TODO/MEANING_NEEDS_REVIEW/source "
            "English). Off by default -- run validate_jlpt_reviewed_csv.py "
            "and build from its clean CSV instead of using this flag."
        ),
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"input file not found: {args.input}")
        return 1

    try:
        rows = read_reviewed_rows(args.input, args.level)
    except ValueError as exc:
        print(str(exc))
        return 1

    if not rows:
        print(f"no reviewed rows matched level={args.level} in {args.input}")
        return 1

    if not args.allow_unreviewed:
        problems = find_unreviewed_rows(rows)
        if problems:
            print(
                f"refusing to build: {len(problems)} row(s) still carry unreviewed "
                "markers (확인 필요/TODO/MEANING_NEEDS_REVIEW/source English). "
                "Run scripts/validate_jlpt_reviewed_csv.py and build from its "
                "clean CSV, or pass --allow-unreviewed to override."
            )
            for problem in problems:
                print(f"  {problem}")
            return 1

    print(f"building deck package for level={args.level.upper()} from {len(rows)} row(s)")
    package = build_deck_package(args.level, rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.output} ({len(package['vocab_items'])} vocab item(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

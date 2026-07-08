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
from app.meaning_ranker import build_meaning_ko  # noqa: E402


CSV_FIELDS = (
    "level",
    "surface",
    "reading",
    "meaning_hint_ko",
    "example_sentence",
    "example_translation_ko",
    "note_ko",
)

DECK_NAME_TEMPLATE = "JLPT {level} 추천 어휘"
# Not an official JLPT word list -- the new-format JLPT does not publish one.
# This is a recommended-vocabulary deck built from public study material and
# this app's own dictionary data. Keep this wording in sync with
# docs/jlpt-decks.md and avoid "공식"/"official" phrasing anywhere it's shown.
DECK_DESCRIPTION = (
    "공식 JLPT 어휘 목록이 아니라, 공개 학습 자료와 내부 사전 데이터를 바탕으로 "
    "구성한 레벨별 추천 어휘 덱입니다. 시험 대비와 원문 읽기 입문용으로 활용하세요."
)
MAX_NOTE_LENGTH = 80
MAX_CONTEXT_LENGTH = 200


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_seed_rows(input_path: Path, level: str) -> list[dict[str, str]]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing_columns = [field for field in CSV_FIELDS if field not in fieldnames]
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
    skipped_blank = 0
    for row in rows:
        if not row.get("surface"):
            skipped_blank += 1
            continue
        row_level = row.get("level", "").strip().upper()
        if row_level and row_level != level.upper():
            skipped_level += 1
            continue
        matched.append(row)

    if skipped_level:
        print(f"skipped {skipped_level} row(s) with a different level")
    if skipped_blank:
        print(f"skipped {skipped_blank} row(s) with no surface")
    return matched


def enrich_from_analyzer(surface: str) -> dict[str, str]:
    # Reuses the exact same tokenize + dictionary lookup pipeline /analyze
    # uses (app.analyzer), just fed a single headword instead of a sentence,
    # so meaning_ko/dictionary_gloss come from the same local JMdict/Kaikki/
    # KRDIC data -- no runtime API calls and no separate lookup logic.
    tokens, raw_tokens = analyzer.analyze_with_raw(surface, deck_id=None)
    if tokens:
        token = tokens[0]
        return {
            "base_form": str(token.get("base_form") or surface),
            "reading": str(token.get("reading") or ""),
            "part_of_speech": str(token.get("part_of_speech") or ""),
            "normalized_form": str(token.get("normalized_form") or surface),
            "meaning_ko": str(token.get("meaning_ko") or ""),
            "dictionary_gloss": str(token.get("dictionary_gloss") or ""),
        }
    if raw_tokens:
        # The word itself was classified as a particle/aux-verb/symbol (e.g. a
        # grammar-point entry like "から") and dropped from `tokens`, but the
        # raw tokenization still has its reading.
        raw = raw_tokens[0]
        return {
            "base_form": str(raw.get("base_form") or surface),
            "reading": katakana_to_hiragana(str(raw.get("reading") or "")),
            "part_of_speech": "",
            "normalized_form": str(raw.get("base_form") or surface),
            "meaning_ko": "",
            "dictionary_gloss": "",
        }
    return {
        "base_form": surface,
        "reading": "",
        "part_of_speech": "",
        "normalized_form": surface,
        "meaning_ko": "",
        "dictionary_gloss": "",
    }


def resolve_meaning_ko(meaning_hint: str, fallback_meaning_ko: str) -> str:
    if not meaning_hint:
        return fallback_meaning_ko

    candidates = [part.strip() for part in meaning_hint.split(",") if part.strip()]
    ranked = build_meaning_ko(candidates)
    # build_meaning_ko only keeps pure-Hangul candidates; if the hand-written
    # hint didn't pass (e.g. it includes punctuation the validator rejects),
    # fall back to the raw hint rather than silently dropping it.
    return ranked or meaning_hint


def build_vocab_item(row: dict[str, str]) -> dict[str, object]:
    surface = row["surface"]
    enriched = enrich_from_analyzer(surface)

    reading = katakana_to_hiragana(row.get("reading") or enriched["reading"])
    meaning_ko = resolve_meaning_ko(row.get("meaning_hint_ko", ""), enriched["meaning_ko"])

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
        # Populated for parity with normal /analyze-created vocab items, but
        # the frontend never renders dictionary_gloss by default -- see
        # docs/jlpt-decks.md.
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
            "from a small, hand-curated CSV seed file. This is NOT an "
            "official JLPT word list -- see docs/jlpt-decks.md."
        )
    )
    parser.add_argument("--level", required=True, help="Level label, e.g. N5")
    parser.add_argument("--input", required=True, type=Path, help="Seed CSV path")
    parser.add_argument(
        "--output", required=True, type=Path, help="Deck package JSON output path"
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"input file not found: {args.input}")
        return 1

    rows = read_seed_rows(args.input, args.level)
    if not rows:
        print(f"no rows matched level={args.level} in {args.input}")
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

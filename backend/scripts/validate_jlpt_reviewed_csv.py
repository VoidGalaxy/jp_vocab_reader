from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Columns a *reviewed* CSV must have. Same shape as
# build_jlpt_deck_from_reviewed_csv.py's REQUIRED_FIELDS -- kept as a
# separate literal here so this script has no import dependency on the
# (heavy, analyzer-loading) build script.
REQUIRED_FIELDS = (
    "level",
    "surface",
    "reading",
    "meaning_ko",
    "example_sentence",
    "example_translation_ko",
    "note_ko",
)

NEEDS_REVIEW_FIELDS = REQUIRED_FIELDS + ("reason",)

DEFAULT_MAX_MEANING_LENGTH = 40
DEFAULT_MAX_CANDIDATES = 4

# Meanings that are too vague to stand alone as a shared-deck gloss.
GENERIC_MEANINGS = {"기타", "것", "수", "때", "점", "부분", "경우"}

KATAKANA_RANGE = ("゠", "ヿ")
HANGUL_RANGE = ("가", "힣")


def is_katakana_char(char: str) -> bool:
    return KATAKANA_RANGE[0] <= char <= KATAKANA_RANGE[1]


def is_hangul_char(char: str) -> bool:
    return HANGUL_RANGE[0] <= char <= HANGUL_RANGE[1]


def is_katakana_word(surface: str) -> bool:
    # "ー" (long vowel mark) and "・" (interpunct, used in compound loanwords
    # like "アイス・クリーム") aren't in the katakana Unicode block but are
    # part of ordinary katakana words, so strip them before checking.
    core = surface.replace("ー", "").replace("・", "")
    return bool(core) and all(is_katakana_char(ch) for ch in core)


def split_candidates(meaning: str) -> list[str]:
    return [part.strip() for part in meaning.split(",") if part.strip()]


def count_hangul(text: str) -> int:
    return sum(1 for ch in text if is_hangul_char(ch))


def count_ascii_letters(text: str) -> int:
    return sum(1 for ch in text if ch.isascii() and ch.isalpha())


def evaluate_row(
    row: dict[str, str],
    max_meaning_length: int,
    max_candidates: int,
) -> list[str]:
    """Return the (possibly empty) list of reason codes this row fails on.

    Every rule is checked independently -- a row can collect more than one
    reason, e.g. a leftover "확인 필요: to avoid" meaning is both
    HAS_CONFIRM_NEEDED and ENGLISH_REMAINS. Reasons are joined by the
    caller with ";".
    """
    reasons: list[str] = []

    meaning = row.get("meaning_ko", "").strip()
    note = row.get("note_ko", "").strip()
    surface = row.get("surface", "").strip()

    if not meaning:
        reasons.append("EMPTY_MEANING")

    # Placeholder/leftover-pipeline markers can show up in either meaning_ko
    # or note_ko -- check both combined.
    marker_text = f"{meaning} {note}"
    if "확인 필요" in marker_text:
        reasons.append("HAS_CONFIRM_NEEDED")
    marker_text_upper = marker_text.upper()
    if "TODO" in marker_text_upper or "MEANING_NEEDS_REVIEW" in marker_text_upper:
        reasons.append("HAS_TODO")
    if "source english" in marker_text.lower():
        reasons.append("HAS_SOURCE_ENGLISH")

    if meaning:
        ascii_letters = count_ascii_letters(meaning)
        hangul_chars = count_hangul(meaning)
        if ascii_letters > 0 and ascii_letters >= hangul_chars:
            reasons.append("ENGLISH_REMAINS")

        candidates = split_candidates(meaning)

        if len(candidates) > max_candidates:
            reasons.append("TOO_MANY_MEANINGS")

        if len(meaning) > max_meaning_length:
            reasons.append("TOO_LONG_MEANING")

        if len(candidates) <= 1 and meaning in GENERIC_MEANINGS:
            reasons.append("TOO_GENERIC_MEANING")

        # Katakana loanwords whose meaning is a single bare candidate are
        # frequently just the reading transliterated into Hangul rather
        # than an actual Korean meaning (e.g. タイプ -> "타입"). Some of
        # these ARE legitimate (Korean also borrows the same loanword), but
        # we can't tell the two apart automatically, so per policy we
        # always route them to needs_review instead of guessing -- a human
        # can promote the good ones back into the clean CSV.
        if is_katakana_word(surface) and len(candidates) <= 1:
            reasons.append("KATAKANA_TRANSLITERATION_ONLY")

    return reasons


def read_rows(input_path: Path) -> list[dict[str, str]]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [field for field in REQUIRED_FIELDS if field not in fieldnames]
        if missing:
            raise ValueError(
                f"CSV is missing required column(s): {', '.join(missing)}"
            )
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in reader
        ]


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Split a human-reviewed JLPT CSV into a shared-deck-ready clean "
            "CSV and a needs_review CSV, based on leftover placeholder "
            "markers, English residue, and other quality signals. See "
            "docs/jlpt-decks.md."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="Reviewed CSV path")
    parser.add_argument(
        "--clean-output", required=True, type=Path, help="Clean CSV output path"
    )
    parser.add_argument(
        "--needs-review-output",
        required=True,
        type=Path,
        help="Needs-review CSV output path",
    )
    parser.add_argument(
        "--max-meaning-length",
        type=int,
        default=DEFAULT_MAX_MEANING_LENGTH,
        help=f"Flag meaning_ko longer than this as TOO_LONG_MEANING (default {DEFAULT_MAX_MEANING_LENGTH})",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=DEFAULT_MAX_CANDIDATES,
        help=(
            "Flag meaning_ko with more than this many comma-separated "
            f"candidates as TOO_MANY_MEANINGS (default {DEFAULT_MAX_CANDIDATES})"
        ),
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"input file not found: {args.input}")
        return 1

    try:
        rows = read_rows(args.input)
    except ValueError as exc:
        print(str(exc))
        return 1

    clean_rows: list[dict[str, str]] = []
    needs_review_rows: list[dict[str, str]] = []
    reason_counts: dict[str, int] = {}

    for row in rows:
        reasons = evaluate_row(row, args.max_meaning_length, args.max_candidates)
        if reasons:
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            needs_review_row = dict(row)
            needs_review_row["reason"] = ";".join(reasons)
            needs_review_rows.append(needs_review_row)
        else:
            clean_rows.append(row)

    write_csv(args.clean_output, REQUIRED_FIELDS, clean_rows)
    write_csv(args.needs_review_output, NEEDS_REVIEW_FIELDS, needs_review_rows)

    print(f"input: {args.input} ({len(rows)} row(s))")
    print(f"clean: {args.clean_output} ({len(clean_rows)} row(s))")
    print(f"needs review: {args.needs_review_output} ({len(needs_review_rows)} row(s))")
    if reason_counts:
        print("reason breakdown:")
        for reason, count in sorted(reason_counts.items(), key=lambda item: -item[1]):
            print(f"  {reason}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

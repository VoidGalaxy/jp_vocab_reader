from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analyzer import analyzer, katakana_to_hiragana  # noqa: E402
from app.meaning_quality_filter import is_risky_korean  # noqa: E402
from app.meaning_ranker import (  # noqa: E402
    get_max_meaning_candidates,
    is_valid_korean_candidate,
)


NORMALIZED_FIELDS = (
    "level",
    "surface",
    "reading",
    "source_meaning_en",
    "source_meaning_ko",
    "source_note",
)

DRAFT_FIELDS = (
    "level",
    "surface",
    "reading",
    "source_meaning_en",
    "generated_meaning_ko",
    "example_sentence",
    "example_translation_ko",
    "note_ko",
    "dictionary_found",
    "meaning_confidence",
    "warnings",
)

# Warning codes in the order a reviewer should look at them: "is this word
# even in our dictionary" first, then meaning quality, then bookkeeping
# issues (duplicates) last.
WARNING_ORDER = (
    "NO_DICTIONARY_MATCH",
    "EMPTY_MEANING",
    "READING_MISMATCH",
    "LOW_CONFIDENCE_MEANING",
    "RISKY_KOREAN_CANDIDATE",
    "TOO_MANY_MEANINGS",
    "MULTIPLE_SENSES",
    "SOURCE_EN_MISMATCH",
    "DUPLICATE_SURFACE",
    "DUPLICATE_SURFACE_READING",
)

# Rough proxy for "this headword has many distinct dictionary senses worth
# double-checking." The local JMdict/Kaikki gloss data interleaves many
# languages under one headword (English, Dutch, French, German, Hungarian,
# Russian, ...), so a raw semicolon-split count is dominated by language
# padding rather than true polysemy. Restricting to plain-ASCII-looking
# segments filters out most (not all) of the non-English noise, but even so,
# ordinary monosemous N5 words routinely land in the 15-25 range on this
# dataset -- calibrated empirically against a handful of basic N5 words so
# this only flags the upper tail instead of firing on nearly every row; this
# is a best-effort/noisy heuristic for a human-reviewed audit, not a
# precise sense count (see docs/jlpt-decks.md).
MULTIPLE_SENSES_THRESHOLD = 28
_ASCII_SEGMENT_RE = re.compile(r"^[A-Za-z0-9 ,()'\-./]+$")

_EN_STOPWORDS = {
    "a", "an", "the", "to", "of", "in", "on", "for", "and", "or", "be", "is",
    "it", "one", "some", "with", "by", "as", "etc", "esp", "usu", "also",
}
_EN_WORD_RE = re.compile(r"[a-zA-Z]+")

MAX_NOTE_LENGTH = 80


def enrich_from_analyzer(surface: str) -> dict[str, str]:
    # Same single-headword reuse of the /analyze pipeline as
    # build_jlpt_deck_package.py -- one local dictionary lookup path, no
    # runtime API calls.
    tokens, raw_tokens = analyzer.analyze_with_raw(surface, deck_id=None)
    if tokens:
        token = tokens[0]
        return {
            "base_form": str(token.get("base_form") or surface),
            "reading": str(token.get("reading") or ""),
            "part_of_speech": str(token.get("part_of_speech") or ""),
            "meaning_ko": str(token.get("meaning_ko") or ""),
            "dictionary_gloss": str(token.get("dictionary_gloss") or ""),
        }
    if raw_tokens:
        raw = raw_tokens[0]
        return {
            "base_form": str(raw.get("base_form") or surface),
            "reading": katakana_to_hiragana(str(raw.get("reading") or "")),
            "part_of_speech": "",
            "meaning_ko": "",
            "dictionary_gloss": "",
        }
    return {
        "base_form": surface,
        "reading": "",
        "part_of_speech": "",
        "meaning_ko": "",
        "dictionary_gloss": "",
    }


def load_safe_example_seeds(level: str) -> dict[str, tuple[str, str]]:
    # Reuse our own already-vetted, self-authored sample sentences (e.g.
    # n5_sample.csv) as a small "safe seed" bank keyed by surface. Never
    # invents new example sentences and never touches textbook/web-novel
    # text. Silently returns {} if no sample exists yet for this level.
    seed_path = BACKEND_DIR / "data" / "jlpt" / f"{level.lower()}_sample.csv"
    if not seed_path.exists():
        return {}

    seeds: dict[str, tuple[str, str]] = {}
    with seed_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            surface = (row.get("surface") or "").strip()
            example_sentence = (row.get("example_sentence") or "").strip()
            if surface and example_sentence:
                seeds[surface] = (
                    example_sentence,
                    (row.get("example_translation_ko") or "").strip(),
                )
    return seeds


def extract_english_words(text: str) -> set[str]:
    return {
        word
        for word in (match.lower() for match in _EN_WORD_RE.findall(text))
        if len(word) > 1 and word not in _EN_STOPWORDS
    }


def count_english_like_segments(dictionary_gloss: str) -> int:
    segments = [part.strip() for part in dictionary_gloss.split(";") if part.strip()]
    return sum(1 for segment in segments if _ASCII_SEGMENT_RE.match(segment))


def resolve_generated_meaning(
    enriched_meaning_ko: str,
    dictionary_found: bool,
    source_meaning_ko: str,
    max_candidates: int,
) -> tuple[str, str]:
    """Returns (generated_meaning_ko, meaning_confidence)."""
    if enriched_meaning_ko:
        return enriched_meaning_ko, ("high" if dictionary_found else "medium")

    # The analyzer/dictionary pipeline found nothing. Only then -- and only
    # as a last resort -- consider the external source's Korean meaning, run
    # through the same Korean-candidate validator and risky-word filter the
    # rest of the app uses. Never trusted blindly.
    if source_meaning_ko:
        candidates = [part.strip() for part in re.split(r"[,/;]", source_meaning_ko) if part.strip()]
        safe_candidates = [
            candidate
            for candidate in candidates
            if is_valid_korean_candidate(candidate) and not is_risky_korean(candidate)
        ][:max_candidates]
        if safe_candidates:
            return ", ".join(safe_candidates), "low"

    return "", "none"


def build_draft_row(
    row: dict[str, str],
    *,
    surface_counts: Counter,
    surface_reading_counts: Counter,
    max_candidates: int,
    example_seeds: dict[str, tuple[str, str]],
) -> dict[str, str]:
    surface = row["surface"]
    source_reading = katakana_to_hiragana(row.get("reading", ""))
    source_meaning_en = row.get("source_meaning_en", "")
    source_meaning_ko = row.get("source_meaning_ko", "")

    enriched = enrich_from_analyzer(surface)
    dictionary_found = bool(enriched["dictionary_gloss"])
    reading = source_reading or enriched["reading"]

    generated_meaning_ko, confidence = resolve_generated_meaning(
        enriched["meaning_ko"], dictionary_found, source_meaning_ko, max_candidates
    )

    example_sentence, example_translation_ko = example_seeds.get(surface, ("", ""))

    warnings: list[str] = []
    if not dictionary_found:
        warnings.append("NO_DICTIONARY_MATCH")
    if not generated_meaning_ko:
        warnings.append("EMPTY_MEANING")
    if source_reading and enriched["reading"] and source_reading != enriched["reading"]:
        warnings.append("READING_MISMATCH")
    if generated_meaning_ko and confidence in ("low", "medium"):
        warnings.append("LOW_CONFIDENCE_MEANING")
    if generated_meaning_ko and any(
        is_risky_korean(candidate.strip())
        for candidate in generated_meaning_ko.split(",")
    ):
        warnings.append("RISKY_KOREAN_CANDIDATE")
    if generated_meaning_ko and len(generated_meaning_ko.split(", ")) > max_candidates:
        warnings.append("TOO_MANY_MEANINGS")
    if count_english_like_segments(enriched["dictionary_gloss"]) > MULTIPLE_SENSES_THRESHOLD:
        warnings.append("MULTIPLE_SENSES")
    if dictionary_found and source_meaning_en:
        source_words = extract_english_words(source_meaning_en)
        gloss_words = extract_english_words(enriched["dictionary_gloss"])
        if source_words and gloss_words and source_words.isdisjoint(gloss_words):
            warnings.append("SOURCE_EN_MISMATCH")
    if surface_counts[surface] > 1:
        warnings.append("DUPLICATE_SURFACE")
    if surface_reading_counts[(surface, reading)] > 1:
        warnings.append("DUPLICATE_SURFACE_READING")

    return {
        "level": row.get("level", ""),
        "surface": surface,
        "reading": reading,
        "source_meaning_en": source_meaning_en,
        "generated_meaning_ko": generated_meaning_ko,
        "example_sentence": example_sentence,
        "example_translation_ko": example_translation_ko,
        # Left blank on purpose -- automatic note generation is out of scope
        # for this step; the column exists for the human reviewer to fill in.
        "note_ko": "",
        "dictionary_found": str(dictionary_found),
        "meaning_confidence": confidence,
        "warnings": ";".join(warnings),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a human-reviewable quality draft CSV from a normalized "
            "JLPT word list: fills in generated_meaning_ko using this app's "
            "own dictionary/analyze pipeline (JMdict + Kaikki/en_ko fallback "
            "+ krdict boosting + meaning quality filter, no runtime API "
            "calls), and flags rows that need human attention via the "
            "warnings column. This file is meant to be reviewed by a person "
            "(or uploaded to an LLM for a first-pass review) before becoming "
            "a deck package -- see docs/jlpt-decks.md."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="Normalized CSV path")
    parser.add_argument(
        "--output", required=True, type=Path, help="Quality draft CSV output path"
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"input file not found: {args.input}")
        return 1

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing_columns = [
            field for field in NORMALIZED_FIELDS if field not in (reader.fieldnames or [])
        ]
        if missing_columns:
            print(f"input CSV is missing required column(s): {', '.join(missing_columns)}")
            return 1
        rows = [
            {key: (value or "").strip() for key, value in row.items()}
            for row in reader
            if (row.get("surface") or "").strip()
        ]

    if not rows:
        print("no rows to process")
        return 1

    levels_present = {row["level"] for row in rows if row.get("level")}
    example_seeds: dict[str, tuple[str, str]] = {}
    for level in levels_present or {"n5"}:
        example_seeds.update(load_safe_example_seeds(level))

    surface_counts = Counter(row["surface"] for row in rows)
    surface_reading_counts = Counter(
        (row["surface"], katakana_to_hiragana(row.get("reading", ""))) for row in rows
    )
    max_candidates = get_max_meaning_candidates()

    draft_rows = [
        build_draft_row(
            row,
            surface_counts=surface_counts,
            surface_reading_counts=surface_reading_counts,
            max_candidates=max_candidates,
            example_seeds=example_seeds,
        )
        for row in rows
    ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DRAFT_FIELDS)
        writer.writeheader()
        writer.writerows(draft_rows)

    warning_counts = Counter()
    for draft_row in draft_rows:
        for code in draft_row["warnings"].split(";"):
            if code:
                warning_counts[code] += 1

    print(f"wrote {args.output} ({len(draft_rows)} row(s))")
    if warning_counts:
        print("warning summary:")
        for code in WARNING_ORDER:
            if warning_counts.get(code):
                print(f"  {code}: {warning_counts[code]}")
    else:
        print("no warnings raised")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

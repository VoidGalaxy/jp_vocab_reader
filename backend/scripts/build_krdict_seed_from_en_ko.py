from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Development/preprocessing-only tool: extracts Korean-language candidates
# from the Kaikki/Wiktionary-derived en_ko_full.json (or en_ko_sample.json
# fallback) and writes them as a plain-text seed list, one word per line,
# for scripts/fetch_krdict_api.py. Never imported or called at runtime, and
# never writes to en_ko_full.json -- it only reads it.

BACKEND_DIR = Path(__file__).resolve().parents[1]
DICTIONARY_DIR = BACKEND_DIR / "data" / "dictionary"
DEFAULT_INPUT_CANDIDATES = (
    DICTIONARY_DIR / "en_ko_full.json",
    DICTIONARY_DIR / "en_ko_sample.json",
)
DEFAULT_OUTPUT = DICTIONARY_DIR / "krdict_seed_generated.txt"

DEFAULT_LIMIT = 3000
DEFAULT_MIN_LENGTH = 1
DEFAULT_MAX_LENGTH = 14

# Splits combined candidates like "일어서다, 일어나다" or "가다/오다" into
# separate seeds.
SPLIT_PATTERN = re.compile(r"[,、，/·;]")
# Strips Hanja/romanization annotations such as "화(化)하다" -> "화하다".
PAREN_PATTERN = re.compile(r"\([^()]*\)")
STRAY_PUNCTUATION_PATTERN = re.compile(r"[()\[\]{}:：\"'“”‘’]")
# After annotation stripping, a usable seed must be plain Hangul syllables
# and spaces only. This single allow-list (instead of a growing blocklist)
# rejects Han/Latin/digit mixes, stray Jamo, tone marks, hyphen-affix
# notation ("-주의", "최-"), and other Wiktionary formatting noise in one
# step.
VALID_CANDIDATE_PATTERN = re.compile(r"^[가-힣][가-힣 ]*$")

# Standalone particles/endings that are not useful dictionary search seeds
# on their own.
FUNCTION_WORD_STOPLIST = {
    "을", "를", "이", "가", "은", "는", "의", "에", "에서", "으로", "로",
    "와", "과", "도", "만", "까지", "부터", "이라고", "라고", "이나", "나",
}


def _default_input_path() -> Path:
    for candidate in DEFAULT_INPUT_CANDIDATES:
        if candidate.exists():
            return candidate
    return DEFAULT_INPUT_CANDIDATES[0]


def load_en_ko_entries(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"unsupported en_ko JSON root in {path} (expected a list)")
    return data


def is_valid_candidate(text: str) -> bool:
    return bool(VALID_CANDIDATE_PATTERN.match(text))


def strip_annotations(text: str) -> str:
    cleaned = text
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = PAREN_PATTERN.sub("", cleaned)
    cleaned = STRAY_PUNCTUATION_PATTERN.sub("", cleaned)
    return " ".join(cleaned.split())


def split_candidate(text: str) -> list[str]:
    return [part.strip() for part in SPLIT_PATTERN.split(text) if part.strip()]


def is_verb_like(text: str) -> bool:
    return len(text) >= 2 and text.endswith("다")


def clean_candidate(raw: object, min_length: int, max_length: int) -> list[str]:
    """Split/clean one raw Korean value into zero or more usable seed words."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    if "�" in raw:
        return []

    results: list[str] = []
    for piece in split_candidate(raw):
        cleaned = strip_annotations(piece)
        if not cleaned:
            continue
        if not is_valid_candidate(cleaned):
            continue
        # Measured including spaces: a multi-word proverb/sentence made of
        # short syllables ("콩 심은 데 콩 나고 팥 심은 데 팥 난다") must still
        # be excluded by --max-length, not just single long words.
        if len(cleaned) < min_length or len(cleaned) > max_length:
            continue
        if cleaned in FUNCTION_WORD_STOPLIST:
            continue
        results.append(cleaned)
    return results


def extract_candidates(
    entries: list[dict],
    min_length: int,
    max_length: int,
    include_verbs: bool,
    include_nouns: bool,
) -> tuple[list[str], int]:
    candidates: list[str] = []
    skipped = 0
    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        korean_values = entry.get("korean")
        if isinstance(korean_values, str):
            korean_values = [korean_values]
        if not isinstance(korean_values, list):
            skipped += 1
            continue

        produced_any = False
        for raw in korean_values:
            for cleaned in clean_candidate(raw, min_length, max_length):
                verb_like = is_verb_like(cleaned)
                if verb_like and not include_verbs:
                    continue
                if not verb_like and not include_nouns:
                    continue
                candidates.append(cleaned)
                produced_any = True
        if not produced_any:
            skipped += 1

    return candidates, skipped


def dedupe_preserve_order(words: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for word in words:
        if word not in seen:
            seen.add(word)
            ordered.append(word)
    return ordered


def load_extra_seed_words(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"extra seed file not found: {path}")
    words: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        words.append(word)
    return words


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Korean-language candidates from the Kaikki/Wiktionary-"
            "derived en_ko_full.json (or en_ko_sample.json fallback) and "
            "write them as a plain-text seed list for "
            "scripts/fetch_krdict_api.py. Development/preprocessing tool "
            "only -- never called at runtime, and only reads en_ko_full.json."
        )
    )
    parser.add_argument(
        "--input",
        help="en_ko JSON file to read (default: en_ko_full.json if present, "
        "otherwise en_ko_sample.json).",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output seed text path (default: %(default)s).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Max number of seed words to write, 0 for unlimited (default: %(default)s).",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=DEFAULT_MIN_LENGTH,
        help="Minimum candidate length in characters (default: %(default)s).",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=DEFAULT_MAX_LENGTH,
        help="Maximum candidate length in characters, to exclude full "
        "sentences/proverbs (default: %(default)s).",
    )
    parser.add_argument(
        "--include-verbs",
        dest="include_verbs",
        action="store_true",
        default=True,
        help='Include verb/adjective-like candidates ending in "다" (default: on).',
    )
    parser.add_argument(
        "--no-include-verbs",
        dest="include_verbs",
        action="store_false",
        help="Exclude verb/adjective-like candidates.",
    )
    parser.add_argument(
        "--include-nouns",
        dest="include_nouns",
        action="store_true",
        default=True,
        help="Include non-predicate (noun-like) candidates (default: on).",
    )
    parser.add_argument(
        "--no-include-nouns",
        dest="include_nouns",
        action="store_false",
        help="Exclude non-predicate (noun-like) candidates.",
    )
    parser.add_argument(
        "--dedupe",
        dest="dedupe",
        action="store_true",
        default=True,
        help="Remove duplicate seeds, keeping first occurrence (default: on).",
    )
    parser.add_argument(
        "--no-dedupe",
        dest="dedupe",
        action="store_false",
        help="Keep duplicate seeds.",
    )
    parser.add_argument(
        "--extra-seed-file",
        action="append",
        default=[],
        help="Additional seed text file(s) to merge in, kept ahead of "
        "generated candidates so curated words are never truncated away by "
        "--limit (repeatable).",
    )
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else _default_input_path()

    try:
        entries = load_en_ko_entries(input_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.min_length <= 0 or args.max_length <= 0 or args.min_length > args.max_length:
        print(
            "Error: --min-length and --max-length must be positive, with "
            "--min-length <= --max-length.",
            file=sys.stderr,
        )
        return 1

    candidates, skipped = extract_candidates(
        entries, args.min_length, args.max_length, args.include_verbs, args.include_nouns
    )
    if args.dedupe:
        candidates = dedupe_preserve_order(candidates)

    extra_words: list[str] = []
    for extra_path_str in args.extra_seed_file:
        try:
            extra_words.extend(load_extra_seed_words(Path(extra_path_str)))
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    if args.dedupe:
        extra_words = dedupe_preserve_order(extra_words)

    # Extra/curated seeds go first so --limit never truncates them away.
    combined = list(extra_words)
    seen = set(combined) if args.dedupe else None
    for candidate in candidates:
        if seen is not None:
            if candidate in seen:
                continue
            seen.add(candidate)
        combined.append(candidate)

    limited = combined[: args.limit] if args.limit > 0 else combined

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(f"{word}\n" for word in limited),
        encoding="utf-8",
    )

    print(f"Input: {input_path}")
    print(f"Input entries: {len(entries)}")
    print(f"Extracted candidates: {len(candidates)}")
    if extra_words:
        print(f"Extra seed words merged in: {len(extra_words)}")
    print(f"Combined before limit: {len(combined)}")
    print(f"Written seeds: {len(limited)}")
    print(f"Skipped entries: {skipped}")
    print(f"Output: {output_path}")
    print("Reminder: generated seed files are intentionally ignored by Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analyzer import analyzer  # noqa: E402
from app.krdict_reverse_service import (  # noqa: E402
    get_krdict_reverse_index,
    get_krdict_reverse_status,
)
from app.meaning_ranker import get_max_meaning_candidates, is_valid_korean_candidate  # noqa: E402


DEFAULT_SENTENCES = [
    "彼は立ち上がり、闇の中で声を聞いた。",
    "少女は小さく笑い、約束を思い出した。",
    "騎士は剣を握り、敵から王を守った。",
]


def _krdict_word_set() -> set[str]:
    index = get_krdict_reverse_index()
    words: set[str] = set()
    for candidates in index.values():
        words.update(candidates)
    return words


def audit_sentence(
    text: str, max_candidates: int, krdict_words: set[str]
) -> tuple[int, int, int, int, int]:
    print(f"文: {text}")
    tokens = analyzer.analyze(text)
    missing_count = 0
    over_limit_count = 0
    broken_count = 0
    krdict_hit_count = 0
    for token in tokens:
        meaning_ko = str(token.get("meaning_ko") or "")
        candidates = [part.strip() for part in meaning_ko.split(",") if part.strip()]
        broken_candidates = [c for c in candidates if not is_valid_korean_candidate(c)]
        krdict_hit = any(c in krdict_words for c in candidates)

        flags = []
        if not meaning_ko:
            missing_count += 1
            flags.append("missing meaning_ko")
        elif len(candidates) > max_candidates:
            over_limit_count += 1
            flags.append(f"too many candidates: {len(candidates)} > {max_candidates}")
        if broken_candidates:
            broken_count += 1
            flags.append(f"broken candidate: {broken_candidates}")
        if krdict_hit:
            krdict_hit_count += 1
            flags.append("krdict hit")
        flag_text = f"  [{'; '.join(flags)}]" if flags else ""

        print(
            f"  {token['surface']} ({token['base_form']}, {token['part_of_speech']}): "
            f"{meaning_ko or '-'} (candidates: {len(candidates)}){flag_text}"
        )
    print()
    return len(tokens), missing_count, over_limit_count, broken_count, krdict_hit_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit meaning_ko output for sample sentences: flags tokens with no "
            "meaning_ko and tokens whose meaning_ko has more candidates than the "
            "configured learner-facing limit."
        )
    )
    parser.add_argument(
        "--text",
        action="append",
        dest="texts",
        help="Sentence to audit. Can be passed multiple times. Defaults to a "
        "built-in sample set if omitted.",
    )
    args = parser.parse_args()

    max_candidates = get_max_meaning_candidates()
    print(f"meaning_ko candidate limit: {max_candidates}")

    krdict_status = get_krdict_reverse_status()
    print(
        "krdict reverse index: "
        f"source={krdict_status.get('source')} entries={krdict_status.get('entries')} "
        "(boosts/ranks en_ko fallback candidates only)"
    )
    print()

    krdict_words = _krdict_word_set()

    sentences = args.texts or DEFAULT_SENTENCES
    total_tokens = 0
    total_missing = 0
    total_over_limit = 0
    total_broken = 0
    total_krdict_hits = 0
    for sentence in sentences:
        token_count, missing_count, over_limit_count, broken_count, krdict_hit_count = audit_sentence(
            sentence, max_candidates, krdict_words
        )
        total_tokens += token_count
        total_missing += missing_count
        total_over_limit += over_limit_count
        total_broken += broken_count
        total_krdict_hits += krdict_hit_count

    print(
        "summary: "
        f"sentences={len(sentences)} tokens={total_tokens} "
        f"missing_meaning={total_missing} over_limit_meaning={total_over_limit} "
        f"broken_candidate={total_broken} krdict_hit={total_krdict_hits}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

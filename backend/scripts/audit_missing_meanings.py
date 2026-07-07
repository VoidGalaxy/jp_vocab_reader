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
from app.meaning_ranker import get_max_meaning_candidates  # noqa: E402


DEFAULT_SENTENCES = [
    "彼は立ち上がり、闇の中で声を聞いた。",
    "少女は小さく笑い、約束を思い出した。",
    "騎士は剣を握り、敵から王を守った。",
]


def audit_sentence(text: str, max_candidates: int) -> tuple[int, int, int]:
    print(f"文: {text}")
    tokens = analyzer.analyze(text)
    missing_count = 0
    over_limit_count = 0
    for token in tokens:
        meaning_ko = str(token.get("meaning_ko") or "")
        candidates = [part.strip() for part in meaning_ko.split(",") if part.strip()]
        flag = ""
        if not meaning_ko:
            missing_count += 1
            flag = "  [missing meaning_ko]"
        elif len(candidates) > max_candidates:
            over_limit_count += 1
            flag = f"  [too many candidates: {len(candidates)} > {max_candidates}]"
        print(
            f"  {token['surface']} ({token['base_form']}, {token['part_of_speech']}): "
            f"{meaning_ko or '-'}{flag}"
        )
    print()
    return len(tokens), missing_count, over_limit_count


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
    print()

    sentences = args.texts or DEFAULT_SENTENCES
    total_tokens = 0
    total_missing = 0
    total_over_limit = 0
    for sentence in sentences:
        token_count, missing_count, over_limit_count = audit_sentence(
            sentence, max_candidates
        )
        total_tokens += token_count
        total_missing += missing_count
        total_over_limit += over_limit_count

    print(
        "summary: "
        f"sentences={len(sentences)} tokens={total_tokens} "
        f"missing_meaning={total_missing} over_limit_meaning={total_over_limit}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

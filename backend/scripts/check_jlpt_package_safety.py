"""Local safety check for the 5 approved JLPT recommended-deck packages.

Guards `backend/data/jlpt/packages/jlpt_n{1..5}_recommended_deck.json` --
the only files in that directory allowed to be committed (see the
"Approved packages/ Exceptions" section in
.claude/skills/jp-vocab-release-manager/SKILL.md and the matching
`!backend/data/jlpt/packages/...` lines in .gitignore).

Checks, for each of the 5 files:
  - the file exists and is valid JSON
  - deck.name matches the expected "JLPT N{n} 추천 어휘" title
  - vocab_items count matches the last verified snapshot
  - custom_terms is empty (these are recommendation decks, not personal decks)
  - none of the known forbidden-copy phrases appear anywhere in the file
  - the file is NOT ignored by git (i.e. the .gitignore exception is still
    wired correctly) -- this only inspects `git check-ignore`, it never
    stages or commits anything

This never touches production, Neon, or `.env` -- it only reads local
files in backend/data/jlpt/packages/ and shells out to `git check-ignore`.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/check_jlpt_package_safety.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
PACKAGES_DIR = BACKEND_DIR / "data" / "jlpt" / "packages"

# Last verified snapshot (see docs/beta-release-checklist.md, Phase 14
# production transition record).
EXPECTED_PACKAGES: dict[str, dict[str, Any]] = {
    "jlpt_n1_recommended_deck.json": {"name": "JLPT N1 추천 어휘", "vocab_count": 3475},
    "jlpt_n2_recommended_deck.json": {"name": "JLPT N2 추천 어휘", "vocab_count": 1830},
    "jlpt_n3_recommended_deck.json": {"name": "JLPT N3 추천 어휘", "vocab_count": 1834},
    "jlpt_n4_recommended_deck.json": {"name": "JLPT N4 추천 어휘", "vocab_count": 640},
    "jlpt_n5_recommended_deck.json": {"name": "JLPT N5 추천 어휘", "vocab_count": 684},
}

FORBIDDEN_PHRASES = (
    "공식" + " JLPT",
    "official" + " JLPT",
    "원문 전체를" + " 저장합니다",
    "원문 전체를" + " 공유합니다",
    "복사된" + " 단어",
    "MEANING" + "_NEEDS" + "_REVIEW",
    "needs" + "_review",
)


def is_git_ignored(path: Path) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    return result.returncode == 0


def check_package(filename: str, expected: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    path = PACKAGES_DIR / filename

    if not path.is_file():
        return [f"{filename}: file not found at {path}"]

    raw_text = path.read_text(encoding="utf-8")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return [f"{filename}: invalid JSON ({exc})"]

    deck = data.get("deck") or {}
    name = deck.get("name")
    if name != expected["name"]:
        failures.append(
            f"{filename}: deck.name={name!r}, expected {expected['name']!r}"
        )

    vocab_items = data.get("vocab_items")
    count = len(vocab_items) if isinstance(vocab_items, list) else None
    if count != expected["vocab_count"]:
        failures.append(
            f"{filename}: vocab_items count={count!r}, "
            f"expected {expected['vocab_count']!r}"
        )

    custom_terms = data.get("custom_terms") or []
    if len(custom_terms) != 0:
        failures.append(
            f"{filename}: custom_terms has {len(custom_terms)} entries, expected 0"
        )

    for phrase in FORBIDDEN_PHRASES:
        if phrase in raw_text:
            failures.append(f"{filename}: forbidden phrase found: {phrase!r}")

    if is_git_ignored(path):
        failures.append(
            f"{filename}: git still treats this file as ignored -- the "
            f".gitignore exception is broken"
        )

    return failures


def main() -> int:
    print("JLPT package local safety check (no production/Neon/.env access)")
    print(f"packages dir: {PACKAGES_DIR}")
    print()

    all_failures: list[str] = []
    for filename, expected in EXPECTED_PACKAGES.items():
        failures = check_package(filename, expected)
        if failures:
            for failure in failures:
                print(f"[FAIL] {failure}")
            all_failures.extend(failures)
        else:
            print(
                f"[PASS] {filename}: name={expected['name']!r} "
                f"vocab_count={expected['vocab_count']} custom_terms=0 "
                f"no forbidden phrases, not git-ignored"
            )

    print()
    if all_failures:
        print(f"{len(all_failures)} check(s) failed.")
        return 1
    print("all checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

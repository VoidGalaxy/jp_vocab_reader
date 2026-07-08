from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import init_db  # noqa: E402
from app.repositories.deck_package_repository import import_deck_package  # noqa: E402
from app.repositories.deck_repository import list_decks  # noqa: E402
from app.repositories.shared_deck_repository import publish_deck  # noqa: E402
from app.repositories.user_repository import (  # noqa: E402
    get_dev_user_by_email,
    get_or_create_dev_user,
)
from app.schemas import DeckPackage  # noqa: E402


def load_package(input_path: Path) -> DeckPackage:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    # Validating through the real DeckPackage model doubles as the "is this
    # JSON compatible with deck package import" check.
    return DeckPackage(**raw)


def run_dry_run(package: DeckPackage, skip_publish: bool) -> int:
    print("[dry-run] no database changes will be made. Pass --apply to write.")
    dev_user = get_dev_user_by_email()
    if not dev_user:
        print("[dry-run] dev user does not exist yet -- would be created on --apply")
        return 0

    user_id = int(dev_user["id"])
    print(f"[dry-run] dev user id={user_id}")

    existing_names = {deck["name"] for deck in list_decks(user_id)}
    collision = (
        " (a deck with this name already exists for this user; import will "
        "auto-rename it)"
        if package.deck.name in existing_names
        else ""
    )
    print(
        f"[dry-run] would create personal deck '{package.deck.name}' with "
        f"{len(package.vocab_items)} vocab item(s){collision}"
    )
    if skip_publish:
        print("[dry-run] --skip-publish set; would not publish to shared decks")
    else:
        print(
            f"[dry-run] would publish it as a public shared deck titled "
            f"'{package.deck.name}'"
        )
    return 0


def run_apply(package: DeckPackage, skip_publish: bool) -> int:
    init_db()
    dev_user = get_or_create_dev_user()
    user_id = int(dev_user["id"])
    print(f"using dev user id={user_id}")

    import_result = import_deck_package(user_id, package)
    print(
        f"created personal deck '{import_result['deck_name']}' "
        f"(deck_id={import_result['deck_id']}), "
        f"imported {import_result['imported_vocab_count']} vocab item(s), "
        f"skipped {import_result['skipped_vocab_count']}"
    )

    if skip_publish:
        print("--skip-publish set; not publishing to shared decks")
        return 0

    publish_result = publish_deck(
        user_id,
        import_result["deck_id"],
        title=import_result["deck_name"],
        description=package.deck.description,
    )
    if not publish_result:
        print("failed to publish deck (deck not found after creation?)")
        return 1

    print(
        f"published shared deck '{publish_result['title']}' "
        f"(shared_deck_id={publish_result['shared_deck_id']}), "
        f"vocab_count={publish_result['vocab_count']}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Register a JLPT recommended-vocabulary deck package (built by "
            "build_jlpt_deck_package.py) as a personal deck, and optionally "
            "publish it as a public shared deck, for the dev/admin user. "
            "Defaults to a read-only dry run -- pass --apply to actually "
            "write to the database. This connects to whatever DATABASE_URL "
            "is configured (which may be a real deployed database), so "
            "review the dry-run output carefully before using --apply."
        )
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="Deck package JSON path"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to the database (default: dry run, read-only)",
    )
    parser.add_argument(
        "--skip-publish",
        action="store_true",
        help="Only create the personal deck; do not publish it as a shared deck",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"input file not found: {args.input}")
        return 1

    try:
        package = load_package(args.input)
    except Exception as exc:
        print(f"failed to parse deck package JSON: {exc}")
        return 1

    print(
        f"deck package: name={package.deck.name!r} "
        f"vocab_items={len(package.vocab_items)} "
        f"custom_terms={len(package.custom_terms)}"
    )

    if not args.apply:
        return run_dry_run(package, args.skip_publish)
    return run_apply(package, args.skip_publish)


if __name__ == "__main__":
    raise SystemExit(main())

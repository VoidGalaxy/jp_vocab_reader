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

from app.database import get_connection, init_db, now_iso  # noqa: E402
from app.jlpt_level_service import extract_jlpt_level_from_title  # noqa: E402
from app.repositories.deck_package_repository import import_deck_package  # noqa: E402
from app.repositories.deck_repository import list_decks  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    add_word_to_shared_deck,
    upsert_lexeme,
)
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


def find_shared_deck_by_title(connection, owner_user_id: int, title: str) -> int | None:
    row = connection.execute(
        """
        SELECT id FROM shared_decks
        WHERE owner_user_id = ? AND title = ? AND visibility = 'public'
        """,
        (owner_user_id, title),
    ).fetchone()
    return int(row["id"]) if row else None


def run_dry_run_lexeme(package: DeckPackage) -> int:
    print(
        "[dry-run] lexeme mode: no database changes will be made. "
        "Pass --apply to write."
    )
    print(
        f"[dry-run] would upsert {len(package.vocab_items)} lexeme(s) tagged "
        f"jlpt_level={extract_jlpt_level_from_title(package.deck.name)!r}"
    )
    print(
        f"[dry-run] would create/reuse a public shared deck titled "
        f"'{package.deck.name}' and link it to shared_deck_words "
        f"(no personal deck, no vocab_items copy, for any user)"
    )
    if package.custom_terms:
        print(
            f"[dry-run] NOTE: {len(package.custom_terms)} custom_term(s) in "
            "this package are NOT registered in lexeme mode yet (phase-2 TODO "
            "-- see docs/architecture/shared-lexeme-progress-storage.md)"
        )
    return 0


def run_apply_lexeme(package: DeckPackage) -> int:
    """Registers a JLPT recommended-vocabulary package straight into the new
    lexeme/shared_deck_words structure -- see
    docs/architecture/shared-lexeme-progress-storage.md. Unlike the legacy
    path (run_apply_legacy below), this never touches the dev user's
    personal decks/vocab_items: the word data is shared, one copy, and a
    user only ever gets a subscription row when they import it from the app.
    """
    init_db()
    dev_user = get_or_create_dev_user()
    owner_user_id = int(dev_user["id"])
    jlpt_level = extract_jlpt_level_from_title(package.deck.name)
    timestamp = now_iso()

    with get_connection() as connection:
        shared_deck_id = find_shared_deck_by_title(
            connection, owner_user_id, package.deck.name
        )
        if shared_deck_id is None:
            cursor = connection.execute(
                """
                INSERT INTO shared_decks (
                    owner_user_id, title, description, visibility,
                    vocab_count, custom_term_count, import_count,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, 'public', 0, 0, 0, ?, ?)
                """,
                (
                    owner_user_id,
                    package.deck.name,
                    package.deck.description or "",
                    timestamp,
                    timestamp,
                ),
            )
            shared_deck_id = int(cursor.lastrowid)
            print(f"created shared deck '{package.deck.name}' (shared_deck_id={shared_deck_id})")
        else:
            print(
                f"reusing existing shared deck '{package.deck.name}' "
                f"(shared_deck_id={shared_deck_id})"
            )

    registered = 0
    for sort_order, vocab_item in enumerate(package.vocab_items):
        base_form = (vocab_item.base_form or vocab_item.surface or "").strip()
        if not base_form:
            continue
        lexeme_id = upsert_lexeme(
            surface=vocab_item.surface or base_form,
            base_form=base_form,
            reading=vocab_item.reading,
            part_of_speech=vocab_item.part_of_speech,
            meaning_ko=vocab_item.meaning_ko,
            dictionary_gloss=vocab_item.dictionary_gloss,
            jlpt_level=jlpt_level,
            source_type="jlpt",
        )
        add_word_to_shared_deck(shared_deck_id, lexeme_id, sort_order)
        registered += 1

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE shared_decks
            SET vocab_count = ?, updated_at = ?
            WHERE id = ?
            """,
            (registered, now_iso(), shared_deck_id),
        )

    print(
        f"registered {registered} lexeme(s) into shared deck "
        f"(shared_deck_id={shared_deck_id}, jlpt_level={jlpt_level!r})"
    )
    if package.custom_terms:
        print(
            f"NOTE: {len(package.custom_terms)} custom_term(s) in this package "
            "were NOT registered (phase-2 TODO -- custom terms don't have a "
            "lexeme-mode equivalent yet)"
        )
    print("no personal deck was created and no user's vocab_items were touched.")
    return 0


def run_dry_run_legacy(package: DeckPackage, skip_publish: bool) -> int:
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


def run_apply_legacy(package: DeckPackage, skip_publish: bool) -> int:
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
        "--legacy",
        action="store_true",
        help=(
            "Use the old registration path: create a personal deck for the "
            "dev user (copying every word into vocab_items) and publish that "
            "as a shared deck (shared_deck_items). Default is the new "
            "lexeme/shared_deck_words structure, which registers the shared "
            "words once and touches no user's personal vocabulary -- see "
            "docs/architecture/shared-lexeme-progress-storage.md. Only use "
            "--legacy if you specifically need the old behavior."
        ),
    )
    parser.add_argument(
        "--skip-publish",
        action="store_true",
        help="Legacy mode only: only create the personal deck; do not publish it",
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

    if args.legacy:
        print("--legacy set: using the old personal-deck-copy + publish path")
        if not args.apply:
            return run_dry_run_legacy(package, args.skip_publish)
        return run_apply_legacy(package, args.skip_publish)

    if not args.apply:
        return run_dry_run_lexeme(package)
    return run_apply_lexeme(package)


if __name__ == "__main__":
    raise SystemExit(main())

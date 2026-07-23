"""Regression check for the Render/Neon production hotfix: PostgreSQL
rejects comparing a BOOLEAN column to an integer literal
(`psycopg.errors.UndefinedFunction: operator does not exist: boolean =
integer`), which SQLite silently tolerates (SQLite has no strict BOOLEAN
type -- it's stored as INTEGER there). `user_deck_subscriptions.is_active`
is the only BOOLEAN column in this schema (see app/database.py -- SQLite
declares it `INTEGER NOT NULL DEFAULT 1`, PostgreSQL declares it `BOOLEAN
NOT NULL DEFAULT TRUE`), so any raw-SQL comparison/assignment against it
using a bare `1`/`0` integer literal instead of `TRUE`/`FALSE` works on
SQLite but 500s on the real Neon PostgreSQL backend.

Two checks:

    1. Static: grep every app/repositories/*.py file for the exact
       boolean-integer literal patterns that caused the outage
       (`is_active = 1`, `is_active = 0`, `is_active=1`, `is_active=0`,
       and the same for `is_public`, in case that column is ever added) --
       fails loudly, naming the file:line, if any are found.
    2. Dynamic: exercises GET /shared-decks-equivalent repository calls
       (list_shared_decks(), get_or_create_subscription() reactivation
       path) against a disposable local SQLite DB to confirm the `TRUE`/
       `FALSE` literals this hotfix introduced still work correctly there
       too (SQLite accepts TRUE/FALSE as 1/0 aliases since 3.23), and that
       both a lexeme-mode and a legacy-mode shared deck are still returned
       correctly, with the right `mode`/`imported_at` reactivation
       behavior.

Never touches a real database -- only a throwaway SQLite file (never
backend/vocab.db, never whatever DATABASE_URL is already set in the
environment, never a remote/Neon database).

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/check_postgres_boolean_sql_compat.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Must happen before any `app.*` import -- see
# check_shared_deck_storage_regression.py for the same pattern/rationale.
_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_boolean_sql_compat_regression.db"
_SCRATCH_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"

from app.database import get_connection, init_db, now_iso  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    add_word_to_shared_deck,
    get_or_create_subscription,
    list_subscribed_shared_deck_ids,
    upsert_lexeme,
)
from app.repositories.shared_deck_repository import (  # noqa: E402
    import_shared_deck,
    list_shared_decks,
)

FAILURES: list[str] = []

# Boolean columns in this schema (see app/database.py). Extend this list if
# a future migration adds another BOOLEAN column.
BOOLEAN_COLUMNS = ["is_active", "is_public"]

# Matches "<column> = 1", "<column>=1", "<column> = 0", "<column>=0" -- the
# exact bare-integer-literal shape that breaks on PostgreSQL. Deliberately
# does NOT flag "= TRUE"/"= FALSE", "!= 1" on a non-boolean column, or
# unrelated numeric comparisons -- only this column name immediately
# followed by an integer boolean literal.
BOOLEAN_INT_LITERAL_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(col) for col in BOOLEAN_COLUMNS) + r")\s*=\s*[01]\b"
)


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def scan_for_boolean_int_literals() -> list[str]:
    repositories_dir = BACKEND_DIR / "app" / "repositories"
    offenses: list[str] = []
    for py_file in sorted(repositories_dir.glob("*.py")):
        text = py_file.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = BOOLEAN_INT_LITERAL_PATTERN.search(line)
            if match:
                offenses.append(f"{py_file.relative_to(BACKEND_DIR)}:{line_number}: {line.strip()}")
    return offenses


def create_user(email: str, display_name: str) -> int:
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (email, display_name, auth_provider, created_at, updated_at)
            VALUES (?, ?, 'local', ?, ?)
            """,
            (email, display_name, timestamp, timestamp),
        )
        return int(cursor.lastrowid)


def create_shared_deck(owner_user_id: int, title: str) -> int:
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO shared_decks (
                owner_user_id, title, description, visibility,
                vocab_count, custom_term_count, import_count, created_at, updated_at
            )
            VALUES (?, ?, '', 'public', 0, 0, 0, ?, ?)
            """,
            (owner_user_id, title, timestamp, timestamp),
        )
        return int(cursor.lastrowid)


def main() -> int:
    # --- 1. static check ------------------------------------------------------
    offenses = scan_for_boolean_int_literals()
    check(
        "no boolean-column-compared-to-integer-literal SQL remains in "
        "app/repositories/*.py",
        not offenses,
    )
    for offense in offenses:
        print(f"  found: {offense}")

    # --- 2. dynamic check -------------------------------------------------------
    print(f"using scratch db: {_SCRATCH_DB}")
    init_db()

    owner_id = create_user("boolcompat-owner@boolean-sql-compat.test", "BoolCompatOwner")
    importer_id = create_user("boolcompat-importer@boolean-sql-compat.test", "BoolCompatImporter")

    # A lexeme-mode deck (has shared_deck_words rows).
    lexeme_deck_id = create_shared_deck(owner_id, "Boolean 호환성 테스트 lexeme 덱")
    lexeme_id = upsert_lexeme(
        surface="불리언", base_form="불리언", reading="", part_of_speech="명사",
        meaning_ko="불리언 테스트",
    )
    add_word_to_shared_deck(lexeme_deck_id, lexeme_id, 0)
    with get_connection() as connection:
        connection.execute(
            "UPDATE shared_decks SET vocab_count = 1 WHERE id = ?", (lexeme_deck_id,)
        )

    # A legacy-mode deck (no shared_deck_words rows).
    legacy_deck_id = create_shared_deck(owner_id, "Boolean 호환성 테스트 legacy 덱")
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO shared_deck_items (
                shared_deck_id, surface, base_form, reading, part_of_speech,
                normalized_form, meaning_ko, dictionary_gloss,
                context_explanation_ko, example_sentence, quality_tag, created_at
            )
            VALUES (?, '레거시', '레거시', '', '명사', '레거시', '레거시 뜻', '', '', '', 'normal', ?)
            """,
            (legacy_deck_id, now_iso()),
        )
        connection.execute(
            "UPDATE shared_decks SET vocab_count = 1 WHERE id = ?", (legacy_deck_id,)
        )

    # GET /shared-decks-equivalent must succeed (this is exactly the query
    # that 500'd on Neon: the is_active = TRUE subquery inside
    # list_shared_decks()).
    try:
        decks_before_import = list_shared_decks(importer_id)
        check("list_shared_decks() runs without a SQL error", True)
    except Exception as exc:  # noqa: BLE001 -- want to report any SQL error here
        check(f"list_shared_decks() runs without a SQL error ({exc})", False)
        decks_before_import = []

    deck_ids_seen = {deck["id"] for deck in decks_before_import}
    check(
        "the lexeme-mode deck is returned by list_shared_decks()",
        lexeme_deck_id in deck_ids_seen,
    )
    check(
        "the legacy-mode deck is returned by list_shared_decks()",
        legacy_deck_id in deck_ids_seen,
    )
    modes_by_id = {deck["id"]: deck["mode"] for deck in decks_before_import}
    check(
        "lexeme-mode deck is tagged mode='subscribed'",
        modes_by_id.get(lexeme_deck_id) == "subscribed",
    )
    check(
        "legacy-mode deck is tagged mode='copied'",
        modes_by_id.get(legacy_deck_id) == "copied",
    )

    # Import (writes is_active = TRUE), then unsubscribe by hand and
    # re-import (exercises the "reactivate is_active = TRUE" UPDATE branch
    # of get_or_create_subscription(), the other half of this hotfix).
    imported = import_shared_deck(importer_id, lexeme_deck_id)
    check(
        "import_shared_deck() (INSERT ... is_active = TRUE) succeeds",
        imported is not None and imported.get("mode") == "subscribed",
    )
    check(
        "list_subscribed_shared_deck_ids() (WHERE is_active = TRUE) sees the "
        "new subscription",
        lexeme_deck_id in list_subscribed_shared_deck_ids(importer_id),
    )

    with get_connection() as connection:
        connection.execute(
            "UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ? AND shared_deck_id = ?",
            (importer_id, lexeme_deck_id),
        )
    check(
        "unsubscribing (is_active = FALSE) removes it from the subscribed set",
        lexeme_deck_id not in list_subscribed_shared_deck_ids(importer_id),
    )

    _subscription, created_again = get_or_create_subscription(importer_id, lexeme_deck_id)
    check(
        "get_or_create_subscription() reactivation (UPDATE ... is_active = TRUE) "
        "does not error and does not report as newly created",
        created_again is False,
    )
    check(
        "reactivated subscription is subscribed again",
        lexeme_deck_id in list_subscribed_shared_deck_ids(importer_id),
    )

    decks_after_import = list_shared_decks(importer_id)
    imported_at_by_id = {deck["id"]: deck["imported_at"] for deck in decks_after_import}
    check(
        "list_shared_decks() reflects imported_at for the reactivated subscription",
        imported_at_by_id.get(lexeme_deck_id) is not None,
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED:")
        for label in FAILURES:
            print(f"  - {label}")
        return 1
    print("PostgreSQL boolean SQL compatibility regression passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

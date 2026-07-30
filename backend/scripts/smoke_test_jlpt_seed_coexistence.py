"""Smoke test for the Phase 12 "A then B" JLPT deck transition strategy.

Round 1 found that the live production N1-N5 shared decks are titled
"N{level}어휘모음" (legacy copy-mode, shared_deck_items), while the local
seed package title is "JLPT N{level} 추천 어휘". Because
find_shared_deck_by_title() in seed_jlpt_shared_decks.py matches on an exact
title string, running the current --apply lexeme path against production is
expected to create a brand new shared_decks row rather than reuse/overwrite
the existing legacy one (option A), never an in-place conversion (option C).

This script reproduces that shape entirely on a disposable local SQLite
scratch DB and proves, end to end:

1. A legacy copied-mode deck (simulating the real "N1어휘모음" production
   row) and a newly seeded lexeme-mode deck (title "JLPT N1 추천 어휘") can
   coexist as two separate shared_decks rows, each reporting its own correct
   `mode` ("copied" vs "subscribed") via list_shared_decks()/get_shared_deck().
2. Importing the new lexeme deck is subscription-only (no vocab_items bulk
   copy, no personal deck row) -- contrasted against importing the legacy
   deck, which still copies into vocab_items/decks exactly as before.
3. Soft-unpublishing the legacy deck (delete_shared_deck()) never deletes
   its row or shared_deck_items rows, never touches an existing subscriber's
   personal decks/vocab_items, and makes a brand-new (logged-out) caller's
   list_shared_decks() show only the lexeme deck -- i.e. "create A, then
   soft-unpublish B" hides the old deck from new users without breaking
   anyone already on it.

Never touches production/Neon data. Forces a throwaway SQLite DATABASE_URL
before importing any app module, refuses to run if that URL ever points at
neon.tech, and deletes the scratch DB plus sidecars in a finally block. Only
uses a tiny (2-3 word) fixture package -- never the real N1-N5 data files.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1
    python scripts/smoke_test_jlpt_seed_coexistence.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Must happen before any `app.*` import touches app.settings/app.database.
_SCRATCH_DB = (
    Path(tempfile.gettempdir()) / "jp_vocab_reader_smoke_test_jlpt_coexistence.db"
)
_SCRATCH_DB.unlink(missing_ok=True)
_DATABASE_URL = f"sqlite:///{_SCRATCH_DB.as_posix()}"
os.environ["DATABASE_URL"] = _DATABASE_URL

if "neon.tech" in _DATABASE_URL.lower() or not _DATABASE_URL.startswith("sqlite:"):
    raise SystemExit(
        "refusing to run: DATABASE_URL is not a safe local sqlite scratch "
        f"file: {_DATABASE_URL}"
    )

from app.database import get_connection, init_db, now_iso  # noqa: E402
from app.repositories.deck_repository import list_decks  # noqa: E402
from app.repositories.lexeme_repository import is_lexeme_deck  # noqa: E402
from app.repositories.shared_deck_repository import (  # noqa: E402
    delete_shared_deck,
    get_shared_deck,
    import_shared_deck,
    list_shared_decks,
)
from app.repositories.vocab_repository import list_vocab_items  # noqa: E402

import seed_jlpt_shared_decks  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


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


def create_legacy_copied_deck(owner_user_id: int) -> int:
    """Simulates the real production 'N1어휘모음' row: a shared_decks row
    with only shared_deck_items rows (no shared_deck_words) -- legacy
    copy-mode, exactly like the deck Phase 11's live API check found.
    """
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO shared_decks (
                owner_user_id, title, description, visibility,
                vocab_count, custom_term_count, import_count,
                created_at, updated_at
            )
            VALUES (?, ?, ?, 'public', ?, 0, 0, ?, ?)
            """,
            (
                owner_user_id,
                "N1어휘모음",
                "production-shape legacy fixture, not a real JLPT deck",
                3,
                timestamp,
                timestamp,
            ),
        )
        shared_deck_id = int(cursor.lastrowid)

        legacy_words = [
            ("見る", "見る", "みる", "動詞", "보다"),
            ("食べる", "食べる", "たべる", "動詞", "먹다"),
            ("本", "本", "ほん", "名詞", "책"),
        ]
        for surface, base_form, reading, part_of_speech, meaning_ko in legacy_words:
            connection.execute(
                """
                INSERT INTO shared_deck_items (
                    shared_deck_id, surface, base_form, reading, part_of_speech,
                    normalized_form, meaning_ko, dictionary_gloss,
                    context_explanation_ko, example_sentence, quality_tag,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, '', '', '', 'normal', ?)
                """,
                (
                    shared_deck_id,
                    surface,
                    base_form,
                    reading,
                    part_of_speech,
                    base_form,
                    meaning_ko,
                    timestamp,
                ),
            )
    return shared_deck_id


def write_fixture_package(tmp_dir: Path) -> Path:
    package = {
        "package_type": "deck_package",
        "package_version": 1,
        "deck": {
            "name": "JLPT N1 추천 어휘",
            "description": "coexistence smoke fixture, not a real JLPT deck",
        },
        "vocab_items": [
            {
                "surface": "読む",
                "base_form": "読む",
                "reading": "よむ",
                "part_of_speech": "動詞",
                "meaning_ko": "읽다",
            },
            {
                "surface": "書く",
                "base_form": "書く",
                "reading": "かく",
                "part_of_speech": "動詞",
                "meaning_ko": "쓰다",
            },
        ],
        "custom_terms": [],
    }
    path = tmp_dir / "smoke_jlpt_coexistence_fixture.json"
    path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    print(f"using scratch db: {_SCRATCH_DB}")
    tmp_dir = Path(tempfile.mkdtemp(prefix="jp_vocab_reader_smoke_jlpt_coexistence_"))

    try:
        init_db()

        # --- Step 2: reproduce the live production legacy deck locally ---
        owner_user_id = create_user("owner@smoke.test", "Owner")
        legacy_deck_id = create_legacy_copied_deck(owner_user_id)

        check(
            "1. legacy deck has no shared_deck_words rows",
            not is_lexeme_deck(legacy_deck_id),
        )
        anon_decks_before = {d["id"]: d for d in list_shared_decks(user_id=None)}
        check(
            "2. legacy deck reports mode='copied' via list_shared_decks()",
            anon_decks_before.get(legacy_deck_id, {}).get("mode") == "copied",
        )

        # --- Step 3: seed the new lexeme-mode deck via the real seed script ---
        fixture_path = write_fixture_package(tmp_dir)
        package = seed_jlpt_shared_decks.load_package(fixture_path)
        exit_code = seed_jlpt_shared_decks.run_apply_lexeme(package)
        check("3. seed script's run_apply_lexeme() exits 0", exit_code == 0)

        with get_connection() as connection:
            lexeme_deck_row = connection.execute(
                "SELECT id FROM shared_decks WHERE title = ?",
                (package.deck.name,),
            ).fetchone()
        check("4. a new shared_decks row was created for the lexeme deck", lexeme_deck_row is not None)
        lexeme_deck_id = int(lexeme_deck_row["id"])

        check(
            "5. the new lexeme deck got a different id than the legacy deck",
            lexeme_deck_id != legacy_deck_id,
        )
        check(
            "6. the lexeme deck reports mode='subscribed'",
            is_lexeme_deck(lexeme_deck_id),
        )

        # legacy row must survive untouched by the seed run
        with get_connection() as connection:
            legacy_row_after_seed = connection.execute(
                """
                SELECT title, visibility FROM shared_decks WHERE id = ?
                """,
                (legacy_deck_id,),
            ).fetchone()
            legacy_items_after_seed = connection.execute(
                "SELECT COUNT(*) AS n FROM shared_deck_items WHERE shared_deck_id = ?",
                (legacy_deck_id,),
            ).fetchone()
        check(
            "7. legacy deck's title is unchanged ('N1어휘모음')",
            legacy_row_after_seed is not None and legacy_row_after_seed["title"] == "N1어휘모음",
        )
        check(
            "8. legacy deck's shared_deck_items rows are still intact (3)",
            legacy_items_after_seed is not None and int(legacy_items_after_seed["n"]) == 3,
        )

        # --- Step 4: coexistence via list_shared_decks() ---
        anon_decks_after_seed = {d["id"]: d for d in list_shared_decks(user_id=None)}
        check(
            "9. both decks appear in list_shared_decks() for an anonymous caller",
            legacy_deck_id in anon_decks_after_seed and lexeme_deck_id in anon_decks_after_seed,
        )
        check(
            "10. legacy deck still mode='copied' after the new deck exists",
            anon_decks_after_seed.get(legacy_deck_id, {}).get("mode") == "copied",
        )
        check(
            "11. lexeme deck is mode='subscribed'",
            anon_decks_after_seed.get(lexeme_deck_id, {}).get("mode") == "subscribed",
        )

        legacy_detail = get_shared_deck(legacy_deck_id, user_id=None)
        lexeme_detail = get_shared_deck(lexeme_deck_id, user_id=None)
        check(
            "12. legacy deck detail is served from shared_deck_items (custom_terms == [])",
            legacy_detail is not None and legacy_detail["mode"] == "copied"
            and len(legacy_detail["items"]) == 3,
        )
        check(
            "13. lexeme deck detail is served from shared_deck_words (2 items)",
            lexeme_detail is not None and lexeme_detail["mode"] == "subscribed"
            and len(lexeme_detail["items"]) == 2,
        )

        # --- Step 5: import the new lexeme deck -- subscription only ---
        lexeme_subscriber_id = create_user("lexeme-subscriber@smoke.test", "LexemeSubscriber")
        vocab_before_lexeme_import = len(list_vocab_items(lexeme_subscriber_id))
        decks_before_lexeme_import = len(list_decks(lexeme_subscriber_id))

        lexeme_import_result = import_shared_deck(lexeme_subscriber_id, lexeme_deck_id)
        check(
            "14. lexeme import returns mode='subscribed'",
            isinstance(lexeme_import_result, dict) and lexeme_import_result.get("mode") == "subscribed",
        )
        with get_connection() as connection:
            subscription_row = connection.execute(
                """
                SELECT 1 FROM user_deck_subscriptions
                WHERE user_id = ? AND shared_deck_id = ? AND is_active = TRUE
                """,
                (lexeme_subscriber_id, lexeme_deck_id),
            ).fetchone()
        check("15. a user_deck_subscriptions row was created", subscription_row is not None)

        vocab_after_lexeme_import = len(list_vocab_items(lexeme_subscriber_id))
        decks_after_lexeme_import = len(list_decks(lexeme_subscriber_id))
        check(
            "16. lexeme subscriber's vocab_items count is unchanged (no bulk copy)",
            vocab_after_lexeme_import == vocab_before_lexeme_import,
        )
        check(
            "17. no personal deck was created for the lexeme subscriber",
            decks_after_lexeme_import == decks_before_lexeme_import,
        )

        # --- Step 6: contrast against importing the legacy deck ---
        legacy_subscriber_id = create_user("legacy-subscriber@smoke.test", "LegacySubscriber")
        vocab_before_legacy_import = len(list_vocab_items(legacy_subscriber_id))
        decks_before_legacy_import = len(list_decks(legacy_subscriber_id))

        legacy_import_result = import_shared_deck(legacy_subscriber_id, legacy_deck_id)
        check(
            "18. legacy import returns mode='copied'",
            isinstance(legacy_import_result, dict) and legacy_import_result.get("mode") == "copied",
        )
        vocab_after_legacy_import = len(list_vocab_items(legacy_subscriber_id))
        decks_after_legacy_import = len(list_decks(legacy_subscriber_id))
        check(
            "19. legacy subscriber's vocab_items count increased by 3 (bulk copy still happens)",
            vocab_after_legacy_import == vocab_before_legacy_import + 3,
        )
        check(
            "20. a personal deck was created for the legacy subscriber",
            decks_after_legacy_import == decks_before_legacy_import + 1,
        )

        # --- Step 7: soft-unpublish the legacy deck (the "B" half of A-then-B) ---
        unpublish_result = delete_shared_deck(owner_user_id, legacy_deck_id)
        check(
            "21. delete_shared_deck() succeeds for the legacy deck's owner",
            isinstance(unpublish_result, dict),
        )
        with get_connection() as connection:
            legacy_row_after_unpublish = connection.execute(
                "SELECT visibility FROM shared_decks WHERE id = ?",
                (legacy_deck_id,),
            ).fetchone()
            legacy_items_after_unpublish = connection.execute(
                "SELECT COUNT(*) AS n FROM shared_deck_items WHERE shared_deck_id = ?",
                (legacy_deck_id,),
            ).fetchone()
        check(
            "22. legacy deck's visibility flipped to 'unpublished' (row not deleted)",
            legacy_row_after_unpublish is not None
            and legacy_row_after_unpublish["visibility"] == "unpublished",
        )
        check(
            "23. legacy deck's shared_deck_items rows still exist after unpublish",
            legacy_items_after_unpublish is not None and int(legacy_items_after_unpublish["n"]) == 3,
        )

        # the already-imported legacy subscriber's personal deck/vocab must survive
        vocab_after_unpublish = len(list_vocab_items(legacy_subscriber_id))
        decks_after_unpublish = len(list_decks(legacy_subscriber_id))
        check(
            "24. legacy subscriber's personal vocab_items count is unaffected by unpublish",
            vocab_after_unpublish == vocab_after_legacy_import,
        )
        check(
            "25. legacy subscriber's personal deck count is unaffected by unpublish",
            decks_after_unpublish == decks_after_legacy_import,
        )

        # a brand-new (logged-out) caller must now see only the lexeme deck
        anon_decks_after_unpublish = {d["id"]: d for d in list_shared_decks(user_id=None)}
        check(
            "26. a brand-new caller no longer sees the unpublished legacy deck",
            legacy_deck_id not in anon_decks_after_unpublish,
        )
        check(
            "27. a brand-new caller still sees the lexeme deck",
            lexeme_deck_id in anon_decks_after_unpublish,
        )

        new_user_id = create_user("brand-new-user@smoke.test", "BrandNewUser")
        new_user_decks = {d["id"]: d for d in list_shared_decks(user_id=new_user_id)}
        check(
            "28. a brand-new logged-in user also no longer sees the unpublished legacy deck",
            legacy_deck_id not in new_user_decks,
        )
        check(
            "29. a brand-new logged-in user still sees the lexeme deck as mode='subscribed'",
            new_user_decks.get(lexeme_deck_id, {}).get("mode") == "subscribed",
        )

        # Known pre-existing scope gap (found by this smoke, not introduced by
        # it): list_shared_decks()/get_shared_deck()'s post-unpublish
        # visibility widening (app/repositories/shared_deck_repository.py) only
        # checks owner_user_id and an active user_deck_subscriptions row --
        # it never checks shared_deck_imports. A legacy-mode importer only
        # ever gets a shared_deck_imports row (see _import_shared_deck_legacy()
        # above), never a user_deck_subscriptions row, so once the owner
        # unpublishes a legacy deck, an existing legacy subscriber's own
        # shared-deck bookshelf list drops it too -- exactly like a brand-new
        # user. This does NOT affect their personal vocab_items/decks copy
        # (checks 24/25 above already proved those survive untouched) -- only
        # the shared-deck-listing entry pointing back at the origin disappears
        # for them. The "owner/subscriber keep seeing the unpublished deck"
        # policy documented in docs/architecture/shared-lexeme-progress-storage.md
        # ("Owner unpublish policy") was implemented and regression-tested only
        # for lexeme-mode subscriptions; this smoke shows it was never extended
        # to legacy shared_deck_imports rows. Recorded here as a Round 3
        # documentation/runbook candidate, not fixed in this round (backend
        # code changes are out of scope for Round 2).
        legacy_subscriber_decks = {
            d["id"]: d for d in list_shared_decks(user_id=legacy_subscriber_id)
        }
        check(
            "30. known gap: legacy deck's existing subscriber does NOT keep seeing it "
            "in their own list after unpublish (unlike a lexeme-mode subscriber)",
            legacy_deck_id not in legacy_subscriber_decks,
        )

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(str(_SCRATCH_DB) + suffix).unlink(missing_ok=True)
        print(f"cleaned up scratch db + sidecars: {_SCRATCH_DB}*")

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("\nall checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase-2 smoke test: shared-deck learning UI integration.

Exercises the actual HTTP endpoints (via FastAPI's TestClient, no real
network/port) the frontend now calls, against a throwaway local SQLite file
-- never backend/vocab.db, never whatever DATABASE_URL is already set in the
environment. See docs/architecture/shared-lexeme-progress-storage.md.

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/smoke_test_shared_deck_learning_ui.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Must happen before any `app.*` import touches app.settings/app.database --
# see smoke_test_shared_lexeme_progress.py for the same pattern/rationale.
_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_smoke_test_phase2.db"
_SCRATCH_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_module  # noqa: E402
from app.database import get_connection, now_iso  # noqa: E402
from app.repositories.lexeme_repository import upsert_lexeme  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


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


def add_lexeme_word(shared_deck_id: int, sort_order: int, **lexeme_kwargs) -> int:
    lexeme_id = upsert_lexeme(**lexeme_kwargs)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO shared_deck_words (shared_deck_id, lexeme_id, sort_order, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (shared_deck_id, lexeme_id, sort_order, now_iso()),
        )
    return lexeme_id


def count_rows(table: str, where: str = "1=1", params: tuple = ()) -> int:
    with get_connection() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", params
        ).fetchone()
    return int(row["c"])


def main() -> int:
    print(f"using scratch db: {_SCRATCH_DB}")

    with TestClient(main_module.app) as client:
        # No Authorization header on any request below -- every call falls
        # back to the shared dev user (see app/auth.py
        # get_current_user_optional_or_dev), same as the local frontend.

        # --- seed one lexeme-mode deck (owned by whatever the dev user's id
        # turns out to be, via /me) --------------------------------------
        me = client.get("/me").json()
        dev_user_id = me["id"]
        shared_deck_id = create_shared_deck(dev_user_id, "JLPT 추천 어휘 N5 (phase2 스모크)")
        lexeme_ids = [
            add_lexeme_word(
                shared_deck_id, i,
                surface=w, base_form=w, reading=r, part_of_speech="명사",
                meaning_ko=m, jlpt_level="N5", source_type="jlpt",
            )
            for i, (w, r, m) in enumerate(
                [("闇", "やみ", "어둠"), ("約束", "やくそく", "약속"), ("騎士", "きし", "기사")]
            )
        ]
        with get_connection() as connection:
            connection.execute(
                "UPDATE shared_decks SET vocab_count = 3 WHERE id = ?", (shared_deck_id,)
            )

        # --- 1. shared deck list -------------------------------------------
        resp = client.get("/shared-decks")
        check("1. GET /shared-decks succeeds", resp.status_code == 200)
        decks = resp.json()
        deck_summary = next((d for d in decks if d["id"] == shared_deck_id), None)
        check("1b. seeded deck appears in the list", deck_summary is not None)
        check(
            "1c. list response tags it mode='subscribed' before import",
            deck_summary is not None and deck_summary.get("mode") == "subscribed",
        )
        check(
            "1d. not yet imported (imported_at is null)",
            deck_summary is not None and deck_summary.get("imported_at") is None,
        )

        vocab_items_before = count_rows("vocab_items", "user_id = ?", (dev_user_id,))

        # --- 2. import ------------------------------------------------------
        resp = client.post(f"/shared-decks/{shared_deck_id}/import")
        check("2. import succeeds", resp.status_code == 200)
        import_result = resp.json()
        check("2b. import mode is 'subscribed'", import_result.get("mode") == "subscribed")
        check(
            "2c. import message does not use copy-tone wording",
            "복사" not in import_result.get("message", ""),
        )
        check(
            "2d. personal vocab_items count did not grow from import",
            count_rows("vocab_items", "user_id = ?", (dev_user_id,)) == vocab_items_before,
        )

        # --- 3. re-import (idempotent) ---------------------------------------
        resp = client.post(f"/shared-decks/{shared_deck_id}/import")
        check("3. re-import succeeds (not an error)", resp.status_code == 200)
        check(
            "3b. re-import still reports subscribed mode",
            resp.json().get("mode") == "subscribed",
        )
        check(
            "3c. still exactly one subscription row (no duplicate)",
            count_rows(
                "user_deck_subscriptions", "user_id = ? AND shared_deck_id = ?",
                (dev_user_id, shared_deck_id),
            )
            == 1,
        )

        # --- 4. "open" the deck (detail/word list) ---------------------------
        resp = client.get(f"/shared-decks/{shared_deck_id}")
        check("4. deck detail (open) succeeds", resp.status_code == 200)
        detail = resp.json()
        check("4b. detail reports mode='subscribed'", detail.get("mode") == "subscribed")
        check("4c. imported_at is now set", detail.get("imported_at") is not None)
        check("4d. all 3 words are present", len(detail.get("items", [])) == 3)
        check(
            "4e. words with no progress default to unclassified/level 0",
            all(
                item.get("status") == "unclassified" and item.get("review_level") == 0
                for item in detail["items"]
            ),
        )

        # --- 5. status change -------------------------------------------------
        target_lexeme_id = lexeme_ids[0]
        resp = client.patch(
            f"/shared-decks/{shared_deck_id}/words/{target_lexeme_id}/progress",
            json={"status": "known"},
        )
        check("5. status update succeeds", resp.status_code == 200)
        check("5b. returned status is 'known'", resp.json().get("status") == "known")
        check(
            "5c. exactly one user_word_progress row now exists",
            count_rows("user_word_progress", "user_id = ?", (dev_user_id,)) == 1,
        )

        # invalid status should be rejected, not silently accepted
        resp = client.patch(
            f"/shared-decks/{shared_deck_id}/words/{target_lexeme_id}/progress",
            json={"status": "not_a_real_status"},
        )
        check("5d. invalid status is rejected (400)", resp.status_code == 400)

        # --- 6. refresh -> status persists ------------------------------------
        resp = client.get(f"/shared-decks/{shared_deck_id}")
        detail_after = resp.json()
        changed_item = next(
            item for item in detail_after["items"] if item["lexeme_id"] == target_lexeme_id
        )
        check("6. status persists after re-fetching the deck", changed_item["status"] == "known")
        other_items_untouched = all(
            item["status"] == "unclassified"
            for item in detail_after["items"]
            if item["lexeme_id"] != target_lexeme_id
        )
        check("6b. other words in the deck are untouched", other_items_untouched)

        # --- 7. existing personal vocabulary endpoints still work -------------
        resp = client.post(
            "/vocab-items",
            json={"surface": "読む", "base_form": "読む", "reading": "よむ", "meaning_ko": "읽다"},
        )
        check("7. POST /vocab-items (personal) still works", resp.status_code == 200)
        resp = client.get("/vocab-items")
        check("7b. GET /vocab-items (personal) still works", resp.status_code == 200)
        check(
            "7c. the personal item just created is in the list",
            any(item["surface"] == "読む" for item in resp.json()["items"]),
        )

        # --- 8. review/stats endpoints stay error-free ------------------------
        resp = client.get("/study-items")
        check("8. GET /study-items has no error", resp.status_code == 200)
        resp = client.get("/stats")
        check("8b. GET /stats has no error", resp.status_code == 200)

        # --- lexeme review rating path (bonus, section 7's minimum) -----------
        review_lexeme_id = lexeme_ids[1]
        resp = client.post(
            f"/shared-decks/{shared_deck_id}/words/{review_lexeme_id}/review",
            json={"rating": "good"},
        )
        check("9. lexeme review rating succeeds", resp.status_code == 200)
        check("9b. review_level advanced past 0", resp.json().get("review_level", 0) > 0)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED:")
        for label in FAILURES:
            print(f"  - {label}")
        return 1
    print("all checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

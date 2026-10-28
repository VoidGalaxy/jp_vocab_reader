"""Characterize the existing scheduler without touching product data.

Run with backend/.venv/Scripts/python.exe from the repository root.
Assertions document current behavior, including undesirable policies;
passing does not mean those policies are good learning design.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timedelta, timezone


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="qa_srs_audit_", dir=ROOT / "backend") as temporary:
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(temporary).as_posix()}/audit.db"
        os.environ["APP_ENV"] = "development"
        from app.database import compute_review_schedule, get_connection, init_db, now_iso
        from app.repositories.learning_plan_repository import get_plan_progress
        from app.repositories.lexeme_repository import (
            add_word_to_shared_deck,
            get_subscribed_lexeme_stats_summary,
            list_subscribed_lexeme_study_items,
            record_lexeme_review,
            upsert_lexeme,
        )
        from app.repositories.shared_deck_repository import import_shared_deck
        from app.repositories.vocab_repository import (
            create_or_update_vocab_item,
            list_study_items,
            record_review,
        )
        from app.schemas import VocabItemCreate

        checks = 0

        def check(label: str, condition: bool) -> None:
            nonlocal checks
            assert condition, label
            checks += 1
            print(f"PASS {checks}: {label}")

        at = datetime(2026, 10, 8, tzinfo=timezone.utc)
        for rating, expected_level, minutes in [
            ("again", 0, 5), ("hard", 1, 15),
            ("good", 1, 15), ("easy", 2, 30),
        ]:
            level, due = compute_review_schedule(rating, 0, at)
            check(f"initial {rating}: level={level}, interval={minutes}m",
                  level == expected_level and datetime.fromisoformat(due) - at == timedelta(minutes=minutes))
        level, due = compute_review_schedule("again", 10, at)
        check("mature again resets to level 0 / 5m",
              level == 0 and datetime.fromisoformat(due) - at == timedelta(minutes=5))
        level, due = compute_review_schedule("hard", 10, at)
        check("mature hard steps back to level 9 / 30d",
              level == 9 and datetime.fromisoformat(due) - at == timedelta(days=30))
        level, due = compute_review_schedule("good", 99, at)
        check("upper interval capped at 90d; level keeps increasing",
              level == 100 and datetime.fromisoformat(due) - at == timedelta(days=90))

        init_db()
        stamp = now_iso()
        with get_connection() as connection:
            user = int(connection.execute(
                "INSERT INTO users (email, display_name, auth_provider, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("audit@srs.test", "Audit", "local", stamp, stamp),
            ).lastrowid)
            publisher = int(connection.execute(
                "INSERT INTO users (email, display_name, auth_provider, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("publisher@srs.test", "Publisher", "local", stamp, stamp),
            ).lastrowid)
        personal, _ = create_or_update_vocab_item(user, VocabItemCreate(base_form="audit-personal", status="unknown"))
        check("never-reviewed personal unknown enters today's queue",
              personal["id"] in {item["id"] for item in list_study_items(user)})
        record_review(user, personal["id"], "good")
        with get_connection() as connection:
            connection.execute("UPDATE vocab_items SET status='known', next_review_at=? WHERE id=?", ("2000-01-01T00:00:00+00:00", personal["id"]))
        check("overdue personal known is excluded from today's queue",
              personal["id"] not in {item["id"] for item in list_study_items(user)})

        with get_connection() as connection:
            shared = int(connection.execute(
                "INSERT INTO shared_decks (owner_user_id, title, description, visibility, vocab_count, custom_term_count, import_count, created_at, updated_at) VALUES (?, ?, '', 'public', 2, 0, 0, ?, ?)",
                (publisher, "Audit deck", stamp, stamp),
            ).lastrowid)
        again_word = upsert_lexeme("audit-again", "audit-again")
        easy_word = upsert_lexeme("audit-easy", "audit-easy")
        add_word_to_shared_deck(shared, again_word, 0)
        add_word_to_shared_deck(shared, easy_word, 1)
        import_shared_deck(user, shared)
        check("never-reviewed subscribed words are new, not due",
              len(list_subscribed_lexeme_study_items(user, shared, first_review_only=True)) == 2
              and not list_subscribed_lexeme_study_items(user, shared, due_only=True))
        record_lexeme_review(user, again_word, "again", shared)
        check("first again counts as seen in learning plan",
              get_plan_progress(user, "subscribed", shared)["seen"] == 1)
        check("first again still contributes to subscribed stats new_count",
              get_subscribed_lexeme_stats_summary(user)["new_count"] == 2)
        check("first-review queue excludes the already-rated again word",
              [word["lexeme_id"] for word in list_subscribed_lexeme_study_items(user, shared, first_review_only=True)] == [easy_word])
        easy_progress = record_lexeme_review(user, easy_word, "easy", shared)
        with get_connection() as connection:
            connection.execute("UPDATE user_word_progress SET next_review_at=? WHERE user_id=? AND lexeme_id=?", ("2000-01-01T00:00:00+00:00", user, easy_word))
        check("initial unclassified easy becomes known and stays out of overdue queue",
              easy_progress["status"] == "known"
              and easy_word not in {word["lexeme_id"] for word in list_subscribed_lexeme_study_items(user, shared, due_only=True)})
        check("both actual ratings count as seen, not mastery",
              get_plan_progress(user, "subscribed", shared)["seen"] == 2)
        print(f"Characterization checks passed: {checks}; temporary SQLite removed on exit.")


if __name__ == "__main__":
    main()

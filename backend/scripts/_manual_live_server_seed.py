"""One-off helper: seed a lexeme-mode shared deck + a test user into whichever
DATABASE_URL is set in this process's environment, for a manual live-server
smoke test. Not part of the test suite -- delete after use.
"""
from __future__ import annotations

import os
import sys

assert os.environ.get("DATABASE_URL", "").startswith("sqlite:///"), "refusing: DATABASE_URL is not local sqlite"
assert "neon.tech" not in os.environ.get("DATABASE_URL", ""), "refusing: DATABASE_URL points to Neon"

from app.database import ensure_schema, get_connection, now_iso
from app.repositories.lexeme_repository import add_word_to_shared_deck, upsert_lexeme
from app.auth_repository import create_user

ensure_schema()

email = "manual_live_test@example.com"
password = "testpass123"
try:
    user = create_user(email=email, password=password, display_name="Manual Live Test")
    print("created user", user["id"])
except Exception as exc:  # already exists from a prior run
    print("user create skipped:", exc)

with get_connection() as connection:
    cursor = connection.execute(
        """
        INSERT INTO shared_decks (owner_user_id, title, description, created_at, updated_at)
        SELECT id, 'Manual Live Test Deck', 'seeded for live-server smoke test', ?, ?
        FROM users WHERE email = ?
        """,
        (now_iso(), now_iso(), email),
    )
    deck_id = cursor.lastrowid

lex1 = upsert_lexeme(surface="食べる", base_form="食べる", reading="たべる", part_of_speech="verb", meaning_ko="먹다", jlpt_level="N5")
lex2 = upsert_lexeme(surface="飲む", base_form="飲む", reading="のむ", part_of_speech="verb", meaning_ko="마시다", jlpt_level="N5")
add_word_to_shared_deck(deck_id, lex1, 0)
add_word_to_shared_deck(deck_id, lex2, 1)

print("shared_deck_id", deck_id, "lexeme_ids", lex1, lex2)

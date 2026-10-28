"""Gate E-5b synthetic accounts, built through the app's own repositories and SRS paths on
whatever database the caller's environment points at (a session SQLite file, or the
protected local PG through the E-1/E-2 harness). Synthetic content only.

Account T (the one to delete) has a row in every account-owned table: decks, cards, a
custom term, personal legacy + FSRS logs, a receipt, settings, a migration run with its
snapshot, a card-deletion ledger row, an identity flag, an evidence restart, a subscription
to O's shared deck with progress and a subscribed log, an import of that deck, and a
meaning feedback, a released P-RB write block and its closed recovery record. T owns no
shared deck and has no app feedback (those block deletion).
Account O (another account) has its own deck, card, review, shared deck (owner) and run.
"""

from __future__ import annotations

from app.database import get_connection, now_iso
from app.repositories import (custom_term_repository as terms, deck_repository as decks,
                              feedback_repository as feedback, lexeme_repository as lexemes,
                              shared_deck_repository as shared, user_repository as users,
                              vocab_repository as vocab)
from app.schemas import CustomTermCreate, DeckCreate, VocabItemCreate

ALL_TABLES = (
    "users", "decks", "vocab_items", "custom_terms", "review_logs", "lexeme_review_logs", "lexemes",
    "shared_decks", "shared_deck_items", "shared_deck_terms", "shared_deck_words", "shared_deck_imports",
    "user_deck_subscriptions", "user_word_progress", "meaning_feedback", "app_feedback",
    "srs_config_versions", "srs_user_settings", "srs_review_receipts", "srs_migration_runs",
    "srs_migration_snapshots", "srs_card_deletions", "srs_card_identity_flags", "srs_evidence_restarts",
    "account_write_blocks", "account_recovery_runs",
)


def sql(query, params=()):
    with get_connection() as c:
        cursor = c.execute(query, params)
        return [dict(r) for r in cursor.fetchall()] if cursor.description else []


def set_mode(user, mode):
    stamp = now_iso()
    sql("DELETE FROM srs_user_settings WHERE user_id = ?", (user,))
    sql("INSERT INTO srs_user_settings (user_id, srs_mode, daily_new_goal, settings_version, created_at, updated_at) "
        "VALUES (?, ?, 20, 0, ?, ?)", (user, mode, stamp, stamp))


def card(user, deck, name):
    return vocab.create_or_update_vocab_item(user, VocabItemCreate(
        surface=name, base_form=name, reading=f"{name}-r", meaning_ko=f"{name}-뜻", deck_id=deck))[0]["id"]


class Accounts:
    def __init__(self, tag="e5b"):
        from app.srs import identity, migration
        from app.srs.engine import CardKey

        self.T = users.create_user(f"target-{tag}@e5b.example.test", "target", "synthetic")["id"]
        self.O = users.create_user(f"other-{tag}@e5b.example.test", "other", "synthetic")["id"]
        # O: own deck, card, a shared deck it owns (with words), a review
        self.o_deck = decks.create_deck(self.O, DeckCreate(name="o-deck"))[0]["id"]
        self.o_card = card(self.O, self.o_deck, "o-word")
        vocab.record_review(self.O, self.o_card, "good")
        self.o_shared = shared.publish_deck(self.O, self.o_deck, "o-shared", "")["shared_deck_id"]
        self.lexeme = lexemes.upsert_lexeme("e5b-lexeme", "e5b-lexeme")
        lexemes.add_word_to_shared_deck(self.o_shared, self.lexeme, 5)
        # T: legacy history -> migration run + snapshot (FSRS after)
        set_mode(self.T, "legacy")
        self.deck = decks.create_deck(self.T, DeckCreate(name="t-deck"))[0]["id"]
        self.m1 = card(self.T, self.deck, "t-migrated")
        vocab.record_review(self.T, self.m1, "good")
        vocab.record_review(self.T, self.m1, "good")
        set_mode(self.T, "fsrs")
        plan = migration.dry_run([CardKey("personal", self.T, self.m1)])
        migration.apply_plan(plan, f"e5b-run-{tag}", approved=True)
        # T: FSRS review with a request id -> receipt; a term; a deleted card -> ledger
        self.c2 = card(self.T, self.deck, "t-fresh")
        vocab.record_review(self.T, self.c2, "good", request_id=f"e5b-req-{tag}", expected_card_version=0,
                            session_id="e5b")
        self.term = terms.create_custom_term(self.T, CustomTermCreate(term="t-term", deck_id=self.deck))[0]["id"]
        gone = card(self.T, self.deck, "t-gone")
        vocab.delete_vocab_item(self.T, gone)
        # T: identity flag on its own card; evidence restart pointing at its own snapshot
        with get_connection() as c:
            identity.flag_identity_unknown(c, [identity.IdentityFinding(self.T, self.c2, ["e5b_synthetic"])])
        snap = sql("SELECT id FROM srs_migration_snapshots WHERE user_id = ?", (self.T,))[0]["id"]
        m1_logs = [r["id"] for r in sql("SELECT id FROM review_logs WHERE vocab_item_id = ? ORDER BY id", (self.m1,))]
        # both boundaries are the account's own logs of that card, as the plan-B writer stores them
        sql("INSERT INTO srs_evidence_restarts (user_id, card_kind, card_ref, source_snapshot_id, previous_boundary, "
            "new_boundary, card_version_before, created_at) VALUES (?, 'personal', ?, ?, ?, ?, 0, ?)",
            (self.T, self.m1, snap, m1_logs[0], m1_logs[-1], now_iso()))
        # T: subscribed to O's shared deck, progress + subscribed log, import, meaning feedback
        lexemes.get_or_create_subscription(self.T, self.o_shared)
        lexemes.update_word_status(self.T, self.lexeme, "known")
        lexemes.record_lexeme_review(self.T, self.lexeme, "good", self.o_shared)
        shared.import_shared_deck(self.T, self.o_shared)
        # an old-style (item) shared deck of O, imported by T: a personal copy + an import row
        stamp = now_iso()
        self.o_legacy = sql("INSERT INTO shared_decks (owner_user_id, title, description, created_at, updated_at) "
                            "VALUES (?, 'o-legacy', '', ?, ?) RETURNING id", (self.O, stamp, stamp))[0]["id"]
        sql("INSERT INTO shared_deck_items (shared_deck_id, surface, base_form, reading, part_of_speech, "
            "normalized_form, meaning_ko, dictionary_gloss, context_explanation_ko, example_sentence, quality_tag, "
            "created_at) VALUES (?, 'o-item', 'o-item', 'o', '', 'o-item', 'o-뜻', '', '', '', 'normal', ?)",
            (self.o_legacy, stamp))
        shared.import_shared_deck(self.T, self.o_legacy)
        feedback.create_meaning_feedback(user_id=self.T, vocabulary_id=self.c2, surface="t", base_form="t",
                                         reading="", current_meaning_ko="", suggested_meaning_ko="", reason="e5b",
                                         source="test")
        # P-RB: a RELEASED write block (history row; an active one would hold the deletion)
        from app import account_blocks
        token = f"e5b-synthetic-recovery-token-{tag}-0123456789abcdef"
        account_blocks.set_block(self.T, f"e5b-recovery-{tag}", token)
        account_blocks.release_block(self.T, f"e5b-recovery-{tag}", token, "precheck_unrecoverable")
        # ...and a CLOSED recovery record of that block (history; synthetic hashes only)
        block_id = sql("SELECT id FROM account_write_blocks WHERE recovery_key = ?", (f"e5b-recovery-{tag}",))[0]["id"]
        stamp = now_iso()
        sql("INSERT INTO account_recovery_runs (user_id, block_id, recovery_key, plan_fingerprint, state, "
            "active_user_id, source_runs_json, baseline_json, prepared_at, closed_at, close_reason) VALUES "
            "(?, ?, ?, ?, 'closed', NULL, '[]', '{}', ?, ?, 'precheck_unrecoverable')",
            (self.T, block_id, f"e5b-recovery-{tag}", "0" * 64, stamp, stamp))

    # ---- observations ----------------------------------------------------------------
    @staticmethod
    def state():
        with get_connection() as c:
            return {t: [dict(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()] for t in ALL_TABLES}

    def rows_of(self, user, state=None):
        """Every row of `user`, by table (owner column or, for runs, scope owner)."""
        import json

        state = state or self.state()
        out = {}
        for table, rows in state.items():
            if table == "users":
                out[table] = [r for r in rows if r["id"] == user]
            elif table == "shared_decks":
                out[table] = [r for r in rows if r["owner_user_id"] == user]
            elif table == "srs_migration_runs":
                out[table] = [r for r in rows if json.loads(r["scope_json"]).get("user_id") == user]
            elif rows and "user_id" in rows[0]:
                out[table] = [r for r in rows if r["user_id"] == user]
        return out

    def shared_and_global(self, state=None):
        state = state or self.state()
        return {t: state[t] for t in ("lexemes", "shared_decks", "shared_deck_items", "shared_deck_terms",
                                      "shared_deck_words", "srs_config_versions")}

    def everything_but(self, user, state=None):
        """All rows not belonging to `user` (the other account, the dev account, global rows)."""
        state = state or self.state()
        mine = self.rows_of(user, state)
        return {t: [r for r in rows if r not in mine.get(t, [])] for t, rows in state.items()}

    def count_of(self, user):
        return {t: len(rows) for t, rows in self.rows_of(user).items()}

    @staticmethod
    def add_app_feedback(user):
        feedback.create_app_feedback(user_id=user, category="bug", message="e5b", screen="test", path="/test")

    @staticmethod
    def own_shared_deck(user, deck, *, unpublish=False, subscriber=None):
        result = shared.publish_deck(user, deck, "t-shared", "")
        if subscriber is not None:
            lexemes.get_or_create_subscription(subscriber, result["shared_deck_id"])
        if unpublish:
            shared.delete_shared_deck(user, result["shared_deck_id"])
        return result["shared_deck_id"]

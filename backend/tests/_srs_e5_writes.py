"""Synthetic inputs shared by SQLite and protected local-PG E-5a checks."""

from app.database import get_connection, now_iso
from app.repositories import (custom_term_repository as terms, deck_repository as decks,
                              deck_package_repository as packages, feedback_repository as feedback,
                              lexeme_repository as lexemes, shared_deck_repository as shared,
                              user_repository as users, vocab_repository as vocab)
from app.schemas import (CustomTermCreate, CustomTermUpdate, DeckCreate, DeckUpdate,
                         DeckPackage, VocabItemCreate, VocabItemUpdate)


def sql(query, params=()):
    with get_connection() as c:
        cursor = c.execute(query, params)
        return [dict(r) for r in cursor.fetchall()] if cursor.description else []


class Writes:
    def __init__(self):
        self.user = users.create_user("writer@e5.example.test", "writer", "synthetic")["id"]
        self.other = users.create_user("other@e5.example.test", "other", "synthetic")["id"]
        self.deck = decks.create_deck(self.user, DeckCreate(name="e5-source"))[0]["id"]
        self.card = vocab.create_or_update_vocab_item(self.user, VocabItemCreate(
            surface="e5-existing", base_form="e5-existing", deck_id=self.deck))[0]["id"]
        self.term = terms.create_custom_term(self.user, CustomTermCreate(term="e5-term", deck_id=self.deck))[0]["id"]
        self.lexeme = lexemes.upsert_lexeme("e5-shared", "e5-shared")
        self.shared = self.make_shared(self.other, "e5-public")
        lexemes.add_word_to_shared_deck(self.shared, self.lexeme, 0)
        self.legacy_shared = self.make_shared(self.other, "e5-legacy")
        self.own_shared = self.make_shared(self.user, "e5-owned")
        self.package = DeckPackage(package_type="jp_vocab_reader_deck", package_version=1,
                                   deck={"name": "e5-package"}, vocab_items=[{"surface": "e5-package-word"}])

    @staticmethod
    def make_shared(owner, title):
        return sql("INSERT INTO shared_decks (owner_user_id, title, created_at, updated_at) "
                   "VALUES (?, ?, ?, ?) RETURNING id", (owner, title, now_iso(), now_iso()))[0]["id"]

    def operations(self):
        u = self.user
        return {
            "vocab_create": lambda: vocab.create_or_update_vocab_item(u, VocabItemCreate(surface="e5-new")),
            "vocab_update": lambda: vocab.update_vocab_item(u, self.card, VocabItemUpdate(meaning_ko="e5-edit")),
            "context_update": lambda: vocab.update_context_explanation(u, self.card, "e5-context"),
            "vocab_delete": lambda: vocab.delete_vocab_item(u, self.card),
            "personal_review": lambda: vocab.record_review(u, self.card, "good"),
            "deck_default": lambda: decks.get_or_create_default_deck_id(u),
            "deck_create": lambda: decks.create_deck(u, DeckCreate(name="e5-new-deck")),
            "deck_update": lambda: decks.update_deck(u, self.deck, DeckUpdate(name="e5-renamed")),
            "deck_delete": lambda: decks.delete_deck_with_items(u, self.deck),
            "term_create": lambda: terms.create_custom_term(u, CustomTermCreate(term="e5-new-term")),
            "term_update": lambda: terms.update_custom_term(u, self.term, CustomTermUpdate(meaning_ko="e5-edit")),
            "term_delete": lambda: terms.delete_custom_term(u, self.term),
            "package_import": lambda: packages.import_deck_package(u, self.package),
            "publish": lambda: shared.publish_deck(u, self.deck, "e5-published", ""),
            "unpublish": lambda: shared.delete_shared_deck(u, self.own_shared),
            "republish": lambda: shared.republish_shared_deck(u, self.own_shared),
            "subscription": lambda: lexemes.get_or_create_subscription(u, self.shared),
            "shared_import": lambda: shared.import_shared_deck(u, self.shared),
            "legacy_import": lambda: shared.import_shared_deck(u, self.legacy_shared),
            "progress": lambda: lexemes.update_word_status(u, self.lexeme, "known"),
            "lexeme_review": lambda: lexemes.record_lexeme_review(u, self.lexeme, "good", self.shared),
            "meaning_feedback": lambda: feedback.create_meaning_feedback(
                user_id=u, vocabulary_id=None, surface="e5", base_form="e5", reading="",
                current_meaning_ko="", suggested_meaning_ko="", reason="e5", source="test"),
            "app_feedback": lambda: feedback.create_app_feedback(
                user_id=u, category="bug", message="e5-feedback", screen="test", path="/test"),
        }

    def erase_account_for_test(self):
        """Not the product deletion policy. Existing data is left for no-write assertions."""
        sql("DELETE FROM users WHERE id = ?", (self.user,))

    def erase_all_for_test(self):
        """Synthetic race fixture only, NOT the approved operator deletion procedure."""
        from app.account_write import begin_account_write
        from _srs_e5_preflight import OWNED_TABLES
        with get_connection() as c:
            begin_account_write(c, self.user)
            for table in ("shared_deck_items", "shared_deck_terms", "shared_deck_words"):
                c.execute(f"DELETE FROM {table} WHERE shared_deck_id IN "
                          "(SELECT id FROM shared_decks WHERE owner_user_id = ?)", (self.user,))
            c.execute("DELETE FROM shared_decks WHERE owner_user_id = ?", (self.user,))
            for table in OWNED_TABLES:
                c.execute(f"DELETE FROM {table} WHERE user_id = ?", (self.user,))
            c.execute("DELETE FROM users WHERE id = ?", (self.user,))
        return "deleted"

    def assert_absent(self, case):
        from _srs_e5_preflight import OWNED_TABLES
        with get_connection(read_only=True) as c:
            for table in OWNED_TABLES:
                case.assertEqual(c.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id = ?",
                                           (self.user,)).fetchone()["n"], 0, table)
            case.assertIsNone(c.execute("SELECT id FROM users WHERE id = ?", (self.user,)).fetchone())
            case.assertIsNone(c.execute("SELECT id FROM shared_decks WHERE owner_user_id = ?", (self.user,)).fetchone())

    @staticmethod
    def state():
        from _srs_e5_preflight import EXPECTED_TABLES
        with get_connection(read_only=True) as c:
            return {table: [dict(r) for r in c.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
                    for table in sorted(EXPECTED_TABLES)}

"""FSRS-based SRS building blocks (Gate B-1).

Nothing in this package is wired into the review API, the study queue or
app startup yet. The runtime keeps using the legacy fixed-level scheduler in
app.database until a later gate switches an account explicitly.

- engine.py: pure adapter around the pinned `fsrs` library.
- completion.py: the '학습 완료' (meaning-completion) evaluation draft.
- schema.py: additive SRS columns/tables for SQLite and PostgreSQL.

See docs/plans/srs-improvement/ (APPROVAL_2026-10-09.md, gate-a/DECISIONS.md).
"""

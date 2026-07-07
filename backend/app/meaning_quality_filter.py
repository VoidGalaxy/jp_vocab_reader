from __future__ import annotations

import re

from app.meaning_ranker import is_valid_korean_candidate


# --- Risky English glosses -------------------------------------------------
# Glosses this broad match almost any noun in a bilingual dictionary (e.g.
# JMdict's "先" can gloss as "point"/"tip"/"end"), so a Korean candidate
# sourced from one of these alone is weak evidence of the actual meaning.
RISKY_ENGLISH_GLOSSES = {
    "point",
    "tip",
    "thing",
    "one",
    "part",
    "place",
    "way",
    "matter",
    "case",
    "time",
    "side",
    "line",
    "form",
    "mark",
    "sign",
    "piece",
    "object",
}

_ARTICLE_PREFIX_RE = re.compile(r"^(a|an|the)\s+")


def is_risky_gloss(gloss: str) -> bool:
    normalized = " ".join((gloss or "").strip().lower().split())
    normalized = _ARTICLE_PREFIX_RE.sub("", normalized)
    return normalized in RISKY_ENGLISH_GLOSSES


# --- Risky Korean candidates ------------------------------------------------
# Overly generic/ambiguous Korean words that tend to surface as mistranslated
# noise from the risky glosses above. Demoted, not hard-removed, since some
# are occasionally the genuinely correct meaning.
RISKY_KOREAN_CANDIDATES = {
    "포인트",
    "팁",
    "점",
    "것",
    "수",
    "때",
    "곳",
    "부분",
    "경우",
    "문제",
    "정",
    "문신",
    "끌",
    "형태",
    "라인",
    "사이드",
    "오브젝트",
}


def is_risky_korean(candidate: str) -> bool:
    return " ".join((candidate or "").strip().split()) in RISKY_KOREAN_CANDIDATES


# --- Candidate scoring -------------------------------------------------------
# Rough 0-100 scale. Candidates scoring below CONFIDENCE_THRESHOLD are
# dropped entirely -- an empty meaning_ko is preferred over a low-confidence
# guess.
KAIKKI_BASE_SCORE = 55.0
KRDICT_ONLY_BASE_SCORE = 30.0
GLOSS_RANK_PENALTY = 3.0
# Capped rather than left to grow linearly forever: some JMdict entries
# interleave dozens of languages/senses under one headword, so a legitimate
# sense (e.g. "front"/"before" for 先) can sit at gloss_rank 25+ purely
# because of unrelated language noise ahead of it, not because it is less
# relevant. An uncapped penalty would zero out every candidate from such a
# sense regardless of how good it otherwise is.
MAX_GLOSS_RANK_PENALTY = 24.0
KRDICT_OVERLAP_BOOST = 15.0
RISKY_GLOSS_PENALTY = 35.0
RISKY_KOREAN_PENALTY = 45.0
VERB_FIT_BOOST = 8.0
VERB_FIT_PENALTY = 12.0
LENGTH_PENALTY = 6.0
# 1-4 characters, excluding spaces. Many perfectly ordinary Korean words are
# a single syllable (앞, 끝, 왕, 빛, 검, ...); only unusually long candidates
# (long garbled phrases, not short common words) are penalized.
IDEAL_LENGTH_RANGE = range(1, 5)

CONFIDENCE_THRESHOLD = 20.0


def score_candidate(
    word: str,
    *,
    gloss_rank: int,
    gloss_risky: bool,
    krdict_confirmed: bool,
    krdict_only: bool,
    prefer_verb_form: bool = False,
) -> float | None:
    """Score one Korean candidate word. Returns None if the candidate must be
    hard-excluded (broken/archaic text, or a KRDIC-only candidate sourced
    from a risky gloss)."""
    cleaned = " ".join((word or "").strip().split())
    if not cleaned or not is_valid_korean_candidate(cleaned):
        return None
    if gloss_risky and krdict_only:
        # KRDIC is a validator, not a generator: it may not introduce a
        # brand-new candidate on the strength of a risky gloss alone.
        return None

    risky_korean = is_risky_korean(cleaned)

    score = KRDICT_ONLY_BASE_SCORE if krdict_only else KAIKKI_BASE_SCORE
    score -= min(gloss_rank * GLOSS_RANK_PENALTY, MAX_GLOSS_RANK_PENALTY)

    if krdict_confirmed and not krdict_only and not risky_korean:
        score += KRDICT_OVERLAP_BOOST

    if gloss_risky:
        score -= RISKY_GLOSS_PENALTY
    if risky_korean:
        score -= RISKY_KOREAN_PENALTY

    if prefer_verb_form:
        score += VERB_FIT_BOOST if cleaned.endswith("다") else -VERB_FIT_PENALTY

    length = len(cleaned.replace(" ", ""))
    if length not in IDEAL_LENGTH_RANGE:
        score -= LENGTH_PENALTY

    return score


# --- Token-level guardrail ---------------------------------------------------
# A single hiragana character tagged as an interjection/conjunction/adnominal
# affix (or with no reliable POS at all) is almost always a discourse
# filler/particle-like token in running text (e.g. "え"), not a content word
# worth guessing a Korean meaning for.
SUPPRESS_SHORT_TOKEN_POS = {
    "感動詞",  # interjection
    "接続詞",  # conjunction
    "連体詞",  # adnominal
    "接頭辞",  # prefix
    "接尾辞",  # suffix
    "",  # uncertain/unknown POS
}

_SINGLE_HIRAGANA_RE = re.compile(r"^[぀-ゟ]$")


def should_suppress_short_token(surface: str, part_of_speech: str) -> bool:
    if not _SINGLE_HIRAGANA_RE.match(surface or ""):
        return False
    return part_of_speech in SUPPRESS_SHORT_TOKEN_POS

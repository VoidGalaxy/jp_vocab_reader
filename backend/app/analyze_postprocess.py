from __future__ import annotations

import re
from typing import Any

from app.analyzer import find_example_sentence, split_sentences
from app.dictionary_service import lookup_dictionary_gloss, lookup_meaning


BASIC_EXCLUDED_BASE_FORMS = {
    "する",
    "ある",
    "いる",
    "なる",
    "こと",
    "もの",
    "これ",
    "それ",
    "あれ",
    "ここ",
    "そこ",
    "どこ",
    "私",
    "僕",
    "俺",
    "彼",
    "彼女",
    "何",
    "誰",
}
GENERAL_PRONOUNS = {"これ", "それ", "あれ", "ここ", "そこ", "どこ", "私", "僕", "俺", "彼", "彼女", "何", "誰"}

COMPOUND_VERBS = [
    ("立ち上がる", "たちあがる", r"立ち上が(?:る|った|り|って|ら(?:ない|なかった|れる|れた)|れば|ろう)"),
    ("差し出す", "さしだす", r"差し出(?:す|した|し|して|さ(?:ない|なかった|れる|れた)|せば|そう)"),
    ("見上げる", "みあげる", r"見上げ(?:る|た|て|ない|なかった|られる|られた|れば|よう)"),
    ("振り返る", "ふりかえる", r"振り返(?:る|った|り|って|ら(?:ない|なかった|れる|れた)|れば|ろう)"),
    ("取り戻す", "とりもどす", r"取り戻(?:す|した|し|して|さ(?:ない|なかった|れる|れた)|せば|そう)"),
    ("受け取る", "うけとる", r"受け取(?:る|った|り|って|ら(?:ない|なかった|れる|れた)|れば|ろう)"),
    ("思い出す", "おもいだす", r"思い出(?:す|した|し|して|さ(?:ない|なかった|れる|れた)|せば|そう)"),
    ("言い出す", "いいだす", r"言い出(?:す|した|し|して|さ(?:ない|なかった|れる|れた)|せば|そう)"),
    ("歩き出す", "あるきだす", r"歩き出(?:す|した|し|して|さ(?:ない|なかった|れる|れた)|せば|そう)"),
    ("駆け出す", "かけだす", r"駆け出(?:す|した|し|して|さ(?:ない|なかった|れる|れた)|せば|そう)"),
    ("目を覚ます", "めをさます", r"目を覚(?:ます|ました|まし|まして|まさ(?:ない|なかった|れる|れた)|ませば|まそう)"),
    ("息を呑む", "いきをのむ", r"息を呑(?:む|んだ|み|んで|ま(?:ない|なかった|れる|れた)|めば|もう)"),
]


def ranges_overlap(
    first_start: int, first_end: int, second_start: int, second_end: int
) -> bool:
    return first_start < second_end and second_start < first_end


def katakana_to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(char) - 0x60) if "ァ" <= char <= "ン" else char for char in text
    )


def improve_analysis_tokens(
    *,
    text: str,
    raw_tokens: list[dict[str, Any]],
    tokens: list[dict[str, Any]],
    deck_id: int | None,
) -> list[dict[str, Any]]:
    sentences = split_sentences(text)
    normalized_tokens = [normalize_quality_tag(token) for token in tokens]
    custom_ranges = [
        (token.get("_start", -1), token.get("_end", -1))
        for token in normalized_tokens
        if token.get("quality_tag") == "custom_term"
    ]

    compound_tokens = find_compound_verb_tokens(
        text=text,
        sentences=sentences,
        custom_ranges=custom_ranges,
        deck_id=deck_id,
    )
    compound_ranges = [
        (token.get("_start", -1), token.get("_end", -1)) for token in compound_tokens
    ]

    filtered_tokens = []
    for token in normalized_tokens:
        if token.get("quality_tag") == "custom_term":
            filtered_tokens.append(token)
            continue
        if is_basic_excluded_token(token):
            continue
        token_start = token.get("_start", -1)
        token_end = token.get("_end", -1)
        if token_start != -1 and any(
            ranges_overlap(token_start, token_end, start, end)
            for start, end in compound_ranges
        ):
            continue
        filtered_tokens.append(token)

    noun_phrase_tokens = find_noun_phrase_candidates(
        raw_tokens=raw_tokens,
        sentences=sentences,
        custom_ranges=custom_ranges,
        occupied_ranges=compound_ranges,
        deck_id=deck_id,
    )

    combined = [*filtered_tokens, *compound_tokens, *noun_phrase_tokens]
    return dedupe_and_sort_tokens(combined)


def normalize_quality_tag(token: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(token)
    if normalized.get("is_custom_term"):
        normalized["quality_tag"] = "custom_term"
    else:
        normalized["quality_tag"] = normalized.get("quality_tag") or "normal"
    return normalized


def is_basic_excluded_token(token: dict[str, Any]) -> bool:
    return (
        (token.get("base_form") in BASIC_EXCLUDED_BASE_FORMS)
        or (token.get("surface") in BASIC_EXCLUDED_BASE_FORMS)
    )


def find_compound_verb_tokens(
    *,
    text: str,
    sentences: list[tuple[int, int, str]],
    custom_ranges: list[tuple[int, int]],
    deck_id: int | None,
) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    occupied_ranges: list[tuple[int, int]] = []
    for base_form, reading, pattern in COMPOUND_VERBS:
        for match in re.finditer(pattern, text):
            start, end = match.span()
            if any(ranges_overlap(start, end, custom_start, custom_end) for custom_start, custom_end in custom_ranges):
                continue
            if any(ranges_overlap(start, end, occupied_start, occupied_end) for occupied_start, occupied_end in occupied_ranges):
                continue
            occupied_ranges.append((start, end))
            surface = match.group(0)
            tokens.append(
                {
                    "surface": surface,
                    "base_form": base_form,
                    "reading": reading,
                    "part_of_speech": "동사",
                    "normalized_form": base_form,
                    "meaning_ko": lookup_meaning(
                        surface=surface,
                        base_form=base_form,
                        normalized_form=base_form,
                        reading=reading,
                        deck_id=deck_id,
                        part_of_speech="動詞",
                    ),
                    "dictionary_gloss": lookup_dictionary_gloss(
                        surface=surface,
                        base_form=base_form,
                        normalized_form=base_form,
                        reading=reading,
                        deck_id=deck_id,
                    ),
                    "example_sentence": find_example_sentence(sentences, start),
                    "is_custom_term": False,
                    "quality_tag": "compound_verb",
                    "_start": start,
                    "_end": end,
                }
            )
    return sorted(tokens, key=lambda token: token.get("_start", 0))


def find_noun_phrase_candidates(
    *,
    raw_tokens: list[dict[str, Any]],
    sentences: list[tuple[int, int, str]],
    custom_ranges: list[tuple[int, int]],
    occupied_ranges: list[tuple[int, int]],
    deck_id: int | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index in range(len(raw_tokens) - 2):
        first, particle, second = raw_tokens[index : index + 3]
        if first.get("part_of_speech") != "名詞" or second.get("part_of_speech") != "名詞":
            continue
        if particle.get("surface") != "の":
            continue

        start = int(first.get("start", -1))
        end = int(second.get("end", -1))
        surface = f"{first.get('surface', '')}の{second.get('surface', '')}"
        if start == -1 or end == -1:
            continue
        if not is_valid_noun_phrase(surface, first, second):
            continue
        if any(ranges_overlap(start, end, custom_start, custom_end) for custom_start, custom_end in custom_ranges):
            continue
        if any(ranges_overlap(start, end, occupied_start, occupied_end) for occupied_start, occupied_end in occupied_ranges):
            continue

        reading = "".join(
            katakana_to_hiragana(str(token.get("reading", "")))
            for token in (first, particle, second)
        )
        # A bare "noun + の + noun" combination is only worth surfacing as
        # its own candidate if the *phrase itself* has an independent
        # dictionary meaning (custom term, built-in dictionary, or a real
        # JMdict headword) -- not just because its two parts happen to be
        # adjacent nouns. Without that, it is noise once the components
        # (e.g. 自分, 身) already appear as their own tokens.
        meaning_ko = lookup_meaning(
            surface=surface,
            base_form=surface,
            normalized_form=surface,
            reading=reading,
            deck_id=deck_id,
            part_of_speech="名詞",
        )
        if not meaning_ko:
            continue

        candidates.append(
            {
                "surface": surface,
                "base_form": surface,
                "reading": reading,
                "part_of_speech": "명사구",
                "normalized_form": surface,
                "meaning_ko": meaning_ko,
                "dictionary_gloss": lookup_dictionary_gloss(
                    surface=surface,
                    base_form=surface,
                    normalized_form=surface,
                    reading=reading,
                    deck_id=deck_id,
                ),
                "example_sentence": find_example_sentence(sentences, start),
                "is_custom_term": False,
                "quality_tag": "known_phrase",
                "_start": start,
                "_end": end,
            }
        )
    return candidates


def is_valid_noun_phrase(
    surface: str, first: dict[str, Any], second: dict[str, Any]
) -> bool:
    if len(surface) < 4:
        return False
    if re.fullmatch(r"[\d\W_]+", surface):
        return False
    first_base = str(first.get("base_form") or first.get("surface") or "")
    second_base = str(second.get("base_form") or second.get("surface") or "")
    if first_base in GENERAL_PRONOUNS and second_base in GENERAL_PRONOUNS:
        return False
    return True


def dedupe_and_sort_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {
        "custom_term": 0,
        "compound_verb": 1,
        "known_phrase": 2,
        "noun_phrase_candidate": 2,
        "normal": 3,
    }
    sorted_tokens = sorted(
        tokens,
        key=lambda token: (
            token.get("_start", 0),
            priority.get(str(token.get("quality_tag", "normal")), 9),
            -(token.get("_end", 0) - token.get("_start", 0)),
        ),
    )
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for token in sorted_tokens:
        key = (
            str(token.get("base_form", "")),
            str(token.get("reading", "")),
            str(token.get("quality_tag", "normal")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(token)
    return deduped

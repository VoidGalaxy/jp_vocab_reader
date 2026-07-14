from app.dictionary import get_korean_meaning
from app.en_ko_dictionary_service import translate_glosses_to_korean
from app.gloss_ko_mapper import map_glosses_to_korean
from app.jmdict_service import lookup_jmdict_gloss
from app.meaning_quality_filter import is_usable_custom_meaning, should_suppress_short_token
from app.meaning_ranker import build_meaning_ko


VERB_POS_TAGS = {"動詞", "동사"}


def lookup_meaning(
    *,
    surface: str,
    base_form: str,
    normalized_form: str,
    reading: str,
    deck_id: int | None,
    custom_meaning_ko: str | None = None,
    part_of_speech: str = "",
) -> str:
    custom_meaning = (custom_meaning_ko or "").strip()
    if custom_meaning and is_usable_custom_meaning(custom_meaning):
        return custom_meaning

    for key in (base_form, normalized_form, surface):
        meaning = get_korean_meaning((key or "").strip())
        if meaning:
            return build_meaning_ko(meaning.split(","))

    # A single hiragana interjection/conjunction/adnominal/affix (or a token
    # with no reliable POS at all) is almost always a discourse filler in
    # running text (e.g. "え"), not a content word -- don't guess a Kaikki/
    # KRDIC-derived meaning for it.
    if should_suppress_short_token(surface, part_of_speech):
        return ""

    dictionary_gloss = lookup_jmdict_gloss(
        surface=surface,
        base_form=base_form,
        normalized_form=normalized_form,
        reading=reading,
    )
    prefer_verb_glosses = part_of_speech in VERB_POS_TAGS
    # translate_glosses_to_korean already ranks and caps its own candidates.
    meaning = translate_glosses_to_korean(
        dictionary_gloss, prefer_verb_glosses=prefer_verb_glosses
    )
    if meaning:
        return meaning

    # Deprecated fallback: keep only as a small exception patch for sample gaps.
    fallback = map_glosses_to_korean(dictionary_gloss)
    return build_meaning_ko(fallback.split(",")) if fallback else fallback


def lookup_dictionary_gloss(
    *,
    surface: str,
    base_form: str,
    normalized_form: str,
    reading: str,
    deck_id: int | None,
) -> str:
    return lookup_jmdict_gloss(
        surface=surface,
        base_form=base_form,
        normalized_form=normalized_form,
        reading=reading,
    )

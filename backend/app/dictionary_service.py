from app.dictionary import get_korean_meaning
from app.en_ko_dictionary_service import translate_glosses_to_korean
from app.gloss_ko_mapper import map_glosses_to_korean
from app.jmdict_service import lookup_jmdict_gloss


def lookup_meaning(
    *,
    surface: str,
    base_form: str,
    normalized_form: str,
    reading: str,
    deck_id: int | None,
    custom_meaning_ko: str | None = None,
) -> str:
    custom_meaning = (custom_meaning_ko or "").strip()
    if custom_meaning:
        return custom_meaning

    for key in (base_form, normalized_form, surface):
        meaning = get_korean_meaning((key or "").strip())
        if meaning:
            return meaning

    dictionary_gloss = lookup_jmdict_gloss(
        surface=surface,
        base_form=base_form,
        normalized_form=normalized_form,
        reading=reading,
    )
    meaning = translate_glosses_to_korean(dictionary_gloss)
    if meaning:
        return meaning

    # Deprecated fallback: keep only as a small exception patch for sample gaps.
    return map_glosses_to_korean(dictionary_gloss)


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

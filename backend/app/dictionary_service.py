from app.dictionary import get_korean_meaning


def lookup_jmdict_meaning(
    *,
    surface: str,
    base_form: str,
    normalized_form: str,
    reading: str,
    deck_id: int | None,
) -> str:
    # TODO: Connect a local JMdict-backed dictionary lookup in a later step.
    return ""


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

    return lookup_jmdict_meaning(
        surface=surface,
        base_form=base_form,
        normalized_form=normalized_form,
        reading=reading,
        deck_id=deck_id,
    )

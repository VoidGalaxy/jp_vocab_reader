GLOSS_KO_MAP = {
    "laziness": "나태함",
    "idleness": "게으름",
    "sloth": "나태",
    "self-awareness": "자각",
    "consciousness": "의식",
    "to present": "내밀다, 제출하다",
    "to submit": "제출하다",
    "to hold out": "내밀다",
    "to look up at": "올려다보다",
    "to raise one's eyes": "눈을 들어 보다",
    "to stand up": "일어서다",
    "to rise": "일어나다",
    "to recover": "회복하다",
    "to resound": "울려 퍼지다",
    "to echo": "메아리치다",
    "hope": "희망",
    "wish": "바람, 소원",
    "darkness": "어둠",
    "voice": "목소리",
}


def map_glosses_to_korean(dictionary_gloss: str) -> str:
    meanings: list[str] = []
    seen: set[str] = set()

    for gloss in dictionary_gloss.split(";"):
        korean = GLOSS_KO_MAP.get(gloss.strip().lower(), "")
        if not korean:
            continue
        for meaning in [part.strip() for part in korean.split(",")]:
            if meaning and meaning not in seen:
                meanings.append(meaning)
                seen.add(meaning)

    return ", ".join(meanings)

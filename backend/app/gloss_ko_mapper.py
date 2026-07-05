from __future__ import annotations


# Deprecated: primary JMdict gloss translation uses en_ko_dictionary_service.
# Keep this table only as a small exception patch for sample/full coverage gaps.
GLOSS_KO_MAP = {
    "ability": "능력",
    "above": "위",
    "act": "행위",
    "action": "행동",
    "appearance": "모습",
    "area": "지역",
    "arm": "팔",
    "back": "뒤",
    "body": "몸",
    "book": "책",
    "case": "경우",
    "child": "아이",
    "consciousness": "의식",
    "darkness": "어둠",
    "day": "날",
    "door": "문",
    "dream": "꿈",
    "eye": "눈",
    "face": "얼굴",
    "feeling": "감정",
    "fire": "불",
    "flower": "꽃",
    "foot": "발",
    "friend": "친구",
    "hand": "손",
    "head": "머리",
    "heart": "마음",
    "hope": "희망",
    "house": "집",
    "idleness": "게으름",
    "laziness": "나태",
    "life": "삶, 생명",
    "light": "빛",
    "man": "남자",
    "mind": "마음",
    "moment": "순간",
    "money": "돈",
    "name": "이름",
    "night": "밤",
    "person": "사람",
    "place": "장소",
    "power": "힘",
    "rain": "비",
    "reason": "이유",
    "room": "방",
    "self-awareness": "자각",
    "shadow": "그림자",
    "sky": "하늘",
    "sloth": "나태",
    "sound": "소리",
    "thing": "것, 물건",
    "time": "시간",
    "voice": "목소리",
    "water": "물",
    "way": "길, 방법",
    "wish": "바람, 소원",
    "woman": "여자",
    "word": "말, 단어",
    "world": "세계",
    "to answer": "대답하다",
    "to ask": "묻다",
    "to become": "되다",
    "to begin": "시작하다",
    "to call": "부르다",
    "to come": "오다",
    "to die": "죽다",
    "to do": "하다",
    "to echo": "메아리치다",
    "to eat": "먹다",
    "to enter": "들어가다",
    "to exist": "존재하다",
    "to fall": "떨어지다",
    "to feel": "느끼다",
    "to find": "찾다",
    "to get up": "일어나다",
    "to give": "주다",
    "to go": "가다",
    "to hear": "듣다",
    "to hold out": "내밀다",
    "to know": "알다",
    "to leave": "떠나다",
    "to live": "살다",
    "to look": "보다",
    "to look up at": "올려다보다",
    "to make": "만들다",
    "to meet": "만나다",
    "to open": "열다",
    "to present": "내밀다, 제시하다",
    "to raise one's eyes": "눈을 들어 보다",
    "to read": "읽다",
    "to recover": "회복하다",
    "to resound": "울려 퍼지다",
    "to return": "돌아가다",
    "to rise": "일어나다",
    "to run": "달리다",
    "to say": "말하다",
    "to see": "보다",
    "to sleep": "자다",
    "to speak": "말하다",
    "to stand": "서다",
    "to stand up": "일어서다",
    "to submit": "제출하다",
    "to take": "잡다, 취하다",
    "to think": "생각하다",
    "to understand": "이해하다",
    "to wait": "기다리다",
    "to walk": "걷다",
    "to write": "쓰다",
}


def _normalize_gloss(gloss: str) -> str:
    return " ".join(gloss.strip().lower().split())


def _candidate_keys(gloss: str) -> list[str]:
    normalized = _normalize_gloss(gloss)
    keys = [normalized]
    for separator in ("; ", ", ", " ("):
        if separator in normalized:
            keys.append(normalized.split(separator, 1)[0].strip())
    return [key for key in keys if key]


def map_glosses_to_korean(dictionary_gloss: str) -> str:
    meanings: list[str] = []
    seen: set[str] = set()

    for gloss in dictionary_gloss.split(";"):
        korean = ""
        for key in _candidate_keys(gloss):
            korean = GLOSS_KO_MAP.get(key, "")
            if korean:
                break
        if not korean:
            continue
        for meaning in [part.strip() for part in korean.split(",")]:
            if meaning and meaning not in seen:
                meanings.append(meaning)
                seen.add(meaning)

    return ", ".join(meanings)

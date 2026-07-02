from sudachipy import dictionary

from app.dictionary import get_korean_meaning


SENTENCE_ENDINGS = {"。", "！", "？", "!", "?"}
EXCLUDED_POS = {"助詞", "助動詞", "補助記号", "記号", "空白"}
POS_LABELS = {
    "名詞": "명사",
    "動詞": "동사",
    "形容詞": "형용사",
    "形状詞": "형용동사",
    "副詞": "부사",
    "連体詞": "연체사",
    "接続詞": "접속사",
    "感動詞": "감탄사",
    "接頭辞": "접두사",
    "接尾辞": "접미사",
    "代名詞": "대명사",
    "助詞": "조사",
    "助動詞": "조동사",
    "補助記号": "기호",
    "記号": "기호",
    "空白": "공백",
}


def katakana_to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(char) - 0x60) if "ァ" <= char <= "ン" else char for char in text
    )


def pos_to_korean(part_of_speech: str) -> str:
    return POS_LABELS.get(part_of_speech, "기타")


def split_sentences(text: str) -> list[tuple[int, int, str]]:
    sentences: list[tuple[int, int, str]] = []
    start = 0

    for index, char in enumerate(text):
        if char in SENTENCE_ENDINGS:
            sentence = text[start : index + 1].strip()
            if sentence:
                sentences.append((start, index + 1, sentence))
            start = index + 1

    trailing = text[start:].strip()
    if trailing:
        sentences.append((start, len(text), trailing))

    return sentences


def find_example_sentence(
    sentences: list[tuple[int, int, str]], token_start: int
) -> str:
    for start, end, sentence in sentences:
        if start <= token_start < end:
            return sentence
    return ""


class JapaneseAnalyzer:
    def __init__(self) -> None:
        self._tokenizer = dictionary.Dictionary().create()

    def analyze(self, text: str) -> list[dict[str, str]]:
        tokens: list[dict[str, str]] = []
        seen_base_forms: set[str] = set()
        sentences = split_sentences(text)
        search_start = 0

        for morpheme in self._tokenizer.tokenize(text):
            surface = morpheme.surface()
            token_start = text.find(surface, search_start)
            if token_start == -1:
                token_start = text.find(surface)
            if token_start != -1:
                search_start = token_start + len(surface)

            if not surface.strip():
                continue

            pos = morpheme.part_of_speech()
            part_of_speech = pos[0] if pos else ""
            if part_of_speech in EXCLUDED_POS:
                continue

            base_form = morpheme.dictionary_form()
            if not base_form or base_form == "*":
                base_form = surface
            if base_form in seen_base_forms:
                continue

            seen_base_forms.add(base_form)
            tokens.append(
                {
                    "surface": surface,
                    "base_form": base_form,
                    "reading": katakana_to_hiragana(morpheme.reading_form()),
                    "part_of_speech": pos_to_korean(part_of_speech),
                    "normalized_form": morpheme.normalized_form(),
                    "meaning_ko": get_korean_meaning(base_form),
                    "example_sentence": find_example_sentence(
                        sentences, token_start
                    ),
                    "is_custom_term": False,
                    "_start": token_start,
                    "_end": token_start + len(surface) if token_start != -1 else -1,
                }
            )

        return tokens


analyzer = JapaneseAnalyzer()

from sudachipy import dictionary


EXCLUDED_POS = {"助詞", "助動詞", "補助記号"}


class JapaneseAnalyzer:
    def __init__(self) -> None:
        self._tokenizer = dictionary.Dictionary().create()

    def analyze(self, text: str) -> list[dict[str, str]]:
        tokens: list[dict[str, str]] = []
        seen_base_forms: set[str] = set()

        for morpheme in self._tokenizer.tokenize(text):
            surface = morpheme.surface()
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
                    "reading": morpheme.reading_form(),
                    "part_of_speech": part_of_speech,
                    "normalized_form": morpheme.normalized_form(),
                    "meaning_ko": "",
                }
            )

        return tokens


analyzer = JapaneseAnalyzer()

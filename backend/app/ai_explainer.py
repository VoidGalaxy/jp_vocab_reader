import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class MissingOpenAIKeyError(RuntimeError):
    pass


class AIExplanationError(RuntimeError):
    pass


def generate_context_explanation(item: dict[str, Any]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise MissingOpenAIKeyError(
            "OPENAI_API_KEY is not set. Add it to backend/.env or the environment."
        )

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-5.2")
    prompt = build_prompt(item)

    try:
        response = client.responses.create(
            model=model,
            instructions=(
                "너는 일본어 원서/웹소설 학습자를 돕는 한국어 일본어 선생님이다. "
                "답변은 한국어로 2~4문장만 작성한다. "
                "단어의 기본 의미, 예문 속 문맥 의미, 외울 때 참고할 뉘앙스를 포함한다."
            ),
            input=prompt,
        )
    except OpenAIError as exc:
        raise AIExplanationError(f"OpenAI API request failed: {exc}") from exc
    except Exception as exc:
        raise AIExplanationError(f"AI explanation failed: {exc}") from exc

    explanation = getattr(response, "output_text", "").strip()
    if not explanation:
        raise AIExplanationError("OpenAI API returned an empty explanation.")
    return explanation


def build_prompt(item: dict[str, Any]) -> str:
    return "\n".join(
        [
            "아래 일본어 단어를 예문 문맥에 맞춰 한국어로 설명해줘.",
            f"- surface: {item.get('surface', '')}",
            f"- base_form: {item.get('base_form', '')}",
            f"- reading: {item.get('reading', '')}",
            f"- part_of_speech: {item.get('part_of_speech', '')}",
            f"- meaning_ko: {item.get('meaning_ko', '')}",
            f"- example_sentence: {item.get('example_sentence', '')}",
        ]
    )

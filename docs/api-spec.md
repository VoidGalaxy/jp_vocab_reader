# API 명세서

## 공통 원칙

- API 서버는 FastAPI로 구현한다.
- 요청과 응답의 기본 형식은 JSON이다.
- CSV 내보내기 API만 `text/csv` 응답을 사용한다.
- MVP에서는 인증을 적용하지 않는다.
- 사용자가 붙여넣은 원문 전체는 DB에 저장하지 않는다.
- `/analyze` 요청의 원문은 형태소 분석과 응답 생성을 위해서만 사용하고, 처리 후 폐기한다.

## 데이터 모델 초안

### AnalyzedToken

```json
{
  "surface": "食べた",
  "base_form": "食べる",
  "reading": "たべる",
  "part_of_speech": "동사",
  "normalized_form": "食べる",
  "meaning_ko": "먹다",
  "dictionary_gloss": "to eat",
  "quality_tag": "normal",
  "example_sentence": "昨日、新しい本を食べる。",
  "is_custom_term": false
}
```

필드 설명:

- `surface`: 원문에 등장한 표면형
- `base_form`: 사전형 또는 기본형. 비어 있으면 `surface`를 사용한다.
- `reading`: 히라가나 읽기
- `part_of_speech`: 한국어 대표 품사명
- `normalized_form`: 정규화형
- `meaning_ko`: dictionary service가 사용자 정의 용어 뜻, 내장 한국어 사전, JMdict gloss 기반 로컬 한국어 매핑 순서로 채운 기본 한국어 뜻. 사전에 없으면 빈 문자열을 반환한다.
- `dictionary_gloss`: 로컬 JMdict JSON 사전에서 찾은 영어 gloss 후보. `meaning_ko`를 덮어쓰지 않으며, 매칭된 gloss를 `; `로 합친 문자열이다.
- `quality_tag`: 분석 품질 태그. `normal`, `custom_term`, `compound_verb`, `noun_phrase_candidate` 중 하나다.
- `example_sentence`: 단어가 처음 등장한 원문 문장. 문장 종료 기호를 포함한다.
- `is_custom_term`: 사용자 정의 용어 사전에서 매칭된 토큰이면 `true`, 일반 분석 토큰이면 `false`

### VocabItem

```json
{
  "id": 1,
  "deck_id": 1,
  "deck_name": "기본 단어장",
  "surface": "食べた",
  "base_form": "食べる",
  "reading": "たべる",
  "part_of_speech": "동사",
  "normalized_form": "食べる",
  "meaning_ko": "",
  "dictionary_gloss": "to eat",
  "quality_tag": "normal",
  "context_explanation_ko": "",
  "example_sentence": "",
  "status": "unknown",
  "correct_count": 0,
  "wrong_count": 0,
  "last_reviewed_at": null,
  "review_level": 0,
  "next_review_at": null,
  "created_at": "2026-07-02T09:00:00+00:00",
  "updated_at": "2026-07-02T09:00:00+00:00"
}
```

### Deck

```json
{
  "id": 1,
  "name": "기본 단어장",
  "description": "기존 단어와 기본 저장 대상",
  "created_at": "2026-07-02T09:00:00+00:00",
  "updated_at": "2026-07-02T09:00:00+00:00"
}
```

## GET /decks/{deck_id}/export-package

선택한 덱을 공유용 JSON 패키지로 반환한다. 기본 단어장도 내보낼 수 있다.

### 응답 예시

```json
{
  "package_type": "jp_vocab_reader_deck",
  "package_version": 1,
  "exported_at": "2026-07-03T00:00:00+09:00",
  "app": {
    "name": "JP Vocab Reader",
    "format": "deck_package"
  },
  "deck": {
    "name": "리제로 1장",
    "description": "리제로 1장 단어장"
  },
  "vocab_items": [
    {
      "surface": "怠惰",
      "base_form": "怠惰",
      "reading": "たいだ",
      "part_of_speech": "명사",
      "normalized_form": "怠惰",
      "meaning_ko": "나태함",
      "dictionary_gloss": "laziness; idleness; sloth",
      "context_explanation_ko": "",
      "example_sentence": "彼は怠惰であることを自覚していた。",
      "quality_tag": "normal"
    }
  ],
  "custom_terms": [
    {
      "term": "大罪司教",
      "reading": "たいざいしきょう",
      "part_of_speech": "명사",
      "meaning_ko": "대죄주교",
      "description": "작품 용어"
    }
  ]
}
```

### 처리 규칙

- 없는 `deck_id`는 `404 Not Found`를 반환한다.
- `status`, `correct_count`, `wrong_count`, `review_level`, `next_review_at`, `last_reviewed_at`, `id`, `deck_id`, `created_at`, `updated_at`은 공유 패키지에 포함하지 않는다.
- `custom_terms`는 해당 덱 전용 용어만 포함하며, 공통 용어(`deck_id: null`)는 현재 단계에서 포함하지 않는다.

## POST /decks/import-package

공유용 JSON 패키지를 받아 새 개인 덱으로 복사한다.

### 요청

`GET /decks/{deck_id}/export-package` 응답과 같은 JSON 구조를 보낸다.

### 응답

```json
{
  "deck_id": 10,
  "deck_name": "리제로 1장 (가져옴)",
  "imported_vocab_count": 120,
  "skipped_vocab_count": 5,
  "imported_custom_term_count": 10,
  "skipped_custom_term_count": 1,
  "message": "덱 패키지를 가져왔습니다."
}
```

### 처리 규칙

- `package_type`이 `jp_vocab_reader_deck`이 아니면 `400 Bad Request`를 반환한다.
- 지원하지 않는 `package_version`은 `400 Bad Request`를 반환한다. 현재 지원 버전은 `1`이다.
- 같은 이름의 덱이 이미 있으면 `덱 이름 (가져옴)`, `덱 이름 (가져옴 2)`처럼 중복되지 않는 이름으로 생성한다.
- 같은 패키지 안의 단어는 `base_form + reading` 기준으로 중복 제거한다.
- 같은 패키지 안의 사용자 정의 용어는 `term` 기준으로 중복 제거한다.
- 가져온 단어의 학습 상태는 `unknown`, 맞음/틀림 횟수와 복습 레벨은 `0`, 복습 날짜는 `null`로 초기화한다.

## POST /analyze

일본어 원문을 분석해 학습 후보 단어 목록을 반환한다.

### 요청

```json
{
  "text": "私は昨日、新しい本を読んだ。",
  "deck_id": 1,
  "include_known": false
}
```

필드 설명:

- `text`: 사용자가 붙여넣은 일본어 원문
- `deck_id`: optional. 지정하면 해당 덱에 저장된 아는 단어만 자동 제외 기준으로 사용한다.
- `include_known`: optional, default `false`. `false`이면 저장된 `known` 단어를 분석 결과에서 제외하고, `true`이면 포함한다.
- `text`만 보내도 기존처럼 정상 동작한다.

### 처리 규칙

- `text`는 필수값이다.
- 공백만 있는 입력은 거부한다.
- 서버는 `text` 원문 전체를 DB에 저장하지 않는다.
- SudachiPy로 형태소 분석을 수행한다.
- DB에 등록된 사용자 정의 용어를 먼저 원문에서 매칭한다.
- `deck_id`가 있으면 해당 덱 전용 용어와 공통 용어를 사용하고, 없으면 전체 사용자 정의 용어를 사용한다.
- 사용자 정의 용어와 일반 토큰이 겹치면 사용자 정의 용어를 우선한다.
- 사용자 정의 용어가 서로 겹치면 더 긴 용어를 우선한다.
- `deck_id`가 있으면 해당 덱 안의 `known` 단어만 제외하고, 없으면 전체 단어장 기준으로 제외한다.
- `include_known`이 `false`여도 `uncertain`과 `unknown` 단어는 숨기지 않는다.
- `include_known`이 `true`이면 저장된 `known` 단어도 응답에 포함한다.
- 품사가 `助詞`, `助動詞`, `補助記号`인 토큰은 응답에서 제거한다.
- `surface`가 공백인 토큰은 응답에서 제거한다.
- `base_form`이 비어 있으면 `surface`를 사용한다.
- 같은 `base_form`은 한 번만 반환한다.
- 후처리에서 지정 복합동사와 일부 `명사 + の + 명사` 명사구 후보를 추가한다.
- `する`, `ある`, `いる`, `なる`, `こと`, `もの`, 주요 지시어/대명사 같은 기초 단어는 일반 토큰에서 제외한다. 사용자 정의 용어로 매칭된 경우는 제외하지 않는다.
- 반환 순서는 원문에서 처음 등장한 순서를 유지한다.
- `reading`은 SudachiPy의 가타카나 읽기를 히라가나로 변환해 반환한다.
- `part_of_speech`는 한국어 품사명으로 반환한다.
- `meaning_ko`는 dictionary service를 통해 채운다. 조회 우선순위는 사용자 정의 용어 뜻, 내장 사전의 `base_form`, `normalized_form`, `surface`, JMdict gloss 기반 로컬 한국어 매핑 순서이며, 사전에 없으면 빈 문자열을 반환한다.
- 일반 Sudachi 토큰의 `dictionary_gloss`는 로컬 JMdict JSON 사전에서 `surface`, `base_form`, `normalized_form`, `reading` 순서로 조회한다.
- 사용자 정의 용어 토큰의 `dictionary_gloss`는 빈 문자열이다.
- `quality_tag`는 일반 토큰 `normal`, 사용자 정의 용어 `custom_term`, 복합동사 `compound_verb`, 명사구 후보 `noun_phrase_candidate`로 반환한다.
- `example_sentence`는 원문을 `。`, `！`, `？`, `!`, `?` 기준으로 나눈 뒤, 해당 토큰이 처음 등장한 문장을 반환한다.
- 문장 종료 기호는 `example_sentence`에 포함한다.

### 응답

```json
{
  "tokens": [
    {
      "surface": "怠惰",
      "base_form": "怠惰",
      "reading": "たいだ",
      "part_of_speech": "명사",
      "normalized_form": "怠惰",
      "meaning_ko": "나태함",
      "dictionary_gloss": "laziness; idleness; sloth",
      "quality_tag": "normal",
      "example_sentence": "彼は怠惰であることを自覚していた。",
      "is_custom_term": false
    }
  ]
}
```

### 오류

- `400 Bad Request`: 입력이 비어 있거나 너무 짧은 경우
- `413 Payload Too Large`: 입력 원문이 MVP 제한 길이를 초과한 경우
- `500 Internal Server Error`: 형태소 분석 또는 서버 내부 오류

## GET /health

서버 상태 확인용 API다.

### 응답

```json
{
  "status": "ok"
}
```

## GET /custom-terms

사용자 정의 용어 목록을 조회한다.

### Query Parameters

- `deck_id` optional: 지정하면 해당 덱 전용 용어와 공통 용어(`deck_id: null`)를 함께 반환한다. 생략하면 전체 용어를 반환한다.

### 응답

```json
{
  "items": [
    {
      "id": 1,
      "term": "大罪司教",
      "reading": "たいざいしきょう",
      "part_of_speech": "명사",
      "meaning_ko": "대죄주교",
      "description": "리제로의 마녀교 대죄주교를 가리키는 작품 용어",
      "deck_id": 1,
      "deck_name": "리제로",
      "created_at": "2026-07-02T09:00:00+00:00",
      "updated_at": "2026-07-02T09:00:00+00:00"
    }
  ]
}
```

## POST /custom-terms

사용자 정의 용어를 등록한다.

### 요청

```json
{
  "term": "大罪司教",
  "reading": "たいざいしきょう",
  "part_of_speech": "명사",
  "meaning_ko": "대죄주교",
  "description": "리제로의 마녀교 대죄주교를 가리키는 작품 용어",
  "deck_id": 1
}
```

### 처리 규칙

- `term`은 공백일 수 없고 앞뒤 공백을 제거해 저장한다.
- `part_of_speech`가 비어 있으면 `명사`로 저장한다.
- `deck_id`가 `null`이면 모든 덱에 적용되는 공통 용어로 저장한다.
- 같은 `term` + `deck_id` 조합은 중복 생성하지 않고 기존 항목을 반환한다.

### 응답

생성되었거나 이미 존재하던 사용자 정의 용어 객체를 반환한다.

## PATCH /custom-terms/{term_id}

사용자 정의 용어를 수정한다. 모든 필드는 optional이다.

### 응답

수정된 사용자 정의 용어 객체를 반환한다.

### 오류

- `400 Bad Request`: `term`이 비어 있는 경우
- `404 Not Found`: 용어 또는 덱을 찾을 수 없는 경우

## DELETE /custom-terms/{term_id}

사용자 정의 용어를 삭제한다.

### 응답

- `204 No Content`

### 오류

- `404 Not Found`: 용어를 찾을 수 없는 경우

## GET /vocab-items

저장된 단어장 항목을 조회한다.

### Query Parameters

- `deck_id` optional: 지정하면 해당 덱의 단어만 반환한다. 생략하면 전체 덱 기준으로 반환한다.
- `status` optional: `unknown`, `uncertain`, `known`, `unclassified` 중 하나로 필터링한다.
- `q` optional: `surface`, `base_form`, `reading`, `meaning_ko`, `dictionary_gloss`, `example_sentence`, `context_explanation_ko`에서 부분 검색한다.
- `due_only` optional, default `false`: `true`면 `next_review_at`이 비어 있거나 현재 시각 이하인 항목만 반환한다.
- `sort` optional: `created_desc`, `created_asc`, `wrong_desc`, `correct_desc`, `review_level_asc`, `next_review_asc` 중 하나를 사용한다.

### 응답

```json
{
  "items": [
    {
      "id": 1,
      "deck_id": 1,
      "deck_name": "기본 단어장",
      "surface": "読んだ",
      "base_form": "読む",
      "reading": "よむ",
      "part_of_speech": "동사",
      "normalized_form": "読む",
      "meaning_ko": "",
      "dictionary_gloss": "",
      "quality_tag": "normal",
      "context_explanation_ko": "",
      "example_sentence": "私は昨日、新しい本を読んだ。",
      "status": "unknown",
      "correct_count": 0,
      "wrong_count": 0,
      "last_reviewed_at": null,
      "review_level": 0,
      "next_review_at": null,
      "created_at": "2026-07-02T09:00:00+00:00",
      "updated_at": "2026-07-02T09:00:00+00:00"
    }
  ]
}
```

## POST /vocab-items

분석 결과에서 사용자가 선택한 단어를 저장하거나, 사용자가 단어장 탭에서 직접 입력한 단어를 저장한다.

### 요청

```json
{
  "surface": "読んだ",
  "base_form": "読む",
  "reading": "よむ",
  "part_of_speech": "동사",
  "normalized_form": "読む",
  "meaning_ko": "",
  "dictionary_gloss": "",
  "quality_tag": "normal",
  "context_explanation_ko": "",
  "example_sentence": "私は昨日、新しい本を読んだ。",
  "status": "unknown",
  "deck_id": 1
}
```

### 처리 규칙

- `surface` 또는 `base_form` 중 하나는 공백이 아니어야 한다.
- `base_form`이 비어 있으면 `surface`를 `base_form`으로 사용한다.
- `normalized_form`이 비어 있으면 `base_form`을 `normalized_form`으로 사용한다.
- `reading`, `part_of_speech`, `meaning_ko`, `dictionary_gloss`, `example_sentence`, `context_explanation_ko`는 빈 문자열로 저장할 수 있다.
- `quality_tag`가 없으면 `normal`로 저장한다.
- `status`가 없으면 `unknown`으로 저장한다.
- `status`는 `unknown`, `uncertain`, `known`, `unclassified` 중 하나여야 한다.
- `deck_id`를 생략하면 `기본 단어장`에 저장한다.
- 같은 덱 안에서 `base_form` + `reading` 기준 중복 저장을 방지한다.
- 이미 존재하는 조합이 들어오면 서버 에러로 처리하지 않고 기존 항목을 반환한다.
- 원문 전체, 문단 전체, 긴 문맥 문자열은 저장하지 않는다.

### 응답

```json
{
  "id": 1,
  "deck_id": 1,
  "deck_name": "기본 단어장",
  "surface": "読んだ",
  "base_form": "読む",
  "reading": "よむ",
  "part_of_speech": "동사",
  "normalized_form": "読む",
  "meaning_ko": "",
  "dictionary_gloss": "",
  "quality_tag": "normal",
  "context_explanation_ko": "",
  "example_sentence": "私は昨日、新しい本を読んだ。",
  "status": "unknown",
  "correct_count": 0,
  "wrong_count": 0,
  "last_reviewed_at": null,
  "review_level": 0,
  "next_review_at": null,
  "created_at": "2026-07-02T09:00:00+00:00",
  "updated_at": "2026-07-02T09:00:00+00:00"
}
```

### 오류

- `400 Bad Request`: 필수 필드 누락 또는 잘못된 `status`
- `409 Conflict`: 중복 처리 정책상 저장할 수 없는 충돌이 발생한 경우
- `500 Internal Server Error`: DB 저장 오류

## PATCH /vocab-items/{item_id}

저장된 단어의 학습 상태와 단어장 필드를 수정한다.

### 요청

```json
{
  "surface": "読んだ",
  "base_form": "読む",
  "reading": "よむ",
  "part_of_speech": "동사",
  "normalized_form": "読む",
  "meaning_ko": "읽다",
  "dictionary_gloss": "to read",
  "quality_tag": "normal",
  "context_explanation_ko": "문맥 설명",
  "example_sentence": "私は昨日、新しい本を読んだ。",
  "status": "known",
  "deck_id": 1
}
```

### 처리 규칙

- 모든 필드는 optional이다.
- 전달되지 않은 필드는 기존 값을 유지한다.
- 수정 가능한 필드는 `surface`, `base_form`, `reading`, `part_of_speech`, `normalized_form`, `meaning_ko`, `dictionary_gloss`, `quality_tag`, `context_explanation_ko`, `example_sentence`, `status`, `deck_id`다.
- `base_form`이 비어 있으면 `surface`를 `base_form`으로 사용한다.
- `normalized_form`이 비어 있으면 `base_form`을 `normalized_form`으로 사용한다.
- `status`가 있으면 `unknown`, `uncertain`, `known`, `unclassified` 중 하나여야 한다.
- `deck_id`가 없으면 기존 덱을 유지하고, 유효하지 않은 덱이면 `기본 단어장`으로 이동한다.
- 수정 시 `updated_at`을 현재 시간으로 갱신한다.

### 응답

수정된 `VocabItem` 객체를 반환한다.

### 오류

- `400 Bad Request`: 잘못된 `status`
- `404 Not Found`: 항목을 찾을 수 없는 경우

## POST /vocab-items/{item_id}/explain

저장된 단어와 예문을 기반으로 AI 문맥 설명을 생성하고 DB에 저장한다.

### 처리 규칙

- 사용자가 버튼을 누른 단어에 대해서만 호출한다.
- 서버는 `surface`, `base_form`, `reading`, `part_of_speech`, `meaning_ko`, `example_sentence`를 AI에 전달한다.
- AI 설명은 한국어 2~4문장으로 생성한다.
- 설명에는 기본 의미, 예문 속 문맥 의미, 외울 때 참고할 뉘앙스를 포함한다.
- 생성 결과는 `context_explanation_ko`에 저장한다.
- `OPENAI_API_KEY`가 없으면 서버는 죽지 않고 JSON 에러를 반환한다.

### 응답

갱신된 `VocabItem` 객체를 반환한다.

### 오류

- `400 Bad Request`: `OPENAI_API_KEY`가 설정되지 않은 경우
- `404 Not Found`: 항목을 찾을 수 없는 경우
- `502 Bad Gateway`: AI 호출 실패 또는 빈 응답

## GET /study-items

자체 학습 모드에서 오늘 복습할 단어 목록을 조회한다.

### Query Parameters

- `deck_id` optional: 지정하면 해당 덱의 오늘 복습할 단어만 반환한다. 생략하면 전체 덱 기준으로 반환한다.

### 처리 규칙

- 학습 대상은 `status`가 `unknown` 또는 `uncertain`인 단어다.
- `known` 단어는 학습 대상에서 제외한다.
- `next_review_at`이 `null`이거나 현재 시간보다 이전 또는 같은 단어만 반환한다.
- `next_review_at`이 지난 단어를 우선한다.
- `wrong_count`가 높은 단어를 우선한다.
- `review_level`이 낮은 단어를 우선한다.
- 아직 복습하지 않아 `last_reviewed_at`이 비어 있는 단어를 우선한다.
- 마지막으로 오래 전에 생성된 단어를 우선한다.

### 응답

```json
{
  "items": [
    {
      "id": 1,
      "deck_id": 1,
      "deck_name": "기본 단어장",
      "surface": "怠惰",
      "base_form": "怠惰",
      "reading": "たいだ",
      "part_of_speech": "명사",
      "normalized_form": "怠惰",
      "meaning_ko": "나태함",
      "dictionary_gloss": "laziness; idleness; sloth",
      "quality_tag": "normal",
      "context_explanation_ko": "怠惰는 게으름이나 나태함을 뜻합니다. 예문에서는 인물이 스스로 그런 성향을 알고 있었다는 문맥입니다. 단순히 쉬는 것이 아니라 해야 할 일을 미루는 부정적인 뉘앙스로 기억하면 좋습니다.",
      "example_sentence": "彼は怠惰であることを自覚していた。",
      "status": "unknown",
      "correct_count": 1,
      "wrong_count": 3,
      "last_reviewed_at": "2026-07-02T09:30:00+00:00",
      "review_level": 0,
      "next_review_at": "2026-07-02T09:30:00+00:00",
      "created_at": "2026-07-02T09:00:00+00:00",
      "updated_at": "2026-07-02T09:30:00+00:00"
    }
  ]
}
```

## POST /study-items/{item_id}/review

학습 카드에서 맞음 또는 틀림 결과를 기록한다.

### 요청

```json
{
  "result": "correct"
}
```

또는:

```json
{
  "result": "wrong"
}
```

### 처리 규칙

- `correct`면 `correct_count`를 1 증가시키고 `review_level`을 1 증가시킨다. `review_level`은 최대 4로 제한한다.
- `correct`일 때 현재 `review_level`이 0이면 `next_review_at`을 1일 뒤로 설정한다.
- `correct`일 때 현재 `review_level`이 1이면 `next_review_at`을 3일 뒤로 설정한다.
- `correct`일 때 현재 `review_level`이 2이면 `next_review_at`을 7일 뒤로 설정한다.
- `correct`일 때 현재 `review_level`이 3 이상이면 `next_review_at`을 14일 뒤로 설정한다.
- `wrong`이면 `wrong_count`를 1 증가시키고 `review_level`을 0으로 초기화한다.
- `wrong`이면 `next_review_at`을 현재 시간으로 설정한다.
- 두 경우 모두 `last_reviewed_at`과 `updated_at`을 현재 시간으로 갱신한다.

### 응답

갱신된 `VocabItem` 객체를 반환한다.

### 오류

- `400 Bad Request`: 잘못된 `result`
- `404 Not Found`: 항목을 찾을 수 없는 경우

## GET /stats

저장된 단어장의 학습 통계와 진도를 조회한다.

### Query Parameters

- `deck_id` optional: 지정하면 해당 덱 기준으로 통계를 계산한다. 생략하면 전체 단어장 기준으로 계산하고 `deck_stats`에 덱별 요약을 포함한다.

### 응답

```json
{
  "scope": "all",
  "deck_id": null,
  "deck_name": null,
  "total_count": 100,
  "known_count": 30,
  "uncertain_count": 25,
  "unknown_count": 40,
  "unclassified_count": 5,
  "due_today_count": 12,
  "total_correct_count": 80,
  "total_wrong_count": 35,
  "average_review_level": 1.8,
  "learned_rate": 0.3,
  "deck_stats": [
    {
      "deck_id": 1,
      "deck_name": "리제로",
      "total_count": 50,
      "known_count": 15,
      "uncertain_count": 10,
      "unknown_count": 23,
      "unclassified_count": 2,
      "due_today_count": 6,
      "learned_rate": 0.3
    }
  ],
  "review_level_counts": [
    {"review_level": 0, "count": 20},
    {"review_level": 1, "count": 10}
  ]
}
```

### 처리 규칙

- `due_today_count`는 `status`가 `unknown` 또는 `uncertain`이고, `next_review_at`이 비어 있거나 현재 시각 이하인 단어 수다.
- `learned_rate`는 `known_count / total_count`이며, `total_count`가 0이면 0이다.
- `average_review_level`은 저장된 단어의 `review_level` 평균이며, 단어가 없으면 0이다.
- `total_correct_count`와 `total_wrong_count`는 각각 `correct_count`, `wrong_count` 합계다.

### 오류

- `404 Not Found`: 지정한 덱을 찾을 수 없는 경우

## DELETE /vocab-items/{item_id}

저장된 단어를 삭제한다.

### 응답

- `204 No Content`

### 오류

- `404 Not Found`: 항목을 찾을 수 없는 경우

## GET /vocab-items/export.csv

저장된 단어장을 CSV 파일로 내보낸다.

### Query Parameters

- `deck_id` optional: 지정하면 해당 덱만 CSV로 내보낸다. 생략하면 전체 덱 기준으로 내보낸다.

### 응답 헤더

```http
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="jp-vocab-items.csv"
```

### CSV 컬럼

```csv
surface,base_form,reading,part_of_speech,quality_tag,meaning_ko,dictionary_gloss,context_explanation_ko,example_sentence,status,review_level,correct_count,wrong_count,next_review_at,created_at
読んだ,読む,よむ,동사,normal,,to read,,私は昨日、新しい本を読んだ。,unknown,0,0,0,,2026-07-02T09:00:00+00:00
```

### 처리 규칙

- `deck_id`가 없으면 저장된 `vocab_items` 전체를 내보내고, 있으면 해당 덱의 항목만 내보낸다.
- CSV 첫 줄에는 헤더를 포함한다.
- CSV는 UTF-8 BOM을 포함해 엑셀에서 한글과 일본어가 깨지지 않도록 한다.
- 저장된 단어가 하나도 없어도 헤더만 있는 CSV를 반환한다.
- 원문 전체나 긴 문맥은 CSV에 포함하지 않는다.

### 오류

- `500 Internal Server Error`: CSV 생성 또는 DB 조회 오류

## GET /decks

덱 목록을 조회한다. 앱 시작 시 `기본 단어장`이 없으면 자동 생성된다.

### 응답

```json
{
  "items": [
    {
      "id": 1,
      "name": "기본 단어장",
      "description": "기존 단어와 기본 저장 대상",
      "created_at": "2026-07-02T09:00:00+00:00",
      "updated_at": "2026-07-02T09:00:00+00:00"
    }
  ]
}
```

## POST /decks

새 덱을 생성한다.

### 요청

```json
{
  "name": "리제로",
  "description": "리제로 원서 단어장"
}
```

### 처리 규칙

- `name`은 공백일 수 없다.
- 같은 이름의 덱이 이미 있으면 새로 만들지 않고 기존 덱을 반환한다.

### 응답

생성되었거나 이미 존재하던 `Deck` 객체를 반환한다.

## PATCH /decks/{deck_id}

덱 이름 또는 설명을 수정한다.

### 요청

```json
{
  "name": "리제로 1권",
  "description": "리제로 1권 단어장"
}
```

### 응답

수정된 `Deck` 객체를 반환한다.

### 오류

- `400 Bad Request`: 덱 이름이 비어 있거나 수정할 수 없는 경우
- `404 Not Found`: 덱을 찾을 수 없는 경우

## DELETE /decks/{deck_id}

덱을 삭제한다.

### 처리 규칙

- `기본 단어장`은 삭제할 수 없다.
- 덱 삭제 시 해당 덱의 단어도 함께 삭제한다.
- 단어 삭제는 반드시 삭제 대상 `deck_id`와 일치하는 항목으로 제한한다.

### 응답

```json
{
  "deleted_deck_id": 2,
  "deleted_vocab_count": 15,
  "message": "덱과 덱에 포함된 단어를 삭제했습니다."
}
```

### 오류

- `400 Bad Request`: 기본 단어장을 삭제하려는 경우
- `404 Not Found`: 덱을 찾을 수 없는 경우

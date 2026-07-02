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
  "reading": "タベル",
  "part_of_speech": "動詞",
  "normalized_form": "食べる",
  "meaning_ko": ""
}
```

필드 설명:

- `surface`: 원문에 등장한 표면형
- `base_form`: 사전형 또는 기본형. 비어 있으면 `surface`를 사용한다.
- `reading`: 가타카나 읽기
- `part_of_speech`: 대표 품사
- `normalized_form`: 정규화형
- `meaning_ko`: 한국어 뜻. MVP에서는 사전 기능이 없으므로 빈 문자열을 반환한다.

### VocabItem

```json
{
  "id": 1,
  "surface": "食べた",
  "lemma": "食べる",
  "reading": "タベル",
  "partOfSpeech": "動詞",
  "meaningKo": "먹다",
  "knownState": "unknown",
  "createdAt": "2026-07-02T09:00:00Z",
  "updatedAt": "2026-07-02T09:00:00Z"
}
```

## POST /analyze

일본어 원문을 분석해 학습 후보 단어 목록을 반환한다.

### 요청

```json
{
  "text": "私は昨日、新しい本を読んだ。"
}
```

필드 설명:

- `text`: 사용자가 붙여넣은 일본어 원문

### 처리 규칙

- `text`는 필수값이다.
- 공백만 있는 입력은 거부한다.
- 서버는 `text` 원문 전체를 DB에 저장하지 않는다.
- SudachiPy로 형태소 분석을 수행한다.
- 품사가 `助詞`, `助動詞`, `補助記号`인 토큰은 응답에서 제거한다.
- `surface`가 공백인 토큰은 응답에서 제거한다.
- `base_form`이 비어 있으면 `surface`를 사용한다.
- 같은 `base_form`은 한 번만 반환한다.
- 반환 순서는 원문에서 처음 등장한 순서를 유지한다.
- `meaning_ko`는 MVP에서 빈 문자열로 반환한다.

### 응답

```json
{
  "tokens": [
    {
      "surface": "昨日",
      "base_form": "昨日",
      "reading": "キノウ",
      "part_of_speech": "名詞",
      "normalized_form": "昨日",
      "meaning_ko": ""
    },
    {
      "surface": "読んだ",
      "base_form": "読む",
      "reading": "ヨム",
      "part_of_speech": "動詞",
      "normalized_form": "読む",
      "meaning_ko": ""
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

## GET /vocab-items

저장된 단어장 항목을 조회한다.

### 쿼리 파라미터

- `knownState`: 선택값. `known`, `unknown`, `unclassified`
- `limit`: 선택값. 기본값 100
- `offset`: 선택값. 기본값 0

### 응답

```json
{
  "items": [
    {
      "id": 1,
      "surface": "読んだ",
      "lemma": "読む",
      "reading": "ヨム",
      "partOfSpeech": "動詞",
      "meaningKo": "읽다",
      "knownState": "unknown",
      "createdAt": "2026-07-02T09:00:00Z",
      "updatedAt": "2026-07-02T09:00:00Z"
    }
  ],
  "total": 1
}
```

## POST /vocab-items

분석 결과에서 사용자가 선택한 단어를 단어장에 저장한다.

### 요청

```json
{
  "items": [
    {
      "surface": "読んだ",
      "lemma": "読む",
      "reading": "ヨム",
      "partOfSpeech": "動詞",
      "meaningKo": "읽다",
      "knownState": "unknown"
    }
  ]
}
```

### 처리 규칙

- MVP에서는 주로 `knownState`가 `unknown`인 항목을 저장 대상으로 사용한다.
- `lemma` 기준 중복 저장을 방지한다.
- 이미 존재하는 `lemma`가 들어오면 기존 항목을 유지하거나 최신 값으로 갱신한다.
- 원문 전체, 문단 전체, 긴 문맥 문자열은 저장하지 않는다.

### 응답

```json
{
  "items": [
    {
      "id": 1,
      "surface": "読んだ",
      "lemma": "読む",
      "reading": "ヨム",
      "partOfSpeech": "動詞",
      "meaningKo": "읽다",
      "knownState": "unknown",
      "createdAt": "2026-07-02T09:00:00Z",
      "updatedAt": "2026-07-02T09:00:00Z"
    }
  ]
}
```

### 오류

- `400 Bad Request`: 필수 필드 누락 또는 잘못된 `knownState`
- `409 Conflict`: 중복 처리 정책상 저장할 수 없는 충돌이 발생한 경우
- `500 Internal Server Error`: DB 저장 오류

## GET /vocab-items/export.csv

저장된 단어장을 CSV 파일로 내보낸다.

### 쿼리 파라미터

- `knownState`: 선택값. 기본적으로 전체를 내보내며, MVP에서는 `unknown` 필터를 우선 지원한다.

### 응답 헤더

```http
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="vocab-items.csv"
```

### CSV 컬럼

```csv
surface,lemma,reading,partOfSpeech,meaningKo,knownState,createdAt
読んだ,読む,ヨム,動詞,읽다,unknown,2026-07-02T09:00:00Z
```

### 처리 규칙

- CSV는 UTF-8로 생성한다.
- 한국어와 일본어가 깨지지 않도록 인코딩을 명확히 한다.
- 원문 전체나 긴 문맥은 CSV에 포함하지 않는다.

### 오류

- `500 Internal Server Error`: CSV 생성 또는 DB 조회 오류

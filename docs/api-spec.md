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
  "meaning_ko": "먹다"
}
```

필드 설명:

- `surface`: 원문에 등장한 표면형
- `base_form`: 사전형 또는 기본형. 비어 있으면 `surface`를 사용한다.
- `reading`: 히라가나 읽기
- `part_of_speech`: 한국어 대표 품사명
- `normalized_form`: 정규화형
- `meaning_ko`: 내장 사전에서 찾은 기본 한국어 뜻. 사전에 없으면 빈 문자열을 반환한다.

### VocabItem

```json
{
  "id": 1,
  "surface": "食べた",
  "base_form": "食べる",
  "reading": "たべる",
  "part_of_speech": "동사",
  "normalized_form": "食べる",
  "meaning_ko": "",
  "status": "unknown",
  "correct_count": 0,
  "wrong_count": 0,
  "last_reviewed_at": null,
  "created_at": "2026-07-02T09:00:00+00:00",
  "updated_at": "2026-07-02T09:00:00+00:00"
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
- `reading`은 SudachiPy의 가타카나 읽기를 히라가나로 변환해 반환한다.
- `part_of_speech`는 한국어 품사명으로 반환한다.
- `meaning_ko`는 내장 사전에서 `base_form` 기준으로 조회해 반환한다. 사전에 없으면 빈 문자열을 반환한다.

### 응답

```json
{
  "tokens": [
    {
      "surface": "彼",
      "base_form": "彼",
      "reading": "かれ",
      "part_of_speech": "대명사",
      "normalized_form": "彼",
      "meaning_ko": "그, 그 사람"
    },
    {
      "surface": "怠惰",
      "base_form": "怠惰",
      "reading": "たいだ",
      "part_of_speech": "명사",
      "normalized_form": "怠惰",
      "meaning_ko": "나태함"
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

### 응답

```json
{
  "items": [
    {
      "id": 1,
      "surface": "読んだ",
      "base_form": "読む",
      "reading": "よむ",
      "part_of_speech": "동사",
      "normalized_form": "読む",
      "meaning_ko": "",
      "status": "unknown",
      "correct_count": 0,
      "wrong_count": 0,
      "last_reviewed_at": null,
      "created_at": "2026-07-02T09:00:00+00:00",
      "updated_at": "2026-07-02T09:00:00+00:00"
    }
  ]
}
```

## POST /vocab-items

분석 결과에서 사용자가 선택한 단어를 단어장에 저장한다.

### 요청

```json
{
  "surface": "読んだ",
  "base_form": "読む",
  "reading": "よむ",
  "part_of_speech": "동사",
  "normalized_form": "読む",
  "meaning_ko": "",
  "status": "unknown"
}
```

### 처리 규칙

- MVP에서는 주로 `status`가 `unknown`인 항목을 저장 대상으로 사용한다.
- `status`는 `unknown`, `known`, `unclassified` 중 하나여야 한다.
- `base_form` + `reading` 기준 중복 저장을 방지한다.
- 이미 존재하는 조합이 들어오면 서버 에러로 처리하지 않고 기존 항목을 반환한다.
- 원문 전체, 문단 전체, 긴 문맥 문자열은 저장하지 않는다.

### 응답

```json
{
  "id": 1,
  "surface": "読んだ",
  "base_form": "読む",
  "reading": "よむ",
  "part_of_speech": "동사",
  "normalized_form": "読む",
  "meaning_ko": "",
  "status": "unknown",
  "correct_count": 0,
  "wrong_count": 0,
  "last_reviewed_at": null,
  "created_at": "2026-07-02T09:00:00+00:00",
  "updated_at": "2026-07-02T09:00:00+00:00"
}
```

### 오류

- `400 Bad Request`: 필수 필드 누락 또는 잘못된 `knownState`
- `409 Conflict`: 중복 처리 정책상 저장할 수 없는 충돌이 발생한 경우
- `500 Internal Server Error`: DB 저장 오류

## PATCH /vocab-items/{item_id}

저장된 단어의 학습 상태를 수정한다.

### 요청

```json
{
  "status": "known"
}
```

### 응답

수정된 `VocabItem` 객체를 반환한다.

### 오류

- `400 Bad Request`: 잘못된 `status`
- `404 Not Found`: 항목을 찾을 수 없는 경우

## GET /study-items

자체 학습 모드에서 복습할 단어 목록을 조회한다.

### 처리 규칙

- 기본 학습 대상은 `status`가 `unknown`인 단어다.
- `wrong_count`가 높은 단어를 우선한다.
- 아직 복습하지 않아 `last_reviewed_at`이 비어 있는 단어를 우선한다.
- 복습한 단어 중에서는 오래 전에 복습한 단어를 우선한다.
- 마지막으로 오래 전에 생성된 단어를 우선한다.

### 응답

```json
{
  "items": [
    {
      "id": 1,
      "surface": "怠惰",
      "base_form": "怠惰",
      "reading": "たいだ",
      "part_of_speech": "명사",
      "normalized_form": "怠惰",
      "meaning_ko": "나태함",
      "status": "unknown",
      "correct_count": 1,
      "wrong_count": 3,
      "last_reviewed_at": "2026-07-02T09:30:00+00:00",
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

- `correct`면 `correct_count`를 1 증가시킨다.
- `wrong`이면 `wrong_count`를 1 증가시킨다.
- 두 경우 모두 `last_reviewed_at`과 `updated_at`을 현재 시간으로 갱신한다.

### 응답

갱신된 `VocabItem` 객체를 반환한다.

### 오류

- `400 Bad Request`: 잘못된 `result`
- `404 Not Found`: 항목을 찾을 수 없는 경우

## DELETE /vocab-items/{item_id}

저장된 단어를 삭제한다.

### 응답

- `204 No Content`

### 오류

- `404 Not Found`: 항목을 찾을 수 없는 경우

## GET /vocab-items/export.csv

저장된 단어장을 CSV 파일로 내보낸다.

### 응답 헤더

```http
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="jp-vocab-items.csv"
```

### CSV 컬럼

```csv
surface,base_form,reading,part_of_speech,meaning_ko,status,created_at
読んだ,読む,よむ,동사,,unknown,2026-07-02T09:00:00+00:00
```

### 처리 규칙

- 저장된 `vocab_items` 전체를 내보낸다.
- CSV 첫 줄에는 헤더를 포함한다.
- CSV는 UTF-8 BOM을 포함해 엑셀에서 한글과 일본어가 깨지지 않도록 한다.
- 저장된 단어가 하나도 없어도 헤더만 있는 CSV를 반환한다.
- 원문 전체나 긴 문맥은 CSV에 포함하지 않는다.

### 오류

- `500 Internal Server Error`: CSV 생성 또는 DB 조회 오류

# jp-vocab-reader

일본어 원서/웹소설 학습자를 위한 자동 단어장 생성 웹서비스입니다.

## 목표

- 일본어 원문 붙여넣기
- 형태소 분석으로 단어 추출
- 중복 단어 제거
- 읽기, 기본형, 품사 표시
- 한국어 뜻 표시
- 아는 단어 / 모르는 단어 분류
- 모르는 단어 저장
- CSV 내보내기
- 추후 AI 문맥 설명 추가

## 기술 스택 예정

- Frontend: Next.js
- Backend: FastAPI
- Tokenizer: SudachiPy
- Database: SQLite

## Backend MVP 실행

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

AI 문맥 설명을 사용하려면 `backend/.env`에 OpenAI API 키를 설정한다. `.env` 파일은 커밋하지 않는다.

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.2
```

헬스체크:

```bash
curl http://localhost:8000/health
```

분석 API 테스트:

```bash
curl.exe -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d "{\"text\":\"彼は怠惰であることを自覚していた。\"}"
```

분석 결과의 `reading`은 히라가나로 반환되고, `part_of_speech`는 한국어 품사명으로 반환된다. `meaning_ko`는 내장 기본 사전에서 `base_form` 기준으로 조회되며, 사전에 없는 단어는 빈 문자열로 반환된다. 단어장은 `backend/vocab.db` SQLite 파일에 저장된다.
분석 결과에는 단어가 처음 등장한 원문 문장인 `example_sentence`도 포함된다. 예문은 단어장 저장, 학습 카드, CSV 내보내기에 함께 사용된다.

## Frontend MVP 실행

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

기본 API 주소는 `http://127.0.0.1:8000`이다. 다른 백엔드 주소를 사용할 때는 `frontend/.env.local`의 `NEXT_PUBLIC_API_BASE_URL` 값을 수정한다.

프론트엔드는 `분석`, `단어장`, `학습`, `정보` 탭으로 구성된다. 탭을 이동해도 현재 분석 결과와 학습 상태는 화면 안에서 유지된다.

## 단어장 저장 기능

1. 백엔드와 프론트엔드를 모두 실행한다.
2. 프론트 화면에서 일본어 원문을 붙여넣고 `분석하기`를 누른다.
3. 분석 결과에서 저장할 단어의 상태를 `모르는 단어`로 바꾼다.
4. `모르는 단어 저장` 버튼을 누르면 선택된 단어가 SQLite 단어장에 저장된다.
5. `저장된 단어장` 섹션에서 목록을 새로고침하고, 상태를 수정하거나 항목을 삭제할 수 있다.
6. `CSV 다운로드` 버튼을 누르면 저장된 단어장이 `jp-vocab-items.csv` 파일로 다운로드된다. CSV는 엑셀에서 한글과 일본어가 깨지지 않도록 UTF-8 BOM을 포함한다.

## 자체 학습 모드

1. 단어장에 `모르는 단어` 상태의 항목을 저장한다.
2. `학습 모드` 섹션에서 `학습 시작`을 누른다.
3. 카드 앞면의 일본어 단어를 보고 뜻과 읽기를 떠올린다.
4. `정답 보기`를 누른 뒤 `맞음` 또는 `틀림`을 선택한다.
5. 학습 대상은 `모르는 단어` 중 `next_review_at`이 비어 있거나 현재 시간이 지난 항목이다.
6. `맞음`을 선택하면 `review_level`이 올라가고 다음 복습일이 1일, 3일, 7일, 14일 간격으로 뒤로 밀린다.
7. `틀림`을 선택하면 `review_level`이 0으로 초기화되고 즉시 다시 복습 대상이 된다.
8. 선택 결과는 `correct_count`, `wrong_count`, `last_reviewed_at`, `next_review_at`에 기록된다.
9. 모든 카드를 끝내면 이번 세션의 맞은 개수와 틀린 개수, 오늘 복습 완료 메시지를 확인할 수 있다.

## AI 문맥 설명

1. 단어장 탭에서 저장된 단어의 `AI 설명 생성` 버튼을 누른다.
2. 서버는 저장된 단어, 뜻, 읽기, 품사, 예문을 OpenAI API에 보내 한국어 문맥 설명을 생성한다.
3. 생성된 설명은 `context_explanation_ko`로 DB에 저장되며, 이후 단어장과 학습 카드에서 다시 볼 수 있다.
4. 이미 설명이 있는 단어는 `AI 설명 다시 생성` 버튼으로 갱신할 수 있다.

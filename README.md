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

헬스체크:

```bash
curl http://localhost:8000/health
```

분석 API 테스트:

```bash
curl.exe -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d "{\"text\":\"彼は怠惰であることを自覚していた。\"}"
```

분석 결과의 `reading`은 히라가나로 반환되고, `part_of_speech`는 한국어 품사명으로 반환된다. 단어장은 `backend/vocab.db` SQLite 파일에 저장된다.

## Frontend MVP 실행

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

기본 API 주소는 `http://127.0.0.1:8000`이다. 다른 백엔드 주소를 사용할 때는 `frontend/.env.local`의 `NEXT_PUBLIC_API_BASE_URL` 값을 수정한다.

## 단어장 저장 기능

1. 백엔드와 프론트엔드를 모두 실행한다.
2. 프론트 화면에서 일본어 원문을 붙여넣고 `분석하기`를 누른다.
3. 분석 결과에서 저장할 단어의 상태를 `모르는 단어`로 바꾼다.
4. `모르는 단어 저장` 버튼을 누르면 선택된 단어가 SQLite 단어장에 저장된다.
5. `저장된 단어장` 섹션에서 목록을 새로고침하고, 상태를 수정하거나 항목을 삭제할 수 있다.
6. `CSV 다운로드` 버튼을 누르면 저장된 단어장이 `jp-vocab-items.csv` 파일로 다운로드된다. CSV는 엑셀에서 한글과 일본어가 깨지지 않도록 UTF-8 BOM을 포함한다.

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

## Frontend MVP 실행

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

기본 API 주소는 `http://127.0.0.1:8000`이다. 다른 백엔드 주소를 사용할 때는 `frontend/.env.local`의 `NEXT_PUBLIC_API_BASE_URL` 값을 수정한다.

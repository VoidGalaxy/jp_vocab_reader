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
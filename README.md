# jp-vocab-reader

일본어 원서/웹소설 학습자를 위한 자동 단어장 생성 웹서비스입니다.

## 현재 상태와 작업 인계

2026-10-07 기준, `0fb5a0f`까지 홈·읽기·복습·단어·덱·학습 계획·통계의 7개 탭 리디자인과 로컬 안정화가 반영되었습니다. 분류 전용 탭은 학습 계획 탭으로 대체되었습니다.

- [현재 구현·검증·남은 위험](docs/project-status.md)
- [다음 작업 로드맵](docs/roadmap.md)
- [학습 계획의 진도·저장·실행 계약](docs/learning-plan.md)
- [클로드·코덱스 공통 작업 인계](docs/work-handoff.md)
- [보존 중인 에셋·QA 자료 정리 후보](docs/asset-cleanup-inventory.md)

이 날짜와 커밋은 문서 작성 기준입니다. 작업을 시작할 때 현재 브랜치와 변경 상태를 다시 확인하세요. 과거 시안·게이트 자료가 로컬에만 있으면 클라우드 작업에서는 보이지 않습니다.

## Recommended Production Deployment

- Frontend: Vercel
- Backend: Render
- Database: Neon PostgreSQL

Use the hosting provider environment variable UI for production settings. `NEXT_PUBLIC_API_BASE_URL` must be the `https://` Render backend URL, and `CORS_ORIGINS` or `CORS_ALLOW_ORIGINS` must include the Vercel frontend origin with `https://`. Do not commit `.env` files or document real `DATABASE_URL`, `JWT_SECRET_KEY`, API keys, or service URLs.

## Dictionary Data

- Built-in Korean meanings and user-defined terms are checked before JMdict fallback data.
- The committed `backend/data/dictionary/jmdict_sample.json` is for development and tests.
- The committed `backend/data/dictionary/en_ko_sample.json` is a small English-to-Korean fallback sample.
- A full local JMdict file can be placed at `backend/data/dictionary/jmdict_full.json`; it is ignored by Git and should not be committed.
- A full Kaikki/Wiktionary English-to-Korean subset can be built as `backend/data/dictionary/en_ko_full.json`; it is ignored by Git and should not be committed.
- In production, Render can also download `en_ko_full.json` (or `.gz`/`.zip`) automatically at startup via `EN_KO_DICTIONARY_URL`, the same way `JMDICT_FULL_JSON_URL` works for JMdict.
- `meaning_ko` is limited to 1-3 short, clean Korean candidates; archaic/broken forms are filtered out.
- An optional krdict (한국어기초사전/우리말샘-style) reverse index (`backend/data/dictionary/krdict_reverse_sample.json`, optionally `krdict_reverse_full.json`) can boost/rank the Kaikki-based candidates. It is auxiliary-only, built and loaded from a local file with no runtime API calls, and `krdict_reverse_full.json` is not committed.
- Dictionary data remains file-based. PostgreSQL stores user data, not the full JMdict, Kaikki/Wiktionary, or krdict datasets.

See [docs/dictionary-data.md](docs/dictionary-data.md) for supported JSON formats, validation scripts, production placement options, and source notice requirements.

## 단어장 탭 UI

- 단어장 탭 상단은 덱 선택, 검색, 상태 필터, 복습 대상 필터, 정렬, 단어 직접 추가만 기본으로 보여주는 compact toolbar로 정리했습니다.
- 덱 만들기/삭제, 덱 공유 JSON 내보내기/가져오기, CSV 다운로드, 사용자 정의 용어 관리는 `덱/공유 관리` 접이식 메뉴 안에서 사용합니다.
- CSV는 엑셀 확인용이고, 앱 간 덱 이동은 덱 공유 JSON 파일을 사용합니다.

## 덱 공유 패키지

- 단어장 탭에서 선택한 덱을 `jp_vocab_reader_deck` JSON 패키지로 내보내고, 다른 사용자가 같은 JSON을 가져와 새 개인 덱으로 복사할 수 있습니다.
- 덱 공유 파일은 이 앱에서 다시 가져오기 위한 JSON이며, CSV 다운로드는 엑셀 확인용으로 별도로 유지됩니다.
- 공유 패키지에는 덱 이름/설명, 단어, 해당 덱 전용 사용자 정의 용어가 포함됩니다.
- 개인 학습 기록인 `status`, `correct_count`, `wrong_count`, `review_level`, `next_review_at`, `last_reviewed_at`, 내부 `id`, `deck_id`, 생성/수정 시각은 포함하지 않습니다.
- 가져오기 시 새 개인 덱이 생성되고, 이름이 겹치면 `덱 이름 (가져옴)`, `덱 이름 (가져옴 2)`처럼 중복되지 않게 저장됩니다.
- 가져온 단어의 학습 상태는 `unknown`, 맞음/틀림 횟수와 복습 레벨은 `0`, 복습 날짜는 비어 있는 상태로 시작합니다.

## 서비스형 구조와 기준 문서

여러 사용자가 각자의 덱, 단어장, 사용자 정의 용어, 학습 기록을 분리해 쓰고 공개 덱을 공유/가져오기 할 수 있는 서비스형 구조를 사용한다. [docs/service-architecture.md](docs/service-architecture.md)는 이 전환의 **초기 설계 초안(historical)**이며, 이후 실제로 바뀐 부분과 어긋나는 서술이 남아 있다. 현재 기준 문서는 용도별로 다음을 참고한다: 공유덱 lexeme/subscription 정책은 [docs/architecture/shared-lexeme-progress-storage.md](docs/architecture/shared-lexeme-progress-storage.md), 베타/릴리스 점검 항목은 [docs/beta-release-checklist.md](docs/beta-release-checklist.md).
백엔드 DB 접근 로직은 `backend/app/repositories`의 기능별 repository로 1차 분리했다.
백엔드는 회원가입/로그인 API와 JWT access token을 지원한다. 개발 모드에서는 토큰이 없는 요청이 기존처럼 `dev@example.local` 사용자로 fallback한다. 운영 환경에서 익명 요청의 권한은 별도로 확인해야 하며, 개발 fallback을 운영 정책으로 간주하지 않는다.
토큰을 보내면 해당 사용자 기준으로 개인 덱, 단어장, 사용자 정의 용어를 조회/수정한다.
프론트엔드는 상단 계정 영역에서 로그인/회원가입/로그아웃을 제공하고, 로그인 성공 시 access token만 `localStorage`에 저장해 이후 API 요청에 사용한다.
저장된 토큰이 만료되었거나 잘못되면 프론트엔드는 현재 토큰에 해당하는 만료 응답인지 확인하고 계정 경계를 초기화한다. 이전 계정의 늦은 조회 응답은 버리고, 복습 세션과 덱 선택도 즉시 비운다. 개발 환경에서는 개발 사용자 데이터를 다시 불러온다. 읽기 원문의 기기 저장은 아직 계정별로 분리되지 않았다.

## 기본 사용 흐름

1. 홈에서 읽기를 열고, 저장할 덱과 일본어 원문을 선택해 분석합니다.
2. 원문 속 단어를 눌러 한국어 뜻을 확인하고 아는/헷갈림/모름/미분류 상태를 바꿉니다.
3. 모름·헷갈림으로 바꾼 새 단어는 자동 저장됩니다. 필요한 단어는 어휘 노트 담기와 선택 저장으로 따로 모을 수도 있습니다.
4. 단어 탭에서 덱별 검색·필터·수정·파일 내보내기를 하고, 덱 탭에서 공개 덱을 찾아 구독합니다.
5. 학습 계획에서 덱 → 기간 → 하루 신규 단어 권장량을 정해 저장하고 복습으로 이어갑니다.
6. 복습에서 답을 확인한 뒤 다시/어려움/보통/쉬움으로 평가하고, 통계에서 날짜별 기록과 어휘 현황을 확인합니다.

## 모바일 레이아웃

- 모바일은 홈 2+2+2 파일 트레이, 읽기 종이 지면과 하단 단어창, 복습 지면, 덱 목록 → 상세 → 뒤로 흐름처럼 화면에 맞는 구성을 사용합니다.
- 긴 일본어 단어, 원문, 예문, 공유 덱 설명은 화면 밖으로 넘치지 않도록 줄바꿈과 가로 스크롤 동작을 보강했습니다.

## 목표

- 일본어 원문 붙여넣기
- 형태소 분석으로 단어 추출
- 중복 단어 제거
- 읽기, 기본형, 품사 표시
- 한국어 뜻 표시
- 원문을 읽으면서 단어 분류
- 아는 단어 / 헷갈리는 단어 / 모르는 단어 / 미분류 상태 관리
- 분류한 단어 저장
- 작품/책/챕터별 덱 관리
- 사용자 정의 용어 사전
- 단어 직접 추가/수정
- 자체 플래시카드 학습 모드
- 복습 스케줄
- 학습 통계와 덱별 진도 표시
- 서울 날짜 기준 학습 기록과 캘린더
- 계정별 기기 저장 학습 계획과 첫 학습 진도
- CSV 내보내기

## 기술 스택

- Frontend: Next.js
- Backend: FastAPI
- Tokenizer: SudachiPy
- Database: SQLite for local development, PostgreSQL for deployment/production

## Backend 실행

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
$env:DATABASE_URL = "sqlite:///./qa_local_session.db"
$env:APP_ENV = "development"
uvicorn app.main:app --reload
```

위 환경변수 두 줄은 PowerShell 예시입니다. 로컬 검증에서는 `.env`에 남은 연결값을 믿지 말고 세션 전용 SQLite를 명시하세요. 로컬에서 Neon/운영 DB에 접근하지 않습니다. 생성한 임시 DB는 서버 종료 후 정리합니다. 데이터 보존이 필요한 개발 DB는 별도로 지정합니다.

Production backend start command, run from `backend`:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Before deployment, set environment variables from `backend/.env.example` in the hosting platform. Do not commit real `.env` files. See [docs/production-deployment.md](docs/production-deployment.md) for production setup details.

AI 보조 기능을 실험하려면 `backend/.env`에 OpenAI API 키를 설정한다. 현재 사용자 UI에서는 개별 단어 AI 설명 기능을 노출하지 않는다. `.env` 파일은 커밋하지 않는다.

```env
DATABASE_URL=
JWT_SECRET_KEY=change-me-in-production
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10080
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.2
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://your-frontend-domain.example
```

DB는 기본적으로 `backend/vocab.db` SQLite 파일을 사용한다. 다른 SQLite 파일을 사용하려면 `backend/.env` 또는 실행 환경에 `DATABASE_URL`을 설정한다.

```env
DATABASE_URL=sqlite:///./vocab.db
```

로컬 개발 DB는 SQLite이며, `DATABASE_URL`이 비어 있으면 기존 `backend/vocab.db`를 계속 사용한다. 배포/운영 DB는 PostgreSQL을 사용한다. PostgreSQL 전환 계획은 [docs/postgres-migration-plan.md](docs/postgres-migration-plan.md)를 참고한다. 기존 SQLite 데이터를 보존해야 할 때만 [docs/postgres-data-migration.md](docs/postgres-data-migration.md)의 마이그레이션 절차를 별도로 검토한다. 배포 전 환경변수, CORS, 빌드, smoke test 점검은 [docs/deployment-checklist.md](docs/deployment-checklist.md)를 참고한다. 실제 호스팅 플랫폼에 올릴 때의 실행 명령과 설정 순서는 [docs/production-deployment.md](docs/production-deployment.md)를 참고한다.

헬스체크:

```bash
curl http://localhost:8000/health
```

분석 API 테스트:

```bash
curl.exe -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d "{\"text\":\"彼は怠惰であることを自覚していた。\"}"
```

분석 결과의 `reading`은 히라가나로 반환되고, `part_of_speech`는 한국어 품사명으로 반환된다. `meaning_ko`는 사전 조회 서비스에서 사용자 정의 용어 뜻, 내장 기본 사전의 `base_form`, `normalized_form`, `surface` 순서로 조회한다. 이 값이 비어 있으면 JMdict 기반 영어 gloss를 Kaikki/Wiktionary 영어→한국어 subset으로 변환해 한국어 뜻 후보로 채운다. JMdict 기반 영어 gloss 원문은 `meaning_ko`를 덮어쓰지 않고 `dictionary_gloss`로 별도 제공하지만 일반 UI에서는 기본 노출하지 않는다. 전체 JMdict JSON을 사용하려면 `backend/data/dictionary/jmdict_full.json` 파일을 직접 넣는다. full 파일이 없거나 파싱할 수 없으면 `backend/data/dictionary/jmdict_sample.json` 샘플 JSON 사전을 사용한다. 찾지 못하면 빈 문자열로 반환된다. 운영 사용자 데이터는 PostgreSQL에 저장하고, SQLite는 로컬 개발 fallback으로만 사용한다.
분석 결과에는 단어가 처음 등장한 원문 문장인 `example_sentence`도 포함된다. 예문은 단어장 저장, 학습 카드, CSV 내보내기에 함께 사용된다.
분석 후처리에서 일부 복합동사와 `명사 + の + 명사` 표현을 학습 후보로 추가한다. 후보 유형은 `quality_tag`로 구분하며, 사용자 정의 용어는 `custom_term`, 복합동사는 `compound_verb`, 명사구 후보는 `noun_phrase_candidate`, 일반 토큰은 `normal`로 반환된다.
앱 시작 시 `기본 단어장` 덱이 자동 생성되며, 기존 저장 단어 중 덱이 없는 항목은 기본 단어장에 자동 연결된다.

## 로컬 JMdict 사전 후보

- `backend/app/jmdict_service.py`는 앱 실행 중 로컬 JSON을 한 번 로드해 kanji/kana 인덱스를 만든다.
- 로딩 우선순위는 `backend/data/dictionary/jmdict_full.json`, `backend/data/dictionary/jmdict_sample.json`, 빈 사전 순서다.
- `jmdict_full.json`은 저장소에 포함하지 않는다. 사용자가 JMdict/EDRDG 라이선스를 확인한 뒤 직접 배치한다.
- 분석 토큰의 `surface`, `base_form`, `normalized_form`, `reading` 중 매칭되는 값이 있으면 gloss 후보를 `; `로 합쳐 `dictionary_gloss`에 반환한다.
- `backend/app/en_ko_dictionary_service.py`는 JMdict 영어 gloss를 Kaikki/Wiktionary 영어→한국어 subset으로 변환한다. AI 자동 호출이나 외부 API 호출은 하지 않는다.
- `backend/app/gloss_ko_mapper.py`는 deprecated 예외 패치로만 유지한다.
- 사전 우선순위는 사용자 정의 용어 `meaning_ko`, 내장 한국어 사전 `meaning_ko`, 로컬 JMdict gloss + Kaikki/Wiktionary 한국어 후보, deprecated 수동 예외 패치, 빈 값 순서다.
- `dictionary_gloss`는 내부 참고/보조 데이터로 유지하며, 화면에서는 한국어 `meaning_ko`를 우선 보여준다.
- JMdict/EDRDG와 Kaikki/Wiktionary의 출처·라이선스 정책은 [docs/dictionary-data.md](docs/dictionary-data.md)를 참고한다.

## 분석 품질 개선

- `立ち上がる`, `差し出す`, `見上げる`, `思い出す`, `目を覚ます` 같은 지정 복합동사는 활용형까지 가능한 범위에서 하나의 학습 후보로 보정한다.
- `嫉妬の魔女`, `銀髪の少女`처럼 조사 `の`로 이어진 명사구는 길이와 품사 조건을 통과하면 명사구 후보로 추가한다.
- `する`, `ある`, `こと`, `これ`, `彼` 같은 기초 기능어/대명사는 기본 분석 결과에서 제외하되, 사용자 정의 용어로 등록된 경우에는 유지한다.

## Frontend MVP 실행

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

기본 API 주소는 `http://127.0.0.1:8000`이다. 다른 백엔드 주소를 사용할 때는 `frontend/.env.local`의 `NEXT_PUBLIC_API_BASE_URL` 값을 수정한다.

Production frontend build:

```bash
cd frontend
npm run build
npm run start
```

Set `NEXT_PUBLIC_API_BASE_URL` to the deployed backend URL before building or deploying the frontend.

Frontend 검사:

```bash
cd frontend
npm test
npm run typecheck
```

`npm test`는 `.mts` 테스트를 Node 내장 타입 제거로 바로 실행하므로 Node 22.18 이상이 필요하다. 로컬 기준 버전은 `frontend/.nvmrc`(24)다.

백엔드 검사는 [작업 인계의 검증 명령](docs/work-handoff.md#검증-명령)을 참고한다. PostgreSQL 지원 코드와 실제 PostgreSQL 검증 완료는 다른 의미다. 이번 안정화의 PostgreSQL 비교는 실제 서버 없이 모킹으로만 검사했다.

## 현재 UI 구조

| 탭 | 역할 | 화면 방향 |
| --- | --- | --- |
| 홈(책상) | 여섯 기능으로 이동, 오늘 복습, 샘플 체험 | 제본 표지와 파일 트레이 |
| 읽기 | 원문 입력·분석, 뜻 확인, 분류·저장 | 데스크톱 C 책 지면, 모바일 종이와 단어창 |
| 복습 | 덱·모드 선택, 답 확인, 네 단계 평가 | 펼친 복습 책 |
| 단어 | 개인 덱과 단어 검색·편집·관리 | 파일 서랍과 일·한 대역 행 |
| 덱 | 공개 덱 탐색·상세·구독·공유 관리 | 검색 가능한 장부 |
| 학습 계획 | 덱·기간·하루량·첫 학습 진도·실행 | C 계획 패드 |
| 통계 | 날짜별 학습 기록과 어휘 현황 | 기록장의 두 화면 |

분류 전용 화면은 없다. 기존 분류 초안은 학습 계획 아래에서 사용자가 선택한 경우에만 내려받기·읽기에서 열기·삭제한다. 읽기의 `/analyze`와 단어 상태 변경은 계속 사용한다.

## 단어장 저장 기능

1. 읽을 원문을 읽기 탭에 입력하고 덱을 골라 분석한다.
2. 단어를 클릭해 뜻을 확인하고 상태를 바꾼다. 처음 저장하는 단어를 모름·헷갈림으로 바꾸면 저장 요청이 나간다.
3. 새 단어를 아는·미분류로 표시하는 것만으로는 개인 단어를 생성하지 않는다. 이미 저장된 단어는 어떤 상태로 바꾸든 갱신된다.
4. 어휘 노트 담기와 선택 저장은 상태 분류와 별도의 저장 경로다. 저장 결과와 이미 저장된 단어 안내를 확인한다.
5. 단어 탭에서 저장된 단어를 수정·삭제하거나 덱별로 검색한다. 고급 백업/파일 내보내기에서 CSV와 공유 JSON을 사용한다.

## 원문과 기기 저장

- 읽기 원문·분석 결과·선택 단어·읽기 위치는 브라우저의 읽기 세션으로 보존된다. 데스크톱·모바일·태블릿 위치 복원이 구현되어 있다.
- 반복 단어를 클릭하면 클릭한 위치 하나만 강조된다. 새로고침 후에는 정확한 등장 위치를 저장하지 않으므로 단어 선택만 복원하고 본문 밑줄은 표시하지 않는다.
- 원문 전체를 서버에 보관하는 기능은 없다. 분석 요청에는 원문이 전송되고, 저장한 단어에는 예문이 포함될 수 있다. 공유 패키지에 원문 전체 필드는 없다.
- 읽기 세션 키는 아직 계정별로 분리되지 않았다. 같은 브라우저에서 계정을 바꿔도 기기의 읽기 자료가 이어질 수 있으므로 완전한 계정 격리라고 설명하지 않는다.
- 학습 계획은 백엔드 환경·로그인 계정별로 이 기기에만 저장한다. 다른 기기와 동기화하지 않는다.

## 상태 의미

- `known`: 사용자가 아는 단어로 표시한 상태. 일반 구독 큐에서는 제외되지만 학습 계획의 미평가 신규 큐에서는 포함될 수 있다.
- `uncertain`: 헷갈리는 단어. 저장되며 학습 대상에 포함된다.
- `unknown`: 모르는 단어. 저장되며 학습 대상에 포함된다.
- `unclassified`: 아직 상태를 고르지 않은 단어. 미평가 신규 학습 대상에 포함될 수 있다.

상태 분류와 복습 평가는 다르다. 읽기에서 상태만 바꿔도 `last_reviewed_at`은 생기지 않으며, 학습 계획의 첫 학습 진도도 늘지 않는다.

## 단어 직접 추가와 수정

1. `단어장` 탭의 `+ 단어 직접 추가` 버튼을 눌러 접이식 직접 추가 폼을 연다.
2. 직접 추가 폼에서 단어, 기본형, 읽기, 품사, 한국어 뜻, 영어 gloss 참고, 예문, 상태, 덱을 직접 입력할 수 있다.
3. 단어 또는 기본형 중 하나만 입력해도 저장할 수 있다. 기본형이 비어 있으면 단어가 기본형으로 저장되고, 상태 기본값은 `모르는 단어`다.
4. `전체 단어장`을 보고 있을 때 직접 추가 덱 기본값은 `기본 단어장`이며, 특정 덱을 보고 있으면 해당 덱이 기본값이다.
5. 추가에 성공하면 폼이 비워지고 다시 접힌다. `취소`를 누르면 저장하지 않고 폼을 닫는다.
6. 저장된 단어 행의 `수정` 버튼을 누르면 단어, 기본형, 읽기, 품사, 한국어 뜻, 영어 gloss 참고, 예문, 상태, 덱을 수정할 수 있다.
7. 자동 분석 결과가 틀렸거나 작품 고유명사를 직접 등록해야 할 때 직접 추가/수정 기능을 사용한다.

## 사용자 정의 용어 사전

1. `단어장` 탭의 `사용자 정의 용어` 섹션에서 `+ 사용자 정의 용어 추가`를 누른다.
2. 용어, 읽기, 품사, 한국어 뜻, 설명, 적용 덱을 입력한다. 덱을 `공통`으로 두면 모든 분석에 적용된다.
3. 특정 덱을 선택한 용어는 해당 덱으로 분석할 때 공통 용어와 함께 적용된다.
4. 분석 시 사용자 정의 용어는 일반 형태소 분석보다 우선되어 하나의 단어로 표시된다.
5. 읽기 분석에서도 사용자 정의 용어는 별도 후보로 구분되며 기존 용어 사전을 재사용한다.
6. 같은 용어와 같은 덱 조합은 중복 생성하지 않고 기존 항목을 사용한다.

## 단어장 검색과 필터

1. `단어장` 탭 상단에서 단어, 한국어 뜻, 영어 gloss, 읽기, 예문을 검색할 수 있다.
2. 상태 필터로 `전체`, `완벽히 아는 단어`, `헷갈리는 단어`, `모르는 단어`, `분류되지 않음`을 빠르게 나눠 볼 수 있다.
3. `복습 대상만 보기`를 켜면 오늘 복습할 항목만 본다.
4. 정렬은 최근 저장순, 오래된 저장순, 많이 틀린순, 많이 맞힌순, 복습 단계 낮은순, 다음 복습 가까운순을 지원한다.
5. 검색과 필터를 바꾸면 목록이 자동으로 다시 불러와진다.

## 덱 관리

1. `단어장` 탭에서 덱 이름과 설명을 입력하고 `덱 만들기`를 누른다.
2. 같은 이름의 덱은 중복 생성되지 않고 기존 덱이 사용된다.
3. `보기` select에서 특정 덱을 선택하면 해당 덱의 단어만 표시된다.
4. 기본 단어장은 삭제할 수 없다.
5. 다른 덱을 삭제하면 해당 덱에 포함된 단어도 함께 삭제된다.
6. `복습` 탭에서도 전체 단어장 또는 특정 덱을 선택해 오늘 복습할 단어를 불러올 수 있다.

## 자체 학습 모드

1. 복습 탭에서 개인/구독 덱과 학습 모드를 선택하고 시작한다.
2. 단어를 보고 읽기·뜻을 떠올린 뒤 답을 공개한다.
3. `다시`, `어려움`, `보통`, `쉬움` 중 하나를 선택한다. 평가는 복습 시각과 다음 복습 일정을 기록한다.
4. 미평가 단어는 신규 대상이며, 구독 덱의 예정 복습(`due_only`)과 구분한다. 첫 평가가 `다시`여도 신규 큐에서 빠지고, 예약 시각이 지난 뒤 복습 대상이 된다.
5. 학습 계획에서 시작할 때 진행 중 세션이 있으면 이어하기/바꾸기/취소를 고른다. 새 큐가 성공적으로 조회되고 비어 있지 않을 때만 바꾼다.
6. 평가별 간격과 기억 완료 기준은 후속 SRS 개선 대상이다. 계획의 첫 학습 완료를 숙련 완료로 해석하지 않는다.

## 학습 통계와 진도

1. 통계에는 `학습 기록`과 `어휘 현황` 두 화면이 있다. 기존 `GET /stats`도 유지된다.
2. `GET /stats/history`와 `GET /stats/history/day`는 서울 날짜 기준의 월·일 기록을 읽기 전용으로 제공한다. 복습 실적은 개인과 구독을 합산한다.
3. 어휘 현황은 개인 단어 기준이며, 오늘 복습 예정 수는 구독 덱을 포함한다. 담은 단어는 지금 남아 있는 개인 단어 기준이다.
4. 조회 실패를 0회나 쉬어간 날로 바꾸지 않는다. 서울 자정 갱신, 계정 전환과 늦은 응답 방어가 구현되어 있다.
5. 학습 계획은 별도의 `GET /learning-plan/progress`로 첫 평가 진도를 읽는다. [계약과 제한](docs/learning-plan.md)을 참고한다.

## AI 보조 기능

개별 단어별 AI 문맥 설명 UI는 현재 비활성화되어 있습니다. 이 앱의 핵심 흐름은 원문 분석, 단어장 저장, 복습, 공유 덱입니다. AI 기능은 이후 문장 단위 해석, 문단 독해 보조, 덱 품질 점검 같은 흐름으로 재검토합니다.

## 공개 공유 덱

- 단어장 탭의 관리 패널에서 현재 선택한 개인 덱을 서버의 공개 공유 덱으로 등록할 수 있습니다.
- 공유 덱에는 단어, 뜻, 읽기, 예문, 해당 덱 전용 사용자 정의 용어만 포함되며 개인 학습 기록은 포함하지 않습니다.
- 덱 탭에서 공개 공유 덱 목록과 상세 미리보기를 확인하고, 원하는 공유 덱을 학습 목록에 추가할 수 있습니다.
- JLPT 추천 어휘 같은 lexeme-mode 공유덱은 개인 덱을 새로 만들지 않고 학습 목록에 구독(subscription)만 추가합니다.
- 기존 legacy 방식으로 발행된 공유덱은 가져오기 시 개인 덱이 생성될 수 있습니다. 자세한 구분은 [docs/architecture/shared-lexeme-progress-storage.md](docs/architecture/shared-lexeme-progress-storage.md)를 참고합니다.
- CSV/JSON 파일 내보내기와 가져오기는 백업이나 수동 이동이 필요한 고급 사용자용 기능이며, 단어장 관리의 고급 백업/파일 내보내기 섹션에서 사용할 수 있습니다.

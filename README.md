# jp-vocab-reader

## Recommended Production Deployment

- Frontend: Vercel
- Backend: Render
- Database: Neon PostgreSQL

Use the hosting provider environment variable UI for production settings. `NEXT_PUBLIC_API_BASE_URL` must be the `https://` Render backend URL, and `CORS_ORIGINS` or `CORS_ALLOW_ORIGINS` must include the Vercel frontend origin with `https://`. Do not commit `.env` files or document real `DATABASE_URL`, `JWT_SECRET_KEY`, API keys, or service URLs.

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

## 향후 서비스형 구조 계획

여러 사용자가 각자의 덱, 단어장, 사용자 정의 용어, 학습 기록을 분리해 쓰고 공개 덱을 공유/가져오기 할 수 있도록 서비스형 구조 전환을 계획한다. 자세한 DB/API/권한 전환 방향은 [docs/service-architecture.md](docs/service-architecture.md)를 참고한다.
백엔드 DB 접근 로직은 `backend/app/repositories`의 기능별 repository로 1차 분리했다.
백엔드는 회원가입/로그인 API와 JWT access token을 지원한다. 개발 모드에서는 토큰이 없는 요청이 기존처럼 `dev@example.local` 사용자로 fallback한다.
토큰을 보내면 해당 사용자 기준으로 개인 덱, 단어장, 사용자 정의 용어를 조회/수정한다.
프론트엔드는 상단 계정 영역에서 로그인/회원가입/로그아웃을 제공하고, 로그인 성공 시 access token만 `localStorage`에 저장해 이후 API 요청에 사용한다.
저장된 토큰이 만료되었거나 잘못되면 프론트엔드는 토큰을 제거하고 개발 모드 사용자 기준 데이터로 다시 전환한다.

일본어 원서/웹소설 학습자를 위한 자동 단어장 생성 웹서비스입니다.

## 기본 사용 흐름

1. 분석 탭에 일본어 원문을 붙여넣고 단어 후보를 추출합니다.
2. 카드에서 완벽히 아는 단어, 헷갈리는 단어, 모르는 단어로 빠르게 분류합니다.
3. 분류한 단어를 선택한 덱에 저장합니다. 저장 후에는 바로 새 분석을 시작할 수 있습니다.
4. 단어장 탭에서 저장한 단어를 검색, 필터링, 수정하고 덱별로 관리합니다.
5. 단어장 탭의 `이 덱 학습하기` 또는 학습 탭에서 오늘 복습, 헷갈리는 단어, 모르는 단어, 전체 학습 모드로 바로 복습합니다.

## Mobile Polish

- 모바일 폭에서 탭, 분석 카드, 단어장 toolbar, 학습 카드, 공유 덱 카드가 터치하기 쉬운 간격과 버튼 크기를 갖도록 정리했습니다.
- 긴 일본어 단어, 원문, 예문, 공유 덱 설명은 화면 밖으로 넘치지 않도록 줄바꿈과 가로 스크롤 동작을 보강했습니다.

## 목표

- 일본어 원문 붙여넣기
- 형태소 분석으로 단어 추출
- 중복 단어 제거
- 읽기, 기본형, 품사 표시
- 한국어 뜻 표시
- 카드 기반 단어 분류
- 완벽히 아는 단어 / 헷갈리는 단어 / 모르는 단어 / 건너뛰기 상태 관리
- 분류한 단어 저장
- 작품/책/챕터별 덱 관리
- 사용자 정의 용어 사전
- 단어 직접 추가/수정
- 자체 플래시카드 학습 모드
- 복습 스케줄
- 학습 통계와 덱별 진도 표시
- CSV 내보내기

## 기술 스택 예정

- Frontend: Next.js
- Backend: FastAPI
- Tokenizer: SudachiPy
- Database: SQLite for local development, PostgreSQL for deployment/production

## Backend MVP 실행

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

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

기본 로컬 개발 DB는 SQLite이며, `DATABASE_URL`이 비어 있으면 기존 `backend/vocab.db`를 계속 사용한다. 배포/운영 DB는 PostgreSQL을 사용한다. PostgreSQL 전환 계획은 [docs/postgres-migration-plan.md](docs/postgres-migration-plan.md)를 참고한다. 배포 전 환경변수, CORS, 빌드, smoke test 점검은 [docs/deployment-checklist.md](docs/deployment-checklist.md)를 참고한다. 실제 호스팅 플랫폼에 올릴 때의 실행 명령과 설정 순서는 [docs/production-deployment.md](docs/production-deployment.md)를 참고한다.

PostgreSQL migration foundation is now available behind `DATABASE_URL`. Leave `DATABASE_URL` empty to keep the existing SQLite development DB, or set a `postgresql://...` URL for a PostgreSQL database after installing backend requirements. See [docs/postgres-migration.md](docs/postgres-migration.md).

SQLite -> PostgreSQL data migration tooling is available in `backend/scripts`, but run it only when existing SQLite data must be preserved. The current production setup starts from a clean PostgreSQL database because `backend/vocab.db` contains only test data. See [docs/postgres-data-migration.md](docs/postgres-data-migration.md).

헬스체크:

```bash
curl http://localhost:8000/health
```

분석 API 테스트:

```bash
curl.exe -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d "{\"text\":\"彼は怠惰であることを自覚していた。\"}"
```

분석 결과의 `reading`은 히라가나로 반환되고, `part_of_speech`는 한국어 품사명으로 반환된다. `meaning_ko`는 사전 조회 서비스에서 사용자 정의 용어 뜻, 내장 기본 사전의 `base_form`, `normalized_form`, `surface` 순서로 조회한다. 이 값이 비어 있으면 JMdict 기반 영어 gloss를 작은 로컬 매핑으로 한국어 뜻 후보로 변환해 채운다. JMdict 기반 영어 gloss 원문은 `meaning_ko`를 덮어쓰지 않고 `dictionary_gloss`로 별도 제공한다. 전체 JMdict JSON을 사용하려면 `backend/data/dictionary/jmdict_full.json` 파일을 직접 넣는다. full 파일이 없거나 파싱할 수 없으면 `backend/data/dictionary/jmdict_sample.json` 샘플 JSON 사전을 사용한다. 찾지 못하면 빈 문자열로 반환된다. 단어장은 `backend/vocab.db` SQLite 파일에 저장된다.
분석 결과에는 단어가 처음 등장한 원문 문장인 `example_sentence`도 포함된다. 예문은 단어장 저장, 학습 카드, CSV 내보내기에 함께 사용된다.
분석 후처리에서 일부 복합동사와 `명사 + の + 명사` 표현을 학습 후보로 추가한다. 후보 유형은 `quality_tag`로 구분하며, 사용자 정의 용어는 `custom_term`, 복합동사는 `compound_verb`, 명사구 후보는 `noun_phrase_candidate`, 일반 토큰은 `normal`로 반환된다.
앱 시작 시 `기본 단어장` 덱이 자동 생성되며, 기존 저장 단어 중 덱이 없는 항목은 기본 단어장에 자동 연결된다.

## 로컬 JMdict 사전 후보

- `backend/app/jmdict_service.py`는 앱 실행 중 로컬 JSON을 한 번 로드해 kanji/kana 인덱스를 만든다.
- 로딩 우선순위는 `backend/data/dictionary/jmdict_full.json`, `backend/data/dictionary/jmdict_sample.json`, 빈 사전 순서다.
- `jmdict_full.json`은 저장소에 포함하지 않는다. 사용자가 JMdict/EDRDG 라이선스를 확인한 뒤 직접 배치한다.
- 분석 토큰의 `surface`, `base_form`, `normalized_form`, `reading` 중 매칭되는 값이 있으면 gloss 후보를 `; `로 합쳐 `dictionary_gloss`에 반환한다.
- `backend/app/gloss_ko_mapper.py`는 샘플 영어 gloss를 한국어 뜻 후보로 매핑한다. AI 자동 호출이나 외부 API 호출은 하지 않는다.
- 사전 우선순위는 사용자 정의 용어 `meaning_ko`, 내장 한국어 사전 `meaning_ko`, 로컬 JMdict gloss 기반 한국어 후보, 빈 값 순서다.
- `dictionary_gloss`는 내부 참고/보조 데이터로 유지하며, 화면에서는 한국어 `meaning_ko`를 우선 보여준다.
- JMdict/EDRDG 라이선스 표기 TODO: 전체 JMdict 데이터 연동 전에 앱/문서/배포물에 필요한 라이선스 문구와 출처 표기를 추가한다.

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

프론트엔드는 `분석`, `단어장`, `공유`, `학습`, `정보` 탭으로 구성된다. 탭을 이동해도 현재 분석 결과와 학습 상태는 화면 안에서 유지된다.

## 현재 UI 구조

- `분석` 탭은 원문 입력, 분석 옵션, 카드 기반 분류, 전체 결과 테이블 토글로 구성된다.
- `단어장` 탭은 덱 선택, 검색/필터/정렬, 접이식 단어 직접 추가, 접이식 사용자 정의 용어, 저장된 단어 목록을 한 화면에서 관리한다.
- `공유` 탭은 공개 공유 덱 목록, 상세 미리보기, 내 단어장으로 가져오기를 제공한다.
- `학습` 탭은 덱 선택 후 오늘 복습할 단어를 플래시카드로 보여주고, 정답 확인 뒤 맞음/틀림을 기록한다.
- `정보` 탭은 전체 학습 통계, 덱별 진도, 앱 목적, 저장 정책, 현재 기능, 이후 TODO를 요약한다.

## 단어장 저장 기능

1. 백엔드와 프론트엔드를 모두 실행한다.
2. 프론트 화면에서 일본어 원문을 붙여넣고 `분석하기`를 누른다.
3. 분석 결과가 카드로 표시되면 `완벽히 아는 단어`, `헷갈리는 단어`, `모르는 단어`, `건너뛰기` 중 하나를 눌러 다음 단어로 넘긴다.
4. 이전 단어를 다시 보고 싶으면 `이전` 버튼으로 돌아가 상태를 바꿀 수 있다.
5. 분류가 끝나면 요약 화면에서 상태별 개수를 확인한다.
6. 저장할 덱을 선택한 뒤 `분류한 단어 저장` 버튼을 누르면 `완벽히 아는 단어`, `헷갈리는 단어`, `모르는 단어`만 저장된다. `분류되지 않음` 또는 건너뛴 단어는 저장하지 않는다.
7. `전체 결과 보기`를 켜면 기존 테이블을 열어 전체 분석 결과를 확인하고 상태를 직접 바꿀 수 있다.
8. `단어장` 탭에서 `전체 단어장` 또는 특정 덱을 선택해 목록을 조회하고, 상태를 수정하거나 항목을 삭제할 수 있다.
9. `CSV 다운로드` 버튼을 누르면 현재 선택한 덱 기준으로 `jp-vocab-items.csv` 파일이 다운로드된다. `전체 단어장`을 선택하면 전체 단어장을 내보낸다. CSV는 엑셀에서 한글과 일본어가 깨지지 않도록 UTF-8 BOM을 포함한다.

## 분류 진행상태 자동 저장

1. 분석 결과와 카드 분류 진행상태는 브라우저 `localStorage`에 자동 저장된다.
2. 저장되는 값은 원문, 저장 덱, `완벽히 아는 단어도 표시` 설정, 분석 결과, 각 단어 상태, 현재 카드 위치, 저장 시각이다.
3. 새로고침하거나 다른 탭으로 이동해도 임시 저장은 유지된다.
4. 앱을 다시 열면 분석 탭에서 이전 분류 결과를 이어하거나 삭제하고 새로 시작할 수 있다.
5. `분류한 단어 저장`이 성공하면 임시 저장은 삭제된다.

## 상태 의미

- `known`: 완벽히 아는 단어. 분석 시 `완벽히 아는 단어도 표시`를 끄면 자동 제외되고, 학습 대상에서도 제외된다.
- `uncertain`: 헷갈리는 단어. 저장되며 학습 대상에 포함된다.
- `unknown`: 모르는 단어. 저장되며 학습 대상에 포함된다.
- `unclassified`: 분류되지 않음. 분석 카드에서 건너뛴 단어와 기본 미분류 상태이며 저장 대상에서 제외된다.

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
5. 분석 카드와 전체 결과 테이블에서 사용자 정의 용어에는 `사용자 용어` 뱃지가 표시된다.
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
6. `학습` 탭에서도 전체 단어장 또는 특정 덱을 선택해 오늘 복습할 단어를 불러올 수 있다.

## 자체 학습 모드

1. 단어장에 `모르는 단어` 또는 `헷갈리는 단어` 상태의 항목을 저장한다.
2. `학습 모드` 섹션에서 `학습 시작`을 누른다.
3. 카드 앞면의 일본어 단어를 보고 뜻과 읽기를 떠올린다.
4. `정답 보기`를 누른 뒤 `맞음` 또는 `틀림`을 선택한다.
5. 학습 대상은 `모르는 단어`와 `헷갈리는 단어` 중 `next_review_at`이 비어 있거나 현재 시간이 지난 항목이다.
6. `맞음`을 선택하면 `review_level`이 올라가고 다음 복습일이 1일, 3일, 7일, 14일 간격으로 뒤로 밀린다.
7. `틀림`을 선택하면 `review_level`이 0으로 초기화되고 즉시 다시 복습 대상이 된다.
8. 선택 결과는 `correct_count`, `wrong_count`, `last_reviewed_at`, `next_review_at`에 기록된다.
9. 모든 카드를 끝내면 이번 세션의 맞은 개수와 틀린 개수, 오늘 복습 완료 메시지를 확인할 수 있다.

## 학습 통계와 진도

1. 백엔드는 `GET /stats`로 전체 또는 특정 덱의 학습 통계를 제공한다.
2. 통계는 전체 단어, 완벽히 아는 단어, 헷갈리는 단어, 모르는 단어, 오늘 복습할 단어, 총 맞음/틀림, 평균 복습 레벨, 진행률을 포함한다.
3. `deck_id`를 지정하면 해당 덱 기준으로 계산하고, 지정하지 않으면 전체 단어장과 덱별 요약을 함께 반환한다.
4. 학습 탭 상단에서는 선택한 덱의 오늘 복습 수와 진행률을 보여주고, 정보 탭에서는 전체 통계와 덱별 통계를 보여준다.

## AI 보조 기능

개별 단어별 AI 문맥 설명 UI는 현재 비활성화되어 있습니다. 이 앱의 핵심 흐름은 원문 분석, 단어장 저장, 복습, 공유 덱입니다. AI 기능은 이후 문장 단위 해석, 문단 독해 보조, 덱 품질 점검 같은 흐름으로 재검토합니다.

## 공개 공유 덱

- 단어장 탭의 관리 패널에서 현재 선택한 개인 덱을 서버의 공개 공유 덱으로 등록할 수 있습니다.
- 공유 덱에는 단어, 뜻, 읽기, 예문, 해당 덱 전용 사용자 정의 용어만 복사되며 개인 학습 기록은 포함하지 않습니다.
- 공유 탭에서 공개 공유 덱 목록과 상세 미리보기를 확인하고, 원하는 공유 덱을 현재 사용자 계정의 개인 덱으로 가져올 수 있습니다.
- 가져오기가 성공하면 새로 생성된 덱이 단어장 탭의 선택 덱으로 즉시 반영됩니다.
- 가져온 덱의 단어 학습 상태는 `unknown`, 정답/오답/복습 단계는 0, 다음 복습일은 비어 있는 상태로 시작합니다.
- 일반 사용자의 덱 공유는 공유 탭의 서버형 직접 공유를 사용합니다.
- CSV/JSON 파일 내보내기와 가져오기는 백업이나 수동 이동이 필요한 고급 사용자용 기능이며, 단어장 관리의 고급 백업/파일 내보내기 섹션에서 사용할 수 있습니다.

## Development Database

The backend uses SQLite for local development when `DATABASE_URL` is empty. PostgreSQL is the deployment/production database selected with a `postgresql://` or `postgres://` `DATABASE_URL`.

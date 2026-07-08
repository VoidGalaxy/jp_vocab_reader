# 개발 로드맵

## 단어장 탭 UI 정리

- 완료: 단어장 탭 상단을 compact toolbar로 정리하고, 덱 선택/검색/필터/정렬/단어 직접 추가만 기본 노출한다.
- 완료: 덱 만들기/삭제, 덱 공유, CSV 다운로드, 사용자 정의 용어 관리는 `덱/공유 관리` 접이식 메뉴로 이동했다.

## 덱 공유 패키지 진행

- 완료: 선택한 덱을 `jp_vocab_reader_deck` JSON으로 내보내고, 같은 JSON을 가져와 새 개인 덱으로 복사할 수 있다.
- 완료: 덱 공유 패키지에는 단어와 해당 덱 전용 사용자 정의 용어를 포함하고, 개인 학습 기록은 포함하지 않는다.
- TODO: 사용자 계정 기반 공유 덱 소유권/권한 관리를 추가한다.
- TODO: 공개 덱 마켓, 검색, 다운로드 수, 버전 관리를 추가한다.

## 서비스형 구조 전환

- 완료: 서비스형 구조 설계 완료. 자세한 내용은 [service-architecture.md](service-architecture.md)를 참고한다.
- 완료: DB access layer 정리. SQLite 쿼리를 기능별 repository 계층으로 분리했다.
- 완료: auth foundation. `users` 테이블, 개발용 기본 사용자, `GET /me`를 추가했다.
- 완료: user-scoped-data. `decks`, `vocab_items`, `custom_terms`를 `user_id` 기준으로 마이그레이션하고 repository 필터를 적용했다.
- 완료: auth-api. 회원가입/로그인 API, JWT access token, 토큰 사용자 처리와 dev user fallback을 추가했다.
- 완료: auth-ui. 프론트엔드 로그인/회원가입/로그아웃 UI와 access token 저장/전송을 추가했다.
- TODO: 운영용 `JWT_SECRET_KEY` 설정과 토큰 보안 정책 정리
- TODO: PostgreSQL 전환 검토
- TODO: 공개 덱 마켓

## Service Stability Pass

- 완료: 로그인/회원가입/로그아웃 후 현재 사용자 기준으로 덱, 단어장, 사용자 정의 용어, 통계, 학습 목록을 다시 불러오는 흐름을 점검했다.
- 완료: 잘못되었거나 만료된 access token은 프론트 공통 API 클라이언트에서 제거하고, 초기 사용자 확인 시 개발 모드 사용자로 복구한다.
- 완료: 단어 생성/수정 시 현재 사용자가 소유하지 않은 `deck_id`는 `404`로 거부하도록 보강했다.
- 완료: 공유 덱 가져오기 후 생성된 개인 덱을 즉시 선택하고 단어장/사용자 정의 용어 목록을 갱신한다.
- 완료: 공유 덱 publish/import가 개인 학습 기록을 공유하지 않고, 가져온 단어의 학습 상태를 초기화하는지 TestClient로 확인했다.
- 완료: `python -m compileall app`, `npm run build`, 인증/분석/저장/공유/가져오기/데이터 분리 API 스모크 검증을 통과했다.

## Postgres Readiness

- 완료: `DATABASE_URL` 기반 DB 설정을 추가했다. 값이 없으면 기존 `backend/vocab.db` SQLite 파일을 사용한다.
- 완료: `sqlite:///...` 형식으로 SQLite 파일 경로를 지정할 수 있게 했다.
- 완료: 초기 단계에서는 `postgresql://...` URL을 명확한 미지원 오류로 처리했다. 이후 postgres-migration-foundation 단계에서 psycopg 기반 연결 분기를 추가했다.
- 완료: SQLite 연결에 `row_factory`, timeout, `PRAGMA foreign_keys = ON`을 일관되게 적용했다.
- 완료: startup schema 보강 흐름을 `initialize_database`, `ensure_schema`, `ensure_auth_schema`, `ensure_core_schema`, `ensure_user_scoped_columns`, `ensure_shared_deck_schema` 중심으로 정리했다.
- 완료: [postgres-migration-plan.md](postgres-migration-plan.md)에 PostgreSQL 전환 이유, 작업 목록, 데이터 마이그레이션 전략, 위험 요소, 추천 순서를 정리했다.

## Postgres Migration Foundation

- 완료: `DATABASE_URL`이 비어 있으면 SQLite를 유지하고, `postgresql://` 또는 `postgres://`이면 psycopg 기반 PostgreSQL 연결을 사용하도록 분기했다.
- 완료: repository의 `?` placeholder와 `cursor.lastrowid` 사용을 보존하기 위한 최소 query adapter를 추가했다.
- 완료: PostgreSQL용 핵심 테이블 생성 로직을 추가하고, dev user/default deck bootstrap이 PostgreSQL에서도 동작하도록 정리했다.
- 완료: [postgres-migration.md](postgres-migration.md)에 SQLite fallback, DATABASE_URL 설정, API 확인 목록, 다음 단계 데이터 마이그레이션 범위를 문서화했다.

## postgres-data-migration-and-test

- Done: PostgreSQL smoke-test guide added in [postgres-data-migration.md](postgres-data-migration.md).
- Done: `backend/scripts/check_postgres_connection.py` verifies a PostgreSQL `DATABASE_URL` without printing the password or full URL.
- Done: `backend/scripts/migrate_sqlite_to_postgres.py` copies `backend/vocab.db` into PostgreSQL, preserves IDs where possible, prints before/after row counts, and stops by default if the target already has data.
- Done: PostgreSQL startup compatibility was tightened so the dev-user seed path no longer emits SQLite-only `AUTOINCREMENT` DDL.
- Done: Empty PostgreSQL feature smoke testing completed successfully.
- Done: SQLite data migration is skipped for this deployment because the existing `backend/vocab.db` contains only test data; production starts from a clean PostgreSQL database.
- Next: Keep the migration script available for future cases where SQLite contains meaningful user data.

## Deployment Readiness

- 완료: 백엔드 환경변수 읽기를 `app.settings`로 정리하고 `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `OPENAI_API_KEY`, `CORS_ALLOW_ORIGINS`를 문서화했다.
- 완료: CORS 허용 origin을 환경변수 기반으로 설정하고 기본 개발 origin을 `localhost`와 `127.0.0.1`로 정리했다.
- 완료: `/health` 응답에 앱 이름, DB 종류, 인증 상태를 추가하되 민감정보는 노출하지 않는다.
- 완료: `backend/.env.example`, `frontend/.env.example`, [deployment-checklist.md](deployment-checklist.md)를 준비했다.
- 완료: README에 env 예시 복사, 로컬 실행 순서, 배포 체크리스트 링크를 추가했다.

## Deployment Check

- 완료: `CORS_ORIGINS`를 배포용 권장 CORS 환경변수로 문서화하고 기존 `CORS_ALLOW_ORIGINS`도 호환 alias로 유지했다.
- 완료: `backend/.env.example`, README, `docs/deployment-checklist.md`의 환경변수와 smoke test 흐름을 현재 SQLite/FastAPI/Next.js 구조 기준으로 정리했다.
- 완료: 배포 전 backend compile, `/health` smoke, frontend build 점검 흐름을 확인했다.

## Production Deployment Setup

- Done: Vercel frontend + Render backend + Neon PostgreSQL deployment test completed successfully.
- 완료: backend production start command를 `uvicorn app.main:app --host 0.0.0.0 --port $PORT`로 정리하고 `backend/Procfile`에 추가했다.
- 완료: `docs/production-deployment.md`에 frontend/backend 배포 절차, 환경변수, CORS, SQLite 주의점, smoke test, troubleshooting 순서를 정리했다.
- 완료: README에 로컬 실행과 production 실행을 구분하고 production deployment 문서 링크를 추가했다.
- 다음 TODO: 실제 배포, PostgreSQL 실제 전환, 운영용 DB 백업, AI 사용량 제한, 공유 덱 신고/관리 기능.

## Dictionary Quality Upgrade

- Done: JMdict full dictionary loader path and sample fallback policy documented.
- Done: Dictionary validation and normalization scripts prepared.
- Done: JMdict/EDICT source notice added to the Info tab and dictionary data docs.
- Done: Kaikki/Wiktionary English-to-Korean fallback subset support added for JMdict gloss translation.
- Done: Production can now download `en_ko_full.json` (or `.gz`/`.zip`) at startup via `EN_KO_DICTIONARY_URL`, mirroring the existing `JMDICT_FULL_JSON_URL` flow, with automatic sample fallback on missing/invalid data.
- Done: `meaning_ranker` limits `meaning_ko` to 1-3 clean, learner-facing Korean candidates and filters archaic/broken forms.
- Done: Added an optional krdict (한국어기초사전/우리말샘-style) reverse index as boost-only auxiliary data -- it ranks/corrects Kaikki-based candidates but is not a translation engine on its own; built and loaded locally, no runtime API calls.
- Done: Added a krdict API fetcher foundation (`scripts/fetch_krdict_api.py`) -- a development/preprocessing-only script that can call the real 국립국어원 Open API in small, resumable batches (or replay a committed sample response with no key/network needed) to produce raw JSONL for `build_krdict_reverse_index.py`.
- Done: Added `scripts/build_krdict_seed_from_en_ko.py` to mine large Korean seed lists from the Kaikki-derived `en_ko_full.json`, plus a curated core-vocabulary seed sample, so `fetch_krdict_api.py` can build a real-world-sized local `krdict_reverse_full.json` instead of only the small built-in seed list.
- Done: Added KRDIC reverse dictionary delivery support -- `ensure_krdict_reverse_file()` downloads/decompresses/validates `krdict_reverse_full.json` (or `.gz`/`.zip`) via `KRDIC_REVERSE_URL` at Render startup, mirroring the existing JMdict/en_ko download flow exactly, with automatic sample fallback on missing/invalid data and no runtime krdict API calls.
- Done: Added an automatic `meaning_ko` quality filter (`app/meaning_quality_filter.py`) instead of hand-fixing individual lemmas -- scores Kaikki/krdict candidates down for generically risky English glosses (`point`/`tip`/`thing`/etc.) and risky Korean words, uses krdict strictly as a validator/booster (never a sole candidate generator for a risky gloss), suppresses gloss-based translation for single hiragana filler/interjection tokens (e.g. `え`), and leaves `meaning_ko` empty rather than showing a low-confidence guess when every candidate scores too low (e.g. `先` no longer shows 점/포인트/팁-style noise).
- Done: Rebalanced the quality filter's precision/recall -- added a high-confidence safety-net fallback (best safe Kaikki-sourced candidate survives even under threshold, never a risky/KRDIC-only one), capped the gloss-rank penalty and raised `MAX_GLOSSES_PER_LOOKUP` so legitimate senses buried behind multi-language JMdict noise are reachable (fixes `先` losing all meaning), added a tiny built-in-dictionary hotfix for `手繰る` (zero Kaikki/krdict coverage for its senses), and suppressed bare "noun+の+noun" phrase candidates (e.g. 自分の身) unless the phrase itself has an independent dictionary meaning (new `known_phrase` quality tag).
- TODO: Prepare the actual `jmdict_full.json` file.
- TODO: Build and upload the actual `en_ko_full.json` file to production file storage.
- TODO: Build and upload an actual `krdict_reverse_full.json` file (subject to 국립국어원 공공데이터 이용조건) to production file storage and set `KRDIC_REVERSE_URL` on Render.
- TODO: Place the full dictionary file in the production deployment environment.
- TODO: Continue improving Korean fallback coverage from Kaikki/Wiktionary data and small exception patches.
- TODO: Add frequent missing words after tester feedback.

## Per-word AI UX Removal

- 완료: per-word AI explanation UX removed/hidden. 단어장과 학습 화면에서 개별 단어 AI 설명 생성/표시 UI를 숨겼다.
- 완료: analysis classification panel closes after successful save. 분석 탭에서 분류 저장 성공 후 분류 카드 영역을 닫는다.
- 완료: shared deck metadata labels polished. 공유 덱 카드와 상세에서 `단어 수`, `용어 수`, `공유된 횟수` 문구를 사용한다.
- 향후 AI 사용 후보: 문장 단위 해석, 문단 단위 독해 보조, 학습자가 헷갈린 단어 기반 추천, 덱 품질 점검.

## Study Session Improvements

- 완료: 단어장 탭에서 선택한 덱을 바로 학습 탭으로 넘기는 `이 덱 학습하기` 흐름을 추가했다.
- 완료: 학습 탭에 오늘 복습, 헷갈리는 단어, 모르는 단어, 전체 학습 모드를 추가했다.
- 완료: 학습 탭에서 선택한 덱 이름, 학습 모드, 오늘 복습/헷갈리는 단어/모르는 단어 수를 명확히 보여준다.
- 완료: 학습 카드와 학습 완료 화면을 단어 암기 중심으로 정리하고, 완료 후 다시 학습하기/단어장으로 가기/분석 탭으로 가기 액션을 추가했다.

## Mobile Polish

- 완료: 모바일 폭에서 탭을 가로 스크롤형으로 정리하고 주요 버튼의 터치 영역을 보강했다.
- 완료: 분석, 단어장, 학습, 공유 탭의 카드/입력/목록 간격과 긴 일본어 텍스트 줄바꿈을 개선했다.
- 완료: 단어장과 사용자 정의 용어 테이블은 기능을 유지하면서 모바일 가로 스크롤과 첫 열 고정으로 읽기성을 보강했다.

## Reader Mode & Word Status Display

- 완료: 분석 탭에 "읽기 모드"를 추가했다 (`ReaderMode.tsx`). 기존 카드/전체 결과 테이블은 그대로 두고, 분석된 token을 원문 순서대로(문장 단위는 `example_sentence` 그룹핑으로 구분) 자연스럽게 이어 보여준다. 백엔드 변경 없이 프론트에서만 구현했다.
- 완료: 단어 상태(known/uncertain/unknown/unclassified)별 색상과 조사/기능어/기호 계열 품사에 대한 무채색 처리를 추가했다 (`TokenChip.tsx`).
- 완료: 읽기 모드에서 단어를 클릭하면 하단 시트/팝업(`TokenDetailSheet.tsx`)으로 기본형·읽기·품사·한국어 뜻·현재 상태를 보여주고, 기존 분류 저장 흐름(`onStatusChange`)을 그대로 재사용해 상태를 변경할 수 있다. 새 API는 추가하지 않았다.
- 완료: 단어장(및 분석 결과 테이블)의 예문에서 해당 단어를 surface → base_form → normalized_form 순으로 매칭해 하이라이트한다 (`HighlightedExample.tsx`). `dangerouslySetInnerHTML` 없이 순수 React 노드 조합으로 렌더링한다.

## 원칙

- 첫 MVP는 작고 안정적으로 만든다.
- 원문 전체를 서버 DB에 저장하지 않는다.
- 저작권 리스크를 줄이기 위해 분석 후 원문은 폐기하고, 사용자가 저장한 단어장 데이터만 보관한다.
- AI는 핵심 단어장 흐름을 방해하지 않는 선택형 보조 기능으로 검토한다.
- 기능을 넓히기 전에 형태소 분석, 중복 제거, 저장, CSV 내보내기, 자체 학습 모드의 기본 흐름을 먼저 검증한다.
- 단어만 외우는 흐름에서 벗어나 원문 예문을 함께 보는 문맥 기반 학습으로 확장한다.

## 1단계: 프로젝트 기본 구조 확인

- 기존 `frontend`, `backend`, `docs` 구조를 유지한다.
- Next.js와 FastAPI 실행 방식을 정리한다.
- 개발용 SQLite DB 위치와 환경변수 정책을 정한다.
- README는 별도 작업 범위에서 정리한다.

## 2단계: 백엔드 MVP 골격

- FastAPI 앱을 구성한다.
- 헬스체크 API를 추가한다.
- SQLite 연결과 마이그레이션 방식을 정한다.
- 단어장 테이블을 만든다.
- 기본 에러 응답 형식을 정한다.

## 3단계: 형태소 분석 기능

- SudachiPy를 백엔드에 연결한다.
- `/analyze` API를 구현한다.
- 표면형, 기본형, 읽기, 품사를 추출한다.
- 조사, 조동사, 기호 등 제외 품사 필터를 적용한다.
- 기본형 기준 중복 제거를 구현한다.
- 원문이 DB에 저장되지 않는지 확인한다.

## 4단계: 뜻 데이터 연결

- MVP에서 사용할 한국어 뜻 제공 방식을 정한다.
- 우선 작은 로컬 사전 또는 내부 매핑으로 시작한다.
- 뜻이 없는 단어의 표시 정책을 구현한다.
- 향후 사전 데이터 확장 가능성을 남긴다.

## 5단계: 단어장 저장 API

- `GET /vocab-items`를 구현한다.
- `POST /vocab-items`를 구현한다.
- `lemma` 기준 중복 저장 방지 정책을 구현한다.
- 저장 데이터에 원문 전체나 긴 문맥이 포함되지 않도록 검증한다.
- 단어가 처음 등장한 짧은 원문 예문을 함께 저장한다.

## 6단계: CSV 내보내기 API

- `GET /vocab-items/export.csv`를 구현한다.
- UTF-8 CSV를 생성한다.
- 일본어와 한국어가 깨지지 않는지 확인한다.
- 기본 컬럼은 표면형, 기본형, 읽기, 품사, 한국어 뜻, 학습 상태, 저장일로 둔다.

## 7단계: 프론트엔드 MVP 화면

- 원문 입력 화면을 만든다.
- 분석 요청과 로딩 상태를 구현한다.
- 분석 결과 목록을 표시한다.
- 아는 단어 / 모르는 단어 분류 UI를 만든다.
- 모르는 단어 저장 버튼을 구현한다.
- 단어장 목록 화면을 만든다.
- CSV 내보내기 버튼을 연결한다.
- 분석, 단어장, 학습, 정보 탭으로 화면을 정리한다.

## 8단계: 통합 검증

- 긴 원문, 짧은 원문, 빈 입력을 테스트한다.
- 제외 품사 필터가 의도대로 작동하는지 확인한다.
- 같은 기본형이 중복 표시 또는 중복 저장되지 않는지 확인한다.
- 저장된 단어장이 CSV로 정상 다운로드되는지 확인한다.
- 저장된 모르는 단어를 자체 학습 모드에서 복습하고 맞음/틀림 기록이 누적되는지 확인한다.
- 분석 결과와 저장된 단어장, 학습 카드에서 예문이 함께 표시되는지 확인한다.
- 탭 이동 후에도 분석 결과와 학습 상태가 유지되는지 확인한다.
- 서버 DB에 원문 전체가 남지 않는지 확인한다.

## 9단계: 자체 학습 모드

- `vocab_items`에 맞음/틀림 횟수와 마지막 복습 시간을 저장한다.
- 작품/책/챕터별 덱을 만들고, 저장/조회/학습/CSV 내보내기를 덱 기준으로도 수행한다.
- `GET /study-items`로 모르는 단어와 헷갈리는 단어 중심의 학습 목록을 제공한다.
- `POST /study-items/{item_id}/review`로 맞음/틀림 결과를 기록한다.
- 맞음/틀림 결과에 따라 `review_level`과 `next_review_at`을 조정하는 기본 복습 스케줄을 제공한다.
- 프론트엔드에 플래시카드형 복습 UI를 만든다.
- 정답 확인 시 단어의 읽기, 뜻, 품사, 기본형과 함께 원문 예문을 표시한다.
- 개별 단어 AI 설명 UI는 현재 숨기고, AI는 이후 문장/문단 독해 보조로 재검토한다.
- 복잡한 간격 반복 알고리즘은 이후 단계로 미룬다.

## 완료된 추가 개선

- 단어장 탭에서 단어를 직접 추가할 수 있다.
- 저장된 단어의 표면형, 기본형, 읽기, 품사, 뜻, 예문, 상태, 덱을 수정할 수 있다.
- 자동 분석 결과가 틀렸거나 작품 고유명사를 등록해야 하는 경우 직접 추가/수정으로 보정할 수 있다.
- 분석 결과를 카드 UI로 하나씩 넘기며 완벽히 아는 단어, 헷갈리는 단어, 모르는 단어, 건너뛰기로 빠르게 분류할 수 있다.
- `uncertain` 상태를 추가하고, 헷갈리는 단어도 저장과 학습 대상에 포함한다.
- 단어 직접 추가 폼은 접이식으로 변경해 단어장 검색/필터 흐름을 방해하지 않도록 정리했다.
- 분석 탭의 카드 분류 진행상태를 localStorage에 임시 저장하고 새로고침 후 이어할 수 있다.
- 덱 삭제 시 해당 덱에 포함된 단어도 함께 삭제하는 정책으로 변경했다.
- 사용자 정의 용어 사전을 추가해 작품 고유명사와 웹소설 용어를 DB 기반으로 등록하고 분석 결과에 우선 반영할 수 있다.
- 프론트 UI의 탭, 카드, 버튼, 입력창, 메시지, 모바일 레이아웃을 MVP 사용 흐름에 맞게 정리했다.
- JMdict 샘플 JSON 로컬 사전을 연동해 일반 분석 토큰에 `dictionary_gloss` 사전 뜻 후보를 표시하고 저장할 수 있다.
- JMdict gloss 기반 한국어 뜻 후보 생성을 추가해 `meaning_ko`가 비어 있을 때 작은 로컬 매핑으로 한국어 후보를 채운다.
- 복합동사와 `명사 + の + 명사` 명사구 후보 감지를 추가하고 `quality_tag`로 분석 후보 유형을 구분한다.
- `jmdict_full.json`이 있으면 전체 JMdict 파일을 우선 로드하고, 없거나 실패하면 샘플 사전으로 fallback하는 로더 구조를 추가했다.
- `GET /stats`와 프론트 학습 현황/덱별 진도 표시를 추가했다.

## 10단계: MVP 이후 후보

- 사용자 계정과 개인 단어장 분리
- 예문 저장 정책 검토
- 단어 빈도와 출현 횟수 표시
- 사전 데이터 확장
- Anki 전용 내보내기
- 문장 단위 해석 보조
- 문단 단위 독해 보조
- 학습자가 헷갈린 단어 기반 추천
- 덱 품질 점검
- 전체 JMdict 데이터 파일 배치 및 라이선스 표기 검증
- JMdict/EDRDG 라이선스 표기 정리
- 고급 간격 반복 기능
- 파일 업로드
- 웹소설 URL 가져오기
- 브라우저 확장 프로그램

## 다음 TODO

- 실제 원서 긴 문단 기준으로 분석 결과 품질과 카드 분류 속도를 점검한다.
- 작은 로컬 사전 데이터를 점진적으로 보강한다.
- 향후 AI 보조 기능의 비용과 응답 실패율을 관찰해 운영 기준을 정한다.

## MVP 완료 기준

- 사용자가 일본어 원문을 붙여넣어 단어 후보를 받을 수 있다.
- 불필요한 토큰이 기본 필터로 제외된다.
- 중복 단어가 기본형 기준으로 제거된다.
- 사용자가 완벽히 아는 단어, 헷갈리는 단어, 모르는 단어를 저장할 수 있다.
- 작품/책/챕터별 덱으로 단어장을 나누어 관리할 수 있다.
- 저장된 단어장을 검색, 필터, 정렬로 빠르게 찾을 수 있다.
- 저장된 단어장을 CSV로 내보낼 수 있다.
- 저장된 모르는 단어와 헷갈리는 단어를 앱 안에서 플래시카드처럼 복습할 수 있다.
- 원문 전체가 서버 DB에 저장되지 않는다.

## Shared Deck Market Foundation

- 완료: 공개 공유 덱 테이블과 repository를 추가했다.
- 완료: 개인 덱을 공개 공유 덱으로 등록하는 `POST /decks/{deck_id}/publish` API를 추가했다.
- 완료: 공개 공유 덱 목록/상세 조회와 내 덱으로 가져오기 API를 추가했다.
- 완료: 프론트엔드에 공유 탭과 현재 덱 공유 등록 UI를 추가했다.
- 완료: 공유 덱에는 개인 학습 기록과 원문 전체를 포함하지 않는 정책을 적용했다.
- 완료: sharing UX polish. CSV/JSON 백업 기능을 고급 접이식 섹션으로 분리하고, 공유 덱 가져오기 완료 피드백과 상세 닫기 동작을 추가했다.

다음 TODO:

- 공유 덱 검색
- 좋아요/평점
- 신고/검수
- 페이지네이션
- 버전 업데이트 정책
- 저작권/원문 저장 제한 정책

## PostgreSQL Readiness

- Done: SQLite remains the active development database.
- Done: Startup schema creation and compatibility migrations are grouped in `backend/app/database.py`.
- Done: Safe SQLite `ALTER TABLE ADD COLUMN` helpers prevent duplicate migration failures.
- Done: Personal repository access was checked for `user_id` scoping; public shared deck reads remain the explicit exception.
- Done: PostgreSQL migration risks and recommended steps are documented in [postgres-readiness.md](postgres-readiness.md).

Next TODO:

- Introduce SQLAlchemy models while still running on SQLite.
- Preserve API responses through the model transition.
- Add Alembic only after model metadata is stable.
- Test a real PostgreSQL connection in a later branch.

## Text Coverage Dashboard

- 완료: 분석 결과 상단에 텍스트 커버리지 카드(`CoverageSummary.tsx`)를 추가했다. 의미 있는 어휘 token(조사/조동사/기호/공백은 이미 백엔드에서 제외됨) 기준으로 아는/헷갈리는/모르는/미분류 단어 수와 커버리지 %를 unique 기준으로, 등장 횟수 기준 커버리지는 보조 지표로 함께 보여준다.
- 완료: `/analyze` 응답에 토큰별 `occurrence_count`(같은 base_form이 원문에 등장한 횟수)와 응답 전체의 `ignored_token_count`(조사/기호 등 제외된 원시 토큰 수)를 추가했다. 새 엔드포인트 없이 기존 `/analyze` 응답만 확장했고 DB 스키마는 변경하지 않았다.
- 완료: 분석 결과에서 unknown → uncertain → unclassified 순으로, 같은 상태 안에서는 등장 횟수·뜻 존재 여부·명사/동사/형용사 여부를 기준으로 우선순위를 매겨 "이 텍스트에서 먼저 볼 단어" 목록(`PriorityVocabList.tsx`)을 최대 10개 보여준다. 상태 변경은 기존 `onStatusChange`/분류 저장 흐름을 그대로 재사용한다.
- 완료: 커버리지와 우선 학습 목록은 현재 선택된 분석/저장 덱(`selectedDeckId`) 기준으로 계산한다 (`coverageUtils.ts`의 `getTokenStatus`). base_form → normalized_form → surface 순서로 단어를 묶고, 세션에서 직접 분류한 상태를 최우선으로, 없으면 해당 덱에 저장된 단어 상태를 사용한다.
- 완료: 읽기 모드에서 단어 상태를 바로 클릭해 바꾸면 같은 `tokens` state를 공유하는 커버리지 카드도 즉시 갱신된다.
- TODO: occurrence 기준 우선순위 정렬을 명사구/복합동사/사용자 정의 용어의 실제 반복 등장까지 더 정확히 반영한다.
- TODO: 커버리지 계산을 텍스트 저장 없이 세션 간에도 이어볼 수 있게 할지 검토한다.

## Reading Study Mode Redesign

- 완료: 기존 단어 chip 나열형 읽기 모드를 원문을 읽는 화면에 가깝게 다시 디자인했다 (`ReaderMode.tsx`, `TokenChip.tsx`). 문장은 자연스러운 줄바꿈(`word-break: keep-all`, 넉넉한 줄간격)으로 흐르고, 단어는 여전히 문장 흐름 안에서 클릭 가능하다. 백엔드 변경은 없다.
- 완료: 상태별 강조 색상을 채도를 낮춘 톤으로 조정했다. `known`은 거의 일반 텍스트(아주 옅은 초록 배경), `uncertain`은 옅은 주황, `unknown`은 옅은 빨강, `unclassified`는 옅은 파랑/회색, 조사·기능어·기호는 흐린 무채색으로 표시해 읽기 흐름을 방해하지 않는다.
- 완료: "모르는/헷갈리는 단어만 강조" 보기 옵션을 추가했다. 켜면 `known`/`unclassified` 단어는 일반 텍스트처럼 보이고 `unknown`/`uncertain`만 옅은 배경으로 강조된다.
- 완료: 선택한 단어는 단어장 예문 하이라이트(`.example-highlight`)와 같은 계열의 노란 톤으로 강조해 두 화면의 하이라이트 스타일을 통일했다.
- 완료: 단어 상세 패널(`TokenDetailSheet.tsx`)은 모바일에서는 기존처럼 하단 시트로, 데스크톱(약 641px 이상)에서는 화면을 어둡게 가리는 모달 대신 우측에 도킹된 카드로 표시해 원문을 계속 읽을 수 있게 했다. 표시 정보(surface/기본형/읽기/뜻/상태)와 상태 변경 버튼, 저장/분류 연동 로직은 기존 그대로 재사용했고 영어 gloss는 노출하지 않는다.
- 완료(이후 separate-reading-study-tab 단계에서 대체됨): 분석 결과 영역에 "읽기 모드 / 분류 모드" 두 개의 보기 탭을 추가했었다. 이후 읽기 모드는 별도 "읽기" 상위 탭으로 분리되었다 (아래 "Analyze/Reading Tab Split" 참고).
- 완료: 분석 폼 아래에 "입력한 원문은 본인 학습용으로 사용하세요. 원문 전체는 서버에 저장되지 않으며, 공유 덱에도 원문 전체가 포함되지 않습니다." 문구를 작게 추가했다.
- 확인: 원문 전체를 저장하는 새 서버 컬럼/엔드포인트를 추가하지 않았다. 분석 시 토큰별 `example_sentence`(짧은 문장 단위)만 기존대로 사용되고, 분류 진행상태 임시 저장은 여전히 브라우저 `localStorage`에만 남는다. 공유 덱 export/import(`DeckPackage`)에는 단어/사용자 정의 용어 필드만 포함되고 원문 전체 필드는 없다.
- TODO: "아는 단어 강조 끄기/켜기", "기능어 흐리게 보기" 같은 추가 보기 옵션은 이후 사용자 피드백을 보고 검토한다.
- TODO: 우선 학습 단어 추천 고도화와 Anki export는 이번 범위에 포함하지 않았다.

## Analyze/Reading Tab Split

- 완료: 분석 탭과 읽기 탭의 역할을 분리했다. **분석 탭**은 원문 입력 → 분석 → 단어 분류/저장 흐름에 집중하고, **읽기 탭**은 덱 선택 → 원문 입력 → 원문을 읽으면서 단어를 클릭해 뜻을 확인하고 상태를 바꾸는 흐름에 집중한다.
- 완료: 분석 탭에서 "이 텍스트에서 먼저 볼 단어"(`PriorityVocabList`)와 읽기 모드(`ReaderMode`)를 기본 화면에서 제거했다. 분석 후에는 커버리지 요약 카드 다음에 곧바로 단어 분류 카드가 이어지도록 정리해, 분류 작업이 다른 영역에 밀리지 않게 했다. `PriorityVocabList.tsx`와 `coverageUtils.buildPriorityStudyList`는 나중에 재사용할 수 있도록 코드는 남기되 분석 화면에서는 호출하지 않는다.
- 완료: 상위 탭에 "읽기" 탭을 새로 추가했다 (`ReadingTab.tsx`). 덱 선택 → 원문 textarea → "읽기 분석" 버튼 → 저작권 안내 문구 → 기존 `ReaderMode`(Reading Study Mode) 순으로 구성되며, `ReaderMode`/`TokenChip`/`TokenDetailSheet`/`HighlightedExample`은 그대로 재사용하고 새로 중복 구현하지 않았다.
- 완료: 읽기 탭의 분석 요청은 기존 `/analyze`를 그대로 재사용하되 `include_known: true`로 호출해, 이미 아는 단어도 원문 흐름 안에 표시되게 했다(단, `known` 상태는 읽기 모드의 옅은 톤 스타일 그대로라 과하게 강조되지 않는다). 응답 토큰의 상태는 선택한 덱의 저장된 단어 상태(`getTokenStatus`, base_form → normalized_form → surface 매칭)로 즉시 반영된다.
- 완료: 읽기 탭에서 단어 상태를 클릭해 바꾸면 별도 저장 버튼 없이 바로 반영된다 -- 같은 덱에 이미 저장된 단어면 `PATCH /vocab-items/{id}`로 상태를 갱신하고, 처음 보는 단어면 `POST /vocab-items`로 새로 저장한다. 새 백엔드 엔드포인트는 추가하지 않았다.
- 완료: 분석 탭 결과 화면에 "이 원문을 읽기 탭에서 보기" 버튼을 추가했다. 현재 입력한 원문과 선택한 덱을 브라우저 메모리(React state)에서 그대로 읽기 탭으로 넘기고 바로 분석을 실행한다 -- 서버 저장이나 `localStorage`/`sessionStorage` 없이 같은 페이지 안에서만 상태를 전달하므로 원문이 브라우저 밖으로 나가지 않는다.
- 완료: 읽기 탭에도 "입력한 원문은 본인 학습용으로 사용하세요. 원문 전체는 서버에 자동 저장되지 않으며 공유 덱에 포함되지 않습니다." 안내 문구를 작게 추가했다.
- 완료: 모바일에서 결과가 있으면 원문 입력 폼을 "원문 입력 접기/펼치기" 버튼으로 접을 수 있게 했다 (분석 완료 시 기본으로 접힘).
- 확인: 이번 작업에서도 원문 전체를 저장하는 서버 컬럼/엔드포인트를 추가하지 않았고, `DeckPackage`/공유 덱 스키마에는 여전히 원문 전체 필드가 없다.

## JLPT Starter Shared Decks

- 완료: N5~N1 레벨별 "추천 어휘" 공유덱을 만들기 위한 오프라인 파이프라인을 추가했다. 공식 JLPT 어휘 목록이 아니라는 점과 출처/라이선스 정책은 [jlpt-decks.md](jlpt-decks.md)에 정리했다.
- 완료: 손으로 작성한 N5 샘플 30단어 CSV(`backend/data/jlpt/n5_sample.csv`)와 이를 기존 deck package(`jp_vocab_reader_deck`) 형식 JSON으로 변환하는 `backend/scripts/build_jlpt_deck_package.py`를 추가했다. 뜻/읽기가 CSV에 없으면 기존 `app.analyzer`/사전 파이프라인을 재사용해 보강하고, 새 DB 스키마나 런타임 외부 API 호출은 추가하지 않았다.
- 완료: 생성된 deck package JSON을 dev 사용자 기준으로 개인 덱 생성 + 공유덱 등록까지 이어주는 선택 스크립트 `backend/scripts/seed_jlpt_shared_decks.py`를 추가했다. 기존 `import_deck_package`/`publish_deck` repository 함수를 그대로 재사용하며, 기본은 읽기 전용 dry-run이고 `--apply`를 명시해야 실제 DB에 기록한다.
- TODO: N4~N1 CSV는 출처/라이선스가 확인된 뒤에만 추가한다. 대량 목록은 확인 전까지 커밋하지 않는다.

## JLPT Deck Quality Pipeline

- 완료: 외부에서 확보한 JLPT 단어 CSV를 바로 공유덱에 넣지 않고, 정규화 → 1차 한국어 뜻 생성/검수용 audit CSV → 사람 검수 → deck package 순서로 이어지는 파이프라인을 추가했다. 전체 흐름과 warning 코드 설명은 [jlpt-decks.md](jlpt-decks.md)에 정리했다.
- 완료: `backend/scripts/normalize_jlpt_word_list.py` — 다양한 컬럼명(word/expression/kanji, kana/furigana, english/gloss 등)의 외부 CSV를 `level,surface,reading,source_meaning_en,source_meaning_ko,source_note` 표준 컬럼으로 정규화한다.
- 완료: `backend/scripts/build_jlpt_quality_draft.py` — 정규화된 CSV를 기존 `app.analyzer`/사전 파이프라인(JMdict + Kaikki/en_ko fallback + krdict 부스팅 + meaning quality filter)으로 처리해 `generated_meaning_ko`, `dictionary_found`, `meaning_confidence`, `warnings`(10종: NO_DICTIONARY_MATCH/EMPTY_MEANING/READING_MISMATCH/LOW_CONFIDENCE_MEANING/RISKY_KOREAN_CANDIDATE/TOO_MANY_MEANINGS/MULTIPLE_SENSES/SOURCE_EN_MISMATCH/DUPLICATE_SURFACE/DUPLICATE_SURFACE_READING)을 채운 검수용 draft CSV를 만든다. 외부 `source_meaning_en`/`source_meaning_ko`는 참고용일 뿐 그대로 신뢰하지 않으며, 사전 매칭이 없을 때만 검증을 거쳐 보조적으로 사용한다.
- 완료: `backend/scripts/build_jlpt_deck_from_reviewed_csv.py` — 사람이 검수해 `meaning_ko`를 확정한 CSV(`level,surface,reading,meaning_ko,example_sentence,example_translation_ko,note_ko`)를 기존 deck package 형식 JSON으로 변환한다. `meaning_ko`는 검수 결과를 그대로 신뢰하고, base_form/품사 등 구조 필드만 analyzer로 보강한다.
- 완료: `.gitignore`에 `backend/data/jlpt/{raw,work,reviewed,packages}/`와 생성 파일 패턴을 추가해 검수 전/후 CSV와 생성된 deck package JSON이 커밋되지 않게 했다. `n5_sample.csv`, `samples/`, `README.md`만 커밋 가능하다.

# E-5c 실제 계정 삭제와 API 지연 요청 통합 검증

2026-10-20 · `codex/fsrs-srs-replacement` · HEAD `e2c07f8` · 검토 대기.

근거:
- 사용자 E-5c 지시(2026-10-19 17:36Z)
- `E5A_CONTRACT.md`·`E5A_REPORT.md`, `E5B_CONTRACT.md`·`E5B_REPORT.md`
- APPROVAL_REQUEST 1절, EXECUTION_PLAN P-ACC1~4

이번 단위는 **테스트·검증·문서만**이다. 제품 결함은 발견하지 못했고, 제품 코드는 바꾸지 않았다.

이번에 하지 않은 것:
- 실제 사용자 삭제, 운영·Neon·기존 `vocab.db` 접근
- FSRS 활성화
- 스테이징·커밋·푸시·병합

## 1. 방식

- E-5a 검사는 계정 행만 지우는 합성 삭제를 썼다. 이번에는 **E-5b의 실제 preview → apply**로 계정을 지우고, 실제 API 인증과 저장소 경로를 이어서 검증했다.
- 대기·해제 지점은 테스트 장치에만 두었다. 제품 코드에 QA 훅은 없다.
  - **순서 1 (인증 → 정지 → 삭제 커밋 → 재개)**: 테스트가 인증 의존성(`current_user_id`·`required_user_id`)을 감싼다. 인증 성공 직후 별도 연결에서 실제 삭제를 실행한 뒤 요청을 이어 간다.
  - **순서 2 (쓰기 잠금 → 삭제 대기 → 쓰기 커밋 → 삭제 재계산)**:
    - 테스트가 E-5a 잠금 함수 `begin_account_write`를 감싸, 요청의 쓰기가 잠금을 잡은 직후 멈추게 한다.
    - 그 사이 실제 삭제(미리보기 지문으로 apply)를 별도 스레드·연결로 시작한다.
    - 삭제가 기다리는 것을 증명한 뒤 풀어 준다.
    - 대기 증명: SQLite는 삭제 쪽 `BEGIN IMMEDIATE` 요청 뒤 0.3초 미완료, PG는 삭제 backend의 미승인 잠금과 `pg_blocking_pids()`가 쓰기 쪽 backend PID를 가리키는 것.
- 모든 대기는 15초 제한이다. 실패해도 멈춘 작업을 풀고 종료를 기다린다. 두 작업의 결과·예외·종료를 모두 모은다.
- **요청 종류**: 모든 경로는 ASGI 인프로세스(httpx `ASGITransport`)로 실행했다. 대표 4경로는 **실제 HTTP**(uvicorn을 루프백 소켓에 띄움, 같은 프로세스)로도 실행했다. 외부 프로세스 서버는 테스트 정지 지점을 둘 수 없어 쓰지 않았다.
- **판정**(오류만으로 통과시키지 않음):
  - 상태 코드와 detail
  - 삭제 결과·사유
  - 대상 계정 잔존 0: 전 표의 `user_id` 행, 소유 공유 덱, scope 소유 실행, 사용자 행. 로그·영수증·이전 기록·원장 포함.
  - 다른 계정·dev 계정·공유·전역 자료 불변
  - 500·교착·잠금 시간 초과·예상 밖 예외는 실패로 본다.
- **오래된 토큰**: 순서 1 뒤 같은 토큰으로 다시 요청하면 `401 invalid token`이고 쓰기 0이다. 인증은 토큰이 있으면 dev 계정으로 돌아가지 않고, 계정 id는 재사용되지 않는다.

## 2. 경로 목록과 자동 대조

- `app/main.py`의 쓰기 라우트(POST·PUT·PATCH·DELETE)는 23개다.
- 검사 대상은 20개 라우트이고, 기존 라우트의 추가 사례가 2개 있어 사례는 22개다.
  - 구독 단어 최초 평가(진도 행 없음)
  - 덱을 지정하지 않은 단어 생성(기본 덱 경로)
- 제외 3개와 근거:
  - `register_user`: 새 계정 생성, 새 id
  - `login_user`: 토큰 발급만, 계정 자료 쓰기 없음
  - `analyze`: 읽기 전용 분석
- 검사가 소스에서 라우트 목록을 읽어 다음을 자동 대조한다.
  - 사례 목록 + 제외 = 실제 라우트
  - 사례 목록 = E-5a 테스트의 분류 목록(테스트 소스에서 읽음)
  - 새 쓰기 라우트가 생기면 실패한다.
- API가 없는 계정 쓰기: 이전 적용·롤백·재전환은 운영자 도구뿐이다. 저장소 수준의 실제 겹침은 E-5b 경합에서 확인했다(삭제 ↔ 평가·단어 생성·구독·발행·이전 적용·롤백·재전환, 두 순서, PG 대기 상대 증명).
- 인증과 대상 조회의 연결:
  - 인증은 자체 연결에서 사용자 행만 확인한다. 쓰기는 다른 연결에서 계정 잠금 안에 실행된다.
  - 순서 1은 바로 이 사이에 삭제를 넣은 경우다.
  - 덱·용어·단어의 수정·설명 경로는 대상 행 조회 결과로 기존 404 문구를 낸다.

## 3. 경로별 결과

SQLite와 실제 PG가 모든 경로에서 같았다.
- **순서 1**: 삭제 결과 / API 상태 / detail. 다음 경우를 빼면 모두 대상 잔존 0, 다른 계정 불변, 오래된 토큰 401이다.
  - `held`(소유자 검토)는 계정이 남아 있으므로 요청이 정상 처리된다.
- **순서 2**: 쓰기 상태 / 삭제 결과 / 대기 증명. 후속 처리는 다음과 같다.
  - `plan_changed`: 쓰기를 보존한 뒤 새 미리보기로 다시 삭제했다(잔존 0).
  - `deleted`: 쓰기가 대상 행 id를 바꾸지 않아 계획이 같으므로 그대로 삭제됐다(잔존 0).
  - `blocked`: 계정이 남는다.

| 사례 (라우트) | 순서 1 | 순서 2 | 증거 |
| --- | --- | --- | --- |
| vocab_create (`post_vocab_item`, 대상 덱 지정) | deleted / 404 / deck not found | 200 / plan_changed / 대기 | ASGI·HTTP, SQLite·PG |
| vocab_create_default_deck (같은 라우트, 덱 없음) | deleted / 404 / account_not_found | 200 / plan_changed / 대기 | ASGI, SQLite·PG |
| vocab_update (`patch_vocab_item`) | deleted / 404 / vocab item not found | 200 / deleted / 대기 | ASGI, SQLite·PG |
| explain (`explain_vocab_item`) | deleted / 404 / vocab item not found | 200 / deleted / 대기 | ASGI, SQLite·PG |
| vocab_delete (`remove_vocab_item`) | deleted / 404 / account_not_found | 204 / plan_changed / 대기 | ASGI, SQLite·PG |
| personal_review (`post_study_review`) | deleted / 404 / account_not_found | 200 / plan_changed / 대기 | ASGI·HTTP, SQLite·PG |
| deck_create (`post_deck`) | deleted / 404 / account_not_found | 200 / plan_changed / 대기 | ASGI, SQLite·PG |
| deck_update (`patch_deck`) | deleted / 404 / deck not found | 200 / deleted / 대기 | ASGI, SQLite·PG |
| deck_delete (`remove_deck`) | deleted / 404 / account_not_found | 200 / plan_changed / 대기 | ASGI, SQLite·PG |
| term_create (`post_custom_term`) | deleted / 404 / account_not_found | 200 / plan_changed / 대기 | ASGI, SQLite·PG |
| term_update (`patch_custom_term`) | deleted / 404 / custom term not found | 200 / deleted / 대기 | ASGI, SQLite·PG |
| term_delete (`remove_custom_term`) | deleted / 404 / account_not_found | 204 / plan_changed / 대기 | ASGI, SQLite·PG |
| package_import (`post_deck_package_import`) | deleted / 404 / account_not_found | 200 / plan_changed / 대기 | ASGI, SQLite·PG |
| publish (`post_deck_publish`) | deleted / 404 / account_not_found | 200 / blocked: shared_deck_owner_review / 대기 | ASGI, SQLite·PG |
| subscribe (`post_shared_deck_import`) | deleted / 404 / account_not_found | 200 / plan_changed / 대기 | ASGI, SQLite·PG |
| progress (`patch_shared_deck_word_progress`) | deleted / 404 / account_not_found | 200 / deleted / 대기 | ASGI, SQLite·PG |
| lexeme_review (`post_shared_deck_word_review`) | deleted / 404 / account_not_found | 200 / plan_changed / 대기 | ASGI·HTTP, SQLite·PG |
| first_lexeme_review (같은 라우트, 최초 평가) | deleted / 404 / account_not_found | 200 / plan_changed / 대기 | ASGI, SQLite·PG |
| meaning_feedback (`post_meaning_feedback`) | deleted / 404 / account_not_found | 200 / plan_changed / 대기 | ASGI, SQLite·PG |
| app_feedback (`post_app_feedback`) | deleted / 404 / account_not_found | 200 / blocked: app_feedback_retention_review / 대기 | ASGI·HTTP, SQLite·PG |
| unpublish (`remove_shared_deck`, 소유자) | held(소유자 검토) / 200 | 200 / blocked: shared_deck_owner_review / 대기 | ASGI, SQLite·PG |
| republish (`republish_shared_deck_endpoint`, 소유자) | held(소유자 검토) / 200 | 200 / blocked: shared_deck_owner_review / 대기 | ASGI, SQLite·PG |

- 잠금 순서(순서 2): 요청이 계정 잠금을 먼저 잡고(SQLite BEGIN IMMEDIATE, PG users 행 FOR UPDATE), 삭제가 같은 잠금에서 기다린다. PG 대기 종류는 모두 `transactionid ShareLock`이다.
- 앱 피드백이 먼저 저장되면 기존 보류 정책, 공유 덱이 먼저 발행되면 기존 소유자 검토 정책이 그대로 적용됐다. 보류를 삭제 완료로 표시하거나 정책을 우회하지 않았다.
- 구독의 가져오기 계수(다른 계정 공유 덱의 `import_count`)는 **쓰기 자체**가 올린 값이다. 다른 계정 불변 비교는 쓰기 뒤·새 삭제 전 상태를 기준으로 했다. 삭제 자체는 다른 계정의 어떤 행도 바꾸지 않았다. 발행은 전역 lexeme을 만들지만 삭제가 차단된다.

## 4. SQLite와 PG의 제약 차이

- SQLite는 SRS 표 6개에만 FK가 있다. PG는 FK 30개(대부분 CASCADE)다.
- E-5b 도구는 명시 삭제와 잔존 검사로 범위를 정하므로, 두 DB의 최종 상태와 API 결과가 같았다.
- E-5a 보고의 PG 차이(합성 users 삭제 뒤 CASCADE로 카드가 먼저 사라져 수정 경로 3개가 missing 문구)는 이번 실제 삭제에서는 두 DB 모두 같은 문구로 나타났다. 실제 삭제가 카드를 명시적으로 지우기 때문이다.

## 5. 검증 수

| 구분 | 결과 |
| --- | --- |
| SQLite E-5c | **46개 통과**: 목록 대조 1, 순서 1 22, 순서 2 22, 실제 HTTP 1(대표 4경로 하위 사례) |
| 실제 PG E-5c (보호 장치·제한 역할·실행 표식·소유 증명) | **45개 통과**: 순서 1 22, 순서 2 22(모두 대기 상대 증명), 실제 HTTP 1(4경로) |
| 변형 검사(메모리) | **8/8 검출**: 단어 쓰기의 계정 경계 제거, 실제 삭제 절차 생략(users 행만 삭제), 삭제의 계정 잠금 제거, 오래된 계획 허용 |
| 백엔드 전체(PG opt-in 해제) | **1094개 실행: 975개 통과·119개 건너뜀**(PG 전용 E-5c 45 포함 건너뜀) |
| 실제 PG 묶음(모든 `*_real` + 커서·E-2c 단위) | **112개 통과**, 예상 실패 1(알려진 업그레이드 교착), 건너뜀 0. E-5a·E-5b·E-5c 포함 |
| 회귀 스크립트 | 9종 rc=0. 전용 임시 폴더를 쓰고 제거 |
| 프론트 | 159/159, 타입 검사 통과. 미수정이라 빌드 생략 |
| diff 검사 | 통과(기존 CRLF 경고만). 새 파일 뒤 공백·탭 0 |

**모킹**: 이번 검증에 결과 모킹은 없다. 설명 생성 외부 호출(`generate_context_explanation`)만 고정 문자열로 바꿨다. 정지 지점은 위 1절의 테스트 래퍼다.

**미검증**:
- 외부 프로세스로 띄운 HTTP 서버: 테스트 정지 지점을 둘 수 없다.
- 실제 HTTP의 나머지 18사례: ASGI로만 확인했다.
- 여러 서버·워커 프로세스가 동시에 쓰는 운영 배치

## 6. 검사표 상태 (P-ACC)

| 항목 | 상태 | 근거 |
| --- | --- | --- |
| P-ACC1 계정 삭제 | 실제 DB 확인(서버 DB 한정) | E-5b 실제 삭제·잔존 0·다른 계정 불변 |
| P-ACC2 삭제 경합 | 실제 DB 확인 | E-5b 경합 7종 × 두 순서, E-5c 순서 2 |
| P-ACC3 삭제 뒤 지연 쓰기(D1) | 실제 DB 확인(서버 DB 한정) | E-5c 순서 1, 22사례 × SQLite·PG, 오래된 토큰 401 |
| P-ACC4 공유 덱 소유 계정 | 자동 삭제 보류만 확인 | 수동 처리 경로는 미구현(승인 범위 밖) |

## 7. 변경 파일과 정리

- 테스트(새 파일):
  - `backend/tests/_e5c_support.py`
  - `backend/tests/test_e5c_account_deletion_api.py`
  - `backend/tests/test_e5c_account_deletion_api_real.py`
- 문서: 이 보고서, REPORT 23절
- 제품 코드 변경 없음.
- 실제 PG:
  - 정상 teardown 뒤 빈 DB 보호 검사로 사용자 객체 0을 확인했다.
  - 이번에 시작한 서버만 PID·실행 파일·자료 경로를 확인한 뒤 종료했다. 55432 리스너 없음.
  - 테스트용 uvicorn은 테스트 안에서 종료를 확인했다.
- `vocab.db` 불변, c1 폴더 19개 그대로, 다른 임시 폴더 0. 출력에 토큰·비밀번호·연결 문자열·사용자 원자료 없음.

## 8. 범위 밖 (완료로 표시하지 않음)

이 결과는 **서버 DB 삭제 경계**의 검증이다. 다음은 완료가 아니다.
- 요청 접수·본인 확인·결과 통지
- 법정 보존 판단(앱 피드백 포함)
- 공유 덱 수동 처리
- 백업·복제본·WAL·브라우저 파기
- 운영 실행 승인

E-5c 검토 대기.

## 9. 검증 보정 두 건 (2026-10-20)

테스트만 바꿨다(`_e5c_support.py`, `test_e5c_account_deletion_api.py`). 제품 코드는 그대로다.

**1. FSRS 구독 평가 사례 추가.** 기존 `lexeme_review`·`first_lexeme_review`(rating만, 호환 경로)는 유지했다.
- `fsrs_first_lexeme_review`: request_id·session_id·명시적 `expected_card_version: null`
- `fsrs_lexeme_review`: 실제 FSRS 최초 평가로 만든 구독 카드를 현재 버전으로 평가
- 순서 1: 두 사례 모두 deleted / 404 / account_not_found, 잔존 0, 오래된 토큰 401.
- 순서 2: 두 사례 모두 200 / plan_changed / 대기. DB 관측 결과:
  - 최초 평가: progress `srs_engine=fsrs`, 버전 0→1, FSRS 로그 1(card_version_before 0), 그 로그를 가리키는 영수증 1
  - 기존 카드: 버전 1→2, 로그 +1(card_version_before 1), 영수증 1

**2. 쓰기 보존 판정 보강.**
- 수정 전: 순서 2는 API 성공과 삭제 결과만 봤다. `deleted` 사례(뜻 변경 등)는 쓰기 효과를 관측하지 않아, 뜻 변경을 버려도 통과했다(Codex 재현).
- 수정 후: 삭제가 계정 잠금을 얻은 직후, 자료를 읽거나 지우기 전에 별도 연결로 사례별 효과를 DB에서 읽는다. 24사례 모두 생성·수정·삭제·평가 효과를 확인한다.
  - 같은 효과를 요청 전에도 읽어, 요청 전 값과 기대값이 다른지 확인한다.
  - 관측은 잠금 획득 뒤 읽기만 하므로 잠금 순서는 그대로다. PG 대기 상대는 24/24 모두 `transactionid ShareLock`이었다.
- `republish`는 효과가 보이도록 먼저 비공개로 만든 공유 덱에서 시작한다. 결과는 기존과 같다(보류 / 200, 차단).

**하네스 결함 보정(테스트 전용).** 순서 2를 먼저 실행하면, 잠금 함수가 패치된 동안 `app.main`이 처음 import됐다. 그때 import된 저장소가 테스트 래퍼를 계속 들고 있었고, 다음 사례(PG `package_import`)가 멈추지 않아 실패했다. 기존 46·45 통과는 순서 1이 먼저 돌아 가려져 있었다. 지금은 열거 전에 `app.main`을 import하고, 원본이 아닌 잠금 함수를 가진 모듈이 있으면 실패시킨다.

| 구분 | 결과 |
| --- | --- |
| SQLite E-5c | **50개 통과**: 목록 대조 1, 순서 1 24, 순서 2 24, 실제 HTTP 1. 순서 2 단독(먼저 실행) 24 통과 |
| 실제 PG(보호 장치) 추가·영향 사례 | **27개 통과**: 순서 2 24(먼저 실행, 대기 상대 24/24), 순서 1 FSRS 2·republish 1 |
| 변형(메모리) | **SQLite 3/3·PG 3/3 검출**: 뜻 변경 버림, 최초 평가 FSRS 우회(legacy 생성), 기존 카드 FSRS 우회(legacy 처리) |

**미검증**: PG 순서 1의 나머지 21사례와 실제 HTTP(바뀌지 않음, 기존 결과), 백엔드 전체·프론트·빌드·회귀 스크립트(제품 미수정이라 생략, 단계 마감 때 실행), 수정 전 검사의 뜻 누락 통과는 Codex 재현에 따랐고 여기서 다시 돌리지 않았다.

**정리**: 시작한 PG(PID 10052, `C:/JV_Tools/pgdata-e2`)만 빈 DB 확인 뒤 종료, 55432 리스너 없음. 임시 SQLite 폴더 0, 기존 폴더 19개 그대로. `vocab.db`·`.env` 미사용.

E-5c 재검토 대기.

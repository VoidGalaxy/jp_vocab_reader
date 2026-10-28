# Gate C-2a 보고: 서버 구현 (새 카드, 구독 최초 평가, 큐 제외·selected)

작성: 2026-10-10. 계약 `CONTRACT.md` v0.2(7절 11개 채택, recent R2, 회차 미루기 D4) + 9절(구현 세부·100개 한도 보충).
상태: **C-2a 서버 구현·검증 완료, 검토 대기.** C-2b·C-2c(클라이언트), 실제 사용자 이전, 기본 FSRS 활성화, 스테이징·커밋·푸시·병합은 하지 않았다.

## 0. 시작 상태

| 항목 | 값 |
| --- | --- |
| 브랜치 / HEAD | `codex/fsrs-srs-replacement` / `e2c07f8` (B-1·B-2·C-1 작업은 미커밋 그대로) |
| AGENTS.md | 없음 |
| 기존 변경 | `docs/roadmap.md`, 미추적 에셋·목업·`references/plans/`·tsbuildinfo 보존 |

## 1. 변경 파일 (C-2a)

| 파일 | 변경 |
| --- | --- |
| `backend/app/srs/storage.py` | `account_uses_fsrs`, `fresh_fsrs_values`, `initialize_new_personal_cards`(같은 트랜잭션, FSRS 계정만, 손대지 않은 legacy 기본 행만) |
| `backend/app/repositories/vocab_repository.py` | `create_or_update_vocab_item`의 **새 행 INSERT 뒤에만** 초기화. 기존 행 갱신 경로는 무변경 |
| `backend/app/repositories/deck_package_repository.py` | 패키지 가져오기: 같은 트랜잭션에서 새로 만든 덱의 카드 초기화 |
| `backend/app/repositories/shared_deck_repository.py` | legacy 공유 덱 복사: 같은 방식 |
| `backend/app/srs/reviews.py` | `validate_first_review_request`, `find_receipt(first_review=)`, `record_fsrs_review(receipt_version=…)`(CAS 버전과 영수증 해시 버전 분리), `record_first_lexeme_review` |
| `backend/app/repositories/lexeme_repository.py` | `record_lexeme_review(first_review=True)`면 legacy 지연 생성 전에 최초 평가 경로로 분기. 그 밖의 경로는 순서·동작 무변경 |
| `backend/app/main.py` | 구독 평가: `model_fields_set`으로 명시적 null만 최초 평가. 개인 평가: 명시적 null은 422 |
| `backend/app/schemas.py` | `StudyQueueItem.card_version`·`config_version`·`participation` null 허용, `materialized` 추가. 응답에 `next_due_at_excluded` |
| `backend/app/srs/queue.py` | `exclude_card`, `mode=selected` + `card_id`, 미생성 구독 단어 신규 출제(`SERVE_UNMATERIALIZED`), `excluded_by_request`·`next_due_at_excluded`, 신규 허용량 기준에 출제 가능한 미생성 포함 |
| `backend/app/srs/queue_cursor.py` | 바인딩에 `filters_hash`(제외·selected 목록), `selected` 모드 허용 |
| `backend/tests/test_srs_c2_server.py` (신규) | 22개 |
| `backend/tests/test_srs_queue.py` | C-1 고정 자료 조정 4곳(아래 4-2) |
| `backend/tests/test_srs_schema.py` | 업그레이드 검사의 "구 코드" 흉내에 새 카드 초기화도 끄도록 1곳 |
| `docs/plans/srs-improvement/gate-c2/CONTRACT.md` | 9절 추가(100개 한도 중단 계약, 구현 세부) |

스키마·저장 키·프론트·의존성은 바꾸지 않았다. `database.import_deck_package`(사용자 인자가 없는 옛 함수, 라우트 미연결)는 손대지 않았다.

## 2. API 결과·호환 [실행 확인, SQLite]

### 2-1. 새 개인 카드

| 경우 | 결과 |
| --- | --- |
| FSRS 계정 단어 담기·패키지 가져오기·legacy 공유 덱 복사 | 새 카드 `fsrs·active·fresh·version 0·상태 NULL·effective due NULL`. known으로 담아도 active, 분류는 known 유지 |
| 같은 단어 다시 담기(갱신) | 평가된 카드의 SRS 열 그대로 |
| legacy·shadow·설정 없음 계정 | legacy 그대로 |
| 기존 legacy 카드(다른 카드 생성·가져오기 중) | 무변경 |

### 2-2. 구독 최초 평가 (`POST /shared-decks/{sid}/words/{lid}/review`)

| 요청 | 결과 |
| --- | --- |
| progress 없음 + 명시적 `expected_card_version: null` + `request_id`·`session_id` | 200. progress 생성(fsrs·fresh, 분류 `unclassified` 유지) + FSRS 평가 한 트랜잭션. 로그 1(`is_first_review=1`, `card_version_before=0`), 영수증 1, 응답 `srs.card_version=1`, 신규 1 |
| 같은 요청 재시도 | 처음 응답 그대로, 쓰기 0 |
| 같은 request_id에 `expected_card_version: 0` 또는 등급 변경 | 409 `request_id_conflict`, 쓰기 0 |
| 영수증 해시 | 원래 null payload 기준(0으로 계산한 값과 다름) |
| 구독 해제 | 404, 쓰기 0 |
| legacy 계정이 null 전송 | 409 `srs_mode_not_fsrs`, 쓰기 0 |
| progress가 이미 있음(다른 창 생성, 상태만 바꾼 legacy 행) | 409 `card_version_conflict`, 쓰기 0 |
| progress 없이 로그만 있는 단어 | 409 `history_initialization_requires_approval`, 생성 행까지 롤백 |
| null + id 누락 | 422 `review_upgrade_required`, 쓰기 0 |
| **키 누락**(기존 legacy 요청) | 기존 동작 그대로(legacy 지연 생성·자동 분류) |
| 키 누락 + request_id, FSRS 카드 | 422 `review_upgrade_required`(누락을 null로 보지 않음) |
| 개인 URL에 명시적 null | 422 `null_card_version_not_allowed`, 쓰기 0 |

### 2-3. `GET /study-queue`

| 기능 | 결과 |
| --- | --- |
| `exclude_card` | 정렬상 앞 10장을 제외하고 `limit=10`이면 뒤 5장 반환. 범주 집계·`total_in_scope`·`new_allowed_now`·`new_goal`은 제외 전과 같음. `excluded_by_request=10`. `next_due_at`과 `next_due_at_excluded` 분리 |
| 검증 | 형식 오류 400, 중복은 하나로, 서로 다른 키 101개면 400 `too_many_excluded_cards`(100개는 허용), 다른 계정 키는 무시(집계에도 없음) |
| 커서 | 제외 목록이 바뀌면 409 |
| `mode=selected` | 지정한 이 계정 개인 카드만. 구독·다른 계정 id 무시. due 출제, 미평가는 목표 잔여 안에서만, 목표 도달·신규 확인 불가 시 신규 0, 미래 대기는 출제 안 함. 목표 도달 뒤에도 이미 받은 카드 평가는 200 |
| selected 검증 | `card_id` 없음, 201개, 다른 모드에서 `card_id`, 덱 scope, 숫자 아님 → 400 |
| 미생성 구독 단어 | 신규 버킷에 `card_version: null`, `materialized: false`로 출제. 항목의 평가 경로로 null을 보내면 생성·평가되고, 다음 조회에서 미래 대기로 바뀜 |
| 쓰기 | 정상·오류 경로 모두 DB 행·파일 바이트 동일 |

## 3. 동시성 [실행 확인, SQLite 실제 스레드·별도 연결]

- **다른 request_id로 동시 최초 평가**: 첫 요청이 엔진 단계에서 0.3초 머무는 동안 두 번째가 들어왔다. 계정 잠금(`BEGIN IMMEDIATE`)으로 직렬화되어 하나는 200, 하나는 409 `card_version_conflict`였다. progress 1행, 로그 1, 영수증 1.
- **같은 request_id 동시 두 요청**: 하나가 생성·평가했고, 다른 하나는 같은 영수증 응답을 받았다. 두 응답이 같고 행·로그·영수증은 1이다.
- **단계별 실패 주입**: 엔진, 신규 집계(로그 기록 뒤), 영수증 해시(영수증 기록 직전)에서 각각 실패시켰다. 세 경우 모두 생성한 progress까지 전체 롤백됐다(DB 행·바이트 동일).
- PostgreSQL에서는 B-2의 행 잠금 코드가 그대로 쓰이지만 **실행하지 않았다.**

## 4. 검사 결과

### 4-1. 실행

| 실행 | 결과 |
| --- | --- |
| `tests/test_srs_c2_server.py` (새) | 22개 통과: 개인 카드 5, 구독 최초 평가 8, 제외 5, selected 4 |
| 백엔드 `unittest discover -s tests` | **218개 중 217 통과, 1 건너뜀**(PG opt-in). B-1·B-2·C-1·학습 계획·통계 포함 |
| 기존 회귀 스크립트 7개 | 모두 exit 0, FAIL 없음 |
| `audit_current_srs.py`(legacy) | 15/15 |
| 프론트 `npm test` / `typecheck` | 73/73 / 통과(프론트 무변경, build 반복 안 함) |
| `git diff --check` + 새 파일 끝 공백 | 깨끗함 |

### 4-2. 기존 테스트 조정 (계약 변경에 따른 것만)

| 테스트 | 조정 | 이유 |
| --- | --- | --- |
| `test_srs_queue.QueueCase.personal` | 만든 카드를 legacy 기본으로 되돌리는 고정 자료 줄 추가 | C-1 검사들은 "새 카드 = legacy, 필요하면 `self.fsrs()`로 전환"을 전제로 쓰였다. 기대값은 그대로 |
| `test_unmaterialized_and_available_never_overlap` | 미생성 단어도 출제됨(7개, `card_version` null 4개) | 3-2 경로 검증 뒤 출제 합류(승인 6·8) |
| `test_every_card_in_exactly_one_category_and_sum_matches` | `new_allowed_now` 1 → 2 | 허용량 기준에 출제 가능한 미생성 포함(계약 3-2) |
| `test_srs_schema` 업그레이드 검사 | 구 코드 흉내에 새 카드 초기화도 끔 | 구 코드는 SRS 스키마도 초기화도 없었다. 보존 검증 내용은 그대로 |

## 5. 미검증·남은 사항

- **PostgreSQL**: 새 경로(구독 최초 평가 INSERT·잠금, 큐 SQL) 실행 미검증. 로컬 PG 없음.
- 클라이언트(C-2b·C-2c): 평가 시도·회차 미루기 집계·100개 정지 상태·모드 판별·연습·recent 연결은 아직 없다. 지금 서버 변경만으로 화면 동작은 바뀌지 않는다. 기존 프론트는 `/study-queue`를 부르지 않고, 구독 평가에 `expected_card_version`을 보내지 않는다.
- 미래 예약 카드의 "남은 단어 연습하기"용 selected 연습 조회는 C-2c에서 정한다(지금 연습 모드에는 `card_id`가 없다).
- 계속 별도 승인 사항: 불완전 이력 초기화, PostgreSQL 로그 보존, 완료 기준, 추가 신규량·목표 우회, 설정 변경 API.

정리: 이번 실행이 만든 임시 회귀 DB 5개와 스크래치 로그를 지웠다. 실행 전부터 있던 회귀 DB 2개는 두었다. 서버는 띄우지 않았다(검사는 TestClient와 테스트 안의 자체 서버만 사용).

## 6. C-2a 동시성 검사 보강 (2026-10-10)

- 문제: 이전 `_parallel`은 결과를 request_id 키로 보관했다. 그래서 같은 request_id 두 요청(I7)은 한 결과가 다른 결과를 덮어써, 사실상 한 응답을 두 번 비교했다. 스레드 종료와 예상 밖 예외도 확인하지 않았다.
- 보정(`tests/test_srs_c2_server.py`):
  - 결과를 작업 인덱스별로 보관한다.
  - 모든 예외를 기록한다(예상 밖 예외는 실패로 처리).
  - 모든 스레드가 종료됐는지 확인한다.
  - 두 작업이 실제로 겹쳤는지 확인한다: 둘 다 시작한 뒤에 첫 작업이 끝났는지.
- I6(다른 request_id): 정확히 하나는 성공, 하나는 `(409, card_version_conflict)`. 성공 응답의 request_id는 둘 중 하나다.
- I7(같은 request_id): 두 작업 모두 성공하고 두 응답이 같다.
- 두 경우 모두 progress·로그·영수증이 각 1건이다.
- 재실행: 세션 전용 SQLite에서 `tests/test_srs_c2_server.py` 22개 전부 통과(약 5초). API 구간 멈춤은 없었다. 서버 코드는 바꾸지 않았다.

## 7. Gate C-2b: 회차 순수 모듈 (2026-10-10)

범위: `frontend/components/studySession.ts`, `studySession.test.mts`, `package.json`의 `test` 스크립트 한 줄. page.tsx·StudySection·실제 화면·저장 키·백엔드는 연결하거나 바꾸지 않았다. C-2c는 별도 승인 뒤다.
**이 모듈의 테스트 통과는 실제 앱의 평가·회차가 보호된다는 뜻이 아니다.** 실제 보호는 C-2c 연결과 브라우저 검증 뒤에 판단한다.

### 7-1. 모듈이 하는 일

- DOM·fetch·저장소·시계에 직접 접근하지 않는다. 시각(`nowMs`), ID(`sessionId`, `requestId`), 응답(`ReviewOutcome`), 큐(`QueueSnapshot`)는 모두 인자로 받는다. React와 무관한 순수 함수다.
- **시도 고정**(`beginAttempt`): 계정 epoch, sessionId, 카드 종류·id·구독 덱 문맥, request_id, payload(등급, request_id, session_id, `expected_card_version` 정수 또는 명시적 null, 개인 카드만 응답 시간)를 얼린 객체로 만든다. 진행 중 시도가 있으면 두 번째 시작을 거절한다.
- **결과 적용**(`resolveAttempt`): 계약 1-3의 조건(계정 epoch, 회차, 현재 카드, 그 회차의 진행 중 시도)이 모두 맞을 때만 반영한다. 아니면 상태를 바꾸지 않는다("ignored"). 늦은 성공·실패·네트워크 오류 모두 같다. `isSubmitting`은 회차 상태에서 계산하므로, 늦은 finally가 새 회차의 버튼을 바꿀 수단이 없다.
- **중복 성공**: 이미 반영한 request_id의 성공은 진행 수·등급·미루기 집계를 다시 바꾸지 않는다.
- **결과 미확정**: 네트워크 오류·5xx는 시도를 유지하고 상태만 "unknown"으로 둔다. 자동 재시도는 최대 1회이고, 그 뒤는 사용자 재시도다. `retryAttempt`는 처음 시도 객체를 그대로 돌려준다(같은 request_id·payload).
- **409·기타**:
  - 409 `card_version_conflict`는 자동 재평가 없이 재조회한다.
  - `request_id_conflict`·`srs_mode_not_fsrs`·422·401·기타 4xx는 회차를 정지한다.
  - 보류·손상·step·이력 초기화·설정 오류와 404는 카드를 넘기고 재조회한다.
- **회차 미루기**: 같은 회차에서 결과 단계가 학습·재학습인 성공 평가가 3회가 되면 `exclude_card` 목록에 넣는다. 100개가 찬 상태에서 101번째가 필요하면 기존 항목을 버리지 않고 `deferred_limit`로 회차를 정지한다. 새 회차(`startSession`)는 집계와 목록이 빈 상태로 시작한다.
- **카드 교체 금지**: 카드가 표시 중이면 큐 결과는 집계만 갱신하고 카드를 바꾸지 않는다. 다른 회차·계정을 위해 요청한 큐 결과는 버린다. 조회 실패는 "할 카드 없음"으로 바꾸지 않는다. 타이머·앱 복귀 재조회는 카드·시도가 없을 때만 한다.
- **주 상태**(`sessionView`): 오류(정지·조회 실패) → 카드 → 곧 돌아옴(15분) → 미룬 카드만(`deferred_only`, 한도 정지는 `deferred_limit`) → 신규 확인 불가 → 목표 달성(신규 후보 > 0, 계획 또는 계정 잔여 0) → 복습 끝. 상태 이름과 판정에 "학습 완료"가 없다.
- **활성 회차**: 종료(`endSession`)하기 전까지 활성이다. 대기·미룸·정지 화면도 포함한다. `replaceGuard`는 전송 중이면 wait, 결과 미확정이면 confirm_unsaved, 활성이면 confirm, 종료·없음이면 free다. `shouldWarnBeforeUnload`는 전송 중·결과 미확정일 때만 참이다.
- **신규 수**: `newGoalDisplay`와 `parseQueueResponse`는 null·unknown을 0으로 바꾸지 않는다(unknown이면 하한만 준다).

### 7-2. 검사 [실행 확인]

| 실행 | 결과 |
| --- | --- |
| `node --test components/studySession.test.mts` | 30개 통과 |
| 프론트 `npm test`(새 테스트 연결 후) | 103/103(기존 73 + 30) |
| 프론트 `npm run typecheck` | 통과 |
| `git diff --check` + 새 파일 끝 공백 | 깨끗함 |
| build | UI 미변경이라 반복하지 않음 |

검사표 대응: P1–P10, P12·P14·P15의 U 항목, L1–L4, Q2·Q4·Q5, D1–D5, 100개 한도(9-1), H1–H8, M10, 응답 해석.
아직 하지 않은 것(C-2c): P11·P13(새로고침·탭 이동), Q1·Q3·Q6의 실제 조회, D6(자정)·D7(앞 10개 미룸 뒤 실제 서버 조회), H9, M1–M3·M11·M12 화면 확인, 계획 실행기(L5·L6)와의 연결.

## 8. Gate C-2b 보정 (2026-10-10)

범위: `frontend/components/studySession.ts`, `studySession.test.mts`, 이 문서. 백엔드·page.tsx·StudySection·저장 키·package.json은 바꾸지 않았다. 아래는 모두 순수 모듈 결과이며 실제 화면 보호는 C-2c 연결 뒤에 확인한다.

### 8-1. 수정 전 재현 [실행 확인, 임시 스크립트]

| 문제 | 수정 전 | 수정 후 |
| --- | --- | --- |
| 같은 회차 조회 두 개 응답 역전 | 옛 응답이 카드 1을 되살림 | 버림(카드 없음 유지) |
| 평가 성공 뒤 옛 조회 도착 | 평가한 카드 1이 다시 표시 | 버림 |
| 최신 성공 뒤 옛 실패 도착 | `queueError: true`(오류 화면) | 버림(카드 화면 유지) |
| 계정 잔여 0 / 계획 잔여 5 | 복습 끝, 잔여 5 표시 | 목표 달성, 계정 기준 20/20 잔여 0 |
| 계정 잔여 5 / 계획 잔여 0 | 목표 달성, 잔여 0 | 목표 달성, 계획 기준 6/6 잔여 0 |
| 계정 잔여 3 / 계획 잔여 7 | 잔여 7 표시(실제 허용 3) | 실제 허용 3, 계정 기준 17/20 잔여 3 |
| null 항목 | 예외 발생 | null(해석 실패) |
| 버전 문자열 "7" | 버전 null로 해석(구독 최초 평가로 오인 가능) | null(해석 실패) |
| 음수 버전·소수 ID | 그대로 해석 | null(해석 실패) |

### 8-2. 변경

- **조회 순번**: 회차에 `queueSeq`를 둔다. 조회는 `beginQueueFetch`로 시작해 티켓(계정 epoch·회차·순번)을 받고, `applyQueue`·`applyQueueFailure`는 티켓이 최신 순번일 때만 반영한다. 새 조회를 시작하거나 평가가 확정(성공·충돌·정지·재조회 대상 오류)되면 순번이 올라가 이전 조회의 성공·실패가 모두 무효가 된다. 결과 미확정(네트워크·5xx)은 경계가 아니므로 순번을 바꾸지 않는다.
- **실제 신규 허용량**: `effectiveNewRemaining` = 계정 잔여와(계획이 있으면) 계획 잔여 중 작은 값. 하나라도 확인 불가면 null. 신규 후보가 있고 이 값이 0이면 목표 달성이다. `newGoalDisplay`는 실제로 막는 쪽(잔여가 작은 쪽, 같으면 계정)의 목표·실적·잔여를 함께 돌려주고 `basis`로 기준을 밝힌다. 계획 집계가 확인 불가면 계획 기준 하한을 보여 준다. 서버 응답의 `plan_daily_new`·`introduced_today_in_scope*`를 새로 읽는다(서버는 이미 보내고 있었다).
- **응답 해석**: 형식이 하나라도 틀리면 예외 없이 null을 돌려준다. 항목은 객체, 카드 종류는 personal/lexeme, ID는 양의 안전 정수, `card_version`은 0 이상 정수이거나 `materialized: false`인 구독 카드의 명시적 null만 허용한다(개인 카드 null·키 누락·문자열·음수·소수는 실패). 연습 카드가 아니면 `/`로 시작하는 평가 경로가 필요하고, 구독 카드는 양의 정수 `shared_deck_id`가 필요하다. 집계·신규 목표 수는 0 이상 정수 또는 null이며, exact/unknown 상태와 값이 어긋나면 실패다.
- 기존 해석 테스트의 미생성 구독 카드 예시에 서버가 실제로 보내는 `materialized: false`를 넣었다.

### 8-3. 검사 [실행 확인]

| 실행 | 결과 |
| --- | --- |
| `node --test components/studySession.test.mts` | 46개 통과(기존 30 + 회귀 16) |
| 프론트 `npm test` | 119/119 |
| 프론트 `npm run typecheck` | 통과 |
| `git diff --check` + 새 파일 끝 공백 | 깨끗함 |
| build | UI 미변경이라 실행하지 않음 |

C-2c에서 화면이 지켜야 할 것: 모든 큐 조회를 `beginQueueFetch`로 시작하고 받은 티켓으로만 반영할 것, 해석 실패(null)를 조회 실패(`applyQueueFailure`)로 다룰 것.

## 9. Gate C-2c: 화면 연결 (2026-10-10)

시작 상태: `codex/fsrs-srs-replacement`, HEAD `e2c07f8`, AGENTS.md 없음. 기존 변경·미추적 자료는 그대로 두었다. 스테이징·커밋·푸시 없음. 실제 사용자 이전·기본 FSRS 활성화 없음.

### 9-1. 변경 파일

| 파일 | 변경 |
| --- | --- |
| `frontend/components/fsrsStudy.ts`(신규, 순수) | 덱·모드 → 큐 대상, `/study-queue` 경로(첫 페이지·limit 10·제외 목록), 모드 판별 결과, 큐 오류 분류, 큐 항목 → 책 지면 카드, 신규 목표 줄·정지·안내 문구 |
| `frontend/components/fsrsStudy.test.mts`(신규) | 위 순수 함수 8개 테스트 |
| `frontend/components/useFsrsStudy.ts`(신규, React 훅) | 회차 상태 저장, 조회 티켓, 평가 시도 전송·재시도, 대기 타이머, 앱 복귀, beforeunload, 연습 넘기기 |
| `frontend/components/studySession.ts` | 연결에 필요한 보강 3개: `queuePending`(다음 카드를 받는 동안 "복습 끝" 대신 불러오는 중), `applyQueueHalt`(모드 변경 409·401·제외 한도 400을 최신 티켓만 반영), 조회 실패·진행 중이면 타이머 재조회 없음 |
| `frontend/components/studySession.test.mts` | 위 보강 테스트 4개 |
| `frontend/app/page.tsx` | 계정 epoch별 모드 판별, 모든 시작 경로(복습 탭·빠른 시작·덱에서 시작·홈·읽기의 recent·학습 계획)를 FSRS 회차로 분기, 교체 보호, 계획 실행기 FSRS 어댑터, 상태 코드·detail을 그대로 주는 `fetchResult`. legacy 계정 경로는 그대로 |
| `frontend/components/StudySection.tsx` | 선택 prop `fsrs`. 없으면 기존 화면 그대로. 있으면 같은 책 지면에서 대기·미룸·목표·확인 불가·오류·회차 기록·연습 두 버튼·결과 미확정 다시 시도를 그림 |
| `frontend/app/globals.css` | 연습 두 칸 버튼, 시도 상태 줄(좁은 화면에서 도구 줄과 겹치지 않게) |
| `frontend/components/planStudyLauncher.ts` | 타입에 선택 필드만 추가(`dailyNew`, `guard`). 보호 규칙 무변경 |
| `frontend/components/LearningPlanPanel.tsx`, `LearningPlanSection.tsx` | 계획 하루량 전달, FSRS 회차 확인 문구(전송 중이면 바꾸기 숨김) |
| `frontend/package.json` | `test`에 `fsrsStudy.test.mts` 추가 |

백엔드·저장 키·에셋·legacy 화면 경로는 바꾸지 않았다. 새 저장 키 없음(QA origin에서 확인: 읽기 v3, 토큰, 학습 계획 v1만 존재).

### 9-2. 연결 방식

- **모드 판별**: `/me` 확인이 끝난 epoch마다 `GET /study-queue?limit=1`. 409 `srs_mode_not_fsrs`만 legacy, 200은 FSRS, 그 밖(401·404·400·5xx·네트워크)은 오류 화면과 "다시 확인"이며 legacy로 바꾸지 않는다. 판별 중·오류 중에는 시작 버튼을 막는다. 평가·조회 중 409 `srs_mode_not_fsrs`를 받으면 회차를 멈추고 다시 판별한다.
- **큐 조회**: 최초 시작·평가 후·대기 타이머·앱 복귀·다시 불러오기 모두 훅의 `fetchQueue` 하나로 하고, 매번 `beginQueueFetch` 티켓을 받는다. 성공·실패·해석 실패(카드 내용 포함)를 그 티켓으로만 반영하고, 모듈이 받아들인 뒤에만 카드 내용·시각 보정·연습 목록을 저장한다. 매 경계에서 첫 페이지(커서 없음)와 제외 목록을 보낸다. 조회 실패는 오류 화면과 "다시 불러오기"이며 자동 반복 조회가 없다.
- **평가**: 최신 회차 상태에서 `beginAttempt`로 한 번 만든 시도 객체를 그대로 보내고 재시도한다. 결과는 `resolveAttempt`로만 반영하고 "ignored"면 아무 상태도 바꾸지 않는다. 결과 미확정은 같은 시도로 자동 1회(1초 뒤), 이후 "다시 시도". 409는 자동 재평가 없이 안내와 재조회. 재시도 직전 계정·회차·카드를 다시 확인하므로 계정 전환 뒤 이전 계정 요청을 보내지 않는다. beforeunload는 전송 중·결과 미확정일 때만 등록하고 끝나면 해제한다.
- **회차·진입 경로**: 대기·미룸 화면도 활성 회차다. 복습 탭의 덱·모드 변경, 빠른 시작, 덱에서 시작, 홈, 읽기의 recent, 학습 계획이 같은 보호(전송 중 대기 안내, 결과 미확정 경고, 활성 회차 확인)를 쓴다. 연습(unknown·uncertain·all)은 `mode=practice`로 받아 화면에서만 넘기고 평가 POST가 없다. recent는 `mode=selected&card_id=…`(R2). 회차를 마치면 "이번 회차 기록"이며 "학습 완료" 문구는 없다.

### 9-3. 검사

층을 나눠 적는다. 순수 테스트 통과만으로 앱 보호를 주장하지 않으며, 브라우저 결과는 아래 합성 환경의 결과다.

**순수 테스트 [실행 확인]**: 프론트 `npm test` 131/131(기존 119 + 모듈 보강 4 + 연결 도우미 8), `npm run typecheck` 통과.

**실제 API [실행 확인, 세션 전용 SQLite, loopback HTTP]**: QA 서버(127.0.0.1:8100, `DATABASE_URL`을 스크래치 SQLite로 지정 후 확인, Neon·운영·기존 DB 미접근). FSRS 합성 계정 판별 200, legacy 합성 계정 409 `srs_mode_not_fsrs`, 토큰 없는 요청 401 `missing token`.

**브라우저 [실행 확인, 127.0.0.1:3100, 합성 계정 4개 중 FSRS 3개는 DB에서 명시적으로 설정]**: 지연·응답 유실·서버 시각 이동은 스크래치 QA 서버의 ASGI 감싸기로 주입했다(제품 코드에 QA 훅 없음).

| 항목 | 결과 |
| --- | --- |
| 미생성 구독 카드 평가 | 요청에 `expected_card_version: null`, 200, 진도 1·로그 1·영수증 1 |
| 개인 카드 첫 평가 | `expected_card_version: 0`, `response_time_ms` 포함 |
| 응답 유실(처리 뒤 503) | 결과 미확정 표시·버튼 잠금 → 같은 request_id·payload로 자동 1회 → 200. 두 번 유실이면 "다시 시도"로 수동 재전송. 로그·영수증 각 1 |
| 두 창 충돌 | 두 번째 창 409 `card_version_conflict`, 재평가 요청 없음, 안내 뒤 재조회 |
| 계정 전환 중 늦은 응답 | 평가 응답을 15초 지연, 다른 창에서 legacy 계정으로 전환. 늦은 응답 뒤 재조회·통계·안내·재전송 0, 새 계정 화면 무변경. 서버에는 이전 계정 로그 1건 |
| 회차 교체 중 늦은 조회(응답 역전) | 첫 회차 조회를 8초 지연, 그사이 모드 변경 확인으로 새 회차 시작. 늦게 온 옛 응답이 새 회차 카드를 바꾸지 않음. 기다리는 동안 "카드를 불러오는 중이에요"(복습 끝으로 보이지 않음) |
| 평가 후 옛 조회 | 같은 회차에서 조회가 겹치는 경로는 화면에서 만들 수 없다(앱 복귀 재조회는 조회 중이면 건너뛰고, 타이머는 조회 중·실패 뒤에 걸지 않음). 이 경우는 순수 테스트로만 확인 |
| 대기 타이머 | Again 뒤 "다음 카드는 HH:MM에 돌아와요", 실제 1분 대기 뒤 due 시각에 조회 1회, 카드 복귀 |
| 회차 미루기 | 서버 시각을 앞당겨 같은 카드에 학습 단계 결과 3회 → 다음 조회부터 `exclude_card` 전송, 제외 카드만 남으면 "이번 회차에서 미룬 단어만 남았어요", "새 회차로 다시 보기"는 제외 목록 없이 시작 |
| 연습 쓰기 0 | 연습 중 요청 0건, 로그·영수증·진도·카드 갱신 시각 전후 동일 |
| 신규 목표 | 계정 기준 "오늘 새 단어 목표 1개를 채웠어요", 학습 계획 기준 "오늘 학습 계획의 새 단어 목표 1개를 채웠어요", 목표 줄에 기준 표기 |
| 신규 확인 불가 | "오늘 새 단어 수를 확인할 수 없어 새 단어는 멈췄어요", 목표 줄 "확인할 수 없음 (적어도 0개)", 옮겨지지 않은 단어 보조 줄 |
| recent 범위 | 읽기에서 담은 단어 1개만 `mode=selected&card_id=13`, 평가 뒤 "남은 단어 연습하기"는 기존 읽기 전용 목록 GET 1건, POST 0 |
| 학습 계획 | `/study-queue?scope=personal_deck&deck_id=…&mode=new&plan_daily_new=1`, 대기 중 회차에서 계획 시작 → "진행 중인 복습 회차가 있어요" 확인, 전송 중이면 "평가를 저장하는 중이에요…"와 바꾸기 숨김 |
| 교체 보호(복습 탭) | 전송 중 모드 변경 → 대기 안내, 결과 미확정 → 경고 확인(취소 시 회차·모드 유지) |
| 탭 이동 | 전송 중 학습 계획 탭으로 이동했다 돌아와도 결과 반영, 회차 유지 |
| 조회 실패 | 오류 화면, 6초 동안 재요청 0, "다시 불러오기"로 회복 |
| 모드 판별 실패 | 503 → "복습 방식을 확인하지 못했어요", 시작 버튼 막힘, legacy 전환 없음, "다시 확인"으로 FSRS |
| legacy 회귀 | legacy 계정: 기존 `/study-items`·`/study-items/lexemes` 조회와 `{"rating","response_time_ms"}` 평가, 기존 진행 표시 그대로 |
| 다른 탭 | 책상·읽기·단어·덱·학습 계획·통계 열기 정상, 콘솔 오류는 주입한 503과 의도한 409뿐 |
| 화면 폭 | 1280·390에서 핵심 흐름, 이어서 1024·800·320에서 준비·질문·정답·결과 미확정·대기·연습·회차 기록을 DOM 측정(가로 스크롤·넘침·겹침 없음)과 스크린숏으로 확인. 390에서 시도 상태가 도구 줄과 겹치던 것을 별도 줄로 고친 뒤 재확인 |

**백엔드 회귀 [실행 확인, 메모리 SQLite]**: SRS 테스트 171개 통과(PostgreSQL 1개 건너뜀), 백엔드 전체 218개 통과(같은 1개 건너뜀).

**기타**: `git diff --check`와 새 파일 끝 공백 깨끗함. QA 서버 종료 뒤 `npm run build` 1회 통과. 직접 띄운 서버 2개(8100·3100)만 종료했고, 스크래치 DB·QA 스크립트·QA origin 저장소를 지웠다. 기존 서버(3000·8000)는 실행 중이 아니었고 건드리지 않았다.

### 9-4. 검토가 필요한 결정과 남은 것

- **방문자(토큰 없음)는 판별 요청 없이 기존 경로**: `/study-queue`는 로그인 계정 전용이라 토큰 없는 요청은 401이다. 계약대로 401을 오류로 두면 방문자 복습이 막히므로, 토큰이 없을 때만 판별을 건너뛰었다. 로그인 계정의 401은 기존 만료 처리를 거쳐 방문자로 돌아온다.
- **학습 계획 시작에서 빈 큐**: FSRS 계정도 기존 실행기 규칙대로 비어 있으면 회차를 바꾸지 않고 "지금 학습할 새 단어가 없어요"를 보여 준다. 목표 달성으로 비었는지는 이 문구가 구별하지 않는다.
- **recent의 "남은 단어 연습하기"**: 서버 `mode=selected`는 연습과 함께 쓸 수 없어, 묶음 전체를 기존 읽기 전용 `/vocab-items`에서 받아 연습한다(평가 POST 없음).
- **연습 범위**: unknown → `status=unknown`, uncertain → `uncertain`, all → 두 상태. 서버 연습 목록은 예약 상태가 있는 카드만 내므로 한 번도 평가하지 않은 카드는 연습에 나오지 않는다.
- **legacy 통계 숫자**: FSRS 계정의 복습 탭에서는 legacy `/stats` 기반 개수를 숨겼다. 책상(홈)의 "오늘 복습 N개"는 바꾸지 않았다(이번 범위 밖).
- **뜻 수정**: FSRS 카드에서 뜻을 고치면 서버에는 저장되지만, 지금 보이는 카드의 뜻은 다음 조회 때 바뀐다.
- **확인창**: 교체 확인은 기존 코드처럼 `window.confirm`·`window.alert`를 쓴다.
- 계속 별도 승인: 불완전 이력 초기화, PostgreSQL 로그 보존, 완료 기준, 추가 신규량, 설정 변경 API.

## 10. Gate C-2c 보정 (2026-10-11)

시작 상태: `codex/fsrs-srs-replacement`, HEAD `e2c07f8`, AGENTS.md 없음. 기존 변경·미추적 자료 보존. 스테이징·커밋·푸시·실제 사용자 이전·기본 FSRS 활성화 없음. SRS 정책·스키마·저장 키·배경 디자인 무변경.

### 10-1. 수정 전 재현 [실행 확인, 브라우저, 세션 전용 SQLite·합성 계정]

| 결함 | 수정 전 | 수정 후 |
| --- | --- | --- |
| 재등장 카드 정답 공개 | 정답 보기 → Again → 대기 → 같은 개인 카드 재등장 시 정답·평가 버튼이 열린 채로 나옴. 그대로 평가하면 `response_time_ms` 10886(이전 공개 시각 기준) | 개인·미생성 구독 카드 모두 질문부터. 다시 정답을 본 뒤 2초 뒤 평가 → `response_time_ms` 2012 |
| 학습 계획 교체 | 첫 조회(200)로 비었는지만 보고 버린 뒤 기존 회차를 버리고 두 번째 조회. 두 번째 조회를 503으로 만들면 기존 회차(本)가 사라지고 새 회차가 오류 화면 | 새 회차용 티켓 조회 1회로 큐·카드 내용을 검증한 뒤에만 교체. 같은 실패 주입에서 기존 회차(本) 그대로, "학습 대상을 불러오지 못했어요. 지금 복습은 그대로예요." |

### 10-2. 변경

- **출제 차례**(`studySession.ts`): 회차에 `presentation`을 두고, 비어 있던 자리에 카드가 놓일 때마다 올린다. `presentationKey()`(회차·차례·카드)에 정답 공개와 응답 시간 기준을 묶었다. 같은 카드가 다시 나오면 새 차례라 질문부터, 같은 시도의 재시도는 카드가 그대로라 차례·정답·고정 payload가 유지된다. 409 충돌 뒤 재조회로 같은 카드가 와도 새 차례다.
- **컨트롤러 분리**(`fsrsStudyController.ts` 신규): 훅이 하던 회차 로직을 React 없이 옮기고(모듈 함수는 주입), `useFsrsStudy.ts`는 다시 그리기·타이머·앱 복귀·beforeunload만 잇는다. 그래서 훅 연결을 Node 테스트로 직접 검사한다.
- **원자적 계획 교체**: `prepare(target)`이 새 회차를 따로 만들고 그 회차의 첫 조회 티켓으로 큐·카드 내용을 받아 검증한다(기존 회차 무변경). `adopt(prepared)`는 계정이 같고 기존 평가가 전송 중이 아닐 때만 교체하며, 검증한 응답을 그대로 쓴다(재조회 없음). 실행기 어댑터 `replaceSession`이 false를 주면 실행기는 started 대신 `sessionChanged`를 돌려준다(`planStudyLauncher.ts`, 보호 규칙은 그대로). 실행기의 세션 지문에 회차·진행 수·출제 차례·시도 상태를 넣어, 준비 중 기존 회차가 진행되면 교체하지 않는다.
- **빈 큐 원인**: 실행기 어댑터 `emptyReason`(선택)으로 목표 달성·신규 확인 불가·카드 없음을 구분해 학습 계획에 안내한다. 기존 회차는 그대로다.
- **방문자 경로**: 토큰이 없으면 이 epoch의 `/me`가 공용 방문자 계정으로 확인된 경우에만 기존 경로를 쓴다. `/me` 실패·인증 오류는 오류 화면이고, "다시 확인"은 계정 확인부터 다시 한다.
- **뜻 수정**: 저장에 성공하면 요청을 보낸 계정의 회차에서 같은 id의 개인 카드 내용에만 반영한다(늦은 응답이 새 계정·다른 카드에 적용되지 않음).
- **연습 범위**: 범위는 바꾸지 않았다. 준비 화면에 "한 번 이상 복습한 단어만 나와요"를, 서버 연습 목록이 비면 "연습할 단어가 없어요"와 그 제한을 밝힌다.
- 충돌 안내 문구를 "다른 창이나 기기에서 먼저 평가한 카드예요. 최신 상태로 다시 불러왔어요."로 바꿨다(같은 카드가 다시 올 수 있어서).

변경 파일: `studySession.ts`·`.test.mts`, `fsrsStudyController.ts`·`.test.mts`(신규), `useFsrsStudy.ts`, `fsrsStudy.ts`, `planStudyLauncher.ts`·`.test.mts`, `LearningPlanPanel.tsx`, `StudySection.tsx`, `app/page.tsx`, `package.json`(테스트 목록). 백엔드·저장 키·CSS 무변경.

### 10-3. 검사

**순수·연결 테스트 [실행 확인]**: 프론트 `npm test` 148/148. 새 컨트롤러·실행기 연결 테스트 14개는 실제 `studySession`·`fsrsStudy`·`planStudyLauncher`에 가짜 요청·시계·타이머만 넣어 돌린다(개인·구독 재등장, 새 공개 기준 응답 시간, 네트워크 재시도 유지, 충돌 뒤 재조회, 준비·검증·교체, 실패·해석 실패·빈 큐 원인, 계정 변경·전송 중 교체 거절, 실행기의 started·failed·empty·cancelled·stale·sessionChanged, 뜻 수정 범위). 출제 차례를 키에서 빼는 돌연변이를 넣으면 재등장 테스트 4개가 실패하는 것을 확인한 뒤 되돌렸다. 타입 검사 통과.

**브라우저 [실행 확인, 127.0.0.1:3100 + QA 서버 8100, 지연·유실·서버 시각 이동은 스크래치 ASGI 감싸기로만 주입]**:

| 항목 | 결과 |
| --- | --- |
| 개인 카드 재등장 | 질문부터, 평가 버튼 0개, 새 공개 기준 응답 시간 2012ms |
| 미생성 구독 카드 재등장 | 첫 평가 `expected_card_version: null` 유실 → 같은 payload로 자동 재시도(그동안 정답·버튼 유지) → 재등장은 질문부터 |
| 두 창 충돌 뒤 같은 카드 | 409 → 재평가 없이 재조회, 같은 카드가 질문부터 + 충돌 안내 |
| 계획 교체 실패 | 준비 조회 503 → 기존 회차 그대로, 실패 안내 |
| 계획 교체 중 기존 회차 진행 | 준비 조회를 6초 지연, 그사이 기존 회차에서 평가 → 교체 없음, 기존 회차 다음 카드로 계속 |
| 계획 교체 성공 | 계획 덱 조회 1회로 교체(이후 조회는 평가 뒤 경계 조회뿐), 목표 줄 학습 계획 기준 |
| 계획 빈 큐 | 계획 목표를 채운 뒤 시작 → "오늘 새 단어 목표를 이미 채웠어요. 지금 복습은 그대로예요.", 진행 중이던 연습 회차 보존 |
| 방문자 | 토큰 없음 + `/me` 503 → 오류 화면(legacy 전환 없음, 시작 막힘) → "다시 확인"으로 `/me` 성공 → 기존 방문자 화면 |
| 뜻 수정 | 연습 정답 화면에서 저장 → 지금 카드 뜻이 바로 바뀜 |
| 연습 범위 | 준비 화면 제한 문구, 빈 연습 목록 안내 |
| legacy 회귀 | legacy 계정은 기존 `/study-items` 조회와 `{"rating","response_time_ms"}` 평가 그대로 |
| 화면 폭 | 1280·390·1024·800·320에서 연습 준비·빈 연습·질문·정답·완료·회차 기록, 320에서 학습 계획 안내 문구를 DOM 측정(가로 스크롤·넘침·겹침 없음) |

**백엔드 회귀 [실행 확인, 메모리 SQLite]**: 전체 218개 통과(PostgreSQL 1개 건너뜀). `git diff --check`와 새 파일 끝 공백 깨끗함. QA 서버 2개(8100·3100)만 종료하고 스크래치 DB·스크립트·QA origin 저장소를 지운 뒤 `npm run build` 1회 통과.

### 10-4. 남은 제한

- 늦은 뜻 수정 응답이 새 계정에 적용되지 않는 것은 연결 테스트와 기존 epoch 확인으로만 확인했다(브라우저에서 계정 전환 중 수정 응답 지연은 따로 돌리지 않았다).
- 계획 교체 중 기존 회차가 진행됐을 때의 실행기 결과(`sessionChanged`)는 연결 테스트로 확인했다. 브라우저에서는 학습 계획 탭을 떠나면 패널이 다시 만들어져 그 안내가 보이지 않고, 기존 회차 보존만 확인했다.
- 신규 확인 불가·카드 없음 원인 안내는 연결 테스트로 확인했고, 브라우저에서는 목표 달성만 확인했다.
- 연습은 계속 예약 상태가 있는 카드만 나온다(서버 C-1 동작). recent의 "남은 단어 연습하기"만 묶음 전체를 기존 읽기 전용 목록에서 받는다.
- 책상(홈)의 "오늘 복습 N개"는 legacy `/stats` 숫자 그대로다.
- 계속 별도 승인: 불완전 이력 초기화, PostgreSQL 로그 보존, 완료 기준, 추가 신규량, 설정 변경 API.

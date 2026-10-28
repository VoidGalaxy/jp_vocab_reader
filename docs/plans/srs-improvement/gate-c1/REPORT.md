# Gate C-1 보고: 읽기 전용 통합 복습 큐

작성: 2026-10-09. 계약 `CONTRACT.md` v0.2(승인 항목 6개를 이번 구현 범위로 채택), 계획 `IMPLEMENTATION_PLAN.md` v0.2, 검사표 `TEST_MATRIX.md` v0.2.
상태: **구현·검증 완료, Gate C-1 검토 대기.** Gate C-2, 기본 FSRS 활성화, 실제 사용자 이전, 스테이징·커밋·푸시·병합은 하지 않았다.

## 0. 시작 상태

| 항목 | 값 |
| --- | --- |
| 브랜치 / HEAD | `codex/fsrs-srs-replacement` / `e2c07f8` (B-1·B-2 작업은 미커밋 상태로 그대로) |
| AGENTS.md | 없음 |
| 기존 변경 | `docs/roadmap.md`, 미추적 에셋·목업·`references/plans/`·tsbuildinfo, B-1·B-2 파일 모두 보존 |

## 1. 변경 파일

| 파일 | 변경 |
| --- | --- |
| `backend/app/srs/queue.py` (신규) | 요청 정규화, 한 트랜잭션 읽기, 범위 안 카드 읽기 SQL, 12개 집계 필드 분류, 정렬 키, 키셋→잔여 신규 페이지 계산, 응답 조립 |
| `backend/app/srs/queue_cursor.py` (신규) | 서명 커서: 용도 분리 HMAC 키, `hmac.compare_digest`, 길이·형식·범위 검증, 조건 바인딩·체인 수명 |
| `backend/app/srs/goals.py` (신규) | 신규 집계(`first_review_times`, `introduced_on`, scope 선택), 계정 설정 읽기. 쓰기 없음 |
| `backend/app/srs/reviews.py` | `introduced_on` 본문을 `goals.introduced_on` 위임으로 교체. 정의·결과 동일(테스트로 기존 SQL과 비교). 그 외 평가 경로 무변경 |
| `backend/app/main.py` | `GET /study-queue` 라우트와 import 추가. 기존 라우트 무변경 |
| `backend/app/schemas.py` | `StudyQueueItem`, `StudyQueueResponse` 추가. 기존 모델 무변경 |
| `backend/tests/test_srs_queue.py` (신규) | 36개 검사(아래 4절) |
| `docs/plans/srs-improvement/gate-c1/REPORT.md` (신규) | 이 문서 |

바꾸지 않은 것: 스키마(`srs/schema.py`, `database.py`), 기존 조회·평가 함수(`vocab_repository`, `lexeme_repository`), 프론트 전체(`recent` 포함), 의존성.

## 2. API 결과

`GET /study-queue` (로그인 필수)

| 상황 | 결과 |
| --- | --- |
| FSRS 모드 계정 | 200. 항목·12개 집계·`total_in_scope`·신규 목표·`next_due_at`·`next_cursor` |
| 설정 행 없음 / legacy / shadow | 409 `srs_mode_not_fsrs` |
| 로그인 없음 | 401 |
| 소유하지 않은 개인 덱, 활성 구독 없는 덱 | 404 `deck not found` |
| 매개변수 오류(범위 밖·형식·중복 단일값·허용되지 않는 조합) | 400 |
| `extra_new` | 400 `unsupported_parameter` |
| 커서 형식·서명·길이·필드 범위 오류 | 400 `invalid_cursor` |
| 정상 커서의 조건 변경·서울 자정 경과·체인 15분 초과·다른 계정 | 409 `cursor_stale` |

항목에는 `card_kind`, `card_id`, 정수 `card_version`, `bucket`, `sort_key`(정렬·커서와 같은 5값), `srs`(phase/step/due/effective_due/last_review), `config_version`, `is_new`, `practice_only`, 자기분류 `status`, `participation`, 평가 `review`(path + 구독 덱 문맥 `shared_deck_id`), 표시 내용이 들어간다. 학습 완료 정보는 넣지 않는다.

계약 대비 구현에서 정한 세부(계약 범위 안의 결정, 새 정책 아님):

- 응답에 `bucket_as_of`를 추가했다. 현재 응답 시각 `server_now`와 버킷 판정 시각(첫 페이지 시각)을 구분해 보여 준다.
- `new_goal`에 `settings_version`, 그리고 페이지 체인의 신규 허용량·사용량을 `chain_new_allowed`·`chain_new_served`로 넣었다.
- 연습 모드의 정렬 키는 bucket 0, `effective_due_at` 기준이다(계약 2-8).
- 알 수 없는 매개변수는 무시한다(기존 API 관례). 단일값 매개변수가 두 번 오면 400이다.
- 체인 수명은 첫 페이지 시각(`server_now0`)부터 잰다. `iat`은 페이지마다 새로 찍히지만 수명을 늘리지 않는다.

## 3. 읽기 일관성

- 한 응답의 모든 SQL(설정, 권한, 개인·구독 카드, 로그 존재 여부, 신규 집계)을 **한 읽기 트랜잭션**에서 실행한다(`queue._begin_snapshot`).
- 읽기 전용 연결만으로는 보장되지 않는다는 점을 확인했다. Python sqlite3는 SELECT를 문장마다 자동 확정하므로, 명시적 `BEGIN` 없이는 문장 사이에 다른 평가가 끼어든다.
- **SQLite [실행 확인]**: 명시적 deferred `BEGIN` 뒤 첫 SELECT부터 커밋까지 읽기 잠금을 유지한다(현재 rollback journal 모드).
  - 검사: 카드를 읽은 뒤 신규 집계 전에 다른 스레드에서 실제 FSRS 평가(B-2 경로)를 시작했다.
  - 결과: 평가는 우리 읽기가 끝날 때까지 커밋하지 못했고, 응답은 "목록에 신규로 있음 + 오늘 신규 0"으로 일관됐다. 평가는 그 뒤 성공했고, 다음 조회에서 신규 1로 반영됐다.
  - 대조 검사: 같은 겹침을 `BEGIN` 없이 돌리면 평가가 읽기 도중 커밋되어 "목록에 신규로 있음 + 오늘 신규 1"이라는 불일치가 실제로 재현된다. 위 검사가 의미 있음을 보이는 대조다.
- **PostgreSQL [미검증]**: 읽기 전용 연결은 `SET TRANSACTION READ ONLY` 뒤 기본 READ COMMITTED라 문장마다 스냅샷이 달라진다. 그래서 첫 조회 전에 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`를 추가로 실행하도록 했다. 로컬 PG가 없어 실행하지 않았다.
- 요청 시각은 `queue._now()`로 한 번만 읽는다. 버킷 판정은 첫 페이지면 그 시각, 다음 페이지면 커서의 `server_now0`를 쓴다. 신규 집계와 서울 날짜는 현재 요청 시각을 쓴다.
- 버킷 판정 시각과 신규 집계 시각이 다른 것은 의도다. 앞쪽은 페이지 사이 정렬을 고정하고, 뒤쪽은 현재 목표를 보여 준다. 페이지 체인의 신규 허용량은 첫 페이지 값으로 고정해 이중 차감을 막는다.

## 4. 검사 결과

### 4-1. 새 검사 `tests/test_srs_queue.py`: 36개 통과

| 층 | 수 | 내용 |
| --- | --- | --- |
| 단위(고정 시계, 함수 직접 호출) | 33 | 정렬 3, 정체성 2, 범주 5, 권한 2, 신규 목표 6, 커서 9, 연습·매개변수 2, 일관성·쓰기 4(읽기 전용 쓰기 거부 포함) |
| API(FastAPI TestClient, 실제 라우트) | 2 | 상태 코드·응답 형식, 큐 조회 전후 legacy 조회 응답 동일 |
| 실제 HTTP(자체 uvicorn 자식 프로세스, loopback) | 1 | 200·400(`extra_new`, 위조 커서)·401·409(shadow), 조회 전후 DB 행 동일 |

TEST_MATRIX 대응:

| 영역 | 확인한 항목 |
| --- | --- |
| 전역 정렬 | S1, S3·S4(종류별 LIMIT 금지 배치), S6·S7·S8(문맥 덱 시각·sort_order) |
| 중복·정체성 | D1·D2·D3·D4·D5 |
| 필터 후 LIMIT | F1·F2(합계로), F3, F4(깨진 카드 10장이 앞서도 정상 3장 반환), F5·F6 |
| 범주 | A1(전 범주 + 합계 불변식), A2·A3(미평가 legacy), A4·A5·A6·A7·A8·A9·A11 |
| 권한 | P1·P2·P3(구독 해제 후 다른 덱 문맥으로 남음)·P5(비공개 전환)·P7(커서 다음 페이지에서 해제 반영)·P8(API)·P9(설정 없음/legacy/shadow) |
| 자정 | M1·M2·M3, M5(자정 넘긴 커서 409) |
| 신규 목표 | G1·G2·G3(두 창·목표 초과 수용·첫 Again·재시도·반복 평가)·G4·G5·G7·G8·G9·G10·G12 |
| 커서 | C1(45장 3페이지), C2·C5(페이지 사이 평가), C4(6=4+2), due·신규 혼합 페이지, C6·C7(변조·위조·길이·형식·서명된 범위 밖 값), C8(다른 계정), C9(필터 변경·순서 정규화), C10(목표·설정 버전·계획 하루량), C11(설정 버전), C12(체인 15분, iat 갱신으로 연장 안 됨) |
| 쓰기 0 | W1·W3·W4·W5(정상·오류·커서 경로 전후 행과 DB 파일 해시 동일), W2 |
| 연습 | R1·R3·R4 |

### 4-2. 회귀 [실행 확인]

| 실행 | 결과 |
| --- | --- |
| 백엔드 `unittest discover -s tests` | **180개 중 179 통과, 1 건너뜀**(PG opt-in). B-2 기준 144개 + 새 36개 |
| B-2 검사(`test_srs_transactions` 36, `test_srs_http` 1) | 위 전체에 포함되어 통과. `introduced_on` 위임 뒤에도 같음 |
| 학습 계획·통계·스키마·엔진·완료 검사 | 위 전체에 포함되어 통과 |
| 기존 회귀 스크립트 7개(구독 SRS, 구독 상태 정책, 구독 로그, 구독 통계, PG 불리언 SQL 호환, 구독 진도 smoke, DB 안전 가드) | 모두 exit 0, FAIL 없음 |
| `audit_current_srs.py` | 15/15 |
| 프론트 `npm test` | 73/73 |
| 프론트 `npm run typecheck` | 통과 |
| `git diff --check` + 새 파일 끝 공백 | 깨끗함 |
| 프론트 파일 변경 | 없음. build는 반복하지 않음 |

모든 DB 실행은 import 전에 지정한 세션 전용 SQLite였다. 테스트는 각자 임시 디렉터리 DB를 만들고 지운다. Neon·운영·`backend/vocab.db`·기존 로컬 DB에는 접근하지 않았다.
정리: 실제 HTTP 검사 서버는 검사 안에서 직접 띄우고 종료를 확인했다. 이번 실행으로 새로 생긴 임시 회귀 DB 5개와 로그를 지웠다. 실행 전부터 있던 같은 이름 회귀 DB 2개는 두었다.

### 4-3. 검사하지 못했거나 약하게만 확인한 항목

- **L4 바이트 비교**: 구현 전 응답을 저장해 두지 않았다. 대신 같은 프로세스에서 큐 조회 전후 legacy 조회 5종의 응답이 같음을 확인했고, `git diff`로 기존 조회 함수가 바뀌지 않았음을 확인했다.
- C3(지난 키 앞에 새 due 생김), G6(이전 apply가 신규를 쓰지 않음: B-2 검사로만 확인), G11(개인·구독 같은 표제어 각각 신규 1), G13(삭제 카드의 신규 집계), M4는 별도 검사를 두지 않았다.
- PostgreSQL 전 항목(스키마, REPEATABLE READ 스냅샷, `EXISTS`·`is_active = TRUE` 실행).
- 1천·1만 카드 성능(Gate E). 이번 구현은 범위 안 카드 전부와 계정 전체 로그의 카드별 최솟값을 매 요청 읽는다.

## 5. 남은 미정 계약 (이번 구현이 승인하지 않은 것)

- 구독 신규 progress 생성과 새 개인 카드의 FSRS 초기값(C-2). 그 전까지 해당 카드는 `new_unmaterialized`·`not_converted`로만 센다.
- `recent`의 FSRS 의미와 신규 목표 적용(C-2). 기존 동작은 그대로다.
- 날짜별 추가 목표량, 중복 방지, 계정·계획 목표와의 관계(후속 계약).
- `PATCH /srs/settings`(별도 계약). 이번 구현은 설정을 읽기만 한다.
- 실제 세션 연결, 재시도·세션 보호, 대기 카드 화면, 학습 단계 반복 어려움 보호(C-2).
- 불완전 이력 초기화, PostgreSQL 로그 보존, 학습 완료 기준 재승인.
- 기본 FSRS 활성화와 실제 사용자 이전.

## 6. 보정 (2026-10-09)

두 결함을 보정 전 코드에서 재현했다(세션 스크래치의 합성 SQLite, 재현 스크립트는 저장소에 넣지 않음). 2번만 구현했고, 1번은 응답 계약을 보완해야 하므로 제안 문서만 쓰고 승인을 기다린다.

### 6-1. 손상된 평가 시각 [재현만, 동작 변경 없음 → 승인 대기]

| 손상 위치·값 | 큐 | 다른 정상 카드의 FSRS 평가 | 평가 쪽 쓰기 |
| --- | --- | --- | --- |
| 개인 `reviewed_at` = `garbage` / `''` | 500 | 500 | 0 |
| 구독 `created_at` = `garbage` / `''` | 500 | 500 | 0 |
| 삭제된 개인 카드 로그 = `''` | 500 | 500 | 0 |

- "쓰기 0"은 로그·영수증 수, 카드 버전, DB 파일 바이트가 같다는 뜻이다. B-2 평가는 카드·로그를 쓴 뒤 신규 집계에서 실패하지만, 트랜잭션 전체가 롤백된다. 사용자는 원인을 알 수 없는 일반 500을 받고, 계정에 손상 로그가 하나라도 있으면 그 계정의 모든 FSRS 평가가 막힌다. legacy 평가는 영향이 없다.
- 원로그 삭제·수정, 손상 기록을 빼고 0으로 세기는 하지 않았다.
- 제안: `CORRUPT_REVIEW_TIME_PROPOSAL.md`. 핵심은 두 가지다.
  - 큐는 200을 유지하되, 신규 수를 "확인 불가"로 표시하고 신규 출제만 멈추고 due는 유지한다.
  - 평가는 다른 카드가 손상됐으면 진행하되 신규 수를 확인 불가로 기록하고, 자기 카드가 손상됐으면 쓰기 전에 409로 거부한다.
- 코드 검토로 함께 찾은 위험(실행 재현 안 함):
  - 시간대 없는 값도 500이 된다.
  - 문자열 MIN이 일부 손상을 가리거나, 손상 값을 "첫 평가"로 고른다.
  - 자기 카드 로그가 손상되면 완료 판정 단계에서 500이 난다(쓰기 전).
  - 롤백 도구도 손상 시각에서 중단된다.
- 검사표: `TEST_MATRIX.md` 14절(T1–T13)에 빈 시각·형식 오류·시간대 없음·`Z` 표기·삭제 카드·MIN 가림·평가 경로·재시도·커서를 추가했다. 승인 뒤 구현할 때 실행한다.

### 6-2. 엔진 설정 밖 학습 단계 [구현·검증 완료]

- 재현(보정 전): Learning `srs_step = 999` 카드가 큐에 나왔고, 보통 평가 한 번에 Review로 올라갔다. 정상 `step = 0`은 Learning(step 1)에 남았다. 라이브러리는 `step >= 단계 수`를 "마지막 단계를 지났다"로 보고 승격시키는데, 어댑터가 이를 막지 않았다.
- 수정(기존 `invalid_state` 계약의 보정):
  - `engine.validate_state_for_config`: Learning step은 `0 ≤ step < 학습 단계 수(2)`, Relearning step은 `0 ≤ step < 재학습 단계 수(1)`여야 한다. `engine.review`가 라이브러리를 부르기 전에 확인한다.
  - `storage.load_state`: 카드의 `srs_config_version`으로 설정을 찾아(`engine.CONFIGS_BY_VERSION`) 같은 함수로 검사한다. 큐(`queue.classify`)와 평가(`reviews.record_fsrs_review`)가 모두 이 함수를 거치므로 규칙이 하나다.
  - 큐: 범위 밖 카드는 `invalid_state`로 세고 출제하지 않는다. 합계 불변식은 유지된다.
  - 평가: 엔진 실행·카드 갱신·로그·영수증 전에 409 `invalid_engine_state`로 거부한다(B-2의 기존 오류 코드 재사용).
  - 원자료 자동 보정이나 Review 승격은 하지 않는다.
- 보정 후 같은 재현: step 999 카드는 큐에서 빠지고, 평가는 409로 거부되며, step 0은 그대로 Learning에 남는다.
- `CONTRACT.md` 3절 범주 4 설명에 이 조건을 추가했다.

### 6-3. 검사 결과 [실행 확인]

| 실행 | 결과 |
| --- | --- |
| 새 검사(엔진 `StepRangeTests` 2, 큐 `QueueStepRangeTests` 3) | 5개 통과. Learning 0·1과 Relearning 0의 정상 전이, Learning 2·999와 Relearning 1의 큐 제외, 개인·구독 API 409와 쓰기 0(DB 바이트 포함), 엔진 직접 거부 |
| `tests/test_srs_queue.py` | 39개 통과(C-1 36 + 3) |
| `tests/test_srs_engine.py` | 28개 통과(26 + 2) |
| 백엔드 `unittest discover -s tests` | **185개 중 184 통과, 1 건너뜀**(PG opt-in). B-1·B-2·C-1 전부 포함 |
| 기존 회귀 스크립트 7개 | 모두 exit 0, FAIL 없음 |
| `audit_current_srs.py`(legacy) | 15/15 |
| 프론트 `npm test` / `typecheck` | 73/73 / 통과(프론트 무변경, build 반복 안 함) |
| `git diff --check` + 새 파일 끝 공백 | 깨끗함 |

변경 파일(보정):

- 코드: `backend/app/srs/engine.py`(`validate_state_for_config`, `CONFIGS_BY_VERSION`, `review`에서 호출), `backend/app/srs/storage.py`(`load_state`에서 같은 검사).
- 테스트: `backend/tests/test_srs_engine.py`, `backend/tests/test_srs_queue.py`.
- 문서: `CONTRACT.md` 범주 4, `TEST_MATRIX.md` 14·15절, `CORRUPT_REVIEW_TIME_PROPOSAL.md`(신규), 이 절.

정리: 이번 실행이 만든 임시 회귀 DB 5개, 재현용 스크래치 DB·스크립트, 로그를 지웠다. 실행 전부터 있던 회귀 DB 2개는 두었다. PostgreSQL은 여전히 미검증이다.

### 6-4. 승인이 필요한 새 계약

`CORRUPT_REVIEW_TIME_PROPOSAL.md` 6절의 다섯 가지다.

1. 카드에 해석할 수 없는 로그 시각이 하나라도 있으면 그 카드의 첫 평가 날짜를 알 수 없음으로 둔다. 문자열 MIN을 쓰지 않는다.
2. 큐 응답 필드(`introduced_today_status`, null 값, `introduced_today_at_least`, `unreadable_review_time_cards`, `new_blocked_reason`)를 추가하고 신규 출제를 중단한다.
3. 손상 로그가 있는 카드 자신은 `invalid_state`로 세고 출제하지 않는다.
4. 평가 경로: 다른 카드가 손상됐으면 평가는 진행하고 신규 수를 확인 불가로 기록한다. 자기 카드가 손상됐으면 409 `review_history_unreadable`로 거부한다.
5. `Z` 표기처럼 시간대가 있는 비정규 값을 정상으로 셀지 정한다.

## 7. 손상된 평가 시각 보정 (2026-10-09)

`CORRUPT_REVIEW_TIME_PROPOSAL.md` 6절 다섯 항목을 이번 구현 범위로 채택해 구현했다. Gate C-2나 운영 전환 승인은 아니다. 확정 계약은 `CONTRACT.md` 7절(4-5)에 있다. 보정 전 재현 결과는 6-1절과 제안서 1절이다.

### 7-1. 변경

| 파일 | 변경 |
| --- | --- |
| `backend/app/srs/goals.py` | `read_utc`(시간대 있는 ISO만 인정, UTC로 변환, 실패 시 None). `first_review_dates`(카드별 모든 로그를 실제 시각으로 비교, 하나라도 못 읽으면 None, 문자열 MIN 제거). `count_introduced`/`introduction_count` → `IntroductionCount(status, count, at_least, unreadable_cards)`. 기존 `introduced_on`(정수 반환)은 제거 |
| `backend/app/srs/reviews.py` | 자기 로그 시각을 엔진·쓰기 전에 검사(409 `review_history_unreadable`). 완료 판정 이벤트를 실제 시각·id 순으로 정렬. 응답·영수증 `srs`에 `introduced_today`(null 가능)·`introduced_today_status`·`introduced_today_at_least`. 권한 → 영수증 → 새 평가 검사 순서는 그대로 |
| `backend/app/srs/queue.py` | 한 읽기 트랜잭션 안에서 계정·scope 확인 상태 계산. 손상 카드 자신은 `invalid_state`. 계정 확인 불가, 또는 계획이 있고 scope 확인 불가면 신규 0. `new_goal` 필드 추가. 커서 확인을 카드·상태 읽기 뒤로 옮김(형식 오류 400은 그대로 먼저) |
| `backend/app/srs/queue_cursor.py` | `goal_basis`에 `account_introduced_status`, `scope_introduced_status` 추가·검증 |
| `backend/tests/test_srs_queue.py` | `QueueCorruptTimeTests` 11개 추가. 기존 검사 2곳은 새 함수 이름에 맞춤(기대값 동일) |
| 문서 | `CONTRACT.md`(커서 표, 응답 예시 주석, 범주 4, 4-1, 7절), `TEST_MATRIX.md` 14절 결과, 제안서 상태, 이 절 |

legacy 평가 경로, 스키마, 기존 조회 라우트, 프론트는 바꾸지 않았다. 원로그를 삭제하거나 수정하는 코드는 없다.

### 7-2. API 결과 [실행 확인, TestClient·실제 라우트]

| 상황 | 결과 |
| --- | --- |
| 다른 카드(개인·구독·삭제 카드) 로그 시각 손상 | 큐 200, 신규 확인 불가, 하한, 신규 0, due 유지 |
| 같은 상황에서 정상 카드 평가 | 200, 응답·영수증 `introduced_today=null`, `status=unknown`, 하한 |
| 평가 대상 자신의 로그 손상(개인·구독) | 409 `review_history_unreadable`, DB 행·파일 바이트 동일 |
| 위 성공 요청 재시도(손상 복구 뒤) | 처음 응답 그대로. 다른 payload는 409 |
| `Z`·`+12:00` 오프셋 | 정상으로 셈. 실제 시각 비교(문자열 MIN이었다면 틀렸을 카드 포함) |
| 시간대 없음·빈 값·`garbage` | 확인 불가 |
| 정상→손상, 손상→정상 뒤 이전 커서 | 409 `cursor_stale` |

### 7-3. 롤백 경로 [실행 확인, 코드 무변경]

- 전환 뒤 평가 로그의 시각이 손상된 카드를 `migration.rollback_plan`으로 되돌리면, 시각 해석에서 일반 `ValueError`가 난다(버전 충돌 오류가 아님).
- `with get_connection()` 트랜잭션 전체가 버려진다. 카드·로그·실행 기록 행과 DB 파일 바이트가 그대로였다. 즉 부분 롤백은 없다.
- 지시대로 로그 수정이나 새로운 부분 롤백 정책은 넣지 않았다. 롤백 도구가 이 경우를 명확한 오류 코드로 알릴지는 후속 결정 사항이다.

### 7-4. 검사 결과

| 실행 | 결과 |
| --- | --- |
| 새 검사 `QueueCorruptTimeTests` | 11개 통과 |
| `tests/test_srs_queue.py` | 50개 통과 |
| 백엔드 `unittest discover -s tests` (B-1·B-2·C-1 포함) | **196개 중 195 통과, 1 건너뜀** |
| 기존 회귀 스크립트 7개 | 모두 exit 0, FAIL 없음 |
| `audit_current_srs.py`(legacy) | 15/15 |
| 프론트 `npm test` / `typecheck` | 73/73 / 통과(프론트 무변경, build 반복 안 함) |
| `git diff --check` + 새 파일 끝 공백 | 깨끗함 |

SQLite와 PostgreSQL 구분:

- 위 결과는 모두 세션 전용 SQLite다.
- PostgreSQL은 미검증이다. 새 집계 SQL은 `UNION ALL`과 문자열 리터럴만 쓰고 해석은 Python에서 하므로 방언 차이는 작다고 보지만, 실행하지 않았다.
- PG에서는 삭제된 카드의 로그가 CASCADE로 사라지므로, T7(삭제 카드 손상) 결과가 PG에서는 다를 수 있다. PG 로그 보존 결정 전에는 미정이다.

정리: 이번 실행이 만든 임시 회귀 DB 5개와 스크래치 로그를 지웠다. 실행 전부터 있던 회귀 DB 2개는 두었다. 서버는 테스트 안에서 띄운 것만 종료를 확인했다.

### 7-5. 여전히 미정

- 불완전 이력 초기화, PostgreSQL 로그 보존, 학습 완료 기준 재승인.
- 롤백 도구의 손상 시각 오류 표현(7-3).
- Gate C-2(세션 연결, 구독 신규 생성, recent 의미 등), 기본 FSRS 활성화, 실제 사용자 이전.

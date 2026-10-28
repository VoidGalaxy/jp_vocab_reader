# Gate C-1 구현 계획 (승인 전)

작성: 2026-10-09 (v0.1), 보정 v0.2: 2026-10-09. 계약은 `CONTRACT.md` v0.2, 검사는 `TEST_MATRIX.md`.
상태: **계획만 작성. 제품 코드·스키마 변경 없음.** `CONTRACT.md` 5절이 승인된 뒤에 시작한다.

## 1. 범위

포함:
- 읽기 전용 `GET /study-queue`
- 범위 안 카드 분류·집계(11개 범주)
- 신규 목표 계산(읽기)
- 서명된 커서
- 연습 모드 목록
- 테스트

제외(v0.2에서 명시):
- `extra_new`와 날짜별 추가 목표량: 후속 계약. 요청에 오면 400만 구현한다.
- `PATCH /srs/settings`와 설정 행 생성: 별도 계약. 이번에는 `srs_user_settings`를 **읽기만** 한다.
- `recent`: 기존 동작·프론트 연결을 바꾸지 않는다. 새 큐에 id 집합 조회를 넣지 않는다.
- 평가 쓰기 경로 변경(구독 progress 생성, 새 개인 카드 FSRS 초기값, 재시도·세션 보호): C-2.
- 프론트 연결·화면, 스키마 변경, 기본 FSRS 활성화, 실제 이전, 완료 지표.
- PostgreSQL 실행 검증(로컬 PG가 없으면 미검증으로 보고).

## 2. 변경 예정 파일

| 파일 | 변경 | 비고 |
| --- | --- | --- |
| `backend/app/srs/queue.py` (신규) | 요청 정규화, 범위 안 카드 읽기 SQL, 범주 분류, 정렬 키, 페이지 계산, 응답 조립 | 읽기 전용 연결만 사용 |
| `backend/app/srs/queue_cursor.py` (신규) | 커서 encode/verify: HMAC-SHA256, 키 파생, 길이·형식·범위 검증, 무효화 판정 | 순수 함수. 비밀값은 로그·예외 메시지에 넣지 않음 |
| `backend/app/srs/goals.py` (신규) | `introduced_today(user, seoul_date, scope=None)`, `account_daily_goal(user)` → `(goal, settings_version)` | `reviews.introduced_on`이 이 함수를 쓰도록 옮겨, 평가 응답과 큐가 **같은 정의**를 공유 |
| `backend/app/srs/reviews.py` | `introduced_on`이 `goals.introduced_today`를 호출하도록 위임 | 동작 동일(결과 비교 테스트 필수). 그 외 평가 경로는 변경 없음 |
| `backend/app/schemas.py` | `StudyQueueItem`, `StudyQueueCounts`, `StudyQueueNewGoal`, `StudyQueueResponse` 추가 | 기존 모델 수정 없음 |
| `backend/app/main.py` | `GET /study-queue` 라우트 하나 추가 | `required_user_id`, 기존 404 문구 재사용 |
| `backend/tests/test_srs_queue.py` (신규) | `TEST_MATRIX.md`의 SQLite 항목 | 세션 전용 SQLite. PG는 opt-in 보호 검사 |
| `docs/plans/srs-improvement/gate-c1/REPORT.md` (신규) | 실행 결과 | |

바꾸지 않는 파일: `vocab_repository.py`·`lexeme_repository.py`의 기존 조회·평가 함수, `database.py`, `srs/schema.py`, 프론트 전체(`recent` 포함).

## 3. 구현 순서

1. **집계 함수 분리**: `introduced_on`을 `goals.py`로 옮기고 scope 인자를 추가한다. 기존 B-2 테스트와 새 비교 테스트로 같은 값을 내는지 먼저 확인한다(행동 변화 0).
2. **커서 모듈**: 서명·검증·무효화를 순수 함수로 만들고 단위 테스트(변조·길이·범위·계정·날짜·설정 변경)를 먼저 쓴다.
3. **범위 안 카드 읽기(한 번의 읽기 전용 트랜잭션)**: 분류에 필요한 열만 SQL로 읽는다. 권한·범위·멤버십·중복 제거까지가 SQL의 일이다.
   - 개인: 소유 카드(덱 scope면 그 덱)와 카드별 로그 존재 여부(`EXISTS`).
   - 구독: 활성 구독 × `shared_deck_words`를 `GROUP BY lexeme_id`로 줄여 문맥 덱 = `MIN(shared_deck_id)`(덱 scope면 그 덱)와 그 덱의 `imported_at`·`sort_order`를 고른다. 그다음 `user_word_progress`를 LEFT JOIN하고 로그 존재 여부를 붙인다.
   - 범주 판정에 필요한 해석(엔진 상태 열 조합, S·D 범위, 시각 정규 형식)은 SQL에서 하지 않는다. 출제 여부를 정하는 판정을 LIMIT 뒤에 하면 페이지가 덜 차거나 합계가 틀어지기 때문이다.
4. **분류·정렬·페이지(서버 메모리)**: 읽은 행 전체를 CONTRACT 3절 순서대로 하나의 범주에 넣는다. 엔진 상태는 B-2 `load_state`로 확인하고, 실패하면 `invalid_state`다. 그다음 다음 순서로 진행한다.
   - 범주별 수와 `total_in_scope`를 같은 집합에서 센다(합계 불변식).
   - 출제 후보(범주 8·9·11)에 정렬 키 `K = (bucket, sort_time, kind_rank, seq, ref_id)`를 붙인다.
   - 키셋 조건 `K > last_key`를 **먼저** 건다.
   - 신규 후보를 `K` 순서로 `min(limit, 신규 잔여량)`개까지 고른다.
   - due 후보와 합쳐 `K`로 전역 정렬하고 `limit`개를 자른다.
   - 종류별 LIMIT 뒤 이어 붙이기는 하지 않는다. 신규 잔여량을 키셋 조건보다 먼저 적용하지 않는다(CONTRACT 2-6-3 금지 사항).
   - 메모리 사용과 처리 시간은 범위 안 카드 수에 비례한다. 1천·1만 카드 측정에서 문제가 되면, SQL로 내리는 최적화는 같은 결과를 내는지 비교 테스트를 붙여 별도 단계로 한다.
5. **신규 허용량**: 첫 페이지에서 `min(new_available, account_remaining, plan_remaining)`를 계산해 `new_allowed0`로 커서에 넣는다. 다음 페이지는 다시 계산하지 않는다.
6. **응답 조립**: 평가 URL과 `shared_deck_id` 문맥, `card_version`, `config_version`, `sort_key`. `next_cursor`는 페이지가 꽉 찼고 남은 후보가 있을 때만 준다.
7. **라우트**: 로그인 → 매개변수 검증(`extra_new`는 400) → FSRS 모드 확인 → 커서 검증 → scope 권한 → 위 단계. 모든 DB 접근은 `get_connection(read_only=True)`.
8. **테스트·회귀**: `TEST_MATRIX.md` 전부. 기존 회귀 스크립트 7개, 감사 15개, 백엔드 전체, 프론트 테스트·타입 검사(프론트 무변경 확인), `git diff --check`.

## 4. 성능 메모

- 단기·장기 due는 B-1의 `(user_id, srs_engine, srs_participation, srs_effective_due_at)` 인덱스(두 카드 테이블)로 덮는다.
- 분류·정렬은 범위 안 카드 전체를 한 번 읽어 서버 메모리에서 한다(3절 3·4단계). 카드 수에 비례한다.
- 신규 집계(`introduced_today`)는 계정의 모든 로그를 카드별로 묶어 최솟값을 구하고 날짜를 비교한다. 로그 수에 비례한다. C-1은 같은 정의를 재사용하고 정확성을 우선한다.
- 1천·1만 카드 측정은 Gate E 범위다. 개선(카드 행에 첫 평가 시각 보관, 로그 `(user_id, seoul_date)` 인덱스 등)은 스키마 변경이므로 별도 승인한다.

## 5. 호환·중단 조건

다음 중 하나라도 생기면 구현을 멈추고 보고한다.

- 기존 `/study-items`, `/study-items/lexemes`, `/vocab-items`, 평가 URL의 응답이나 정렬이 달라짐(기존 테스트·회귀 스크립트·감사 실패 포함).
- 프론트 파일, 특히 `recent` 경로를 바꿔야 하는 상황.
- 조회 한 번으로 DB 행 수나 내용이 바뀜(행 수·행 지문 비교 실패, 읽기 전용 연결에서 쓰기 예외).
- legacy 모드 계정이 새 엔드포인트에서 409가 아닌 결과를 받음.
- 다른 계정 카드, 구독 해제 덱, 소유하지 않은 개인 덱 카드가 응답이나 집계에 섞임.
- 같은 lexeme이 한 응답이나 집계에서 두 번 나옴, 또는 개인과 구독이 표제어로 합쳐짐.
- 범주 합계가 `total_in_scope`와 다름.
- 큐의 `introduced_today`와 같은 시각 평가 응답의 `introduced_today`가 다름.
- 변조 커서나 다른 계정 커서가 200을 받음.
- 기존 데이터의 시각 문자열이 정규 형식이 아니어서 문자열 정렬이 틀어질 위험이 있음. 이때는 멈추고 정규화 방안을 별도 승인받는다(자동 변환하지 않음).
- 구현에 스키마 변경(인덱스 포함)이나 설정 쓰기가 필요해짐.
- SQLite와 PG에서 다르게 동작할 수밖에 없는 SQL이 필요해짐.

## 6. 실행 안전

- 테스트와 스크립트는 앱/DB import 전에 세션 전용 SQLite `DATABASE_URL`과 `APP_ENV=development`를 지정한다.
- 커서 서명 테스트는 테스트 전용 비밀값을 환경변수로 주입한다. 실제 비밀값을 쓰거나 출력하지 않는다.
- Neon·운영·기존 로컬 DB에는 접근하지 않는다.
- PostgreSQL은 `tests/_local_postgres_guard.py`를 통과한 빈 로컬 테스트 DB만 쓴다. 없으면 설치·원격 접속 없이 미검증으로 보고한다.
- 서버를 띄우면 자신이 띄운 것만 정리하고 기존 서버는 건드리지 않는다.

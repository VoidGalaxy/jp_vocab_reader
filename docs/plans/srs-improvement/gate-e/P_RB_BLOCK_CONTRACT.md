# P-RB 계정별 쓰기 차단 장치 계약 (보완 승인 반영, 2026-10-20)

2026-10-20 · `codex/fsrs-srs-replacement` · HEAD `e2c07f8` · 문서만 작성했다. 구현·DB 실행은 없다.

- 승인된 방향: B(계정별 차단). 강제 legacy 변환 없음(①). 사전 확인에서 복구 불가면 시작하지 않음. 운영 시험 평가 없음.
- 이 문서의 내용은 모두 **[제안]**이다. 현재 코드 사실은 **[사실]**로 표시했다.

## 1. 현재 코드 사실

- 모든 계정 쓰기는 트랜잭션 시작에서 `account_write.begin_account_write`를 거친다. [사실]
  - SRS 쓰기는 `storage.begin_card_write`를 통해 거친다.
  - 계정 삭제·롤백도 같은 함수를 쓴다.
  - SQLite는 `BEGIN IMMEDIATE`, PG는 `users` 행 `FOR UPDATE` 뒤 계정 존재를 확인한다.
- `AccountWriteError(code, status)`는 앱 공통 처리기가 `{"detail": code}`로 응답한다(`main.py:162`). [사실]
- 영수증 재시도(`find_receipt`)는 잠금을 얻은 **뒤에** 조회한다. [사실]
- 차단 상태를 저장하는 표나 값은 없다. [사실]

## 2. 차단 기록 `account_write_blocks`

| 열 | 내용 |
| --- | --- |
| `id` | 정수 PK |
| `user_id` | NOT NULL, FK `users(id)`, 삭제 동작 **RESTRICT**(PG·SQLite 동일) |
| `purpose` | 고정 값 `srs_recovery`(허용 목록) |
| `recovery_key` | 운영자가 정한 복구 실행 식별자(형식 제한, 고유) |
| `grant_hash` | 복구 허가 토큰의 SHA-256(토큰 원문은 저장하지 않음) |
| `status` | `active` · `released` |
| `active_user_id` | 활성일 때만 `user_id`, 해제 뒤 NULL. UNIQUE(계정당 활성 하나, 두 DB 공통 제약) |
| `run_watermark` | 설정 시점의 `srs_migration_runs` 최대 id(이후 이 계정의 롤백 실행 판별) |
| `changes_started` · `changes_started_at` | 복구 쓰기 시작 기록. 허가된 복구 쓰기와 **같은 트랜잭션**에서 1로 바뀐다 |
| `created_at` · `released_at` | 시각 |
| `release_reason` | 고정 코드: `completed` · `precheck_unrecoverable` (`operator_abandoned`는 이번에 허용하지 않음) |

- 계정당 `active`는 하나다(`active_user_id` UNIQUE. 부분 색인은 PG 업그레이드 검사 형식 밖이라 쓰지 않음).
- DB 행이라 프로세스 종료·재시작·여러 워커와 무관하게 유지된다.
- 메모리 상태, 시간 제한(TTL), 자동 만료는 없다.
- 해제는 행을 지우지 않고 `released`로 바꾼다. 이력이 남는다.

## 3. 직렬화 순서 (모두 계정 잠금 안, 한 트랜잭션)

- **설정**: 잠금 → `active` 행 확인 → 넣기 → commit.
  - 같은 `recovery_key`가 이미 `active`면 **같은 허가 토큰을 검증한 뒤** 그 행을 돌려준다(재호출). 토큰이 다르면 `recovery_grant_invalid`. 토큰 자동 교체는 없다.
  - 해제된 키의 재사용은 `recovery_key_used`로 거부한다.
  - 다른 키가 `active`면 `recovery_already_active`로 거부한다.
  - 잠금을 먼저 잡은 일반 쓰기는 설정보다 먼저 commit된다. 그래서 진행 중인 쓰기의 배출은 잠금 대기로 끝난다.
- **확인**: `begin_account_write`가 계정 존재 확인 직후 같은 트랜잭션에서 `active` 행을 읽는다. 잠금 뒤에 읽으므로 설정·해제와 직렬화된다.
- **해제**: 잠금 → `active`·키·허가 토큰 확인 → 해제 조건(6절) 확인 → `released` → commit.

## 4. 일반 쓰기의 거부와 읽기

- 차단 중 모든 일반 쓰기는 **409 `account_writes_blocked`**다. 쓰기는 0이고 그 트랜잭션은 롤백한다.
  - 대상: 카드·덱·용어·평가·진도·구독·발행·피드백·식별 표시·이전 적용·계정 삭제.
  - 계정 삭제(E-5b)도 사유를 `account_writes_blocked`로 통일한다. 삭제 도구는 `blocked`로 보고하고 `account_not_found`로 바꾸지 않는다(미리보기 사유에도 포함).
- **영수증 재시도도 409다.** 잠금 직후 거부하므로 재생 전에 멈춘다. 쓰기는 없다. 해제 뒤 같은 `request_id`로 다시 보내면 기존 규칙대로 재생된다.
- **읽기는 허용한다.** 큐·통계·목록·`/me`·로그인은 잠금을 잡지 않는다. 복구 중 화면이 바뀌는 상태를 보일 수 있다.
  - 남은 결정: 화면 안내가 필요한지, 큐가 차단 상태를 표시할지.

## 5. 복구 실행 경로 (차단이 롤백을 막지 않게)

- 차단 확인은 `begin_account_write(connection, user_id, recovery=None)`에서 한다.
  - 일반 경로는 `recovery`를 넘기지 못한다. 저장소 함수와 HTTP 라우트에 이 인자가 없다.
- 복구 도구만 `RecoveryGrant(user_id, block_id, token)`를 만든다. 운영자 CLI가 차단 설정 때 받은 토큰을 쓴다.
  - 이 허가는 다음 내부 함수에만 전달된다:
    - `rollback_plan(..., recovery=grant)`
    - 새 `switch_mode_after_check(..., recovery=grant)`
  - 잠금 안에서 확인하는 것: `user_id`가 잠금 대상과 같은지, `block_id`가 `active`인지, 토큰 해시가 같은지, 호출 목적이 허용 목록(`rollback`·`mode_switch`·`release`)에 있는지. 어긋나면 409 `recovery_grant_invalid`다.
- **토큰 원문**은 DB(해시만)·출력·로그·명령줄 인자에 남기지 않는다. 허가 객체의 표시(repr)에서 빠진다. 향후 CLI는 숨김 입력으로 받는다.
- 범용 allow·bypass 플래그와 HTTP 인자는 두지 않는다.
  - 허가는 한 계정과 한 차단(복구 실행)에 묶인다.
  - 해제 뒤에는 무효다.
  - 다른 계정의 잠금에는 쓸 수 없다.

## 6. 설정·재호출·실패·재시작·해제 조건

- **설정 전**: 읽기 전용 사전 확인을 한다(P_RB_PLAN 1-2). 복구 불가면 차단 없이 끝낸다.
- **설정 뒤**: 같은 사전 확인을 다시 한다. 복구 불가면 롤백 없이 해제한다(`precheck_unrecoverable`).
  - 이 해제는 DB가 무변경을 증명할 때만 허용한다: `changes_started = 0`이고, `run_watermark` 뒤 이 계정의 롤백 실행 행이 0.
  - `changes_started`는 허가된 복구 쓰기의 트랜잭션 안에서 바뀌므로, 그 쓰기가 롤백되면 함께 0으로 남고 커밋되면 함께 1로 남는다. 일부 롤백 뒤 재시작하면 1이므로 사전 확인 실패로 해제할 수 없다.
- **실패**:
  - 롤백 예외, 정상 반환의 결과 혼합, 전수 확인 불일치 어느 경우든 차단은 **유지**된다.
  - 실패나 시간 경과로 자동 해제하지 않는다.
- **재시작**: 도구가 죽어도 행이 남는다. 같은 `recovery_key`·토큰으로 다시 붙어 재개한다. 같은 `rollback_key`는 요약을 돌려준다.
- **해제**:
  - `completed`: 다음이 모두 확인됐을 때만 해제한다.
    - 실행 요약이 전부 `rolled_back`
    - FSRS 행 0
    - 모드 legacy
    - 사후 읽기 확인 통과(I1~I6, 로그 수)
  - `operator_abandoned`는 **이번에 허용하지 않는다**. 결과가 섞인 계정은 차단된 채 남고, 처리 정책은 별도 결정이다.
  - `completed`는 이번 단계에서 항상 거부한다(11절). 사후 검증 절차가 구현·승인될 때 다시 연다.
- **다른 계정**: 확인은 `user_id`가 같은 행만 본다. 다른 계정의 쓰기·잠금 대기·결과는 바뀌지 않는다.
  - 다른 계정의 구독처럼 차단 계정 소유 공유 덱의 계수를 바꾸는 쓰기는 그 계정의 잠금으로 실행되므로 막히지 않는다. 복구 대상(SRS 카드)과 겹치지 않는다.

## 7. 영향 범위

- **스키마**: SQLite·PG 두 생성 코드와 업그레이드 경로에 새 표 1개, 부분 고유 색인 1개가 든다.
- **E-5b 계정 삭제**:
  - `OWNED_TABLES`·`DELETE_ORDER`(users 앞)·`EXPECTED_TABLES`·두 DB의 기대 FK 목록에 추가해야 한다.
  - 추가하지 않으면 스키마 검사가 `schema_unverified`로 삭제를 막는다.
  - `active` 행이 있으면 삭제를 거부한다(`account_recovery_in_progress`). `released` 이력은 그 계정 자료로 함께 삭제한다.
  - 참조 검사(`_cross_references`)에는 다른 계정 참조가 없으므로 영향이 없다.
- **테스트 장치**: E-1 PG 장치의 선언 표 목록(`expected_schema_tables`)과 E-4 감사 소유 검사에 새 표를 넣어야 한다.
- **E-5a·E-5c**: 쓰기 라우트 목록은 바뀌지 않는다. 거부 사례만 추가된다.

## 8. 최소 검사표 (승인 뒤, 합성 SQLite·실제 PG)

| 검사 | 확인 |
| --- | --- |
| 잠금 양쪽 순서 | 쓰기가 먼저 잠금 → 차단 설정이 대기(PG 대기 상대) → 쓰기 커밋 보존. 차단이 먼저 → 쓰기 409·쓰기 0 |
| 일반 요청 거부 | 모든 쓰기 라우트(E-5a 목록)·계정 삭제·영수증 재시도가 409·쓰기 0. 읽기는 200 |
| 복구 범위 제한 | 허가로 롤백·모드 변경만 됨. 다른 계정·해제된 차단·틀린 토큰·일반 경로는 거부 |
| 실패 후 차단 유지 | 롤백 예외·결과 혼합·도구 재시작 뒤에도 `active`. 시간 경과로 해제 0 |
| 다른 계정 불변 | 차단 중 다른 계정 쓰기 정상, 그 계정 자료 해시 불변 |

## 9. 다음 구현 단위 (각각 별도 승인)

1. **차단 장치**: 표·색인, `begin_account_write` 확인, 409 코드, 허가 검증, E-5b·E-1·E-4 목록 반영, 8절 검사.
2. **복구 도구**: 운영자 CLI를 만든다.
   - 단계: 사전 확인 → 설정 → 재확인 → 실행별 롤백 → 전수 확인 → 모드 변경(한 트랜잭션) → 사후 읽기 확인 → 해제
   - 결과는 건수만 남긴다. 기본은 dry run이다.

남은 결정:
- 부분 복구 처리와 `operator_abandoned` 허용 여부
- 읽기 화면의 차단 안내
- `recovery_key`·토큰 전달 방식(CLI 입력, 저장하지 않음)

## 10. 구현 결과 (2026-10-20, 차단 장치만)

**변경:**
- 제품:
  - `app/srs/schema.py`: `account_write_blocks` 표. 두 DB 모두 `CREATE TABLE IF NOT EXISTS`로 만들거나 업그레이드한다.
  - `app/account_write.py`: 잠금 직후 차단 확인, `RecoveryGrant`, `changes_started` 기록. 표가 없는 구 스키마 DB에서는 차단이 없는 것으로 본다(카탈로그로 확인).
  - `app/account_blocks.py`(새 파일): 설정·재호출·조건부 해제(내부 경로)
  - `srs/storage.begin_card_write`·`migration.rollback_plan`: `recovery` 전달
  - `account_deletion`: 소유 표·삭제 순서·FK 목록, 미리보기 사유, `blocked` 보고
  - `invariant_audit` I1: 차단 행 소유 확인
- 테스트:
  - 새 파일: `test_p_rb_account_blocks.py`(SQLite 12), `test_p_rb_account_blocks_real.py`(PG 11)
  - 기존 파일:
    - `_e5b_fixture`: 해제된 차단 이력 추가로 삭제 대상 포함
    - `_e5c_support`: 잠금 래퍼가 키워드 인자를 받게 함
    - `_srs_e5_preflight`·`test_srs_e5_preflight`(표 25개), `test_srs_e2_compare` 표 목록

**검사:**

| 구분 | 결과 |
| --- | --- |
| P-RB SQLite | 12 통과 |
| P-RB 실제 PG | 11 통과. 두 잠금 순서 모두 대기 backend의 `pg_blocking_pids`가 보유 쪽 backend를 가리킴(잠금 종류는 기록하지 않음) |
| 변형(메모리) | SQLite 6/6, PG 6/6 검출: 차단 미확인, 토큰 미확인, 진행 기록 누락, 사전 해제의 변경 무시, 재호출 토큰 미확인, 삭제가 `account_not_found` 보고 |
| E-5a·E-5b·E-5c SQLite | 165 통과(해제 이력이 든 fixture로) |
| 백엔드 전체(PG opt-in 해제) | 1130 실행: 996 통과, 134 건너뜀 |
| 실제 PG 묶음(모든 `*_real` 14개) | 113 실행: 112 통과, 예상 실패 1(알려진 업그레이드 교착) |

- 첫 전체 실행에서 실패 40건이 나왔다. 원인은 셋이고, 모두 고친 뒤 다시 실행했다.
  - 구 스키마 DB의 표 부재
  - 기존 잠금 감시 래퍼가 키워드 인자를 받지 못함
  - 표 분류 목록 2곳
- 그 실행이 남긴 임시 폴더 5개는 생성 시각으로 확인하고 지웠다. 기존 19개는 그대로다.

**미검증·범위 밖:**
- 복구 CLI, 모드 전환 도구, I1~I6 사후 확인을 묶은 해제 절차, 화면 안내
- 여러 서버 프로세스의 실제 운영 배치
- 운영 DB 업그레이드

**정리:**
- 시작한 PG(PID 12328)는 빈 DB 확인 뒤 종료했고, 리스너는 없다.
- `vocab.db`·`.env`·운영에는 접근하지 않았다. 스테이징·커밋은 하지 않았다.

차단 장치 구현 검토 대기. 복구 도구는 시작하지 않았다.

## 11. 검토 보정 두 건 (2026-10-20)

**1. 활성 차단의 NULL 우회**
- 수정 전(재현): active 행의 `active_user_id`를 NULL로 바꿀 수 있었다. 상태 CHECK에서 `NULL = user_id`가 거짓이 아니라 "알 수 없음"이라 통과했기 때문이다. 그 결과 일반 쓰기가 통과했고, 같은 계정에 active 행이 2개 생겼다.
- 수정 후 제약: 이름 붙은 CHECK `account_write_blocks_active_state`. active 행이면 `active_user_id IS NOT NULL AND active_user_id = user_id`여야 한다.
- 수정 후 조회: `active_user_id`만 보지 않는다. 그 계정에서 깨끗이 해제되지 않은 모든 행(상태 또는 표시)을 읽는다.
  - 행이 정확히 하나이고 상태·소유자·표시가 일치할 때만 정상 차단으로 본다.
  - 불일치나 중복이면 일반 쓰기는 `account_writes_blocked`로 거부한다. 설정·해제·허가는 `recovery_block_inconsistent`로 거부한다.
  - 삭제 미리보기도 같은 조건으로 `account_writes_blocked`를 보고한다.
  - 불일치 자료를 자동으로 고치거나 지우거나 다른 계정에 연결하지 않는다.
  - E-4 I1은 상태와 표시의 불일치를 위반으로 센다.
- 업그레이드: 이전 정의의 표만 바꾼다. 행·id·이력·고유 표시는 보존한다. 다시 실행하면 아무것도 하지 않는다.
  - PG: 스키마 트랜잭션 안에서 `ALTER TABLE … DROP CONSTRAINT …, ADD CONSTRAINT …`
  - SQLite: SAVEPOINT 안에서 표를 다시 만들고 `sqlite_sequence`를 보존
  - 새 제약에 맞지 않는 행이 있으면 바꾸기 전에 `account_write_blocks_rows_inconsistent`로 중단한다.

**2. completed 해제**
- 수정 전: 모드가 fsrs만 아니면 통과했다. 그래서 shadow에서도 해제됐다.
- 수정 후: 이번 단계에서 `completed`는 항상 `release_not_allowed`다. legacy·shadow·fsrs·설정 누락 모두 차단이 유지되고 쓰기는 0이다.
- `completed`는 사후 검증 절차가 구현·승인될 때 다시 여는 **후속 기능**이다.
- `precheck_unrecoverable`(DB 무변경 증명)과 `operator_abandoned` 금지는 그대로다.
- 기존 검사의 "completed 성공" 기대값은 "모든 모드에서 거부"로 바꿨다. 사후 확인이 없는 상태에서 성공을 기대하는 것 자체가 결함이었기 때문이다.

**검사:**

| 구분 | 결과 |
| --- | --- |
| 수정 전 새 검사 | SQLite에서 실패 확인: 표시 NULL·약한 스키마 조회 3, 업그레이드 3, completed 1(모드 4개 하위 사례) |
| P-RB SQLite | 18 통과(기존 12 + 표시 1 + 약한 스키마 조회 2 + 업그레이드 3. completed 사례는 기대값 교체) |
| P-RB 실제 PG | 15 통과(기존 11 + 표시 1 + 업그레이드 3, 잠금 순서 대기 상대 포함) |
| 변형 | SQLite 4/4, PG 3/3 검출: NOT NULL 제거, 업그레이드 생략, completed 재개방, 표시만으로 조회(SQLite 전용) |
| 관련 SQLite | 228 통과(E-5a·E-5b·E-5c, preflight, E-2 비교, 스키마, 구 구조 리허설 2종) |
| 관련 실제 PG | 37 통과(E-5b 삭제, E-13 init DDL, E-2b 업그레이드, E-3 FK, E-4 감사, E-5a 쓰기) |

**미검증:**
- 약한 스키마 위의 조회 실패 닫힘은 SQLite에서만 확인했다. PG는 제약 검사와 업그레이드로 확인했다.
- 백엔드 전체·프론트·빌드는 지시대로 다시 실행하지 않았다.
- 운영 DB 업그레이드

**정리:** 시작한 PG(PID 64912)만 빈 DB 확인 뒤 종료했다. 임시 폴더는 기존 19개 그대로다. 커밋은 하지 않았다.

차단 장치 재검토 대기.

## 12. 업그레이드 자료 삭제 결함 보정 (2026-10-20)

- **수정 전:**
  - SQLite 재구성이 알려진 열만 복사한 뒤 기존 표를 지웠다. 그래서 추가 열의 값과 추가 색인·트리거가 사라졌다.
  - 정상 구조 판정은 CHECK 문자열 일부(`active_user_id IS NOT NULL`)에 의존했다.
  - PG는 `released_at`이 든 CHECK를 모두 지웠다.
  - 새 회귀 검사 9종 모두 수정 전에 실패했다(SQLite).
- **수정 후:**
  - 인정하는 구조는 둘뿐이다: 승인된 **이전 구조**(검토 보정 1 이전)와 **현재 구조**. 구조화된 카탈로그로 판정한다.
    - SQLite: 정규화한 표 정의 전체, 고유 색인 목록과 열, 다른 색인·트리거·뷰·다른 표의 FK 참조 없음
    - PG: 열(형식·NOT NULL·identity·기본값), NOT NULL 외 제약 전체(이름·종류·정의), 색인 정의, 트리거·참조 FK·규칙·정책·뷰 없음
  - 그 밖의 구조는 `account_write_blocks_structure_unrecognized`로 **변경 없이** 중단한다. 자동으로 삭제·수정·복구하거나 무시하지 않는다.
  - 이전 구조만 고친다.
    - SQLite: SAVEPOINT 안에서 재구성하고 행·id·`sqlite_sequence`를 보존한다.
    - PG: 정확히 이전 상태 제약 `account_write_blocks_check` 하나만 바꾼다.
    - 둘 다 바꾼 뒤 현재 구조인지 다시 확인한다.
  - 현재 구조를 다시 실행하면 아무것도 바꾸지 않는다.
  - NULL 우회 방지, 실패 시 거부하는 조회, completed 폐쇄는 그대로다.
- **주의:** PG 판정은 PostgreSQL 18이 출력하는 제약·색인 정의 문자열과 비교한다. 다른 주 버전에서 출력이 다르면 업그레이드가 무변경으로 거부된다(안전 쪽 실패). 운영 버전 18.6은 사용자가 알려 준 값이다.

| 구분 | 결과 |
| --- | --- |
| 수정 전 새 검사(SQLite) | 9/9 실패: 추가 열 값, 색인, 트리거, CHECK, FK, 참조 표, 뷰, 비슷한 문자열 CHECK, 현재 구조 + 추가 색인 |
| P-RB SQLite | 27 통과(18 + 거부 9. 실패 롤백·성공 사례는 객체·시퀀스까지 비교) |
| P-RB 실제 PG | 24 실행: 22 통과, 2 건너뜀(트리거·뷰는 함수·뷰 생성을 E-1 장치가 막아 **미검증**) |
| 변형 | 구조를 문자열로 판정: SQLite 9/9·PG 7/7 검출. SQLite 표 정의만 비교: 5/5 검출. 기존 NULL·업그레이드 생략·completed 재개방 변형: SQLite 4/4·PG 3/3 유지 |
| 관련 SQLite | 228 통과(E-5a·E-5b·E-5c, preflight, E-2 비교, 스키마, 구 구조 리허설) |
| 관련 실제 PG | 37 통과(E-5b, E-13 init DDL, E-2b 업그레이드, E-3 FK, E-4 감사, E-5a) |

**미검증:**
- PG의 트리거·뷰 거부
- PostgreSQL 18 외 버전의 카탈로그 출력
- 백엔드 전체(지시대로 생략)

**정리:** 시작한 PG(PID 112112)만 빈 DB 확인 뒤 종료했다. 임시 폴더는 기존 19개 그대로다. 커밋은 하지 않았다.

차단 장치 재검토 대기.

## 13. Codex 직접 보정: SQLite 식별자 표기 누락 (2026-10-20)

사용자가 직접 보정을 요청했다. 범위는 SQLite 차단 표 업그레이드의 참조·객체 판정이며 PG 경로, 차단 정책, completed 폐쇄는 바꾸지 않았다.

- **수정 전:** SQLite는 `ACCOUNT_WRITE_BLOCKS`도 같은 표로 해석하지만 검사에서는 이름을 그대로 비교했다. 그래서 대문자 참조 FK를 놓치고 재구성에 들어가 참조 행이 CASCADE로 삭제됐다. 대문자 표에 붙은 트리거도 삭제됐고, 뷰·다른 표의 트리거는 변경 전 거부 대신 재구성 중 일반 SQL 오류로 끝났다.
- **수정:** 식별자를 SQLite 규칙에 맞춰 ASCII 대소문자만 접어 비교한다. FK는 PRAGMA가 해석한 참조 이름, 색인·트리거는 카탈로그 소유 표 이름으로 판정한다. 뷰·트리거 본문의 보수적인 참조 검사도 같은 ASCII 비교를 사용한다. 인용·스키마 한정 표기라고 무시하지 않는다.
- **이름 전달:** `pragma_foreign_key_list(?)`와 `pragma_index_info(?)`에 객체 이름을 매개변수로 전달한다. 이름 안의 따옴표가 SQL 문법을 바꾸지 않는다. 승인되지 않은 색인은 열을 읽기 전에 거부한다.
- **새 회귀 8개:** FK·색인·트리거·뷰 각각 대문자·혼합·큰따옴표·대괄호·백틱 표기, 다른 표 트리거의 한정 참조, 따옴표가 있는 무관한 표, ASCII와 Unicode 비교의 구분, 표현식 색인 거부. 거부 시 표 정의·색인·트리거·뷰·시퀀스와 참조 행을 보존한다.

| 검사 | 결과 |
| --- | --- |
| 보정 전 새 회귀 6개 | 하위 사례 기준 10 실패·12 오류. 나머지 2개는 보정 후 추가한 보조 검사 |
| 보정 후 P-RB SQLite | 35 통과(기존 27 + 새 8) |
| P-RB·SRS 스키마·E-5b 집중 묶음 | 87 실행: 86 통과·PG 전용 1 건너뜀 |
| 대소문자 접기를 제거하는 메모리 변형 | FK·트리거 2개 검사, 하위 사례 10/10 실패로 검출 |
| diff·수정 코드 뒤 공백 검사 | 통과 |

**미실행:** 실제 PG·운영 DB·전체 백엔드·프론트·빌드는 반복하지 않았다. SQLite 전용 경로의 보정이며 기존 PG 미검증 항목은 그대로다.

변경 파일은 `app/srs/schema.py`, `tests/test_p_rb_account_blocks.py`, 이 문서와 REPORT 24-3절이다. 테스트는 세션 전용 합성 SQLite만 사용하고 임시 폴더를 정리했다. 서버는 시작하지 않았고 기존 DB·기존 임시 폴더·사용자 변경을 건드리지 않았다. 스테이징·커밋·푸시는 하지 않았다.

차단 장치 재검토 대기. 복구 CLI는 시작하지 않았다.

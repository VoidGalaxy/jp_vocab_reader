# P-RB 복구 도구 상세 계약안 (보정판, 검토 대기)

2026-10-20 · `codex/fsrs-srs-replacement` · HEAD `e2c07f8` · 문서만 작성했다(구현·DB 실행 없음).
근거: `P_RB_PLAN.md`, `P_RB_BLOCK_CONTRACT.md`(13절까지), `account_blocks`, `account_write`, `migration.rollback_plan`·`apply_plan`, `restoration._undone_by_completed_rollback`, `invariant_audit`.

**보정(2026-10-20 2차):**
1. 기존 롤백 상태의 의미: `aborted`만으로 롤백됐다고 보지 않는다.
2. 삭제 증명과 성공 집계를 구분했다.
3. 트랜잭션 경계와 `plan_changed`의 실제 쓰기 범위를 적었다.
4. 검증 결과를 자료 지문에 묶고, 기준 날짜를 고정했다.
5. 24시간 여유는 경고로 바꿨다. 진행 기록은 계정당 활성 1개로 정했다.

표기:
- **[사실]** 지금 코드
- **[제안]** 승인받을 안

유지하는 것: 강제 legacy 변환 없음, `operator_abandoned` 없음, 운영 계정 시험 평가 없음, 자동 해제 없음. **completed 해제는 이번에도 닫혀 있다**(4-4는 재개방 조건의 제안일 뿐이다).

## 0. 현재 코드 사실

- **공개 롤백 API.** `rollback_plan(run_key, rollback_key, …)`는 자기 연결에서 apply 실행 **하나**를 한 트랜잭션으로 처리하고 커밋한다. [사실]
  - 카드별 결과(`rolled_back`·`conflict`·`blocked`·`skipped`·`missing_or_access_lost`)를 롤백 실행의 `summary_json`에 남긴다.
  - `rolled_back` 카드만 롤백 실행의 snapshot(`baseline`: 카드 버전·카드 지문·로그 지문·마지막 로그 id)을 남긴다.
  - 결과가 섞여도 롤백 실행은 `completed`, 원래 apply 실행은 `aborted`가 된다.
  - 롤백 실행의 `scope_json`에는 `source_run_id`가 들어 있다.
- **`aborted`의 출처.** `aborted`는 롤백만 만들고, `apply_plan`의 재개를 막는 데 쓰인다. [사실] 따라서 `aborted`는 "롤백이 한 번 실행됐다"는 뜻이지 "모든 카드가 롤백됐다"는 뜻이 아니다.
- **apply 상태.** `apply_plan`은 카드마다 커밋하고, 실행 상태는 `started` → `completed` 또는 `failed`다. [사실]
- **삭제 원장.** `srs_card_deletions`는 개인 카드만 기록한다(`card_kind = 'personal'`). 구독 진도 행에는 삭제 원장이 없다. [사실]
- **차단.** `begin_account_write`는 허가가 있으면 같은 트랜잭션에서 `changes_started = 1`로 바꾼다. 이미 1이면 시각만 처음 값으로 유지된다. 즉 쓰기 횟수는 세지 않는다. [사실]
- **해제.** `release_block`은 `precheck_unrecoverable`만 허용하고 completed는 항상 거부한다. [사실]

## 1. 입력과 기본 동작 [제안]

- 운영자 CLI `scripts/prb_recover.py`(HTTP 없음)의 하위 명령: `preview` · `apply` · `verify` · `release`.
  - 대상: `--user-id`, `--recovery-key`. `apply`·`release`에는 `--plan <64자 지문>`도 필요하다.
- **기본은 `preview`다.** 읽기 전용 스냅숏에서 실행하고 쓰기는 0이다. 출력은 건수·사유 코드·지문·경고뿐이다.
- `apply`는 다시 입력한 계정 id, 복구 키, 지문이 미리보기와 모두 같을 때만 진행한다.
- **허가 토큰은 숨김 입력(`getpass`)만 쓴다.** 명령줄·환경 변수·파일로 받지 않고, 출력·로그·예외에 남기지 않는다. DB에는 해시만 둔다.

## 2. 실행 상태, 트랜잭션 경계, 재개 [제안]

### 2-1. 진행 기록 `account_recovery_runs`

- **계정당 활성 기록은 최대 1개다.** 종료된 기록은 이력으로 남는다(전체 이력이 1개라는 뜻이 아님).
  - 활성 표시 열 `active_user_id` UNIQUE를 둔다. 차단 표와 같은 방식이다.
  - 상태 CHECK: 활성이면 표시가 NOT NULL이고 `user_id`와 같다.
- 열(내용 없는 값만):
  - `id`, `user_id`(FK users RESTRICT), `block_id`(FK 없음: 승인된 차단 표 구조가 들어오는 참조를 허용하지 않으므로, 코드와 E-4 I1이 같은 계정·같은 키의 차단인지 확인), `recovery_key` UNIQUE
  - `plan_fingerprint`, `state`, `active_user_id`, `source_runs_json`
  - `baseline_json`(4-2절. 기준 시각과 날짜 목록 포함)
  - `verification_json`, `verified_digest`
  - `prepared_at`, `applied_at`, `verified_at`, `closed_at`, `close_reason`
- **상태:** `prepared` → `applied` → `verified` → `closed`. 역행하지 않는다.
  - `prepared`에서 바로 `closed`로 갈 수도 있다(무변경 해제).
  - `close_reason`은 `precheck_unrecoverable`이다. `completed`는 재개방 승인 뒤에만 쓴다.
- **재복구:** 차단을 해제하면 기록이 닫히고 활성 표시가 비워진다. 그 뒤 새 복구 키로 새 기록을 만든다. 닫힌 기록과 해제된 차단 이력은 보존하고, 계정 삭제 때 함께 지운다(E-5b 소유 표).

### 2-2. 커밋 경계

| 단계 | 연결·트랜잭션 | 하는 일 | 커밋되는 쓰기 |
| --- | --- | --- | --- |
| `preview` | 읽기 전용 스냅숏 | 3절 판정, 지문, 경고 | 없음 |
| **A 준비** | 새 연결 1개, 한 트랜잭션, 계정 잠금 | 차단 설정 → 같은 잠금 아래 3절 재판정과 지문 비교 → 기준선 계산 → 진행 기록 `prepared` | 차단 행 1개와 진행 기록 1개. **둘이 함께 커밋된다** |
| A에서 `plan_changed`·차단 조건 발견 | 같은 트랜잭션을 롤백 | 없음 | **없음**. 차단도 기록도 남지 않는다 |
| **B 복구** | 새 연결 1개, 한 트랜잭션, 계정 잠금 + 허가 | 3절 재판정과 지문 비교 → 내부 롤백 함수(연결을 받음, 커밋하지 않음)로 대상 실행 전부 처리 → 집계식(3-3) 확인 → FSRS 0 확인 → 모드 legacy(정확히 1행) → 진행 기록 `applied` | 카드·롤백 실행·snapshot·원래 실행 상태·설정·차단 진행 표시·진행 기록. **전부 함께 커밋되거나 전부 롤백된다** |
| B 실패 | 롤백 | 없음 | 없음. 차단은 A 때문에 남고, 기록은 `prepared`, `changes_started`는 0 |
| **verify 읽기** | 읽기 전용 스냅숏 R | 4-3 검사, 검증 대상 자료의 지문 D 계산 | 없음 |
| **verify 저장** | 새 연결, 한 트랜잭션, 계정 잠금 | 잠금 아래 지문 D를 다시 계산해 R의 값과 비교 → 같으면 `verified`와 D 저장 | 진행 기록 1행. 다르면 쓰기 없이 `verification_stale` |
| 무변경 해제 | 계정 잠금 | 기존 증명 조건 확인 → 차단 해제, 기록 `closed` | 차단 행·기록 행 |

- **공개 `rollback_plan`의 동작은 바꾸지 않는다.** 새 경로는 다음 두 함수로 분리한다.
  - 카드별 판정 순수 함수: 공개 API와 공유한다.
  - 연결을 받는 내부 실행 함수
- 커밋·롤백은 최상위 복구 함수(A·B·verify 저장·해제)만 한다.
- 내부 함수의 예외는 최상위 함수가 받아 롤백한다.

### 2-3. 재개 (DB에서만 판단)

| 저장 상태 | 판단 | 다음 동작 |
| --- | --- | --- |
| 활성 기록 없음, 차단 없음 | 시작 전 | `preview`부터 |
| `prepared`, `changes_started = 0`, 대상 원래 실행이 모두 `completed`, 결정론적 키 롤백 실행 없음 | B 미실행 | B 재시도 |
| `applied`, `changes_started = 1`, 대상 원래 실행이 전부 `aborted`, 결정론적 키 롤백 실행이 전부 `completed` | B 완료 | `verify` |
| `verified` | 검증 완료 | 해제 대기(completed는 닫혀 있음) |
| 그 밖의 조합 | 불일치 | 차단 유지, 보고만 함. 자동 보정 없음 |

예: `prepared`인데 `changes_started = 1`이거나, 결정론적 키 롤백 실행이 일부만 있는 경우.

결정론적 롤백 키는 `prb:<recovery_key>:<source_run_id>`다. 같은 키 재호출의 저장 요약과 새 실행을 이 키와 진행 기록 상태로 구분한다. B는 원자적이라 일부 키만 존재하는 상태는 정상 경로에서 생기지 않는다.

## 3. 사전 판정 [제안]

### 3-1. 기존 롤백 기록과 재전환 이력 (보정 3차)

**과거 롤백의 증명**과 **현재 복구 대상의 판정**을 나눈다. 현재 카드가 FSRS라는 이유만으로 과거 롤백을 무효로 보지 않는다. 정상 재전환(A → A 롤백 → B)이면 카드는 B 때문에 FSRS다.

**(1) apply 실행 단위의 과거 롤백 증명** (실행 자체만 본다. 카드의 현재 엔진은 보지 않는다)

| 분류 | 조건 | 처리 |
| --- | --- | --- |
| 대상 | `completed` | 이번 복구에서 롤백 |
| 롤백 증명됨 | `aborted`이고, `source_run_id`로 연결된 `completed` 롤백 실행이 정확히 1개이며, 그 요약이 비어 있지 않고 모두 `rolled_back` | 대상 아님. 카드 사슬로 다시 확인(2) |
| 기존 부분 롤백 | `aborted`이고 요약에 `rolled_back` 외 결과가 있음 | `prior_partial_rollback`으로 차단 |
| 설명 불가 | `aborted`인데 연결 롤백 실행이 0개 또는 2개 이상, 요약을 읽을 수 없거나 비어 있음 | `prior_rollback_unverifiable`로 차단 |
| 진행 중·실패 | `started`·`failed` | `migration_run_in_progress` / `migration_run_failed`로 차단 |

**(2) 카드 사슬** (카드별로 이 계정의 apply·롤백 snapshot을 id 순으로 늘어놓은 것)

| 사슬 | 판정 |
| --- | --- |
| apply(A, `completed`) | A의 대상 카드 |
| apply(A) → rollback(A의 롤백) | 지금 legacy여야 한다. 현재 카드가 legacy이고 버전 ≥ 롤백 뒤 버전이면 정상. 카드가 없으면(이후 삭제) 남은 카드 없음 |
| apply(A) → rollback(A) → apply(B, `completed`) | **정상 재전환**. A의 롤백은 증명된 과거이고, 카드는 B의 대상이다 |
| A → rb(A) → B → rb(B) → C(`completed`) | **반복 재전환**. 마지막 apply C의 대상이다 |
| apply 다음에 또 apply(롤백 없이) | `overlapping_source_runs`, `card_history_ambiguous`로 차단 |
| 롤백 기록이 바로 앞 apply 실행의 롤백이 아님, 또는 사슬이 롤백으로 시작 | `card_history_ambiguous`로 차단 |
| 다음 기록의 `card_version_before`가 앞 기록 뒤 버전보다 작음 | `card_history_ambiguous`로 차단 |
| 마지막이 롤백인데 현재 카드가 FSRS이거나 버전이 뒤로 감 | `card_history_ambiguous`로 차단(자동 추정 없음) |
| 마지막이 `aborted` 실행의 apply(그 롤백이 이 카드를 남김) | `prior_partial_rollback`으로 차단 |
| 다른 계정 실행의 snapshot이 이 계정 이름으로 있음 | `card_history_ambiguous`로 차단 |

- 연결은 `srs_migration_runs.scope_json`의 `source_run_id`, snapshot의 `run_id`·`card_version_before`로만 확인한다.
- 연결이 없거나 모호하면 차단한다. 현재 엔진 검사를 빼서 통과시키지 않는다.
- 기존 부분 롤백은 공개 API로 생긴 과거 상태다. 새 도구의 원자적 복구는 이런 상태를 만들지 않는다.

### 3-2. 카드별 판정 (대상 실행의 snapshot 카드마다, 읽기만)

| 판정 | 조건 | 결과 |
| --- | --- | --- |
| 롤백 가능 | 카드 존재·접근 가능, 식별 표시 없음, snapshot 완전, 엔진·설정·버전 사슬 일치, 이후 로그 읽기 가능·순서 일치 | `rollback` |
| **삭제 증명됨** | 아래 4개를 모두 만족 | `deleted_proven`(쓰기 없음, 복원 없음) |
| 접근 상실 | 진도 행은 있으나 구독·접근 없음 | `access_lost`로 차단(삭제로 보지 않음) |
| 그 밖 | snapshot 불완전, 충돌, 식별 불가, 이력 읽기 불가·순서 불일치 | 각 사유로 차단 |

삭제 증명 조건(개인 카드만):
1. 개인 카드 행이 없다(어느 계정에도 같은 id가 없다).
2. 삭제 원장에 `(user_id, 'personal', card_ref)` 행이 있다.
3. 그 `deleted_at`을 읽을 수 있고, 원래 실행의 `started_at` 이후다.
4. 그 id에 식별 불가 표시가 없다.

구독 진도 행은 원장이 없으므로 행이 없으면 `card_missing_unproven`으로 차단한다.

계정 단위 판정(하나라도 있으면 차단):
- snapshot 없는 FSRS 개인 카드·진도 행(`fsrs_card_without_snapshot`, ①)
- 대상 실행끼리 카드 겹침(`overlapping_source_runs`)
- 실제 기간 만료·확인 불가(`rollback_window_closed` / `rollback_window_unverifiable`). preview·A·B 모두에서, B는 잠금 아래 다시 검사한다.
- 계정 모드가 fsrs·shadow가 아니거나 설정 행 없음(`srs_mode_unexpected`)
- 차단·기록 불일치

### 3-3. 성공 집계식

대상 실행의 snapshot 카드 전체 수를 N이라 할 때, B는 다음이 모두 참일 때만 커밋한다.
- `rolled_back` + `deleted_proven` = N
- 다른 판정 0
- `deleted_proven`은 B 안에서 다시 확인한 값이다.

`deleted_proven`은 롤백 성공으로 세지 않는다. 기록에는 따로 남긴다. 모든 항목에 `rolled_back`을 요구하지 않으므로 삭제 카드 때문에 막히지 않는다. 대신 삭제가 증명되지 않은 결측은 막는다.

### 3-4. 기간 여유

- **권장안(경고):** 남은 기간이 24시간 미만이면 preview·A에서 `rollback_window_margin` **경고**만 낸다. 진행은 막지 않는다.
- **강제안(대안):** 같은 조건에서 시작을 거부한다.
- 어느 쪽이든 실제 만료·확인 불가는 거부하고, B 안에서 잠금 아래 다시 검사한다. B가 원자적이라 도중 만료로 부분 상태가 남지 않는다.
- 두 안 중 무엇을 쓸지는 승인 항목이다.

## 4. 완료 증명 [제안]

**4-1. B의 같은 트랜잭션:** 다음을 하고, 하나라도 어긋나면 B 전체를 롤백한다.
- 3-3 집계 성립
- 계정의 개인 카드·진도 행에서 `srs_engine = 'fsrs'`가 0
- `UPDATE srs_user_settings SET srs_mode = 'legacy', settings_version = settings_version + 1 WHERE user_id = ? AND srs_mode = <계획의 이전 모드>`가 정확히 1행
- 기록 `applied`

**4-2. 기준선(A에서 계산, 차단과 같은 트랜잭션):**
- 기준 시각과 날짜 목록을 **저장**한다. 날짜 목록은 계정 로그의 서울 날짜 전부와 기준 시각의 날짜다. 자정이 지나도 I7 비교 대상이 바뀌지 않는다.
- 계정 로그 행 해시와 건수
- 카드별 보존 열(`ROLLBACK_PRESERVED`) 해시
- 저장한 날짜별 I7 지표(그 날짜 정오 서울 기준으로 계산하는 E-4 방식)
- 대상 카드·버전 목록

**4-3. verify:** 읽기 전용 R에서 계산한다.

| 검사 | 기준선 |
| --- | --- |
| I1·I2·I3·I4·I5 | 불필요 |
| I6(복구용): 계정 로그 해시·건수 일치 | 4-2 |
| I7(복구용): 저장한 날짜별 지표 일치 | 4-2(저장된 날짜·시각) |
| 완료 이력: 보존 열 해시 일치 | 4-2 |
| 결과: FSRS 0, 모드 legacy, 원래 실행 `aborted`, 결정론적 키 롤백 실행 요약이 3-3 집계 성립 | 진행 기록 |

- 결과는 `pass`·`fail`·`unknown`·`not_evaluated`를 그대로 저장한다. **`not_evaluated`를 `pass`로 바꾸지 않는다.** 전부 `pass`일 때만 `verified`다.
- **검증 지문 D** (보정 3차, 필드 고정). 아래 목록 그대로 계정 범위 행을 id 순으로 정렬한 canonical JSON의 SHA-256이다.

  | 출처 | 포함 필드 |
  | --- | --- |
  | `vocab_items`, `user_word_progress` (계정 행) | 전체 열 |
  | `review_logs`, `lexeme_review_logs` (계정 행) | 전체 열 |
  | `srs_migration_runs` (scope가 이 계정) | 전체 열 |
  | `srs_migration_snapshots` (계정 행) | 전체 열 |
  | `srs_user_settings`, `srs_card_deletions`, `srs_card_identity_flags`, `srs_evidence_restarts`, `srs_review_receipts` (계정 행) | 전체 열 |
  | `account_write_blocks` (이 차단 행) | `id`, `user_id`, `recovery_key`, `grant_hash`, `status`, `active_user_id`, `run_watermark`, `changes_started`, `changes_started_at` |
  | `account_recovery_runs` (이 기록) | `id`, `user_id`, `block_id`, `recovery_key`, `plan_fingerprint`, `source_runs_json`, `baseline_json`, `prepared_at`, `applied_at` |

  - 지문에서 **빼는 것**: 진행 기록의 `state`, `active_user_id`, `verification_json`, `verified_digest`, `verified_at`, `closed_at`, `close_reason`. 그래서 `verified` 저장이 지문을 바꾸지 않는다.
  - 빠진 값은 지문 대신 **별도 상태 검사**로 확인한다: 해제 때 `state = 'verified'`, 활성 표시 = 계정, `closed_*` NULL, 저장된 `verification_json` 전부 `pass`.
  - 실제 복구 자료(카드·로그·실행·snapshot·설정·차단 진행 표시)는 모두 포함 필드에 있다. 그래서 어떤 변경이든 지문 차이로 검출된다.
  - R에서 계산하고, 저장 트랜잭션에서 잠금 아래 다시 계산해 같을 때만 저장한다(verify는 이번 단위에서 구현하지 않는다).

**4-4. completed 해제를 다시 여는 조건(이번에는 열지 않음, 제안):**
- 계정 잠금 안에서 D를 다시 계산해 저장값과 같다.
- 기록이 `verified`이고, 지문·차단·키·토큰이 일치한다.
- 저장된 검사가 전부 `pass`다.
- **검증 뒤 허가된 복구 쓰기가 없었다.**
  - D가 카드·설정·실행 행을 덮으므로, 자료를 바꾼 쓰기는 지문 차이로 잡힌다.
  - 자료가 결과적으로 같은 쓰기까지 막으려면 차단 행에 `recovery_write_seq`(허가 쓰기마다 +1)를 추가하고 D에 넣는다. 이는 차단 표 구조 변경이라 업그레이드 허용 구조가 추가된다. 승인 항목이다.
- 어긋나면 `release_not_allowed`이고 차단을 유지한다.

## 5. 시나리오별 기대 결과

| 시나리오 | 기대 결과 |
| --- | --- |
| 정상 복구(실행 2개, 삭제 없음) | A: 차단+기록 커밋. B: 전부 `rolled_back`, FSRS 0, legacy, `applied`. verify: 전부 `pass`, `verified`. 해제는 completed가 닫혀 있어 대기 |
| 기존 부분 롤백(`aborted`, 요약에 `skipped`) | preview·A: `prior_partial_rollback`. A 롤백 → 차단·기록 없음. 쓰기 0 |
| `aborted`인데 연결 롤백 실행 없음 | `prior_rollback_unverifiable`, 위와 같음 |
| 삭제 증명된 개인 카드 1장 + 나머지 정상 | B: `rolled_back` N−1 + `deleted_proven` 1 = N → 커밋. 삭제 카드는 복원하지 않음 |
| 개인 카드 없음 + 원장 없음, 또는 구독 진도 행 없음 | `card_missing_unproven`으로 차단, 쓰기 0 |
| 접근 상실 진도 행 | `access_lost`로 차단(삭제로 보지 않음) |
| preview 뒤 계획 변경 | A 안에서 `plan_changed` → A 롤백. **차단·기록 모두 남지 않음**, 쓰기 0 |
| A 뒤, B 전 계획 변경(차단 중이라 일반 쓰기 불가, 기간 만료 등) | B 안에서 판정 실패 → B 롤백. 차단·`prepared` 유지, `changes_started = 0` → 무변경 해제 가능 |
| B 중간 실패(예외 주입) | B 전체 롤백. 위와 같음 |
| 검증 뒤 허가된 복구 쓰기 | 지문 D 불일치(또는 `recovery_write_seq` 불일치) → 해제 거부, 다시 verify 필요 |
| R과 저장 사이 변경 | `verification_stale`, 저장 없음 |
| 자정 경과 뒤 verify | 저장한 기준 시각·날짜로 I7 비교 → 결과 불변 |
| 남은 기간 24시간 미만 | 권장안: 경고만. 강제안: 시작 거부 |
| 기간 만료(B 직전) | B 안 재검사로 거부, 쓰기 0, 차단·`prepared` 유지 |
| 프로세스 종료(A 뒤 / B 뒤 / verify 뒤) | 2-3 표대로 이어 감. 불일치 조합은 보고만 함 |

## 6. 예상 변경 파일

- 제품:
  - `app/srs/migration.py`: 카드별 판정 순수 함수(공개 API와 공유), 연결을 받는 내부 실행 함수. 공개 `rollback_plan` 동작 불변
  - 새 파일 `app/recovery.py`: 판정·지문·기준선·A·B·verify·해제 최상위 함수(커밋은 여기서만)
  - `app/srs/schema.py`: `account_recovery_runs`. 선택 시 차단 표 `recovery_write_seq`와 업그레이드 허용 구조
  - `app/account_write.py`: 선택 시 허가 쓰기 순번 증가
  - `app/account_blocks.py`: 해제 시 진행 기록 닫기(completed 재개방은 별도 승인)
  - `app/account_deletion.py`: 소유 표·삭제 순서·FK 목록, 활성 기록이면 삭제 보류
  - `app/srs/invariant_audit.py`: 복구용 I6·I7 비교, 새 표 소유 확인
- 도구: `scripts/prb_recover.py`
- 테스트:
  - 새 파일: `test_p_rb_recovery.py`, `test_p_rb_recovery_real.py`
  - 표 목록 갱신: `_srs_e5_preflight`, `test_srs_e5_preflight`, `test_srs_e2_compare`, `_e5b_fixture`
- 문서: 이 계약, REPORT

검사표는 5절 시나리오 각각을 합성 SQLite와 보호된 실제 PG에서 확인하는 것으로 한다. 여기에 다음을 더한다.
- 공개 `rollback_plan`의 기존 검사 회귀 없음
- 토큰이 명령줄·출력에 없음
- 다른 계정 불변

## 7. 다음 구현 단위 (각각 별도 승인)

1. **사전 확인·재개:**
   - 카드별 판정 분리, 3-1~3-4 판정
   - 지문, `preview`
   - `account_recovery_runs`와 A 단계, 2-3 재개 판정
   - 이 단위는 복구 자료를 바꾸지 않는다(차단·기록만).
2. **복구·완료 증명:**
   - 내부 실행 함수와 B 단계
   - verify(R + 잠금 아래 지문 저장)
   - 진행 기록 닫기
   - completed 재개방은 이 단위에서도 별도 승인 전까지 닫아 둔다.

## 8. 승인할 항목

1. A·B 경계와 원자적 B(롤백 + 집계 + FSRS 0 + 모드 + 상태)
2. 3-1 기존 롤백 분류(부분 롤백·설명 불가 차단)
3. 3-2 삭제 증명 4조건과 3-3 집계식
4. 3-4 기간 여유: **경고(권장)** 또는 강제 거부
5. `account_recovery_runs`(계정당 활성 1개, 이력 보존)와 결정론적 롤백 키
6. 검증 지문 D, 저장된 기준 날짜. 선택: `recovery_write_seq`(차단 표 구조 변경 포함)
7. completed 재개방 조건(4-4). 이번에는 열지 않음
8. 구현 단위 분할(7절)

## 9. 구현 상태: ① 사전 확인·재개 (2026-10-20)

① 구현 검토 대기다. B 복구·모드 변경·verify·completed 해제는 구현하지 않았다. 실제 복구나 운영 준비 완료가 아니다.

**구현:**
- `migration.judge_rollback_card`: 카드별 롤백 판정(읽기 전용). 공개 `rollback_plan`은 이 판정을 쓰되 결과·트랜잭션 계약은 그대로다.
- `app/recovery.py`:
  - 3-1 사슬 판정과 3-2 카드 판정(삭제 증명 4조건 포함)
  - 기간 판정(만료·확인 불가는 차단, 24시간 미만은 경고만)
  - 계획 지문, 읽기 전용 `preview`
  - A 준비 `prepare`(한 연결·한 트랜잭션: 잠금 → 차단 → 재판정·지문 비교 → 기준선 → `prepared`)
  - DB 기반 `resume_status`(안내만)
- `account_recovery_runs` 표: 계정당 활성 1개. NULL 우회는 CHECK와 상태 기준 조회로 막고, 종료 이력은 보존한다.
- `release_block`의 무변경 해제가 같은 트랜잭션에서 `prepared` 기록을 닫는다. 그 밖의 상태면 해제를 거부한다.
- `scripts/prb_recover.py`: `preview` · `prepare` · `status`. 토큰은 숨김 입력만 받는다.
- 맞춘 목록: E-5b 소유 표·삭제 순서·FK, E-4 I1(기록 소유·표시·차단 연결), E-1 표 목록(자동), preflight·E-2 비교 표 목록, E-5b fixture(닫힌 기록 1행)


**검사:**

| 구분 | 결과 |
| --- | --- |
| P-RB 복구 ① SQLite | 22 통과 |
| P-RB 복구 ① 실제 PG | 22 통과 |

위 22개가 다루는 것:
- 정상·반복 재전환, 부분 롤백, 설명 불가·모호 이력
- 삭제 증명·원장 없음, snapshot 없는 카드, 식별 표시, 기간 4경계
- preview 무쓰기, A 성공·단계별 실패 4종 롤백, 계획 변경(기존 차단 보존)
- 같은 키 재개·다른 토큰·키·계획 충돌, 활성 기록 표시·중복 방지
- 해제 시 기록 닫기 원자성, 재개 판정, CLI 숨김 입력
- A↔평가·삭제·전환 양쪽 순서 6종. PG는 대기 상대도 증명했다.

| 구분 | 결과 |
| --- | --- |
| 변형 | SQLite 5/5, PG 5/5 검출: `aborted`만으로 롤백 인정, 과거 롤백에 현재 legacy 요구, 원장 없는 결측을 삭제로 인정, 여유 미달 거부, A 밖에서 차단 커밋 |
| 공개 롤백·재전환 관련 기존 SQLite | 187 통과(판정 분리 직후) |
| 실제 PG 관련 묶음 | 64 실행: 62 통과, 2 건너뜀(기존 트리거·뷰 미검증). 차단·E-5b·E-13·E-2b 업그레이드·E-3·E-4·E-5a·PG 기본 |
| 백엔드 전체(PG opt-in 해제) | 1210 실행: 1041 통과, 169 건너뜀 |

- 전환 먼저 → A 순서에서 A가 받는 결과는 둘 중 하나이고, 둘 다 거부·잔여 0이다.
  - 전환 실행이 아직 `started`인 사이에 끼면 `migration_run_in_progress`
  - 전환이 끝난 뒤면 `plan_changed`
  - PG에서 실제로 앞의 경우가 관측됐다.

**미검증:**
- B 복구, 모드 변경, verify, completed 해제(미구현)
- 구독 진도 행의 접근 상실·원장 없음 사례(코드상 차단 경로만 있고 합성 검사는 개인 카드 위주)
- 운영 DB, PG 18 외 버전
- 프론트·빌드(생략)

**정리:** 시작한 PG(PID 28740)만 빈 DB 확인 뒤 종료했다. 임시 폴더는 기존 19개 그대로다. 스테이징·커밋은 하지 않았다.

① 구현 검토 대기.

## 10. ① 검토 보정 세 건 (2026-10-20)

**3-5. 계획 지문 입력**(보정). 다음 값의 **행 전체**를 해시한다. 건수·버전 대신 행 전체를 쓰고, 원문은 출력하거나 기록에 복사하지 않는다.
- 이 계정의 apply·롤백 실행 행 전체(요약 포함)
- 계정 snapshot 행 전체
- 대상 카드 행 전체와 그 카드의 평가 로그 행 전체(개인·구독)
- 구독 카드의 접근 근거(구독 행, 공유 덱 단어 행)
- 설정 행, 식별 표시, 삭제 원장, 증거 재시작 행

여기에 판정 결과(대상·카드 판정·삭제 증명·과거 롤백 분류·기간 상태·사유)를 더한다. 현재 시각 자체는 넣지 않는다. 기간은 `open`/만료 상태만 넣는다. 그래서 같은 입력이면 지문이 같다.

**3-1 (1) 보강: 과거 롤백 증명.** `aborted` 실행의 연결 롤백이 아래를 모두 만족해야 "롤백 증명됨"이다. 하나라도 어긋나면 `prior_rollback_record_invalid`로 차단하고, 자료는 고치거나 지우지 않는다.
- 요약 항목은 정확히 `{kind, ref_id, result, preserved_reviews}` 형식이고, 카드가 중복되지 않는다.
- 요약의 카드 집합 = 롤백 기록의 카드 집합 = apply 기록의 카드 집합(누락·추가 없음).
- 롤백 기록마다 다음을 만족한다.
  - 롤백 형식(`_record_shape`, 카드 식별 일치)
  - 읽을 수 있는 baseline과 복원 투영(`_read_rollback_record`)
  - `card_version_before = apply 기록 버전 + 1 + preserved_reviews`
  - baseline 버전 = 그 값 + 1
- 현재 카드가 FSRS인지는 보지 않는다. 그래서 정상·반복 재전환은 그대로 인정된다.
- 주의(4차 정정):
  - **현재 정리 도구:** U10 정리 도구(`d2_snapshot_prune`)는 기간이 지난 apply 기록만 형식 3으로 축소하고, 롤백 기록과 그 복원 값은 유지한다. 과거 롤백 증명은 롤백 기록과 apply 기록의 버전 열만 읽으므로, 현재 도구의 실행 결과로는 증명이 막히지 않는다.
  - **가정상 손상 사례:** 롤백 기록의 복원 값이 어떤 이유로 없어졌다면 증명할 수 없고, 그 계정은 `prior_rollback_record_invalid`로 차단된다(보수적 판단). 정리 정책·도구는 바꾸지 않았다.

**2-3 보강: 재개 판정의 기록 검증.** 다음을 모두 만족하지 않으면 `report_only`(`recovery_record_invalid`)로 끝낸다. 예외를 내지 않고 쓰기도 0이다.
- `source_runs_json`이 비어 있지 않은 목록이다. 항목은 정확히 `{run_id, rollback_key}` 정수·문자열이다.
- run_id가 중복되지 않고, 이 계정의 apply 실행이다.
- 결정론적 롤백 키가 일치한다.
- 기준선을 읽을 수 있다.
- `prepared` 상태라면, 다시 판정한 대상 집합과 계획 지문이 저장값과 같다.

| 구분 | 결과 |
| --- | --- |
| 수정 전 새 검사(SQLite) | 3개 모두 실패. 하위 사례 기준 13 실패·2 오류: 로그 등급 변경 뒤 지문 동일, 과거 롤백 기록 손상 7종 통과, 재개 기록 손상 7종 통과·예외 |
| 수정 후 ① SQLite | 25 통과(기존 22 + 새 3) |
| 수정 후 ① 실제 PG | 25 통과 |
| 이번 변형 | SQLite·PG 각 3/3 검출: 지문 입력 제거, 과거 롤백 증명 생략, 재개 기록 검증 생략. 기존 ① 변형 5/5 유지(SQLite) |

**미검증:**
- 복원 값이 없어진 과거 롤백 기록(가정상 손상 사례; 현재 정리 도구는 만들지 않음)
- 구독 카드 접근 상실 합성 사례(이전과 같음)
- 전체 백엔드·프론트·빌드(지시대로 생략)

**변경 파일:** `app/recovery.py`, `tests/test_p_rb_recovery.py`, `tests/test_p_rb_recovery_real.py`, 이 문서, REPORT 25-1. 공개 함수는 바꾸지 않았다.

**정리:** 시작한 PG(PID 92340)만 빈 DB 확인 뒤 종료했다. 임시 폴더는 기존 19개 그대로다. 커밋은 하지 않았다.

① 보정 재검토 대기.

## 11. ① 재개 판정 보정 두 건 (2026-10-20)

**기준선 값 검증**(모든 활성 상태). 다음을 모두 만족해야 한다. 강제 변환은 없다(불리언은 정수가 아니고, 문자열은 숫자가 아니다).
- 키는 정확히 `{at, days, logs, preserved, metrics_digest, cards}`다.
- `at`: 읽을 수 있는 시각이고, 저장된 `prepared_at`과 같다.
- `days`: 비어 있지 않은 ISO 날짜 문자열 목록이다. 중복이 없고 오름차순이며, `at`의 서울 날짜를 포함한다.
- `logs`·`preserved`: `{count, digest}`. count는 0 이상의 정수다(0 허용). digest는 64자 소문자 hex다.
- `metrics_digest`: 64자 hex다.
- `cards`: `[종류, id, 버전]` 목록이다. 종류는 personal·lexeme, id는 양의 정수, 버전은 0 이상의 정수다. 중복이 없다.
  - 빈 목록은 허용한다(대상 카드가 모두 삭제 증명인 경우).
  - `preserved.count`와 개수가 같다.
  - 각 카드는 저장된 출처 실행의 snapshot 카드다.
  - `prepared`이면 다시 판정한 롤백 카드 목록과 정확히 같다.

**상태 조합표**(상태 문자열만으로 안내하지 않음):

| 상태 | 필요한 조합 | 안내 |
| --- | --- | --- |
| prepared | `changes_started = 0`; `applied_at`·`verified_at`·`verification_json`·`verified_digest` 모두 NULL; 출처 실행 모두 `completed`; 결정론적 롤백 실행 없음; 다시 판정한 지문·대상이 저장값과 같음 | `run_recovery` |
| applied | `changes_started = 1`; `applied_at` ≥ `prepared_at`; 검증 필드 모두 NULL; 출처 모두 `aborted`; 결정론적 롤백 실행 모두 `completed` | `verify` |
| verified | applied의 조건 + `verified_at` ≥ `applied_at` + `verification_json`이 비어 있지 않은 객체이고 모든 항목이 `status = pass` + `verified_digest` 64자 hex | `await_release` |
| 그 밖 | — | `report_only` |

- 지문 재판정은 `prepared`에서만 한다. 출처·기준선 검증은 모든 활성 상태에 적용한다.
- `verification_json`의 상세 형식은 ②에서 정한다. 지금은 "모든 항목 pass"가 아니면 거부한다.
- 손상·판정 불가는 예외 없이 `report_only`이고, 쓰기는 0이다(읽기 전용 스냅숏).

| 구분 | 결과 |
| --- | --- |
| 수정 전 새 검사(SQLite) | 2개 모두 실패. 하위 사례 기준 27: 기준선 값 손상 22종(Codex 사례 포함), 상태 조합 5종 |
| 수정 후 ① SQLite | 27 통과(기존 25 + 새 2) |
| 관련 SQLite | ①·차단·공개 롤백 재전환 87 통과 |
| 수정 후 ① 실제 PG | 27 통과 |
| 변형 | SQLite·PG 각 2/2 검출: 기준선 값 검사 제거, 상태 문자열만으로 판정. 이전 ① 보정 변형 3/3 유지(SQLite) |

**미검증:** 실제 `applied`·`verified` 상태의 정상 사례(② 미구현이라 손상 사례만 확인했다), 전체 백엔드·프론트·빌드(생략).

**변경 파일:** `app/recovery.py`, `tests/test_p_rb_recovery.py`, 이 문서, REPORT 25-2. 공개 함수와 정리 도구는 바꾸지 않았다.

**정리:** 시작한 PG(PID 92636)만 빈 DB 확인 뒤 종료했다. 임시 폴더는 기존 19개 그대로다. 커밋은 하지 않았다.

① 보정 재검토 대기.

## 12. ② 원자적 B·완료 증명 (2026-10-20, 구현 전 고정 → 구현)

**12-1. B `recover(user_id, recovery_key, token, plan)`.** 한 연결·한 트랜잭션에서 처리한다.

- 허가:
  - 계정 잠금 + `RecoveryGrant(user, key, "rollback", token)`
  - 차단이 일치해야 한다. 여기서 같은 트랜잭션에 `changes_started = 1`이 기록된다.
  - 기록은 활성 1개, 같은 키, 같은 차단 id, 토큰 해시 일치, `plan` = 저장 지문이어야 한다.
- 재확인:
  - 저장 출처 검증(11절)
  - 잠금 아래 `assess`: `ready`이고 지문 = 저장값, 대상 실행 = 저장 출처
  - 기준선 검증(`prepared` 판정 카드와 일치)
  - 실제 기간은 실행마다 `_require_window`로 다시 검사한다. 24시간 미만은 경고만 한다.
- 쓰기(출처 실행 id 역순, 실행마다):
  - 결정론적 키 `prb:<key>:<source_run_id>`의 롤백 실행이 없어야 한다. 있으면 `rollback_key_exists`다.
  - 롤백 실행 행을 만든다.
  - snapshot 카드마다 `judge_rollback_card`(잠금)를 거친다.
    - `rollback`: 공유 내부 함수 `write_card_rollback`으로 쓴다. 공개 `rollback_plan`도 이 함수를 쓴다.
    - `missing`이고 삭제 증명(3-2 4조건)이 B 안에서 다시 성립: 요약에 `{"kind","ref_id","result":"deleted_proven"}`만 남긴다. 카드는 복원하지 않는다.
    - 그 밖: `card_changed`로 거부한다.
  - 롤백 실행을 `completed`로 바꾸고 요약을 저장한다. 원래 실행은 `aborted`로 바꾼다.
- 마무리:
  - `rolled_back + deleted_proven = snapshot 카드 수`
  - FSRS 행 0
  - 모드 CAS: `srs_mode`와 `settings_version`이 판정 때 값과 같을 때만 legacy로 바꾸고 version을 1 올린다(정확히 1행).
  - 기록 `prepared → applied` + `applied_at`(정확히 1행)
- 결과:
  - 하나라도 실패하면 B 전체가 롤백된다. 카드, 실행, snapshot, 설정, `changes_started`가 모두 원래대로이고, A의 차단·`prepared`는 남는다.
  - 커밋 뒤 같은 키로 다시 부르면 상태(`applied`/`verified`)만 돌려준다. 롤백·모드 버전·실행 기록을 다시 만들지 않는다.
- 공개 `rollback_plan`:
  - 호출 방식, 혼합 결과, 자기 트랜잭션은 그대로다.
  - 카드 쓰기만 공유 함수로 옮겼다.
  - 범용 bypass나 HTTP 인자는 없다.

**12-2. `deleted_proven`의 기록 위치와 호환.**
- B가 만든 롤백 실행의 요약에만 들어간다. 롤백 snapshot 기록은 만들지 않는다.
- 과거 롤백 증명(3-1)은 이 항목을 받아들인다. 조건은 다음과 같다.
  - 개인 카드다.
  - 키가 정확히 `{kind, ref_id, result}`다.
  - 그 카드의 롤백 기록이 없다.
  - 원래 실행 기준으로 삭제 증명이 지금도 성립한다.
- 그래서 B 뒤의 계정을 다시 판정해도 "롤백 증명됨"이다.
- 공개 `rollback_plan`은 이 결과를 만들지 않는다. 그대로 `missing_or_access_lost`를 남기므로 부분 롤백으로 판정된다.
- 식별 검사(`identity._run_ids`)와 I3는 요약 항목의 `kind`·`ref_id`만 읽으므로 호환된다.

**12-3. verify `verify(user_id, recovery_key, token)`.**

1. **R(읽기 전용 스냅숏):**
   - 차단·기록·토큰을 확인한다.
   - 상태가 `applied`이고 조합표의 `verify` 조건을 만족해야 한다.
   - 출처와 기준선을 검증한다.
   - 필수 검사를 계산하고 지문 D를 계산한다.
2. 필수 검사가 하나라도 `pass`가 아니거나 빠졌으면 `not_verified`를 반환한다. 쓰기는 0이다.
3. **저장(새 연결·한 트랜잭션, 계정 잠금):**
   - 같은 기록이 아직 `applied`이고, D를 다시 계산해 R의 값과 같아야 한다. 다르면 `verification_stale`이고 쓰기는 0이다.
   - 같으면 `applied → verified`로 바꾸고 `verified_at`, `verification_json`, `verified_digest = D`를 저장한다.
4. 이미 `verified`면 쓰기 없이 돌려준다.

**필수 검사 목록과 저장 형식.** `verification_json`은 정확히 다음 9개 키를 가진 JSON 객체이고, 각 값은 `{"status": "pass"|"fail"|"unknown"|"not_evaluated", ...건수}`다. 전부 `pass`일 때만 `verified`다.

| 키 | 내용 |
| --- | --- |
| `I1`~`I5` | E-4 `audit()`의 해당 상태 그대로 |
| `I6_recovery` | 계정 로그 행 전체의 건수·해시가 기준선과 같음 |
| `I7_recovery` | 저장된 날짜별 지표(오늘 신규·상태·하한·달력·목표)가 기준선과 같음. 현재 시각이 아니라 저장된 날짜를 쓰므로 자정이 지나도 같다 |
| `completion_history` | 기준선 카드의 보존 열(`ROLLBACK_PRESERVED`) 해시가 같음 |
| `recovery_result` | FSRS 행 0, 모드 legacy, 출처 모두 `aborted`, 결정론적 키 롤백 실행 모두 `completed`이고 과거 롤백 증명(12-2 포함) 성립 |

- E-4의 I6·I7(삭제 리허설용 메모리 기준선)은 이 목록에 넣지 않는다. 복구용 비교가 그 자리를 대신한다.
- `not_evaluated`는 통과가 아니다.
- 재개 판정의 `verified` 조건(11절)도 이 9개 키를 정확히 요구한다.

**지문 D**는 10절 표의 필드 그대로다(`verification_digest`). `verified` 저장은 D에 들어가지 않는 필드만 바꾸므로 D가 그대로다. 카드·로그·실행·snapshot·설정·차단 진행 필드가 바뀌면 D가 달라진다.

**해제:** 무변경 해제(`precheck_unrecoverable`)만 기존 조건으로 남는다. B 뒤에는 `changes_started = 1`이라 거부된다. `completed`·`operator_abandoned`·자동 해제는 계속 거부한다.

**CLI:** `scripts/prb_recover.py`에 `recover`·`verify`를 더했다. 계정 id를 다시 입력하고 토큰은 숨김 입력으로만 받는다. 해제 명령은 없다.

**12-4. 검사 결과**

| 구분 | 결과 |
| --- | --- |
| 복구 ①+② SQLite | 43 통과(① 27 + ② 16) |
| 복구 ①+② 실제 PG | 43 통과. B와 다른 작업이 겹치는 5종은 대기 상대까지 증명 |
| 관련 SQLite | 103 통과(복구·차단·공개 롤백 재전환) |
| 실제 PG 관련 묶음 | 108 실행: 106 통과, 2 건너뜀(기존 트리거·뷰 미검증). 복구·차단·E-5b·E-13·E-2b·E-3·E-4·E-5a·PG 기본·E-2c 경합 |
| 백엔드 전체(PG opt-in 해제) | 1252 실행: 1062 통과, 190 건너뜀 |
| ② 변형 | SQLite·PG 각 4/4 검출: B 비원자(출처별 커밋), 허가 토큰 미확인, 필수 검사 일부만 요구, 저장 시 D 재확인 생략 |

② 검사 16개가 다루는 것:
- 두 출처·두 종류(개인·구독)의 B와 verify, 다른 계정 불변
- 재호출 무쓰기, 삭제 증명(복원 없음), 정상·반복 재전환 뒤 B
- A 뒤 변경(기간 만료·접근 상실·snapshot 없는 카드)과 토큰·지문 불일치의 거부·무쓰기
- B 4단계 실패 주입(두 번째 카드·집계 뒤·모드·기록)의 전체 롤백
- DB만으로 재개
- 검증 읽기와 저장 사이 변경, 필수 검사 누락·`not_evaluated`·`unknown`·로그 변조, 자정 경과
- B 선점 뒤 평가·삭제·공개 롤백·전환이 409, 같은 B 중복은 무쓰기
- CLI(숨김 입력)

**미검증:**
- 운영 DB와 실제 사용자 복구
- 여러 서버 프로세스가 동시에 쓰는 배치
- B↔E-2c 정리 도구의 실제 겹침(정리 도구도 계정 잠금을 쓰므로 직렬화될 것으로 보지만, 겹침 검사는 하지 않았다)
- 프론트·빌드(생략)

**변경 파일:**
- 제품: `app/srs/migration.py`(`write_card_rollback` 분리, 공개 동작 불변), `app/recovery.py`(B·verify·검사·D·조합표 갱신, `deleted_proven` 증명)
- 도구: `scripts/prb_recover.py`(recover·verify)
- 테스트: `tests/test_p_rb_recovery.py`, `tests/test_p_rb_recovery_real.py`, `tests/test_p_rb_account_blocks.py`(정적 경계 목록에 `recovery.py` 추가)
- 문서: 이 계약, REPORT 26

**정리:** 시작한 PG(PID 136300)만 빈 DB 확인 뒤 종료했다. 임시 폴더는 기존 19개 그대로다. 스테이징·커밋은 하지 않았다.

② 구현 검토 대기. 운영 복구 준비 완료나 completed 해제 승인이 아니다. completed 해제는 계속 닫혀 있다.

## 13. ② 재호출 의미 보정 (2026-10-21)

계약을 먼저 고친 뒤 구현했다.

**13-1. B 재호출.**
- 허가 확인과 진행 표시를 분리했다.
  - `authorize_recovery`: 계정 잠금 + 차단·토큰·동작 확인. 쓰기가 없다.
  - `record_recovery_change`: `changes_started` 기록
- 최초 B는 첫 복구 쓰기 직전에 같은 트랜잭션에서 진행 표시를 기록한다. B가 실패하면 함께 롤백된다.
- 이미 `applied`·`verified`인 같은 B를 다시 부르면 잠금과 허가는 확인하고, INSERT·UPDATE·DELETE는 하나도 실행하지 않는다.
- 공개 롤백과 기존 허가 경로(`begin_account_write(recovery=…)`)는 그대로다. 허가한 뒤 즉시 진행 표시를 남긴다.
- 범용 플래그는 없다. 두 함수는 `account_write`와 복구 도구만 쓴다(정적 검사로 고정).

**13-2. verify 재호출.** 저장된 `verified`를 근거로 검증을 생략하지 않는다. `applied`·`verified` 모두 현재 자료에서 필수 9개 검사와 D를 R에서 계산한다.

| 현재 자료 | 결과 | 쓰기 |
| --- | --- | --- |
| 9개 전부 pass이고, 상태 verified이고, D와 검사 결과가 저장값과 같음 | `verified`, `created: false` | 없음 |
| 9개 전부 pass이고, 상태 applied | 잠금 아래 D 재확인 뒤 `applied → verified` | 기록 1행 |
| 9개 전부 pass이고, 상태 verified이고, D가 다름 | 잠금 아래 D 재확인 뒤 **증명 갱신**(`verification_json`, `verified_digest`, `verified_at`). 저장 digest에 대한 비교 후 갱신 | 기록 1행 |
| 하나라도 누락·fail·unknown·not_evaluated | `not_verified`. 저장된 증명은 과거 기록일 뿐이다 | 없음 |
| R과 저장 사이 D 변경 | `verification_stale` | 없음 |

- 기준선은 덮어쓰지 않는다. 상태는 되돌리지 않는다. 차단은 해제하지 않는다.

**13-3. 재개 안내.** `verified` 기록이라도 현재 자료를 다시 본다.
- 9개 전부 pass이고 D가 저장값과 같을 때만 `await_release`
- pass지만 D가 다르면 `verify`(갱신 필요)
- 검사가 실패하면 `report_only`(`verification_not_current`)

**검사(쓰기 0은 값 비교가 아니라 SQL 실행 관측으로 판정):**
- SQLite: 앱 연결 클래스의 `execute`를 추적해 INSERT·UPDATE·DELETE가 0임을 확인했다.
- PG: 같은 추적에 더해, 차단·기록·설정 행의 `xmin`이 그대로인 것을 보조로 확인했다.
- 계정 잠금(`BEGIN IMMEDIATE`·`FOR UPDATE`)은 허용했다.

| 구분 | 결과 |
| --- | --- |
| 수정 전 새 검사(SQLite) | 4개 모두 실패 확인 |
| - B 재호출 | `account_write_blocks` UPDATE 1회 |
| - 자료 변경 뒤 | 재개 안내가 `await_release` |
| - 검사 누락 | `verified` 반환 |
| - 동시 실행 | 새 함수 부재 |
| 수정 후 복구 SQLite | 47 통과(43 + 새 4) |
| 관련 SQLite | 107 통과(복구·차단·공개 롤백 재전환) |
| 실제 PG 복구 + 차단 | 71 실행: 69 통과, 2 건너뜀(기존 트리거·뷰). 같은 B 동시 실행의 대기 상대 포함 |
| 변형 | SQLite·PG 각 2/2 검출: 조기 `verified` 반환 되살리기, 재호출 UPDATE 되살리기. 기존 ② 변형 4/4 유지(SQLite) |

새 검사 4개가 다루는 것:
- applied·verified 상태의 B 재호출과 토큰 불일치(쓰기 0)
- 정상 verify 재호출(쓰기 0)
- 자료 변경 뒤 재검증: 통과하면 갱신, 실패하면 무쓰기·재개 `report_only`
- 필수 검사 누락, 읽기와 저장 사이 변경
- 같은 B의 실제 동시 실행: 두 번째는 쓰기 0

**미검증:** 운영 DB, 여러 서버 프로세스, 전체 백엔드·프론트·빌드(지시대로 생략).

**변경 파일:** `app/account_write.py`, `app/recovery.py`, `tests/test_p_rb_recovery.py`, `tests/test_p_rb_recovery_real.py`, `tests/test_p_rb_account_blocks.py`(정적 경계), 이 문서, REPORT 26-1.

**정리:** 시작한 PG(PID 132276)만 빈 DB 확인 뒤 종료했다. 임시 폴더는 기존 19개 그대로다. 커밋은 하지 않았다.

② 보정 재검토 대기. completed 해제는 닫혀 있다.

## 14. completed 해제 (2026-10-21, 계약 고정 → 구현)

**14-1. 조건.** `release_block(user, key, token, "completed", plan=…)` 안에서만 처리한다(운영자 CLI `release`). 범용 bypass, HTTP 인자, `operator_abandoned`, 시간 기반 해제는 없다.

1. **R(읽기 전용 스냅숏)**
   - 차단·기록이 활성 1개씩이고 서로 연결돼 있어야 한다. 키, 토큰 해시, `plan` = 저장 지문이 모두 맞아야 한다.
   - 상태 `verified`이고 조합표의 `await_release` 조건을 만족해야 한다(출처·기준선·저장 검사 9개 pass·시각 순서).
   - **현재 자료**로 9개 검사가 전부 pass여야 한다(FSRS 0, legacy, 출처별 복구 결과 포함).
   - 현재 D = 저장 `verified_digest`여야 한다. D만 다르면 `verification_not_current`로 거부한다. 명시적 verify가 먼저다. 자동 갱신이나 자동 해제는 없다.
   - 그 밖의 불일치는 `release_not_allowed`, `recovery_plan_mismatch`, `recovery_grant_invalid`, `recovery_state_inconsistent`로 거부한다.
2. **잠금 트랜잭션**
   - 계정 잠금 → 차단·토큰 재확인
   - 같은 기록이 아직 `verified`이고 저장 digest = R의 D
   - 잠금 아래 D를 다시 계산해도 같고, FSRS 0, legacy
   - 그 다음 기록 `verified → closed`(completed)와 차단 `active → released`(completed)를 **한 트랜잭션**에서 처리한다. 각 UPDATE의 영향 행 수가 1이 아니면 둘 다 롤백한다.
3. **증명 없는 기존 completed 요청**(`plan` 없음)은 계속 `release_not_allowed`다.
4. **무변경 해제**(`precheck_unrecoverable`)는 조건이 그대로다.

**14-2. 재호출·충돌.**
- 같은 키·토큰·지문의 **완료 결과 재호출**은 쓰기 없이 `created: false`를 돌려준다.
  - 조건: 해제된 차단(`completed`)과 닫힌 기록(`completed`)
  - 해제 뒤에는 일반 쓰기로 자료가 바뀔 수 있으므로 현재 자료를 다시 검증하지 않는다.
- 다른 토큰은 `recovery_grant_invalid`, 다른 지문은 `recovery_plan_mismatch`, 다른 키는 `recovery_state_inconsistent`다.

**14-3. 검사 범위와 D 입력 범위.**
- D는 계정 범위다(10절 표). 9개 검사 중 I1~I5는 E-4 전역 감사(DB 전체)이고, 나머지는 계정 범위다.
- 해제 R은 읽기 전용 스냅숏에서 9개를 다시 계산하고, 잠금 트랜잭션은 계정 범위 D만 다시 확인한다.
- **남은 운영 조건:** R과 잠금 사이에 다른 계정의 쓰기가 전역 불변식(I1~I5)을 바꿀 수 있다.
  - SQLite는 잠금(`BEGIN IMMEDIATE`)이 DB 전체 쓰기를 막지만, R은 그보다 먼저다.
  - 이를 막으려면 전역 잠금이 필요하므로 이번에 구현하지 않았다.

**14-4. 정리 도구.** 영수증 최소화·만료 정리, snapshot 최소화, 만료 정리 모두 `begin_card_write`(차단 확인 포함)를 잡는다(코드 확인).
- 차단 중에는 세 도구 모두 `account_writes_blocked`로 거부되고 쓰기 0이다(SQL 추적).
- 실행 가능한 겹침은 영수증 만료 정리다. 양쪽 순서로 실제 겹쳐 실행했다.
  - 해제 먼저: 정리가 해제를 기다린 뒤 실행되어 만료 영수증을 지운다.
  - 정리 먼저: 잠금 뒤 차단으로 거부되고, 해제는 그 뒤 완료된다.
- snapshot 최소화·만료 정리는 차단 중 거부만 확인했다. 해제 뒤 실제 작업이 있는 겹침은 합성 자료에 해당 기록이 없어 확인하지 않았다.
- 정리를 통과시키려는 허가 우회는 추가하지 않았다.

**검사:**

| 구분 | 결과 |
| --- | --- |
| 복구 SQLite | 59 통과(47 + 해제·정리 12) |
| 실제 PG 복구 + 차단 | 83 실행: 81 통과, 2 건너뜀(기존 트리거·뷰). 해제 겹침 6종은 대기 상대까지 증명 |
| 실제 PG 관련 | E-5b·E-2c 도구·CLI·E-4 18 통과 |
| 백엔드 전체(PG opt-in 해제) | 1284 실행: 1078 통과, 206 건너뜀 |
| 변형 | SQLite·PG 각 4/4 검출: D 비교 제거, 9개 검사 생략, `verified` 상태 요구 제거, 잠금 아래 재확인 생략 |

해제·정리 검사 12개가 다루는 것:
- 정상 A→B→verify→해제→일반 쓰기 재개, 다른 계정 불변
- 재호출 무쓰기(SQL 추적, PG `xmin`)
- 거부 11종: verify 전, 오래된 D, 검사 누락, 손상 증명, FSRS 잔존, 모드 오류, 부분 결과, 지문 없음·불일치, 토큰·키 불일치
- 해제 실패 주입과 증명·잠금 사이 변경
- 해제 ↔ 일반 쓰기 / 허가된 롤백 / 영수증 정리의 양쪽 순서
- CLI 숨김 입력

- 해제 실패 주입 중 한 번은 테스트 정리에서 Windows 파일 잠금 때문에 임시 폴더가 남았다. 생성 시각으로 확인한 뒤 지웠다(기존 19개 그대로).

**미검증·남은 운영 조건:**
- 운영 DB, 실제 사용자 복구, 여러 서버 프로세스
- 14-3의 전역 검사 경합
- snapshot 정리 도구의 해제 뒤 실제 겹침
- 프론트·빌드(생략)

**변경 파일:** `app/account_blocks.py`, `app/recovery.py`, `scripts/prb_recover.py`, `tests/test_p_rb_recovery.py`, `tests/test_p_rb_recovery_real.py`, 이 문서, REPORT 27.

**정리:** 시작한 PG(PID 126756)만 빈 DB 확인 뒤 종료했다. 스테이징·커밋은 하지 않았다.

completed 해제 구현 검토 대기. Gate E 전체 완료나 운영 복구 준비 완료가 아니다.


## 15. completed 해제 검토 보정 (2026-10-21)

### 15-1. 잠금 아래 검증 기록 재확인 (구현)

- 문제: R 뒤 `verification_json.I6_recovery.status`를 fail로 바꿔도 해제됐다. 상태·검사·시각은 D에서 빠진 제어 필드라 D 비교에 걸리지 않았다.
- 보정: R이 읽은 제어 필드 `state, verification_json, verified_digest, prepared_at, applied_at, verified_at`를 증명에 함께 담는다. 잠금 아래에서 하나씩 같은지 비교하고, 저장된 9개 검사 전부 pass, 해석 가능, `prepared ≤ applied ≤ verified`, 지문 64자리 16진수를 다시 확인한다. 그 뒤 현재 D = 저장 지문을 확인한다.
- 하나라도 어긋나면 `release_not_allowed`로 거부하고 쓰기는 0이다. 자동 재검증·상태 수정·해제는 하지 않는다. 단일 트랜잭션과 rowcount 확인은 그대로다.
- 검사: `test_release_rechecks_the_stored_proof_under_the_lock`(검사 fail, 검사 누락, 손상, 다른 시각). 보정 전 4개 하위 검사 모두 실패, 보정 뒤 통과(SQLite·PG). SQL 추적 무쓰기, PG에서는 차단·설정 행 `xmin` 불변도 확인했다.

### 15-2. 같은 해제 동시 재호출 (구현)

- 문제: 같은 요청 둘이 모두 R을 지나면 두 번째가 잠금을 얻은 뒤 활성 차단이 없어 `recovery_grant_invalid`로 끝났다.
- 보정: 잠금을 얻은 같은 연결·트랜잭션에서 활성 차단이 없거나 키가 다르면, 먼저 이 키의 끝난 completed 해제를 찾는다(`recovery.finished_release`). 찾으면 토큰 해시, 닫힌 기록(`closed`/`completed`, 같은 차단), 계획 지문을 확인하고 완료 결과(`created: false`)를 무쓰기로 돌려준다. 해제 뒤 재검증은 하지 않는다. 토큰·기록·계획이 다르면 기존 거부 코드를 낸다.
- 검사: `test_the_same_release_twice_at_once`. 보정 전에는 두 번째가 `recovery_grant_invalid`. 보정 뒤에는 두 결과 `[True, False]`, 대기 스레드 쓰기 0(추적 대상임을 확인), 보유 스레드 쓰기 2, 스레드 종료와 실제 대기를 확인했다(SQLite 대기 탐침, PG `pg_locks` 대기).
- 변형: 잠금 아래 증명 재확인 제거, 잠금 아래 완료 결과 재확인 제거. SQLite·PG 각 2/2 검출. 14절 변형 4/4도 SQLite에서 다시 검출했다.

### 15-3. 전역 검사와 계정 지문의 범위 차이 (계약안, 승인 전 구현 없음)

재현(Codex): R 뒤 다른 계정에 손상 참조가 생기면 전역 I1이 fail이 된다. 그러나 대상 계정의 D는 그대로라 해제가 성공한다. 지금 해제는 저장된 I1~I5 pass를 근거로 삼지만, 그 입력 대부분은 D 밖에 있고 잠금 범위도 아니다. 이 문서는 같은 보장을 주장하지 않는다.

**현재 범위 표**

| 검사 | 입력 범위 | 잠금 범위 | D 포함 |
|---|---|---|---|
| I1 고아 기록, 차단·복구 기록 정합 | 모든 계정의 personal 기록, 카드, 삭제 장부, 차단, 복구 기록, users | 대상 users 행만 | 대상의 기록·카드·장부, 대상 차단·기록의 D 필드만 |
| I2 기록-카드 소유 일치, 구독 없는 lexeme 기록 | 모든 계정의 기록·카드·진행 | 대상만 | 대상 행만 |
| I3 sequence 앞섬 | 모든 계정의 personal 참조(카드, 기록, 영수증, 스냅숏, 장부, 표식, 재시작, meaning_feedback, 실행 범위) + 전역 sequence | 없음(sequence는 MVCC·잠금 밖) | 대상 참조만. sequence 값, meaning_feedback, 소유자 없는 실행 범위는 제외 |
| I4 재사용 식별 표식 | 모든 계정의 (계정, 카드) 쌍 | 대상만 | `scan_identity(user_id=U)`가 읽는 행은 전부 대상 행이라 D 안 |
| I5 기록 참조 | 모든 계정의 카드 경계, 영수증, 스냅숏, 재시작 → 기록 | 대상만 | 대상 행만 |

**권장 계약: 계정 필수 검사와 전역 진단을 나눈다.** 단순히 `WHERE user_id = U`만 붙이지 않는다. 대상 자료를 가리키는 다른 계정 행과 전역 sequence 의존을 따로 둔다.

1. 계정 필수(A): 대상 행만 입력으로 쓰는 판정. pass 조건을 대상 행으로만 쓸 수 있다. 예를 들어 대상 기록이 대상 카드나 대상 장부를 가리키면 pass다. 다른 계정 카드를 가리키면 그 계정 행과 무관하게 fail이다.
   - I1a: 대상 기록의 고아 여부, 대상 차단·복구 기록 정합
   - I2a: 대상 기록 소유, 대상 lexeme 기록의 대상 진행
   - I4a: 대상만 스캔
   - I5a: 대상 행의 기록 참조가 대상 기록인지
   - 입력이 전부 D 안이고 대상 잠금이 직렬화하므로, 잠금 아래 D 비교로 R의 결과가 유지됨을 보인다. 남는 한계는 휴리스틱 자체(I4의 거짓 음성)뿐이다.
2. 유입 참조(N): 다른 계정 행이 대상의 카드 id나 기록 id를 가리키는지 센다(기록, 영수증, 스냅숏, 장부, 표식, 재시작, meaning_feedback, 소유자 없는 실행 범위의 카드 목록). 0이어야 하고, R과 잠금 트랜잭션 안에서 두 번 읽는다.
   - 한계: 다른 계정 쓰기는 대상 잠금으로 막히지 않는다. 잠금 시점 관측일 뿐 해제 뒤 보장이 아니다.
   - 직렬화 대안: 참조한 계정의 users 행을 id 순으로 함께 잠근다. 새 참조를 만드는 계정은 미리 알 수 없어 완전하지 않다. 전역 잠금만 완전하다(아래 승인 항목, 권장하지 않음).
3. sequence(S): 잠금 트랜잭션 안에서 sequence가 max(대상 참조 ∪ N이 본 참조)보다 앞서는지 읽는다.
   - 한계: sequence는 잠글 수 없다. 앱 경로는 증가만 하므로 pass는 유지된다고 추론하지만, `setval`·재설정은 사이에 일어나도 보이지 않는다.
4. 전역 진단(G): 지금의 I1~I5를 그대로 실행해 `fail`/`unknown`을 그대로 저장·출력한다(계정 밖 위반 건수만). pass로 바꾸지 않는다. 해제를 막을지는 승인 항목 2다.

**검증 기록 형태:** 9개 검사 대신 `A(I1a, I2a, I4a, I5a, I6_recovery, I7_recovery, completion_history, rollback_proof)`, `N`, `S`, `G`로 나눈다. 판정 버전을 올리고, 옛 형태의 `verified` 기록은 해제하지 않는다. 명시적 verify를 다시 요구하고 자동으로 갱신하지 않는다.

**승인 항목**
1. 해제 관문을 A + N + S로 하고 셋 다 잠금 트랜잭션 안에서 다시 읽는다(권장).
2. 전역 진단 G의 fail이 해제를 막을지 정한다. 권장: 대상 밖 위반은 막지 않고 결과에 fail로 보인다. 대안: 지금처럼 막되 잠금 아래 다시 읽는다. 이 경우 Codex 재현은 막지만, 잠금 뒤 경합은 남고 무관한 계정 손상이 모든 해제를 막는다.
3. N과 S는 잠금 시점 관측이고 해제 뒤를 보장하지 않는다는 한계를 받아들인다. 전역 잠금은 구현하지 않는다(권장). 또는 참조 계정 추가 잠금이나 전역 잠금을 승인한다.
4. 검증 기록 형태와 판정 버전을 바꾸고, 옛 기록은 재검증을 요구한다.
5. 구현 범위: `invariant_audit`에 계정 범위 함수를 추가하고 전역 함수는 바꾸지 않는다. `recovery._checks`, `completed_release_proof/confirm`, 테스트를 고친다. 테스트: Codex 재현(다른 계정 손상 → G fail로 보이고 관문은 정책대로), R 뒤 유입 참조 생성 → 잠금 아래 거부, 대상 행 손상 → 거부, 변형.

해제 보정 재검토 + 검사 범위 계약 승인 대기.

### 15-4. 검사 범위 계약 보정 (2026-10-21, 승인 방향 반영 → 구현)

승인 방향: **A·N·전역 S는 해제 필수 관문, G는 진단.** 전역 잠금, 참조 계정 추가 잠금, 범용 bypass, 자동 보정은 없다. 운영 실행·실제 사용자 복구는 승인 범위 밖이다. 15-3의 "S는 대상 참조 ∪ N이 본 참조" 안은 아래로 **대체**한다. 전역 감사 `invariant_audit.audit`의 의미·결과는 바꾸지 않는다.

**식별 공간.** 비교는 공간 안에서만 한다. 숫자가 같아도 공간이 다르면 참조가 아니다.

| 공간 | 식별자 | 소유 |
|---|---|---|
| 개인 카드 | `vocab_items.id` (DB 전체에서 하나, sequence 발급) | 그 id를 가진 행·장부의 `user_id` |
| 개인 로그 | `review_logs.id` | 로그 행 `user_id` |
| 구독 로그 | `lexeme_review_logs.id` | 로그 행 `user_id` |
| 구독 카드 | `(user_id, lexeme_id)` 쌍. `lexeme_id` 단독은 식별자가 아니다 | 쌍의 `user_id` |
| 변환 실행 / snapshot / 차단 | 각 `id` | `scope_json.user_id` / `user_id` / `user_id` |

대상 U의 공간 T(U): U 행에 나타나는 개인 카드 id(U 카드, U 개인 로그의 카드, U 영수증·snapshot·장부·표식·재시작의 개인 `card_ref`, U 실행 scope·summary의 개인 `ref_id`), U의 개인·구독 로그 id, U 실행 id, U snapshot id, U 차단 id. **여러 계정이 같은 lexeme를 학습하는 것은 각자의 쌍이라 T에 들어오지 않는다(유입 아님).**

**A — 계정 필수(관문).** U 행만 읽는다(다른 계정 행을 읽지 않고 판정). 항목 8개: `I1a, I2a, I4a, I5a, I6_recovery, I7_recovery, completion_history, recovery_result`.
- I1a: U 개인 로그 → U 카드, 또는 카드가 없고 U 장부. 그 밖(다른 계정 카드 포함) fail. U snapshot의 실행이 U 실행. U 차단·복구 행(`user_id = U` 또는 `active_user_id = U`) 정합.
- I2a: U 개인 로그 카드가 U 소유(I1a와 같은 입력, 전역 I2처럼 따로 센다). U 구독 로그의 진행 없음은 전역 I2처럼 건수만.
- I4a: `scan_identity(user_id=U)` 발견 ⊆ U 표식. I5a: U 카드·영수증·snapshot·재시작의 로그 참조가 같은 종류·같은 카드의 U 로그이고, 재시작 source snapshot이 U의 같은 카드.
- 해석 불가는 unknown이고 pass가 아니다.

| A 입력 | D 포함 | 직렬화 |
|---|---|---|
| U의 카드·로그·영수증·snapshot·설정·장부·표식·재시작 행 | D 표 10개(`user_id = U`) | 대상 잠금 |
| U 실행(scope 소유자 U) | D의 실행 목록 | 대상 잠금(변환·롤백은 대상 잠금 아래) |
| 활성 차단·복구 기록의 D 필드 | D | 대상 잠금 |
| U의 닫힌 차단·기록 행 | D 밖 | set·release가 대상 잠금 아래에서만 바꾼다 |
| `_deletion_proven`의 "카드 행 없음"(전역 id 조회) | D 밖 | 같은 id의 다른 계정 행은 N이 잡는다 |

**N — 유입 참조(관문).** U가 아닌 행(소유자 NULL·해석 불가 포함)이 T(U)를 가리키는지 종류별 공간에서 센다. 대상: 다른 계정의 카드(id·`evidence_from_log_id`), 구독 진행(`evidence_from_log_id`), 개인 로그(카드), 영수증(개인 `card_ref`, 종류별 `review_log_id`), snapshot(`run_id`, 개인 `card_ref`, 본문 카드 id·`last_log_id`·`baseline.last_log_id`·`restart.previous_boundary`·`card.evidence_from_log_id`), 장부, 표식, 재시작(개인 `card_ref`, 경계, `source_snapshot_id`), `meaning_feedback.vocabulary_id`, U 아닌 실행(롤백 `source_run_id`, scope·summary 개인 `ref_id`), 다른 계정 복구 기록의 `block_id`.
- 다른 계정 소유이고 T 안: violation.
- 소유자(NULL·형식 오류)·종류·참조 값·JSON 본문을 읽을 수 없어 **T 밖임을 보일 수 없으면 unknown**이다. 0건이나 pass로 세지 않고 차단한다.
- T 밖임이 확인된 손상(다른 계정의 고아 로그, 없는 로그를 가리키는 다른 계정 카드 등)은 N과 무관하고 G에만 보인다.

**S — 전역 sequence(관문).** 대상 계정이 아니라 **모든 계정의 개인 카드 참조 최댓값 M**을 기준으로 한다. 조사 범위는 전역 I3와 같다: 카드, 개인 로그, 영수증, snapshot 열·본문, 장부, 표식, 재시작, `meaning_feedback`, 실행 scope·summary. 같은 조사 함수를 바꾸지 않고 관문으로 다시 부른다.
- SQLite: `sqlite_sequence.seq`(행 없으면 0) ≥ M. `AUTOINCREMENT`가 아니면 fail. PG: `is_called`이면 `last_value` ≥ M, 아니면(참조가 있을 때) `last_value` > M. 증가값이 1이 아니면 unknown.
- 최댓값 동률은 pass, 빈 DB는 pass. 참조 하나라도 해석 불가면 M을 알 수 없으므로 unknown(차단).

**G — 전역 진단.** 기존 I1~I5를 그대로 실행해 `status`·`violations`·`unknown`을 기록·출력한다. 관문이 아니다. 대상 관련 위반은 G로 넘기지 않고 A·N·S가 독립 판정한다: U 행의 위반 → A, 다른 계정 행이 T를 가리킴 → N, sequence → S. 그래서 대상과 무관함이 확인된 G 위반만 해제를 막지 않는다.

**관측의 한계.**
- N·S는 관측이다. R과 해제 잠금 트랜잭션 안에서 다시 읽지만 다른 계정의 쓰기는 대상 잠금으로 막히지 않는다. PG에서는 **마지막 검사와 해제 커밋 사이에도** 다른 계정이 유입 참조를 만들거나 참조를 키울 수 있다. SQLite는 `BEGIN IMMEDIATE`가 커밋까지 같은 DB 파일의 쓰기를 막는다.
- 해제 뒤 상태는 보장하지 않는다.
- 앱 쓰기 경로를 전제로 한다. 관리자의 직접 SQL, sequence 재설정(`setval`, `sqlite_sequence` 수정)을 막지 않으며, 검사 뒤에 일어나면 보이지 않는다.
- A의 남은 한계는 I4 휴리스틱의 거짓 음성이다.

**증명 버전 2.** `verification_json = {"version": 2, "A": {8개}, "N": {...}, "S": {...}, "G": {"I1".."I5"}}`.
- 형식 규칙은 한 함수로 verify·재개·해제가 같이 쓴다: 최상위 키 정확히 5개, `version`은 정수 2, A 키 정확히 8개, A 8개·N·S 모두 `pass`, G 키 I1~I5이고 각 `status`가 pass·fail·unknown 중 하나.
- 재개: `verified` + 버전 2 → `await_release`(현재 자료 재검사 포함). `verified` + 옛 9항목 형식 → `verify`. 그 밖 → `report_only`.
- verify: 옛 형식 `verified`에서도 실행된다. R에서 A·N·S·G와 D를 계산하고, 관문이 통과할 때만 잠금 아래에서 D 동일·N·S 재확인 뒤 저장된 `verified_digest`와 `verification_json`을 조건으로 갱신한다. 관문이 실패하면 `not_verified`, 쓰기 0, 기준선과 과거 증명을 그대로 둔다.
- 해제 R: 저장 증명이 버전 2가 아니면 `verification_not_current`(옛 형식 포함). 현재 A·N·S pass, D = 저장 지문. G는 결과의 `diagnostics`로 보인다.
- 해제 잠금: 제어 필드 동일, 버전 2 규칙, D, FSRS 0, legacy, **그리고 A·N·S 재계산 pass**. R의 결과만 믿지 않는다.
- 끝난 해제의 동일 요청 재호출(과거 완료 결과), 동시 재호출 무쓰기, 원자적 해제는 그대로다.

### 15-5. 15-4 구현 결과 (2026-10-21)

- 코드: `app/srs/recovery_scope.py`(신설: A·N·S·G), `app/recovery.py`(증명 버전 2, `gate_pass`·`proof_ok`·`legacy_proof`, verify 잠금 아래 관문 재확인과 `verification_json` 조건 갱신, 해제 R·잠금의 A·N·S 재계산), `app/account_blocks.py`(해제 결과에 `diagnostics`). `invariant_audit`는 바꾸지 않았다(S는 I3 함수를, G는 `audit`를 그대로 부른다).
- 수정 전: 새 검사 12개 중 SQLite에서 동작 실패 8(R 뒤 유입 4종이 해제됨, 옛 증명 해제, 무관한 손상으로 verify 거부, verify 잠금 재확인 없음 2), 새 항목 부재 오류 11.

| 구분 | 결과 |
|---|---|
| 복구 SQLite | 73 통과 |
| SQLite 관련(차단·E-4·삭제·E-3·D-2·CLI) | 194 실행: 191 통과, 3 건너뜀 |
| 실제 PG 복구+차단 | 97 실행: 95 통과, 2 건너뜀. 첫 실행 2건 오류는 PG의 `meaning_feedback` FK로 시험 자료 삽입이 실패한 것 → 장부 행으로 바꿔 재실행 통과 |
| 실제 PG 관련(E-4·E-2c CLI·E-5b·E-5c) | 64 통과 |
| 변형(실행 중 교체, 원본 무수정) | SQLite·PG 각 7/7 검출: 해제 잠금 A·N·S 생략, N 무시, N unknown→pass, G를 관문화, 옛 증명 해제, S 무시, verify 잠금 관문 생략 |
| 백엔드 전체(PG opt-in 해제) | 1312 실행: 1092 통과, 220 건너뜀 |

- 실제 겹침: 해제가 대상 잠금을 쥔 동안 다른 계정이 자기 잠금으로 유입 참조를 쓴다. SQLite는 쓰기가 해제를 기다리고 해제가 먼저 끝난다(해제 뒤 유입은 관측 밖). PG는 쓰기가 기다리지 않고 먼저 커밋되며, 해제의 잠금 아래 N 재확인이 거부한다(쓰기 0).
- 미검증: 운영 DB·실제 사용자·여러 서버 프로세스, PG에서 마지막 검사와 커밋 사이의 다른 계정 쓰기(설계상 관측 한계), 관리자 직접 SQL·sequence 재설정, snapshot 정리 도구의 해제 뒤 실제 겹침, 프론트·빌드(생략).
- 정리: 이번에 시작한 PG(PID 32756)만 소유 객체 0 확인 뒤 정지, 55432 리스너 없음. 임시 폴더는 기존 19개 그대로. 스테이징·커밋 없음.

검사 범위 구현 검토 대기. Gate E 전체 완료나 운영 복구 준비 완료가 아니다.

### 15-6. 검사 범위 누락 두 건 보정 (2026-10-21)

정책·관측 한계는 15-4 그대로다.

1. **I2a 진도 행 누락.** 대상 구독 로그의 `(U, lexeme)` 진도 행이 없으면 건수(`subscribed_logs_without_progress`)만이 아니라 **위반**으로 센다(앱에는 진도 행을 지우는 경로가 없다). 전역 I2의 의미는 바꾸지 않았다. 로그·진도 행을 복구·삭제·합성하지 않는다.
2. **snapshot `restart.rollback_record_id`.** apply 기록(형식 1·2·3)에만 허용되는 `restart`의 이 값은 로그 id가 아니라 **snapshot id**다. 0은 허용된 빈 값, `restart` 생략도 허용된다. rollback 기록에는 `restart`가 없다.
   - A(I5a): 대상 apply 기록의 값은 같은 카드의 대상 rollback 기록이어야 한다. 다른 계정 snapshot·다른 카드·apply 기록을 가리키면 fail, 정수가 아니면 unknown.
   - N: 다른 계정 snapshot의 값이 대상 snapshot id면 violation, 읽을 수 없으면 unknown. `previous_boundary`(로그 공간)와 재시작 `source_snapshot_id` 검사는 그대로다.

- 수정 전: 새 재현 검사 4개에서 실패 7(진도 누락이 I2a pass·재개 `verify`, 다른 계정→대상 연결이 R 전·후 모두 해제 통과, 손상 값이 N pass, 대상→다른 계정·apply 연결이 A pass).
- 수정 뒤: 복구 SQLite 77 통과, 차단 SQLite 35 통과, 실제 PG 복구 77 통과(건너뜀 0). 새 변형 3/3(진도 건수만, N 생략, A 생략) SQLite·PG 각 검출, 기존 변형 7/7 SQLite 재검출. 거부 때 차단 유지·기록 `verified` 유지·차단·기록 쓰기 0(SQL 추적).
- 미검증: 운영·실제 사용자, 형식 3 기록에서의 이 필드(형식 판정은 공용이라 따로 만들지 않음), 프론트·빌드·백엔드 전체(지시대로 생략).
- 정리: 시작한 PG(PID 4688)만 소유 객체 0 확인 뒤 정지. 커밋 없음. 검사 범위 보정 재검토 대기.

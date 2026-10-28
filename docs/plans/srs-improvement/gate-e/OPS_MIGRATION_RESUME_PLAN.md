# 명시 전환 CLI 미완료 실행 재개(`resume`) 계약 계획·합성 구현 기록 (2026-10-27 작성, 2026-10-28 RS3 합성 마감)

**현재 상태(2026-10-28)**: RS2·RS2b·RS3 합성 검증 마감(11~15절). RS4 실제 로컬 PG 검증도 "PostgreSQL 18.6에서 개인 카드의 명시적 `resume` 경로" 범위로 마감했다(1차 0/25·2차 25/25·보완 3/3을 따로 집계, [RS4 기록](OPS_MIGRATION_RESUME_REAL_PG_PLAN.md) 14절, [증거 목록](OPS_MIGRATION_RESUME_REAL_PG_EVIDENCE.md)). 구독 카드 재개·실제 장애·운영 활성화는 범위 밖이다.

이전 상태: RS2(제품 P2)·RS2b(근거 결속 기반)·RS3(CLI `resume`)의 **합성 검증을 마감**했다(11~15절). 실제 PostgreSQL 검증(RS4)은 계획만 있고 승인 전이다([RS4 계획](OPS_MIGRATION_RESUME_REAL_PG_PLAN.md)). 운영 활성화는 범위 밖이다.

작성 당시 상태: 계획만 있다. 코드·권한·지문·기대값을 바꾸지 않았고, 검사·DB 접속·PG 시작·키 생성·GRANT/REVOKE도 하지 않았다. 아래에서 **[코드 확인]**은 정적 읽기로 확인한 현재 코드 사실, **[기존 계약]**은 `OPS_MIGRATION_CLI_PLAN.md`에 이미 있는 규칙(제안 상태 포함, 새로 승인된 것으로 기록하지 않음), **[제안]**은 이 문서의 새 정책안, **[미검증]**은 확인하지 못한 것이다. 이 문서의 어떤 제안도 승인된 것이 아니다.

범위: `apply`가 이미 실행 행을 만든 작업(`started` 또는 `failed`, 커서 < 카드 수)의 남은 카드 처리. **범위 밖**: `completed` 재호출, 자동 상태 보정, 새 작업 키로의 우회 전환, `rollback_plan`, 운영 활성화.

## 0. 기존 계약에서 그대로 쓰는 것 (다시 정의하지 않음)

| 주제 | 위치(`OPS_MIGRATION_CLI_PLAN.md`) | 요지 |
| --- | --- | --- |
| 실행 상태 판정 | 4-1, 4-2, 4-3 | `incomplete`·`failed_at_cursor`만 재개 대상. `completed`·`cursor_end_not_completed`·`closed`·`conflict`·`inconsistent`·창 밖은 재개하지 않음. `status`의 `not_started`는 실행 부재의 증거가 아님 |
| 재개 때 새 dry-run 비교를 하지 않는 이유 | 4-2 표 아래 | 이미 커밋된 카드는 값이 바뀌었으므로 최초 계획과의 단순 비교는 항상 다름 |
| 재개 승인·이전 승인 사슬 | 5-1~5-4, 계약 4-6-2~4-6-6 | 재개마다 새 적용 승인(`based_on` = 최초 조회 승인), 사슬 서명 검증, 지금 승인만 권한을 줌 |
| 백업 확인 | 8, 4-4-7 D10·C10 | 재개 시 새 백업을 요구하지 않고 최초 확인 백업의 존재·유효성 확인. 운영 방식 미결 |
| 쓰기 전 거부/시작 후 실패, 종료 코드 | 9-1~9-4 | 실행 시작 뒤 실패는 1, 쓰기 전 거부는 4, 확인 못 한 커서·미커밋 추정 금지 |
| 판정 시각 | 4-4-8 판정 시각 | 연결 요청마다 그 순간의 시계로 승인·서명·만료 재판정 |
| 최초 적용의 원자적 확인(P1) | 4-4-2, 4-4-2-1 | `new_run_only=True`는 최초 `apply` 전용 |

## 1. 코드 확인 사실

- **[코드 확인] 제품 재개 경로** (`app/srs/migration.py`): `apply_plan(..., new_run_only=False)`의 첫 연결은 `begin_card_write`(계정 잠금) 뒤 `_run_id`를 부른다(777행대). `_run_id`는 `run_key`로 행을 찾아, 있으면 `_scope_matches`(저장 범위 = 지금 계획의 `_plan_json`, 정리된 범위면 `request_sha256`)·`mode`·`config_version`이 같을 때 그 실행 id를 돌려주고(다르면 `migration_run_conflict`, `aborted`면 `migration_run_closed`), **없으면 새로 `INSERT`한다**. 범위 JSON에는 `user_id`가 들어 있으므로 범위 일치가 소유 확인을 겸한다.
- **[코드 확인] 커서와 창**: 첫 연결에서 `summary_json`의 커서를 읽고, 커서 < 카드 수면 `_require_window(started_at, at, "resume")`로 30일 창을 확인한다(`ROLLBACK_WINDOW = 30일`, `rollback_window`는 `open`·`expired`·`unverifiable`). 이때 현재 시각 `at`은 `app.database.now_utc()`(= `datetime.now(timezone.utc)`, `app/database.py:1584`)가 얻는 **앱 프로세스 시각**이며 DB 서버 시각이 아니다. 카드 연결의 창 재확인도 같은 함수다. 커서 ≥ 카드 수면 **상태와 관계없이 저장 결과를 돌려주고 쓰지 않는다**(`completed`와 `started`·커서 끝을 구분하지 않음).
- **[코드 확인] 카드별 처리**: 카드마다 새 연결에서 계정 잠금 뒤 실행 행의 `status != aborted`와 저장 커서 = 이 카드 순번을 확인하고(아니면 `migration_cursor_conflict`), 창을 다시 확인하며, snapshot이 있으면 `already_applied`, 없으면 `inspect_card(..., for_update=True)` 재판정 결과가 계획 후보와 같을 때만 쓰고 다르면 `conflict`로 남긴다. 커서는 카드마다 커밋된다.
- **[코드 확인] 실패 표시**: 카드 처리 중 예외(창 오류 제외)면 실패 표시 연결에서 커서 = 그 순번이고 `started`일 때만 `failed`로 바꾼다. 창 오류는 상태를 바꾸지 않는다.
- **[코드 확인] CLI** (`backend/scripts/srs_migrate.py`): `run_apply`는 이전 승인 사슬이 비어 있고(`prior_chain` 없음) 승인의 `supersedes`가 `null`이어야 하며, 적용 직전 새 dry-run이 계획과 같아야 하고, 제품에 `new_run_only=True`를 넘긴다. 따라서 **지금 CLI로는 재개할 수 없다**(부분 처리 결과는 `resume: not_implemented`). `run_status`·`judge_status`는 소유·범위·일관성 판정을 읽기 트랜잭션에서 한다(잠금 없음).
- **[코드 확인] 승인 사슬** (`_ops_approval.check_apply_chain`, `_ops_preflight.PreflightInput.prior_chain`): 제시된 사슬(첫 적용 승인부터 직전까지, 각자의 `based_on` 조회 승인 포함)의 서명·연쇄·같은 작업을 검증하고 직전 승인을 `prior`로 돌려준다. 과거 승인의 유효 기간은 요구하지 않는다(근거로만 씀). **제시된 사슬이 정합함만 보이며, 그것이 최신 사슬임은 증명하지 않는다**(더 나중 승인을 숨길 수 있음). 권한은 지금 승인 1건만 준다.

## 2. 기존 API로 보장할 수 없는 조건 (계약에 드러냄)

1. **"실행 행이 이미 있고 재개 가능한 상태"를 잠금 아래 보장할 방법이 없다.** `new_run_only=False`로 부르면 행이 없을 때 새 실행을 만든다(재개 명령이 최초 적용이 되어 버림). 행이 `completed`이거나 `started`·커서 끝이어도 쓰지 않고 저장 결과를 돌려줄 뿐, 재개 명령이 그것을 구분해 거부하지 않는다. CLI의 사전 `status` 읽기는 잠금 밖이므로 그 사이 바뀔 수 있다.
2. 따라서 최소 제품 변경이 필요하다 → 6절 **P2**.
3. **P2의 존재·상태·커서 확인만으로는 부족하다**(2026-10-27 검토 보완). 사전 조회(단계 9) 뒤 다른 경로가 `summary_json`(결과 목록)을 손상시키거나 이 실행의 snapshot을 더하거나 지우면, 상태가 `started`·커서 < 카드 수라는 조건은 그대로 통과한다. 처리된 구간(커서 앞)의 일관성은 잠금 아래에서 다시 결속해야 한다 → 4-1절.
4. **새 승인과의 대조만으로는 "최초 계획 파일"임을 보장하지 못한다.** 새 적용 승인의 `plan`은 제시된 계획 파일로 계산되므로, 다른 계획 파일로 새 승인을 받으면 그 파일과도 일치한다. 최초 적용 승인과의 결속이 따로 필요하다 → 3-1절.
5. **이미 서명된 과거 승인에는 근거 해시를 사후에 넣을 수 없다.** 현재 적용 승인 형식(`_ops_approval.FIELDS["apply"]`: 공통 필드 + `based_on`·`plan`)에는 백업 근거를 결속하는 필드가 없다 → 7절.

## 3. 재개 명령과 입력 [제안]

- 명령: `apply`와 다른 명시적 명령 `resume`(같은 도구 `srs_migrate`, `TOOLS`에 `resume: write` 추가는 구현 단위의 승인 항목). `apply`는 계속 최초 적용 전용(`new_run_only=True`)이다. 실행 행이 있는데 `apply`를 부르면 지금처럼 `migration_run_exists`로 거부되며, 자동으로 재개로 바꾸지 않는다.
- 입력(모두 필수, 기본값 없음): 계정·작업 키·카드(요청), **최초 계획 파일**(`--plan`, 최초 `apply`에 쓴 바로 그 파일), 배치 크기, 새 적용 승인과 서명, 최초 조회 승인과 서명(`based_on`), 이전 적용 승인 사슬(첫 적용 승인부터 직전까지, 각자의 `based_on` 포함, 바이트·서명만), 백업 근거 문서와 서명. 호출자가 넣은 "검증 완료" 표시나 로컬 실행 기록은 받지 않는다.
- 최초 계획 파일 결속: 파일을 한 번 읽은 바이트로 고정하고, 그 `artifact_sha256`·제품 지문·`db_identity`·계정·작업 키·카드 목록(순서 포함)·`config_version`이 요청·새 적용 승인의 `plan`(작업 계획 지문)·관측 DB 식별·현재 엔진 설정과 모두 같아야 한다(최초 `apply`와 같은 규칙, `OPS_MIGRATION_CLI_PLAN.md` 2-2·4-4-1). 계획 파일을 다시 만들거나 덮어쓰지 않는다.
- 승인: 새 적용 승인의 `supersedes`는 직전 적용 승인(형식 버전 2의 id·바이트 해시)이고, `based_on`은 **최초 조회 승인**이다(5-3). 사슬은 사전 검사가 서명·연쇄를 검증한다. 적용 단계는 `apply`와 같이 읽기(`dry_run` 대신 재개용 읽기 단계 이름은 구현에서 고정)·쓰기 두 단계로 둔다. 쓰기 단계 `args`는 배치 크기.
- 사슬의 한계: 제시된 사슬의 정합성만 확인하며 최신 사슬임은 증명하지 못한다. 이 한계는 지금 승인 외의 권한을 주지 않는다는 점에서만 받아들이고, 실행 기록 위치가 정해지면 대조 보조로 쓴다(5-2 금지 사항 그대로).

### 3-1. 최초 계획 파일과 최초 적용 승인의 결속 [제안, 2026-10-27 검토 보완]

- 식별: 사전 검사가 서명 검증한 이전 승인 사슬의 **첫 항목**이 최초 적용 승인 A₀이고, 그 `based_on` 조회 승인 I₀이다(`check_apply_chain`은 첫 항목의 `supersedes`가 비어 있음과 연쇄를 확인한다). A₀·I₀가 없거나(빈 사슬), 서명 검증이 안 되거나, A₀의 `based_on`이 I₀가 아니면 재개하지 않는다(4, `resume_initial_approval_missing`·`_invalid`).
- 재계산: 제시된 계획 파일의 고정 바이트에서 `artifact_sha256`·제품 지문을 계산하고, **A₀에 서명된 필드**(`db_identity`, `manifest` 지문, `tool`, 계정, `job.key`, `job.inputs`)와 함께 `job_plan_fingerprint`로 다시 계산해 A₀의 `plan[계정]`과 같아야 한다. 다르면 `resume_plan_not_initial`(4). A₀의 `manifest` 값은 서명된 문자열(지문)로만 쓰며, 과거 manifest 바이트를 현재 실행물 검증에 대신 쓰지 않는다.
- 현재 승인 판정은 별도로 그대로: 새 적용 승인 Aₙ의 `plan`은 **현재** manifest·현재 관측 DB 식별·같은 계획 파일로 계산한 값과 같아야 하고(기존 사전 검사), 권한은 Aₙ만 준다. A₀의 단계·역할·계정 권한을 합치지 않는다.
- 같은 대상: A₀와 Aₙ의 `db_identity`·`tool`·`job.key`·`job.inputs`·계정은 같아야 한다(다르면 4). DB 식별이 바뀐 경우는 5-3대로 거부·보고.
- 거부 사례(검사표에 포함): 제품 지문은 같지만 `artifact_sha256`만 다른 파일(직렬화 바이트 차이), 후보의 `reconversion`·`restart_json`만 다른 파일(제품 지문 `_plan_json`에는 두 필드가 없으나 계획 파일 후보 필드 `CANDIDATE_FIELDS`에는 있어 `artifact_sha256`이 달라짐) → 둘 다 `resume_plan_not_initial`.
- 필요한 코드: 사전 검사 결과의 검증된 사슬(`_Verified.prior` 계열)에서 A₀·I₀를 꺼내는 공급자 내부 접근, `job_plan_fingerprint` 재사용. 새 지문 형식은 만들지 않는다.

## 4. 재개 흐름 [제안]

| 단계 | 내용 | 실패 |
| --- | --- | --- |
| 1 입력 | 요청·배치 크기·두 단계 입력·`args` 형식(4-4-8 검토 보정 규칙) | 4 |
| 2 고정 읽기 | 최초 계획 파일·백업 근거·서명 | 4 |
| 3 계획·요청 대조 | 2절 결속 | 4 `plan_file_*` |
| 4 사전 검사 | 시계 기준 판정 시각, 새 적용 승인·`based_on`·이전 사슬 서명·연쇄, `supersedes` = 사슬 마지막 | 4 `preflight_*` |
| 5 승인 형태 | `tool = srs_migrate`, `kind = apply`, 재개 단계 존재, `supersedes` 있음 | 4 `approval_*` |
| 6 계획 대상 | 계획 `db_identity` = 관측 DB 식별 | 4 `plan_file_target_mismatch` |
| 6-1 최초 결속 | 사슬 첫 항목 A₀·I₀ 식별과 A₀ `plan` 재계산 대조(3-1절) | 4 `resume_initial_approval_*`·`resume_plan_not_initial` |
| 7 백업 근거 | 7-1절: 최초 근거 기록 검증·재개 근거 검증·필드 대조 | 4 `backup_*`·`resume_backup_*` |
| 8 app import | 위 통과 뒤 | 1 |
| 9 상태 사전 확인(예비) | 읽기 연결로 4-3 `status` 판정. `incomplete`·`failed_at_cursor`만 계속하고 4-1절 고정 값을 만든다. 다른 판정은 쓰기 없이 종료(아래 표) | 판정별 |
| 10 근거 재확인 | 첫 쓰기 연결 직전 근거 `recheck` | 4 |
| 11 적용 | `apply_plan(최초 계획 후보, run_key, approved=True, batch_size=n, new_run_only=False, existing_run_only=True, expected_progress=고정 값)` 1회(P2) | 결과 표 |

- 새 dry-run 비교 없음: 4-2의 이유대로 최초 계획과 새 dry-run을 비교하지 않는다. 처리된 카드(커서 앞)는 단계 9의 일관성 검사(실행 결과·snapshot 대조)로, 남은 카드(커서 뒤)는 제품의 카드별 잠금 아래 재판정(`conflict`)으로 판단한다.
- 단계 9는 **예비** 확인이다. 그 결과는 4-1절의 방식으로 잠금 아래에서 다시 결속한다. 잠금 밖이므로 실제 보장은 P2의 잠금 아래 확인이다. 9와 11 사이에 상태가 바뀌면 11이 고정 코드로 거부하고, 그 거부는 첫 연결 안의 `SrsWriteError`이므로 쓰기 전 거부(4)다.

| 단계 9 판정 | 재개 명령 결과 | 종료 |
| --- | --- | --- |
| `not_started` | `resume_target_not_found`. 실행 부재의 증거가 아니므로 `apply`로 바꾸지 않음 | 4 |
| `completed` | `migration_run_completed`. 완료 재호출은 범위 밖 | 4 |
| `cursor_end_not_completed` | 보고만(기존 D7-A) | 6 |
| `closed` | `migration_run_closed` | 4 |
| `conflict`(범위·종류·설정 다름) | `migration_run_conflict` | 6 |
| `inconsistent`(손상: 요약 해석 불가, 커서·결과·snapshot 불일치 등) | 보고만 | 6 |
| 소유 불명(범위 해석 불가·다른 계정) | `status`에서 `not_started`와 같게 보이므로 첫 행과 같이 `resume_target_not_found` | 4 |
| 창 `expired`·`unverifiable` | `migration_resume_window_closed`·`_unverifiable` | 4 |
| DB 식별 변경·최초 조회 승인 서명 키 폐기 | 단계 4·6에서 거부, 자동 재개·새 작업 전환 없음(5-3, D9-B 전까지) | 4 |

### 4-1. 처리된 구간의 잠금 아래 일관성 [제안, 2026-10-27 검토 보완]

두 안을 비교한다.

| 안 | 내용 | 장점 | 대가 |
| --- | --- | --- | --- |
| (A) 잠금 아래 재판정 | 제품의 첫 연결이 계정 잠금 뒤 4-3 일관성 검사 전체(요약 해석, 커서·결과 순서, snapshot 대응)를 다시 수행 | 사전 조회와 무관하게 잠금 시점 상태로 판정 | 판정 로직(`srs_migrate.judge_status`, CLI 모듈)을 제품이 import할 수 없어 제품 안에 같은 규칙을 다시 만들어야 함(별도 판정 엔진, 이중 관리) |
| (B) 사전 조회 결과 고정·잠금 아래 대조 | CLI가 읽기 트랜잭션에서 기존 `judge_status`로 판정한 바로 그 행·snapshot의 요약값을 고정해 제품에 넘기고, 제품은 첫 연결의 잠금 아래에서 같은 값인지 **비교만** 함 | 기존 판정 로직 재사용, 제품은 바이트 비교만, 스키마 변경 없음 | 사전 조회 뒤 정상적인 커서 전진(다른 재개 호출)도 불일치로 거부됨(보수적) |

- **권장: (B)**.
- 고정하는 값(사전 조회, 기존 `read_status`의 한 읽기 트랜잭션): 실행 행의 `id`, `status`, `mode`, `config_version`, `started_at` 원문, `finished_at` 원문, `scope_json`의 SHA-256, `summary_json` 원문의 SHA-256(없으면 고정 표식), 이 실행 snapshot의 정렬된 `(id, user_id, card_kind, card_ref)` 목록의 SHA-256. 지금 `read_status`의 snapshot 조회는 `user_id, card_kind, card_ref`만 읽으므로 `id`를 더 읽도록 바꾼다(읽기 SQL 열 추가, 스키마 변경 없음).
- 제품 대조 위치: `apply_plan(..., existing_run_only=True, expected_progress=...)`의 **첫 연결 안**, `begin_card_write`(계정 잠금)와 `_run_id`의 행 조회 직후, 창 확인·커서 사용·어떤 쓰기보다 먼저, 같은 트랜잭션에서 같은 값을 다시 읽어 비교한다. 하나라도 다르면 `SrsWriteError("migration_run_changed")`로 첫 연결을 롤백한다(쓰기 전 거부 4). 같으면 그 트랜잭션에서 읽은 커서로 기존 카드 처리를 이어 간다.
- 경계: 대조는 첫 연결 트랜잭션에서만 한다. 그 뒤 카드 연결은 각자 잠금 아래 기존 커서 확인(`stored_cursor == index`)으로 보호된다. 첫 연결이 커밋된 뒤 카드 연결 전에 다른 경로가 요약을 바꾸면 카드 연결의 커서 확인·snapshot 확인이 그것을 잡는다(잡지 못하는 손상 형태는 [미검증]).
- 거부 조건: 사전 조회 판정이 `incomplete`·`failed_at_cursor`가 아니면 제품 호출 없음(4절 표). 고정 값과 잠금 아래 값이 다르면 `migration_run_changed`(4). 정상적인 커서 전진도 여기서 거부되며, 사용자는 `status`로 다시 확인한 뒤 새 호출을 한다(자동 재시도 없음).

## 5. 시각과 기간 [기존 계약 + 제안]

- 판정 시각: 연결·재연결 요청마다 그 순간의 시계로 새 적용 승인·서명·권한을 재판정한다(4-4-8 규칙 그대로).
- 기간 구분: (1) **30일 창**은 최초 실행 행의 `started_at` 기준이며 제품이 첫 연결·카드마다 앱 프로세스 시각(`now_utc()`)으로 확인한다(DB 서버 시각 아님). (2) **새 적용 승인의 유효 기간**(최대 24시간)은 CLI·공급자가 연결 요청마다 확인한다. (3) **백업 근거의 `valid_until`**은 최초 검사와 첫 쓰기 직전에 확인한다. 셋은 서로 대신하지 않는다. 승인이 유효해도 창이 닫혔으면 거부, 창이 열려도 승인이 만료되면 거부.

## 6. 필요한 코드 변경 지점

| 항목 | 위치 | 근거 | 승인 단위 |
| --- | --- | --- | --- |
| **P2** `apply_plan(..., existing_run_only=False, expected_progress=None)`와 `_run_id`의 같은 인자 [제안] | `app/srs/migration.py` | 2절 1·3: 재개는 "행이 있고 이 요청의 범위·종류·설정과 같으며 `started`·`failed`이고 커서 < 카드 수"를 **계정 잠금 아래 같은 트랜잭션에서** 확인하고, 4-1절 고정 값을 같은 트랜잭션에서 대조해야 한다. 행이 없으면 `INSERT` 전에 `SrsWriteError("migration_run_missing")`, `completed`이거나 커서 ≥ 카드 수면 `migration_run_not_resumable`, 고정 값 불일치면 `migration_run_changed`. `existing_run_only=True`에는 `expected_progress`가 필수이며 형식이 틀리면 연결 전 거부, `new_run_only`와 동시 참도 연결 전 `invalid_run_mode`. 기본값이면 기존 동작 그대로 | 제품 변경(별도 승인) |
| `run_resume` | `backend/scripts/srs_migrate.py` | 4절 흐름. `run_apply`의 공통 단계는 재사용하되 사슬 허용·`supersedes` 필수·새 dry-run 비교 생략·단계 9 추가·3-1절 최초 승인 결속·4-1절 고정 값·P2 인자 | CLI 합성 구현 |
| `read_status` snapshot 조회에 `id` 열 추가 | `srs_migrate.py` | 4-1절 snapshot 지문 | 같은 단위 |
| 사슬 첫 항목 접근 | `_ops_provider`·`_ops_preflight`(검증된 사슬 반환 경로) | 3-1절. 공통 모듈 변경이므로 이유와 최소 범위를 먼저 보고 | 공통 모듈(별도 승인) |
| `TOOLS`의 `srs_migrate.resume: write` | `_ops_approval.py` | 재개 단계 | 같은 단위 |
| 실행 시작 판정(`_Tracked`) | `srs_migrate.py` | 재개는 실행 행이 이미 있으므로 "첫 연결 커밋 = 실행 시작"이 아니다. 첫 연결 안의 고정 거부(P2)는 쓰기 전 4, 그 뒤 카드 연결이 열린 뒤의 실패는 1 | 같은 단위 |

- 같은 키의 동시 `resume`(시점별, P2·4-1절 적용 가정의 [제안], 실제 PG [미검증]). 모든 경우 자동 재시도 없음:

| 시점 | 결과 | 근거 | 종료 |
| --- | --- | --- | --- |
| 두 호출이 같은 시작 커서를 사전 조회했고, B가 A의 첫 연결 커밋 전에 계정 잠금을 기다림 | A 진행. B는 잠금을 얻은 뒤 4-1절 대조에서 A가 바꾼 상태(아직 바뀌지 않았다면 카드 단계)를 만남: 고정 값이 이미 다르면 `migration_run_changed`(첫 연결, 쓰기 전 4). 같다면 B도 첫 연결을 통과한 뒤 같은 카드 처리를 경쟁하고, 카드 연결의 잠금 아래 커서 확인에서 늦은 쪽이 `migration_cursor_conflict` | [코드 확인] 카드별 `stored_cursor == index`; 4-1절 | A 0/3/5, B 4(첫 연결) 또는 1(`after_start`, `uncertain`, `status_required`) |
| 앞 호출 A의 카드 커밋 뒤 B가 전진한 커서를 사전 조회 | B의 고정 값은 그 시점 값. 그 뒤 A가 더 전진하면 B 첫 연결에서 `migration_run_changed`(4). A가 멈춰 있으면 B가 이어서 처리 | 4-1절 | B 4 또는 0/3/5 |
| A가 완료한 뒤 B가 잠금을 얻음 | 사전 조회가 A 완료 전이었다면 B 첫 연결에서 `migration_run_changed` 또는 P2 `migration_run_not_resumable`(4). 사전 조회가 A 완료 뒤라면 단계 9 `completed` → 4(제품 호출 없음) | P2, 4절 표 | B 4 |

## 7. 재개 시 백업 근거 [기존 계약 D4-A·D10 + 제안, 2026-10-27 검토 보완]

- [기존 계약] 재개는 새 백업을 요구하지 않고 최초 확인 백업이 아직 존재하고 유효한지 확인한다. 운영 방식은 미결.
- [코드 확인] 현재 적용 승인 형식에는 백업 근거를 결속하는 필드가 없고, 최초 `apply`는 근거 문서 해시(`evidence_sha256`)를 출력만 한다. **이미 서명된 과거 승인에는 근거 해시를 사후에 넣을 수 없다**(승인 바이트가 바뀌면 서명·`based_on` 해시가 깨짐). C10 `verify_backup_evidence`는 언제나 지금 시각의 유효성(`now < valid_until`)을 요구한다.

### 7-1. 결속 경로 [제안]
1. **결속 필드(최초 `apply`부터)**: 적용 승인에 선택 필드 `backup_evidence`(`{"sha256": <근거 원문 SHA-256>}`)를 둔다. 최초 `apply`의 CLI는 이 필드가 있으면 제시된 근거 원문의 SHA-256이 그 값과 같아야 진행한다. 서명된 A₀의 이 필드가 최초 근거를 결속하는 유일한 근거다.
2. **재개 입력**: `resume`은 (a) 최초 근거 원문·서명(A₀가 결속한 것)과 (b) 새 재개 근거 원문·서명을 따로 받는다.
3. **최초 근거 검증**: (a)의 원문 SHA-256 = A₀의 `backup_evidence.sha256`, `backup` 주체 서명 검증, 형식·대상(`db_identity`·계정·작업 키 = A₀), `taken_at` ≥ I₀의 `valid_from`. 과거 문서이므로 **지금 시각의 유효성은 요구하지 않는** 기록 검증 함수(C10 모듈에 별도 함수, 시각 검사만 다름)를 쓴다. 지금 시각으로 속여 기존 함수를 통과시키지 않는다.
4. **재개 근거 검증**: (b)는 기존 C10 검증(지금 시각 유효성 포함, 첫 쓰기 직전 `recheck`)을 그대로 받는다.
5. **필드 대조**(원문 검증 뒤, 해시와 `backup_id`를 직접 비교하지 않음): (a)와 (b)의 `backup_id`·`db_identity`·`account_id`·`job_key`·`method`·`artifact_sha256`(진술된 산출물 해시)·`taken_at`이 같아야 한다. `evidence_id`는 달라야 하고, (b)의 `valid_until`은 지금 이후다. 하나라도 다르면 `resume_backup_evidence_mismatch`(4).
6. 의미: 이것은 "서명자가 같은 백업이 아직 유효하다고 다시 진술했다"는 **진술 검증**이다. 산출물 존재·해시 일치·복원 가능성은 확인하지 않으며 `restore_verified`·`backup_artifact_checked`는 false다. 실제 산출물 확인은 운영 백업 방식 결정 뒤의 별도 단위다.

### 7-2. 변경 영향
- 승인 형식: 적용 승인에 선택 필드 하나를 더하는 것은 `_ops_approval.FIELDS["apply"]`(정확히 이 키만 허용) 변경이며, 형식 버전을 올릴지(기존 v2 문서는 필드 없음 그대로 유효)는 결정 R3에서 정한다. 기존 v2 승인은 필드가 없으므로 그대로 해석되지만 **재개 대상이 될 수 없다**(아래 7-3).
- CLI: 최초 `apply`(`run_apply`)에 근거 해시 대조 단계 추가, `resume`에 두 근거 입력.
- C10 모듈: 기록 검증 함수(시각 검사 제외판) 추가.

### 7-3. 결속 없이 시작된 기존 미완료 실행 [제안]
- `backup_evidence` 필드가 없는 A₀로 시작된 실행(현재까지의 모든 실행: 합성 시험뿐, 운영 실행 없음)은 **재개하지 않는다**: `resume_backup_binding_missing`(4).
- 그 실행의 처리 선택지는 (a) 기존 `rollback_plan`(별도 승인 경로)으로 되돌림, (b) 그대로 두고 보고만, 둘뿐이다. 새 작업 키로 남은 카드를 우회 전환하지 않는다.
- 로컬 실행 기록, 호출자의 진술, 과거 근거를 새로 서명한 문서만으로는 "그 근거가 최초 적용에 쓰였다"는 사실을 증명할 수 없으므로 받지 않는다.

## 8. 출력과 종료 코드

- 9-2·9-3을 그대로 쓴다. 재개 특유: 부분 처리(정상 반환, 커서 < 카드 수) 3, 남은 카드 모두 처리하고 마무리 성공 0(결과에 `conflict`·`blocked`가 있으면 5), 카드 연결이 열린 뒤 승인 만료·권한 변경·창 만료·중간 실패·마무리 실패·커밋 미확정은 1(`after_start`, `confirmed: unknown` 또는 확인 범위, `uncertain: true`, `next: status_required`). 확인하지 못한 커서·미커밋·변경 없음을 추정하지 않는다.
- 4절 단계 9 판정표의 종료 코드를 따른다.

## 9. 결정 필요 (승인 아님)

| 결정 | 선택지 | 권장안 | 대가 |
| --- | --- | --- | --- |
| R1 재개 원자 확인 | (A) 제품 `existing_run_only`(P2) / (B) CLI 사전 `status`만 / (C) 별도 예약 표 | A | A는 제품 변경(기본값이면 동작 동일). B는 경합에서 새 실행 생성·완료 재호출로 흐름. C는 스키마 변경 |
| R2 재개 명령 형태 | (A) 별도 `resume` 명령 / (B) `apply --resume` | A | A는 `TOOLS` 항목 추가. B는 최초 적용과 경계가 흐려짐 |
| R3 백업 근거 결속 | (A) 적용 승인 선택 필드 `backup_evidence`(최초 `apply`부터) + 최초 근거 기록 검증 + 필드 대조(7-1) / (B) 실행 기록 위치 결정 뒤 대조 / (C) 운영 방식 결정 전까지 재개 차단 | A(합성), 운영은 C | A는 승인 형식·최초 `apply` CLI·C10 모듈 변경, 기존 실행은 재개 불가. B는 기록 위치 결정 선행. C는 재개 불가 기간 |
| R4 단계 9 예비 확인 | (A) 둠 / (B) 생략하고 P2만 | A(4-1절 (B)와 함께 필수) | A는 연결 1회 추가 |
| R5 처리된 구간 일관성 | (A) 잠금 아래 재판정 / (B) 사전 조회 고정값 잠금 아래 대조(4-1) | B | B는 정상 커서 전진도 거부(보수적). A는 제품 안 판정 규칙 중복 |
| R6 최초 계획 결속 | (A) 사슬 첫 항목 A₀의 `plan` 재계산 대조(3-1) / (B) 현재 승인 대조만 | A | A는 검증된 사슬 접근(공통 모듈) 필요. B는 다른 계획 파일로 받은 새 승인을 막지 못함 |

## 9-1. 결정 기록 (2026-10-27 사용자)

- **R1 확정**: 제품 P2(`existing_run_only`).
- **R5 확정**: 사전 조회 고정값을 첫 연결의 잠금 아래 대조(4-1절 (B)).
- R2·R3·R4·R6은 승인 전 그대로.
- 후속 결정 메모(승인 아님): RS2b의 `backup_evidence` 필드는 **승인 형식 버전 3 도입**을 권장안으로 둔다(버전 2 문서는 그대로 해석되며 이 필드를 가질 수 없음). 재개 적용 승인의 `based_on`은 I₀로 유지하는 현재 규칙에서는 공통 사전 검사가 적용 승인과 근거 조회 승인의 `manifest` 일치를 요구하므로(계약 4-6-2), **현재 배포 manifest도 I₀의 manifest와 같아야 한다.** 배포가 바뀐 뒤의 재개는 별도 절차가 마련될 때까지 거부한다.

## 9-2. RS2 입력 계약 (2026-10-27 고정, 사용자 승인 범위: RS2 제품 변경·합성 SQLite 회귀)

`apply_plan(plan, run_key, *, approved=False, batch_size=100, connect=None, new_run_only=False, existing_run_only=False, expected_progress=None)`

- `existing_run_only`: `type(x) is bool`만. 아니면 연결 전 `SrsWriteError("invalid_existing_run_only", 400)`.
- 조합: `new_run_only`와 `existing_run_only`가 둘 다 참이면 연결 전 `invalid_run_mode`(400). `existing_run_only`가 거짓인데 `expected_progress`가 `None`이 아니면 `invalid_run_mode`. `existing_run_only`가 참인데 `expected_progress`가 `None`이면 `invalid_expected_progress`(400).
- `expected_progress`: `type(x) is dict`이고 키가 정확히 아래 9개. 값의 형식이 하나라도 다르면 연결 전 `invalid_expected_progress`(400). 변환·정상화·누락 추정 없음.

| 키 | 형식 | 의미(같은 읽기 트랜잭션의 사전 조회 값) |
| --- | --- | --- |
| `run_id` | `type is int`, 1 이상(불리언 아님) | 실행 행 `id` |
| `status` | `"started"` 또는 `"failed"` | 실행 행 `status` |
| `mode` | `"apply"` | 실행 행 `mode` |
| `config_version` | 문자열 1~128자 | 실행 행 `config_version` |
| `started_at` | 문자열 1~64자 | 실행 행 `started_at` 원문 그대로 |
| `finished_at` | `None` 또는 문자열 1~64자 | 실행 행 `finished_at` 원문(SQL NULL은 `None`) |
| `scope_sha256` | 소문자 16진수 64자 | `scope_json` 원문의 UTF-8 바이트 SHA-256 |
| `summary_sha256` | `None` 또는 소문자 16진수 64자 | `summary_json` 원문의 UTF-8 바이트 SHA-256, SQL NULL이면 `None` |
| `snapshots_sha256` | 소문자 16진수 64자 | 이 실행(`run_id`)의 snapshot 행 `(id, user_id, card_kind, card_ref)`를 `id` 오름차순으로 나열한 JSON 배열 `[[id, user_id, "kind", card_ref], ...]`을 `json.dumps(..., separators=(",", ":"), ensure_ascii=True)`로 직렬화한 UTF-8 바이트의 SHA-256(행이 없으면 `"[]"`의 해시) |

- 잠금 아래 순서(첫 연결, `begin_card_write` 뒤 같은 트랜잭션, 창 판정·커서 사용·업무 쓰기보다 먼저): ① `run_key` 행 없음 → `migration_run_missing`(INSERT 없음) ② 범위(`_scope_matches`, 계정 포함)·`mode`·설정 불일치 → `migration_run_conflict`(세부 없음) ③ `aborted` → `migration_run_closed` ④ `status`가 `started`·`failed`가 아님 → `migration_run_not_resumable` ⑤ 9개 고정값 중 하나라도 다름 → `migration_run_changed` ⑥ 요약의 커서가 정수(불리언 아님)이고 0 이상 카드 수 미만이 아니면 → `migration_run_not_resumable` ⑦ 기존 창 판정 → 기존 카드 처리.
- 보장 범위: 대조는 첫 연결 트랜잭션에서만 한다. 그 뒤 카드 연결은 기존 카드별 커서 확인으로 보호되며, 첫 연결 이후의 모든 손상을 탐지한다고 보장하지 않는다. 카드별 커밋·실패 표시·마무리의 기존 책임은 그대로다.
- 두 인자를 생략하면 기존 동작(재개·완료 재호출), `new_run_only=True`는 최초 적용(P1) 동작 그대로.
- 계산 도우미는 판정 없이 해시만 만든다. CLI(`read_status`)의 같은 값 계산과 연결은 RS3.

## 9-3. RS2b 세부 계약 (2026-10-28 고정, 사용자 승인: R3 합성 결속안·R6 최초 승인 재계산안 확정, RS2b 합성 구현)

결정 기록: **R3**(적용 승인 선택 필드로 최초 근거 결속, 합성) · **R6**(사슬 첫 항목 A₀의 `plan` 재계산 대조) 확정. **R2·R4, RS3(CLI `resume`), 실제 PG는 승인 전.** 운영 재개는 범위 밖.

- **승인 형식 v3** (`_ops_approval`):
  - `FORMAT_VERSIONS = (1, 2, 3)`. v3는 v2의 모든 규칙(`supersedes` 형식 포함)을 그대로 따르고, **적용 승인에만** 선택 필드 `backup_evidence`를 더 허용한다.
  - 필드가 있으면 값은 정확히 `{"sha256": <소문자 16진수 64자>}`. `null`·다른 타입·추가/누락 키·형식 오류는 `approval_backup_evidence_invalid`.
  - v1·v2 문서에 이 필드가 있으면 기존과 같이 `approval_fields_invalid`(조용히 받거나 변환하지 않음). 조회 승인은 어느 버전이든 이 필드를 허용하지 않는다(`approval_fields_invalid`).
  - 필드는 승인 원문 바이트에 있으므로 서명에 결속된다. 해석 결과 `Approval.backup_evidence_sha256`(없으면 `None`). `job.inputs`·제품 지문·작업 계획 지문 알고리즘·서명 이름공간·`Approval.sha256`(원문 해시)은 바꾸지 않는다.
- **최초 apply 대조 위치** (`srs_migrate.run_apply`): 단계 5(실제 사전 검사가 검증한 승인 형태 확인) 바로 뒤, 단계 6(계획 대상)·7(C10 검증)·8(app import)보다 먼저. 검증된 적용 승인의 `backup_evidence_sha256`이 있으면 단계 2에서 한 번 읽어 고정한 근거 원문의 SHA-256과 같아야 하며, 다르면 `backup_evidence_binding_mismatch`(종료 4, app import·제품 조회·DB 연결 0). 같아도 C10 검증(서명·대상·시각)은 그대로 수행한다. 필드가 없으면 기존 동작이며, 그 실행은 근거가 결속된 실행으로 취급하지 않는다(7-3).
- **과거 근거 기록 검증** (`_ops_backup_evidence.verify_backup_evidence_record`): 원문 형식·`backup` 주체 서명(현재 신뢰·폐기 목록, 서명 검증 시각은 지금)·합성 용도·대상·계정·작업 키·복원 주장 거부·문서 내부 시각 순서(`taken_at < valid_until`, `taken_at ≥ 기준 시각`, `taken_at ≤ 지금`)를 검사하고, **`지금 < valid_until`만 요구하지 않는다.** 결과는 현재 근거와 다른 형(`BackupEvidenceRecord`)이며 `recheck`나 최초 apply 근거로 쓸 수 없다. 기존 `verify_backup_evidence`·`recheck`의 현재 유효성 검사는 바꾸지 않는다. 기록 검증 성공은 현재 쓰기 허가나 산출물 존재·복원 가능성의 증거가 아니며 `restore_verified`·`artifact_checked`는 false다.
- **검증된 A₀·I₀ 접근** (`_ops_preflight.initial_apply_approvals(result, inputs)`): 사전 검사가 이전 사슬을 서명·연쇄 검증할 때 첫 쌍을 내부 결과 `_Verified`에 함께 담고(출력·`repr` 비노출), 접근 함수는 (1) 결과의 내부 객체가 `_Verified`이고 (2) 첫 쌍이 모두 `verified`이며 (3) 그 원문 해시가 지금 입력 `prior_chain[0]`의 승인·조회 승인 바이트 해시와 같고 (4) A₀의 `based_on`이 I₀를 가리킬 때만 `(A₀, I₀)`를 돌려준다. 입력 `prior_chain`은 첫 항목에 접근하기 전에 사전 검사와 같은 규칙(`_chain_links`)으로 검사한다(2026-10-28 검토 보정): tuple이 아니거나(목록·dict·정수·불리언·`None` 포함) 항목이 `ChainLink`가 아니거나 네 필드가 bytes가 아니면 `approval_chain_invalid`, 항목 수 초과는 `approval_chain_too_long`, 바이트 합계 초과는 `approval_chain_too_large`. 형식이 맞는 빈 tuple은 `approval_chain_first_missing`, 그 밖 불일치는 `preflight_result_mismatch`. 변환·넓은 예외 처리 없음. 호출자가 넣은 "검증 완료" 표시·승인 객체는 입력으로 받지 않는다. 권한은 여전히 지금 승인 1건만 주며(과거 승인 권한 비합산), 공급자의 연결 후 재판정·재연결 재검증은 그대로다. 사슬 정합성은 최신 사슬 증명이 아니다. A₀ `plan` 대조(3-1)와 `run_resume`·`TOOLS.resume`은 RS3.

## 9-4. RS3 CLI `resume` 계약 (2026-10-28 고정, 사용자 승인: R2 별도 `resume` 명령·R4 쓰기 전 상태 예비 확인 확정, RS3 합성 구현)

결정 기록: **R2·R4·RS3** 확정. 실제 PG·운영 실행은 승인 전·범위 밖.

- 명령·단계: `srs_migrate resume`. `TOOLS["srs_migrate"]`에 `resume: write` 추가. 현재 적용 승인 Aₙ은 `tool = srs_migrate`, `kind = apply`, **형식 v3**, `supersedes` 있음, 이전 적용 승인 사슬(첫 항목 A₀부터) 필수, `based_on`은 I₀(A₀의 근거 조회 승인)와 같아야 함. 단계는 읽기 `status`(read)와 쓰기 `resume`(write) 두 개이며 연결마다 그 단계로 판정한다. `resume` 단계 `args`는 정확히 `{"batch_size": str(n)}`, `status` 단계는 `{}`. 기존 `dry-run`·`status` 명령의 조회 승인 경계와 최초 `apply`의 `new_run_only` 경계는 그대로다.
- 입력: 요청(계정·작업 키·카드), 배치 크기, 두 단계 사전 검사 입력(공유 필드 동일, `prior_chain` 비어 있지 않음, `artifact_sha256`·제품 지문 필수), 최초 계획 파일, 최초 근거 원문·서명, 새 재개 근거 원문·서명(각각 한 번 읽어 고정), 프로필 범위, 드라이버, 시계. 명령줄 `resume`은 `--batch-size --plan --initial-evidence --initial-evidence-signature --backup-evidence --backup-signature`가 필수이며 실제 연결 경로가 없어 `connection_not_available`(4)로 끝난다.
- 검사 순서(앞 단계 실패 시 뒤는 하지 않음, 거부는 `phase: before_first_write`, `changes: none` — 이번 호출이 쓰지 않았다는 뜻일 뿐, 기존 부분 커밋과 무관):

| 단계 | 내용 | 실패 |
| --- | --- | --- |
| 1 입력 | 배치·형식·두 단계 명령(`resume`/`status`)·`args`·공유 필드·요청·사슬 필수 | 4 `request_mismatch`·`resume_chain_required` 등 |
| 2 고정 읽기 | 계획 파일, 최초 근거·서명, 새 근거·서명 | 4 |
| 3 계획·요청 | 계정·작업 키·카드·`artifact_sha256`·제품 지문 = 요청·입력 | 4 `plan_file_request_mismatch` |
| 4 사전 검사 | 앱 환경 고정 뒤 두 입력 실제 사전 검사(Aₙ·I₀·전체 사슬 서명·연쇄, 현재 manifest = Aₙ = I₀, 대상, 단계, `args`, 현재 작업 계획 지문), 시계 기준 | 4 `preflight_*` |
| 5 승인 형태 | Aₙ v3·`apply`·`supersedes` 있음, 두 결과가 같은 승인 바이트, 쓰기 `resume`·읽기 `status` | 4 `approval_*` |
| 6 A₀·I₀ | `initial_apply_approvals`, Aₙ `based_on` = I₀, A₀와 Aₙ의 DB 식별·도구·작업 키·작업 입력·계정 같음 | 4 `preflight_*`·`resume_basis_not_initial_inquiry`·`resume_initial_approval_mismatch` |
| 7 계획 대상·최초 결속(순수 파일) | 계획 `db_identity` = 관측 DB 식별, A₀ 서명 필드 + 계획 파일 `artifact_sha256`·제품 지문으로 작업 계획 지문 재계산 = A₀ `plan` | 4 `plan_file_target_mismatch`·`resume_plan_not_initial` |
| 8 근거 | A₀ `backup_evidence` 없음 `resume_backup_binding_missing`, 최초 근거 해시 ≠ A₀ `resume_initial_evidence_mismatch`, 최초 근거 기록 검증, Aₙ에 필드가 있으면 새 근거 해시 대조 `backup_evidence_binding_mismatch`, 새 근거 현재 C10 검증, 두 근거의 `backup_id`·대상·계정·작업 키·방법·산출물 해시·`taken_at` 같고 `evidence_id` 다름 | 4 `backup_*`·`resume_*` |
| 9 app import | 위 통과 뒤 | 1 |
| 10 제품 계산 대조 | 설정 = 현재 엔진, `to_candidates`(제품 규칙으로 후보 복원·제품 지문 재계산 = 파일) | 4 `plan_file_*` |
| 11 상태 예비 확인 | `status` 단계 공급자 읽기 연결, 기존 `read_status`(snapshot `id` 포함)·`judge_status`, 같은 트랜잭션의 행·snapshot으로 RS2 고정값 9개 계산, 창은 `rollback_window(started_at, now_utc())` | 아래 표 |
| 12 근거 재확인 | 첫 쓰기 연결 직전 새 근거 `recheck` | 4 |
| 13 적용 | `apply_plan(최초 계획 후보, run_key, approved=True, batch_size=n, new_run_only=False, existing_run_only=True, expected_progress=고정값)` 정확히 1회 | 아래 |

| 단계 11 판정 | 결과 | 종료 |
| --- | --- | --- |
| 실행 없음·소유 불명(`not_started`와 같은 응답) | `resume_target_not_found`(최초 apply·새 키로 바꾸지 않음) | 4 |
| `incomplete`·`failed_at_cursor`, 창 `open` | 계속 | - |
| 창 `expired`·`unverifiable` | `migration_resume_window_closed`·`_unverifiable` | 4 |
| `completed` | `migration_run_completed` | 4 |
| `closed` | `migration_run_closed` | 4 |
| `cursor_end_not_completed` | 보고만(`status: report`) | 6 |
| `conflict`·`inconsistent` | 보고만, 사유 포함 | 6 |

- 결과: 첫 제품 연결 안 P2 거부(`migration_run_*`)는 쓰기 전 4. P2를 통과한 뒤 후속 연결 거부·카드 실패·마무리 실패·커밋 미확정은 1·`after_start`·`confirmed: unknown`·`uncertain: true`·`next: status_required`. 첫 연결 커밋만으로 카드 커밋을 추정하지 않는다. 정상 반환이고 남은 카드가 있으면 3(`phase: partial`, `next: status`), 끝까지 처리하면 0(결과에 `conflict`·`blocked`가 있으면 5). 자동 재호출·재시도·상태 보정 없음. 출력에는 고정 필드만(계획·근거 해시, `restore_verified: false`, `backup_artifact_checked: false`).
- 시각: 읽기·쓰기의 모든 연결 요청마다 시계의 새 시각으로 공급자 검사(4-4-8). 30일 창(앱 프로세스 시각), 현재 승인 기간, 새 근거 기간은 각각 판정.

## 10. 승인 단위와 검사 계획 (모두 승인 전)

| 단위 | 범위 | 선행 조건 |
| --- | --- | --- |
| **RS1** 계약 검토 | 이 문서와 결정 R1~R6 | - |
| **RS2** 제품 P2 + 합성 SQLite 회귀 | `apply_plan`의 `existing_run_only`·`expected_progress`(4-1), `_run_id` 같은 인자. 기존 재개(`new_run_only=False`)·최초 적용(P1)·완료 재호출 회귀 | RS1(R1·R5) |
| **RS2b** 근거 결속 기반 | 적용 승인 선택 필드 `backup_evidence`, 최초 `apply` CLI의 근거 해시 대조, C10 기록 검증 함수, 사슬 첫 항목 접근(공통 모듈) | RS1(R3·R6). 공통 모듈 변경은 이유·최소 범위를 먼저 보고 |
| **RS3** CLI `resume` 합성 구현 + 집중 회귀 | 4절 흐름, 3-1·4-1·7-1 연결, `TOOLS`, 판정·출력 | RS2·RS2b |
| **RS4** 실제 로컬 PG 검증·R2 | 별도 계획·승인([`OPS_MIGRATION_RESUME_REAL_PG_PLAN.md`](OPS_MIGRATION_RESUME_REAL_PG_PLAN.md), 2026-10-28 마감: 개인 카드 resume 경로) | RS3 |

- 다음 최소 구현 단위는 **RS2**(제품만, 근거 결속과 무관하게 독립 검증 가능).

검사 계획(기대값은 계약에서 정하며 관측에서 역으로 만들지 않음):

- 기존 커밋 보존: 부분 처리(배치 1) 뒤 재개 → 앞 카드 snapshot·값 그대로, 남은 카드만 처리, 결과 `already_applied`/`applied` 구분, 최종 `completed`.
- 남은 카드 재판정: 재개 전 남은 카드를 바꾸면 그 카드만 `conflict`, 다른 카드 처리.
- 다른 계정·범위 밖 자료 불변.
- 잠금 아래 일관성(4-1): 사전 조회 뒤 `summary_json` 손상 → `migration_run_changed` 4, 이 실행 snapshot 추가·삭제 → 4, 정상적인 커서 전진(다른 재개 커밋) → 4(보수적 거부), 값이 같으면 통과.
- 최초 계획 결속(3-1): 빈 사슬·A₀ 서명 불량·A₀의 `based_on` 불일치 → 4, 제품 지문 같고 `artifact_sha256`만 다른 파일 → `resume_plan_not_initial`, 후보의 `reconversion`·`restart_json`만 다른 파일 → 같은 거부, A₀와 Aₙ의 대상·작업 불일치 → 4.
- 백업 근거(7절): 결속 필드 없는 A₀ → `resume_backup_binding_missing`, 최초 근거 원문 해시 불일치·서명 불량 → 4, 최초·재개 근거의 `backup_id`·`artifact_sha256`·`taken_at` 등 하나라도 다름 → `resume_backup_evidence_mismatch`, 재개 근거 만료 → `backup_evidence_expired`, 같은 `evidence_id` 재사용 → 거부.
- 승인 사슬 거부: 사슬 없음·`supersedes` 불일치·다른 작업 키·서명 변조·지금 승인 만료 → 연결 전 4.
- 기간 경계: 창 마지막 순간 허용·정각 거부(`migration_resume_window_closed`, 앱 프로세스 시각 기준), 승인 만료와 근거 만료 구분, 연결별 판정 시각.
- 상태별: `not_started`·`completed`·`cursor_end_not_completed`·`closed`·`conflict`·`inconsistent` 각각 4절 표대로, 쓰기 0.
- 경합(6절 표): 같은 시작 커서 경쟁, 앞 호출 커밋 뒤 전진 커서, 앞 호출 완료 뒤, 실행 행 없음(P2 `migration_run_missing` 4, 새 실행 생성 0).
- 중단·미확정: 카드 중간 실패·마무리 실패·커밋 응답 유실 주입 → 1·`uncertain`, 커밋 범위 추정 없음.
- `apply`로 기존 실행 재개 시도는 여전히 `migration_run_exists` 4.

## 11. RS2 구현 결과 (2026-10-27, 제품 변경·합성 SQLite만)

- 제품(`app/srs/migration.py`): `apply_plan`에 `existing_run_only=False`, `expected_progress=None`. 입력 검사(9-2절 형식·조합)는 연결 전. `_run_id`에 같은 인자: 행 없음 `migration_run_missing`(INSERT 전), 범위·종류·설정 불일치 `migration_run_conflict`, `aborted` `migration_run_closed`, `started`·`failed` 아님 `migration_run_not_resumable`. 첫 연결에서 계정 잠금(`begin_card_write`)·`_run_id` 직후 `run_progress_values`(해시만 계산하는 도우미)로 9개 값을 다시 읽어 비교 → 다르면 `migration_run_changed`, 이어 `_resumable_cursor`(정수·0 이상 카드 수 미만) 아니면 `migration_run_not_resumable`. 모두 창 판정·커서 사용·업무 쓰기보다 먼저. 카드별 커밋·실패 표시·마무리는 그대로, 새 커밋 경계 없음. 두 인자를 생략하면 기존 동작, `new_run_only=True`는 P1 동작 그대로. CLI 모듈 import·판정 엔진 복제 없음.
- 검사(`tests/test_srs_migration_existing_run.py`, 합성 SQLite, 기대값은 시험이 계약 규칙으로 독립 계산): 부분 처리·`failed` 실행 재개(앞 카드 값·snapshot 보존, 남은 카드만 처리, `completed`), 잠금 → 대조 → 창 순서, 실행 행 없음(새 실행 0·DB 동일), 완료·커서 끝·닫힘·범위/계정/설정 불일치 무쓰기 거부, 요약 텍스트·snapshot 추가/삭제/교체·`started_at`·`status`·`finished_at` 변경과 정상 커서 전진의 `migration_run_changed`, 다른 실행 snapshot 변화 무관, 잘못된 형식·조합 연결 0회, 다른 계정·범위 밖 행 불변, 인자 생략 경로의 재개·완료 재호출·최초 적용 유지.
- 무쓰기 거부의 판정: DB 전체 덤프 전후 동일, 첫 연결 1회만 열리고 롤백. SQLite `BEGIN IMMEDIATE` 결과이며 PostgreSQL 행 잠금 증거가 아니다.
- RS3(CLI `resume`·`read_status` 확장)·RS2b·실제 PG는 미구현·승인 전.

## 12. RS2b 구현 결과 (2026-10-28, 합성만)

- `_ops_approval`: `FORMAT_VERSIONS = (1, 2, 3)`, v3 적용 승인만 선택 필드 `backup_evidence`(정확히 `{"sha256": 소문자 16진수 64자}`, 아니면 `approval_backup_evidence_invalid`), v1·v2·조회 승인은 그 필드가 있으면 `approval_fields_invalid`. `Approval.backup_evidence_sha256`(없으면 `None`). 원문 해시·작업 계획 지문·서명 이름공간 변경 없음. 기존 버전 거부 검사 2곳은 지원 범위 변경에 맞춰 "미지원 버전" 예시 값 3을 4로 바꿈.
- `srs_migrate.run_apply` 단계 5-1: 검증된 적용 승인에 `backup_evidence_sha256`이 있으면 고정한 근거 원문 해시와 대조, 다르면 `backup_evidence_binding_mismatch`(4, app import·연결·제품 호출 0). 같아도 C10 검증은 그대로.
- `_ops_backup_evidence`: `verify_backup_evidence_record` + `BackupEvidenceRecord`(현재 근거와 다른 형, `recheck` 불가). 공통 검사 순서는 `_checked`로 묶고 현재 유효성(`_times`)은 `verify_backup_evidence`·`recheck`에만 둠(동작 불변). 기록 검증은 `taken_at ≤ 지금`·기준 시각·문서 내부 순서를 유지하고 `지금 < valid_until`만 요구하지 않음. 서명은 지금 시각과 현재 신뢰·폐기 목록으로 검증.
- `_ops_preflight`: `_Verified`에 `first_apply`·`first_inquiry`(출력·`repr` 비노출), 사슬 검증 때 첫 쌍을 담음. `initial_apply_approvals(result, inputs)`는 결과 형·검증 표시·지금 입력 첫 링크 바이트 해시·A₀ `based_on` = I₀를 확인한 뒤에만 (A₀, I₀) 반환, 빈 사슬 `approval_chain_first_missing`, 그 밖 `preflight_result_mismatch`. 권한은 지금 승인만(과거 승인 권한 비합산), 공급자 재판정·재연결 재검증 경로 불변.
- RS3에 남은 연결: `run_resume`·`TOOLS.resume`, A₀ `plan` 재계산 대조(3-1), 최초 근거 기록 검증과 재개 근거 필드 대조(7-1), `read_status`의 고정값 9개 계산과 P2 호출(9-2).

## 13. RS3 구현 결과 (2026-10-28, 합성만)

- `srs_migrate.py`: `run_resume`(9-4절 순서 1~13), `progress_values`(같은 읽기 트랜잭션의 행·snapshot으로 고정값 9개), `read_status`의 snapshot 조회에 `id` 추가(`judge_status`·`status` 출력 불변), 명령줄 `resume`(`--initial-evidence`·`--initial-evidence-signature` 추가, `apply`는 이 두 인자를 받지 않음, 실제 연결 경로 없어 `connection_not_available` 4). `_ops_approval.TOOLS`에 `resume: write`. 최초 `apply`의 부분 처리 출력 `resume: not_implemented`는 그대로 둠(그 출력은 apply 명령의 것).
- 공급자 관측 경로는 이 단위 검사에서 연결 원천 주입으로 대체했다(읽기 `status`·쓰기 `resume` 단계의 승인·역할·`args` 판정은 실제 사전 검사). 시험용 연결·시계 주입은 Python 인자로만 있고 명령줄·환경 변수 옵션이 없다.

## 14. RS3 공급자 경로 합성 통합 검사 (2026-10-28, 합성만)

13절에서 연결 원천 주입으로 대체했던 공급자 관측 경로를 `resume`에 대해 따로 확인했다. 기존 실제 SQLite 제품 검사 19개는 그대로 두었다.

- 실제 코드로 실행한 것: `run_resume`, `_timed_connector`, `_product_connector` → `ProductConnector`, 어댑터(`provide_with_adapter`·`CopyingFactory`), 공급자(연결마다 사전 검사, 연결, 관측 시작문, `CatalogObserver`, `judge_observation`, 연결 후 `authorize_command`, 롤백·닫기), 승인·서명(시험 전용 임시 키)·이전 사슬·근거 확인·계획 파일, `read_status`·`judge_status`·`progress_values`, 제품 `rollback_window`·`to_candidates`·`AppPostgresConnection`. 횟수·추적 래퍼는 원래 함수를 그대로 호출하고 기록만 한다.
- 가짜로 대체한 것: 드라이버 함수, 연결·커서의 서버 응답(계약 권한 표로 만든 관측 카탈로그, 상태 조회 SELECT 두 개의 고정 응답). 가짜 서버는 스냅샷을 잡는 문장 뒤의 `SET TRANSACTION`만 거부한다(관측 시작문·`SET TRANSACTION READ ONLY`는 스냅샷을 잡지 않음). 기존 `FakeConn`은 이보다 엄격해 `read_status`의 격리 수준 문장을 거부하므로 이 파일에서만 서버 규칙에 맞췄다. 실제 PostgreSQL에서의 확인은 아니다.
- 대체한 제품 본문: `migration.apply_plan`만. 대체본은 주입된 `connect`를 제품 연결 수(첫 연결, 남은 카드, 마무리)만큼 실제로 열고 들어가 한 문장을 실행한 뒤 나오며(커밋·닫기는 실제 `ProductConnection`), 인자(`new_run_only=False`, `existing_run_only=True`, `expected_progress`, `batch_size`)를 기록한다. 제품의 기존 실행 전용·사전 값 대조 동작은 이 검사의 대상이 아니다(SQLite 19개·RS2 검사가 담당).
- 정상 경로: 상태 읽기 연결 1개(`ops_read`)와 쓰기 연결 3개(`ops_write_prb`)가 모두 관측 시작문 → 관측 → 계약 프로필 판정 → 연결 후 재판정을 거친 뒤에만 넘겨졌다. 프로필은 계약 상수(`contract_profiles`)로 만들고, 승인은 `status`(읽기)·`resume`(쓰기, `batch_size` 정확 결속)를 명시한다. 기대 권한은 관측에서 만들지 않는다.
- 거부: 읽기·첫 쓰기 연결 각각에서 역할 불일치 `observed_role_mismatch`, 필수 권한 누락 `observed_privileges_missing`, 초과 권한 `observed_privileges_excess`는 4·`before_first_write`·`changes: none`. 거부된 연결은 관측 뒤 `ROLLBACK`으로 끝나고 닫혔으며 넘겨지지 않았다(넘김 0, 업무 문장 0). 첫 커밋 뒤 두 번째 쓰기 연결에서 같은 세 경우는 1·`after_start`·`confirmed: unknown`·`uncertain`·`status_required`, 넷째 연결 없음, `apply_plan` 1회(재시도·다음 카드 없음). 상태 연결 전 만료는 드라이버 호출 0. 첫 쓰기의 드라이버 실패는 기존 규칙대로 `connect_failed` 1·`before_first_write`. 출력에 DSN·비밀번호·드라이버 문구 없음.
- 연결별 결속: 연결마다 새 시각으로 사전 검사가 다시 실행되고, 그 안에서 서명 검증 4회(Aₙ, I₀, A₀, I₀)와 사슬 판정이 반복됐다. 연결 후 재판정은 같은 시각에 현재 승인 Aₙ, 이전 승인 A₀, 기준 조회 I₀, 계획 `artifact_sha256`를 받았다. 첫 쓰기 뒤 승인 만료를 넣으면 다음 연결은 드라이버 호출 전에 `preflight_approval_expired`로 거부됐다. 첫 사전 검사 결과만으로 이후 연결을 허용하는 경로는 관찰되지 않았다.
- 검사: 새 `backend/tests/test_srs_migrate_resume_provider.py` 9개(단독·저장소 루트 discovery), 기존 resume SQLite 19개, 공급자 29개·제품 연결 21개·어댑터 16개 모두 통과(`-X dev`, 외부 `PYTHONPATH` 없이). 제품·공통 모듈·CLI 변경 없음, 발견된 결함 없음.
- 미검증: 실제 PostgreSQL에서의 관측·권한·`SET TRANSACTION` 순서, 실제 제품 `apply_plan`을 공급자 연결 위에서 실행하는 경우, 동시 재개, 운영 실행.

## 15. RS2·RS2b·RS3 합성 마감 (2026-10-28)

증거는 세 종류로 나누며 서로 대신하지 않는다.

| 단위 | 확인한 것 | 증거 종류 | 확인하지 않은 것 |
| --- | --- | --- | --- |
| RS2 | 제품 `apply_plan(existing_run_only, expected_progress)`: 실행 행 없음·완료·닫힘·불일치 거부, 잠금 → 대조 → 창 순서, 부분·`failed` 재개 | **실제 제품 + 합성 SQLite**(`test_srs_migration_existing_run.py`, `BEGIN IMMEDIATE`) | PostgreSQL 행 잠금·트랜잭션 |
| RS2b | 승인 형식 v3 `backup_evidence`, 최초 `apply`의 근거 해시 대조, 근거 기록 검증, 검증된 A₀·I₀ 접근 | **합성 단위 검사**(실제 서명은 시험 임시 키) | 실제 서버 |
| RS3 제품 실행 | CLI `resume` 1~13단계와 실제 제품 `read_status`·`apply_plan`: 기존 커밋·snapshot 보존, 남은 카드 처리, 잠금 아래 `migration_run_changed`, 결속 거부, 상태별 거부·보고, 기간 구분, 시작 뒤 실패 | **실제 제품 + 합성 SQLite**(`test_srs_migrate_resume_sqlite.py` 19개). 연결 원천은 앱의 SQLite 연결로 주입했고 **공급자 관측 경로를 거치지 않았다** | 공급자 관측·권한 판정 |
| RS3 공급자 경로 | `run_resume` → `_timed_connector` → `ProductConnector` → 어댑터 → 관측기 → 연결 후 재판정, 연결별 시각·사전 검사·사슬 서명, 역할·누락·초과 권한 거부와 정리 | **가짜 서버를 통한 합성 통합**(`test_srs_migrate_resume_provider.py` 9개). 드라이버·서버 응답은 가짜, 제품 `apply_plan`은 연결만 열고 닫는 대체본 | 공급자 연결 위의 실제 제품 `apply_plan`(실행하지 않았다), 실제 서버의 관측·권한 |

- 두 RS3 검사는 서로 보완할 뿐 합쳐서 "공급자 연결 위에서 실제 제품이 재개했다"는 증거가 되지 않는다. 그 조합은 RS4에서 처음 확인한다.
- 가짜 서버의 `SET TRANSACTION` 규칙(스냅샷 전이면 허용)은 **시험 모델**이다. `read_status`가 공급자의 `SET TRANSACTION READ ONLY` 뒤에 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`를 보내는 순서가 실제 PostgreSQL에서 받아들여지는지는 미검증이며 RS4 첫 항목이다.
- C10 근거는 합성 서명 진술이고 `restore_verified`·`backup_artifact_checked`는 `false`다.
- 마감 범위 밖: 실제 PostgreSQL(잠금·동시 재개·권한·문장 순서), 실제 장애(커밋 응답 유실·OS·네트워크), 운영 활성화, 근거 장기 보존 위치.

RS3 합성 마감. RS4 계획 검토 대기.

# 명시 전환 CLI 계획 (2026-10-25, 문서만, 보정 2차, 계약 재검토 대기)

상태: **계획만.** 구현, 코드 변경, DB 접속, PG 실행, 키 생성, 운영 실행은 승인되지 않았다. 아래 정책·결정은 모두 제안이며 승인된 것이 아니다. 로드맵 `OPERATIONS_READINESS_PLAN.md` 순위 5. 공통 규칙은 `OPS_TOOL_SAFETY_CONTRACT.md`(지문 3절, 승인 4-6절, 결과 확정 9-2절, 트랜잭션 10절, 실행 기록 11절)를 그대로 따르고, 여기에는 전환 도구에 고유한 부분과 공통 모듈에 필요한 변경 후보만 적는다. 전환 알고리즘·후보 판정·모드 설정은 새로 만들지 않는다.

보정 1차(2026-10-25 검토 사항): ① 계획 파일 해시를 서명된 적용 승인 `plan`에 넣는 계산 경로(2절), ② 커서 끝과 `completed` 기록의 구분(4절), ③ 재개 승인의 이전 승인 전달·검증 경로(5절), ④ 결정표 구체화(12절), 후보 필드 수 정정(10개).

보정 2차(2026-10-25 검토 사항): ① `artifact_sha256`과 서명 검증된 이전 승인이 사전 검사뿐 아니라 공급자의 연결 후 재판정까지 전달되는 경로(5-4절), ② 최초 쓰기 전 거부와 실행 시작 후 중단의 분리, 사례별 종료 코드·출력·다음 행동(9절), ③ 결정표 D7~D9 정리(12절).

## 0. 확인한 코드 사실 (정적 읽기, 실행 안 함)

- `app/srs/migration.py`
  - `dry_run(keys)`: `_scope`가 계정 하나·카드 하나 이상을 요구하고(`explicit_single_account_scope_required`), 카드를 `(kind, ref_id)`로 정렬·중복 제거한다. `get_connection(read_only=True)` 한 연결에서 카드마다 `inspect_card`. run·config·snapshot 행을 만들지 않는다.
  - `MigrationCandidate`: 필드 **10개**(`key`, `card_fingerprint`, `logs_fingerprint`, `card_version`, `quality`, `flags`, `values_json`, `last_log_id`, `reconversion`, `restart_json`). 적용 때 비교는 데이터클래스 전체 동등(`current != candidate`)이다.
  - `_plan_json(plan)`(= 실행의 `scope`): `user_id`, `config_version`, 카드별 9개 값(`kind`, `ref_id`, `card`, `logs`, `version`, `quality`, `values`, `flags`, `last_log_id`). **`reconversion`·`restart_json`은 들어 있지 않다.** 따라서 저장된 `scope_json`만으로는 후보를 복원할 수 없다.
  - `apply_plan(plan, run_key, approved=True, batch_size)`: `approved` 없으면 `explicit_apply_required`. `_run_id`가 `run_key` 형식을 검사하고, 기존 실행이면 범위(`_scope_matches`: 원문 또는 U10-e 뒤 `request_sha256`)·`mode`·`config_version`이 같아야 하며(다르면 `migration_run_conflict`), `aborted`면 `migration_run_closed`. 새 실행이면 `started` 행을 만든다(첫 연결에서 커밋).
  - 카드마다 새 연결 한 개 = 트랜잭션 한 개: 계정 잠금(`begin_card_write` → `lock_account`·활성 차단 검사) → 저장 커서가 이 카드 위치인지(`migration_cursor_conflict`) → 30일 창(`_require_window`) → 이미 snapshot 있으면 `already_applied` → 잠금 아래 `inspect_card(for_update=True)` 재판정 → 후보와 다르면 `conflict`(쓰기 없음), 값 없음이면 `blocked`, 그 외 카드 갱신 + snapshot 삽입 → 커서·결과를 실행 행에 저장. 연결 컨텍스트 종료가 커밋이다.
  - `blocked` 카드도 쓰기가 있을 수 있다: `identity_unknown`·`unavailable`·`already_fsrs`·`reconvert_blocked` 외에는 `record_intro`가 카드의 `history_intro_*` 열을 갱신할 수 있다(`app/srs/history_intro.py`).
  - 한 호출은 커서부터 `batch_size`장까지만 처리한다. 루프가 끝난 뒤 **별도 연결**에서 `end == len(plan)`일 때만 `completed`·`finished_at`을 쓴다. 이 마무리 연결은 루프의 `try` 밖이라, 여기서 실패하거나 마지막 카드 커밋 뒤 중단되면 커서는 카드 수인데 상태는 `started`로 남는다.
  - 커서가 이미 카드 수 이상이면 저장 결과를 돌려주고 **마무리 블록 전에 반환한다.** 따라서 같은 키 재호출은 `started`를 `completed`로 바꾸지 않는다.
  - 예외: 창 오류는 그대로 올리고 상태를 바꾸지 않는다. 그 밖의 루프 안 오류는 별도 트랜잭션에서 커서가 실패 카드 위치이고 `started`일 때만 `failed`로 바꾼 뒤 다시 올린다. 실패 카드 앞까지는 이미 커밋돼 있다. `failed` 실행은 같은 키로 이어서 처리된다(카드 쓰기마다 상태를 `started`로 다시 씀, `aborted`만 닫힘). 코드상 `failed`는 커서 < 카드 수일 때만 생긴다.
  - 완료 재호출: 첫 연결에서 계정 잠금·`_run_id` 조회만 하고 저장 결과를 돌려준다(`applied` → `already_applied`). 표 행 변경은 없지만 계정 잠금은 잡으며, 활성 쓰기 차단이 있으면 재호출도 `account_writes_blocked`로 거부된다. 창 판정은 커서 < 카드 수일 때만 한다.
- `app/database.get_connection`: 앱 `DATABASE_URL`만 따른다(`assert_safe_database_url`). 연결 주입 지점이 없다.
- `scripts/inspect_srs_migration.py`: 합성 SQLite(`qa_srs_b2_*.db`) 전용 읽기 미리보기. 적용 명령 없음.
- `scripts/_ops_approval.py`
  - `TOOLS`에 전환 도구가 없다.
  - `job_plan_fingerprint(db_identity, manifest, tool, account_id, job_key, job_inputs, product_fingerprint)`: 이 일곱 값만 다이제스트한다. 계획 파일 같은 추가 산출물을 받을 자리가 없다.
  - `authorize_command`는 적용 승인이면 위 값을 다시 계산해 `approval.plan_for(account)`와 비교하고(`job_plan_mismatch`), `job_inputs`가 승인과 정확히 같아야 한다(`job_input_mismatch`).
  - `check_succession(current, prior)`: `prior`가 없는데 `current.supersedes`가 있으면 `approval_supersedes_unknown`. `supersedes`는 승인 id만 담고 바이트 해시가 없다(`based_on`은 id + SHA-256).
- `scripts/_ops_preflight.py` `run_synthetic_preflight`: `authorize_command`를 `prior` 없이 부른다. `PreflightInput`에는 이전 승인 바이트·서명 필드가 없다. **따라서 지금은 `supersedes`가 있는 승인은 모두 거부된다.**
- `scripts/_ops_provider.py` `provide_synthetic_connection`: 호출마다(재연결도 새 호출) `run_synthetic_preflight(inputs)`로 서명을 검증한 뒤, 같은 입력 바이트를 `parse_approval`로 다시 해석해 연결·관측 후 `judge_observation`과 `authorize_command`를 **다시 부른다.** 이때도 `prior`·추가 산출물 값을 넘기지 않는다. `_ops_adapter.provide_with_adapter`가 이 경로를 감싼다.
- `apply_plan`이 연결 함수에서 예외를 받으면: 카드 루프 안이면 `except Exception`에서 **또 다른 연결**로 `failed` 표시를 시도한다. 그 연결도 같은 이유(승인 만료 등)로 거부되면 `failed` 표시 없이 그 예외가 올라가고 상태는 `started`로 남는다. 첫 연결(실행 행 생성) 전에 거부되면 아무것도 커밋되지 않는다.
- `scripts/_ops_audit_run.py`: 공급자에서 연결 1개를 받아 감사 한 번에 쓴다. 전환은 연결이 카드 수 + 2개(+ 실패 표시 1개) 필요하다.

## 1. 최소 경로 (재사용)

`scripts/srs_migrate.py`(가칭, 새 파일) → 공통 승인·대상·연결 검사 → 기존 `dry_run` / `apply_plan`. CLI가 하는 일은 입력 검사, 계획 파일 기록·대조, 승인 연결, 연결 주입, 상태 판정, 출력·종료 코드·실행 기록뿐이다.

- 명령: `dry-run`(기본, 읽기), `apply`(쓰기), `status`(읽기: 실행 행의 상태·커서·창, 쓰기 없음).
- 범위: `--account <id>` 하나와 `--personal-id`·`--lexeme-id`(명시 카드 목록)가 필수. 계정 전체·여러 계정 자동 확장 없음. 여러 계정은 계정마다 별도 작업 키와 별도 실행이다(`_scope` 제약 그대로).
- 작업 키: `--run-key`(형식은 `_run_id` 규칙 그대로). 조회 때 정해 승인 `job`에 고정한다.
- `apply`는 계정 id 재입력과 적용 승인이 모두 있어야 한다(계약 10절). `apply_plan(approved=True)`는 그 확인 뒤에만 호출한다.

### 1-1. `dry-run` 합성 읽기 경로 계약 (2026-10-26 고정, 이 단위 범위)
- 구현 상태(2026-10-26, 합성): `backend/scripts/srs_migrate.py`, `_ops_approval.TOOLS`에 `srs_migrate: {dry_run: read}`. `apply`·`status`·실제 드라이버·실제 PG 종단은 미구현.
- 명령: `scripts/srs_migrate.py`. 명령 생략 시 `dry-run`. CLI `dry-run`은 승인 단계 이름 `dry_run`(읽기)에 대응한다. `TOOLS`에는 `srs_migrate: {dry_run: read}`만 둔다. `apply`·`status`는 이 단위에서 등록하지 않고, CLI는 `command_not_implemented`로 쓰기 없이 거부한다.
- 입력: `--account`(1 이상 정수 하나), `--run-key`(`[A-Za-z0-9_.:-]{1,128}`), `--personal-id`·`--lexeme-id`(반복, 1 이상 정수, 합계 1~2000개), `--out`(새 계획 파일 경로). 계정 전체·다른 계정으로 확장하지 않는다. 같은 카드를 두 번 주면 사용법 오류(조용히 합치지 않음). 검사 우회·연결 함수 선택 인자나 환경 변수는 없다.
- 카드 목록 정규형: `(kind, ref_id)`를 `kind`(`lexeme` < `personal`), `ref_id` 오름차순으로 정렬한 배열을 `json.dumps([[kind, ref_id], ...], separators=(",", ":"))`의 ASCII 바이트로 만들고, `cards_sha256 = sha256(b"jp-vocab-ops/migration-cards/v1
" + 그 바이트)`. 이 순서는 제품 `_scope`의 정렬과 같다.
- 승인 `job`: `key` = 작업 키, `inputs` = `{"account_id": 계정, "cards_sha256": 위 해시, "card_count": 개수}`(기존 승인 입력 자료형: 정수·문자열). 실행 입력이 이 값과 정확히 같아야 한다(`job_input_mismatch`). 해시·건수가 같다는 것만으로 다른 입력을 받아들이지 않도록, 제품 `dry_run` 결과의 카드 키 순서가 정규 목록과 정확히 같은지 다시 확인한다(`card_scope_mismatch`).
- 허용 승인(2026-10-26 검토 보정): 사전 검사가 직접 서명 검증한 승인이 `tool = srs_migrate`, `kind = inquiry`이고 현재 명령 단계가 `dry_run`·읽기일 때만 진행한다. 다른 도구(`d2_*`의 `dry_run` 등)나 적용 승인 형식은 서명이 유효해도 app import·연결·파일 생성 전에 `approval_tool_not_srs_migrate`·`approval_kind_not_inquiry`(4)로 거부한다. 형식 해석만으로 허용하지 않으며, 공통 승인 모듈의 다른 도구 동작은 바꾸지 않는다.
- 흐름: 입력 검사 → 실행 입력과 요청 대조 → app 환경 고정 → 실제 사전 검사(서명·manifest·대상·명령·역할·계정·작업 입력) → 그 뒤에만 `app.srs.migration` import → 위 허용 승인 확인 → `ProductConnector`(연결마다 공급자 경로 전체, 읽기 연결)로 제품 `dry_run(keys, connect=...)` → 제품 지문 `sha256(_plan_json)` → 계획 파일 직렬화·새 파일 기록·다시 읽기·제품 후보 복원 대조 → 작업 계획 지문 `job_plan_fingerprint(..., product_fingerprint, artifact_sha256)` → 출력.
- 출력(성공): `status`, `command`, `db_identity`, `account_id`, `job_key`, `card_count`, 품질별 건수, `product_fingerprint`, `artifact_sha256`, `job_plan`. 후보 JSON·단어·뜻·연결 비밀·드라이버 원문·파일 경로는 출력하지 않는다. 실패는 `status`와 고정 `code`만.
- 종료 코드(이 읽기 범위만, 적용 정책 승인 아님): 0 정상, 2 사용법, 4 승인·입력 거부(사전 검사·승인·작업 입력·연결 단계 승인 대조 거부, 미구현 명령, 실제 연결 경로 없음), 1 실행·파일 기록 실패(연결·관측 실패, 제품 조회 실패, 계획 파일 기록·재확인 실패).
- 닫힌 경계: 기본 실제 드라이버는 없다. CLI 프로세스는 실제 연결을 열 수 없으며 `dry-run`도 `connection_not_available`(4)로 끝난다. 정상 실행은 시험 코드가 Python에서 합성 입력·가짜 드라이버(또는 합성 SQLite 연결)를 주입한 경우뿐이다. 계획 파일의 동시 교체 방지는 완전한 원자적 보장이 아니다(2-3).

## 2. 계획 파일과 서명 승인의 결속

### 2-1. 값
- 계획 파일: 조회(`dry-run`)가 후보 10개 필드 전체를 고정 형식으로 쓴 파일(저장소 밖). 출력에는 건수·품질별 수·고정 코드·지문만 쓰고 단어·뜻·JSON 본문은 쓰지 않는다(계약 10절).
- 제품 계획 지문 = `sha256(_plan_json(plan))`. **바꾸지 않는다.** U10-e 뒤 실행 행에 남는 `request_sha256`와 같은 값이라 DB와 대조할 수 있다.
- 계획 파일 지문 = 계획 파일 바이트의 SHA-256. `_plan_json`에 없는 `reconversion`·`restart_json`까지 묶는다.

### 2-2. 계산 경로 (공통 계약 최소 변경안, 결정 D2)
- 구현 상태(2026-10-25, 사용자 승인 범위: 이 결속만, 합성): 계약 `OPS_TOOL_SAFETY_CONTRACT.md` 3-3-1절 고정, `_ops_approval`·`_ops_preflight`·`_ops_provider`에 반영, `_ops_adapter`는 입력을 그대로 넘겨 변경 없음. 계획 파일 읽기·직렬화, 전환 도구 등록, 승인 사슬(5-2)은 미구현.
1. 조회 승인의 `job.inputs` = 계정과 카드 목록(작업 키는 `job.key`). 계획 파일이 아직 없으므로 계획 파일 지문은 `job.inputs`에 넣지 않는다. 적용 승인의 `job`도 같은 값이라 기존 4-6-2 "조회와 같은 `job`" 규칙과 충돌하지 않는다.
2. 조회 실행이 계획 파일을 쓴 뒤 작업 계획 지문을 계산한다:
   `job_plan_fingerprint(db_identity, manifest, tool, account_id, job_key, job_inputs, product_fingerprint, artifact_sha256 = 계획 파일 지문)`.
   새 인자 `artifact_sha256`은 선택 값이며, `None`이면 다이제스트 입력에 키 자체를 넣지 않아 **기존 도구의 지문 값은 그대로다.** 값이 있으면 `{"artifact": <hex64>}`를 더한다.
3. 사람이 그 출력값을 적용 승인 `plan`(계정별)에 적고 서명한다. 계획 파일 지문은 이렇게 서명된 `plan` 안에 들어간다.
4. 적용 때 CLI는 제시된 계획 파일 바이트로 계획 파일 지문과 제품 계획 지문을 다시 계산해 `authorize_command`(→ `job_plan_fingerprint`)에 넘긴다. 서명된 `plan`과 같을 때만 통과한다.
- **로컬 실행 기록의 해시와 같다는 사실은 근거가 아니다.** 승인 여부는 서명된 적용 승인 `plan`과의 대조로만 판정한다. 실행 기록의 해시는 운영자가 파일을 찾는 보조 정보일 뿐이다.
- 영향: `_ops_approval.job_plan_fingerprint`·`authorize_command`에 선택 인자 1개, `_ops_preflight.PreflightInput`에 선택 필드 1개(`artifact_sha256`), 그리고 사전 검사뿐 아니라 공급자의 연결 후 재판정에도 같은 값이 전달돼야 한다(5-4). 기존 도구 호출은 바뀌지 않음. 공통 모듈 변경이므로 별도 구현 단위(13절 2단계)다.

### 2-3. 계획 파일 형식 버전 1 (2026-10-26 고정, 합성 구현 범위)
- 구현 상태(2026-10-26, 합성): `backend/scripts/_ops_plan_file.py`(`parse_plan_bytes`·`read_plan_file`·`serialize_plan`·`write_plan_file`·`to_candidates`). 전환 CLI 실행, `TOOLS` 등록, `apply_plan` 호출은 미구현.
- 성격: 조회가 쓰는 **자료 파일**이다. 실행 코드 manifest의 허용 경로에 넣지 않고 manifest 규칙을 넓히지 않는다. 파일의 결속은 바이트 해시(`artifact_sha256`)가 서명된 적용 승인 `plan`에 들어가는 것뿐이다(2-2, 계약 3-3-1).
- 인코딩: UTF-8(BOM 없음), JSON 하나, 최대 8 MiB, 중첩 깊이 최대 4(최상위 객체 → 후보 배열 → 후보 객체 → `flags` 배열). 중복 키, `NaN`·`Infinity`, 소수(부동소수) 값은 어디에도 허용하지 않는다. 쓰기는 `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` 형태이지만, 읽을 때 정규화하거나 다시 직렬화하지 않는다.
- 최상위 키(정확히 이 8개): `format` = `"jp-vocab-ops/migration-plan"`, `format_version` = 정수 1(불리언·문자열 불가, 그 밖의 버전은 거부), `db_identity`(소문자 16진수 64자), `account_id`(1 이상 2^63-1 이하 정수), `job_key`(`[A-Za-z0-9_.:-]{1,128}`, `run_key` 형식), `config_version`(`[A-Za-z0-9_.:-]{1,64}`), `product_fingerprint`(소문자 16진수 64자, `sha256(_plan_json(후보))`), `candidates`(배열 1~2000개).
- 후보 키(정확히 11개, `MigrationCandidate`의 10개 필드와 같은 뜻; `key`는 `kind`·`ref_id`로 나누고 계정은 최상위 `account_id`): `kind`(`personal`·`lexeme`), `ref_id`(1 이상 정수), `card_fingerprint`(16진수 64자 또는 `null`), `logs_fingerprint`(16진수 64자), `card_version`(0 이상 정수 또는 `null`), `quality`(`complete`·`incomplete`·`fresh`·`unavailable`·`already_fsrs`·`identity_unknown`·`reconvert_blocked`), `flags`(문자열 배열 0~64개, 각 `[A-Za-z0-9_.:-]{1,64}`, 순서 유지), `values_json`(문자열 최대 64 KiB 또는 `null`), `last_log_id`(0 이상 정수), `reconversion`(`null`·`restored`·`state_none`·`state_none_restart`), `restart_json`(`null` 또는 `{"previous_boundary":n,"rollback_record_id":m}`의 정규 JSON 문자열, 둘 다 0 이상 정수). 생략 가능한 키는 없다(값이 `null`이어도 키는 있어야 함).
- 조합(기존 `_scope_card`·후보 생성 코드 기준, 2026-10-26 보정): `card_fingerprint`와 `card_version`은 둘 다 `null`이거나 둘 다 값이 있다. 둘 다 `null`이면 `quality`는 `unavailable`이어야 하지만, `unavailable`이라고 반드시 `null`은 아니다(접근을 잃었지만 진도 행이 남은 구독 카드는 지문·버전이 있는 `unavailable`이 정상; 이전 문안의 '⇔ unavailable'은 잘못이었다). `unavailable`·`already_fsrs`·`identity_unknown`·`reconvert_blocked`는 `values_json`·`reconversion`·`restart_json`이 모두 `null`. `reconversion`이 `null`이면 `restart_json`도 `null`. `restored`는 `values_json` 필수, `restart_json`은 선택. `state_none`은 `quality: incomplete`·`values_json` 필수·`restart_json` 없음. `state_none_restart`는 `quality: incomplete`·`values_json`·`restart_json` 필수.
- 순서·중복: 후보는 `(kind, ref_id)` 오름차순(제품 `_scope`와 같은 순서)이고 중복이 없어야 한다. 계정은 파일 하나에 하나.
- 제품 후보 복원: 순수 해석(앱 import 없음)이 끝난 뒤, 앱 환경을 고정한 상태에서만 `app.srs.migration`을 import해 `MigrationCandidate`를 만든다. 새 판정 규칙을 만들지 않고 기존 `_plan_json`·`_full_scope`(값 계약)·`_scope`(순서)를 그대로 써서 확인하고, `config_version`이 현재 엔진 설정과 같고 `sha256(_plan_json(복원 후보))`가 파일의 `product_fingerprint`와 같아야 한다.
- 고정 바이트: 파일은 한 번 읽은 바이트를 보존하고, 해석·`artifact_sha256`·복원은 모두 그 바이트에서만 한다. 읽은 뒤 원본 파일이 바뀌어도 영향이 없다.
- 쓰기: 기존 파일을 덮어쓰지 않는다(같은 폴더의 임시 파일을 배타 생성 → 동기화 → 대상 이름으로 새 링크, 대상이 있으면 거부). 쓴 뒤 다시 읽어 바이트가 같을 때만 성공으로 돌려준다. 쓰기 실패·부분 출력은 성공 결과가 아니다. 정리는 **이번 호출이 만든 파일만** 한다(2026-10-26 보정): 임시 파일은 배타 생성에 성공한 경우에만, 최종 파일은 링크에 성공했고 지금도 임시 파일과 같은 파일(장치·파일 번호 동일)일 때만 지운다. 생성에 실패했거나 소유를 확인할 수 없는 파일, 이름이 충돌한 기존 파일은 지우지 않고 내용도 바꾸지 않는다. 임시 이름 충돌은 `plan_file_write_failed`, 최종 이름 충돌은 `plan_file_exists`.
- 거부: 고정 코드만 담고 파일 본문·원값·절대 경로·OS 원문을 담지 않는다(`plan_file_unreadable`, `plan_file_too_large`, `plan_file_format_invalid`, `plan_file_fields_invalid`, `plan_file_version_unsupported`, `plan_file_value_invalid`, `plan_file_candidates_invalid`, `plan_file_combination_invalid`, `plan_file_exists`, `plan_file_write_failed`, `plan_file_config_mismatch`, `plan_file_scope_invalid`, `plan_file_product_mismatch`).

## 3. 승인 연결과 거부

- 조회 승인(`inquiry`): 읽기 역할·읽기 프로필, `job` = 작업 키 + 계정 + 카드 목록. 결과: 계획 파일, 제품 계획 지문, 계획 파일 지문, 작업 계획 지문(2-2).
- 적용 승인(`apply`): `based_on` 조회 승인, `plan` = 2-2의 작업 계획 지문, `job`은 조회 승인과 같다(4-6-2). 쓰기 역할·쓰기 프로필.
- 적용 직전(쓰기 0) 거부:
  - 업무 입력(계정·카드 목록·작업 키)이 승인과 다르면 `job_input_mismatch`.
  - 제시된 계획 파일로 다시 계산한 작업 계획 지문이 서명된 `plan`과 다르면 `job_plan_mismatch`.
  - 4절의 최초 적용 판정에서 현재 상태가 계획과 다르면 `plan_changed`.
- 카드 단위 재판정은 기존대로 `apply_plan`이 잠금 아래 한다. 그 결과 `conflict`는 그 카드만 쓰기 없음이며 실행 전체 거부가 아니다.

## 4. 실행 상태 판정

### 4-1. 원칙
- `cursor = 카드 수`만으로 정상 완료를 선언하지 않는다. 정상 완료는 `status = completed`이고 `finished_at`이 있으며 아래 일관성 검사를 통과할 때만이다.
- **현재 코드의 재호출 결과와 CLI의 상태 판정은 다르다.** 커서가 끝에 있으면 `apply_plan` 재호출은 상태와 관계없이 저장 결과를 돌려준다(0절). CLI는 그 반환을 완료 근거로 쓰지 않고, 호출 전에 실행 행을 읽어 상태를 따로 판정한다.
- **자동 상태 보정은 이 범위에 없다.** CLI는 `started`를 `completed`로 바꾸거나, 커서·결과·snapshot을 고치지 않는다. 보정 경로가 필요한지는 결정 D7.
- 일관성 검사(읽기): `summary_json`을 읽을 수 있고, 커서가 0 이상 카드 수 이하이며, 결과 수 = 커서, 결과 순서가 계획 파일 카드 순서와 같고, `applied`·`already_applied` 결과 카드에는 이 실행의 snapshot이 있고 `conflict`·`blocked` 카드에는 없으며, 이 실행의 snapshot이 범위 밖 카드에 없음. 실행의 범위는 계획 파일의 `_plan_json`과 같아야 한다(`_scope_matches`), `mode`·`config_version`도 같아야 한다.

### 4-2. 상태별 기대 결과

| 실행 행 상태 | CLI 판정 | `status` 출력 | `apply` 동작 | 쓰기 |
| --- | --- | --- | --- | --- |
| 없음 | 최초 적용 | `not_started` | 새로 읽은 후보 전체가 계획 파일과 같으면 `apply_plan`, 다르면 `plan_changed` | 카드마다 커밋 |
| `started`, 커서 < 카드 수, 검사 통과 | 미완료(중단 또는 다른 프로세스 실행 중일 수 있음) | `incomplete` | 30일 창 안이면 **최초 계획 파일 그대로** `apply_plan`(재개). 다른 프로세스와 겹치면 기존 잠금·`migration_cursor_conflict` | 미처리 카드만 |
| `failed`, 커서 < 카드 수, 검사 통과 | 중간 실패 | `failed_at_cursor` | 위와 같음(재개) | 미처리 카드만 |
| `completed`, 커서 = 카드 수, `finished_at` 있음, 검사 통과 | 정상 완료 | `completed` | 재호출: 저장 결과 반환(`already_applied`) | 없음(계정 잠금만) |
| `started`, 커서 = 카드 수, 검사 통과 | **커서 끝·완료 미기록** | `cursor_end_not_completed` | `apply_plan`을 부르지 않는다. 보고하고 멈춤(D7) | 없음 |
| `aborted` | 닫힘 | `closed` | `migration_run_closed` | 없음 |
| 범위·`mode`·설정 다름 | 다른 요청 | `conflict` | `migration_run_conflict` | 없음 |
| 창 밖·창 확인 불가(커서 < 카드 수) | 기존 | `window_closed`·`window_unverifiable` | 기존 거부 | 없음 |
| 손상·불일치: `summary_json` 읽기 불가, 커서 범위 밖, 결과 수·순서 불일치, snapshot 누락·초과, `completed`인데 커서 < 카드 수, `failed`인데 커서 = 카드 수, `completed`인데 `finished_at` 없음 | 확인 필요 | `inconsistent` + 고정 사유 코드 | 부르지 않음. 보고하고 멈춤 | 없음 |

- 재개 때 새 dry-run으로 계획을 다시 만들어 승인 지문과 비교하지 않는다. 이미 커밋된 카드는 정상적으로 값이 바뀌었으므로 그 비교는 언제나 다르다(정상 부분 커밋을 `plan_changed`로 막지 않음). 대신 (1) 서명된 `plan`으로 최초 계획 파일을 다시 검증하고(2-2), (2) 커서 앞은 4-1 일관성 검사로 대조하며, (3) 커서 뒤 카드는 `apply_plan`의 잠금 아래 재판정에 맡긴다. 변경 검사를 생략하는 것이 아니라 위치에 따라 근거가 다르다.
- 실패·중단: 카드별 커밋 경계와 커서가 보존된다. 전체 원자적 실행이 아니므로 결과는 "커서까지 적용됨 + 나머지 미처리"로 보고하고, 되돌림은 기존 `rollback_plan`(별도 승인, 이 단위 범위 밖)이다.
- `batch_size`를 넘는 범위는 여러 번 호출해야 끝난다. 호출마다 4-2 표로 다시 판정한다.

### 4-3. `status` 읽기 경로 계약 (2026-10-26 고정, 합성 범위)
- 구현 상태(2026-10-26, 합성): `srs_migrate.run_status`·`read_status`·`judge_status`, `TOOLS` `srs_migrate.status: read`. 상태 보정·재개 실행·`apply`·실제 드라이버·실제 PG 종단은 미구현. 범위를 해석할 수 없는 자기 계정 실행도 `not_started`로 보이는 것은 정보 비노출 정책의 대가다.
- 입력: `dry-run`과 같은 `--account`·`--run-key`·`--personal-id`·`--lexeme-id`. `--out`은 받지 않는다(사용법 오류). 새 dry-run 계획이나 계획 파일을 만들지 않는다. 이 결과는 현재 기록의 상태 보고일 뿐이며, 최초 계획 파일의 승인 결속 검증이나 재개 허가가 아니다(`resume_ready` 같은 출력 없음).
- 승인: 새 조회 승인. 사전 검사가 서명 검증한 승인이 `tool = srs_migrate`, `kind = inquiry`, 현재 단계 `status`·읽기여야 한다(아니면 app import·연결 전에 4). `job.inputs`는 1-1과 같은 `account_id`·`cards_sha256`·`card_count`. `TOOLS`는 `srs_migrate: {dry_run: read, status: read}`이며 적용 단계는 없다.
- 읽기: `ProductConnector` 읽기 연결 하나에서 일관된 읽기 트랜잭션(PostgreSQL은 첫 업무 문장으로 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`, SQLite는 `BEGIN`)으로 실행 행 → 범위 확인 → 이 실행의 snapshot만 읽는다. 계정 쓰기 잠금·상태 갱신·보정은 하지 않는다.
- 소유권과 외부 응답: `run_key`는 전역 키다. 실행 행의 `scope_json`을 기존 형식 함수(원문 `_full_scope`, 정리 뒤 `_reduced_scope`)로 해석해 `user_id`가 요청 계정일 때만 세부 상태를 낸다. 키가 없거나, 다른 계정의 실행이거나, 범위를 해석할 수 없어 소유자를 확인할 수 없으면 **모두 같은 응답** `not_started`(세부 필드 없음)를 낸다. 따라서 `not_started`는 "이 계정의 확인 가능한 실행 기록이 없음"이지 같은 키로 새 실행을 시작해도 된다는 뜻이 아니다. 저장된 `scope_json`·`summary_json`은 모든 깊이에서 중복 키를 거부하는 엄격한 해석으로만 읽는다(2026-10-26 검토 보정): `scope_json`에 중복 키가 있으면 원문·정리된 형식 모두 소유 확인 불가(없는 키와 같은 `not_started`, snapshot 조회 없음), 소유가 확인된 실행의 `summary_json`에 중복 키가 있으면 `inconsistent`(`summary_unreadable`). 첫 값·마지막 값을 골라 정상화하지 않는다.
- 소유가 확인된 실행의 범위 대조: `mode = apply`, 실행 행과 범위의 `config_version`이 현재 엔진 설정과 같고, 범위 카드 `(kind, ref_id)` 목록이 요청 목록과 순서까지 같아야 한다. 다르면 `conflict`(사유 `mode`·`config`·`cards`).
- 일관성 검사(4-1과 같음): `summary_json`이 없으면 커서 0·결과 없음, 있으면 키가 정확히 `cursor`·`results`, 커서는 0 이상 카드 수 이하의 정수(불리언 아님), 결과 수 = 커서, 결과 i의 `kind`·`ref_id`가 범위 카드 i와 같고 `result`는 `applied`·`already_applied`·`conflict`·`blocked` 중 하나, `applied`·`already_applied` 카드에는 이 실행·이 계정의 snapshot이 정확히 1개, `conflict`·`blocked` 카드와 커서 뒤 카드에는 없음, 이 실행의 snapshot 중 범위 밖·다른 계정 것이 없음, `finished_at`은 `completed`에만. 다른 실행의 snapshot으로 누락을 메우지 않는다.

| 판정 | 조건 | 종료 코드 |
| --- | --- | --- |
| `not_started` | 확인 가능한 이 계정의 실행 없음(외부 응답 동일) | 0 |
| `incomplete` | `started`, 커서 < 카드 수, 일관 | 3 |
| `failed_at_cursor` | `failed`, 커서 < 카드 수, 일관 | 3 |
| `completed` | `completed`, 커서 = 카드 수, `finished_at` 있음, 일관 | 0, 결과에 `conflict`·`blocked`가 있으면 5 |
| `cursor_end_not_completed` | `started`, 커서 = 카드 수, 일관 | 6 |
| `closed` | `aborted` | 0 |
| `conflict` | 이 계정 실행이지만 종류·설정·카드 범위가 요청과 다름 | 6 |
| `inconsistent` | 위 일관성 검사 실패, 알 수 없는 상태, `failed`·커서 끝, `completed`·커서 미달, `finished_at` 불일치 | 6 |

- 기간: 소유가 확인된 실행에 한해 기존 `rollback_window(started_at, 지금)` 결과(`open`·`expired`·`unverifiable`)를 `window`로 따로 보고한다. 상태 판정과 재개 가능 여부를 섞지 않는다.
- 출력: `status`, `command = status`, `state`, 소유 확인 시 `reason`(해당 시), `card_count`, `cursor`, 결과 종류별 건수, `window`, `finished`. 실행 id·시각 원문·카드 키·snapshot 내용·연결 비밀은 출력하지 않는다. 승인·입력 거부 4, 사용법 2, 실행 실패 1은 1-1과 같다.

### 4-4. 최초 `apply` 합성 구현 계약 (2026-10-26 작성, 문서만, 계약 검토 대기)
범위는 **실행 기록이 없는 작업의 첫 적용**뿐이다. 미완료 재개, 완료 재호출, 상태 보정은 후속 단위다. 아래 정책·결정은 모두 제안이며 승인된 것이 아니다.

#### 4-4-1. 승인과 계획 파일
- 승인: 사전 검사가 서명 검증한 승인이 `tool = srs_migrate`, `kind = apply`, `based_on` = `srs_migrate` 조회 승인이어야 한다. 적용 승인의 `steps`에는 두 단계를 따로 둔다: `dry_run`(읽기 역할·읽기 프로필, 적용 직전 비교용)과 `apply`(쓰기 역할·쓰기 프로필, `apply_plan`용). 연결마다 그 연결의 명령 단계로 사전 검사·공급자 판정을 받는다(읽기 연결은 `dry_run`, 쓰기 연결은 `apply`). 한 단계의 역할·프로필로 다른 단계를 대신하거나 자동 변경하지 않는다. `TOOLS`에 `srs_migrate.apply: write`를 추가하는 것은 구현 단위의 승인 항목이다.
- 공통 경로 검증(기존): `based_on` id·바이트 해시·필드·계정 범위(4-6-2), `job.inputs` = `account_id`·`cards_sha256`·`card_count`(1-1, 조회 승인과 동일), 서명된 `plan` = `job_plan_fingerprint(..., product_fingerprint, artifact_sha256)`(2-2, 3-3-1). 이전 승인 사슬은 최초 적용에서는 비어 있어야 한다(`supersedes: null`).
- 계획 파일: `--plan`으로 받은 파일을 한 번 읽은 바이트로 고정(`read_plan_file`)하고, 그 바이트의 `artifact_sha256`·제품 지문으로만 지문을 계산한다. 파일의 `db_identity`는 사전 검사가 관측한 DB 식별 지문과, `account_id`·`job_key`·카드 목록(`(kind, ref_id)` 순서)·`config_version`은 요청·승인·현재 엔진 설정과 같아야 한다. 다르면 쓰기 전 거부(4).
- app import는 실제 사전 검사 뒤에만 한다(1-1과 같은 순서).
- 적용 직전 비교: `dry_run` 단계 읽기 연결로 같은 카드 범위의 새 `dry_run` 후보 전체를 만들어 계획 파일에서 복원한 후보(`to_candidates`)와 데이터클래스 전체 동등으로 비교한다. 하나라도 다르면 `plan_changed`로 쓰기 없이 거부하며 계획 파일을 다시 만들거나 덮어쓰지 않는다. 이 비교는 시점 차이를 줄이는 예비 검사이며, 실제 보장은 `apply_plan`의 카드별 잠금 아래 재판정(`conflict`)이다.

#### 4-4-2. "최초 실행"의 원자적 확인 (정적 확인 결과와 필요한 제품 변경)
- `status`의 `not_started`는 실행 행 부재의 증명이 아니다(숨긴 다른 계정 실행, 해석 불가 기록 포함, 4-3).
- 현재 코드(`app/srs/migration.py`): `apply_plan`의 첫 연결은 `begin_card_write`(PostgreSQL: `SELECT id FROM users WHERE id = ? FOR UPDATE`, SQLite: `BEGIN IMMEDIATE`; 이어 `account_write_blocks` 활성 차단 확인) 뒤 `_run_id`를 부른다. `_run_id`는 `run_key`로 행을 찾아, **있으면** 범위·`mode`·설정이 같을 때 그 실행 id를 돌려주고(= 재개), 다르면 `migration_run_conflict`, `aborted`면 `migration_run_closed`; **없으면** `INSERT`(`run_key`는 `UNIQUE`)한다. 첫 연결 블록이 끝날 때 커밋된다.
- 따라서 기존 API만으로는 "첫 적용이 기존 실행에 쓰지 않음"을 보장할 수 없다: 같은 계정·같은 범위의 실행 행이 이미 있으면(앞선 호출이 만든 행, 또는 사전 조회 뒤 다른 프로세스가 만든 행) `apply_plan`은 이를 재개로 처리해 미처리 카드를 쓴다. 다른 범위·손상·다른 계정 행은 `_scope_matches` 불일치로 `migration_run_conflict`가 되어 쓰지 않는다. 같은 계정의 동시 호출은 계정 잠금으로 직렬화되지만, 뒤 호출은 앞 호출의 행을 보고 재개한다. 다른 계정의 같은 키 동시 생성은 `UNIQUE` 제약으로 한쪽 `INSERT`가 실패하고 그 트랜잭션은 롤백된다(쓰기 없음, 결과 코드는 드라이버 오류).
- 필요한 최소 제품 변경(별도 승인 항목 P1): `apply_plan(..., new_run_only=False)` 선택 인자와 `_run_id`의 같은 인자. 참이면 계정 잠금 아래 같은 트랜잭션에서 행이 있으면 어떤 상태든 `SrsWriteError("migration_run_exists")`로 `INSERT` 전에 거부한다. 다른 계정의 동시 생성은 기존 `UNIQUE` 제약이 막는다(이 경우의 고정 코드 분류는 구현 단위에서 정한다). 기본값 거짓이면 기존 동작과 같다. CLI 사전 검사만으로 원자성을 보장한다고 하지 않는다.

#### 4-4-2-1. P1 `new_run_only` 구현 계약 (2026-10-27 고정, 사용자 승인 범위: P1 구현과 합성 SQLite 검증만)
- 서명: `apply_plan(plan, run_key, *, approved=False, batch_size=100, connect=None, new_run_only=False)`. 인자를 생략하거나 `False`면 기존 최초 적용·재개·완료 재호출 동작 그대로다.
- 형식: `type(new_run_only) is bool`만 받는다. 정수·문자열·`None` 등은 변환하지 않고 **연결 전에** `SrsWriteError("invalid_new_run_only", 400)`로 거부한다.
- 확인 위치: 첫 연결에서 기존 `begin_card_write`(계정 잠금: PostgreSQL `users ... FOR UPDATE`, SQLite `BEGIN IMMEDIATE`)를 얻은 **뒤**, 같은 트랜잭션의 `_run_id` 안에서 `run_key` 행을 조회한 직후, 기존 실행 재사용(범위 대조·재개) 전에 확인한다. `True`이고 행이 있으면 상태(`started`·`failed`·`completed`·`aborted`)·소유 계정·범위와 관계없이 `SrsWriteError("migration_run_exists")`(409)로 거부한다. 오류에는 고정 코드만 있고 기존 실행의 상태·계정·커서는 담지 않는다. 거부는 `INSERT`·커서·카드·snapshot·설정·소개 기록 쓰기 전이며, 첫 연결 블록은 예외로 끝나 롤백된다.
- 새 실행(행 없음)은 기존 `INSERT`와 카드별 처리 경로를 그대로 쓴다. 조건은 첫 연결에만 적용하며 같은 호출의 카드·실패 표시·마무리 연결에는 적용하지 않는다(그 연결들은 `_run_id`를 부르지 않는다).
- 사전 조회나 CLI `status`의 `not_started`는 이 잠금 아래 확인을 대신하지 않는다.
- 경합: 같은 계정의 동시 최초 호출은 계정 잠금(SQLite는 DB 전체 쓰기 잠금)으로 직렬화되어, 뒤 호출은 잠금을 얻은 뒤 앞 호출이 만든 행을 보고 `migration_run_exists`로 거부된다. 다른 계정의 같은 키 동시 생성은 PostgreSQL에서 계정 잠금이 서로 다르므로 기존 `run_key UNIQUE` 제약이 한쪽 `INSERT`를 실패시키는 경로이며(이 단위에서 실제 PG 미검증), SQLite에서는 DB 전체 쓰기 잠금 때문에 같은 계정과 같은 직렬화가 일어난다.
- D10(백업 근거)·D11(배치 크기)·D12(`users` 잠금 권한)는 미결 그대로다.

#### 4-4-3. 트랜잭션·결과
- 카드별 커밋·커서·snapshot·잠금 아래 재판정은 기존 `apply_plan`을 그대로 쓴다(전체 원자적 실행 아님, "실패하면 전부 무변경" 아님).
- 첫 호출은 `apply_plan`을 **한 번만** 부른다(자동 반복 없음). 배치 크기는 결정 D11.

| 사례 | 종료 코드 | 출력 | 다음 행동 |
| --- | --- | --- | --- |
| 쓰기 전 거부(승인·서명·계획 파일 불일치·`plan_changed`·`migration_run_exists`·백업 근거 없음·첫 쓰기 연결 거부) | 4 | `phase: before_first_write`, `reason` | 원인 확인, 필요하면 조회부터 |
| 모두 처리·완료 기록 | 0 / 5 | 결과별 건수(`conflict`·`blocked` 있으면 5) | 계정별 사후 검사·전역 감사(7절) |
| 배치 한도로 부분 처리(정상 반환, 커서 < 카드 수) | 3 | `phase: after_start`, 확인된 커서, `next: status` | 재개는 후속 단위(미구현)라고 명시. 자동 반복 없음 |
| 카드 처리 중 실패(예외, 앞 카드 커밋됨) | 1 | `reason`, `confirmed: unknown`, `uncertain: true`, `next: status_required` | `status`로 확인. 재개 미구현 |
| 카드 사이 승인 만료·권한 변경(다음 연결 거부) | 1 | 위와 같음, `reason`은 공급자 코드 | 같음 |
| 카드 사이 30일 창 만료 | 1 | `reason: migration_resume_window_closed` | 같음 |
| 마무리 연결 실패 | 1 | `uncertain: true`, `next: status_required` | `status`가 `cursor_end_not_completed`면 보고만(D7-A) |
| 응답 유실·연결 끊김·시간 초과 | 1 | `reason: result_unconfirmed` | `status`로 확인, 미커밋 추정 금지 |

- 실행이 시작된 뒤의 거부는 쓰기 전 거부(4)로 낮추지 않는다(9-3).

#### 4-4-4. 백업 근거와 최소 권한
- 백업: 최초 적용 전 확인과 재개 시 확인(8절)을 구분한다. 운영 백업 방법은 미결이므로 승인된 것으로 가정하지 않는다. 합성 단계 제안(결정 D10): **서명된 백업 근거 문서**(형식 버전, `db_identity`, `account_id`, `job_key`, 백업 식별자, 백업 시각, 방법 `synthetic`, 근거 바이트 해시)를 승인 서명과 같은 신뢰 경로의 별도 주체 이름공간으로 검증한다. 대상 결속은 `db_identity`·계정·작업 키 일치, 시각은 조회 승인 이후·적용 시각 이전. 단순 "백업 확인됨" 불리언이나 환경 변수는 근거로 받지 않는다.
- 최소 권한(정적 코드 근거, 구현 단위에서 열 목록을 코드로 고정):

| 역할 | 표 | 권한 | 근거 코드 |
| --- | --- | --- | --- |
| 읽기(`dry_run`) | `vocab_items`, `user_word_progress`, `review_logs`, `lexeme_review_logs`, `shared_deck_words`, `user_deck_subscriptions`, `srs_card_identity_flags`, `srs_card_deletions`, `srs_migration_runs`, `srs_migration_snapshots` | SELECT | `inspect_card`·`load_card`·`load_logs`·`_authorized`·`is_identity_unknown`·`_was_converted`·`_latest_rollback_record`·`_id_reused` |
| 쓰기(`apply`) | 위 읽기 표 | SELECT | 잠금 아래 `inspect_card` 재판정 |
| 쓰기 | `users` | SELECT + `FOR UPDATE`에 필요한 UPDATE(최소 열 단위) | `lock_account`(PostgreSQL은 `FOR UPDATE`에 UPDATE 권한 필요) |
| 쓰기(`apply`·`resume`, LQ1 2026-10-29) | `user_deck_subscriptions` | UPDATE(`updated_at`) | 구독 카드 쓰기 접근 판정의 `FOR SHARE`; 제품은 이 표를 UPDATE하지 않지만 역할은 해당 열을 실제 수정할 수 있음 |
| 쓰기(`apply`·`resume`, LQ1 2026-10-29) | `shared_deck_words` | UPDATE(`created_at`) | 같은 접근 경로의 덱 단어 행 `FOR SHARE`; 전역 행의 해당 열을 실제 수정할 수 있다는 대가 포함 |
| 쓰기 | `account_write_blocks` | SELECT | `active_block` |
| 쓰기 | `vocab_items`, `user_word_progress` | UPDATE(열 단위: `srs_*` 상태·엔진·설정·참여·사유·품질·플래그·유효 마감, `srs_card_version`, `history_intro_status`, `history_intro_known_by`) | `update_card`, `record_intro`, `load_card(for_update=True)` |
| 쓰기 | `srs_migration_runs` | SELECT, INSERT, UPDATE(`summary_json`, `status`, `finished_at`) (시퀀스 USAGE 없음, 2026-10-27 S1) | `_run_id`, 커서·실패·완료 표시 |
| 쓰기 | `srs_migration_snapshots` | SELECT, INSERT (시퀀스 USAGE 없음, 2026-10-27 S1) | snapshot 기록 |
| 쓰기 | `srs_config_versions` | SELECT, INSERT | `ensure_config` |

- (2026-10-27 S1 승인·S2 반영) 두 실행 표의 시퀀스 USAGE를 계약에서 뺐다(`srs_migrate.WRITE_PRIVILEGES`의 두 튜플만 제거, `OPS_APPLY_SEQUENCE_PRIVILEGE_PLAN.md`). 두 `id`는 identity 기본값으로 채워지고 최초 `apply` 경로에는 시퀀스 함수 호출이 없다. 객체 목록에는 두 시퀀스가 그대로 있다. 실제 PG 재확인(S3)은 승인 전이다.

- 관측된 권한을 그대로 기대 프로필로 채택하지 않고, 위 표로 기대 프로필을 먼저 정한 뒤 관측과 대조한다(기존 공급자 규칙: 초과·부족 모두 거부). 부족을 넓은 GRANT로 메우지 않는다. `users`의 `FOR UPDATE`용 UPDATE 권한 범위는 결정 D12.
- (2026-10-29 LQ1 합성 구현) 추가한 두 열 권한과 대기 상한·오류 처리는 `OPS_MIGRATION_RESUME_LEXEME_RACE_PLAN.md` 11절을 따른다. 읽기 프로필·객체 목록·프로필 알고리즘은 그대로이며 쓰기 지문 값은 바뀐다. 이 새 계약의 실제 PG 권한·구문·경합 검증과 GRANT·배포는 미승인이다. 과거 실제 PG 결과에 소급하지 않는다.

#### 4-4-5. 결정 필요 (승인 아님)

| 결정 | 선택지 | 권장안 | 대가 |
| --- | --- | --- | --- |
| P1 최초 실행 보장 | (A) 제품 `new_run_only` 인자(4-4-2) / (B) CLI 사전 조회만 / (C) 별도 예약 표 | A | A는 제품 변경(기본값이면 동작 동일). B는 경합에서 기존 실행에 씀. C는 스키마 변경 |
| D10 백업 근거 | (A) 서명된 별도 근거 문서 / (B) 적용 승인에 백업 필드 추가(형식 버전 3) / (C) 운영 방법 결정 전까지 합성에서도 생략 | A | A는 새 서명 주체·검증 코드. B는 승인 형식 변경. C는 근거 없이 적용 |
| D11 첫 호출 배치 | (A) 카드 수 전체(최대 2000)를 한 번에 / (B) 제품 기본 100 / (C) 명시 인자 필수(상한 2000) | C | A는 호출이 길어짐(카드별 커밋이라 잠금은 짧음). B는 큰 범위가 부분 처리로 끝남. C는 운영자 입력이 늘어남 |
| D12 `users` 잠금 권한 | (A) 열 단위 UPDATE 한 열 / (B) 잠금 전용 함수(보안 정의자) / (C) 잠금 표 분리 | A(갱신 영향이 없는 열 선택 검토) | A도 그 열 UPDATE는 가능해짐. B·C는 스키마·제품 변경 |

#### 4-4-6. 다음 승인 단위 (각각 따로)
1. 이 계약 검토.
2. 제품 변경 P1(`new_run_only`)과 그 회귀(합성 SQLite).
3. 최초 `apply` 합성 구현: `TOOLS` 적용 단계, 쓰기 프로필, 백업 근거(D10), CLI `apply`, 검사 — 승인·계획 파일 불일치 무쓰기, `plan_changed` 무쓰기, 첫 실행 경합(같은 계정 재호출·다른 계정 같은 키), 중간 실패의 부분 커밋, 마무리 실패, 결과 미확정, 배치 부분 처리 보고, 다른 계정 불변.
4. 실제 로컬 PG 준비·검증(역할 읽기·쓰기 분리, 잠금 권한, R2 정리), 별도 계획.
5. 운영 적용(11절 차단 조건 해소 뒤).

#### 4-4-7. D10~D12 계약 보완 (2026-10-27 작성, 문서만, 계약 검토 대기)
각 항목은 **[코드 확인]**(정적 읽기로 확인한 현재 코드 사실), **[제안]**(승인 전 정책안), **[미검증]**으로 구분한다. 어떤 제안도 승인된 것이 아니다.

##### D10. 백업 근거 문서
- [코드 확인] 서명 주체는 `_ops_approval.SUBJECTS = ("approval", "manifest")`뿐이고, `signature_namespace(purpose, subject)`는 그 밖의 주체를 `signature_namespace_invalid`로 거부한다. `_ops_signature.NAMESPACES`와 `SyntheticOpenSSHVerifier.verify`도 합성 `approval`·`manifest` 이름공간만 받는다. 따라서 **현재 코드로는 별도 백업 근거 문서를 서명 검증할 수 없다.**
- [제안·별도 변경 항목 C10] 서명 주체 `backup`을 추가한다(`SUBJECTS`, `NAMESPACES`, 합성 검증기 허용 목록 각 1항목, 이름공간 `jp-vocab-ops/v1/synthetic/backup`). 이 단위에서는 구현하지 않는다. 승인 형식(버전 2)은 바꾸지 않는다.
- [제안] 최소 필드(엄격 JSON, 중복 키·소수 금지, 정확히 이 키): `format`(`jp-vocab-ops/backup-evidence`), `format_version`(1), `evidence_id`(승인 id 형식), `purpose`(`synthetic`), `db_identity`, `account_id`, `job_key`, `backup_id`(`[A-Za-z0-9_.:-]{1,128}`), `taken_at`(UTC 초 단위), `method`(합성에서는 `synthetic`만), `artifact_sha256`(백업 산출물 바이트의 SHA-256, 소문자 16진수 64자), `valid_until`(UTC), `attested_by`(서명자 표시 문자열), `restore_verified`(불리언, 합성에서는 반드시 `false`).
- [제안] 검증 절차와 차단 단계(모두 **사전 검사 승인 단계, 연결 전**): ① 형식·필드 ② 서명(`backup` 주체, 승인과 같은 신뢰 목록·폐기 목록, 지금 시각 기준) ③ `purpose`가 실행 모드와 같음 ④ `db_identity`·`account_id`·`job_key`가 적용 승인·계획 파일과 같음(다르면 `backup_evidence_target_mismatch`·`_job_mismatch`) ⑤ `taken_at`은 근거 조회 승인의 `valid_from` 이후이며 지금 이전, `valid_until`은 지금 이후(아니면 `backup_evidence_expired`·`_too_old`) ⑥ 근거 바이트의 SHA-256을 실행 기록에 남김. 근거가 없거나 하나라도 실패하면 첫 쓰기 연결을 열지 않는다(쓰기 전 거부 4). 재개 시 확인(8절)은 같은 근거의 `valid_until`을 다시 확인하는 별도 단계로, 재개 단위에서 정한다.
- [제안] 의미 구분: 서명은 "서명자가 이 내용의 백업을 확인했다고 진술했다"는 증명일 뿐이다. 산출물 해시 일치는 이 도구가 산출물을 직접 읽을 수 있을 때만 확인할 수 있으며(합성에서는 시험이 만든 파일), 그때도 "그 바이트가 있다"는 뜻뿐이다. **복원 가능성**은 서명이나 해시로 판정하지 않으며, 실제 복원 리허설(4단위)의 별도 증거가 필요하다. 이 단위의 `restore_verified`는 언제나 `false`로 두고 출력에 그대로 표시한다.
- [제안] 대체 금지: 불리언 인자, 환경 변수, 서명 없는 로컬 기록·파일 존재만으로는 근거로 받지 않는다.
- [미검증·운영 미충족] 운영 백업 방법(Neon 분기·시점 복구 / `pg_dump`)이 미결이므로 운영용 `method` 값, 산출물 식별 방식, 보존 기간, 서명자 권한, 산출물 접근 방법이 정해지지 않았다. 운영 모드에서는 근거를 받을 수 없어 운영 `apply`는 계속 거부 상태다.

- [제안·D10 보정 1차, 2026-10-27] 만료 재확인: 근거는 처음 읽은 바이트를 고정해 재사용하되, **최초 쓰기 연결을 요청하기 직전**에 그 순간의 현재 시각으로 유효성을 다시 확인한다(최초 검사 시각을 재사용하지 않음). 유효 조건은 `taken_at <= now < valid_until`이며 `now == valid_until`은 만료다. 최초 검사 뒤 `dry_run` 비교 중 만료되면 쓰기 연결 없이 `backup_evidence_expired`(쓰기 전 거부 4)로 끝난다. 재확인 함수는 C10에서 구현·검사하고, CLI 호출 지점 연결은 C11에서 한다.

###### C10 백업 근거 검증 함수 계약 (2026-10-27 고정, 합성 구현 범위)
- 위치: 새 모듈 `backend/scripts/_ops_backup_evidence.py`. DB 연결·제품 import·파일 읽기를 하지 않는다. 입력은 호출자가 고정한 근거 바이트, 서명 바이트, 기대값(`db_identity`, `account_id`, `job_key`, 기준 시각 = 근거 조회 승인의 `valid_from`), 신뢰 입력(허용 서명자·폐기 목록·주체 이름), 현재 시각(시간대 있는 값, 인자로 주입).
- 서명: 공통 서명 주체에 `backup`을 추가한다(`_ops_approval.SUBJECTS`, `_ops_signature.NAMESPACES`, 합성 검증기 허용 이름공간). 합성 이름공간은 `jp-vocab-ops/v1/synthetic/backup`. 운영 검증기와 기본 실행 진입점은 그대로 거부한다. 기존 `approval`·`manifest` 서명·지문·승인 형식은 바꾸지 않는다.
- 상한: 근거 바이트 1~16 KiB, UTF-8(BOM 없음), JSON 최상위 객체 하나에 값은 모두 스칼라(중첩 깊이 1; 배열·객체 값은 거부), 중복 키·소수·`NaN`·`Infinity` 거부. 서명은 기존 서명 검사 상한.
- 필드(정확히 14개, 형식 버전 1): `format` = `"jp-vocab-ops/backup-evidence"`, `format_version` = 정수 1, `evidence_id`(승인 id 형식), `purpose`(`synthetic`; 실행 모드와 같아야 함), `db_identity`(소문자 16진수 64자), `account_id`(1 이상 정수), `job_key`(`run_key` 형식), `backup_id`(`[A-Za-z0-9_.:-]{1,128}`), `taken_at`·`valid_until`(`YYYY-MM-DDTHH:MM:SSZ`), `method`(합성에서는 `synthetic`만), `artifact_sha256`(백업 산출물의 SHA-256 진술, 소문자 16진수 64자), `attested_by`(출력 가능한 ASCII 1~128자), `restore_verified`(불리언, `false`만 허용).
- 검증 순서와 고정 코드: 형식(`backup_evidence_format_invalid`·`_fields_invalid`·`_version_unsupported`·`_value_invalid`) → 서명(`backup_signature_invalid`, 운영·다른 주체 이름공간·다른 키·폐기 키·변조 모두 같은 코드) → 모드(`backup_evidence_purpose_mismatch`) → 대상(`_target_mismatch`)·계정(`_account_mismatch`)·작업 키(`_job_mismatch`) → 복원 주장(`_restore_claim_invalid`) → 시각(`taken_at > now`면 `_from_future`, `taken_at < 기준 시각`이면 `_too_old`, `valid_until <= taken_at`이면 `_value_invalid`, `now >= valid_until`이면 `_expired`). 거부에는 고정 코드만 담고 원값·비밀값·예외 연쇄를 담지 않는다.
- 결과: 고정 바이트, 근거 문서 해시(`evidence_sha256` = 근거 바이트의 SHA-256), 진술된 산출물 해시(`artifact_sha256_claimed`), 각 필드. `artifact_checked`는 항상 `false`다(이 함수는 산출물을 읽지 않으므로 존재·해시 일치를 확인했다고 표시하지 않는다). `attested_by`는 서명된 표시 문자열일 뿐이며 실제로 검증된 서명자 신원(허용 서명자 목록의 주체)을 대신하지 않는다. 서명 통과는 복원 가능성을 뜻하지 않는다.
- 재확인: `recheck(evidence, now)`는 고정 바이트를 다시 해석해 `taken_at <= now < valid_until`만 확인한다(서명·대상은 최초 검증 결과를 그대로 쓴다).
- 입력 검사(2026-10-27 검토 보정): 기대값은 비교·변환·서명 검사 **전에** 모두 검사한다. `account_id`는 `type is int`이고 1~2^63-1(불리언·실수·문자열 불가, `7.0`은 `7`이 아님), `db_identity`·`job_key`는 근거 문서와 같은 형식, `basis_from`은 시간대가 있고 UTC로 변환 가능해야 하며, 아니면 `backup_evidence_expected_invalid`(서명 검증기 미생성). `now`(검증·재확인 모두)는 시간대가 있고 UTC로 변환 가능해야 하며 아니면 `backup_evidence_time_input_invalid`. 표현 범위를 벗어나는 변환(예: `datetime(1, 1, 1, tzinfo=+01:00)`)은 `OverflowError`·`ValueError`만 좁게 잡아 같은 고정 코드로 거부한다. 정상화·숫자 자동 변환은 하지 않는다.
- 완료 범위 밖: 근거 파일 읽기, 산출물 읽기·해시 대조, CLI 통합(C11), 운영 방식.

##### D11. 첫 호출 배치 크기
- [코드 확인] 승인 단계는 `args`(이름 `[a-z_][a-z0-9_]{0,62}` → 값 `[A-Za-z0-9_.:-]{1,128}` 문자열)를 가질 수 있고, `authorize_command`는 실행 인자를 단계의 `args`와 **정확히** 비교한다(`command_args_not_approved`). `job` 일치 규칙(조회·적용 승인 간 `job` 동일, 4-6-2)은 `args`를 보지 않는다.
- [제안] CLI `apply`는 `--batch-size`를 필수로 받는다(기본값 없음). 형식은 10진 정수 1~2000이며 앞의 `0`·부호·공백·불리언 변환 없음(argparse 정수 변환 뒤 `type is int`와 범위 확인, 문자열 원문이 정규형 `str(n)`과 다르면 사용법 오류 2). 서명된 적용 승인의 `apply` 단계는 `args: {"batch_size": "<n>"}`를 가져야 하고, 실행 인자 `{"batch_size": str(n)}`가 그와 정확히 같아야 한다(사전 검사·연결 후 재판정 모두). `dry_run` 단계에는 `args`를 두지 않는다. 배치 크기는 `job.inputs`에 넣지 않으므로 조회·적용 승인의 `job` 일치 규칙과 충돌하지 않는다.
- [제안] `apply_plan`은 그 값으로 **한 번만** 호출한다. 커서가 카드 수보다 작게 끝나면 종료 코드 3과 `next: status`, `resume: not_implemented`를 출력하며, 자동 재호출·새 승인·새 작업을 만들지 않는다.
- [제안] 상한 2000은 계획 파일 후보 상한(2-3)과 맞춘 입력 상한일 뿐이며 운영 성능·안전성 검증 결과가 아니다.

##### D12. `users` 잠금 권한
- [코드 확인] 계정 잠금 문장은 `lock_account`의 `SELECT id FROM users WHERE id = ? FOR UPDATE`(PostgreSQL)뿐이다. PostgreSQL 문서상 `FOR UPDATE`는 조회한 열의 SELECT 권한과, 그 표의 **적어도 한 열**에 대한 UPDATE 권한을 요구한다. 관측기는 열 권한을 `has_column_privilege`로 모아 `(종류, 스키마, 표, 열, 권한)` 항목으로 표현하고, 공급자는 기대 프로필보다 많거나 적은 권한을 `observed_privileges_excess`·`_missing`으로 거부한다.
- [제안] 대상 열은 `users.updated_at` 하나. 제안 GRANT(쓰기 역할 이름은 구현 단위에서 고정): `GRANT SELECT (id), UPDATE (updated_at) ON public.users TO <apply_write_role>;` 표 전체 UPDATE, 소유, 관리 권한은 제안하지 않는다.
- [제안] 대가: 열 단위 UPDATE도 잠금 전용 권한이 아니다. 이 역할은 모든 계정의 `updated_at` 값을 실제로 바꿀 수 있다(도구 코드는 쓰지 않음). `email`·`password_hash`·`display_name`·`auth_provider`·`id`·`created_at`보다 영향이 작아 골랐을 뿐이며 무해하다는 뜻은 아니다. 더 좁히려면 잠금 전용 함수(보안 정의자)나 잠금 표 분리 같은 스키마·제품 변경이 필요하다(별도 결정).
- [제안] 기대 프로필에 `("table", "public", "users", "id", "SELECT")`와 `("table", "public", "users", "updated_at", "UPDATE")`만 넣는다. 관측에 표 단위 UPDATE나 다른 열 UPDATE가 있으면 기존 규칙대로 `observed_privileges_excess`로 연결을 거부한다.
- [미검증] 실제 PostgreSQL에서 이 권한으로 `FOR UPDATE`가 성공하는지, 초과 권한이 관측·거부되는지는 후속 실제 로컬 PG 단위에서 확인한다. 가짜 관측 검사로는 증명하지 않는다.

##### 최초 `apply` 흐름 (세 결정의 전달)

| 단계 | 연결 | D10 백업 근거 | D11 배치 크기 | D12 잠금 권한 | 실패 시 |
| --- | --- | --- | --- | --- | --- |
| 입력 검사 | 없음 | 근거 파일 바이트를 한 번 읽어 고정 | `--batch-size` 필수·정수·범위·정규형 | - | 사용법 2 |
| 사전 검사(적용 승인·`based_on`·계획 파일·근거 서명) | 없음 | ①~⑥ 검증 | `apply` 단계 `args.batch_size`와 정확히 일치 | 쓰기 단계 기대 프로필에 열 권한 2개 | 쓰기 전 거부 4 |
| 적용 직전 비교(`dry_run` 단계 읽기 연결) | 읽기 1 | 재사용(다시 읽지 않음) | - | - | `plan_changed` 쓰기 전 거부 4 |
| 첫 쓰기 연결(`apply` 단계, 공급자 재판정) | 쓰기 | 사전 검사 결과 재사용, 시각 재확인은 하지 않음(제안) | 연결 후 재판정에도 같은 `args` | 관측 열 권한이 기대 프로필과 같아야 함(초과·부족 거부) | 첫 연결 거부는 쓰기 전 4, `migration_run_exists`(P1)도 4 |
| `apply_plan` 1회(카드별 연결) | 쓰기 반복 | - | 그 값으로 1회 | 매 연결 재판정 | 시작 후 실패·만료·마무리 실패·미확정은 1, 부분 처리는 3(재개 미구현) |

- 쓰기 전 거부(4)와 실행 시작 후 실패(1)·부분 커밋·결과 미확정은 9-1~9-3 규칙 그대로 구분한다. P1 검토 결과, 제품 지문, 재개 정책은 바꾸지 않는다.

##### 추가 승인이 필요한 항목
- C10: 서명 주체 `backup` 추가(공통 서명 모듈 변경).
- C11: `TOOLS`에 `srs_migrate.apply: write` 추가와 CLI `apply`의 `--batch-size`·근거 인자.
- C12: 실제 로컬 PG에서 D12 권한 충분성·초과 권한 거부 확인(별도 계획·승인).

#### 4-4-8. C11 최초 `apply` CLI 합성 구현 계약 (2026-10-27 고정, 사용자 승인 범위: 합성 구현)
- 구현 상태(2026-10-27, 합성): `backend/scripts/srs_migrate.py`의 `run_apply`·`contract_profiles`·`batch_from_text`, `TOOLS` `srs_migrate.apply: write`. 실제 PG(C12)·운영 활성화·재개는 미구현.
- 범위: 실행 기록이 없는 작업의 첫 적용만. 재개·완료 재호출·상태 보정·자동 반복·재시도는 없다. 실제 PG(C12)와 운영 활성화는 범위 밖. D11은 명시 배치 크기 1~2000, D12는 `users`의 `SELECT(id)`·`UPDATE(updated_at)`를 기대 프로필에 표현하는 범위만(실제 GRANT 없음).
- `TOOLS`: `srs_migrate: {dry_run: read, status: read, apply: write}`. `dry-run`·`status`는 계속 조회 승인(`inquiry`)만 받는다.
- 입력(Python 합성 주입 `run_apply`): 요청(계정·작업 키·카드), 배치 크기 `n`, 쓰기 단계 사전 검사 입력(`command = apply`, `args = {"batch_size": str(n)}`), 읽기 단계 사전 검사 입력(`command = dry_run`, `args = {}`), 두 입력은 승인·근거 조회 승인·manifest·대상·계정·작업 키·작업 입력·제품 지문·`artifact_sha256`·신뢰 입력이 같아야 하고 이전 승인 사슬은 비어 있어야 한다, 계획 파일 경로, 백업 근거·서명 경로, 프로필 범위(관측 대상 목록·`search_path`·TLS 버전: 환경 사실), 드라이버, 시계(`now()` 호출 가능 값). 명령줄 `apply`는 `--batch-size`(ASCII 정규형 `[1-9][0-9]{0,3}`, 2000 이하)·`--plan`·`--backup-evidence`·`--backup-signature`가 필수이며, 실제 연결 경로가 없어 `connection_not_available`(4)로 끝난다.
- 기대 프로필: 권한은 코드에 고정한 계약 표(4-4-4, `srs_migrate.READ_PRIVILEGES`·`WRITE_PRIVILEGES`)로만 만든다. 관측 결과를 기대 권한으로 쓰지 않는다. `users`는 쓰기 프로필에서 열 단위 `SELECT(id)`·`UPDATE(updated_at)`뿐이며 표 단위 UPDATE는 넣지 않는다. 관측 대상 목록·`search_path`·TLS는 호출자가 주는 환경 사실이다.
- 검사 순서(앞 단계 실패 시 뒤는 하지 않음):

| 단계 | 내용 | 실패 |
| --- | --- | --- |
| 1 입력 | 요청·배치 크기(`type is int`, 1~2000)·두 사전 검사 입력의 명령·인자·공유 필드·작업 입력·이전 승인 사슬 없음 | 4 `request_mismatch` 등 |
| 2 고정 읽기 | 계획 파일(`read_plan_file`, 8 MiB), 백업 근거(16 KiB)·서명(64 KiB)을 한 번씩 읽어 고정 | 4 `plan_file_*`·`backup_evidence_unreadable`·`backup_signature_unreadable` |
| 3 계획·요청 대조 | 계획 파일의 계정·작업 키·카드 목록 = 요청, `artifact_sha256`·제품 지문 = 두 사전 검사 입력 | 4 `plan_file_request_mismatch` |
| 4 사전 검사 | 앱 환경 고정 뒤 쓰기·읽기 입력 각각 실제 사전 검사(서명·manifest·대상·단계·역할·프로필·계정·작업 입력·`args`·작업 계획 지문) | 4 `preflight_*` |
| 5 승인 형태 | 검증된 승인 `tool = srs_migrate`, `kind = apply`, `supersedes = null`, 근거 조회 승인 `srs_migrate`·`inquiry`, 쓰기 결과 `apply`·쓰기, 읽기 결과 `dry_run`·읽기, 두 결과가 같은 승인 바이트 | 4 `approval_*` |
| 6 계획 대상 | 계획 파일 `db_identity` = 사전 검사가 관측한 DB 식별 지문 | 4 `plan_file_target_mismatch` |
| 7 백업 근거 | C10 `verify_backup_evidence`: 기대값은 검증된 승인(계정·작업 키·근거 조회 승인 `valid_from`)과 관측 DB 식별에서만 만든다 | 4 `backup_*` |
| 8 app import | 위를 모두 통과한 뒤에만 | 1 `product_import_failed` |
| 9 계획 복원 | 설정 = 현재 엔진, `to_candidates`(제품 지문·범위 계약) | 4 `plan_file_*` |
| 10 적용 직전 비교 | 읽기 단계 연결로 새 `dry_run` 후보 전체 = 계획 후보 | 4 `plan_changed`(쓰기 연결 0회), 연결 거부 4/실패 1 |
| 11 근거 재확인 | 최초 쓰기 연결 요청 직전 그 순간의 시각으로 `recheck` | 4 `backup_evidence_expired`(쓰기 연결 0회) |
| 12 적용 | 쓰기 단계 `ProductConnector`로 `apply_plan(계획 후보, run_key, approved=True, batch_size=n, connect=..., new_run_only=True)` **정확히 한 번** | 아래 결과 표 |

- 결과(9-1~9-3, 4-4-3):

| 결과 | 판정 근거 | 종료 코드 | 출력 |
| --- | --- | --- | --- |
| 완료 | 정상 반환, 결과 수 = 카드 수 | 0, `conflict`·`blocked`가 있으면 5 | `phase: completed`, `cursor`, 결과별 건수 |
| 배치 부분 처리 | 정상 반환, 결과 수 < 카드 수 | 3 | `phase: partial`, `cursor`, `resume: not_implemented`, `next: status` |
| 쓰기 전 거부 | 첫 쓰기 연결이 커밋 없이 끝났고 제품 고정 거부(`SrsWriteError`, 예: P1 `migration_run_exists`) 또는 첫 연결 자체가 공급자에서 거부 | 4(연결 실패 성격은 1) | `phase: before_first_write`, `code`, `changes: none` |
| 실행 시작 후 실패 | 첫 쓰기 연결이 커밋된 뒤의 예외(카드 처리 실패·다음 연결 거부·30일 창·마무리 실패) | 1 | `phase: after_start`, `code`, `confirmed: unknown`, `uncertain: true`, `next: status_required` |
| 결과 미확정 | 첫 연결 커밋 단계 자체의 실패, 첫 연결 안의 고정 거부가 아닌 예외 | 1 | 위와 같음(`phase`는 커밋 확인 여부로) |

- 판정 시각(2026-10-27 검토 보정): 승인·서명·만료 판정의 현재 시각은 `run_apply`의 시계(`clock`)다. `PreflightInput.now`는 허가 근거로 쓰지 않는다. 고정 바이트(승인·서명·manifest·계획 파일·근거)는 그대로 두고 `now`만 그 순간의 시계 값으로 바꾼 입력으로 기존 검사 경로 전체를 실행한다: 초기 사전 검사 1회(쓰기·읽기 입력 같은 시각), 백업 근거 최초 검사, **읽기·쓰기 연결 요청마다**(최초·카드별·실패 표시·마무리 연결 모두; 공급자의 사전 검사와 연결 후 재판정이 그 요청의 시각을 받음), 최초 쓰기 직전 근거 `recheck`. 시계 값이 시간대 없거나 UTC로 변환할 수 없으면 `clock_invalid`. 최초 쓰기 연결 전 승인 만료는 쓰기 연결 없이 4, 실행 시작 뒤 다음 연결에서 만료되면 1·`uncertain`·`status_required`(이미 커밋된 카드 유지, 자동 재시도 없음). 제품 트랜잭션 경계와 만료된 과거 근거 승인의 취급(4-6-2)은 바꾸지 않는다.
- 인자 형식(검토 보정): 쓰기·읽기 입력의 `args`는 변환 전에 `dict`이며 키는 승인 인자 이름 형식, 값은 승인 인자 값 형식의 문자열이어야 하고, 쓰기는 정확히 `{"batch_size": str(n)}`, 읽기는 `{}`여야 한다. 어긋나면 `args_invalid`(4)로 app import·연결·제품 실행 전에 거부한다.
- 근거 결속(2026-10-28, `OPS_MIGRATION_RESUME_PLAN.md` 9-3): 실제 사전 검사가 검증한 적용 승인이 형식 v3의 `backup_evidence`를 가지면 단계 5 뒤에 고정한 근거 원문의 SHA-256과 대조하고, 다르면 `backup_evidence_binding_mismatch`(4, app import·연결 전). 같아도 단계 7 C10 검증은 그대로 한다. 필드가 없는 승인은 기존 동작이며 근거가 결속된 실행으로 취급하지 않는다.
- 앞 카드가 커밋됐을 수 있는 실패를 "변경 없음"으로 보고하지 않는다. 확인하지 못한 커서·커밋 범위는 추정하지 않고 `status_required`로 안내한다. `KeyboardInterrupt`·`SystemExit`는 잡지 않고 기존 연결 정리 계약대로 전파한다.
- 출력에는 고정 필드만(계획 파일 해시·근거 문서 해시·`restore_verified: false`·`backup_artifact_checked: false` 포함). 후보 JSON·카드 키·근거 원문·경로·연결 비밀·드라이버 원문은 출력하지 않는다.

## 5. 재개 승인과 이전 승인 전달

### 5-1. 현재
- 적용 승인 유효 기간은 최대 24시간, 재개 창은 최초 `started_at`부터 30일이다. 긴 재개는 새 적용 승인이 필요하다(D3-B, 권장).
- 새 적용 승인은 같은 종류 이전 승인을 `supersedes`로 가리켜야 하는데(4-6-4), 사전 검사가 `prior`를 넘기지 않아 **지금은 거부된다**(0절).

### 5-2. 필요한 전달·검증 경로 (공통 모듈 변경, 별도 구현 단위)
1. `PreflightInput`에 이전 승인 사슬 필드를 추가한다: 이 작업의 **첫 적용 승인부터 직전 적용 승인까지** 각 승인의 바이트와 서명(그리고 각자의 `based_on` 조회 승인 바이트·서명). 호출자는 바이트와 서명만 넣는다. `Approval` 객체나 "검증 완료" 표시는 입력으로 받지 않는다.
2. 사전 검사는 사슬의 승인마다 서명을 검증한다(`verify_signed`; 유효 기간은 검사하지 않음 — 근거로만 쓰고 실행 허가로 쓰지 않는다). 첫 승인의 `supersedes`는 비어 있어야 하고, 이후 각 승인의 `supersedes`는 바로 앞 승인을 가리켜야 하며(D8-B면 id와 바이트 해시 모두), 모두 같은 종류·도구·용도·작업 키여야 한다(`check_succession`을 연쇄 적용).
3. 지금 승인은 `prior` = 사슬의 마지막 승인으로 `authorize_command`에 넘긴다. 연결 후 재판정 전달은 5-4.
4. `supersedes` 형식은 D8. 구현 상태(2026-10-25, 사용자 승인 범위: D8-B 형식 버전 2와 호환 규칙만, 합성): 계약 4-6-5절, `_ops_approval`만 변경. 1~3(사슬 전달·연쇄 검증)은 2026-10-26 사용자 승인으로 적용 승인 사슬에 한해 합성 구현했다(계약 4-6-6절, 5-4절의 연결 후 재판정 포함). 조회 승인 대체 사슬은 별도 범위이며, 제시한 사슬이 최신임은 증명하지 않는다.
- 금지: 로컬 실행 기록에 남은 이전 승인 id·해시를 서명 승인 대신 근거로 쓰는 것, 사슬의 여러 승인 권한(명령·역할·계정)을 합치는 것. 각 명령은 지금 제시된 적용 승인 1건(과 그 `based_on`)만으로 판정한다(4-6-4).
- "직전 승인이 정말 마지막인가"는 서명만으로 증명할 수 없다(더 나중 승인을 숨길 수 있음). 이 한계는 쓰기 권한을 넓히지 않는다(지금 승인만 권한을 준다)는 점에서만 허용하며, 실행 기록 위치가 정해지면 대조 보조로 쓴다.

### 5-3. 최초 조회 승인 만료 뒤의 재개 (기존 계약과 대조)
- 재개용 새 적용 승인의 `based_on`은 **최초 조회 승인**이다. 계획 파일과 작업 계획 지문이 그 조회에서 나왔기 때문이다. 근거 조회 승인의 유효 기간이 지나 있어도 된다(4-6-2: 근거로만 쓴다).
- 결과 미확정·만료 뒤의 `status`(4-6-3)는 기존 작업 키에 묶인 **새 조회 승인**으로 한다. 그 조회는 읽기만 하며 새 계획 지문을 만들지 않고(새 dry-run 계획은 이미 커밋된 카드 때문에 다름), 재개 적용 승인의 `based_on`이 되지 않는다. 결과 확정(9-2: 종료 코드만으로 미커밋 추정 안 함)은 그대로다.
- 식별 갱신(복원 등)으로 DB 식별 지문이 바뀌었거나 최초 조회 승인의 서명 키가 폐기돼 검증되지 않으면, 별도 절차(D9-B)가 마련될 때까지 **자동 재개도 새 작업 전환도 하지 않고** 거부·보고만 한다.

### 5-4. 연결 후 재판정까지의 전달 (공급자 경로)
- 원칙: 연결·재연결(공급자 새 호출)마다 **현재 승인**과 그 연결의 **실제 관측값**으로 다시 판정한다. 시각은 그 호출의 `now`다. 앞 연결의 판정 결과를 재사용하지 않는다.
- 전달 값: `artifact_sha256`(계획 파일 지문)과 이전 승인 사슬 바이트·서명은 `PreflightInput` 필드로만 들어간다. 사전 검사와 연결 후 재판정은 같은 입력 객체에서 같은 값을 읽는다.
- 서명 검증된 값만 쓰기: 사전 검사(`run_synthetic_preflight`)가 지금 승인·`based_on` 조회 승인·이전 승인 사슬의 서명을 검증하고, 그 결과 객체(`SyntheticPreflightMatched` 또는 공급자 내부 전용 반환값)에 **검증된 `Approval`들**을 담아 돌려준다. 공급자는 연결 후 `authorize_command`에 이 검증된 객체들(`approval`, `inquiry`, `prior`)과 `artifact_sha256`을 넘긴다. 현행처럼 입력 바이트를 `parse_approval`로 다시 해석하는 방식은 같은 바이트이긴 하나, 이전 승인 사슬까지 늘어나면 검증과 사용의 대응이 흐려지므로 검증 결과를 직접 넘기는 쪽으로 바꾼다. 호출자가 넣은 `Approval` 객체·검증 표시는 어느 단계에서도 받지 않는다.
- 공급자 변경 목록(공통 모듈, 별도 단위): `_ops_preflight.PreflightInput`(`artifact_sha256`, 이전 승인 사슬), `run_synthetic_preflight`(사슬 검증, 검증된 승인 반환, 두 값을 `authorize_command`에 전달), `_ops_provider.provide_synthetic_connection`(검증된 승인 사용, 연결 후 `authorize_command`에 `prior`·`artifact_sha256` 전달), `_ops_adapter.provide_with_adapter`(입력 그대로 전달 확인), `_ops_approval.job_plan_fingerprint`·`authorize_command`(`artifact_sha256`).
- 공급자 거부 코드는 기존처럼 `preflight_*`(사전 검사), `observed_*`(연결 후 재판정)로 구분된다. CLI는 이 코드를 그대로 고정 사유로 기록한다.

## 6. 연결 공급자 주입

- 현재 `dry_run`·`apply_plan`은 모듈의 `get_connection`을 직접 부른다.
- 최소 변경 지점(제품 변경, 결정 D1-A): `dry_run(keys, *, connect=None)`·`apply_plan(..., connect=None)`. 함수 안에서 연결이 필요할 때마다 `factory = get_connection if connect is None else connect`로 고른다(호출 시점 선택이라 기존 테스트의 모듈 교체도 그대로 동작). `connect`는 `read_only` 키워드를 받아 컨텍스트 관리자 연결을 돌려주는 함수다. `None`이면 동작은 지금과 같다. 판정·쓰기 코드는 바꾸지 않는다.
- CLI는 공급자를 감싼 함수를 넘기고, 공급자는 **연결마다** 대상·연결·권한 확인(계약 7절)을 다시 한다. 연결 수·각 확인 결과는 실행 기록에 남긴다. 전환 쓰기 역할 프로필과 `TOOLS` 항목은 새로 정해야 한다(쓰기 프로필은 카드 표, `srs_migration_runs`·`srs_migration_snapshots`, `history_intro_*` 열, `ensure_config` 대상 표).

### 6-1. 연결 주입 계약 (2026-10-26 고정, D1-A 사용자 승인 범위)
- 구현 상태(2026-10-26, 합성 SQLite 검증): `app/srs/migration.py`의 `_connector`와 두 함수의 연결 5곳(읽기 1, 시작·카드·실패 표시·마무리 4). 전환 CLI·공급자 결합·계획 파일 처리는 미구현.
- 서명: `dry_run(keys, *, connect=None)`, `apply_plan(plan, run_key, *, approved=False, batch_size=100, connect=None)`. `rollback_plan` 등 다른 함수는 이 단위에서 바꾸지 않는다.
- `connect`가 `None`이면 연결이 필요할 때마다 **그 시점의** 모듈 전역 `get_connection`을 쓴다(인자를 생략한 기존 호출과 시험의 `get_connection` 교체가 그대로 동작). `None`도 호출 가능도 아니면 `invalid_connection_factory`(400)로 연결 전에 거부한다.
- 주입 함수 계약: 키워드 `read_only`(불리언)를 받아 연결 컨텍스트 관리자를 돌려준다. 제품은 `dry_run`에서 `read_only=True` 한 번, `apply_plan`에서 시작·카드마다·실패 표시·마무리 연결을 모두 `read_only=False`로 이 함수에서 얻는다. 기본 경로와 같은 인자다(`get_connection()`은 `read_only=False`).
- 커밋·롤백·닫기 책임은 기존과 같다: `with` 블록 정상 종료가 커밋, 예외 종료가 롤백, 블록이 끝나면 닫힘. 제품 함수에 새 커밋 경계를 만들지 않으며 주입 함수가 이 의미를 지켜야 한다(공급자 연결을 감싸는 쪽의 책임, 이 단위 범위 밖).
- 전환 판정·계정 잠금·차단·CAS·커서·30일 창·부분 커밋·완료 재호출 동작은 바꾸지 않는다. 공급자나 앱 전역 연결 훅을 제품 함수에 직접 연결하지 않는다.

### 6-2. 공급자 연결을 제품 연결 컨텍스트로 감싸기 (2026-10-26 고정, 합성 범위)
- 구현 상태(2026-10-26, 합성: 실제 승인·서명·사전 검사 + 가짜 드라이버·연결·관측): `backend/scripts/_ops_product_connect.py`. 제품 함수에 실제로 주입한 실행(전환 CLI), 실제 PG에서의 커밋·롤백 의미는 미검증.
- 기준(정적 확인): `app.database.get_connection`은 PostgreSQL에서 `psycopg.connect(..., row_factory=dict_row)` 뒤 `read_only`면 `SET TRANSACTION READ ONLY`를 실행하고 `AppPostgresConnection`으로 감싼다. `AppPostgresConnection.__exit__`는 psycopg `Connection.__exit__`(정상 종료 커밋, 예외 시 롤백 — 롤백 오류는 경고만 하고 원래 예외 유지 — 뒤 닫기)를 부른 다음 `finally`에서 한 번 더 닫는다.
- 새 도우미 `scripts/_ops_product_connect.py`의 `ProductConnector(inputs, expected=..., driver=...)`: 호출 형태 `connect(*, read_only=False)`, 6-1 주입 함수 계약을 따른다. 합성 모드만, 기본 드라이버 없음.
- 호출마다: ① `read_only`가 불리언인지 ② 승인 바이트를 형식만 읽어 지금 명령 단계의 접근(읽기·쓰기)과 `read_only`가 맞는지 확인(맞지 않으면 연결 전 `connection_access_mismatch`; 이 읽기는 거부에만 쓰고 허가 근거가 아님, 승인·역할 자동 변경 없음) ③ app import 전 환경 고정 ④ 기존 공급자 경로 전체(`provide_with_adapter`: 사전 검사·서명·대상·TLS·연결·관측·재판정) ⑤ 인계를 **한 번** 꺼냄 ⑥ 인계 요약의 접근을 다시 대조 ⑦ 행 형식 `dict_row`(SQL 없음) ⑧ 사전 검사 뒤에만 `AppPostgresConnection` import·포장 ⑨ `read_only`면 `get_connection`과 같은 `SET TRANSACTION READ ONLY` 한 문장(쓰기 연결에는 SQL 없음) ⑩ 일회용 컨텍스트 반환. 연결 재사용·자동 재시도·범용 우회 없음.

| 단계 | 책임 | 내용 |
| --- | --- | --- |
| 공급자 관측 트랜잭션 | 공급자 | 관측용 읽기 전용 트랜잭션을 롤백하고 IDLE로 인계(기존) |
| 인계 뒤 준비 | 도우미 | 행 형식, 포장, 읽기 연결의 `SET TRANSACTION READ ONLY`. 실패하면 연결을 한 번 닫고 고정 코드로 거부, 연결을 돌려주지 않음 |
| 업무 트랜잭션 시작 | 제품 | 첫 문장으로 암묵 시작(쓰기 연결은 업무 첫 설정 문장이 그대로 첫 SQL). PostgreSQL은 첫 조회 전이면 `SET TRANSACTION`을 이어 쓸 수 있으나 이 단위에서 실제 PG로 확인하지 않음 |
| 정상 종료 | 도우미 `__exit__` | 커밋 → 닫기 1회 |
| 업무 예외·중단 | 도우미 `__exit__` | 롤백 시도 → 닫기 1회 → 원래 예외·중단을 그대로 전파(정리 실패는 연결 도우미의 `failures`에 코드만 기록) |
| 커밋 실패 | 도우미 `__exit__` | 롤백 시도 → 닫기 1회 → `commit_failed_result_unconfirmed`. 롤백 성공은 미커밋 확인이 아님(결과 미확정, 계약 9-2) |
| 정리 중 중단 | 도우미 `__exit__` | 남은 정리(닫기) 뒤 그 중단을 원래 객체 그대로 다시 발생 |

- 정리 실패 우선순위(정상 종료 경로에서 올리는 코드): `connection_close_unconfirmed` > `commit_failed_result_unconfirmed` > `rollback_failed`. 첫 코드를 `code`, 나머지를 `also`에 담는다. 오류 객체에는 고정 코드만 있고 드라이버 원문·비밀값·예외 연쇄가 없다.
- 기존과 다른 점(지시에 따른 것): 커밋 실패를 드라이버 예외 대신 고정 코드로 올리고 롤백을 한 번 시도한다, 닫기를 두 번 부르지 않는다. 제품 함수가 보는 연결 객체와 커밋·롤백·닫기 의미는 같다.
- 중단 보존 규칙(2026-10-26 검토 보정):
  - 업무에서 난 최초 예외·중단(`KeyboardInterrupt`·`SystemExit` 포함)은 정리 전에 보존하고, 정리가 끝나면 **그 객체 그대로** 전파한다(`SystemExit` 값 포함). 정리 중 난 다른 중단은 이를 덮어쓰지 않으며 `cleanup_interrupted`와 해당 단계 코드(`rollback_failed`·`connection_close_unconfirmed`)로만 기록한다.
  - 업무 예외가 없을 때는 도우미 자신의 단계에서 **처음 발생한 중단**을 보존한다: 준비 단계 중단 > 닫기 중단(준비 실패 경로), 커밋 중단 > 롤백 중단 > 닫기 중단(종료 경로). 보존한 중단은 남은 정리를 모두 시도한 뒤, 원인·문맥 연쇄를 떼고(`__cause__`·`__context__` 없음) 다시 발생시킨다. 이때 정리 실패 코드는 연결 도우미의 `failures`에 남는다.
  - 중단은 성공 결과나 일반 실패 코드로 바꾸지 않는다. 준비 단계의 일반 오류는 기존 고정 코드(`connection_prepare_failed` 등)로 처리하고, 중단을 전파할 때도 준비 오류·정리 오류의 원문은 예외 연쇄에 남기지 않는다.
  - 롤백·닫기는 각각 한 번만 시도한다. 롤백이나 닫기가 중단되면 성공으로 추정하지 않고 실패·미확인으로 기록한다. 중단 때문에 남은 정리 단계와 코드 기록을 건너뛰지 않는다.
  - 닫기 단계는 `close()` 호출과 그 뒤 닫힘 상태 조회(`closed`)를 함께 보호한다(2026-10-26 검토 보정 2). 상태 조회의 일반 오류는 원문 없이 `connection_close_unconfirmed`, 상태 조회 중단은 위 규칙대로 수집·기록하며, `close()`는 다시 부르지 않는다.

## 7. 계정별 전후 검사와 전역 감사

- 계정별 전후 검사(CLI 책임): 적용 전과 후에 같은 계정·카드 목록으로 dry-run을 다시 읽어 품질별 건수, `applied` 카드가 `already_fsrs`가 됐는지, `conflict`·`blocked` 카드의 SRS 값이 바뀌지 않았는지(`history_intro_*`는 바뀔 수 있음, 0절) 확인한다. 범위 밖 카드·다른 계정은 대상이 아니다.
- 전역 감사(`srs_invariant_audit`, 순위 3): DB 전체의 불변식. 적용 전후 각각 별도 조회 승인으로 실행하고 결과를 따로 기록한다. 단독 실행의 I6/I7 `not_evaluated`·`partial`은 그대로 기대값이다.
- 두 결과는 합치지 않는다. 계정별 검사 통과가 전역 감사 통과를 뜻하지 않고, 그 반대도 아니다.

## 8. 적용 전 백업 확인

- 근거: 전환은 계정 카드 값을 바꾸며 되돌림은 snapshot 기반 `rollback_plan`이다. 백업 복원은 그 뒤 평가를 잃어 기본 복구 수단이 아니다(로드맵 2-2 실패 복구 행). 그래도 운영 적용 전에는 복구 가능한 시점이 있어야 한다(EXECUTION_PLAN 4-1-3).
- 최초 확인(D4-A): 작업의 첫 `apply` 전에 한 번, 그 시점 이후에 만들어진 백업이 있음을 확인한 기록.
- 재개 시 확인(D4-A): 새 백업을 요구하지 않고, 최초 확인의 백업이 **아직 존재하고 유효한지**(보존 기간 안, 파기·만료 안 됨, 복원 가능 표시) 확인한다.
- 확인 형식: 운영 백업 방법이 미결이라(로드맵 순위 4) 지금은 정할 수 없다. 합성 단계에서는 "확인 기록이 없거나 재개 시 유효하지 않으면 `apply` 거부"라는 자리만 검사한다.
- (2026-10-27 추가) 재개 시 확인의 구체 경로(최초 근거를 적용 승인에 결속하는 방식, 결속 없는 기존 실행의 처리)는 `OPS_MIGRATION_RESUME_PLAN.md` 7절 제안이며 승인 전이다. 이미 서명된 과거 승인에는 근거 해시를 사후에 넣을 수 없다.

## 9. 오류·결과 미확정·종료 코드·실행 기록

### 9-1. 두 단계의 구분
- **쓰기 전 거부**: `apply_plan`의 첫 연결이 열리기 전(사용법·승인·서명·지문·`plan_changed`·4-2 판정·백업 확인 거부), 또는 첫 연결 자체가 공급자에서 거부된 경우. 실행 행도 만들어지지 않으므로 "변경 없음"이라고 말할 수 있는 유일한 경우다. CLI의 연결 함수가 성공한 연결 수(0)로 판정한다.
- **실행 시작 후 중단**: 첫 연결이 열린 뒤의 모든 중단. 실행 행 생성·카드 일부 커밋이 이미 있을 수 있다. 다음 연결에서 승인 만료·권한 변경·창 만료로 거부되더라도 "쓰기 전 거부·변경 없음"으로 보고하지 않는다.
- 결과 출력·기록의 필드(실행 시작 후 중단): `reason`(고정 거부·실패 코드), `phase`(`after_start`), `confirmed`(이번 호출에서 **확인된** 커밋 범위: `apply_plan`이 정상 반환한 결과에서만, 또는 같은 작업의 읽기 `status`로 확인한 커서·상태), `uncertain`(확인하지 못한 부분이 있는지), `next`(`status_required` 등).
- 상태를 확인하지 못하면 커서·미커밋을 추정하지 않는다. `confirmed`는 `unknown`, `uncertain`은 참, `next`는 `status_required`다. 같은 호출 안에서 CLI가 읽기 `status`를 하려면 그 연결도 공급자의 판정을 받아야 하며(같은 원인으로 거부될 수 있음), 거부되면 위와 같이 남긴다.

### 9-2. 사례별 기대 결과

| 사례 | 종료 코드 | 출력(고정 값) | 다음 행동 |
| --- | --- | --- | --- |
| 최초 연결 전 승인 거부(서명·기간·지문·입력·`plan_changed`·첫 연결 공급자 거부) | 4 | `phase: before_first_write`, `reason`, `changes: none` | 승인·입력 확인, 필요하면 조회부터 |
| 실행 행만 생성된 뒤 중단(첫 연결 커밋 뒤, 첫 카드 전) | 1 | `phase: after_start`, `reason`, `confirmed: unknown`(또는 `status`로 확인된 `started`·커서 0), `uncertain: true`, `next: status_required` | 새 조회 승인으로 `status`. 실행 행이 있으면 30일 창이 시작된 상태로 기록 |
| 카드 일부 커밋 뒤 승인 만료·권한 변경(다음 연결 `observed_*`·`preflight_*` 거부) | 1 | `phase: after_start`, `reason`(공급자 코드), `confirmed`: 이번 호출에서 확인된 범위 또는 `unknown`, `uncertain: true`, `next: status_required` | `status`로 커서 확인. `failed` 표시도 같은 거부로 실패해 `started`로 남을 수 있음(0절). 재개는 새 적용 승인(D3-B) |
| 카드 사이 30일 창 만료(`migration_resume_window_closed`) | 1 | `phase: after_start`, `reason`, 상태는 바뀌지 않음(코드), `confirmed`는 `status`로만, `next: status_required` | 재개 불가. 보고 |
| 마지막 카드 뒤 완료 표시 실패(마무리 연결 거부·오류) | 1 | `phase: after_start`, `reason`, `uncertain: true`, `next: status_required` | `status`가 `cursor_end_not_completed`(6)를 보이면 D7-A대로 보고만 |
| 응답 유실로 커밋 여부 미확정(연결 끊김·시간 초과·처리되지 않은 예외) | 1 | `phase: after_start`(첫 연결이 열린 뒤라면), `reason: result_unconfirmed`, `confirmed: unknown`, `uncertain: true`, `next: status_required` | 새 조회 승인으로 `status`. 미커밋 추정 금지(계약 9-2) |

### 9-3. 종료 코드 우선순위 (D5, 제안)

| 우선순위 | 코드 | 의미 |
| --- | --- | --- |
| 1 | 2 | 사용법 오류(인자 형식). 아무것도 열지 않음 |
| 2 | 1 | 실행 시작 후 중단·실패·미확정. 거부 사유가 함께 있어도 이 코드이며, 사유는 `reason`에 남긴다 |
| 3 | 4 | 쓰기 전 거부(9-1) |
| 4 | 6 | 상태 확인 필요: `cursor_end_not_completed`, `inconsistent`(쓰기 없이 판정만 한 경우) |
| 5 | 3 | 부분 처리: 이번 호출이 정상 반환했고 커서 < 카드 수 |
| 6 | 5 | 완료(`completed` 확인)했으나 결과에 `conflict`·`blocked` 포함 |
| 7 | 0 | 완료, `conflict`·`blocked` 없음 / dry-run·`status` 정상 |

- 1과 4는 단계로 갈린다. 실행이 시작된 뒤에는 어떤 거부 사유도 1을 4로 낮추지 않는다(이미 발생한 처리 실패·미확정을 덮어쓰지 않음).
- 부분 처리 + `conflict`·`blocked`는 3이며 건수는 출력에 따로 적는다. `status` 명령은 같은 표를 따른다(`incomplete`·`failed_at_cursor`는 3, `completed`는 0 또는 5, 확인 불가는 1).

### 9-4. 출력·실행 기록
- 출력·기록에 넣지 않는 것: 연결 문자열, 비밀번호, 단어·뜻·JSON 본문, 드라이버 원문. 오류는 고정 코드로만.
- 실행 기록: 계약 11절 필드 + 계획 파일 지문, 제품 계획 지문, 사용한 승인 사슬의 id·바이트 해시, 실행 id, 성공한 연결 수와 연결마다 판정 결과, 9-1의 `phase`·`reason`·`confirmed`·`uncertain`·`next`, 호출 전후 커서·상태(확인된 경우만), 4-2 판정, 결과별 건수. 위치·보존 기간은 미정(계약 12-2). 실행 기록은 근거 보조이며 승인을 대신하지 않는다.

## 10. 검증 기준 (합성)

- 합성 SQLite(기존 `qa_srs_b2_*` 장치 방식)와 합성 로컬 PG, 각각 계정 둘 이상.
- 확인 항목: 기본 dry-run 무쓰기, 승인 없는 `apply` 거부, 업무 입력·계획 파일 변경 시 쓰기 0 거부, 계획 파일 지문이 서명된 `plan`을 거쳐야만 통과(로컬 기록 해시만으로는 거부), 기존 도구의 작업 계획 지문 값 불변(`artifact_sha256=None`), 최초 적용 `plan_changed`, 중간 실패 뒤 커서·커밋 보존과 같은 키 재개가 미처리 카드만 처리, 4-2 표의 모든 상태(마무리 직전 중단을 만든 `cursor_end_not_completed`, 손상 사례)의 판정·종료 코드·무쓰기, 완료 재호출의 행 변경 0, 다른 범위의 같은 키 `migration_run_conflict`, 창 밖 거부, `supersedes` 사슬 검증(누락·순서·종류·작업 키·서명 오류 거부, 권한 비합산), 최초 조회 승인 만료 뒤 재개, 9-2 표의 여섯 사례(종료 코드·`phase`·`confirmed`·`uncertain`·`next`, 실행 시작 후 거부를 4로 보고하지 않음), 연결마다 확인 횟수 = 연결 수, **다른 계정의 표 행 전체가 전후 같음**, 범위 밖 카드 불변, 계정별 검사와 전역 감사 결과의 별도 기록.
- 공급자 경로 검사표(공통 모듈 단위, 가짜 연결·관측):

| 사례 | 기대 결과 |
| --- | --- |
| 사전 검사 성공 + 연결 후 관측·지문 일치(`artifact_sha256`·이전 승인 사슬 포함) | 연결 인계 |
| 사전 검사 성공 + 연결 후 재판정에 `artifact_sha256`·`prior`가 빠지거나 다른 값이 들어감(전달 경로 결함을 모의) | `observed_job_plan_mismatch`·`observed_approval_supersedes_unknown` 등 `observed_*` 거부, 연결 닫힘, 인계 없음. 정상 경로에서는 두 판정이 같은 입력을 읽으므로 생기지 않아야 한다 |
| 사전 검사 성공 + 연결 후 연결·권한 지문 불일치(관측 프로필·역할·권한이 승인과 다름) | `observed_connection_profile_mismatch` 또는 `judge_observation`의 `observed_*`, 인계 없음 |
| 사전 검사 성공 + 연결 후 DB 식별·역할·권한 관측 불일치 | 기존 `observed_*` 거부, 인계 없음 |
| 재연결(새 호출)에서 승인 기간 만료 | `preflight_approval_expired`(또는 해당 코드), 인계 없음 |
| `supersedes` 있는 승인 + 이전 승인 사슬 누락 | 사전 검사 `approval_supersedes_unknown`, 연결 없음 |
| 이전 승인 사슬의 서명 오류·순서·종류·작업 키 불일치 | 사전 검사 거부, 연결 없음 |
| 호출자가 `Approval` 객체·검증 표시를 넣음 | 입력 형식 거부(필드 자체가 없음) |
| `artifact_sha256` 없음(기존 도구) | 기존 지문 값 그대로, 기존 회귀 통과 |

- 기존 전환·롤백 회귀 검사와 공통 모듈 회귀 검사는 각 변경이 들어가는 단위에서만 다시 돌린다.

## 11. 현재 가능한 합성 경로와 운영 차단 조건

- 지금 가능(합성): 합성 서명 승인(`_ops_approval`·`_ops_signature`의 합성 경로), 합성 manifest·사전 검사, 합성 공급자, 로컬 PG 18.6 장치. 단 `supersedes` 승인과 계획 파일 결속은 5-2·2-2의 공통 모듈 변경 전에는 합성에서도 불가하다.
- 운영 차단(갖춘 것으로 가정하지 않음): 운영 신뢰 루트·서명 도구 결정, import 무결성(검사한 바이트와 Python이 읽는 코드의 결속, 계약상 미검증), 실행 기록 위치·보존, 운영 쓰기 역할·권한표(순위 10), 운영 식별 행, 운영 백업 방법(순위 4), 비밀 보관소. 이 중 하나라도 없으면 운영 `apply`는 거부 상태로 둔다.

## 12. 결정 필요 (승인 아님)

아래 권장안은 모두 제안이며 사용자 승인으로 기록하지 않는다.

| 결정 | 선택지 | 권장안 | 대가 |
| --- | --- | --- | --- |
| D1 연결 주입 | (A) `connect=None` 선택 인자, 호출 시 `get_connection` 선택 / (B) CLI에서 모듈 `get_connection` 교체 / (C) 앱 전역 연결 훅 | A. `connect`는 공급자를 감싸 연결마다 5-4 재판정을 받는다 | A는 제품 두 함수 서명 변경. B는 제품 변경 없음이나 모듈 전역 교체라 깨지기 쉬움. C는 영향 범위가 앱 전체 |
| D2 계획 결속 | (A) 제품 계획 지문만 / (B) `job_plan_fingerprint`에 선택 인자 `artifact_sha256`, 서명된 `plan`에 포함, 사전 검사와 연결 후 재판정 모두에 전달(2-2·5-4) / (C) 적용 승인에 계획 파일 해시 필드 신설 | B | B는 공통 모듈·공급자 경로 변경, 기존 값 불변. A는 `reconversion`·`restart_json`을 승인이 묶지 못함. C는 승인 형식 변경이 더 큼 |
| D3 재개 승인 | (A) 최초 적용 승인을 기간 안에서 재사용 / (B) 재개마다 새 적용 승인(`supersedes`), 5-2·5-4 경로 구현 뒤 | B | B는 승인 작업과 공통 모듈 변경이 늘어남. A는 24시간 승인 기간과 30일 창이 어긋남 |
| D4 백업 확인 | (A) 첫 `apply` 전 확인 + 재개 시 그 백업의 존재·유효성 확인 / (B) 호출마다 새 백업 | A | B는 부담이 큼. A는 긴 재개 사이 백업이 오래됨. 운영 백업 방법은 미결 |
| D5 종료 코드 | 9-3 표(단계 구분, 시작 후 중단 우선) / 0·1만 | 9-3 표 | 세분화는 다음 행동을 고르기 쉬우나 검사 항목이 늘어남 |
| D6 `blocked` 카드의 `history_intro` 갱신 | 현행 유지(쓰기 프로필에 열 포함) / 전환 CLI에서 제외 | 현행 유지 | 제외는 제품 동작 변경 |
| D7 커서 끝·완료 미기록 처리 | (A) 보고만, 사람 판단 / (B) 별도 승인된 읽기 검사 뒤 `completed` 기록 경로 신설 / (C) 제품 `apply_plan` 재호출이 마무리하도록 변경 | 이번 범위는 A | B·C는 새 쓰기 경로나 제품 변경. A는 상태가 `started`로 남아 정리·창 판정에 남는 영향을 사람이 따로 판단 |
| D8 `supersedes` 형식 | (A) id만(현행) / (B) `{approval_id, sha256}` | B. 승인 `format_version`을 올려 새 형식에서만 객체형을 받는다. 기존 형식(id 문자열)의 승인은 새 버전 검사기에서 `supersedes`가 있으면 형식 오류로 거부하고(첫 승인처럼 `supersedes`가 없는 기존 승인은 그대로 해석 가능 여부를 별도 판단), 문자열을 객체로 바꾸거나 해시를 채워 넣는 **조용한 변환은 하지 않는다.** 필요하면 사람이 새 형식으로 다시 서명한다 | 기존 승인 문서 재서명, 공통 형식·검사기 변경. A는 같은 id의 다른 바이트를 구별 못함 |
| D9 식별 갱신·키 폐기 뒤 재개 | (A) 재개 불가, 새 `run_key`로 새 작업 / (B) 별도 절차 설계 | B. 절차가 마련될 때까지 자동 재개·새 작업 전환은 모두 거부하고 보고만 한다 | B는 설계 비용과 그동안 미완료 실행이 남음. A는 기존 실행 처리 판단 없이 새 작업이 생김 |

## 13. 구현 순서 (각각 별도 승인)

1. 이 계획의 계약 재검토.
2. 공통 모듈 변경(합성): `_ops_approval`(`artifact_sha256`, D8 결정 시 `supersedes` 형식·형식 버전), `_ops_preflight`(입력 필드, 이전 승인 사슬 서명·연쇄 검증, 검증된 승인 반환), `_ops_provider`·`_ops_adapter`(연결 후 재판정에 검증된 `approval`·`inquiry`·`prior`와 `artifact_sha256` 전달). 10절 공급자 경로 검사표와 기존 공통 모듈·감사 경로 회귀 포함. 전환 도구 코드는 넣지 않는다.
3. 전환 CLI 합성 구현: 새 CLI + `TOOLS` 항목·쓰기 프로필 + 제품 `connect` 인자(D1-A) + 4-2 상태 판정 + 9절 결과 형식 + 합성 SQLite 검사. 제품 변경이 들어가므로 기존 전환·롤백 회귀 포함.
4. 실제 로컬 PG 준비·검증: 새 대상 묶음(역할 읽기·쓰기 분리, 계정 둘 이상, TLS), 10절 항목, R2 정리. 별도 계획·승인.
5. 운영 적용: 11절 차단 조건 해소, 백업 방법 결정, 계정별 적용 승인 뒤에만.

명시 전환 CLI 계획 계약 재검토 대기.

- 2026-10-29 참조: 완료 재호출(완료 결과 재조회) 계약 검토는 `OPS_MIGRATION_COMPLETED_REPLAY_PLAN.md`에 있다(계획만, 승인 전). D7-A(`cursor_end_not_completed` 보고만)는 그대로다.
- 2026-10-30: 완료 재조회 검토 지적 3건을 해당 계획 7절에서 보완했다. C5는 최초 검사·연결 직전 시각 갱신을 권장하며, 확정 시 CR-S1 코드 보정·합성 검사가 선행된다. C1~C5는 아직 사용자 결정 대기이며 상태 보정·실제 PG·운영은 승인하지 않는다.

- 2026-10-30 CR-S1 마감: 완료 재조회 C1~C5 확정 뒤 기존 status의 진입·연결 요청 시각을 갱신했다. 합성 회귀 112개 통과·독립 검토 완료이며, 제품 적용·재개·상태 보정은 바꾸지 않았다. 상세는 `OPS_MIGRATION_COMPLETED_REPLAY_PLAN.md` 10절, 다음 실제 PG 제안은 `OPS_MIGRATION_COMPLETED_REPLAY_REAL_PG_PLAN.md`다. 실제 PG 실행은 승인 전이다.

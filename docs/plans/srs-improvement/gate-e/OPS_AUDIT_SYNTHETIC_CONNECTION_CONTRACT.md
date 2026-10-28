# 읽기 전용 감사 도구의 합성 연결 계약 (2026-10-22, 계약 승인, 합성 구현 마감 2026-10-23)

상태: **문서만.** 구현·DB 접속·PG 실행·키 생성·운영 활성화는 승인되지 않았다. 다음 구현 단위는 합성 환경까지이며 운영 모드는 계속 거부한다.
근거(정적 확인): `backend/scripts/srs_invariant_audit.py`, `app/srs/invariant_audit.py`(`read_snapshot`·`_require_snapshot`·`audit`), `app/database.py`(`AppPostgresConnection`·`is_postgres_connection`), `app/settings.py`(import 시 `load_dotenv`), `scripts/_ops_preflight.py`·`_ops_provider.py`·`_ops_adapter.py`·`_ops_observer.py`, `_ops_approval.TOOLS["srs_invariant_audit"] = {"audit": "read"}`, `OPS_TOOL_SAFETY_CONTRACT.md` 312·378·418행, `OPS_CONNECTION_PROVIDER_CONTRACT.md` 2·3·10·11절, `OPERATIONS_READINESS_PLAN.md` 순위 3.

## 1. 기존 모드 보존과 새 경로

- 기존 `--sqlite-db`·`--local-test-postgres` 모드는 코드·인자·종료 코드를 바꾸지 않는다.
- 새 경로는 **라이브러리 함수**로만 붙인다: 새 `backend/scripts/_ops_audit_run.py`의 `run_synthetic_audit(inputs, *, expected, driver) -> (report, exit_code)`. 기본 드라이버는 없다(`driver`가 없으면 `connection_factory_not_implemented`). 다음 구현 단위에서는 `srs_invariant_audit.py`에 새 인자를 추가하지 않는다(기존 CLI 연결은 별도 승인).
- 공급자는 기존 `_ops_provider.provide_synthetic_connection` + `_ops_adapter.CopyingFactory` + `_ops_observer.CatalogObserver`를 그대로 쓴다. 승인·서명·권한 판정은 다시 설계하거나 완화하지 않는다.

## 1-1. 조회 범위: 지정 DB 전체 (보정 1차)

- 사실: 기존 `audit()`는 계정 하나가 아니라 **지정 DB 전체**의 카드·로그·사용자·표식을 읽는다. 결과가 집계값뿐이어도 실제 조회 범위는 DB 전체다. 감사 함수의 범위와 판정은 바꾸지 않는다.
- 문제: 공통 승인 검사(`authorize_command`)는 `account_id`가 `accounts`에 있는지만 본다. 그대로 쓰면 계정 하나의 조회 승인이 전역 감사를 허용하게 된다.
- 표현(새 승인 형식 없이 기존 서명 필드로): 서명 대상인 `job.inputs`에 정확히 두 키를 둔다.
  - `audit_scope = "database_all"`
  - `audit_db_identity = <승인의 db_identity와 같은 64자리 hex>`
  - `job.inputs`는 서명된 승인 바이트 안에 있고, `authorize_command`가 실행 입력과 정확히 같은지(`_canonical` 비교) 확인하며, 작업 계획 지문(`job_plan_fingerprint`)에도 들어간다. 그래서 범위 누락·변조·다른 값은 서명 검증 또는 입력 대조에서 걸린다. 새 승인 형식은 필요하지 않다고 판단한다.
- 실행기 검사(연결 전, 공급자 호출 전): `_ops_audit_run`이 승인 바이트를 형식 해석(`parse_approval`)해 다음을 모두 요구하고, 실행 입력 `job_inputs`를 이 고정 값으로만 만든다(호출자가 다른 값을 넘길 수 없음).
  1. `tool = srs_invariant_audit`, `kind = inquiry`, `steps`는 `audit`(read) 하나, 단계 `args` 없음.
  2. `job.inputs`의 키 집합이 정확히 위 두 개, `audit_scope = "database_all"`.
  3. `audit_db_identity` = 승인 `db_identity`(다른 DB 범위면 거부).
  4. `accounts`는 정확히 하나, `max_accounts = 1`, 실행 `account_id` = 그 값.
  - 이어서 공급자의 5단위 사전 검사가 서명·manifest·대상 지문·입력 대조를 다시 하고, 연결 후 관측 식별 지문이 승인 `db_identity`와 같아야 한다(기존 경로). 연결은 이 모두가 통과한 뒤에만 열린다.
- `account_id`·`accounts`의 뜻(이 경로 한정): 승인 형식과 작업 계획 지문이 요구하는 **작업 슬롯 값**일 뿐이며 조회 범위를 좁히거나 넓히지 않는다. 계정 목록을 전역 조회 허가로 해석하지 않으며, 전역 감사 허가는 오직 서명된 `audit_scope = "database_all"`에서 나온다. 출력에도 넣지 않는다.
- 거부 코드(고정, 연결 전): `audit_scope_missing`(키 없음·키 집합 다름), `audit_scope_not_database`(계정 한정 등 다른 값), `audit_scope_db_mismatch`(다른 DB), `audit_approval_shape_invalid`(도구·종류·단계·인자·계정 슬롯 조건 위반). 서명 뒤 변조는 기존 `preflight_approval_signature_invalid`, 실행 입력 불일치는 기존 `preflight_job_input_mismatch`.

## 2. 호출 흐름 (코드 위치)

| 순서 | 무엇 | 위치 |
| --- | --- | --- |
| 1 | 모드 확인: `synthetic`만, 운영 모드 거부 | `_ops_audit_run.run_synthetic_audit` 첫 줄 |
| 2 | app import 전 환경 고정: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, `PYTHON_DOTENV_DISABLED=1`(기존 CLI 26~28행과 같은 전제. `app/settings.py`의 `load_dotenv`는 기존 값을 덮지 않음) | 같은 함수, app import보다 먼저 |
| 3 | 조회 승인과 범위: 1-1절 실행기 검사(연결 전) → `tool = srs_invariant_audit`, `audit`(read) 하나, `kind = inquiry`만, `job.inputs` = 지정 DB 전체 범위 | `_ops_audit_run`(형식 해석) → `_ops_preflight.run_synthetic_preflight` → `_ops_approval.verify_signed`·`authorize_command` |
| 4 | 서명·manifest: 승인·manifest 서명, 배포 파일 해시(감사가 import할 `backend/app/**`·`backend/scripts/**` 포함), TLS 루트 하나 | `_ops_preflight`(3·4·10단계), `_ops_manifest` |
| 5 | 대상·권한 확인: 연결 전 DSN·환경 검사 → 검증 사본 → 연결 → 관측 트랜잭션(READ ONLY) → 대상·식별·역할·소속·소유·TLS·업무 기본값·search_path·객체·실효 권한 대조 → 롤백 → IDLE → 인계 | `_ops_target.check_preconnect`, `_ops_adapter.CopyingFactory.open`, `_ops_provider` |
| 6 | 인계 연결 포장: `handoff.take()` → `conn.row_factory = dict_row`(SQL 없음) → `AppPostgresConnection(conn)` | `_ops_audit_run` |
| 7 | 읽기 전용 감사: `with read_snapshot(app_conn):` 안에서 `SET LOCAL statement_timeout = '15s'`·`lock_timeout = '5s'`(확정값) → 대상 재확인(`current_database`·서버 주소·포트, 식별 행 = 관측값) → `audit(app_conn)` | `app/srs/invariant_audit.py`(변경 없음) + `_ops_audit_run` |
| 8 | 종료: `read_snapshot`의 롤백 → 연결 닫기 1회 | `read_snapshot` finally, `_ops_audit_run` finally |
| 9 | 출력: 5절 형식, 종료 코드는 기존과 같음(0 pass, 1 fail, 2 error/unknown, 3 partial) | `_ops_audit_run` |

## 3. 공급자 연결을 기존 감사 함수가 쓸 수 있는지

- 가능하다고 판단한다(정적 근거, 실제 PG 미검증). `audit()`·`read_snapshot()`은 `is_postgres_connection`(속성 `is_postgres`)과 `connection._connection`(원시 psycopg 연결)만 요구하고, `AppPostgresConnection`은 원시 연결을 받는 얇은 포장이다. 인계 시점 상태는 IDLE이고(6-2 c01 실제 확인), `read_snapshot`의 첫 문장 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`는 공급자 계약 3절이 허용하는 업무 첫 문장이다(6-2 c01에서 같은 꼴 실제 성공).
- 차이 두 가지를 이 경로가 맞춘다: ① 기존 로컬 모드는 `dict_row`로 연결하지만 공급자는 기본 행 형식이다 → 인계 뒤 `row_factory`만 바꾼다. ② 기존 로컬 모드는 연결 `options`로 `search_path=public,pg_catalog`·제한 시간을 주지만 공급자 고정값에는 없다 → search_path는 승인 프로필의 고정값으로 관측·대조하고(다르면 거부), 제한 시간은 감사 트랜잭션 안 `SET LOCAL`로 준다.
- 쓰지 않는 것: `get_connection`·`get_database_url`·`init_db`·`initialize_database`·`.env`. 감사가 import하는 app 모듈의 import 부작용은 위 2단계 환경 고정으로 막는다(기존 CLI와 같은 전제). import 시점 무결성(해시 검사와 import 사이 파일 교체)은 미해결 전제다(7절).

## 4. 트랜잭션·격리·종료 책임, 쓰기 없음 검사

- 관측 트랜잭션: 공급자 소유(READ ONLY, `read committed`, 끝나면 롤백).
- 감사 트랜잭션: `read_snapshot` 소유(`REPEATABLE READ, READ ONLY`, 성공·실패 모두 롤백). I1~I5는 이 한 스냅숏에서 본다. 시퀀스는 MVCC 밖이라 I3은 관측일 뿐이다(기존 주석과 같음).
- 연결 닫기: `_ops_audit_run`이 한 번. 닫기 실패는 `audit_close_failed`(기존 문구)로 결과를 덮고 성공으로 바꾸지 않는다.
- 쓰기·DDL·자동 복구가 없음을 보이는 겹 검사:
  1. 서버 강제: 역할 업무 기본 `default_transaction_read_only=on`, 감사 트랜잭션 `READ ONLY`, 승인 프로필은 SELECT·USAGE·CONNECT만(초과 권한이면 연결 단계에서 거부).
  2. 합성 검사: `AppPostgresConnection.execute`를 감싼 SQL 추적으로 실행 문장을 모두 모아 허용 목록(`SET TRANSACTION …`, `SET LOCAL statement_timeout|lock_timeout`, `SELECT`, `SHOW`) 밖이 0인지, `commit` 호출 0인지 확인.
  3. 실제 PG(별도 승인): 감사 트랜잭션 롤백 직전 `pg_catalog.pg_current_xact_id_if_assigned()`가 NULL(쓰기가 있었다면 트랜잭션 ID가 배정됨), 대상 표의 `xmin`·행 수 전후 불변.
  4. 정적: `app/srs/invariant_audit.py`와 감사가 부르는 함수(`goals.account_goal`·`introduction_count`·`read_utc`, `identity.scan_identity`, `migration._card_columns`·`_record_shape`·`_reduced_scope`, `stats_history_repository._review_rows`)에 쓰기 문장·`commit`이 없는지 목록 검사.

## 5. 출력

- 허용: 기존 `audit()` 결과 그대로(`audit_version`, `status`, `checks`의 상태·개수), 고정 사유 코드(`reason`: 1-1절 범위 거부 코드, 공급자 거부 코드 또는 기존 `audit_refused_or_unreadable`·`audit_close_failed`), 대상·승인 식별값(`alias`, `db_identity` 지문, `manifest` SHA-256, `approval_id`, `tool`·`command`), 조회 범위 `scope = database_all`(결과가 집계값이어도 DB 전체를 읽었다는 표시). `host`·`port` 원문은 넣지 않는다(확정, 지문만).
- 금지: DSN·비밀번호·호스트 문자열 원문 조합, 카드·단어 내용, 이메일, 토큰·토큰 해시, 드라이버 원문, SQL.
- 의미 보존: `fail`·`unknown`·`not_evaluated`(→ 전체 `partial`)를 바꾸거나 통과로 올리지 않는다. 단독 실행의 I6/I7은 계속 `not_evaluated`다. 공급자 거부·감사 예외는 `status = error`, 종료 2.

## 6. 최소 변경 파일과 검사표 (다음 구현 단위)

- 새 `backend/scripts/_ops_audit_run.py`, 새 `backend/tests/test_ops_audit_run.py`. 그 밖 변경 없음(`app/`·기존 CLI·공급자·관측기·어댑터 그대로).

| # | 사례 (가짜 드라이버·가짜 커서 + 실제 서명·합성 파일) | 기대 |
| --- | --- | --- |
| 1 | 정상 조회 승인 → 인계 → 감사(가짜 `audit`) | 순서대로 호출, 결과·식별값만 출력, 종료 0 |
| 2 | 감사 결과 `fail`·`unknown`·`partial` | 종료 1·2·3, 상태 그대로 |
| 3 | apply 승인·쓰기 단계·다른 도구·운영 모드·드라이버 없음 | 연결 전 거부, 종료 2 |
| 4 | 공급자 거부(대상·프로필·소유 등) | 고정 코드, 감사 미호출, 연결 닫힘 |
| 5 | 인계 연결이 IDLE 아님·이미 트랜잭션 | `read_snapshot` 거부(기존 `transaction_already_open`), 종료 2 |
| 6 | SQL 추적: 허용 목록 밖 문장 0, `commit` 0, 감사 뒤 롤백·닫기 각 1회 | 통과 |
| 7 | 닫기 실패 | `audit_close_failed`, 성공 아님 |
| 8 | 출력·예외에 DSN·비밀번호·이메일·토큰 없음 | 없음 |
| 9 | app import 전 환경 고정, `get_connection`·`init_db` 미호출(패치로 확인) | 통과 |
| 10 | 변형: 감사 전 `row_factory` 미설정, `SET LOCAL` 누락, 롤백 생략, 종료 코드 매핑 변경, 범위 검사 제거 | 각각 검출 |
| 11 | 계정 한정 승인(`job.inputs`에 범위 없음, 또는 `audit_scope = "account"`) | `audit_scope_missing`·`audit_scope_not_database`, 연결 0·사전 검사 0 |
| 12 | 범위 키 누락·추가 키·값 타입 다름 | `audit_scope_missing`, 연결 0 |
| 13 | 서명 뒤 범위 변조(승인 바이트 수정) | `preflight_approval_signature_invalid`, 연결 0 |
| 14 | 실행 입력과 승인 범위 불일치(실행기 고정 입력과 서명 값 다름) | `preflight_job_input_mismatch`, 연결 0 |
| 15 | 다른 DB 범위(`audit_db_identity` ≠ 승인 `db_identity`) | `audit_scope_db_mismatch`, 연결 0 |
| 16 | 다른 DB에 대한 정상 범위 승인으로 이 DB 연결 | 기존 대상 지문 불일치(연결 전 사전 검사 또는 연결 후 `observed_identity_mismatch`), 감사 미호출 |
| 17 | `accounts` 둘 이상·`max_accounts` > 1·`account_id` 불일치 | `audit_approval_shape_invalid`, 연결 0 |
| 18 | 출력에 `scope = database_all`, `host`·`port` 원문 없음 | 통과 |

- 실제 PG 검사(별도 승인, 6-2 클러스터는 삭제됨): 새 합성 클러스터 준비, 앱 스키마를 소유 역할로 만드는 방법, 감사용 읽기 역할과 기대 프로필(감사가 읽는 표 전체의 SELECT), 같은 합성 자료에서 기존 `--local-test-postgres` 결과와 새 경로 결과의 일치, `xact_id` NULL·`xmin` 불변.

## 7. 실제 PG 검증 여부와 미결 사항

- 실제 PG에서 검증된 공통 기능(6-2 1·2차): 사전 검사·사본·드라이버 인자·관측 SQL 26개·대조·인계·업무 첫 문장, 보호 장치의 연결 전 거부.
- 아직 없는 것: `_ops_audit_run`, 감사 SQL의 공급자 연결 경유 실행, 감사용 프로필, 앱 스키마가 있는 합성 클러스터, 결과 보관 형식.
- 이번 합성 감사 연결에 필요한 전제(구현됐다고 취급하지 않음): 운영 신뢰 루트(합성은 시험 키), import 무결성(해시 검사 뒤 import 사이 교체 방지 미해결: 합성은 한계로 기록), 실행 기록(합성은 표준 출력만), 실행 계정(합성 해당 없음).
- 확정(2026-10-22 사용자): 감사 `statement_timeout` 15초, `lock_timeout` 5초, 출력에 `host`·`port` 원문 없이 지문만.
- 별도 승인 유지: 실제 PG 준비·접속, 기존 CLI 연결(인자 추가), 운영 활성화.

## 8. 합성 구현 결과 (2026-10-22, 사용자 승인)

- 새 `backend/scripts/_ops_audit_run.py`(`check_scope`, `run_synthetic_audit`), 새 `backend/tests/test_ops_audit_run.py`. `app/`·기존 CLI·공통 승인·공급자·관측기·어댑터는 바꾸지 않았다.
- 계약과 다르게 정한 것 한 가지: 검사표 14(호출자 실행 입력 ≠ 서명 범위)는 실행기가 사전 검사보다 먼저 `audit_job_inputs_mismatch`로 거부한다(덮어쓰지 않음). 사전 검사의 `preflight_job_input_mismatch`는 두 번째 겹으로 그대로 있다.
- 추가한 것: 감사 함수가 정의되지 않은 상태 값을 돌려주면 `audit_result_invalid`(종료 2)로 통과시키지 않는다. 감사 모듈의 고정 사유(`AuditInputError`, 예 `transaction_already_open`)는 그 코드로 보고한다.
- 실제 PG 감사는 아직 실행하지 않았다(6절 실제 PG 검사는 별도 승인).

- 검토 보정(2026-10-22): ① app import 순서: 실행기가 범위 검사 → 환경 고정 → 실제 5단위 사전 검사(승인·manifest 서명, 배포 파일 해시, 대상·명령)를 직접 통과시킨 뒤에만 app을 import하고, 공급자가 연결 전에 같은 사전 검사를 다시 한다. 호출자가 주는 "검사 완료" 값은 없다. 이것은 import 순서만 바꾼 것이며, 검사한 바이트와 실제 import되는 파일의 결합·교체 방지는 여전히 미검증이다. ② 연결 정리: 인계 뒤 포장·스냅숏·감사 전체를 `finally`로 감싸 모든 경로에서 닫기를 한 번 시도한다. `KeyboardInterrupt`·`SystemExit`는 정리 뒤 그대로 전파하고 결과로 바꾸지 않는다. 일반 오류의 고정 코드와 닫기 실패 우선(`audit_close_failed`)은 그대로다.

- 검토 보정 2(2026-10-22): 감사 중 `KeyboardInterrupt`·`SystemExit`(등 `Exception`이 아닌 중단) 뒤 `read_snapshot`의 롤백까지 실패하면 롤백 오류가 중단을 가려 `audit_refused_or_unreadable`로 끝났다. 이제 실행기가 최초 중단을 롤백 전에 기록하고, 연결 닫기를 한 번 시도한 뒤 그 같은 예외 객체를 다시 던진다(`SystemExit` 값 보존, 롤백·닫기 오류는 원인·문맥으로 연결하지 않음). 중단이 없는 일반 오류의 결과 코드와 닫기 실패 우선은 그대로다. `read_snapshot`·공급자는 바꾸지 않았다.

- 마감(2026-10-23): Codex 독립 검토에서 집중 테스트 29개 통과로 합성 단위를 닫는다. 실제 PG 감사·import 결합·실제 롤백/닫기 장애는 미검증으로 유지한다. 실제 로컬 PG 검증은 `OPS_AUDIT_REAL_PG_PLAN.md`에서 마감(2차 실제 통과 4/4, 2026-10-24). 감사 역할 권한은 표 14개·시퀀스 1개로 확정했다(공유 덱 두 표 제외, 같은 문서 0절 정정).

읽기 전용 감사 합성 연결: 합성 단위 마감.

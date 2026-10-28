# 실제 로컬 PG 감사 검증 계획·실행 기록 (2026-10-24 마감)

**현재 상태(2026-10-24)**: 마감. P1 시험 코드 독립 검토 통과(최종 41개), P2~P4 1차 실행은 준비만 성공·실제 통과 0(8절), 재승인된 2차 실행은 실제 통과 4/4(9절). 남은 제한은 10절.

작성 당시 상태(2026-10-23): **계획만.** PG 시작·접속, 클러스터·인증서·키 생성, 코드 변경은 승인되지 않았다. 6-2 계획(`OPS_REAL_PG_6_2_PLAN.md`)을 다시 쓰지 않고 **감사에 필요한 차이만** 적는다. 6-2에서 실제로 확인한 공통 기능(사전 검사·사본·관측·대조·인계·보호 장치)은 반복하지 않는다. 운영 모드·기본 진입점·기존 CLI 연결·E-1 장치는 그대로다.

**승인 기록 (2026-10-23 사용자)**: P1 독립 검토(39개 통과) 뒤 P2 준비·P3 실제 검사·P4 R2 정리를 일괄 승인했다. 대상은 `C:/JV_Tools/pg63/{data,tls,runs}`, localhost:55472, `jp_vocab_test_audit_ok`·`_bad`, `jpva_admin`·`jpva_owner`·`jpva_audit`, 기존 PG 18.6 바이너리. 검토된 실행기로 한 차례만 진행하고, 경로가 있거나 포트가 사용 중이면 중단한다. 기존 CLI 비교의 `sslmode=require`는 이 비교에만 허용한다. 운영 접속·제품 보정·기존 CLI 운영 활성화는 포함하지 않는다.

**재실행 승인 기록 (2026-10-23 사용자, 프로젝트 채팅)**: P1 보정(집중 41개 독립 검토 통과) 뒤 같은 계획의 P2·P3·P4를 새 클러스터에서 한 차례 재실행하도록 승인했다. 대상·조건은 1차와 같다(`C:/JV_Tools/pg63`, 55472, 두 DB, 세 역할, PG 18.6). 1차 실행 기록(준비만 성공, 실제 감사 통과 0)은 그대로 보존한다. 코드 보정·임의 재실행은 포함하지 않는다.

## 0. 정적으로 확인한 사실 (2026-10-23, 읽기만)

| 항목 | 근거 | 이 계획에서의 뜻 |
| --- | --- | --- |
| 앱 스키마 생성 함수 | `app/database.py` `ensure_schema(connection)`(298행): PG면 `create_postgres_tables` → `drop_personal_log_card_fk` → `ensure_srs_schema` → `seed_dev_user` → 기본 덱 보정. 연결을 **인자로** 받는다. `init_db`·`initialize_database`(289·293행)만 `get_connection()`(= `DATABASE_URL`·`.env`)을 쓴다 | 준비는 `ensure_schema(AppPostgresConnection(관리 연결))`만 쓰고 `init_db`·`get_connection`은 부르지 않는다. 선례: `tests/test_srs_e3_fk_real.py` 82행 |
| 감사가 읽는 객체(단독 실행, 기준선 없음, 표 14 + 시퀀스 1) | `app/srs/invariant_audit.py` 95~108행 `_rows`: `vocab_items`·`user_word_progress`·`review_logs`·`lexeme_review_logs`·`srs_review_receipts`·`srs_migration_snapshots`·`srs_migration_runs`·`srs_card_deletions`·`srs_card_identity_flags`·`srs_evidence_restarts`·`account_write_blocks`·`account_recovery_runs`, `users`(108), `meaning_feedback.vocabulary_id`(176), `vocab_items` id 시퀀스 `last_value`(222~231, `pg_get_serial_sequence`·`pg_sequence`), I4 `identity.scan_identity`(`vocab_items`·`srs_card_deletions`·`review_logs`·`srs_review_receipts`·`srs_migration_snapshots`, 모두 위 목록 안). **정정(2026-10-23)**: 처음 안은 `migration._reduced_scope`가 `shared_deck_words`·`user_deck_subscriptions`를 읽는다고 적었으나 틀렸다. `_reduced_scope()`는 표를 읽지 않고, 두 표는 감사가 부르지 않는 `migration._authorized()`의 조회 대상이다. 확정 목록은 표 14개 + 시퀀스 1개다 | 기대 권한의 근거. 기준선 경로(`goals`·`stats_history_repository._review_rows`, `srs_user_settings`)는 단독 감사에서 실행되지 않는다 |
| 기존 로컬 CLI | `scripts/srs_invariant_audit.py --local-test-postgres`: `SRS_E_TEST_POSTGRES_OPT_IN=1` + `SRS_E_TEST_POSTGRES_URL`, `tests/_local_postgres_guard.validate_local_postgres_test_url`(호스트 localhost·루프백, DB 이름 `^jp_vocab_test(_[a-z0-9]+)*$`, 허용 키에 `sslmode`는 있고 `sslrootcert`는 없음, PG 대상 환경 변수 거부), 연결 옵션 읽기 전용·`search_path=public,pg_catalog`·15s/5s | 새 클러스터 DB 이름을 이 규칙에 맞추면 기존 CLI를 **완화 없이** 참조 경로로 쓸 수 있다. 다만 `sslrootcert`가 없어 `sslmode=require`(암호화, 인증서 미검증)만 가능하다 → 비교 전용, 2절의 보호 장치로 대상을 먼저 확인 |
| 포트·경로 | TCP 55470~55479 리스너 없음, `C:/JV_Tools/pg63` 없음(읽기만 확인) | 아래 값 |

## 1. 새로 준비할 대상 (6-2와 다른 값만)

| 항목 | 값 |
| --- | --- |
| 폴더 | `C:/JV_Tools/pg63/{data,tls,runs}` (있으면 중단) |
| 포트 | 55472, `listen_addresses = 'localhost'` (사용 중이면 중단) |
| DB | `jp_vocab_test_audit_ok`(정상 합성 자료), `jp_vocab_test_audit_bad`(합성 위반 자료, 대상 불일치 시험에도 사용). 둘 다 기존 CLI 이름 규칙을 만족 |
| 역할 | `jpva_admin`(initdb 관리 역할, SSPI만, 공급자에 넘기지 않음), `jpva_owner`(NOLOGIN, 앱 스키마·자료 소유), `jpva_audit`(LOGIN·SCRAM, 비소유, 슈퍼유저·생성·복제·RLS 우회 없음, 소속 없음) |
| HBA | 6-2와 같은 구조: 관리 역할 `hostssl … sspi`, `jpva_audit`만 두 DB에 `hostssl … scram-sha-256`, `hostnossl` 거부, 그 밖 거부 |
| TLS·인증서·비밀번호 | 6-2와 같은 방식(시험 CA·서버 인증서, CA 개인 키 즉시 삭제, SCRAM 검증값만 전송, 평문은 메모리) |

## 2. 재사용 범위

- 그대로 재사용: 6-2의 생성 근거 기록(`Record`, 즉시 기록), 연결 전·후 대상 확인(생성 기록 해시·postmaster PID·실행 파일·리스너 PID·루프백·포트·버전·DB OID·식별 행), 준비 실패·시험 장치 결함·제품 결함 구분과 중단, R2 정리(PID·경로·OID 대조 뒤 정지·삭제, 불일치면 멈춤), 실행기 종료 코드 규칙(모든 선택 검사가 통과·기록될 때만 0).
- 차이: 대상 상수(경로·포트·DB·역할)만 다르다. 6-2 장치(`tests/_ops_pg62.py`)는 대상이 모듈 상수에 고정돼 있으므로 3절의 최소 일반화가 필요하다.

## 3. 시험 코드 변경 범위 (다음 구현 단위, 시험 코드만)

- `tests/_ops_pg62.py`: 대상 상수를 묶은 대상 설정 하나를 받도록 최소 일반화(기본값은 6-2 그대로). 보호 규칙은 바꾸지 않는다. 기존 6-2 가짜 검사(`test_ops_pg62_guard.py`·`test_ops_pg62_cli.py`) 회귀로 확인.
- 새 `tests/_ops_audit_real.py`(명시 실행: `prepare`·`check`·`cleanup`, 탐색 대상 아님): 준비(앱 스키마·합성 자료·권한), 감사 검사표, 정리.
- 새 `tests/test_ops_audit_real_guard.py`: 새 대상의 보호 규칙·기대 권한 목록을 가짜 사실로 검사(실제 연결 없음).
- 제품 코드(`app/`·`scripts/_ops_*`·기존 CLI) 변경 없음.

## 4. 앱 스키마와 합성 자료

1. 관리 연결(SSPI, 각 DB)에서 `SET ROLE jpva_owner` 후 원시 연결을 `AppPostgresConnection`으로 감싸 `app.database.ensure_schema(conn)`을 호출하고 커밋한다. 앱 import 전 `APP_ENV=test`·`DATABASE_URL=sqlite:///:memory:`·`PYTHON_DOTENV_DISABLED=1`. `init_db`·`get_connection`·앱 시작 경로는 쓰지 않는다(호출되면 실패하도록 패치).
2. 같은 소유 역할로 합성 자료를 고정 SQL로 넣는다: 합성 사용자 2명(시드 `dev` 사용자 포함), 덱·단어 몇 개, 그에 맞는 `review_logs`·`user_word_progress`(정상 DB). 위반 DB는 같은 자료에 **한 가지 알려진 위반**(예: 없는 단어를 가리키는 `review_logs` 행 → I1 위반, 기존 `test_srs_e4_audit_real.py`의 손상 참조 사례와 같은 종류)을 더한다. 넣은 행 수·위반 종류를 생성 기록에 남긴다(내용은 합성값만).
3. 공급자 관측용 식별 표 `jp_vocab_ops_synthetic.db_identity` 1행(실행별 nonce)을 관리 역할이 만든다.
4. 권한: 0절 목록의 표에 `jpva_audit` SELECT, `vocab_items` id 시퀀스 SELECT, 식별 표 SELECT, 두 스키마 USAGE, DB CONNECT만. `PUBLIC`의 DB `CONNECT`·`TEMPORARY`는 회수. 그 밖 표는 권한 없음(객체 목록에는 남는다).
5. 정확한 표 목록과 SQL은 구현 단위에서 코드와 다시 대조해 확정하고 실행 전에 검토받는다. 실행 중 생기는 차이는 기대값을 바꾸지 않고 거부·중단으로 처리한다.

## 5. 기대 권한 프로필 (사전 작성)

- 객체 목록: `ensure_schema`가 만드는 관계·시퀀스(정적 목록 + 식별 스키마·표), 두 스키마, 대상 DB, 테이블스페이스 두 개. 실행 전에 문서로 확정한다.
- 실효 권한: 4절 4번의 SELECT·USAGE·CONNECT만. 쓰기·소유·생성 권한 없음.
- 관측 결과를 그대로 기대값으로 받아들이지 않는다. 사전 목록과 다르면 `observed_objects_mismatch`·`observed_privileges_*`로 감사 전에 거부되고, 그 차이는 결함 후보로 보고한다(목록 보정은 새 검토 대상).

## 6. 실제 경로와 검사표 (최소)

경로: 실행기가 6-2 보호 장치를 거친 드라이버로 `_ops_audit_run.run_synthetic_audit` 호출 → 실제 공급자 연결 → `AppPostgresConnection` → `read_snapshot` → `audit()`.

| # | 검사 | 기대 |
| --- | --- | --- |
| 1 | `audit_ok`: 새 경로 실제 감사 | I1~I5 `pass`, I6/I7 `not_evaluated` → 전체 `partial`, 종료 3 (실패나 완전 통과로 바꾸지 않음) |
| 2 | 같은 DB를 기존 `--local-test-postgres` 경로로(같은 `jpva_audit`, `sslmode=require`, 하네스가 대상 확인 뒤 그 호출 안에서만 환경 값 설정) | `checks` 상태·개수가 1과 같음. 기존 CLI 보호는 그대로 |
| 3 | `audit_bad`: 새 경로와 기존 경로 | 해당 검사 `fail`, 전체 `fail`, 종료 1, 두 경로 일치 |
| 4 | 범위 없음·서명 변조·다른 DB 승인·초과 권한(관리자가 `jpva_audit`에 쓰기 권한 일시 부여 후 원복) | 각각 `audit_scope_*`·`preflight_*`·`observed_identity_mismatch`·`observed_privileges_excess`, 감사 SQL 0(서버 세션·로그 확인), 원복 확인 |
| 5 | 감사 트랜잭션 설정 | `transaction_isolation = repeatable read`, `transaction_read_only = on`, `statement_timeout = 15s`, `lock_timeout = 5s`(감사 중 별도 읽기 탐침) |
| 6 | 쓰기 없음과 정리 | 감사 롤백 직전 `pg_current_xact_id_if_assigned()` NULL, 감사 전후 대상 표 행 수·`xmin` 불변, `commit` 0, 감사 뒤 해당 세션 0 |

- 5·6번의 "감사 중 탐침"은 시험 실행기가 `audit()`를 감싸 같은 연결에서 읽기만 하는 질의로 확인한다(제품 코드 변경 없음).
- 미검증 유지: 실제 롤백·닫기 장애, import 무결성(검사한 바이트와 import 파일의 결합), 응답 없는 서버·`connect_timeout`, 운영 신뢰 루트·실행 계정·실행 기록.

## 6-1. P1 구현 결과 (2026-10-23, 시험 코드·가짜 검사만)

- `tests/_ops_pg62.py`: 닫힌 대상 프리셋 `PG62`(기존 6-2 값, 모든 기본값)·`PG63_AUDIT`(`C:/JV_Tools/pg63`, 55472, `jp_vocab_test_audit_ok`·`_bad`, 관리 `jpva_admin`, 공급자 역할 `jpva_audit`만)를 두고, 대상 인자는 이 두 객체 자체만 받는다(같은 값의 다른 객체·문자열·CLI·환경 변수 거부). 6-2의 기본 호출·거부 규칙은 그대로다. 공급자 경로는 관리 역할을 기록에 적혀 있어도 거부한다.
- 새 `tests/_ops_audit_real.py`(명시 실행 `prepare`·`check`·`cleanup`, import만으로 외부 작업 없음): 기대 객체·권한을 코드 근거로 고정(`AUDIT_TABLES` 14, `vocab_items_id_seq`, `ensure_schema`가 만드는 표 26·시퀀스 24), 앱 스키마는 소유 역할로 `ensure_schema`(그동안 `get_connection`·`init_db` 호출은 실패), 연결 직후 대상 재확인(루프백·포트·버전·DB OID, 롤백 후 IDLE), 검사 c1~c4(정상 `partial`·종료 3과 15s/5s·REPEATABLE READ READ ONLY·xid NULL·자료 불변·세션 0, 기존 CLI 비교, 위반 I1 `fail` 일치, 범위·서명·다른 DB·초과 권한 거부와 감사 미호출), 결과는 기록된 뒤에만 통과, 실행기 종료 코드는 모든 검사 통과·기록 시에만 0. 기존 CLI 비교 경로의 `sslmode=require`는 비교 전용 한계다.
- 새 `tests/test_ops_audit_real_guard.py`: 가짜 검사 14개(프리셋 닫힘·변형 거부, pg63 보호 장치의 금지 포트·DB·역할·호스트·TLS 모드, 기록 PID·데이터 경로·해시 불일치, 6-2 기본값 보존, 관리 연결 범위, 연결 직후 재확인, 권한 목록과 두 표 제외의 코드 대조, 앱 표 목록의 스키마 소스 대조, 종료 코드 4사례·사용법 오류, import 무작업).
- P1 검토 보정(2026-10-23): ① 두 경로 비교는 `audit_version`·전체 `status`·`checks` 전체(집계값 포함)와 종료 코드를 그대로 비교한다. 새 경로에만 있는 `target`·`scope`는 비교 밖으로 분리하고, 값을 삭제·변환·정규화하지 않는다(정상·위반 자료 모두). ② 감사 연결만 `CommitTracker`로 감싸 `commit()` 호출과 `COMMIT`·`END` 문장을 앱 포장 경로·원시 경로 모두에서 세고, c1~c4는 0회를 요구한다. 호출은 그대로 전달해 트랜잭션·격리·롤백 의미를 바꾸지 않는다. 관리 연결(준비·자료·권한 변형/원복)은 감싸지 않아 별도로 취급한다. XID 미배정·자료 불변 검사는 그대로 따로 있다.
- P1 검토 보정 2(2026-10-23): `CommitTracker.cursor()`가 계측된 커서를 돌려준다. 일반·`with` 커서의 `execute`로 보낸 `COMMIT`·`END`(문자열과 `psycopg.sql` 객체, 끝 `;`·공백 차이 포함)와 `cursor.connection.commit()`도 같은 추적기에 센다. 지원 범위는 문장 전체가 `COMMIT`·`END`(`TRANSACTION`·`WORK` 붙은 형태 포함)인 경우뿐이며 SQL 파서는 아니다(`executemany`·여러 문장 묶음·`SAVEPOINT`·`PREPARE TRANSACTION`은 세지 않음). 호출은 그대로 전달한다. 관리 연결은 계속 계측하지 않는다.
- P1 검토 보정 3(2026-10-23): 연결 `execute()`가 돌려주는 커서도 같은 추적기의 `TrackedCursor`로 감싼다. 그 커서의 `execute(COMMIT/END)`와 `.connection.commit()`이 집계되고, 연결 `execute("COMMIT")`은 연결에서 한 번만 센다(반환 커서가 더 세지 않음). 문법 지원 범위는 그대로다.
- P2~P4(준비·실제 실행·정리)는 아직 승인 전이다.

## 7. 승인 항목 (최소)

| 항목 | 내용 |
| --- | --- |
| P1 시험 코드 | 3절 변경 구현·가짜 검사 (승인·구현, 보정 4회 뒤 독립 검토 41개 통과) |
| P2 준비 | `C:/JV_Tools/pg63` 클러스터(55472), TLS·인증서, 역할 3, DB 2, `ensure_schema`로 앱 스키마, 합성 정상·위반 자료, 식별 표, 권한 |
| P3 실행 | 6절 검사표 실제 실행(새 경로 + 기존 CLI 참조 경로, 관리자 권한 일시 변형·원복 포함) |
| P4 정리 | R2: 기록 대조 뒤 서버 정지, `pg63`·시험 키 삭제(불일치면 멈춤) |

- 권장: P1을 먼저 승인·검토한 뒤 P2~P4를 함께 승인. 운영 접속·운영 정책·기존 CLI 운영 연결은 포함하지 않는다.

실제 로컬 PG 감사 검증 준비 승인 대기.

## 8. 1차 실행 결과 (2026-10-23, 실행 ID 20261023T030158) — 상세는 REPORT 50절

- P2 준비 완료. P3는 c1에서 시험 장치 결함(`ModuleNotFoundError`)으로 중단해 실제 통과 0, c2~c4 미실행. P4 R2 정리 완료(서버 정지, `C:/JV_Tools/pg63` 삭제, 55472 리스너 없음). 보정·재실행은 새 승인이 필요하다.
- 실행기 보정(2026-10-23, P2~P4 재실행 승인 전): 실행기 모듈이 백엔드 경로를 `sys.path`에 더한다(경로만, app import 없음). `Harness.audit`는 더 이상 app을 import하지 않고 `_ops_audit_run`을 그대로 부른다. 감사 설정·XID 확인은 감사 연결의 `CommitTracker`가 감사의 첫 문장(`_require_snapshot`)과 감사 롤백 직전에 자기 커서로 읽는다. 새 프로세스 회귀(`tests/_ops_audit_real_probe.py`)로 경로·순서를 확인했다(실제 감사 SQL 검증은 아님). 상세는 REPORT 50-1절.
- XID 탐침과 롤백(2026-10-24, 코드보다 먼저 고정): 감사 롤백 직전의 XID 탐침은 진단일 뿐이다. 탐침이 성공하든 실패하든 원시 `rollback()`은 정확히 한 번 시도한다. 탐침 실패는 `xid=None`이나 정상으로 바꾸지 않고 `xid_probe_failed`(오류 종류 이름만)로 남기며, 그 검사는 시험 장치 결함으로 실패하고 후속 검사는 멈춘다. 오류 우선순위: ① 감사 중 중단(`KeyboardInterrupt`·`SystemExit`)은 정리 뒤 그대로 전파 ② 롤백 실패는 기존처럼 제품 경로로 올라가 실행기가 고정 코드로 보고 ③ 그와 별개로 탐침 실패가 기록돼 있으면 검사 판정은 시험 장치 결함이 우선한다(증거가 불완전하므로 제품 판정을 내리지 않음). 원문·SQL·비밀값은 남기지 않는다.

## 9. 2차 실행 결과 (2026-10-24, 실행 ID 20261024T030246) — 상세는 REPORT 51절

- P2 준비 완료, P3 c1~c4 실제 통과 4/4(실행기 종료 0), P4 R2 정리 완료. 1차 결과(8절)는 별개로 보존한다.

## 10. 마감 정리 (2026-10-24)

| 실행 | 실행 ID | 결과 |
| --- | --- | --- |
| 1차 | 20261023T030158 | 준비 성공, P3는 c1 시험 장치 결함(`ModuleNotFoundError`)으로 중단, **실제 통과 0**, R2 정리 완료 |
| 2차 | 20261024T030246 | 준비 성공, **실제 통과 4/4**(c1~c4), 실행기 종료 0, R2 정리 완료 |

- 원시 증거(비밀값·사용자 자료 없음, 합성 자료의 기록·대상·서버 로그만). 보존 위치는 저장소 밖의 이 작업 세션 임시 폴더 `C:/Users/mjwmm/AppData/Local/Temp/claude/C--JV-Project-jp-vocab-reader/31735110-cd12-4705-a3fe-8f284e68018b/scratchpad/`이다. 세션 임시 폴더라 장기 보존 장소가 아니므로, 인수하려면 사용자가 지정한 위치로 옮겨야 한다(파일 크기·SHA-256 앞 16자리로 대조).

| 폴더 | 파일 | 크기 | SHA-256(앞 16) |
| --- | --- | --- | --- |
| `pg63_evidence/`(감사 1차) | `record.json` | 3431 | 6d4077dfab2c3935 |
| | `target.json` | 609 | 17be2023785ad92d |
| | `server.log` | 4582 | a8459e02fbe72a23 |
| `pg63_evidence_run2/`(감사 2차) | `record.json` | 4313 | 03797944b7f2573d |
| | `target.json` | 608 | 2bec446391b17240 |
| | `server.log` | 9469 | 8389ce64e20ee087 |
| `pg62_evidence/`(6-2 1차, 참고) | `record.json`·`target.json`·`server.log` | 7004·636·21668 | ef7db1ce302b3944·b80254de1aa9c279·bfae1a82b7cc7d97 |
| `pg62_evidence_run2/`(6-2 2차, 참고) | `record.json`·`target.json`·`server.log` | 5234·636·9597 | 7a6ca135fce22636·3e3c0f67e7b0aa21·0f3cfd8dadfb0660 |

- 남은 제한(유지): 실제 롤백·닫기 장애 미재현, import 무결성(검사한 바이트와 import 파일의 결합) 미해결, `connect_timeout`·응답 없는 서버 미검증, commit 계측 미지원 형태(`executemany`·여러 문장 묶음·`PREPARE TRANSACTION`), 운영 신뢰 루트·실행 계정·실행 기록 미구현, 기존 CLI 운영 연결·운영 실행 미승인.

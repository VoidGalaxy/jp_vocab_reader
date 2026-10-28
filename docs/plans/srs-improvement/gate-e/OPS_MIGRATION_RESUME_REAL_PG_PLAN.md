# RS4 CLI `resume` 실제 로컬 PostgreSQL 검증 계획·RS4-1 기록 (2026-10-28 작성, 2026-10-28 검토 보정, 2026-10-28 RS4-1 구현)

**현재 상태(2026-10-28 마감)**: "PostgreSQL 18.6에서 개인 카드의 명시적 `resume` 경로 검증" 범위를 마감했다. 세 실행은 따로 집계한다(합산하지 않음): 1차(20261028T114240) G1 시험 장치 결함으로 중단·본 검사 0/25(12절), 2차(20261028T123027) 본 검사 25/25·당시 r3 비교값 자체는 기록 미보존(13절), 보완(20261028T131854) r1·r2·r3 3/3·여섯 딕셔너리 값 보존·사후 확인 통과(13-2절). 관문·사후 확인은 통과 수에서 뺐다. 증거 목록은 `OPS_MIGRATION_RESUME_REAL_PG_EVIDENCE.md`. 구독 카드 재개·실제 장애·실제 백업·복원·운영 실행은 범위 밖이고, Q5는 미결이다.

이전 상태: 2차 실행(실행 ID 20261028T123027, 13절)에서 준비 성공, G0·G1 통과, **본 검사 25/25 통과**, 실행기 종료 0, R2 정리 완료. 1차 실행(12절: G1 시험 장치 결함, 본 검사 0/25)과 합산하지 않는다. 운영 실행·Gate E 전체 완료가 아니며 Q5(증거 장기 보존)는 미결이다.

1차 직후 상태: RS4-1 구현·보정 마감, Q2(닫힌 목록 범위) 승인, RS4-2~RS4-4 1차 실행 완료(12절): 준비 성공, G0 통과, **G1에서 시험 장치 결함으로 중단, 본 검사 실행 0·통과 0·미실행 25**, R2 정리 완료. Q5(증거 장기 보존)는 미결이다.

이전 상태: Q1·Q4·Q6 확정, RS4-1 구현(11절), RS4-2~RS4-4 승인 전.

작성 당시 상태: 계획만 있다. 이 문서를 쓰는 동안 코드·권한·지문·기대값을 바꾸지 않았고, 검사 실행, PG 시작·접속, DB 접속, 키·인증서 생성, GRANT/REVOKE도 하지 않았다. 아래 RS4-1~RS4-4는 모두 **승인 전**이다. 기존 PG 장치(`C:/JV_Tools/pgdata-e2`·55432 등), 운영·Neon·`vocab.db`·사용자 키·기존 임시 폴더·C12 원시 증거는 대상이 아니다.

표기: **[코드 확인]**은 이번에 정적 읽기로 확인한 사실, **[C12 재사용]**은 `OPS_APPLY_REAL_PG_PLAN.md`(C12)와 그 실행기의 장치를 그대로 쓰는 것, **[신규]**는 RS4에서 새로 만들어야 하는 것, **[미검증]**은 아직 확인하지 못한 것이다.

선행 문서는 다시 쓰지 않고 차이만 적는다. 계약은 `OPS_MIGRATION_RESUME_PLAN.md` 4·4-1·5·6·9-2~9-4절, 합성 마감 범위는 같은 문서 15절을 따른다. 보호 장치·생성 기록·R2 정리는 C12 2·3·5·6절과 같은 규칙을 쓴다.

## 0. 합성 마감 결과와 RS4에서 처음 확인할 것

| 영역 | 합성에서 확인한 것 (RESUME_PLAN 15절) | RS4에서 실제 PG로 처음 확인할 것 |
| --- | --- | --- |
| 상태 사전 읽기 | SQLite 실제 제품 경로, 가짜 서버의 문장 순서 모델 | 공급자의 `SET TRANSACTION READ ONLY` 뒤 `read_status`의 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`가 실제 서버에서 받아들여지는지, 그 트랜잭션의 실제 격리 수준·읽기 전용 |
| 재개 제품 경로 | SQLite에서 실제 `apply_plan(existing_run_only)` | **공급자 연결 위의** 실제 제품 재개(합성에서는 한 번도 함께 실행하지 않음) |
| 잠금 아래 대조(P2) | SQLite `BEGIN IMMEDIATE` | `users ... FOR UPDATE` 아래 9개 고정값 재조회와 사전 조회 값의 일치, 변경 시 무쓰기 거부 |
| 권한 | 계약 표로 만든 가짜 카탈로그 | 재개 경로(상태 읽기, P2 재조회, 카드·마무리·실패 표시)가 계약 권한만으로 실행되는지, 누락·초과 거부 |
| 동시 재개 | 없음(계약 6절 표는 [미검증]) | 세 시점의 실제 결과와 잠금 대기의 서버 근거 |
| 백업 | C10 합성 서명 진술 | **변화 없음**: `restore_verified`·`backup_artifact_checked` = `false`, 실제 백업·복원 검증이 아님 |

## 1. 정적으로 확인한 코드 사실 (읽기만, 2026-10-28)

| 항목 | 근거 | 계획상 뜻 |
| --- | --- | --- |
| 상태 사전 읽기 | **[코드 확인]** `srs_migrate.read_status`: `connect(read_only=True)` 안에서 PG면 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`, 이어 실행 행 SELECT·snapshot SELECT(`id, user_id, card_kind, card_ref`). `ProductConnector._prepare`는 읽기 연결에서 먼저 `SET TRANSACTION READ ONLY`를 보냄 | 두 `SET TRANSACTION`이 한 트랜잭션의 첫 질의 전에 연달아 온다. 실제 서버 허용 여부·결과 설정이 r0의 대상 |
| P2 순서 | **[코드 확인]** `apply_plan` 첫 연결: `begin_card_write`(계정 잠금) → `_run_id`(행 없음 `migration_run_missing`, 범위·종류·설정 `migration_run_conflict`, `aborted` `migration_run_closed`, `started`·`failed` 아님 `migration_run_not_resumable`) → `run_progress_values` 대조(`migration_run_changed`) → `_resumable_cursor` → 창 확인 | 완료된 실행은 대조 **전에** `migration_run_not_resumable`. 기대값은 이 순서에서 정한다 |
| 카드 연결 | **[코드 확인]** 카드마다 새 연결·계정 잠금 → `status != aborted`·`stored_cursor == index`(아니면 `migration_cursor_conflict`) → 창 → snapshot 있으면 `already_applied` → 재판정 → 커밋 시 `summary_json`·`status = 'started'` 갱신 | `failed` 실행은 재개 첫 카드 커밋에서 `started`로 돌아간다. 동시 재개의 늦은 쪽은 카드 연결에서 거부될 수 있다 |
| 시작 판정 | **[코드 확인]** `run_resume` 13단계 `_Tracked`: 첫 쓰기 연결 안의 `SrsWriteError`는 4, 첫 연결 커밋·불확정·둘째 연결 이후 실패는 1·`after_start`·`uncertain`·`status_required` | 종료 코드 기대값의 근거 |
| 열 형식 | **[코드 확인]** `app/srs/schema.py`: `srs_migration_runs`의 `scope_json`·`summary_json`·`started_at`·`finished_at`은 PG에서도 `TEXT` | 9개 고정값은 문자열 원문의 해시이므로 PG 형 변환에 따른 차이는 없을 것으로 보이나 실제 확인 대상(r3) |
| 키 수명 | **[코드 확인]** C12 `Harness.start`는 실행(`check`)마다 시험 서명 키를 새로 만든다 | A₀·I₀와 재개 승인 Aₙ은 같은 실행 안에서 같은 시험 키로 서명돼야 한다. 최초 apply를 `prepare`에서 미리 할 수 없고 `check` 실행의 준비 관문에서 한다(3절) |
| 시퀀스 권한 | **[코드 확인]** `srs_migrate.WRITE_PRIVILEGES`에 두 시퀀스 USAGE 없음(S2·S3 마감) | RS4는 이 계약을 그대로 쓴다. 시퀀스 USAGE를 부여하지 않으며, 부여된 상태는 초과 권한 거부 대상 |

## 2. C12 장치의 재사용 범위와 대상 분리 (2026-10-28 검토 보정)

**정정**: 처음 판에서 쓴 "C12 장치를 import만으로 재사용"은 맞지 않다. **[코드 확인]** `tests/_ops_apply_real.py`는 모듈 상수 `T = g.PG65_APPLY`와 그로부터 만든 `TEMPLATE`·`CHECK_DB`·`BUSINESS_DATABASES`·`ADMIN_DATABASES`·`ADMIN`·`OWNER`·`READ`·`WRITE`·`BUSINESS_ROLES`·`VARIANTS`에 대상 결속 함수 대부분이 묶여 있다. 반면 `tests/_ops_pg62.py`의 공통 보호 함수(`Guard(..., target=)`, `admin_connect(..., target=)`, `single_run(target)`, `server_is_ours(pid, target)`, `postmaster_pid(target)`)는 이미 닫힌 프리셋을 인자로 받는다.

### 2-1. 그대로 쓸 수 있는 순수 도우미 (대상 값 없음)

`expected_objects(db)`(스키마 소스 목록만), `grant_statements(privileges, role)`, `first_word`, `rejection_stage`, `content_hashes`, `run_facts`, `attributed_changes`, `Pause`, `wait_blocked`, `race`, `run_recorded`, `InjectedFault`, `ticking`, `quality_label`, `name_qualities`, `_ops_pg62_real.run_check`·`CheckFailed`·`expect`. 이들은 import로 재사용한다.

### 2-2. 대상 분리가 필요한 코드

| 함수·상수 | PG65 결속 지점 | 재개에 필요한 차이 |
| --- | --- | --- |
| `expected_profiles`·`contract_grants`·`variant_statements`·`VARIANTS` | `BUSINESS_DATABASES`, `READ`·`WRITE` | 검사 DB·역할 이름, 재개용 변형 목록(읽기 역할 변형 포함) |
| `require_target_bound`·`require_ours`·`business_check`·`post_connect_check`·`admin` | `T`(포트·경로), DB·역할 목록, `ADMIN_DATABASES` | 대상 프리셋 |
| `Counts`·`Tracked`·`counted_connector`·`RunScopes` | `BUSINESS_ROLES`, **역할 판정이 `inputs.command == cli.APPLY_COMMAND`** | 재개 쓰기 단계(`resume`)가 읽기 역할로 잘못 계수된다. 역할은 명령 이름이 아니라 승인 단계의 접근(`read`/`write`) 또는 닫힌 쓰기 명령 집합으로 정해야 한다(실행기 결함 후보, RS4-1 수정 범위에 포함) |
| `hba`·`conf` | `TEMPLATE`·`ADMIN`·역할, SSPI 맵 이름 `pg65`. `conf`는 기존 코드가 `mock.patch.object(real, "T", T)`로 감사 실행기 전역값을 바꿔 씀 | 대상 값. 새 코드는 이 전역 교체 방식을 따라 하지 않는다 |
| `SEED`·`build_template`·`prepare`·`synthetic_ids` | `T`·`TEMPLATE`·`OWNER`·역할 | 대상 값(자료 형태는 같음) |
| `Harness`·`Case`·`g0_gate`·`template_qualities`·`quality_names` | `CHECK_DB`·역할·조회/적용 승인 v1 고정 | 재개는 v3 A₀·근거 결속·Aₙ·사슬(4-2) |
| `check`·`run_fixed`·`cleanup`·`main` | `T`, 검사 목록 | 재개 검사 목록 |

### 2-3. 두 안 비교

| 안 | 내용 | 장점 | 대가 |
| --- | --- | --- | --- |
| (A) 최소 분리 | 2-2의 대상 결속 부분을 **닫힌 배치 값 객체**(프리셋 `Target` + 원본·검사 DB 이름·역할·관리·소유 역할·SSPI 맵·변형 목록, `_ops_pg62`의 닫힌 목록에 있는 객체만 허용)를 명시 인자로 받는 함수로 바꾼다. C12 실행기는 PG65 배치 객체를 넘겨 같은 동작을 하고, 재개 실행기는 PG66 배치 객체를 넘긴다 | 보호 코드가 한 벌(두 실행기가 같은 대상 확인·관리 연결 제한을 씀), 역할 계수 결함을 한 곳에서 고침 | 실제 PG로 검증을 마친 C12 실행기를 고친다. PG65 실제 경로는 다시 실행하지 않으므로 보존 증거는 가짜 보호 검사뿐 |
| (B) 새 실행기에 대상 결속 부분 복제 | 재개 실행기가 2-2 함수들의 PG66 판을 따로 갖고, C12 실행기는 그대로 | C12 실행기·기록 무변경 | 보안 판정 코드가 두 벌로 갈라져 한쪽만 고쳐질 위험, 역할 계수 결함이 C12 쪽에 남음 |

- **권장: (A)**. 바꾸는 것은 대상 값을 인자로 받게 하는 것과 역할 판정뿐이며, 판정 규칙·문장·순서는 바꾸지 않는다. 모듈 전역값 교체·monkeypatch로 PG65를 PG66으로 바꾸는 방식은 쓰지 않는다. 기존 `conf`의 감사 실행기 전역값 교체를 `_ops_audit_real.conf`가 대상을 인자로 받는 형태로 바꿀지, 기존 그대로 둘지는 감사 실행기 변경이 되므로 RS4-1 착수 전에 따로 보고한다.
- 범용화 금지: 배치 값 객체는 `_ops_pg62`의 닫힌 목록 객체와 **동일 객체**일 때만 받으며(같은 값의 다른 객체 거부), 명령줄·환경 변수로 대상·DB·역할·포트를 받지 않는다. 관리 연결 허용 DB·문장 목록 제한은 배치마다 그대로 둔다.
- 이번에는 분리 코드를 구현하지 않는다.

### 2-4. (A)의 변경 파일과 PG65 보존 검사 범위 (RS4-1 예정)

| 파일 | 변경 |
| --- | --- |
| `backend/tests/_ops_pg62.py` | 닫힌 프리셋 `PG66_RESUME` 추가, 닫힌 배치 값 목록(PG65·PG66) 추가. 기존 프리셋 값 불변 |
| 새 공통 모듈(예: `backend/tests/_ops_real_layout.py`) | 2-2의 대상 결속 함수를 배치 인자 판으로 옮김. 역할 판정을 단계 접근 기준으로 |
| `backend/tests/_ops_apply_real.py` | PG65 배치 객체로 새 공통 함수를 부르도록 바꿈. 공개 명령(`prepare`·`check`·`check-d1`·`check-seq`·`cleanup`)·검사 목록·기대값 불변 |
| 새 `backend/tests/_ops_resume_real.py`·`test_ops_resume_real_guard.py` | 재개 실행기와 가짜 보호 검사 |
| (보고 뒤 결정) `backend/tests/_ops_audit_real.py` | `conf` 대상 인자화 여부 |

- PG65 보존 검사: 기존 `test_ops_apply_real_guard.py`(96개) 전부와 `_ops_pg62` 가짜 보호 검사(닫힌 목록 단언은 프리셋 추가에 따른 기대 목록 갱신만, 이유를 주석으로 기록), 감사 실행기를 바꾸면 그 가짜 보호 검사. 추가로 "PG65 배치로 만든 GRANT 문장·HBA·관리 연결 허용 목록·검사 DB 목록이 분리 전 출력과 바이트 단위로 같음"을 비교하는 검사를 둔다. 역할 판정 수정은 `apply` 경로 계수가 이전과 같음(읽기 `dry_run`, 쓰기 `apply`)을 단언한다. PG65 실제 PG 재실행은 하지 않으며, C12 기록·원시 증거는 그대로다.

### 2-5. 새로 필요한 부분 (어느 안이든)

- 최초 apply 입력을 v3 A₀ + `backup_evidence`로 만드는 경로, 최초·새 근거 쌍, Aₙ·이전 사슬·재개 입력(4-2).
- `run_resume` 호출 래퍼(같은 계측 문맥).
- 계측 래퍼(원래 함수를 그대로 호출하고 기록만): `srs_migrate.progress_values`, `migration.run_progress_values`, 그리고 5-2의 잠금 아래 읽기 기록·인계 정지점, 5-1-1의 r0 탐침.

## 3. 격리된 시험 대상 (RS4-2에서 생성, 승인 전)

| 항목 | 제안 값 |
| --- | --- |
| 폴더 | `C:/JV_Tools/pg66/{data,tls,runs}`(있으면 중단). 비밀 작업 폴더 `%LOCALAPPDATA%/Temp/jpv_pg66_<실행ID>/`(CA 개인 키·시험 서명 키, 사용 직후 삭제) |
| 포트 | 55502, `listen_addresses = 'localhost'`(시작 전 리스너 있으면 중단). 거부 목록: 55432·55462·55472·55482·55492 |
| 바이너리 | 기존 `C:/JV_Tools/pgsql-18.6`(읽기만) |
| 서버 설정 | C12와 같음(`ssl = on`, TLS 1.3 최소, SCRAM, `log_statement = 'none'`, 연결·종료 기록, `log_lock_waits` 끔) |
| 역할 | `jpvr_admin`(SSPI 관리, 공급자에 넘기지 않음), `jpvr_owner`(NOLOGIN, 스키마·자료 소유), `jpvr_read`·`jpvr_write`(LOGIN·SCRAM, 비소유, 계약 프로필만). 슈퍼유저·생성·복제·RLS 우회·소속 없음 |
| DB | 원본 `jp_vocab_test_resume_tpl`(업무 역할 CONNECT 없음) + 검사 DB `jp_vocab_test_resume_<ID>`(5절 ID 목록, 준비 단계에서 원본 복제, DB별 새 nonce). `PUBLIC`의 `CONNECT`·`TEMPORARY` 회수 |
| HBA | 관리 `hostssl … jpvr_admin … sspi`, 업무 역할 두 개만 검사 DB 목록에 `hostssl … scram-sha-256`, 그 밖 거부 |
| 식별 | 검사 DB마다 `jp_vocab_ops_synthetic.db_identity` 1행 |
| 프리셋 | `tests/_ops_pg62.PRESETS`에 닫힌 프리셋 `PG66_RESUME` 하나 추가(기존 네 프리셋 불변). 닫힌 목록을 단언하는 기존 가짜 검사의 기대 목록 갱신은 계약 변경에 따른 것으로 주석을 남긴다 |
| 작업 키 | `rs4-resume-1`(DB별로 독립, 다른 계정 경합용 키는 쓰지 않음) |

- 기존 자원과의 분리: 폴더·포트·역할 접두어(`jpvr_`)·DB 접두어(`jp_vocab_test_resume_`)·대상 문서(`PG66_TARGET.md`)가 C12(`pg65`·`jpvm_`·`jp_vocab_test_apply_`)와 모두 다르다. C12 R2로 `pg65`는 이미 없어야 하며, 남아 있으면 건드리지 않고 중단한다.
- 권한(계약 표 = `srs_migrate.READ_PRIVILEGES`·`WRITE_PRIVILEGES` 그대로, 두 시퀀스 USAGE 없음): 계약 튜플마다 GRANT 하나. 관측된 권한으로 이 목록을 고치지 않는다.

## 4. 준비 관문 (통과 수에 넣지 않음)

### 4-1. G0 (C12 재사용)
대상·식별·nonce 대조, 관측 대상 목록 = 스키마 소스, 업무 역할 관측 권한 = 계약 프로필, 의도한 후보 품질(카드 키 대응). 실패면 준비 실패.

### 4-2. G1 최초 실행 만들기 (`check` 실행 안, 시험 키 생성 직후) [신규]

검사 DB마다 아래 순서를 고정 코드로 수행한다. 명령줄·환경 변수로 고를 수 없다.

1. **입력 고정**: 그 DB의 배포 폴더 1개(`target.json`·manifest 파일 포함)를 만들고, 이 실행의 manifest 바이트를 최초 apply와 재개 모두에 그대로 쓴다(현재 manifest = I₀ manifest 조건). 배포 폴더를 다시 만들거나 파일을 바꾸지 않는다.
2. **I₀**: 조회 승인(`dry_run` 읽기 단계, 계약 읽기 프로필 지문, 계정 1개, 작업 키·입력). 시험 키로 서명.
3. **최초 계획 파일**: 실제 CLI `run_dry_run`(공급자 읽기 연결)으로 생성. 파일 바이트의 SHA-256(`artifact_sha256`)을 기록.
4. **최초 근거 E₀**: 합성 C10 문서(`evidence_id` E₀, `backup_id`·`artifact_sha256`·`taken_at`·`method`·대상 필드 고정, `restore_verified: false`), 시험 키 서명. 원문 SHA-256 기록.
5. **A₀**: 적용 승인 **v3**, `based_on` = I₀, `supersedes: null`, `plan` = 사전 검사가 낸 작업 계획 지문, 단계 `dry_run`(읽기)·`apply`(쓰기, `batch_size` 정확 결속), `backup_evidence.sha256` = E₀ 원문 해시. 서명.
6. **최초 apply**: 실제 CLI `run_apply`(공급자 경로)로 실행. 미완료 형태는 검사별로 고정한다.
   - `started`: 카드 3개, 배치 1 → 기대 종료 3, 커서 1.
   - `failed`: 카드 3개, 배치 3, 둘째 카드 연결에서 실제 연결 뒤 예외 **주입**(C12 g3 장치) → 기대 종료 1, 커서 1, 상태 `failed`(실패 표시 연결 성공 시). 주입으로 만든 상태임을 기록.
   - `completed` 등 상태 검사용은 5절 각 항목의 준비 열대로.
7. **재개 입력**: 새 근거 E₁(E₀와 결속 필드 같고 `evidence_id`만 다름, 시험 키 서명), Aₙ(v3 적용, `supersedes` = A₀, `based_on` = I₀, 같은 manifest·DB·작업, 단계 `status`(읽기, `jpvr_read`, 계약 읽기 프로필)·`resume`(쓰기, `jpvr_write`, 계약 쓰기 프로필, `args.batch_size` 정확 결속)), 이전 사슬 `(ChainLink(A₀, 서명, I₀, 서명),)`. Aₙ에 `backup_evidence`를 넣는 경우는 E₁ 해시만.
8. **관리 연결 확인**(제품 경로 밖, 읽기만): 실행 행 1개(`run_key`), `mode = apply`, 상태·커서·결과 목록이 6의 기대와 같음, `md5(scope_json)` = 최초 계획 파일로 미리 계산한 값(C12 8-2 방식), snapshot 수·카드 = 커밋된 `applied` 카드, 커밋된 카드의 `srs_card_version` 증가 1, 남은 카드·다른 계정·범위 밖 행 해시 = G0 기록, 업무 세션 0·`idle in transaction` 0, 앱 스키마 객체·권한 = G0 기록.
9. 위 결과(해시·계수·상태)를 기록하고 디스크 재읽기로 확인.

- G1 하나라도 실패하면 **준비 실패**: 이후 검사를 실행하지 않고 실행기 종료 1. 자동 재시도·현장 보정 없음.
- G0·G1은 기록하되 통과 수에 넣지 않는다.

## 5. 최소 실제 검사표

### 5-0. 판정 용어

C12 4-0의 네 단계(① 연결 생성 ② 제품 인계 ③ 업무 문장·`COMMIT` ④ 커밋된 변경)를 역할별로 따로 센다. 재개는 읽기 역할(상태 사전 읽기)과 쓰기 역할을 구분한다. 결과의 출처를 셋으로 나눠 적는다.

- **서버 결과**: 권한 오류 SQLSTATE, 실제 잠금 대기, 실제 세션 설정, 실제 행 내용.
- **연결 전 CLI 거부**: 사전 검사·입력·근거·계획·결속 판정(두 역할 ① 0).
- **시험 장치 주입**: 실행기가 넣은 예외·시계·정지점. 주입 결과는 실제 장애 증거가 아니다.

거부 위치별 기대(C12와 같음): 연결 전 거부는 해당 역할 ① 0, 관측 후 거부는 ② 0·③ 0·④ 0, 제품 잠금 아래 거부는 쓰기 ② 1·③ 잠금·조회 문장만(`INSERT`·`UPDATE` 0)·`COMMIT` 0·④ 0. 무변경은 행 내용 기준이며 잠금 기록·통계·WAL은 포함하지 않는다. 기대값은 실행 전에 고정하고 결과에 맞춰 바꾸지 않는다.

### 5-1. 검사표

| ID | 항목 | 준비(G1 형태) | 절차 | 기대 결과 | 계측·증거 |
| --- | --- | --- | --- | --- | --- |
| r0 | 상태 읽기 세션 설정·문장 순서 | `started` | 재개 1회(r1과 같은 실행, 별도 DB 아님). 탐침 위치는 5-1-1 | 읽기 인계 연결의 인계 뒤 업무 문장이 정확히 `SET TRANSACTION READ ONLY` → `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` → 실행 행 SELECT → snapshot SELECT, 서버 오류 없음. 탐침: `transaction_isolation = repeatable read`, `transaction_read_only = on`. 읽기 연결 `INSERT`·`UPDATE` 0 | 문장 첫 낱말·순서(원문 매개값 없음), 탐침 값. 서버가 둘째 `SET TRANSACTION`을 거부하면 **제품 결함 후보**로 기록하고 기대값을 바꾸지 않는다(7절 중단 규칙 적용) |
| r1 | 부분 처리 실행 재개 | `started`, 커서 1/3 | 배치 3 재개 | 종료 0, `already_applied` 1·`applied` 2, 앞 카드 값·snapshot(id 포함) 그대로, 남은 카드만 처리, 실행 행 `completed`·커서 3, `restore_verified`·`backup_artifact_checked` false | ①: 읽기 1·쓰기 1+2+1, ④ 차이 = 남은 카드 2·snapshot 2·실행 행만 |
| r2 | `failed` 실행 재개 | `failed`(주입으로 생성), 커서 1/3 | 배치 3 재개 | 종료 0, 첫 카드 커밋 시 상태 `started`로 복귀 뒤 `completed`, 앞 카드·snapshot 보존 | r1과 같음. G1의 주입 사실을 같이 기록 |
| r3 | 9개 고정값의 잠금 아래 일치 | r1·r2와 같은 실행 | 계측 래퍼 | 사전 조회 `progress_values` = 첫 쓰기 연결의 잠금 아래 `run_progress_values` = 관리 연결 독립 계산(재개 전 시점). P2 통과 | 세 값의 기록(해시·id·상태 문자열만) |
| r4a | 사전 조회 뒤 요약 변경 | `started` | 상태 읽기 연결 종료 뒤·첫 쓰기 연결 요청 전 훅에서 관리자가 `summary_json`을 같은 내용의 다른 직렬화로 바꿈(기록한 변경) | `migration_run_changed` 4, 제품 잠금 아래 거부, 업무 쓰기 0 | ④는 관리자 변경만 차이 |
| r4b | 사전 조회 뒤 snapshot 추가 | `started` | 같은 훅에서 관리자가 이 실행 snapshot 1행 추가 | 같음 | 같음 |
| r4c | 사전 조회 뒤 정상 커서 전진 | `started`, 커서 1/3 | 같은 훅에서 다른 재개 호출 B(배치 1)를 끝까지 실행(커서 2) | A: `migration_run_changed` 4, A에 귀속되는 변경 0. B: 종료 3, 정상 변경(위반으로 세지 않음) | 5-2 귀속 규칙 |
| r5 | 권한 충분성·누락·초과 | `started` | 충분성: r1의 성공. 각 변형을 관리자가 일시 적용 → 재개 → 원복 확인: 읽기 역할 `srs_migration_runs` SELECT 회수(누락), 읽기 역할 `srs_migration_runs` INSERT 부여(초과), 쓰기 역할 `srs_migration_runs` `UPDATE(status)` 회수(누락), 쓰기 역할 `users` 표 단위 UPDATE 부여(초과), 쓰기 역할 두 시퀀스 USAGE 부여(초과, 시퀀스 제거 계약 확인) | 읽기 변형: `observed_privileges_*` 4, 읽기 관측 후 거부(쓰기 ① 0). 쓰기 변형: `observed_privileges_*` 4, 첫 쓰기 관측 후 거부(쓰기 ② 0), 전체 DB 불변. 역할 불일치(단계 역할과 다른 업무 역할의 DSN)는 거부 단계·코드를 RS4-1에서 코드 근거로 미리 고정하고(연결 전 판정인지 관측 후 `observed_role_mismatch`인지), 관측된 결과로 정하지 않는다 | 원복 뒤 관측 = 계약 프로필, 원복 실패 즉시 중단 |
| r6 | 결속 거부 | `started` | 실제 CLI로: 다른 최초 계획 파일(제품 지문 같고 `reconversion`만 다름) `resume_plan_not_initial`, 이전 사슬 없음 `resume_chain_required`, A₀ 서명 변조 `preflight_*`, E₀ 해시 불일치 `resume_initial_evidence_mismatch`, E₁ 결속 필드 다름 `resume_backup_evidence_mismatch`, 같은 `evidence_id` 재사용 `resume_backup_evidence_mismatch`, Aₙ v2 `approval_format_not_v3`. 별도 DB r6b: A₀를 `backup_evidence` 없이 만든 미완료 실행 → `resume_backup_binding_missing` | 각 정확한 코드 4, 호출 추적이 목표 단계까지 일치, **두 역할 ① 0**, 업무 쓰기 0, 전체 DB 불변 | C12 d1 방식 호출 추적 |
| r7 | 상태별 거부·보고 | DB별: r7a `completed`(실제 끝까지 apply), r7b 커서 끝·`started`(관리자 상태 변경 기록), r7c `aborted`(관리자), r7d 요약 손상(관리자), r7e 다른 계정 소유(다른 계정 계획의 실행 행) | 재개 1회씩 | r7a `migration_run_completed` 4, r7b `cursor_end_not_completed` 보고 6, r7c `migration_run_closed` 4, r7d `inconsistent` 보고 6(사유 코드는 손상 형태에서 미리 고정), r7e `resume_target_not_found` 4. 모두 읽기 ① 1·쓰기 ① 0, DB 불변 | 관리자 변경은 준비 기록에 남기고 비교에서 뺌 |
| r8 | 시각·기간 구분 | `started` | ① Aₙ 짧은 유효 기간 + 시계 주입으로 시작 전 만료 ② 같은 방식으로 상태 읽기 뒤 첫 쓰기 전 만료 ③ 관리자가 `started_at`을 31일 전 문자열로 바꿈(기록) ④ E₁만 `recheck`에서 만료(시계 주입) | ① `preflight_approval_expired` 4·두 역할 ① 0 ② 같은 코드 4·읽기 ① 1·쓰기 ① 0 ③ `migration_resume_window_closed` 4·쓰기 ① 0(CLI 사전 판정, 앱 프로세스 실제 시각) ④ `backup_evidence_expired` 4·쓰기 ① 0 | 셋은 서로 대신하지 않음. 창 경계(정각) 재현은 하지 않음(합성 SQLite에서 확인) |
| r9a | 커밋 뒤 후속 연결 거부(실제) | `started`, 커서 1/3 | 재개 배치 2, 첫 남은 카드 커밋 뒤 관리자가 쓰기 역할 카드 열 UPDATE 1개 회수(C12 g2 방식) | 1·`after_start`·`uncertain`·`status_required`, 커밋된 카드 유지, 나머지 불변, 원복 확인 | 서버 결과(관측 후 거부) |
| r9b | 중간 실패(주입) | `started` | 둘째 남은 카드 연결에서 연결 뒤 예외 주입 | 1·`after_start`, 앞 커밋 유지, 실행 행 `failed`(실패 표시 연결 성공 시) | **주입** |
| r9c | 마무리 실패(주입) | `started` | 마무리 연결 열기에서 예외 주입 | 1·`uncertain`, 모든 카드 커밋, 실행 행 `started` | **주입** |
| h | 다른 계정·범위 밖 불변, 세션 정리 | 모든 DB | 각 검사 뒤 공통 | 다른 계정·범위 밖 행 해시 불변, 업무 세션 0, `idle in transaction` 0(`pg_stat_activity`) | 각 검사 판정에 포함 |

- 자동 재시도·다음 카드 자동 진행 없음. `status_required` 다음 단계는 실행하지 않는다.
- 권한 일시 변형은 관리 연결의 닫힌 GRANT/REVOKE 목록으로만 하고, 원복 뒤 관측이 계약 프로필과 같아야 다음 검사로 간다.

### 5-1-1. r0 탐침 위치와 실패 처리 (실행기 계측 설계, 실제 PG 미확인)

- 두 `SET TRANSACTION` 사이에는 어떤 탐침 문장도 넣지 않는다. 첫째는 `ProductConnector._prepare`가, 둘째는 `read_status`가 보내며, 그 사이와 업무 SELECT 사이에도 실행기 문장은 없다.
- 위치: 읽기 인계 연결의 실행기 감싸개(`HandOver.__exit__`)에서, 제품 `with` 본문이 **예외 없이** 끝난 직후, 원래 컨텍스트의 종료(커밋·닫기)를 부르기 **전**. 이때 `read_status`는 실행 행(`fetchone`)과 snapshot(`fetchall`)을 이미 읽어 자기 값으로 바꿨고, 같은 읽기 트랜잭션이 아직 열려 있다.
- 방법: 업무 커서를 쓰지 않고 원래 연결에서 **새 커서**를 열어 `SAVEPOINT rs4_probe` → `SELECT current_setting('transaction_isolation'), current_setting('transaction_read_only')` → `RELEASE SAVEPOINT rs4_probe`. 탐침 문장은 업무 문장 계수(③)와 r0의 순서 판정에서 빼고 따로 기록한다. 업무 커서의 결과를 소비하지 않으며, 같은 트랜잭션 안이므로 새 트랜잭션의 설정을 읽지 않는다.
- 탐침 실패: 실패하면 `ROLLBACK TO SAVEPOINT rs4_probe`를 시도해 트랜잭션을 탐침 전 상태로 돌리고, 성공·실패와 무관하게 **원래 컨텍스트 종료(커밋 또는 롤백·닫기)를 반드시 한 번 부른다**. 탐침 실패는 r0의 시험 장치 결함으로 기록한다. `ROLLBACK TO SAVEPOINT`도 실패하면 원래 종료가 커밋 실패로 보고할 수 있으므로, 그 실행의 제품 결과는 판정하지 않고 시험 장치 결함으로 중단한다(7절).
- 우선순위: 제품 본문이 예외·중단으로 끝나면 탐침을 실행하지 않고 원래 종료로 넘긴다(제품 예외가 그대로 전파). 원래 종료의 예외·중단은 탐침 기록보다 우선해 그대로 전파한다. 탐침 오류는 제품 예외를 대체하거나 연결하지 않으며, 별도 기록 필드(`probe_error`, 고정 코드)로만 남는다.
- 이것은 설계이며, `SAVEPOINT`·`current_setting` 탐침이 실제 PostgreSQL에서 의도대로 동작하는지는 아직 확인하지 않았다.

### 5-2. 동시 재개 (계약 6절 표의 세 시점, 2026-10-28 검토 보정)

**보정**: 처음 판의 c2b와 c3b는 정지점(A의 마지막 남은 카드 연결 잠금 직후)과 B의 사전 조회 커서(2)가 같아 중복이었다. 또 A의 마무리 연결과 B의 첫 연결 중 누가 먼저 잠금을 얻는지가 정해지지 않아 결과가 둘로 갈렸다. 아래 배선은 **두 번째 정지점**으로 순서를 고정해 사례마다 단일 결과를 요구한다. 허용 집합은 두지 않는다.

정지점 두 종류(실행기 계측, 제품 코드 불변):
- **문장 뒤 정지**(C12 `Pause`): 지정 연결에서 계정 잠금 문장(`SELECT id FROM users WHERE id = … FOR UPDATE`)이 반환된 직후 멈춤. 그 연결이 잠금을 쥔 상태.
- **인계 정지**(신규): 지정 실행·역할의 n번째 쓰기 연결이 제품에 인계되는 순간(`HandOver.__enter__`, 업무 문장 전) 멈춤. 잠금을 쥐지 않은 상태.

| ID | 목적 | G1 | 배선(순서 고정) | B가 잠금 아래 처음 읽는 상태 | 기대 |
| --- | --- | --- | --- | --- | --- |
| c1 | 같은 시작 커서를 읽은 두 호출 | `started` 커서 1/3 | A(배치 3) 시작. A의 첫 남은 카드 연결(카드 1) 잠금 뒤 문장 정지 P1, A의 다음 쓰기 연결(카드 2)에 인계 정지 P2 설치 → B 상태 읽기(커서 1) → B 첫 쓰기 연결 잠금 대기 → 대기 증명 → P1 해제(A가 카드 1 커밋, A는 P2에서 멈춤) → B 잠금 획득·첫 연결 종료 → P2 해제 | `started`, 커서 2 | B `migration_run_changed` 4(제품 잠금 아래 거부, B ② 1·`INSERT`·`UPDATE` 0·`COMMIT` 0). A 종료 0 |
| c2 | 앞 호출 커밋 뒤 전진한 커서를 읽고, 그 뒤 앞 호출이 더 전진 | `started` 커서 1/3 | A(배치 3). A의 둘째 남은 카드 연결(카드 2) 잠금 뒤 문장 정지 P1, A의 다음 쓰기 연결(마무리)에 인계 정지 P2 → B 상태 읽기(커서 2) → B 잠금 대기 → 대기 증명 → P1 해제(A 카드 2 커밋, 마무리는 P2에서 멈춤) → B 잠금 획득·첫 연결 종료 → P2 해제 | `started`, 커서 3(마무리 전) | B `migration_run_changed` 4. A 종료 0 |
| c2s | 전진한 커서를 읽고 앞 호출이 멈춰 있음(순차) | `started` 커서 1/3 | A(배치 1) 종료(3, 커서 2) → B(배치 3) | `started`, 커서 2 = 사전 조회 값 | B 종료 0, `already_applied` 2·`applied` 1, A 커밋 보존 |
| c3 | 앞 호출 완료 뒤 잠금을 얻는 호출 | `started` 커서 2/3 | A(배치 3). A의 마지막 카드 연결(카드 2) 잠금 뒤 문장 정지 P1 → B 상태 읽기(커서 2, 재개 가능), B의 첫 쓰기 연결에 인계 정지 Q1 → P1 해제 → A가 카드·마무리까지 끝나고 종료 0, A의 업무 세션 0 확인 → Q1 해제 | `completed`(`finished_at` 있음) | B `_run_id`에서 `migration_run_not_resumable` 4(대조보다 먼저, 1절 P2 순서). 잠금 대기는 주장하지 않음 |
| c3r | 앞 호출의 마무리 전 사전 조회 | `started` 커서 2/3 | A(배치 3). A 마무리 연결 잠금 뒤 문장 정지 P1 → B 상태 읽기 → P1 해제 | (사전 조회만) `started`, 커서 3 | B `cursor_end_not_completed` 보고 6, 쓰기 ① 0(제품 호출 없음). A 종료 0 |
| c3c | 앞 호출 완료 뒤 시작 | `started` 커서 2/3 | A 종료 0 → B | (사전 조회만) `completed` | B `migration_run_completed` 4, 쓰기 ① 0 |

- 증거 구분:
  - **대기 증거**(c1·c2): B 첫 쓰기 연결의 PID에 대해 `pg_blocking_pids` = A의 해당 카드 연결 PID, `pg_locks`(대기 항목의 `locktype`·`mode`·`granted = false`, 보유 항목). 대기 증명이 제한 시간 안에 안 되면 시험 장치 결함·중단. 시각 순서·sleep은 대기 증거가 아니다.
  - **잠금 아래 읽기 증거**(c1·c2·c3): B 첫 쓰기 연결 안에서 제품이 실제로 읽은 값. ⓐ `TrackedCursor`가 실행 행 조회(`SELECT * FROM srs_migration_runs WHERE run_key = …`)의 `fetchone` 반환 행에서 `status`·`finished_at` 유무·`summary_json`의 SHA-256과 커서만 기록(같은 객체를 그대로 돌려줌) ⓑ `migration.run_progress_values` 래퍼가 반환값을 기록(대조까지 갔을 때만) ⓒ 제품 예외 코드. 기대 상태는 그 시점 관리 연결 독립 계산(A 커밋 직후 값)과 대조한다.
  - **정지점 증거**: P1·P2·Q1 도달·해제 순서와 그때의 연결 PID. 해제 순서는 배선의 일부이며 대기 증거를 대신하지 않는다.
- 판정: 반환 코드만으로 분기 원인을 추정하지 않는다. 기대 코드 + 잠금 아래 읽기 증거의 상태·커서 + (c1·c2) 대기 증거가 모두 기대와 같아야 통과다. 하나라도 다르면 실패(7절).
- 경합 귀속 규칙(C12 4-0 ⓐ~ⓓ를 재개에 맞춤): ⓐ 해당 키 실행 행 1개, `scope_json` MD5 = 최초 계획에서 미리 계산한 값 ⓑ snapshot 수 = `applied` 수(G1 + A) ⓒ 카드별 `srs_card_version` 증가가 정확히 1회 ⓓ 거부된 호출(B)의 인계 연결 `COMMIT` 0. 상대 실행(A)의 정상 변경은 위반으로 세지 않는다.
- 기록 필드(경합 사례별, 비밀·원문 매개값 없음): 실행별 `pre_read`(사전 조회 9개 값 해시·상태·커서), `under_lock`(ⓐ·ⓑ), `code`·`exit`·`phase`, 역할별 ①~③, 정지점 도달·해제 순서와 PID, `blocking`(대기 PID·보유 PID·`pg_blocking_pids` 결과·`pg_locks` 항목), 관리 연결 독립 계산 값, 귀속 판정 ⓐ~ⓓ.

### 5-3. 검사 DB 목록 (HBA·프리셋에 고정할 제안)

`jp_vocab_test_resume_` + `r1`·`r2`·`r4a`·`r4b`·`r4c`·`r5`·`r6`·`r6b`·`r7a`·`r7b`·`r7c`·`r7d`·`r7e`·`r8`·`r9a`·`r9b`·`r9c`·`c1`·`c2`·`c2s`·`c3`·`c3r`·`c3c`(23개). r0·r3은 r1·r2 실행에서 함께 판정하되 검사 항목으로는 따로 집계한다. 실행 순서는 이 목록 순서로 고정하고, 최종 목록은 RS4-1에서 검토받는다.

## 6. 증거와 집계

- 집계: G0·G1·사후 확인은 기록하되 통과 수에 넣지 않는다. 각 검사는 결과 기록이 디스크에 저장되고 재읽기로 확인됐을 때만 통과로 센다.
- 기록 항목(비밀값·원문 SQL 매개값 없음): `record.json`(생성 기록·G0·G1·검사 결과·역할별 ①~③ 계수·거부 위치·출처 구분), `target.json`, `server.log`(연결·종료만), 경합 기록(5-2 기록 필드: 대기 증거는 c1·c2, 잠금 아래 읽기 증거는 c1·c2·c3), 권한 변형·원복 전후 관측, 9개 고정값 비교(r3), 세션 탐침(r0).
- 실행별로 폴더를 나누고(`pg66_evidence_<실행ID>/`), R2 전에 이 세션 임시 폴더로 복사한 뒤 파일별 크기·전체 SHA-256을 REPORT에 남긴다. **장기 보존 위치·기간은 미결**로 유지한다(사용자 지정).
- 표현 한계:
  - 실제 커밋 응답 유실, OS·프로세스 장애, 네트워크 단절, 서버 강제 종료는 재현하지 않는다. r9b·r9c·G1 `failed` 생성은 **주입**이며 이를 실제 장애의 대체 검증이라고 쓰지 않는다.
  - C10은 합성 서명 진술이다. `restore_verified`·`backup_artifact_checked`는 `false`로 남고, RS4 결과를 실제 백업·복원 검증으로 표현하지 않는다.
  - 결과는 PostgreSQL 18.6 로컬 단일 서버의 사실이다. 운영 준비 완료를 뜻하지 않는다.

## 7. 실패 분류·중단·정리 (2026-10-28 검토 보정)

- **통과와 실패의 구분**: 계약대로 거부되는 음성 사례(예: r4의 `migration_run_changed`, r6의 결속 거부)는 기대 코드·단계·계수가 모두 맞으면 **검사 통과**다. 실패는 기대와 다른 결과다(다른 코드, 다른 거부 단계, 기대하지 않은 연결·인계·업무 쓰기, 증거 불일치).
- **실패 종류**(모두 그 검사를 실패로 기록):
  - 준비 실패(클러스터·TLS·역할·DB·스키마·자료·G0·G1)
  - 시험 장치 결함(실행기 예외, 탐침 실패, 원복 실패, 정지점·대기 증명 실패, 귀속 판정 불가)
  - 제품 결함 후보(기대와 다른 제품·CLI 결과)
  - 기록 실패(결과 저장 또는 재읽기 확인 실패)
- **중단**: 종류와 관계없이 첫 실패에서 **후속 검사를 모두 중단**한다(제품 결함 후보도 계속하지 않는다). 실행기 종료 코드는 1이다. 선택한 모든 검사가 통과·기록됐을 때만 0, 사용법 오류는 2.
- **집계**: 실패 전까지 결과 저장과 디스크 재읽기가 확인된 검사만 통과로 센다. 실패한 검사는 실패 1, 그 뒤 항목은 **미실행**으로 기록한다(통과·실패 어느 쪽에도 넣지 않음). G0·G1·사후 확인은 통과 수에 넣지 않는다.
- 제품·CLI·공통 모듈은 고치지 않고 기대값도 바꾸지 않는다. 현장 보정·임의 재실행 금지, 재실행은 새 승인으로만 한다.
- **중단과 R2 정리는 별개다**: 검사 중단은 `check` 명령의 종료일 뿐 정리를 하지 않는다. 정리는 별도 명령 `cleanup`(RS4-4)으로만 하며, 실패 뒤에도 생성 기록과 현재 관측(PID·실행 파일·리스너·데이터 경로·`system_identifier`·DB/역할 OID·업무 세션 0)이 모두 일치할 때만 서버 정지와 이번 대상 폴더 삭제를 한다. 하나라도 다르면 아무것도 지우지 않고 상태만 기록해 사용자 판단을 기다린다. 중단 시점의 정지점·스레드는 `check` 안에서 해제·종료 확인을 먼저 하고, 확인되지 않으면 그 사실을 기록한다(정리 단계에서 프로세스 검색·강제 종료는 하지 않는다).

## 8. 승인 단위 (모두 승인 전)

| 단위 | 정확한 범위 | 하지 않는 것 |
| --- | --- | --- |
| **RS4-1** 시험 코드·가짜 보호 검사 | 2-4절 (A) 최소 분리(대상 결속 함수의 배치 인자화, 역할 판정 수정, C12 동작 보존), `PG66_RESUME` 프리셋·배치, 새 `tests/_ops_resume_real.py`(G1·재개 입력·검사표·계측 래퍼·정지점·r0 탐침·정리, 실제 연결 코드는 있으나 실행 안 함), 새 `tests/test_ops_resume_real_guard.py`(프리셋·배치 닫힘, 금지 포트/DB/역할, 권한 = 계약 상수(시퀀스 USAGE 없음), 검사 DB 목록, 7절 중단·집계·미실행 기록, 거부 위치 집계, 경합 정지점 순서·잠금 아래 읽기 기록, 탐침 실패 시 원래 종료 보존, 기록 재읽기, import 무작업). 회귀는 2-4절 PG65 보존 검사와 RS3 집중 검사만 | `app/`·`scripts/` 변경, PG 실행·접속, 키·인증서 생성 |
| **RS4-2** 준비 | `C:/JV_Tools/pg66` initdb·설정·HBA·TLS(CA 키 즉시 삭제)·역할 4·원본·검사 DB·`ensure_schema`·합성 자료·식별 행·계약 권한 | 기존 PG·DB 변경, 운영 접속 |
| **RS4-3** 실제 검사 | `check` 한 차례: 시험 키 생성, G0·G1, 5절 검사표, 승인된 권한 일시 변형(r5·r9a)과 원복, 관리자 자료 일시 변경(r4a·r4b·r7b~r7e·r8 ③, 기록 후 비교에서 제외), 정지점·잠금 관측(c1~c3), 주입(G1 `failed`·r9b·r9c) | 기대값 수정, 제품 보정, 임의 재실행 |
| **RS4-4** R2 정리 | 기록 대조(PID·실행 파일·리스너·데이터 경로·`system_identifier`·DB/역할 OID·업무 세션 0)가 맞을 때만 서버 정지, `pg66`·비밀 작업 폴더만 삭제, 증거 복사·크기·SHA-256 기록 | 기록과 다른 대상 정리, `CASCADE`, 개별 `DROP` |

- 고정 진입점: `python tests/_ops_resume_real.py prepare` → `check` → `cleanup`. 명령줄·환경 변수로 검사·DB·역할·포트를 고를 수 없다. CLI `main`의 `resume`은 계속 `connection_not_available` 4이고 운영 모드는 거부된다. 실제 드라이버는 실행기에만 있다.

## 9. 필요한 결정 (승인 아님)

| 번호 | 질문 | 권장 |
| --- | --- | --- |
| Q1 | 대상 값(폴더 `pg66`, 포트 55502, 역할 `jpvr_*`, DB `jp_vocab_test_resume_*`) | 제안 값 그대로 |
| Q2 | 관리자 자료 일시 변경으로 상태를 만드는 검사(r4a·r4b·r7b~r7e·r8 ③)를 허용할지 | 허용. 실제 경로로 만들 수 없는 상태만, 변경 문장을 닫힌 목록으로 고정하고 기록 |
| Q3 | (5-2 보정으로 대체) 결과가 갈리는 경합 포함 여부 | Q6으로 대체: 단일 결과로 고정 |
| Q4 | C12 장치 재사용 방식 | 2-3절 (A) 최소 분리. 감사 실행기 `conf` 인자화 여부는 RS4-1 착수 전 따로 보고 |
| Q5 | 증거 장기 보존 위치·기간 | 미결 유지(사용자 지정) |
| Q6 | 경합을 정지점 두 개로 단일 결과에 고정할지(5-2) | 고정. 결과가 갈리는 허용 집합은 두지 않음 |

## 10. 다음 최소 구현 단위

**RS4-1**(시험 코드·PG 없는 가짜 보호 검사). 그 검토 뒤 RS4-2~RS4-4를 한 차례로 승인받는 순서를 권장한다.

## 11. RS4-1 구현 결과 (2026-10-28, 시험 코드·PG 없는 가짜 검사만)

- 사용자 확정: Q1 PG66 대상 값, Q4 (A) 최소 분리, Q6 단일 결과 고정. 미결 유지: Q2, Q5. 승인 전: RS4-2~RS4-4.
- **보존 기준(변경 전)**: 안전 환경 고정 뒤 연결 없이 PG65의 GRANT 문장(검사 DB 20개)·기대 프로필 지문·권한 변형 문장·HBA·설정 문자열·사후 확인 SQL·관리 연결 허용 목록·검사 DB 목록과, 감사 실행기의 기본(PG63) `conf`·`hba`·TLS·서버 시작 호출 인자 및 PG65 경로의 같은 호출 인자를 계산해 `backend/tests/ops_pg65_preserve.json`(SHA-256 `31a75924565ca116d89194dcb2a4d4bb50d284bfc3a3ae53e74ff5e8ab62657d`)으로 남겼다. 비교 때 바꾸는 것은 매번 무작위인 인증서 일련번호(`-set_serial` 다음 값)와 임시 비밀 폴더 경로를 표식으로 바꾸는 것뿐이며, 변경 후 출력으로 기준을 다시 만들지 않는다.
- **분리 경계**: 새 `backend/tests/_ops_real_layout.py`. 닫힌 배치 객체 `Layout`(`PG65`·`PG66`만, 동일 객체만 허용, 값이 같은 복제는 `layout_refused`)을 명시 인자로 받는 대상 결속 함수(`expected_profiles`·`contract_grants`·`variant_statements`·`require_target_bound`·`require_ours`·`business_check`·`post_connect_check`·`admin`·`hba`·`conf`·`counted_connector`·`RunScopes`·`build_template`·`prepare`·`cleanup`)와, C12 실행기에서 그대로 옮긴 대상 무관 도우미. 공통 모듈은 실행기를 import하지 않는다. C12 실행기는 같은 이름의 얇은 PG65 래퍼만 두고 공개 명령·검사 목록·판정·기대값을 바꾸지 않았다(파일 1834 → 1152줄). 기존 검사가 C12 모듈 이름(`ap.admin` 등)을 패치하는 위치는 그대로 동작하도록 C12의 상위 함수가 자기 래퍼를 부른다(패치 위치 이동 없음).
- **전역 교체 제거**: C12가 쓰던 `mock.patch.object(real, "T", T)` 3곳(설정·TLS·서버 시작)을 없애고 `_ops_audit_real.conf`·`make_tls`·`start_server`가 닫힌 프리셋을 인자로 받게 했다(인자 없으면 기존 PG63 그대로).
- **역할 계수 보정**: `counted_connector`가 `command == apply`가 아니라 닫힌 명령 집합으로 역할을 정한다(`dry_run`·`status` 읽기, `apply`·`resume` 쓰기, 그 밖은 시험 장치 결함). C12의 `dry_run`·`apply` 계수는 이전과 같다.
- **PG66**: `_ops_pg62`에 닫힌 프리셋 `PG66_RESUME`(`C:/JV_Tools/pg66`, 55502, `jpvr_admin`·`jpvr_read`·`jpvr_write`, 원본 + 검사 DB 23개). 새 `backend/tests/_ops_resume_real.py`(진입점 `prepare`·`check`·`cleanup`만, 인자·환경 변수로 대상·검사 범위를 바꿀 수 없음): G0, G1(검사 DB마다 실제 최초 apply로 초기 상태를 만들고 관리 연결로 확인, `failed`는 주입으로 생성), v3 A₀·E₀ 결속, Aₙ·이전 사슬·E₁, 5-1 검사표, 5-2 경합 배선(c1·c2·c2s·c3·c3r·c3c), 5-1-1 r0 탐침, 7절 중단·미실행 기록. 대표 재개 카드는 계정 a의 개인 카드 p1·p2·p3(카드 키로 대응)이며, 1장 처리 뒤 재개에서 남는 카드는 개인 카드 p2·p3이다. 구독(어휘) 카드 재개는 범위 밖이다.
- **Q2 잠금**: 관리자 자료 변경이 필요한 r4a·r4b·r7b·r7c·r7d·r8은 구현했지만, 파일 안의 `Q2_ADMIN_DATA_CHANGES`가 결정 전(`None`)이면 `check`는 G0 전에 종료 1로 멈추고 관리자 자료 변경 함수도 거부한다. 결정은 사용자 답 뒤 이 값을 고치는 것으로만 하며 인자·환경 변수로 열 수 없다.
- 코드 근거로 고정한 기대: 역할 불일치(쓰기 단계 DSN을 읽기 역할로)는 사전 검사의 연결 전 판정 `preflight_role_mismatch`, A₀ 서명 변조는 `preflight_approval_signature_invalid`, 요약 손상(`{"cursor": 1}`)은 `summary_unreadable` 보고 6. 실제 실행 전까지 미검증.
- 가짜 검사(새 Python 프로세스의 import 무작업·`__main__` 종료 코드 포함, 실제 연결·프로세스·리스너·키·관리 연결 차단): 새 `test_ops_real_layout.py` 15개(배치 닫힘, 역할 계수, 원래 종료 1회 보장과 제품 예외 우선, PG65·PG63 보존 기준 비교, 전역 교체 부재, 순환 import 없음), 새 `test_ops_resume_real_guard.py` 31개(대상·업무 행렬·관리 연결 제한·기록·PID·OID·해시 불일치, 계약 권한(시퀀스 USAGE 없음)·변형·고정 코드, G1 초기 상태·주입 범위, G1·검사·기록 재읽기·사후 확인 실패의 중단과 종료 1·미실행 기록, Q2 잠금, 정리 불일치 시 삭제 0, 탐침 위치·실패 기록·원래 종료, 원래 객체를 돌려주는 계측, 경합 정지점·해제·스레드 종료). 회귀: C12 보호 96개, 감사 보호 41개, 백업 보호 42개, `_ops_pg62` 보호 8개·명령줄 1개, RS3 공급자 경로 9개·SQLite 19개. 모두 단독 실행과 저장소 루트 discovery에서 통과(`-X dev`, 외부 `PYTHONPATH` 없이, `ResourceWarning` 0). 기존 기대값 변경은 닫힌 프리셋 목록 단언 3곳(PG66 추가)뿐이다.
- 실제 PG 미검증: 준비 SQL·G1 최초 apply·재개 제품 경로·두 `SET TRANSACTION`·탐침의 `SAVEPOINT`·잠금 대기 증명·정지점 시점·권한 변형·검사별 고정 코드는 한 번도 실제로 실행되지 않았다. 차이가 나면 기대값을 바꾸지 않고 7절 규칙으로 멈춘다.

### 11-1. RS4-1 보정: 탐침 복구 중단의 원문 노출 (2026-10-28, 시험 코드·가짜 검사만)

- 수정 전 재현(가짜 연결에 넣은 합성 실패이며, 실제 OS 장애나 PG 증거가 아님): 실제 `make_probe`와 `counted_connector` 종료 경로에서 탐침 SELECT가 합성 비밀값을 담은 `OSError`를 내고 `ROLLBACK TO SAVEPOINT`가 `KeyboardInterrupt`(또는 `SystemExit(9)`)를 내면, 원래 종료는 1회였고 같은 중단 객체가 나왔지만 그 `__context__`가 비밀값을 담은 `OSError`였고 traceback에 비밀값이 보였다. 탐침 자체의 중단은 기록이 없고 저장점 복구도 시도하지 않았다. 기록에는 예외 클래스 이름이 남았다.
- 보정(`_ops_resume_real.make_probe`, `_ops_real_layout.counted_connector` 종료 경로):
  - 기록은 고정 단계 코드만 남긴다. `probe_error`는 `probe_failed`/`probe_interrupted`, `rollback`은 `rolled_back_to_savepoint`/`rollback_to_savepoint_failed`/`rollback_to_savepoint_interrupted`이고 원문·클래스 이름은 남기지 않는다(r0 판정 규칙은 그대로).
  - 저장점 복구는 탐침의 예외 처리 블록 밖에서 실행해 연쇄가 생기지 않게 했다. 탐침이 중단돼도 복구를 한 번 시도한다.
  - 일반 오류는 기록만 하고 올리지 않는다. 중단은 처음 것을 보존해 같은 객체·같은 `SystemExit` 값으로, 원인·문맥을 끊은 채 올린다.
  - 종료 경로에서는 원래 종료를 정확히 한 번 부른 뒤에만 보존한 중단을 올리며, 올릴 때도 원인·문맥을 끊는다.
- 우선순위(변경 없음): 제품 본문에 예외·중단이 있으면 탐침을 실행하지 않고 원래 종료로 전달한다. 원래 종료의 예외·중단은 탐침 실패보다 우선한다. 원래 종료가 정상이면 보존한 탐침·복구 중단을 정리한 뒤 전파한다. 커밋·롤백·닫기 재시도나 중단을 성공으로 바꾸는 경로는 없다.
- 검사: `test_ops_resume_real_guard.py`에 실제 탐침과 종료 경로 조합 6개를 추가했다(복구 중단, 복구 `SystemExit(9)`, 탐침 자체 중단, 복구 일반 오류, 원래 종료 오류·`SystemExit(3)`·중단 우선, 정상 탐침과 제품 예외 보존). 기존 탐침 실패 검사 1개는 기록 형식이 고정 코드로 바뀐 데 맞춰 기대값을 바꿨다. `test_ops_real_layout.py` 15개, `test_ops_resume_real_guard.py` 37개가 단독 실행과 저장소 루트 discovery에서 통과했다(`-X dev`, 외부 `PYTHONPATH` 없이, `ResourceWarning` 0). 실제 PG에서는 아직 확인하지 않았다.

## 12. 1차 실제 실행 결과 (2026-10-28, 실행 ID 20261028T114240)

- 승인(2026-10-28 사용자): RS4-1 보정 마감, Q2 닫힌 목록 범위, RS4-2 준비·RS4-3 실제 검사·RS4-4 R2 정리, 대상 PG66_RESUME만. 실행기 코드 변경은 `Q2_ADMIN_DATA_CHANGES = True` 한 줄뿐이다(그 위 설명 주석의 "UNDECIDED" 문구는 코드 수정 금지 범위라 그대로 두었다).
- 실행 전 확인: `C:/JV_Tools/pg66` 없음, 55502 리스너 없음, PG 환경 변수 없음, 비밀 작업 폴더 잔존 없음.
- RS4-2 `prepare`: 종료 0. 클러스터·TLS·역할 4·원본과 검사 DB 23개·`ensure_schema`·합성 자료·식별 행·계약 GRANT.
- RS4-3 `check`: 실행기 종료 **1**. G0 통과(기록, 통과 수 제외). **G1 실패**: 첫 검사 DB(r1)의 최초 계획 dry-run이 `dry_run_failed`로 끝나 실행기가 `preparation_failure`로 기록했다. 본 검사 25항목은 **실행 0·통과 0·실패 0·미실행 25**이고, 사후 확인도 실행되지 않았다. 최초 apply·재개·관리자 자료 변경·권한 변형·경합은 한 번도 실행되지 않았다.
- 원인(정적 확인, 재실행·현장 보정 없음): **시험 장치 결함**이다. `Harness.case`가 계획 dry-run에서 연결 계수 범위(`scopes.run(counts, [])`)와 보호 드라이버(`self.driver(..., counts, [])`)에 **서로 다른 빈 목록**을 넘겼다. 그래서 공통 `counted_connector`의 "연결 1개 뒤 인계 1개" 확인이 0개를 보고 `harness_defect`를 냈고, CLI `run_dry_run`이 이를 일반 오류로 받아 `dry_run_failed`로 바꿨다. 서버 로그에 ERROR·FATAL 0건이어서 서버·권한·제품 결과가 아니다. 같은 실행기의 `first_apply`·`resume`은 같은 목록을 넘긴다. RS4-1 가짜 검사는 `Harness.case`를 실행하지 않아 이 경로를 잡지 못했다. 실행기는 이를 준비 실패로 분류했는데, 분류도 시험 장치 결함이 맞다.
- 제품 결함 후보: 없음(제품 경로에 닿기 전 중단).
- 증거(세션 임시 폴더 `pg66_evidence_20261028T114240/`, 원본 이동·수정 없음, 비밀값·개인 키·SQL 매개값 없음 확인):

| 파일 | 크기(바이트) | SHA-256 |
| --- | --- | --- |
| `record.json` | 8495 | `59e5c382bdf4b4a874697533dd0fc4189edba8de6979f595d7f0874fb8074edb` |
| `target.json` | 7286 | `4c896e40c7ab40ceae268baf326580d8cd254fdbbc303117bde1e96c29248b74` |
| `server.log` | 33852 | `dbcb1ce9e4cc903e88bd97ab885026548233b1a9ba7a0248e93fbc3011ac70f7` |
| `check_stdout.log` | 192 | `b37ad9d600d43d3c9df803eb1ffa11fe52ca903b9b692cea00fc6b2a2ee2db5b` |

  계획된 잠금·계측 기록은 본 검사가 실행되지 않아 생기지 않았다.
- RS4-4 `cleanup`: 종료 0. 기록 대조(시작 PID·`target.json` 결속·`system_identifier`·DB/역할 OID·업무 세션 0) 뒤 서버를 정지했다. 정리 뒤 55502 리스너 없음, `C:/JV_Tools/pg66` 없음, 비밀 작업 폴더·시험 키·배포 임시 폴더 없음. 기존 `pgdata-e2`·`pgsql-18.6`·과거 증거는 그대로다.
- 다음 단위(**승인 전**): `Harness.case`의 목록 결속 보정과 그 경로를 실제로 실행하는 가짜 검사를 추가하고, 새 클러스터에서 RS4-2~RS4-4를 다시 실행한다. 1차 기록은 수정하지 않는다.
- 미검증 유지: 실제 공급자 위의 제품 재개, 고정값 대조, 권한·원복, 기간 구분, 부분 커밋 보존, 경합, 구독 카드 재개, 실제 장애, 운영 실행. Q5 장기 보존 위치·기간은 미결이다.

### 12-1. 보정: `Harness.case`의 목록 결속 (2026-10-28, 시험 코드·PG 없는 가짜 검사만)

12절 1차 기록(G1 `preparation_failure`, 본 검사 0/25)과 원시 증거는 그대로 둔다. 이 절은 별도의 보정 기록이다.

- 수정 전 재현: 새 `CasePath` 검사가 실제 `Harness.case`를 끝까지 실행한다.
  - **실제로 실행한 부분**: Harness 초기화와 대상 기록 결속, 배포 폴더, manifest, I₀, CLI `run_dry_run`(실제 사전 검사와 서명 검증), 공통 `counted_connector`, `Harness.driver`(업무 행렬·생존 확인·연결 직후 대조), 계획 파일, `run_synthetic_preflight`, E₀·E₁, A₀.
  - **대체한 부분**: 보호 드라이버의 실제 연결(`g.Guard`), 연결·커서, CLI 제품 연결기 뒤의 공급자 경로(`ORIGINAL_CONNECTOR`를 드라이버를 한 번 부르고 원시 연결을 넘기는 가짜로 대체), 제품 dry_run 본문(넘겨받은 연결에 한 번 들어갔다 나오고 실제 계획 후보를 돌려주는 대체본), 인증서 파일 내용.
  - 서명은 기존 합성 방식의 시험 전용 임시 OS ssh-keygen 키만 썼다. 그 밖의 프로세스·연결·리스너 조회·TLS 생성·관리 연결은 호출 즉시 실패하게 막았다.
  - 결과: 수정 전에는 1차 실행과 같은 `r1: plan dry-run dry_run_failed`(`preparation_failure`)가 났다. 연결 생성은 1이었고 인계는 0이었으며, 공통 계수기가 `harness_defect`("one hand-over must follow exactly one connection")를 냈다. 계수 범위의 목록은 길이 0, 드라이버 목록은 길이 1인 서로 다른 객체였다.
- 보정(`backend/tests/_ops_resume_real.py`): `Harness.case`가 목록 하나를 만들어 `scopes.run`과 `self.driver`에 같은 객체를 넘긴다. "연결 1개 → 인계 1개" 확인은 그대로다.
  - 인접 호출부도 확인했다. `first_apply`, `resume`/`resume_call`, `observe_both`, 경합 `Runs`는 이미 같은 목록을 넘기고 있다.
  - `Q2_ADMIN_DATA_CHANGES = True`는 그대로 두고, 위 주석만 승인 상태로 정정했다.
- 보정 뒤 증거(`CasePath`):
  - 두 목록이 같은 객체이고, 연결 생성·인계가 읽기 역할 1·1, 쓰기 0·0이다.
  - 계획 파일 `artifact_sha256`이 파일 바이트 해시와 같고, 제품 지문이 후보 `_plan_json` 해시와 같다.
  - A₀는 v3 `apply`이고, `backup_evidence.sha256` = E₀ 원문 해시, `based_on` = I₀ 해시다. 최초 apply 입력이 A₀와 계획 값을 쓴다.
  - E₀와 E₁은 `evidence_id`만 다르다.
  - 계획 dry-run이 실패하면 G1이 `preparation_failure`로 멈추고, 최초 apply와 다음 검사 DB 준비는 실행되지 않는다.
- Q2 승인에 따라 기존 검사 2곳의 전제를 바꿨다. "Q2 미결 시 시작 전 종료 1"과 관리자 변경 거부는 승인값을 단언한 뒤, 값을 바꾼 상태에서 그 분기를 계속 검사한다. 새 프로세스 `__main__` 검사도 같다.
- 집중 검사: `test_ops_resume_real_guard.py` 39개(새 2개 포함), `test_ops_real_layout.py` 15개가 단독 실행과 저장소 루트 discovery에서 통과했다(`-X dev`, 외부 `PYTHONPATH` 없이, `ResourceWarning` 0). 이번 시험 임시 자료 잔존 0.
- 실제 PG 미검증: 공급자 경로를 거친 계획 dry-run, G1 최초 apply, 본 검사 25항목 전부. 재실행(RS4-2~RS4-4)은 승인 전이다.

## 13. 2차 실제 실행 결과 (2026-10-28, 실행 ID 20261028T123027)

- 승인(2026-10-28 사용자): 12-1 보정 검토 마감, 새 클러스터에서 RS4-2~RS4-4 한 차례 재실행, Q2 닫힌 목록 승인 유지. 실행기·제품·보호 조건·기대값은 현장에서 고치지 않았다.
- 실행 전 확인(읽기만): `C:/JV_Tools/pg66` 없음, 55502 리스너 없음, PG 환경 변수 없음, 비밀 작업 폴더 잔존 없음, `Q2_ADMIN_DATA_CHANGES = True`, `Harness.case` 공유 목록 경로.
- 결과: `prepare` 0 → `check` **0** → `cleanup` 0. G0 통과(23 DB OID·식별 nonce, 의도한 품질 p1~p3·l1·l2 변환 가능, p4 `blocked:incomplete`). G1 통과: 23개 DB 모두 실제 공급자 경로의 계획 dry-run과 실제 최초 apply로 초기 상태를 만들었다(r2 `failed`는 **주입**, r6b는 결속 없는 A₀, r7a `completed`, r7e는 계정 b 소유, c3·c3r·c3c는 커서 2/3, 나머지 `started` 1/3). 본 검사 **25/25 통과**(실패 0·미실행 0), 사후 확인 통과(업무 세션 0·`idle in transaction` 0). G0·G1·사후 확인은 통과 수에 넣지 않았다. 서버 로그 ERROR·FATAL 0건.
- **실제 서버 결과**:
  - r1·r2: 공급자 연결 위의 실제 제품 재개다. 부분 처리(`started`)와 `failed` 실행 모두 `completed`, 결과는 `already_applied` 1·`applied` 2. p1 버전 불변, p2·p3 버전 +1, snapshot 3, 다른 계정·범위 밖 행 불변. r1 계수: 읽기 생성·인계 1·1(쓰기 문장 0), 쓰기 생성·인계 4·4.
  - r0: 읽기 인계 연결의 문장 순서가 `SET TRANSACTION READ ONLY` → `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` → 실행 행 → snapshot이었고, 서버가 둘째 `SET TRANSACTION`을 받아들였다. 탐침 결과 `repeatable read`, `read_only on`.
  - r3: 사전 조회 9개 값 = 잠금 아래 `run_progress_values` = 관리 연결 독립 계산(r1·r2).
  - r4a·r4b·r4c: 요약 재직렬화, snapshot 추가, 정상 커서 전진(실제 다른 재개 B가 커서 2까지 처리) 모두 `migration_run_changed` 4. 제품 잠금 아래 거부이며 쓰기 인계 1·`COMMIT` 0이다. r4c의 변경은 B의 것뿐이었다.
  - r5: 계약 권한만으로 재개가 성공했다(r1·r2). 권한 변형별 결과는 아래와 같고, 각 변형 뒤 원복과 두 역할의 관측 = 계약 프로필을 확인했다.
    - 읽기 누락 `observed_privileges_missing`, 읽기 초과 `observed_privileges_excess`: 읽기 관측 후 거부, 쓰기 연결 0
    - 쓰기 누락 `observed_privileges_missing`, 쓰기 초과(`users` 표 단위 UPDATE)·시퀀스 USAGE 부여 `observed_privileges_excess`: 첫 쓰기 관측 후 거부
  - r9a: 첫 남은 카드 커밋 뒤 쓰기 역할의 `UPDATE(srs_state)`를 실제로 회수했다. 다음 연결이 `observed_privileges_missing`으로 거부돼 1·`after_start`·`uncertain`·`status_required`, 커밋된 카드는 유지됐고(커서 2·snapshot 2), 원복 뒤 관측이 계약과 같았다.
  - r7: `completed` → `migration_run_completed` 4, 커서 끝 → `cursor_end_not_completed` 6, `aborted` → `migration_run_closed` 4, 요약 손상 → `summary_unreadable` 6, 다른 계정 소유 → `resume_target_not_found` 4. 모두 읽기 1·쓰기 연결 0, DB 불변이다.
  - r8 ③: `started_at` 31일 전 → `migration_resume_window_closed` 4, 쓰기 0. CLI 사전 판정이며 앱 프로세스 실제 시각 기준이다.
- **연결 전 CLI 거부**(두 역할 연결 0, DB 불변):
  - r6: `resume_plan_not_initial`, `resume_chain_required`, `preflight_approval_signature_invalid`, `resume_initial_evidence_mismatch`, `resume_backup_evidence_mismatch`(필드 다름·같은 `evidence_id`), `approval_format_not_v3`
  - r6b: `resume_backup_binding_missing`
  - r5 역할 불일치: `preflight_role_mismatch`
  - r8 ①: 시작 전 승인 만료 `preflight_approval_expired`
  - r8 ②: 상태 읽기 뒤 승인 만료 `preflight_approval_expired`(읽기 1·쓰기 0)
  - r8 ④: 새 근거만 만료 `backup_evidence_expired`(읽기 1·쓰기 0)
- **경합**: 대기는 서버 근거로 확인했다. B의 첫 쓰기 연결이 `transactionid` `ShareLock`을 기다렸고(`granted = false`), `pg_blocking_pids(B)` = A의 카드 연결 PID였다. 기대 결과는 하나로 고정돼 있었다.
  - c1: B가 잠금 아래 읽은 상태가 `started`·커서 2, A 커밋 직후 관리 연결 요약 해시와 같았다. B `migration_run_changed` 4, 쓰기 `COMMIT` 0, A 0.
  - c2: B가 잠금 아래 `started`·커서 3(마무리 전)을 읽었다. B `migration_run_changed` 4, A 0.
  - c2s: B가 커서 2를 읽고 이어 처리, `already_applied` 2·`applied` 1, 종료 0.
  - c3: A 완료 뒤 B가 잠금 아래 `completed`(`finished_at` 있음)를 읽었다. 대조 전에 `migration_run_not_resumable` 4가 났고, 잠금 대기는 주장하지 않는다.
  - c3r: A 마무리 전 사전 조회로 `cursor_end_not_completed` 6, 쓰기 연결 0.
  - c3c: A 완료 뒤 시작해 `migration_run_completed` 4.
  - 정지점 순서는 기록과 같았다(c1·c2: P1 도달 → P1 해제 → P2 도달 → B 종료 → P2 해제 → A 종료). 귀속 규칙(실행 행 1·범위 MD5·snapshot 수·카드당 1회 증가·B `COMMIT` 0)도 모두 만족했다. 모든 정지점이 해제되고 스레드가 종료됐다.
- **시험 장치 주입**:
  - G1의 r2 `failed` 상태
  - r9b: 둘째 남은 카드 연결 뒤 예외 → 1·`after_start`, 앞 커밋 유지, 상태 `failed`
  - r9c: 마무리 연결 예외 → 1·`uncertain`, 모든 카드 커밋, 상태 `started`

  이 결과들은 실제 장애 증거가 아니다.
- 관리자 자료 변경은 닫힌 목록 6종만 각 1회 했다(요약 재직렬화, snapshot 추가, 커서 끝, `aborted`, 요약 손상, `started_at` 31일 전). 권한 변형은 r5 5종과 r9a 1종을 각각 적용·원복했다(기록 18건).
- C10 `restore_verified`·`backup_artifact_checked`는 `false`다.
- 발견 사항: 준비 실패 0, 시험 장치 결함 0, 제품 결함 후보 0.
- 증거(세션 임시 폴더 `pg66_evidence_20261028T123027/`, 원본 이동·수정 없음, 비밀값·개인 키·SQL 매개값 없음 확인). 계측 기록(계수·문장 순서·탐침·잠금 아래 읽기·대기 증거·정지점 순서·변형·관리자 변경)은 `record.json`에 있다.

| 파일 | 크기(바이트) | SHA-256 |
| --- | --- | --- |
| `record.json` | 40291 | `95d2434f4b9e0001cd19f9d6d62ddb5ed566904a8a307c249379a19238200588` |
| `target.json` | 7285 | `607e55390e5acda594b5ca272c22776986bdba9f1deb6e08389dcb4fba95eb7c` |
| `server.log` | 304718 | `7b3ceaef39309f1b0ba712c0f13f72e39c44fdd9f7f521cbe6015af2f0418da7` |
| `check_stdout.log` | 336 | `564c3515e17246a29ad4f2aebbc25d6865a3882018afc32ce1d8f4ba06f3e9bb` |
| `prepare_stdout.log` | 10 | `aba1a6c58bc0c175b5a77d0a73a018cd667b7cd07efa6a1f0bd1fa001e07635c` |

- RS4-4 `cleanup`: 종료 0. 기록 대조 뒤 서버를 정지했고, 55502 리스너·`C:/JV_Tools/pg66`·비밀 작업 폴더·시험 키·배포 임시 폴더가 모두 없다. 1차 증거 `pg66_evidence_20261028T114240/`, 기존 `pgdata-e2`·`pgsql-18.6`, 이전부터 있던 `ops_sig_test_keys_6_y4m1w7`은 그대로다.
- 미검증 유지: 구독(어휘) 카드 재개(대표 재개는 개인 p2·p3), 실제 커밋 응답 유실·OS·네트워크·서버 강제 종료, 실제 백업·복원(C10은 합성 진술), 운영 실행·운영 신뢰 루트, 30일 창 정각 경계(합성 SQLite에서만). PostgreSQL 18.6 로컬 단일 서버의 결과이며 운영 준비 완료가 아니다. Q5 미결.

### 13-1. r3 비교값 기록의 한계와 보정 계획 (2026-10-28, 2차 결과 이후 문서 고정 → 코드)

- **2차 기록의 한계**: 2차 실행의 r3는 실행 중에 r1·r2 각각의 세 값(사전 조회, 잠금 아래 조회, 관리 연결 독립 계산)을 비교해 통과했다. 그러나 결과 기록에는 `{"compared": ["r1", "r2"]}`만 저장됐고, 각 9개 값은 파일에 보존되지 않았다. 따라서 2차 증거로 확인할 수 있는 것은 "세 값이 같았다는 실행 중 판정과 그 통과 기록"뿐이며, 값 자체는 증거에 없다. 2차 원시 기록과 25/25 결과는 그대로 둔다. 다른 DB의 값이나 현재 계산값으로 과거 증거를 사후에 채우지 않는다.
- **새 기록 형식(코드보다 먼저 고정)**: r3 결과 `details`는 정확히 아래 구조다. 9개 값의 키는 `run_id`, `status`, `mode`, `config_version`, `started_at`, `finished_at`, `scope_sha256`, `summary_sha256`, `snapshots_sha256`이다(계약 9-2와 같은 이름, SQL 원문·매개값·DSN·비밀번호·키 없음).

```json
{
  "compared": ["r1", "r2"],
  "values": {
    "r1": {"pre_read": {"…9개 값…"}, "under_lock": {"…9개 값…"}, "admin_values": {"…9개 값…"}},
    "r2": {"pre_read": {"…"}, "under_lock": {"…"}, "admin_values": {"…"}}
  }
}
```

- 판정은 그대로다: r1·r2마다 세 값이 모두 있고, 키 집합이 정확히 9개이며, 세 값이 같아야 통과한다. 값이 없거나 키가 다르면 시험 장치 결함, 값이 다르면 실패다. 기록에는 고정 사본을 넣고 원래 계측값·반환 객체는 바꾸지 않는다.
- **고정 보완 진입점 `check-values`**: 명령줄·환경 변수로 검사나 대상을 고를 수 없다.
  - 순서: G0 → G1(r1·r2 초기 상태만) → r1 → r2 → r3 → 보완 사후 확인.
  - 통과 수는 r1·r2·r3 세 개이며, 관문과 사후 확인은 기록하되 제외한다.
  - 보완 사후 확인: r1·r2 DB의 다른 계정·범위 밖 자료가 G1 직후와 같을 것, r1 필수 탐침에 실패가 없을 것, 업무 세션·`idle in transaction`이 0일 것.
  - 기록에 보완 실행임(`supplement_values`)과 "이전 25/25에 합산하지 않음"을 남긴다.
  - 최초 실패에서 후속 단계를 멈추고, 모두 통과·저장·재읽기됐을 때만 종료 0이다.
  - 기존 전체 `check`의 25항목·G1 범위·판정은 바꾸지 않는다.

- **구현(2026-10-28, 시험 코드·PG 없는 가짜 검사만)**: `backend/tests/_ops_resume_real.py`.
  - `r3_fixed_values`는 위 형식으로 r1·r2의 세 값 고정 사본(JSON 왕복 사본, 원래 계측값·반환 객체는 바꾸지 않음)을 돌려준다. 값이 없거나 키가 정확히 9개가 아니면 시험 장치 결함, 값이 다르면 실패다.
  - `g1_gate(h, checks)`: 인자 없이 부르면 기존처럼 25항목 전체 DB를 준비하고, `check-values`만 `("r1", "r2")`를 넘긴다. G1 직후의 범위 밖 자료를 사후 확인용으로 기록한다.
  - 고정 진입점 `check-values`, `values_post`, `VALUES_PLANNED = ("r1", "r2", "r3")`를 추가했다. 기존 `check`의 25항목·G1 범위·판정은 바꾸지 않았다.
- **가짜 검사**(`test_ops_resume_real_guard.py`, 실제 연결·PG 프로세스·TLS·리스너·관리 연결 차단):
  - 실제 `r3_fixed_values`를 실제 기록 저장·재읽기 경로(`lay.run_recorded`, `g.Record`)로 실행했다. 임시 `record.json`을 다시 읽어 r1·r2 각각 세 딕셔너리와 9개 값이 모두 보존됐는지, 원래 값이 바뀌지 않았는지, 고정 사본인지 확인했다.
  - 값 누락·키 차이(시험 장치 결함), 불일치(실패), 기록 실패·재읽기 실패는 통과로 세지 않는다.
  - 이전 구현("compared 이름만 저장")에서는 새 기록 검사가 `KeyError: 'values'`로 실패함을 수정 전에 확인했다.
  - `check-values`의 실제 조립(관문·검사 본문은 가짜)으로 확인한 것:
    - 순서 G0 → G1(`("r1", "r2")`) → r1 → r2 → r3 → 사후 확인
    - 집계: 통과 수 3, 관문·사후 확인 제외
    - 기록: `supplement_values`와 "25/25에 합산하지 않음"
    - 실패 지점(G1, r2, r3, 사후 확인)마다 후속 중단, 종료 1, 미실행 기록
    - `values_post`의 요구 조건: 범위 밖 자료 불변, 탐침 실패 없음, 세션 0, G1 기록 존재
  - 새 Python 프로세스의 `__main__`: `check-values` 뒤 추가 인자는 2, PG 환경 변수가 있으면 1이다. 그 밖에는 기록 조회까지만 가고, 그 조회는 여기서 차단했다.
  - 이 가짜 비교값·기록 검사는 실제 PostgreSQL에서 세 값이 같다는 증거가 아니다.
- 집중 검사: `test_ops_resume_real_guard.py` 47개, `test_ops_real_layout.py` 15개가 단독 실행과 저장소 루트 discovery에서 통과했다(`-X dev`, 외부 `PYTHONPATH` 없이, `ResourceWarning` 0). 이번 시험 임시 자료 잔존 0.
- 실제 보완 실행(**승인 전**): 새 클러스터에서 `prepare` 1회 → `check-values` 1회 → `cleanup`이 필요하다. 대상은 PG66_RESUME이며, 관리자 자료 변경·권한 변형은 쓰지 않는다(r1·r2·r3 범위에는 없음).

### 13-2. r3 보완 실제 실행 결과 (2026-10-28, 실행 ID 20261028T131854)

- 승인(2026-10-28 사용자): 새 PG66_RESUME 대상에서 `prepare` 1회 → `check-values` 1회 → R2 `cleanup`. 전체 `check`는 다시 실행하지 않았다. 관리자 자료 변경·권한 변형은 없었다(기록 0건). 코드·기대값·권한 변경과 재시도도 없었다.
- 실행 전 확인: `C:/JV_Tools/pg66` 없음, 55502 리스너 없음, PG 환경 변수 없음, 비밀 작업 폴더 잔존 없음.
- 결과: `prepare` 0 → `check-values` 0 → `cleanup` 0. 서버 로그 ERROR·FATAL 0건.
  - G0 통과.
  - G1 통과: r1·r2 두 DB만 실제 공급자 경로의 계획 dry-run과 실제 최초 apply로 준비했다. r1은 `started` 1/3이고, r2의 `failed`는 **시험 장치 주입**(둘째 카드 연결 뒤 예외)으로 만들었으며 실제 장애가 아니다.
  - **r1·r2·r3 3/3 통과**, 보완 사후 확인 통과(G1 직후 대비 r1·r2 DB의 다른 계정·범위 밖 자료 불변, r1 탐침 `repeatable read`·`on`, 업무 세션 0·`idle in transaction` 0).
  - 기록에는 `supplement_values`와 "이전 25/25에 합산하지 않음"이 있다. 관문·사후 확인은 통과 수에서 제외했다.
- 실제 서버 결과: 공급자 연결 위의 실제 제품 재개. r1(`started`)과 r2(`failed`) 모두 `completed`, 결과 `already_applied` 1·`applied` 2. r1의 p1 버전 불변, p2·p3 +1. 계수는 읽기 생성·인계 1·1(쓰기 문장 0), 쓰기 4·4.
- **여섯 딕셔너리 대조**(저장된 `record.json`을 다시 읽어 확인): r1·r2 각각 `pre_read`·`under_lock`·`admin_values`가 모두 있고, 각 딕셔너리의 키가 계약의 9개와 정확히 같으며, 실행마다 세 값이 정확히 같았다. 값은 그 실행의 DB에서 얻은 것이고 과거 값으로 채우지 않았다.
  - r1: `status` `started`, `run_id` 1, `finished_at` null, `started_at` `2026-10-28T04:19:33.604202+00:00`, `summary_sha256` `eeef50f0…dfdf3aab1`, `snapshots_sha256` `37f71e3b…8eac66`, `scope_sha256` `0a96a6dd…67e90eb`.
  - r2: `status` `failed`, `started_at` `2026-10-28T04:19:39.219930+00:00`. 나머지 해시는 r1과 같다(같은 합성 자료·같은 초기 커서의 별도 DB).
  - 전체 값은 `record.json`의 r3 `details.values`에 있다.
- C10 `restore_verified`·`backup_artifact_checked`는 `false`다.
- 발견 사항: 준비 실패·시험 장치 결함·제품 결함 후보 모두 0.
- 증거(세션 임시 폴더 `pg66_evidence_20261028T131854/`, 원본 이동·수정 없음, 비밀값·개인 키·SQL 매개값 없음 확인):

| 파일 | 크기(바이트) | SHA-256 |
| --- | --- | --- |
| `record.json` | 12270 | `82901439782ee31dfec8d4f14efefcde7972bbeb174ee466e98a329d44d464e7` |
| `target.json` | 7285 | `8f9351287dab396b26d955df63606612cad8306bdf9bd9b0c7d29a206bf6763a` |
| `server.log` | 58028 | `e039fcb468aa95d5010163262e64f3b09d6136ee33c36dfcfaeb0137a88d0964` |
| `check_values_stdout.log` | 119 | `2e51d6c412caeba0c780e5675b4737de746ade9741a1c0f744e00f8bd67a5f3f` |
| `prepare_stdout.log` | 10 | `aba1a6c58bc0c175b5a77d0a73a018cd667b7cd07efa6a1f0bd1fa001e07635c` |

- 정리: 기록 대조 뒤 서버를 정지했다. 55502 리스너·`C:/JV_Tools/pg66`·비밀 작업 폴더·시험 키·배포 임시 폴더가 모두 없다. 1·2차 증거, `pgdata-e2`, 이전부터 있던 `ops_sig_test_keys_6_y4m1w7`은 그대로다.
- 미검증 유지: 구독 카드 재개, 실제 장애, 실제 백업·복원, 운영 실행. Q5(증거 장기 보존) 미결.

## 14. 마감 (2026-10-28)

- 마감 범위: PostgreSQL 18.6 로컬 단일 서버에서 개인 카드의 명시적 `resume` 경로. 명시 전환 CLI 전체나 Gate E 전체의 완료가 아니다.
- 실행별 결과(합산 없음): 1차 0/25(G1 시험 장치 결함), 2차 25/25(r3 비교값 자체는 미보존), 보완 3/3(여섯 딕셔너리 보존). 보완은 과거 기록을 고치거나 소급해 채우지 않았다.
- 증거 14개 읽기 전용 대조: 모두 있고 크기·해시·실행 ID·`target_written` 결속이 일치하며, 보완 표시와 여섯 딕셔너리를 확인했다(`OPS_MIGRATION_RESUME_REAL_PG_EVIDENCE.md` 3절).
- 남은 것: 구독(어휘) 카드 재개, 실제 커밋 응답 유실·OS·네트워크 장애, 실제 백업·복원(C10은 합성 진술), 30일 창 정각 경계의 실제 PG 확인, 운영 실행·운영 신뢰 루트, 증거 장기 보존 위치·기간(Q5).
- 구분: 30일 창은 실제 PG에서 31일 전 실행의 거부만 확인했고, 정각·1초 전 경계는 합성 SQLite 증거뿐이다. r2 초기 `failed`와 r9b·r9c는 주입 결과이며 실제 장애 증거가 아니다. C10 `restore_verified`·`backup_artifact_checked`는 `false`다. 세션 임시 폴더와 해시 목록만으로는 보존·진본성이 보장되지 않는다(Q5 미결).

RS4 마감 검토 대기.

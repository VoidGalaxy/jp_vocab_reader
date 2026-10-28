# 6-2 실제 로컬 PG 검증 준비 계획·승인 요청서 (2026-10-22 승인, 1·2차 실행 완료, 마감)

**승인 기록 (2026-10-22 사용자)**: A~F 전부와 R2(시험 뒤 삭제)를 승인했다. 범위: 기존 PG 18.6 바이너리 사용, `C:/JV_Tools/pg62/{data,tls,runs}` 분리 클러스터, localhost:55462(서비스·방화벽 변경 없이 `pg_ctl`), 시험 CA·서버·거부 시험용 인증서, 계획의 관리·소유·읽기·쓰기·소유 거부 시험 역할, `jp_vocab_test_62a`·`62b`와 합성 자료·식별 행·권한, 시험 전용 실행기·테스트와 실제 6-2 검사, 검증 가능한 이번 실행 자료만 R2로 삭제. `pg62` 경로가 있거나 55462가 사용 중이면 중단한다. 운영 접속·운영 정책 확정·기존 CLI 활성화 승인이 아니며, 제품 보정도 포함하지 않는다. 기존 `pgdata-e2`·55432·기존 시험 DB·`vocab.db`·Neon·운영은 접속·변경하지 않는다.

상태(작성 당시): **계획만 작성했다.** 이번 작업에서 한 일은 읽기 전용 확인과 문서 작성뿐이다. initdb, PG·서버 실행, DB 접속, 역할·DB·키·인증서 생성, 설치·다운로드는 하지 않았다. 관련 문서: `OPS_CONNECTION_PROVIDER_CONTRACT.md` 6-2·7·10·11절, `LOCAL_POSTGRES_E2.md`. 기준: 6-1a~6-1d 합성 검토 통과, 공통 검사 202개(199 통과·3 건너뜀).

## 0. 읽기 전용으로 확인한 사실 (2026-10-22)

| 항목 | 확인 결과 |
| --- | --- |
| 실행 파일 | `C:/JV_Tools/pgsql-18.6/pgsql/bin`에 `initdb.exe`·`pg_ctl.exe`·`libssl-3-x64.dll` 있음(실행하지 않음) |
| 기존 클러스터 | `C:/JV_Tools/pgdata-e2`, `port = 55432`, `listen_addresses = localhost`, SSL 설정 없음, HBA는 SSPI 2역할 + 그 밖 reject. `postmaster.pid` 없음(꺼져 있음) |
| 포트 | TCP 55430~55449·5432 리스너 없음(`netstat` 조회만) |
| 인증서 도구 | `C:/Program Files/Git/usr/bin/openssl.exe` 있음(실행하지 않음). PATH에는 없음 |
| 디스크 | C: 여유 약 182GB |

기존 설치·`pgdata-e2`·55432·`jp_vocab_test_e`·E-1 보호 장치(`tests/_local_postgres_guard.py`, `scripts/_local_test_postgres.py`, `tests/_srs_pg_harness.py`)는 이 계획 전체에서 읽기만 하고 바꾸지 않는다.

## 1. 준비 계획 (권장 값)

| 항목 | 권장 값 | 이유 |
| --- | --- | --- |
| 루트 폴더 | `C:/JV_Tools/pg62/` (새로 만듦, 이미 있으면 중단) | 기존 `pgdata-e2`와 형제 경로, 이름으로 구분 |
| 데이터 | `C:/JV_Tools/pg62/data` | 새 initdb 대상 |
| 인증서 | `C:/JV_Tools/pg62/tls` (서버 인증서·키, 시험 CA 인증서) | 서버가 읽는 파일만 둔다 |
| 실행 기록 | `C:/JV_Tools/pg62/runs/<실행ID>/` (`record.json`, `server.log`, 결과 요약) | 중단돼도 복원 근거가 남는다. 비밀값 없음 |
| 비밀 작업 폴더 | `%LOCALAPPDATA%/Temp/jpv_pg62_<실행ID>/` (CA 개인 키, 서명 직후 삭제) | 저장소·`JV_Tools` 밖, 실행마다 새로 만듦 |
| 포트 | **55462** | 55432와 떨어진 미사용 포트. 시작 전 리스너 없음을 다시 확인하고 있으면 중단 |
| 바인딩 | `listen_addresses = 'localhost'`(127.0.0.1·::1), 방화벽·서비스 변경 없음 | 루프백 전용 |
| 시작·종료 | `pg_ctl start -D <data> -l <runs>/server.log -w -t 30` / `pg_ctl stop -D <data> -m fast -w -t 30`. `pg_ctl register`·Windows 서비스·작업 스케줄러 없음. 창 없이 배경 실행 | 기존 E-2와 같은 방식 |
| 서버 설정 | `ssl = on`, `ssl_min_protocol_version = 'TLSv1.3'`, `ssl_cert_file`·`ssl_key_file`·`ssl_ca_file` = `tls/` 파일, `password_encryption = scram-sha-256`, `log_statement = 'none'`, `log_connections = on` | verify-full·TLS 1.3 허용 목록과 맞춤, 비밀번호 문장 기록 방지 |
| HBA(주소마다 한 줄, 127.0.0.1/32·::1/128) | `hostssl postgres,jp_vocab_test_62a,jp_vocab_test_62b jpv62_admin <주소> sspi map=pg62` / `hostssl jp_vocab_test_62a,jp_vocab_test_62b jpv62_read,jpv62_write <주소> scram-sha-256` / `hostssl jp_vocab_test_62a jpv62_owner_login <주소> scram-sha-256`(소유 거부 시험 전용, 62a만) / `hostnossl all all <주소> reject` / 마지막 `host all all 0.0.0.0/0`·`::0/0 reject` | 관리 역할은 SSPI(현재 Windows 사용자만 명시 매핑, 비밀번호 없음), 시험 역할은 TLS+SCRAM만 |
| 시험 CA | 이름 `jp_vocab 6-2 synthetic test CA`, EC P-256, 유효 2일, `basicConstraints=CA:TRUE` | 시험 전용, 짧은 수명 |
| 서버 인증서 | CN `localhost`, SAN `DNS:localhost, IP:127.0.0.1, IP:::1`, `extendedKeyUsage=serverAuth`, 유효 2일 | verify-full 대상 이름 |
| 거부 시험용 인증서 | ① 다른 시험 CA(`wrong CA`)의 루트(클라이언트 쪽 manifest에만) ② SAN `DNS:mismatch.test`만 가진 서버 인증서(서버 교체 + `pg_reload_conf()`) | 잘못된 루트·호스트 이름 거부 |
| 파일 보호 | 서버 키·CA 개인 키는 현재 Windows 사용자만 읽기(상속 해제 ACL). CA 개인 키는 서버 인증서 서명 직후 삭제 | 시험 키 노출 범위 최소화 |
| 역할 | `jpv62_admin`(initdb 부트스트랩 관리 역할, SSPI만), `jpv62_owner`(NOLOGIN, 표 소유), `jpv62_read`·`jpv62_write`(LOGIN, 비소유, 슈퍼유저·생성·복제·RLS 우회 없음, 소속 없음), `jpv62_owner_login`(소유 거부 시험 동안만 존재, 아래 1-1) | 2-1절 기준: 비소유·소속 없음 |
| DB | `jp_vocab_test_62a`(검사 대상), `jp_vocab_test_62b`(식별 불일치 시험). 둘 다 `jpv62_owner` 소유, `PUBLIC`의 `CONNECT`·`TEMPORARY` 회수 후 역할별로 `CONNECT`만 부여 | 기존 시험 DB 이름 규칙과 같은 꼴, 기존 DB와 겹치지 않음 |
| 식별 행 | 두 DB에 `jp_vocab_ops_synthetic.db_identity(identity_value text NOT NULL)` 1행. 값 `pg62-a-<nonce>`·`pg62-b-<nonce>`, nonce는 실행마다 새 난수 | 이 실행의 클러스터만 가진 값으로 대상 결합 |
| 합성 업무 표 | `public.users(id, email)`, `public.vocab_items(id, word)`와 시퀀스, 소유 `jpv62_owner`. 읽기: 표 `SELECT`, 쓰기: + `vocab_items` `UPDATE`·시퀀스 `USAGE` | 6-1c 시험의 기대 프로필과 같은 구조 |

- **1-1. 소유 거부 시험 역할**(보정): `jpv62_owner_login`은 LOGIN·SCRAM(검증값만 전송), 슈퍼유저·생성·복제·RLS 우회·소속 없음. 관리 연결이 시험 직전에 만들고 `jp_vocab_test_62a`의 `CONNECT`, 두 스키마 `USAGE`, 읽기 프로필과 같은 표 `SELECT`만 준 뒤, 그 역할이 소유하는 합성 표 `public.owner_probe` 하나를 만든다(권한 차이는 소유뿐). HBA는 위 표의 62a·TLS+SCRAM 한 줄뿐이라 인증은 통과하고, 공급자의 소유 검사(`observed_ownership`, 객체 대조보다 먼저)에서 거부돼야 한다. 승인 단계 역할은 시험 서명 키로 만든 이 시험 전용 승인에만 넣는다. 시험 직후 원복: `owner_probe`를 이름·OID 확인 후 `DROP TABLE`(CASCADE 없음) → 부여 권한 `REVOKE` → `DROP ROLE`(OID 확인). 원복 전에는 다른 검사를 진행하지 않는다(객체 목록이 달라지므로). 관리 역할은 공급자에 넘기지 않는다.
- **관리자 작업 단계**(`jpv62_admin`, SSPI, 관리 연결만): initdb 직후 HBA·설정 작성, 역할·DB·스키마·표·식별 행·권한 부여, 시험별 권한 변형과 원복, 서버 인증서 교체·reload, 정리.
- **일반 역할 검증 단계**(`jpv62_read`·`jpv62_write`, TLS+SCRAM, 공급자 경로만): 6-1a~6-1d 공급자·사본·관측기·어댑터로 연결·관측·인계. 관리 역할은 공급자에 절대 넘기지 않는다.
- **비밀값**: 시험 역할 비밀번호는 실행기 프로세스 안에서 `secrets` 모듈로 만들고, SCRAM-SHA-256 검증값만 계산해 관리 연결로 `ALTER ROLE … PASSWORD '<SCRAM 검증값>'`을 보낸다(평문 비밀번호가 서버·로그로 가지 않음). 평문은 실행기 메모리에서만 연결 인자로 쓰고 파일·명령줄·화면·기록에 남기지 않는다. 실행이 끝나면 버린다(다음 실행은 새로 만든다). 시험 개인 키는 비밀 작업 폴더와 `tls/`에만 두고 정리 단계에서 지운다.

## 2. 실제 연결 전용 보호 장치 설계

이유: 6-1d의 드라이버 주입 API는 "넘긴 드라이버로 연결한다"일 뿐 대상 제한 장치가 아니다. E-1 장치(`_local_postgres_guard`)는 비 TLS·SSPI·`jp_vocab_test_e` 전제라 운영형 조건(TLS·SCRAM·비소유)과 맞지 않는다. 그래서 E-1을 바꾸지 않고, 이 클러스터에만 맞는 별도 장치를 둔다.

- **위치**: 실제 드라이버(`psycopg.connect`)를 부르는 코드는 새 시험 전용 실행기 `backend/tests/_ops_pg62_runner.py` 하나에만 둔다(구현은 이 승인 뒤 별도 단위). `scripts/`의 공급자·어댑터·기본 진입점 `provide_connection`·운영 모드는 계속 거부한다. 실행기는 드라이버를 인자로 받지 않고 스스로 감싼 드라이버만 쓴다. CLI 인자·환경 변수·우회 플래그로 대상을 바꿀 수 없다.
- **신뢰 근거**: ① 생성 기록 `record.json`(관리 연결로 시작 직후 기록: 데이터 경로, 실행 파일 경로, 포트, postmaster PID와 그 실행 파일 경로, DB 이름·OID, 역할 이름·OID, 서버 인증서·CA 인증서 SHA-256, 식별 행 nonce, `system_identifier`) ② 그 기록의 SHA-256을 실행 승인 문서(시험 서명 키로 서명한 inquiry/apply)에 넣는다 ③ 실행기는 기록과 서명된 승인을 모두 다시 읽어 대조한다. 가짜 사전 검사 결과를 받는 입력은 없고, 실행기가 실제 5단위 사전 검사를 스스로 돌린다.
- **연결 전 검사**(연결마다): 호스트는 정확히 `localhost`, 포트 55462, DB는 두 이름 중 하나, 역할은 `jpv62_read`·`jpv62_write`(소유 거부 시험 동안만 `jpv62_owner_login`, 그 시험 전용 서명 승인과 생성 기록에 있을 때), `sslmode=verify-full`. PG 환경 변수 5종·`PGSERVICE` 등 있으면 거부(기존 `check_environment`). `data/postmaster.pid`의 PID가 기록과 같고, 그 PID의 실행 파일이 `C:/JV_Tools/pgsql-18.6/pgsql/bin/postgres.exe`이며, 55462 리스너 소유 PID가 그 PID일 때만 진행.
- **연결 후 검사**(관측 트랜잭션 안, 연결마다): 드라이버 `info.hostaddr`가 127.0.0.1 또는 ::1, SQL `inet_server_addr()`가 루프백, `inet_server_port()` = 55462, `server_version_num` = 180006, 식별 행 = 기록의 nonce 값, DB OID = 기록 값. 하나라도 다르면 롤백·닫기·거부.
- **거부해야 할 대상**: 55432(`pgdata-e2`), 다른 포트·호스트, Neon·운영 이름, `jp_vocab_test_e`·`postgres` DB, 관리 역할. 실행기는 `DATABASE_URL`·`.env`를 읽지 않는다.
- **관리 연결 분리**: 관리 연결은 실행기의 별도 함수에서 SSPI로만 열고(비밀번호 없음), 공급자·관측기·어댑터를 거치지 않으며 인계 객체를 만들지 않는다. HBA상 관리 역할은 SCRAM으로, 시험 역할은 SSPI로 들어올 수 없다. 관리 연결이 허용하는 작업은 이 계획 1·3·4절에 적힌 생성·변형·원복·정리 문장 목록뿐이다.
- **이번 단위 한계**: 같은 Windows 계정의 다른 프로세스가 파일·서버를 바꾸는 것은 막지 못한다. 보호 장치는 "이번 실행이 만든 클러스터에만 연결한다"를 확인할 뿐 운영 연결 허가가 아니다.

## 3. 검사표와 기대값 (순서대로, 기대값은 실행 결과에 맞춰 바꾸지 않음)

| # | 검사 | 기대 |
| --- | --- | --- |
| 1 | 정상 읽기 역할(62a): 사전 검사 → 사본 → 연결(verify-full) → 관측 → 대조 → 롤백 → IDLE → 인계 | 인계. 관측 `transaction_read_only=on`, 업무 기본 `default_transaction_read_only=on`·`read committed`, TLS 1.3, 프로필 지문 = 승인 |
| 2 | 정상 쓰기 역할 | 인계, 업무 기본 off, 관측은 READ ONLY |
| 3 | 인계 뒤 업무 첫 문장 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`(읽기)·`READ COMMITTED`(쓰기) | 성공, 롤백 뒤 SQL 미전송 확인(서버 로그·`pg_stat_activity`는 관리 연결로) |
| 4 | 관측 SQL 26개 전체: 구문·열 이름·타입 적재(`"char"`→text, oid·bigint, 배열 바인딩), 한정 연산자 | 오류 0, 6-1c 자료형 그대로 |
| 5 | 악성 search_path(관리자가 `evil` 스키마에 `=` 연산자·`current_setting` 같은 이름 함수 생성 후 역할 기본 search_path를 `evil, pg_catalog`로) | 관측값이 정상과 같고 `observed_search_path_mismatch`로만 거부 |
| 6 | 목록 밖 표 쓰기 권한, 표 권한 없는 열 단위 `UPDATE`, `PUBLIC`에 준 권한, 역할 소속(INHERIT·NOINHERIT 각각), 소유 역할(`jpv62_owner_login`, 1-1), 새 표·`SECURITY DEFINER` 함수·기본 권한 항목·매개변수 ACL·큰 객체 | 각각 초과·소속·소유·객체 불일치로 거부. NOINHERIT 소속은 소속 자체로 거부. 소유 역할은 인증 통과 뒤 `observed_ownership` |
| 7 | 열 수·열 목록·열 권한 완전성(정상, 열 0개 뷰, 삭제된 열 포함 표) | 정상 통과, 삭제 열 제외, 0개 뷰 허용 |
| 8 | 관측 중 객체 삭제(관리 연결이 질의 사이 표 삭제·열 추가) | unresolved로 거부(보장 아님, 재현되면 기록) |
| 9 | 다른 DB(62b) 연결 | `observed_identity_mismatch` |
| 10 | 잘못된 루트(wrong CA), SAN 불일치 서버 인증서 | 핸드셰이크 실패 `connect_failed`, 사본 정리 |
| 11 | 비 TLS: `hostnossl … reject` 확인(관리 쪽 시도), DSN `sslmode` 변경은 연결 전 거부 | 서버가 거부, 공급자는 연결 전 거부 |
| 12 | 제한 시간: `lock_timeout`(관리 연결이 식별 표에 `ACCESS EXCLUSIVE` 잠금을 잡은 채 관측) | `observation_lock_timeout`, 롤백·닫힘. 실제 연결 실패·연결 대기 제한(`connect_timeout`)과 `statement_timeout`(5초 > 잠금 2초라 잠금이 먼저 걸림)은 공급자 값을 바꾸지 않고는 재현할 수 없어 미검증으로 보고 |
| 13 | 롤백 실패·닫기 실패 | 실제로 재현하지 않음(가짜 검사로만 유지, 미검증으로 보고) |
| 14 | 재연결: 같은 승인으로 두 번 | 사전 검사·새 사본·새 관측 각 2회 |
| 15 | 보호 장치: 55432·다른 포트(예: 리스너 없는 55463)·`postgres` DB·관리 역할·PG 환경 변수·기록 해시 불일치·postmaster PID 불일치 | 연결 전 거부, 실제 연결 시도 0회. 이것은 보호 장치 검사이며 실제 연결 실패나 `connect_timeout` 검증으로 세지 않는다 |

- 기대값 정정(2026-10-22 검토): 처음 안의 #12는 55463 연결 거부를 `connect_failed`로 기대했지만, 이는 "다른 포트는 연결 전에 거부"하는 보호 규칙(#15)과 충돌했다. 보호 규칙을 유지하고 55463은 #15의 연결 전 거부로 옮겼다. 실제 연결 실패·대기 제한은 미검증으로 남긴다.

- 결과 분류와 중단:
  - **준비 실패**(initdb·인증서·서버 시작·역할 생성 실패, 포트 사용 중): 즉시 중단, 4절 절차로 이번 실행이 만든 것만 정리하거나 멈춤. 검사 결과로 세지 않는다.
  - **시험 장치 결함**(실행기·기록·변형 원복 오류): 중단하고 보고. 고친 실행기로 재실행하려면 다시 승인을 받는다.
  - **제품 결함**(정상 환경에서 공급자·관측기·어댑터가 계약과 다르게 동작, 예: 초과 권한 통과, 실제 SQL 구문 오류): 그 항목에서 중단하고 보고. 기대값을 바꾸거나 같은 실행에서 코드를 고치지 않는다.
  - 보호 장치 검사(#15)가 하나라도 연결을 허용하면 즉시 전체 중단.

## 4. 생성 근거와 정리

- 기록: 실행 시작 직후 `runs/<실행ID>/record.json`을 만들고, 단계마다(폴더, initdb, 서버 시작 PID, 역할·DB OID, 인증서 지문, 식별 nonce, 권한 변형과 원복) 추가 기록 후 디스크에 반영한다. 비밀번호·개인 키·연결 문자열은 넣지 않는다.
- 종료: `postmaster.pid`의 PID = 기록의 PID, 그 프로세스 실행 파일 = 기록의 `postgres.exe`, 데이터 경로 = 기록 값일 때만 `pg_ctl stop -D <data>`. 그 뒤 55462 리스너 없음 확인. 이름만 보고 프로세스를 끝내지 않는다.
- 정리: 기록에 있는 대상만 명시적으로(역할·DB는 이름과 OID가 기록과 같을 때만 `DROP DATABASE`/`DROP ROLE`, CASCADE 없음). 기존 클러스터·DB 재생성 없음.
- 잔존·불일치(기록에 없는 객체, PID·경로·OID 불일치, 정리 실패): 자동 정리하지 않고 멈춰 보고한다.

## 5. 승인 항목 (항목별 또는 한 번에)

| 항목 | 실제 수행 작업 | 원상 정리 |
| --- | --- | --- |
| A. 새 합성 클러스터 | `C:/JV_Tools/pg62/{data,tls,runs}` 생성, `initdb -D data -U jpv62_admin --auth=reject --encoding=UTF8 --locale=C`, 설정·HBA 작성, 포트 55462, `pg_ctl` 시작·종료(서비스 없음) | 서버 정지(PID 확인) |
| B. 로컬 TLS | Git `openssl.exe` 실행으로 시험 CA·서버 인증서·wrong CA·SAN 불일치 인증서 생성, 키 ACL 제한, CA 개인 키 즉시 삭제 | 키·인증서 삭제 |
| C. 시험 역할 | `jpv62_owner`(NOLOGIN)·`jpv62_read`·`jpv62_write`(SCRAM 검증값만 전송), 소유 거부 시험 동안만 `jpv62_owner_login`(1-1: 62a 한정 TLS+SCRAM HBA, 읽기와 같은 권한 + `owner_probe` 소유) | `owner_probe` 삭제 → 권한 회수 → 역할 삭제(각각 OID 확인, 시험 직후) |
| D. 합성 DB 둘 | `jp_vocab_test_62a`·`62b` 생성, 식별 표·행, 합성 업무 표 | DB 삭제(OID 확인) |
| E. 권한·변형 | 기대 프로필대로 GRANT, 3절 #5~#8·#12의 변형과 각 원복 | 원복 확인, 클러스터 삭제 시 함께 정리 |
| F. 관리자 작업·실행기 | 관리 역할 SSPI 연결, 서버 시작·reload·정지, 새 시험 실행기 `_ops_pg62_runner.py`·보호 장치 구현과 3절 실행 | 서버 정지, 리스너 없음 확인 |
| R1. 시험 뒤 보존 | `pg62/data`·`runs` 보존(서버는 끔), 키·인증서·비밀 폴더만 삭제 | 다음 실행 재사용은 별도 승인 |
| R2. 시험 뒤 삭제 | 기록 대조 후 `pg62/` 전체 삭제, 기록 사본만 저장소 밖 실행 폴더에 요약으로 남김 | — |

- **권장 조합**: A~F 일괄 + **R2(삭제)**. 이유: 비밀번호·키가 실행마다 새로 생기므로 클러스터를 남길 이점이 적고, 남은 TLS·역할이 다음 실행의 근거를 흐린다. 실행 순서는 B 전에 F의 실행기·보호 장치 구현과 합성 검사(가짜 드라이버)를 먼저 끝내고, 그 뒤 A→B→C→D→E→3절 순으로 진행한다.
- **실행 뒤에도 미검증으로 남는 것**: 실제 연결 실패(리스너 없음·거부)와 연결 대기 제한(`connect_timeout`), 관측 `statement_timeout`, 실제 롤백·닫기 실패, 같은 Windows 계정의 다른 프로세스 간섭.
- **위험과 중단 조건**: 55462가 사용 중, `pg62/`가 이미 있음, `pgdata-e2`가 실행 중이어서 PID 대조가 모호함, 시작한 서버의 PID·경로가 기록과 다름, 보호 장치 검사에서 연결 허용, 기록에 없는 잔존 객체 → 모두 즉시 중단·보고. 같은 Windows 계정의 다른 프로세스 간섭은 막지 못하는 한계로 남는다.

6-2 실제 로컬 PG 준비·실행 승인 대기.

## 6. 실행 결과 (2026-10-22, 실행 ID 20261022T181933) — 상세는 REPORT 46절

- 준비 완료 후 검사표 10개 실제 통과(#1~#11, #4는 c03), #12 잠금 검사에서 결과 기록 키 충돌(시험 장치 결함)로 3절 규칙대로 중단. #14·#15·#16(매개변수 ACL·큰 객체)은 실행하지 않았다. 실행기 결함은 고쳤지만 재실행은 새 승인이 필요하다.
- R2 정리: 기록과 PID·실행 파일·리스너·DB/역할 OID를 대조한 뒤 서버 정지, `C:/JV_Tools/pg62` 삭제, 55462 리스너 없음.
- 2차 재실행(같은 A~F + R2 재승인, 실행 ID 20261022T183550): 기록 단계 보정 후 새 클러스터에서 대표 읽기·쓰기와 #12·#14·#15·#16 실제 통과. R2로 서버 정지·`pg62` 삭제. 상세는 REPORT 46-1절.
- 마감(2026-10-22): 실행기 종료 코드 보정(REPORT 46-2)이 독립 검토에서 통과해 6-2를 닫는다. 미검증(실제 연결 실패·`connect_timeout`, 관측 `statement_timeout`, 실제 롤백·닫기 실패, 같은 계정 다른 프로세스 간섭)은 그대로 유지한다. 6-2 클러스터는 삭제됐으므로 이후 실제 PG 검사는 새 준비·접속 승인이 필요하다.

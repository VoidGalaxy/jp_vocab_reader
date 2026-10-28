# 연결 공급자·연결 후 재확인 계약안 (6-0단위 보정 1차, 2026-10-22, 재검토 대기)

보정 1차 요지(검토 2건): 관측 트랜잭션의 읽기 전용과 업무 기본 설정·승인 프로필을 분리했다(2-2·3절). 권한 검사를 "프로필 목록의 권한 확인"에서 "정의한 범위 안 실효 권한 전체 집합의 정확 일치"로 바꾸고 범위·제외·한계를 적었다(2-1절).

상태: **설계안. 승인되지 않았다.** 문서만 썼다. 앱 import, DB 접속, PG·서버 실행, 키·인증서 생성, 설치·다운로드는 없었다. 운영 모드는 계속 거부한다.
기준: 1~5단위 합성 구현(최근 독립 검사 121개 중 119 통과·2 건너뜀). 기존 판정·서명·manifest 검사는 다시 설계하지 않는다. 관련: `OPS_TOOL_SAFETY_CONTRACT.md` 3·6·7·7-1·8절, `OPS_SIGNATURE_DESIGN.md`.

## 0. 코드 근거 (이 기기에서 확인, 연결 없이)

| 항목 | 근거 |
| --- | --- |
| 드라이버가 주는 연결 정보 | psycopg 3.3.4 `Connection.info`(`ConnectionInfo`): `dbname`·`user`·`host`·`port`·`server_version`·`transaction_status`·`backend_pid`·`parameter_status` |
| TLS 사용 여부 | `Connection.pgconn.ssl_in_use`(bool). 이 바이너리 빌드에는 `ssl_attribute`가 없다 → 프로토콜·암호는 SQL `pg_stat_ssl`로 본다 |
| 연결 제한 시간 기본값 | `psycopg.conninfo._DEFAULT_CONNECT_TIMEOUT = 130`초, `timeout_from_conninfo`는 `connect_timeout`이 없거나 0 이하면 이 기본값을 쓴다(libpq 규칙상 최소 2초) |
| 트랜잭션 상태 | 기본 `autocommit=False`: 첫 문장 앞에 드라이버가 `BEGIN`을 보낸다. `rollback()`, `transaction_status`, `closed`·`broken` 속성이 있다 |
| 기존 앱의 읽기 전용 방식 | `app/database.py` `get_connection(read_only=True)`가 연결 직후 `SET TRANSACTION READ ONLY`를 보낸다(새 트랜잭션의 첫 문장이어야 함) |
| 기존 로컬 PG 장치 | `tests/_local_postgres_guard.py`(루프백·시험 DB 이름·PG 환경 변수 거부·빈 DB 확인), `scripts/_local_test_postgres.py`(DB 이름·루프백·제한 역할·표식 표 OID·nonce 확인, `-c default_transaction_read_only=on` 등 세션 옵션). 로컬 시험 역할은 표 소유자이고 SSPI·비 TLS다 |
| 인증서 도구 | PATH에는 `openssl`이 없고, `C:\Program Files\Git\usr\bin\openssl.exe`가 있다(실행하지 않음) |

## 1. 연결 공급자

- 모든 운영형 연결은 공급자 하나만 연다. 재연결도 새 연결로 보고 처음부터(아래 2·3절) 전부 다시 검사한다.
- 공급자는 시작 때 고정한 값만 쓴다: 사전 검사(5단위)를 통과한 연결 정보·승인·manifest 바이트, 그 결과(DB 식별 지문, 단계 역할·프로필, TLS 루트 항목). 실행 중 환경 변수·파일을 다시 읽어 대상을 바꾸지 않는다.
- 사전 검사 일치(`connection_allowed=False`)와 실제 연결 허용은 다르다. 실제 연결은 ① 사전 검사 일치 ② 이 계약의 연결 후 재확인 통과 ③ 운영이면 별도 운영 승인이 모두 있을 때만 업무 계층에 넘어간다. 이번 설계 단계에서 운영은 계속 거부한다.
- 공급자가 고정해 붙이는 매개변수(사용자 연결 문자열에는 여전히 금지, 6-1 파서 그대로):

| 매개변수 | 고정값(권장) | 이유 |
| --- | --- | --- |
| `connect_timeout` | 10 | 기본 130초 대기를 막는다 |
| `sslrootcert` | 공급자가 만든 검증 사본 경로(5절) | 드라이버가 읽는 바이트를 manifest 바이트와 맞춘다 |
| `sslcertmode` | `disable` | 기본 위치의 클라이언트 인증서 자동 사용 방지 |
| `gssencmode` | `disable` | GSS 시도·외부 설정 의존 방지 |
| `options` | 업무 기본 설정: 읽기 단계 `-c default_transaction_read_only=on`, 쓰기 단계 `-c default_transaction_read_only=off`, 단계별 `-c default_transaction_isolation=…`(2-2). 공통 `-c idle_in_transaction_session_timeout=60s` | 서버 측 업무 기본값 고정, 방치 트랜잭션 정리 |
| `application_name` | 고정 이름(값은 결정 항목) | 서버 쪽 식별 |
| `channel_binding` | `require`(결정 항목) | SCRAM 사용 시 중간자 완화 |

- 기존 CLI·앱 연결(`get_connection`)에 공급자를 주입하는 작업은 이번 범위 밖이다.

## 2. 연결 후 관측 (같은 연결에서, 호출자 제공값만으로는 통과 없음)

| 관측 | 출처 | 비교 대상 |
| --- | --- | --- |
| 접속 호스트·포트 | 드라이버 `info.host`·`info.port` | 사전 검사의 승인 대상 |
| DB 이름 | SQL `current_database()`(드라이버 `info.dbname`과도 대조) | 승인 대상 |
| 서버 주 버전 | SQL `current_setting('server_version_num')`(드라이버 `info.server_version`과도 대조) | DB 식별 지문 입력 |
| 운영 식별 행 | SQL로 식별 표의 행 읽기(표 이름·형식은 결정 항목) | DB 식별 지문 입력 |
| 현재·세션 역할 | SQL `current_user`, `session_user` | 승인 단계 역할 |
| 역할 속성 | SQL `pg_roles`(rolsuper·rolcreaterole·rolcreatedb·rolreplication·rolbypassrls·rolinherit) | 모두 거짓이어야 함(rolinherit는 프로필에 기록) |
| 소속 | SQL `pg_auth_members` 재귀(INHERIT·SET 옵션 포함) | 권장: 소속 없음(2-1) |
| 실효 권한 | 2-1절 범위 전체를 SQL `has_*_privilege`로 열거 | 2-1절 정규화 집합의 지문 = 승인 프로필 |
| 소유 | 2-1절 소유 검사 | 0 |
| search_path | SQL `current_setting('search_path')` | 고정값 |
| 업무 기본 설정 | SQL `current_setting('default_transaction_read_only')`·`current_setting('default_transaction_isolation')`(세션 기본값. 관측 트랜잭션의 `SET TRANSACTION`에 영향받지 않음) | 2-2절 |
| 관측 트랜잭션 상태 | SQL `current_setting('transaction_read_only')` | 항상 on(관측 안전 조건 확인용, 프로필·업무 판정에 쓰지 않음) |
| TLS 사용 | 드라이버 `pgconn.ssl_in_use` + SQL `pg_stat_ssl`(자기 `pg_backend_pid()`의 `ssl`·`version`) | 둘 다 사용 중, 버전은 허용 목록 |

- DB 식별 지문은 위 관측값으로 다시 계산해 승인 값과 비교한다(3-1). 연결·권한 지문(프로필)은 관측한 역할·속성·소속·2-1절 권한 집합·소유·search_path·**업무 기본 설정**·TLS 사용을 정규화해 계산하고 승인 단계 프로필과 비교한다. 관측 트랜잭션의 `transaction_read_only`는 넣지 않는다. 5단위의 호출자 제공 관측값은 여기서 실제 관측값으로 대체되고, 다르면 거부한다.

### 2-1. 권한 검사 범위 (보정 1차)
검사하는 것은 **아래에 정의한 범위 안의 실효 권한**이다. DB의 모든 권한을 완전히 증명하지 않는다.

- 방식: 범위 안 모든 객체·권한 조합을 열거해 "현재 역할이 가진 실효 권한"의 정규화 집합을 만들고, 그 지문이 승인 프로필 지문과 **정확히 같아야** 한다. 그래서 필요한 권한의 존재와 허용 목록 밖 권한의 부재를 한 번에 확인한다(하나라도 더 있거나 빠지면 불일치).
- 실효 권한: `has_*_privilege(current_user, …)`는 직접 부여, INHERIT 소속 역할, `PUBLIC` 부여를 모두 반영한다. 다만 INHERIT 없이 `SET ROLE`로만 얻는 권한은 반영하지 않는다 → 권장: 운영 역할은 **소속 없음**. 소속이 하나라도 있으면(승인 프로필이 허용하지 않는 한) 거부한다.

| 대상 | 범위 | 확인할 권한 | 판정 |
| --- | --- | --- | --- |
| 관계(표·분할 표·뷰·구체화 뷰·외부 표) | 시스템 스키마(`pg_catalog`·`information_schema`·`pg_toast*`·`pg_temp*`) 밖의 모든 `pg_class`(relkind `r`·`p`·`v`·`m`·`f`) | `SELECT`·`INSERT`·`UPDATE`·`DELETE`·`TRUNCATE`·`REFERENCES`·`TRIGGER`·`MAINTAIN` | 집합에 포함 |
| 열 | 위 관계의 모든 사용자 열(`attnum > 0`, 삭제 열 제외) | `SELECT`·`INSERT`·`UPDATE`·`REFERENCES`(표 수준 권한이 없을 때 열 단위로 생기는 초과 권한 포함) | 집합에 포함 |
| 시퀀스 | 같은 스키마 범위의 relkind `S` | `USAGE`·`SELECT`·`UPDATE` | 집합에 포함 |
| 스키마 | 시스템 밖 모든 스키마 | `USAGE`·`CREATE` | `CREATE`는 어디에도 없어야 함 |
| 데이터베이스 | 현재 DB | `CONNECT`·`CREATE`·`TEMPORARY` | `CREATE`·`TEMPORARY` 없음(권장) |
| 테이블스페이스 | 모두 | `CREATE` | 없음 |
| 함수·프로시저 | 시스템 밖 스키마의 `SECURITY DEFINER` 루틴 | `EXECUTE` | 승인 프로필에 없는 것이 실행 가능하면 거부 |
| 기본 권한 | `pg_default_acl` 전체 | 현재 역할·`PUBLIC`에 앞으로 생길 객체의 쓰기 권한을 주는 항목 | 없어야 함 |
| 매개변수 | `pg_parameter_acl` 전체 | 현재 역할·`PUBLIC`에 준 `SET`·`ALTER SYSTEM` | 없어야 함 |
| 큰 객체 | `pg_largeobject_metadata` | 현재 역할의 `SELECT`·`UPDATE` | 없어야 함(앱이 쓰지 않음) |

- 소유: 현재 역할(그리고 허용된 소속이 있다면 그 역할들)이 소유한 관계·스키마·루틴·타입·큰 객체·DB·테이블스페이스·기본 권한 항목의 수가 0이어야 한다. 소유자는 모든 권한과 `GRANT`·`DROP`을 가지므로 소속 역할을 통한 소유도 같은 기준으로 본다.
- 제외와 근거·한계:
  - `SECURITY INVOKER` 함수의 `EXECUTE`: 기본으로 `PUBLIC`에 열려 있고 호출자 권한으로 돌아 위 표·열 권한을 넘지 못한다. 단 함수 안의 동적 SQL·외부 호출이 하는 일은 이 검사 밖이다.
  - 타입·도메인·언어·외부 데이터 래퍼·서버의 `USAGE`, 행 수준 보안 정책의 내용, 이벤트 트리거, 시스템 카탈로그 객체는 검사하지 않는다. `BYPASSRLS`는 역할 속성으로 거부한다.
  - 관측은 관측 트랜잭션 시점의 상태다. 관측 뒤 새로 생긴 객체·권한은 다음 연결의 관측 때까지 보지 못한다(기본 권한 항목 검사가 일부를 막는다).
- 예상 밖 객체·판정 불가: 범위 안에 정의하지 않은 relkind, 권한 함수 오류(관측 중 삭제된 객체 등), 해석할 수 없는 ACL 값은 통과로 치지 않고 `privilege_scope_unknown`으로 거부한다.
- 프로필 고정: 승인 단계의 `profile` 지문은 위 정규화 집합(범위 정의 버전 `jp-vocab-ops/profile/v1` 포함)의 해시다. 범위 정의가 바뀌면 지문도 바뀐다. 사람이 검토할 기대 집합 파일은 서명된 manifest에 넣는 것을 권장한다(`ops/profiles/<이름>.json`). 다만 3단위 파일 규칙은 지금 `ops/tls/*.pem`만 받으므로 이 경로 허용은 **결정 항목**이며, 결정 전에는 승인 지문만으로 고정한다.

### 2-2. 관측 안전 조건, 업무 기본 설정, 승인 프로필 (보정 1차)

| 구분 | 무엇 | 어디에 쓰나 |
| --- | --- | --- |
| 관측 안전 조건 | 관측 트랜잭션은 읽기·쓰기 연결 모두 첫 문장 `SET TRANSACTION READ ONLY`. 그 안의 `transaction_read_only`는 항상 on이어야 함 | 관측 자체의 안전 확인뿐. 프로필·1단위 판정에 넣지 않음 |
| 업무 기본 설정 | 롤백 뒤 새 업무 트랜잭션에 적용될 세션 기본값: `default_transaction_read_only`(읽기 단계 on, 쓰기 단계 off), `default_transaction_isolation`(승인 프로필에 적힌 값), 드라이버 `Connection.read_only`·`isolation_level`이 설정되지 않음(None) | 승인 프로필 지문에 포함 |
| 1단위 `Observed.read_only` | 업무 기본 설정의 `default_transaction_read_only` 값 | 읽기 단계는 True, 쓰기 단계는 False여야 1단위가 통과시킨다 |

- 그래서 쓰기 연결도 관측 중에는 읽기 전용이지만, 1단위에는 업무 기본값(off)이 넘어가 정상 쓰기 단계가 `write_step_read_only`로 거부되지 않는다.
- 공급자는 업무 계층의 첫 트랜잭션 설정(`SET TRANSACTION ISOLATION LEVEL …`)을 미리 실행하지 않는다. 업무 기본 설정은 연결 매개변수(`options`의 `-c default_transaction_read_only=…`)로만 정하고, 관측으로 확인만 한다.
- TLS의 두 의미를 구분한다. `ssl_in_use`·`pg_stat_ssl`은 "암호화된 연결을 쓰고 있다"만 보여 준다. 서버 인증서가 고정 루트로 서명됐고 호스트 이름이 맞는지(verify-full)는 핸드셰이크 때 libpq가 검사하며, 연결 뒤에 따로 관측할 수 없다. 그래서 이 보장은 "공급자가 `sslmode=verify-full`과 검증 사본 `sslrootcert`를 실제로 넘겼다"는 호출 사실과 연결 성공에 기댄다.

## 3. 검증 트랜잭션과 인계

- 관측은 한 트랜잭션에서 한다. 첫 문장은 `SET TRANSACTION READ ONLY`(2-2 관측 안전 조건, 쓰기 단계 연결도 같음), 이어서 `SET LOCAL statement_timeout`·`SET LOCAL lock_timeout`(4절), 그다음 관측 질의(업무 기본 설정도 이 안에서 세션 기본값으로 읽는다).
- 관측이 끝나면 성공·실패와 관계없이 `rollback()`하고, **SQL 없이** 드라이버 `info.transaction_status`가 IDLE인지 확인한다. `autocommit=False`에서는 롤백 뒤 어떤 질의든 새 트랜잭션을 열기 때문이다. 부득이 롤백 뒤 확인 질의를 보내면 그 뒤 다시 롤백하고 IDLE을 확인해야 하며, 권장안은 롤백 뒤 질의를 보내지 않는 것이다.
- 롤백·IDLE 확인과 함께 드라이버 `Connection.read_only`·`isolation_level`이 설정되지 않았는지(None) 확인한다. 이 모두가 성공한 연결만 업무 계층에 넘긴다.
- 인계 뒤 업무는 새 트랜잭션의 첫 문장으로 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY` 등을 실행할 수 있어야 한다. 공급자는 그 문장을 미리 실행하지 않는다. 관측은 세션 수준 설정을 바꾸지 않는다(`SET LOCAL`만 사용, 롤백으로 원상).
- 실패 시 연결은 반환·재사용하지 않고 닫는다. 오류 우선순위(높은 것 하나를 코드로, 나머지는 고정 코드 목록으로 실행 기록에):
  1. `connection_close_unconfirmed`: 닫기 실패. 서버 세션이 남았을 수 있다.
  2. `observation_rollback_failed`: 롤백 실패 또는 IDLE 아님.
  3. 원래 실패: 관측 불일치(`observed_target_mismatch`·`observed_profile_mismatch`·`observed_tls_not_in_use` 등), 관측 질의 시간 초과, 연결 실패(`connect_failed`·`connect_timeout`).
- 불확실한 연결(롤백·닫기 상태를 모르는 연결, `broken` 연결)은 어떤 경로로도 반환하거나 풀에 넣지 않는다.

## 4. 제한 시간·수명

| 대상 | 방식 | 권장값 |
| --- | --- | --- |
| 연결 수립 | 공급자 고정 `connect_timeout` | 10초 |
| 관측 질의 | 관측 트랜잭션 안 `SET LOCAL statement_timeout` | 5초 |
| 잠금 대기(관측) | `SET LOCAL lock_timeout` | 2초 |
| 방치 트랜잭션 | 세션 `idle_in_transaction_session_timeout` | 60초(결정 항목) |
| 닫기 | `close()` 한 번, 재시도 없음 | 별도 시간 제한 없음(동기 호출) |

- 업무 질의의 제한 시간은 각 도구 계약이 정한다(이 공급자는 관측 단계만 정한다).
- 접속 전후 오류는 모두 고정 코드로 바꾸고 연결 문자열·SQL·드라이버 원문을 담지 않는다.
- 한계: `connect_timeout`은 이름 해석(DNS)을 포함한 모든 OS 호출의 절대 종료를 보장하지 않는다. 서버 쪽 `statement_timeout`은 네트워크가 멈춘 경우 클라이언트 대기를 끊지 못한다. TCP keepalive 값은 결정 항목이다. `close()`는 동기 호출이라 상한을 보장하지 않는다.

## 5. 파일·인증서 경계

- 틈: 5단위는 manifest의 `ops/tls/*.pem` 바이트를 검사하지만, 드라이버는 연결 때 `sslrootcert` 경로의 파일을 **다시** 읽는다. 그 사이 파일이 바뀔 수 있다.
- 제안: 공급자는 연결 직전 그 인증서 파일을 3단위 규칙(링크·하드 링크 거부, 정체·크기 대조)으로 다시 읽어 manifest 해시와 대조하고, 일치한 바이트를 실행별 전용 임시 폴더에 쓴 사본의 경로를 `sslrootcert`로 넘긴다. 연결 수립 뒤 사본을 지운다. 재연결은 사본을 새로 만든다.
- 관계: 드라이버가 읽는 바이트 = 공급자가 쓴 사본 = 연결 직전 manifest 해시와 일치한 바이트. 사본을 쓴 뒤 드라이버가 읽기 전까지 같은 OS 계정의 다른 프로세스가 사본을 바꾸는 것은 막지 못한다.
- libpq 기본 위치(`%APPDATA%\postgresql\root.crl` 등)의 폐기 목록은 있으면 쓰일 수 있다(제한만 더함). 기본 위치의 클라이언트 인증서는 `sslcertmode=disable`로 쓰지 않는다.
- 보장할 수 없는 부분(같은 계정의 사본 변조, 서버 인증서 체인의 실제 내용)은 **미검증**이며 운영 차단 조건으로 남긴다.

### 5-1. 검증 사본 구현 경계 (6-1b, 2026-10-22)
- 입력: manifest 바이트(시작 때 고정)와 배포 루트. TLS 루트는 manifest의 `ops/tls/*.pem`이 **정확히 하나**일 때 그 항목이다. 0개·여러 개는 `tls_root_not_bound`, 다른 경로를 인자로 받아 대체하지 않는다.
- 읽기: 3단위의 경로·링크·하드 링크·파일 정체·크기·해시 검사를 그대로 쓰고(공용 함수 `read_verified_entry`), 그 검사에서 읽은 **바로 그 바이트**를 돌려받는다. 원본을 다시 열어 복사하지 않는다.
- 쓰기: 실행마다 새 임시 폴더에 새 파일로만 쓴다(기존 파일 덮어쓰기 없음). 부분 쓰기는 남은 바이트를 이어 쓰고, 0바이트 쓰기는 진행 없음으로 즉시 거부한다(무한 반복 없음). 다 쓴 뒤 사본을 다시 읽어 검증한 바이트와 같은지 확인한다.
- 결과 의미: "사본 바이트 = 이번에 검사한 manifest 항목 바이트"뿐이다. manifest 승인·서명 유효성, 인증서 형식·신뢰성, 서버 인증 성공은 증명하지 않는다.
- 수명: 컨텍스트 하나로만 쓴다. 들어갈 때 사본을 만들고, 나갈 때 지운다. 경로는 사용 중에만 꺼낼 수 있고 종료 뒤에는 `tls_copy_closed`로 거부한다. 사용 중에는 사본에 읽기 핸들을 하나 열어 둔다(Windows에서는 공유 삭제 권한 없이 연 핸들이 있는 동안 다른 프로세스의 삭제·이름 변경이 실패한다). 같은 OS 계정의 다른 프로세스가 내용을 바꾸는 것은 막지 못한다.
- 정리: 종료는 보호 핸들 닫기 → 파일 삭제 → 폴더 삭제 순이다. 이미 정리를 마친 뒤의 종료는 아무것도 하지 않는다.
  - 보호 핸들(파일 번호)은 닫기를 **한 번만** 시도하고, 성공 여부와 관계없이 그 번호를 다시 닫지 않는다(P1 보정, 2026-10-22). 닫기가 실패하면 번호를 버리고 "보호 핸들 닫기 미확인" 상태를 따로 남긴다. 실패 뒤 같은 번호가 다른 파일에 재사용될 수 있기 때문이다. `fstat` 성공이나 번호의 존재로 원래 핸들이라고 판단하지 않는다.
  - 파일·폴더 삭제는 정리 실패 뒤 명시적 종료 호출마다 한 번씩 다시 시도할 수 있다. 이 재시도는 핸들을 다시 닫지 않는다.
  - 보호 핸들 닫기 미확인은 모듈 안에서 종료를 증명할 수 없으므로 반복 호출해도, 파일이 사라져도 성공으로 바뀌지 않는다. 그동안 종료는 계속 `tls_copy_cleanup_unconfirmed`(부가 `tls_copy_guard_close_unconfirmed`)로 거부되고 경로는 내주지 않는다. 남은 실제 핸들의 처리는 이 모듈 밖이다.
- 오류 우선순위: ① `tls_copy_cleanup_unconfirmed`(임시 자료가 남았을 수 있음) ② 원래 실패(검증·임시 폴더·쓰기·사본 닫기·재확인 실패). 부가 실패는 고정 코드 목록으로만 남기고 파일 본문·경로·OS 오류 원문은 담지 않는다.

## 6. 단계별 검사표

### 6-1. ① 가짜 연결 기반 수명·오류 검사 (DB 없음)

| # | 사례 | 기대 |
| --- | --- | --- |
| 1 | 사전 검사 불일치 상태로 공급자 호출 | 연결 함수 미호출, 거부 |
| 2 | 공급자 고정 매개변수가 연결 함수에 정확히 전달(사용자 문자열에 추가 불가) | 인자 일치 |
| 3 | 관측값이 승인 대상·프로필과 다름(각 항목) | 거부, 연결 닫힘 |
| 4 | 호출자 제공값만 있고 관측이 없음 | 거부 |
| 5 | 관측 성공 → 롤백 → IDLE → 인계 | 인계, 업무 첫 문장 실행 가능 |
| 6 | 롤백 실패, IDLE 아님 | `observation_rollback_failed`, 닫힘 |
| 7 | 닫기 실패와 다른 실패의 조합 | 우선순위대로 |
| 8 | 연결 시간 초과, 관측 질의 시간 초과 | 고정 코드, 원문 없음 |
| 9 | 재연결 | 처음부터 전부 다시 검사, 이전 결과 재사용 없음 |
| 10 | 인증서 사본: 연결 직전 해시 불일치·링크, 사본 정리 | 거부·정리 |
| 11 | 오류·결과에 연결 문자열·SQL·드라이버 원문·비밀값 없음 | 없음 |
| 12 | 운영 모드 | 공급자 진입 전 거부 |
| 13 | 읽기 연결·쓰기 연결 모두 관측 트랜잭션이 READ ONLY로 성공 | 관측 성공 |
| 14 | 쓰기 연결: 관측 중 `transaction_read_only=on`, 업무 기본값 off | 1단위에 False 전달, 정상 쓰기 단계 통과 |
| 15 | 업무 기본 설정(`default_transaction_read_only`·격리 수준)이 승인 프로필과 다름 | 거부 |
| 16 | 인계 시점에 IDLE, 롤백 뒤 SQL 미전송, 드라이버 `read_only`·`isolation_level` 미설정 | 인계, 업무 첫 문장(`SET TRANSACTION …`) 실행 가능 |
| 17 | 정규화 권한 집합에 목록 밖 항목 하나 추가·하나 누락 | 프로필 불일치 거부 |
| 18 | 정의하지 않은 relkind, 권한 함수 오류, 해석 불가 ACL | `privilege_scope_unknown` |

### 6-2. ② 승인된 실제 로컬 PG 검사 (7절 준비가 승인된 뒤)

| # | 사례 | 기대 |
| --- | --- | --- |
| 1 | 비소유 읽기 역할, TLS verify-full, 정상 식별 행 | 관측 일치, 인계 |
| 2 | 비소유 쓰기 역할로 같은 작업 계획 | 관측 일치 |
| 3 | 다른(두 번째) 합성 DB에 연결 | 식별 불일치 거부 |
| 4 | 기존 표 소유 역할 | 소유·프로필 불일치 거부(완화 없음) |
| 5 | 잘못된 루트 인증서·호스트 이름 | 핸드셰이크 실패, 고정 코드 |
| 6 | 비 TLS 서버 | 연결 실패 또는 TLS 미사용 거부 |
| 7 | 롤백 후 업무 첫 문장 `SET TRANSACTION ... READ ONLY` | 성공 |
| 8 | 읽기 역할·쓰기 역할 각각 관측(READ ONLY) 뒤 정상 인계, 쓰기 단계가 관측 설정 때문에 거부되지 않음 | 통과 |
| 9 | 정상 최소 권한 프로필 | 지문 일치 |
| 10 | 목록 밖 표에 쓰기 권한 추가 | 거부 |
| 11 | 표 권한 없이 열 단위 `UPDATE` 초과 권한 | 거부 |
| 12 | 역할 소속을 통한 초과 권한, `PUBLIC`에 준 초과 권한 | 거부(소속 자체도 거부) |
| 13 | 예상 밖 객체(새 표·`SECURITY DEFINER` 함수·기본 권한 항목) 또는 판정 불가 | 거부 |
| 14 | 소유 역할로 연결 | 소유 검사로 거부 |

## 7. 실제 PG 준비 계획 (각각 별도 승인, 이번에 실행하지 않음)

현재 로컬 시험 역할(`jp_vocab_e2`)은 표 소유자이고 SSPI·비 TLS다. 이를 운영형 연결로 통과시키려고 조건을 완화하지 않는다. 기존 시험 클러스터(`C:/JV_Tools/pgdata-e2`, 포트 55432)와 그 보호 장치는 그대로 둔다.

- 권장 경로: **기존 클러스터와 분리된 일회용 합성 클러스터**를 따로 만든다. 기존 장치(루프백·시험 DB 이름·SSPI 제한 역할·표식 표)는 운영형 조건(비밀번호·TLS·비소유 역할)과 충돌하므로, 기존 장치를 바꾸거나 우회하지 않고 새 클러스터에만 운영형 조건을 둔다.

| 승인 항목 | 내용 | 원상 정리 |
| --- | --- | --- |
| A. 새 합성 클러스터 | 같은 PG 18.6 실행 파일로 새 데이터 폴더 `initdb`, 별도 포트, `listen_addresses=localhost`만 | 서버 정지 뒤 데이터 폴더 삭제 |
| B. 로컬 TLS | 시험 전용 CA·서버 인증서(호스트 `localhost`) 생성, 서버 `ssl=on`, `pg_hba`는 `hostssl ... scram-sha-256`만 | 인증서·키 파일 삭제 |
| C. 시험 역할 | 비소유 읽기 역할·쓰기 역할(비밀번호, 슈퍼유저·생성 권한 없음), 표 소유는 별도 소유 역할 | 역할 삭제 |
| D. 두 번째 합성 DB | 식별 불일치 시험용 | DB 삭제 |
| E. 식별 행·권한·ACL | 식별 표·행, 프로필대로 GRANT | 클러스터 삭제로 함께 정리 |
| F. 관리자 작업 | 위 준비를 위한 클러스터 관리자 역할 사용·서버 시작·설정 변경 | 시험 끝에 정지 |

- 인증서 생성 도구(Git의 `openssl.exe`)는 실행 승인 전 사용하지 않는다. 비밀번호·개인 키는 시험 임시 폴더에만 두고 시험 뒤 지운다.
- 구체 값·실제 연결 전용 보호 장치·검사표·중단 조건·생성 근거·정리·A~F 실제 작업과 보존(R1)/삭제(R2) 선택은 `OPS_REAL_PG_6_2_PLAN.md`(2026-10-22, 승인 대기)에 있다.

## 8. 사용자 결정 (승인 아님)
1. 공급자 고정값: `connect_timeout` 10초, 관측 `statement_timeout` 5초·`lock_timeout` 2초, `idle_in_transaction_session_timeout` 60초, `application_name`, `channel_binding=require`, TCP keepalive
2. 운영 식별 표의 이름·형식, 허용 TLS 버전 목록
3. 7절 A~F 각각의 실행 승인
4. 권한 범위: 운영 역할 소속 없음(권장), 데이터베이스 `TEMPORARY` 없음(권장), 기대 권한 집합 파일을 manifest의 `ops/profiles/`에 둘지(3단위 규칙 확장 필요)
5. 업무 기본 격리 수준(단계별)과 `default_transaction_read_only`를 연결 매개변수로 고정하는 방식

## 9. 6-1a 합성 구현 기준 (2026-10-22, 사용자 지시 — 합성 시험 기준일 뿐 운영 정책 승인 아님)

- 고정값: 연결 제한 10초, 관측 `statement_timeout` 5초·`lock_timeout` 2초, `idle_in_transaction_session_timeout` 60초, 업무 기본 격리 수준 읽기·쓰기 모두 `read committed`, 업무 기본 읽기 전용 읽기 on·쓰기 off, `application_name=jp_vocab_ops_synthetic`, 역할 소속 없음, DB `TEMPORARY` 없음. 나머지(`channel_binding`, keepalive, TLS 버전 목록, 식별 표 등)는 정하지 않는다.
- 연결 생성(`ConnectionFactory`)과 관측기(`Observer`)는 인터페이스다. 실제 구현은 없고 기본 진입점은 연결 전에 거부한다. 가짜 구현은 테스트에서만 주입하며, 가짜 관측값은 실제 서버 값이 아니고 운영 허용 근거가 될 수 없다. 운영 모드는 계속 거부한다.
- 관측 결과는 타입·필수 항목을 엄격히 검사하고, 권한은 **객체 목록**과 **실효 권한 집합**을 따로 정규화한다(권한 없는 새 객체도 객체 목록 변화로 잡힌다). 기대 프로필은 인자로 받고, `ops/profiles/` 파일 허용은 열지 않는다.
- 이 단위에서 공급자가 직접 보내는 SQL은 관측 트랜잭션 시작 문장 셋(`SET TRANSACTION READ ONLY`, `SET LOCAL statement_timeout`, `SET LOCAL lock_timeout`)뿐이다. 카탈로그 관측 SQL, 식별 표, 인증서 사본은 다음 단위다.
- 오류: 부가 실패는 고정 코드 목록(`also`)으로만 남기고, 대표 코드는 닫기 미확인 > 롤백 실패 > 원래 실패 순이다.
- 검토 보정(2026-10-22):
  - 프로필 형식 `jp-vocab-ops/profile/v2`: v1 항목에 **허용 TLS 버전 목록**(정규화: 정렬, 빈 목록·중복·형식 밖 값 거부)을 더했다. 순서만 다르면 같은 지문, 구성원이 다르면 다른 지문이다. 기대 목록을 바꾸면 그에 맞는 새 서명 승인이 있어야 하고, 없으면 연결 생성 전에 `expected_profile_not_approved`로 거부한다. 관측 TLS 버전도 승인된 목록 안이어야 한다. **호환**: v1 지문의 기존 승인은 v2 지문과 맞지 않아 거부되며 자동으로 바꾸지 않는다(새로 서명해야 함). 다른 기대값(객체 목록·권한 집합·search_path)은 이미 지문에 있었고, 소속 없음·소유 0·업무 격리 수준은 코드 상수로 지문에 들어간다. 미결합은 TLS 목록 하나였다.
  - 관측 결과의 중첩 구조(`role_attributes` 2개짜리, `objects` 3개짜리, `privileges` 5개짜리 튜플과 원소 타입)를 풀거나 집합·정렬하기 전에 확인하고, 어긋나면 `observation_invalid`로 기존 롤백·닫기 경로를 따른다.
  - 연결 `options`는 셸 인용이 아니라 libpq 규칙(값 안의 공백은 백슬래시로 이스케이프, 백슬래시는 두 번)으로 만든다: `-c default_transaction_isolation=read\ committed`. 드라이버 conninfo 파싱과 문서 규칙으로 만든 분리 검사만 했고, 실제 서버에서 적용됐는지는 미검증이다.

## 10. 6-1c 관측 SQL 수집기 (2026-10-22, 코드보다 먼저 고정, 가짜 커서로만 검사)

- 역할: 공급자가 넘긴 연결(관측 트랜잭션 시작 문장 셋이 이미 실행됨)에서 2·2-1·2-2절 값을 읽어 6-1a `Observation` 하나를 돌려준다. 연결 생성·`commit`·`rollback`·`close`·`execute`·업무 실행을 하지 않고 커서만 쓴다. 판정·인계·롤백·닫기는 기존 공급자 몫이다. 시작 때 `info.transaction_status`가 INTRANS가 아니면 `observation_not_in_transaction`.
- SQL 규칙: 모든 카탈로그·함수·타입·연산자는 `pg_catalog.`(연산자는 `OPERATOR(pg_catalog.=)`)로 한정한다. 설정 이름·권한 이름·relkind·정규식 같은 값은 바인딩한다. 식별자는 식별 표에만 쓰며 `psycopg.sql.Identifier`로 만든다. 질의는 모듈 상수뿐이고 외부 SQL 문자열을 받아 실행하는 경로는 없다. 행은 이름 붙은 열(`dict_row`)로 읽고 열 이름 집합이 정확히 같아야 한다.
- 식별 표(합성 시험 형식만, 운영 형식 미정): `jp_vocab_ops_synthetic.db_identity`의 `identity_value`(text, NULL 아님), 행은 **정확히 1개**. 표 생성·운영 형식 확정은 하지 않는다. 표가 없으면 `observation_identity_missing`, 0·2개 이상이면 `observation_identity_rows`.

| 질의 | 관측 항목 | 자료형·조건 | 실패 |
| --- | --- | --- | --- |
| `session` | DB 이름, `server_version_num`, `CURRENT_USER`·`SESSION_USER`, `search_path`, `default_transaction_read_only`·`default_transaction_isolation`, `transaction_read_only`, `lo_compat_privileges` | 1행. text, on/off는 정확히 `on`·`off`, 격리 수준은 PG 네 값, 버전은 숫자 5~6자리 | 형식 밖·NULL·행 수 → `observation_invalid`. 드라이버 `info.dbname`·`server_version` 주 버전과 다르면 `observation_driver_mismatch`. 주 버전 17 미만(`MAINTAIN` 없음) → `observation_server_unsupported` |
| `role` | `pg_roles`의 6개 속성 | 1행, bool | 행 수·NULL·타입 → `observation_invalid` |
| `memberships` | `pg_auth_members` 재귀 소속 역할 이름 | 0행 이상, 이름 중복 없음 | 이름 형식 밖 → `observation_invalid` |
| `ownership` | 현재 역할이 `MEMBER`인 역할이 소유한 관계·스키마·루틴·타입·큰 객체·DB·테이블스페이스·기본 권한 항목 수 | 1행, 8개 정수 ≥ 0, 합을 `owned_count`로 | NULL·음수·타입 → `observation_invalid` |
| `tls` | `pg_stat_ssl`(자기 `pg_backend_pid()`)의 `ssl`·`version` + 드라이버 `pgconn.ssl_in_use` | 1행. ssl 거짓이면 version은 `none`으로 표시(공급자가 거부) | ssl 참인데 version NULL → `observation_invalid` |
| `identity` | 식별 행 | 위 형식 | 위 코드 |
| 객체 목록 6종 | 관계·시퀀스(시스템 밖 스키마 `pg_class` 전체 relkind), 스키마, 현재 DB, 테이블스페이스, `SECURITY DEFINER` 루틴, 기본 권한 항목, 매개변수 ACL, 큰 객체 | oid·이름은 객체마다 1행 | oid 중복 → `observation_invalid` |
| 권한 7종 | 객체×권한 이름마다 `has_*_privilege(CURRENT_USER, …)` 1행(`granted`) | bool | 아래 |
| `default_acl_privileges`·`large_object_privileges` | `aclexplode`에서 수혜자가 `PUBLIC` 또는 현재 역할이 `USAGE`로 이어받는 역할인 항목 | 권한 이름이 정한 목록 안 | 목록 밖 → unresolved |

- 객체 식별값 `(종류, 스키마, 이름)`: relkind `r·p·v·m·f·S`는 2-1절 종류로, 색인·분할 색인·복합 타입(`i·I·c`)은 권한 대상이 아니라 제외, 그 밖 relkind는 `relkind_unknown`. 루틴은 오버로드가 합쳐지지 않게 `이름$` + 식별 인자 텍스트(`pg_get_function_identity_arguments`, 관측 search_path 기준 표기) SHA-256 앞 16자리. 기본 권한 항목은 `소유역할.종류`(스키마 없으면 빈 값), 큰 객체는 oid 문자열. 이름이 6-1a 이름 형식(`[A-Za-z0-9_.$-]`, 1~128자) 밖이면 `object_name_unrepresentable`, 서로 다른 객체가 같은 식별값이면 `object_identity_collision`. 둘 다 생략하지 않고 unresolved로 남겨 공급자가 `privilege_scope_unknown`으로 거부한다.
- 권한 집합: 객체 목록과 따로 모은다(권한 없는 새 객체도 목록에 남음). `granted`가 NULL(관측 중 삭제 등)이면 `privilege_check_null`, 객체 목록에 없는 oid의 권한 행은 `privilege_object_unknown`, 객체마다 요청한 권한 이름 행이 다 오지 않으면 `privilege_rows_incomplete`(모두 unresolved). 같은 (oid, 권한) 행 중복·요청하지 않은 권한 이름은 `observation_invalid`. 열 권한은 표 수준 권한이 없을 때 생기는 열 단위 권한만 `(종류, 스키마, 표, 열, 권한)`으로 넣는다. `ALTER SYSTEM`은 `ALTER_SYSTEM`으로 적는다. `lo_compat_privileges=on`이면 `large_object_compat_privileges`(unresolved).
- 예상 열 집합(보정, 2026-10-22): 열 권한 응답만으로는 "행이 없음"과 "열이 없음"을 구분할 수 없다. 그래서 권한 응답과 독립된 두 질의로 예상 열을 먼저 정한다. `column_counts`는 2-1절 관계(relkind `r·p·v·m·f`)마다 정확히 1행(사용자 열 수, `attnum > 0`·삭제 열 제외)이고, `columns`는 같은 기준의 (관계 oid, 열 이름) 목록이다. 관계 목록·열 수·열 목록이 서로 맞지 않으면(관계 행 누락·추가, 수와 목록 불일치) `column_list_mismatch`. 열 수 0인 관계는 열 수 행이 0을 말할 때만 정상이며, 응답이 없다는 이유로 0개로 추정하지 않는다.
- 열 권한 판정: 예상 열마다 요청한 권한 종류가 정확히 한 번씩 있어야 한다. 열 전체·관계 전체·일부 종류가 빠지면 `privilege_rows_incomplete`, 예상 밖 열이면 `column_unexpected`(둘 다 unresolved → 공급자가 롤백·닫고 `privilege_scope_unknown`). 같은 (oid, 열) 중복·같은 (oid, 열, 권한) 중복·NULL 이름·잘못된 타입·음수 열 수는 `observation_invalid`, 권한 NULL은 `privilege_check_null`. 열 식별은 (관계 oid, 열 이름)이라 다른 관계의 같은 이름 열과 합쳐지지 않는다. 표 수준 권한과 열 단위 초과 권한의 구분은 그대로다.
- 이 대조는 질의 사이 열 추가·삭제를 불일치로 거부할 뿐, 세 질의가 같은 시점을 봤다고 보장하지 않는다(질의마다 새 스냅숏, 아래 일관성 한계).
- 실효 권한 의미: 표·열·시퀀스·스키마·DB·테이블스페이스·루틴·매개변수는 `has_*_privilege`가 정하는 의미(직접·`PUBLIC`·INHERIT 소속)를 그대로 쓴다. 기본 권한·큰 객체는 ACL을 풀어 `PUBLIC`과 이어받는 역할만 고른다. 수혜자 구분(`PUBLIC`인지 역할인지)은 권한 튜플에 남지 않는다.
- 현재 `Observation`으로 표현하지 않는 것(보고만, 생략으로 통과시키지 않음): 소속의 INHERIT·SET·ADMIN 옵션(소속이 하나라도 있으면 거부되므로 이름만 남김), 권한의 `WITH GRANT OPTION`(2-1절 범위 밖, 미검사), 소유 수의 종류별 내역(합만), 기본 권한·큰 객체 권한의 수혜자. 범위 밖 소유(연산자·형변환·확장·게시 등)는 세지 않는다.
- 일관성 한계: 관측 트랜잭션은 업무 기본 격리(`read committed`)라 질의마다 새 스냅숏을 본다. 질의 사이 객체 변화는 oid 대조·완전성 검사로 일부만 잡고 unresolved로 거부한다.
- 오류: 드라이버 오류는 그대로 올려 공급자가 고정 코드(`observation_timeout`·`observation_lock_timeout`·`observation_failed`)로 바꾼다. 관측기가 내는 거부도 고정 코드뿐이며 SQL·연결 문자열·드라이버 원문을 담지 않는다(`from None`).
- 가짜 커서 검사는 변환·호출 계약 검사다. SQL이 실제 PG에서 실행되는지, `has_*_privilege`·`aclexplode`·재귀 소속·소유 질의가 실제 ACL 의미를 정확히 반영하는지는 증명하지 않는다(아래 실제 PG 확인 목록).
- 실제 PG에서 확인할 것: 모든 질의의 구문·열 이름·타입 적재(`"char"`→text 형변환, oid·bigint, 이름 배열 바인딩), 한정 연산자 동작, 악성 search_path에서의 결과 불변, `MAINTAIN`(17+)·`has_parameter_privilege`(16+)·`pg_parameter_acl`, 열 단위 초과 권한, `PUBLIC`·INHERIT/NOINHERIT 소속 의미, 기본 권한 `aclexplode`(PG18 큰 객체 `L` 포함), `lo_compat_privileges`, 오버로드 표기 안정성, `pg_stat_ssl` 자기 행, 관측 중 삭제 객체의 NULL, 시간 초과·잠금 대기 코드, 큰 카탈로그에서의 소요 시간.

## 11. 6-1d 연결 어댑터 통합 (2026-10-22, 코드보다 먼저 고정, 가짜 드라이버로만 검사)

- 순서(호출 하나 = 연결 하나, 재연결은 새 호출이라 전부 다시): 6-1a 공급자의 5단위 사전 검사 → 어댑터 `open`: ① 연결 인자 구성·검사 ② 6-1b 검증 사본 생성(새 임시 폴더) ③ 드라이버 연결 호출(`sslrootcert` = 사본 경로) ④ 호출이 끝난 뒤 사본 정리 → 공급자: 관측 트랜잭션 → 6-1c `CatalogObserver` → 승인·프로필 대조 → 롤백 → IDLE·드라이버 설정 확인 → 인계. 사본은 ④에서 사라지므로 관측·롤백·닫기 단계와 수명이 겹치지 않는다.
- 연결 인자: 사전 검사를 통과한 DSN을 libpq 파서(`conninfo_to_dict`, 연결 없음)로 다시 읽어 키가 정확히 `user`·`password`·`host`·`port`·`dbname`·`sslmode`·`sslrootcert`인지, `sslmode=verify-full`, `sslrootcert`가 manifest의 유일한 `ops/tls/*.pem` 원본 경로인지 확인한다(아니면 `connect_arguments_invalid`). 드라이버에는 구조화된 키워드 인자만 넘긴다: 사용자 값은 `user`·`password`·`host`·`port`·`dbname` 다섯 개, `sslmode`는 `verify-full` 고정, `sslrootcert`는 원본이 아닌 **검증 사본 경로**, 그 밖은 공급자 고정값(`application_name`·`connect_timeout`·`gssencmode`·`options`·`sslcertmode`) 정확히 그 집합. 사용자 값과 고정값이 같은 키를 가지거나 고정값 집합이 다르면 `connect_arguments_conflict`. 임의 kwargs·문자열 조합 DSN은 만들지 않고, 비밀번호는 출력·`repr`·오류에 담지 않는다.
- 수명: 드라이버 호출이 끝나기(성공·실패) 전에는 사본을 정리하지 않는다. 사본 생성·검증이 실패하면 드라이버를 부르지 않는다. 연결 성공 뒤 사본 정리가 실패하면 연결을 인계하지 않고 한 번 닫는다. 어댑터는 한 번만 쓴다(두 번째 `open`은 `adapter_already_used`).
- 오류 우선순위(대표 코드 하나, 나머지는 고정 코드 `also`): ① `connection_close_unconfirmed` ② `tls_copy_cleanup_unconfirmed` ③ `observation_rollback_failed` ④ 원래 실패(사본 생성·검증 코드, `connect_failed`·`connect_timeout`, 관측·대조 거부). 사본 정리 실패는 ④의 연결 실패와, 또는 성공한 연결의 닫기 실패와만 겹친다(관측 전에 사본을 정리하므로). 닫기 미확인·사본 정리 미확인은 어떤 경우에도 성공으로 바꾸지 않는다.
- 닫힌 경계(이번 단위): 실제 드라이버(`psycopg.connect`)를 부르는 코드는 없다. 어댑터 진입점은 드라이버 함수를 인자로 받아야만 동작하고, 테스트만 가짜를 넘긴다. 기본 진입점 `provide_connection`과 운영 모드는 계속 거부한다. 환경 변수·CLI 인자·우회 플래그는 없다. 이 단위의 통과는 실제 연결 허가도, TLS·인증·서버 `options` 적용의 증명도 아니다(인자를 넘겼다는 사실만 확인).
- 향후 실제 어댑터를 열 조건(각각 별도 승인): 7절 A~F 실제 로컬 PG 준비 승인과 그 준비 완료, 6-2 실제 검사표 통과, 실제 드라이버를 넘기는 진입점의 범위(합성 클러스터 한정)와 호출 위치 승인, 운영 신뢰 루트·키·실행 계정 결정(8절). 운영 모드는 이와 별도의 운영 승인이 있기 전까지 거부한다.

연결 공급자·연결 후 재확인 계약 승인 대기.

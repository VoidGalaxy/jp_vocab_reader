# 로컬 E-2 PostgreSQL 인계

2026-10-18 설치 및 실제 검사 완료. 최신 결과는 REPORT 9절 참조.

## 설치 상태
- PostgreSQL 18.6 Windows x64, EDB 공식 ZIP 배포본.
- 실행 파일: `C:/JV_Tools/pgsql-18.6/pgsql/bin`.
- 클러스터: `C:/JV_Tools/pgdata-e2`.
- 포트: 55432, localhost IPv4/IPv6 전용.
- Windows 서비스 없음. 종료 상태로 인계한다. 폴더와 ZIP은 보존했다.
- SSPI로 현재 Windows principal만 명시 매핑한다. 비밀번호와 trust 규칙은 없다.
- 관리 역할은 초기 생성에만 사용했다. 테스트 역할 `jp_vocab_e2`는 비관리자이며 `jp_vocab_test_e`만 소유한다. public 사용자 관계 수 0으로 정리했다.

## 다음 실행의 경계
1. 재설치·재초기화하지 말고 바이너리·PG_VERSION·포트·HBA를 확인한다.
2. 승인된 검사를 할 때만 이 클러스터를 pg_ctl로 시작한다. 배경 실행은 숨김으로 하고 서비스·방화벽을 만들지 않는다.
3. 앱 import 전에 APP_ENV=test와 전용 테스트 변수를 실행 셸에 설정한다. 연결 문자열을 파일·보고서에 쓰지 않는다. PG 대상 변수 5종이 있으면 중단한다.
4. `tests/_local_postgres_guard.py` 및 `tests/_srs_pg_harness.py`의 빈 DB·역할·실행 표식·oid 보호를 우회하지 않는다. 테스트에 관리 역할을 쓰지 않는다.
5. 새 실행은 소유 객체 정리 후 빈 DB에서 시작한다. 중단으로 객체가 남으면 임의 DROP·TRUNCATE로 비우지 말고 원인을 보고한다.
6. 종료 전 소유 객체 0을 확인한다. 서버 PID·실행 파일·자료 경로가 모두 맞는 PG만 pg_ctl로 종료하고 55432 리스너 부재를 확인한다. 설치·자료를 삭제하지 않는다.

## 남은 승인
E-2a의 준비된 다섯 단계 비교는 통과했다. 로그 FK 보존·계정 삭제·지연 쓰기·운영 전환 등 미승인 정책과 나머지 PG 검사표는 별개다. 실제 사용자 이전·운영 접속·FSRS 기본 활성화·커밋·푸시·병합은 하지 않았다.

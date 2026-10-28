# E-2c 검토 보정

2026-10-19. 사용자 "그부분은 너가 작업해줘"로 다음 두 건의 보정을 승인했다.
운영 접속, 실제 자료 적용, 새 삭제 정책, 커밋/푸시는 승인 범위가 아니다.

## 고정한 범위

1. 표식의 이름/1행 여부만 보던 검사를 실행 nonce와 표식 테이블 OID 비교로
   보강한다. 기대값은 부모 보호 장치의 자체 생성 기록에서만 전달한다.
2. 검증 거부나 검증 중 오류 뒤 close가 실패해도 원시 오류를 출력하거나
   연결을 반환하지 않는다. 고정 코드로 종료한다.

## 전달과 검증

- CLI는 기존 전용 URL/opt-in 외에 `SRS_E_TEST_POSTGRES_MARKER_NONCE`와
  `SRS_E_TEST_POSTGRES_MARKER_OID`를 요구한다. 명령행/파일/보고서로 값은
  전달하거나 보존하지 않는다. DB의 현재 값을 기대값으로 채우지 않는다.
- 부모 `PgRun.cli_marker_environment()`는 시작되었고 중단되지 않은 실행의
  자체 nonce/OID만 반환한다. 이 메서드는 DB에 접속하지 않는다.
- PG suite의 승인된 정리 CLI 자식과 in-process 호출에만 기대값을 전달한다.
  다른 자식에는 URL, opt-in, nonce, OID를 모두 제거한다. in-process 환경은
  성공/실패에 관계없이 이전 값으로 되돌린다.
- 기대 nonce는 보호 장치가 생성하는 소문자 16진수 32자리, OID는 유효한
  양의 PostgreSQL OID 범위의 십진수다. 누락/형식 오류는 접속 전 거부한다.
- 실제 연결에서 기존 DB/주소/포트/제한 권한 검사를 유지한다. 표식은 public의
  일반 테이블이며 현재 역할 소유이고 기대 OID와 같아야 한다. nonce도 정확히
  1행이며 기대값과 같아야 한다. nonce 읽기 후 카탈로그를 다시 확인한다.
- 표식 SELECT가 획득한 ACCESS SHARE는 확인 트랜잭션이 끝날 때까지 유지한다.
  별도 강한 표 잠금이나 앱 쓰기의 직렬화는 추가하지 않는다. 연결 확인 시점의
  증명이며 운영용 지속 권한/임대 계약을 새로 만들지 않는다.

## 실패 계약

- 기대값 누락: `run_marker_expectation_required`.
- 기대값 형식 오류: `run_marker_expectation_invalid`.
- 표식의 값/OID/종류/소유자 불일치 또는 검증 중 교체: `run_marker_mismatch`.
- 행 없음/복수 행: 기존 `run_marker_missing`.
- 드라이버 질의/검증 rollback 실패: 기존 `connected_target_unverifiable`.
- 거부 뒤 close도 실패: `local_postgres_close_failed`. 원시 오류/문맥은 숨긴다.
  close 성공으로 보고하지 않으며 연결을 반환하거나 재사용하지 않는다.
- 성공한 rollback 뒤에만 앱 래퍼로 넘긴다. 검증은 쓰기 0이며 정리 함수,
  배치 commit/CAS/잠금/커서/7일·30일 보존 규칙은 변경하지 않는다.

## 검증

수정 전 같은 회귀에서 잘못된 표식이 허용되고 종료 오류가 그대로 올라오는
것을 확인했다. 새 테스트, 실제 PG 결과와 최종 회귀 수는 REPORT 18절에 기록한다.

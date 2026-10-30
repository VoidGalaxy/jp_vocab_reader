# PG69 완료 결과 재조회 시험 대상 (2026-10-30, CR-PG1 코드 준비)

- 프리셋: `PG69_COMPLETED_REPLAY`, 배치: `PG69`
- 폴더: `C:/JV_Tools/pg69`, 호스트: localhost/loopback, 포트: 55532
- 관리자: `jpvq_admin`(SSPI), 소유자: `jpvq_owner`(NOLOGIN)
- 업무 역할: `jpvq_read`·`jpvq_write`(비소유·SCRAM)
- 템플릿: `jp_vocab_test_completed_template`
- 검사 DB: `jp_vocab_test_completed_p1`~`jp_vocab_test_completed_p10`
- 고정 검사: p1~p10, 관문 g0·g1·사후 확인은 통과 수에서 제외
- 공개 명령: prepare / check-completed / cleanup

명칭 등록·가짜 보호 검사만 승인된 상태다. 실제 클러스터·역할·DB 생성, 접속, GRANT, 관리자 자료 변경, 실제 검사, R2·보관은 별도 승인이 필요하다. 명령별 승인 상수는 None이며 외부 입력으로 활성화할 수 없다.

기대 권한은 `srs_migrate`의 현행 계약에서 계산한다. 새 권한·제품·승인 형식·상태 보정은 없다. 신규 시험 자료만 사용하며 기존 DB·다른 클러스터·운영·Neon·vocab.db에는 접근하지 않는다. 기록과 현재 대상이 다르거나 종료 미확인 기록이 있으면 정리하지 않는다.

설계·승인 경계는 `OPS_MIGRATION_COMPLETED_REPLAY_REAL_PG_PLAN.md` 8절을 따른다. 이 파일은 향후 시험 manifest에 대상 바이트를 결속하기 위한 문서이며 실제 실행 승인이나 실제 서버 증거가 아니다.

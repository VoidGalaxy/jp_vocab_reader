# 백업·복원 합성 리허설 증거 목록 (2026-10-25, 읽기만)

범위: PG 18.6 동일 클러스터의 합성 자료 논리 복원 리허설(`OPS_BACKUP_RESTORE_REHEARSAL_PLAN.md` 9·9-3절, REPORT 54·55절)의 비밀값 없는 증거 사본. 운영 백업·재해 복구·운영 실행 준비의 증거가 아니다.

| 실행 | 파일 | 절대 경로 | 크기(바이트) | SHA-256 |
| --- | --- | --- | --- | --- |
| 1차 20261025T122553 | 실행 기록 | `C:/Users/mjwmm/AppData/Local/Temp/claude/C--JV-Project-jp-vocab-reader/31735110-cd12-4705-a3fe-8f284e68018b/scratchpad/pg64_evidence/record.json` | 2927 | `661231c14c3fe62a57d6ac19055cf6ef64becdbfe4ede50c049a4e2d46da2999` |
| 1차 | 대상 기록 | `C:/Users/mjwmm/AppData/Local/Temp/claude/C--JV-Project-jp-vocab-reader/31735110-cd12-4705-a3fe-8f284e68018b/scratchpad/pg64_evidence/target.json` | 605 | `e071d22b233dc38ec6dc8cb6d52d93d38158f8d1a2e11907d766fd4008914334` |
| 1차 | 서버 로그 | `C:/Users/mjwmm/AppData/Local/Temp/claude/C--JV-Project-jp-vocab-reader/31735110-cd12-4705-a3fe-8f284e68018b/scratchpad/pg64_evidence/server.log` | 3418 | `3e734d7ccb2f8a8129e032a4c94a7994527b67085f95d6dce66a6397d950062c` |
| 2차 20261025T171354 | 실행 기록 | `C:/Users/mjwmm/AppData/Local/Temp/claude/C--JV-Project-jp-vocab-reader/31735110-cd12-4705-a3fe-8f284e68018b/scratchpad/pg64_evidence_run2/record.json` | 407906 | `d9c804a3eb57838624494acdd26b78f53b7c0257d54c9c1b699bb4b703dd0b31` |
| 2차 | 대상 기록 | `C:/Users/mjwmm/AppData/Local/Temp/claude/C--JV-Project-jp-vocab-reader/31735110-cd12-4705-a3fe-8f284e68018b/scratchpad/pg64_evidence_run2/target.json` | 605 | `7569595a8233636addb2526081dbf7944cdb6168418cb59697850cb9b749b391` |
| 2차 | 서버 로그 | `C:/Users/mjwmm/AppData/Local/Temp/claude/C--JV-Project-jp-vocab-reader/31735110-cd12-4705-a3fe-8f284e68018b/scratchpad/pg64_evidence_run2/server.log` | 10482 | `6ad68e48a377de9893d95af6636d1dbd3441dad519ca20a475712db13e86b131` |

- 대조: 각 실행 기록의 `target_written` 해시가 같은 실행의 대상 기록 해시와 일치한다(1차 `e071d22b…`, 2차 `7569595a…`). 1차 결과 `b1_dump` error 1건, 2차 결과 관문 pass + b1~b8 묶음 6개 pass.
- 덤프 파일은 B4 정리에서 `pg64`와 함께 삭제됐고 사본이 없다. 2차 덤프는 기록된 SHA-256(`2bcfd725…`)만 남는다.
- 비밀값 점검(패턴 수만 셈, 원문 미복사): 연결 문자열 비밀번호·`password=`·SCRAM 검증값·개인 키 머리글·`PGPASSWORD`/`sslpassword`·토큰 문자열 0건. `password_hash`는 합성 앱 표의 열 이름이다. 처리가 필요한 의심 자료 없음.
- 원시 증거는 이동·수정·삭제하지 않았다.
- **보존 한계**: 위치는 이 대화 세션의 임시 폴더로 장기 보존 장소가 아니며, 세션·임시 폴더 정리로 사라질 수 있다. 장기 보존 위치·기간·접근 제한은 **미결**이다. 이 해시 목록은 작성 시점의 내용 대조용일 뿐 진본성이나 장기 보존을 보장하지 않는다.

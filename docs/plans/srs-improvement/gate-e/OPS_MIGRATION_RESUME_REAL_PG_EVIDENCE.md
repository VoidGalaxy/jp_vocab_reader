# RS4 CLI `resume` 실제 로컬 PG 검증 증거 목록 (2026-10-28)

대상 범위: **PostgreSQL 18.6에서 개인 카드의 명시적 `resume` 경로 검증**(`OPS_MIGRATION_RESUME_REAL_PG_PLAN.md` 12·13·13-2·14절, REPORT 86·87·87-2·88절). 구독(어휘) 카드 재개, 실제 장애, 실제 백업·복원, 운영 실행은 범위 밖이다.

이 문서는 아래 14개 파일을 **읽기만** 해서 만들었다(이동·복사·수정·삭제 없음). 파일에 비밀값·개인 키·SQL 매개값은 없다. `password`·`secret` 문자열은 이벤트 이름(`passwords_rotated_in_memory`, `secret_folder_created/removed`)에만 나온다.

## 1. 실행별 결과 (합산하지 않음, 관문·사후 확인은 통과 수 제외)

| 실행 | 실행 ID | 결과 |
| --- | --- | --- |
| 1차 | 20261028T114240 | G0 통과, **G1 시험 장치 결함으로 중단**(`Harness.case` 목록 결속, 기록상 `preparation_failure`), 본 검사 **0/25**(미실행 25), 실행기 종료 1 |
| 2차 | 20261028T123027 | G0·G1 통과, 본 검사 **25/25**, 사후 확인 통과, 종료 0. 당시 r3는 실행 중 세 값을 비교해 통과했지만 기록에는 `compared` 이름만 있고 비교값 자체는 **보존되지 않았다** |
| 보완 | 20261028T131854 | `supplement_values`, G0·G1(r1·r2) 통과, **r1·r2·r3 3/3**, 여섯 딕셔너리 값 보존, 보완 사후 확인 통과, 종료 0 |

보완 실행은 2차 기록을 고치거나 소급해 채우지 않았다. 보완의 값은 그 실행의 r1·r2 DB에서 새로 얻은 것이다.

## 2. 파일 목록

| 실행 | 실행 ID | 파일 | 용도 | 절대 경로 | 크기(바이트) | SHA-256 |
| --- | --- | --- | --- | --- | --- | --- |
| 1차 | 20261028T114240 | `record.json` | 생성 기록·관문 결과·미실행 기록 | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T114240\record.json` | 8495 | `59e5c382bdf4b4a874697533dd0fc4189edba8de6979f595d7f0874fb8074edb` |
| 1차 | 20261028T114240 | `target.json` | 대상 사실(PID·OID·nonce 등) | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T114240\target.json` | 7286 | `4c896e40c7ab40ceae268baf326580d8cd254fdbbc303117bde1e96c29248b74` |
| 1차 | 20261028T114240 | `server.log` | 서버 로그(연결·종료) | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T114240\server.log` | 33852 | `dbcb1ce9e4cc903e88bd97ab885026548233b1a9ba7a0248e93fbc3011ac70f7` |
| 1차 | 20261028T114240 | `check_stdout.log` | `check` 표준 출력 | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T114240\check_stdout.log` | 192 | `b37ad9d600d43d3c9df803eb1ffa11fe52ca903b9b692cea00fc6b2a2ee2db5b` |
| 2차 | 20261028T123027 | `record.json` | 생성 기록·관문·25항목 결과·계측(계수·문장 순서·탐침·잠금 아래 읽기·대기 증거·정지점·권한 변형·관리자 변경) | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T123027\record.json` | 40291 | `95d2434f4b9e0001cd19f9d6d62ddb5ed566904a8a307c249379a19238200588` |
| 2차 | 20261028T123027 | `target.json` | 대상 사실 | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T123027\target.json` | 7285 | `607e55390e5acda594b5ca272c22776986bdba9f1deb6e08389dcb4fba95eb7c` |
| 2차 | 20261028T123027 | `server.log` | 서버 로그 | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T123027\server.log` | 304718 | `7b3ceaef39309f1b0ba712c0f13f72e39c44fdd9f7f521cbe6015af2f0418da7` |
| 2차 | 20261028T123027 | `check_stdout.log` | `check` 표준 출력 | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T123027\check_stdout.log` | 336 | `564c3515e17246a29ad4f2aebbc25d6865a3882018afc32ce1d8f4ba06f3e9bb` |
| 2차 | 20261028T123027 | `prepare_stdout.log` | `prepare` 표준 출력 | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T123027\prepare_stdout.log` | 10 | `aba1a6c58bc0c175b5a77d0a73a018cd667b7cd07efa6a1f0bd1fa001e07635c` |
| 보완 | 20261028T131854 | `record.json` | 생성 기록·관문·r1·r2·r3(여섯 딕셔너리)·보완 사후 확인 | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T131854\record.json` | 12270 | `82901439782ee31dfec8d4f14efefcde7972bbeb174ee466e98a329d44d464e7` |
| 보완 | 20261028T131854 | `target.json` | 대상 사실 | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T131854\target.json` | 7285 | `8f9351287dab396b26d955df63606612cad8306bdf9bd9b0c7d29a206bf6763a` |
| 보완 | 20261028T131854 | `server.log` | 서버 로그 | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T131854\server.log` | 58028 | `e039fcb468aa95d5010163262e64f3b09d6136ee33c36dfcfaeb0137a88d0964` |
| 보완 | 20261028T131854 | `check_values_stdout.log` | `check-values` 표준 출력 | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T131854\check_values_stdout.log` | 119 | `2e51d6c412caeba0c780e5675b4737de746ade9741a1c0f744e00f8bd67a5f3f` |
| 보완 | 20261028T131854 | `prepare_stdout.log` | `prepare` 표준 출력 | `C:\Users\mjwmm\AppData\Local\Temp\claude\C--JV-Project-jp-vocab-reader\31735110-cd12-4705-a3fe-8f284e68018b\scratchpad\pg66_evidence_20261028T131854\prepare_stdout.log` | 10 | `aba1a6c58bc0c175b5a77d0a73a018cd667b7cd07efa6a1f0bd1fa001e07635c` |

1차에는 `prepare` 표준 출력 파일이 없다(당시 보존하지 않음).

## 3. 대조 결과 (2026-10-28, 읽기 전용)

| 확인 | 1차 | 2차 | 보완 |
| --- | --- | --- | --- |
| 파일이 모두 있고 크기·SHA-256이 실행 직후 기록과 같음 | 예(4) | 예(5) | 예(5) |
| `record.json` 실행 ID = 폴더 실행 ID = `target.json` 실행 ID | 예 | 예 | 예 |
| `target_written` 이벤트 1개, 그 SHA-256 = `target.json` 해시 | 예 | 예 | 예 |
| `server_started` 1개, PID = `target.json`의 postmaster PID | 예 | 예 | 예 |
| 결과 기록 | G0 `pass`, G1 `fail`, `not_run` 25 | G0·G1·25항목·`post_check` 모두 `pass` | G0·G1·r1·r2·r3·`values_post` 모두 `pass` |
| 보완 표시 | - | - | `phase: supplement_values`, `checks: [r1, r2, r3]`, "not added to the earlier 25/25 result" |
| r3 저장 값 | - | `{"compared": ["r1", "r2"]}`만 | r1·r2 각각 `pre_read`·`under_lock`·`admin_values` 여섯 딕셔너리 모두 계약 9개 키, 실행별 세 값 일치 |

- 불일치·누락은 없다. 전체 값은 보완 `record.json`의 r3 `details.values`에 있으며 여기에 복제하지 않는다.
- 장기 보존 위치·기간(Q5)은 미결이다. 위 파일은 이 세션의 임시 폴더에만 있다.

## 4. 유지할 제한

- 미검증: 구독(어휘) 카드 재개(대표 재개는 개인 p2·p3), 실제 커밋 응답 유실·OS·네트워크 장애·서버 강제 종료, 실제 백업·복원, 운영 활성화·운영 실행.
- 30일 창: 실제 PG에서는 `started_at`을 31일 전으로 바꾼 실행이 `migration_resume_window_closed`로 거부되는 것만 확인했다(2차 r8 ③). 창 정각 거부와 1초 전 허용 경계는 합성 SQLite 증거(RS3)뿐이다.
- r2의 초기 `failed` 상태(2차·보완 G1)와 2차 r9b·r9c는 시험 장치 주입 결과다. 실제 장애 증거가 아니다.
- C10 근거는 합성 서명 진술이다. `restore_verified`·`backup_artifact_checked`는 `false`다.
- Q5(장기 보존 위치·기간)는 미결이다. 세션 임시 폴더와 이 해시 목록만으로는 파일의 보존이나 진본성이 보장되지 않는다(임시 폴더는 정리될 수 있고, 해시 목록도 같은 저장소 안의 문서다).

## 5. 현재 보관 위치 (2026-10-28 추가)

- **주 보관본**: `C:\JV_Evidence\rs4\<실행 ID>\`. 위 14개 파일을 같은 이름으로 새로 만들기 전용 복사했고, 다시 읽어 크기·SHA-256 14/14 일치를 확인했다.
  - 접근은 작업 사용자·SYSTEM·Administrators만 허용하며, `C:\JV_Evidence`에서 상속을 끊었다.
  - 인수 기록 `C:\JV_Evidence\rs4\custody.json`의 SHA-256은 `9df9d9a8cc854e87875120f0a100f24422ac03c2ebd19fe69465c0ac47a94062`이다.
  - 보존 기산일은 2026-10-28, 보존 기한은 2027-10-28이다(`OPS_EVIDENCE_RETENTION_PLAN.md` 8절).
- 2절의 원래 경로(세션 임시 폴더)는 원본 위치이며 그대로 유지한다(E5). 삭제는 승인되지 않았다.
- 별도 사본(E2)은 없다. 주 보관본은 같은 디스크에 있으므로 백업이 아니다.

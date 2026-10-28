# 최초 `apply` CLI 실제 로컬 PG 검증 증거 목록 (2026-10-27, C12 + 시퀀스 USAGE 조정 S3)

대상 범위: **최초 `apply` CLI의 실제 로컬 검증**(`OPS_APPLY_REAL_PG_PLAN.md` 9~11절, REPORT 72~74절)과 **PostgreSQL 18.6 최초 `apply` 경로의 두 시퀀스 USAGE 제거 검증**(`OPS_APPLY_SEQUENCE_PRIVILEGE_PLAN.md` 7·8절, REPORT 78절). 재개·완료 재호출·상태 보정(미구현), 운영 활성화, 실제 장애·백업 검증은 이 목록의 범위가 아니다.

이 문서는 아래 12개 파일을 **읽기만** 해서 만들었다(이동·복사·수정·삭제 없음). 로그 원문과 비밀값은 싣지 않는다. 12개 파일에 비밀번호·키 값은 없고, `password`·`secret` 문자열은 이벤트 이름(`passwords_rotated_in_memory`, `secret_folder_created/removed`)과 서버 로그의 인증 방식 표기(`scram-sha-256`)뿐이다.

## 1. 파일 목록

보존 위치는 모두 이 작업 세션의 임시 폴더 아래다: `C:/Users/mjwmm/AppData/Local/Temp/claude/C--JV-Project-jp-vocab-reader/31735110-cd12-4705-a3fe-8f284e68018b/scratchpad/` (아래 표의 "폴더"는 이 경로 아래의 하위 폴더).

| 실행 | 실행 ID | 폴더 | 파일 | 용도 | 크기(바이트) | SHA-256 |
| --- | --- | --- | --- | --- | --- | --- |
| 1차 | 20261027T131459 | `pg65_evidence/` | `record.json` | 생성 기록·검사 결과 | 7065 | `b559ae3924f1e266d45e57abed1ba1e8b1521b945f2e1a02a11b81b63cc2b6a7` |
| 1차 | 20261027T131459 | `pg65_evidence/` | `target.json` | 대상 사실(PID·OID·nonce 등) | 6422 | `aa2267a9c13fb443a68485264ce19b1e886d18e98261cc1073799ec6372286cb` |
| 1차 | 20261027T131459 | `pg65_evidence/` | `server.log` | 서버 로그(연결·종료·오류) | 28835 | `e232e269ee0fd354d69622f570dfd62c52862fb5bf1bdbb6fe62d84ac0586f68` |
| 2차 | 20261027T141258 | `pg65_evidence_20261027T141258/` | `record.json` | 생성 기록·검사 결과(잠금·권한 변형 포함) | 13220 | `e5a1f7813709e6f6dfb5e911084f7a52e17d0c98647ef6aad7ec8808233b2533` |
| 2차 | 20261027T141258 | `pg65_evidence_20261027T141258/` | `target.json` | 대상 사실 | 6422 | `fe20ad7852f307784e5572b7c33d307e314705ff429de3b0b74317f708b74e0e` |
| 2차 | 20261027T141258 | `pg65_evidence_20261027T141258/` | `server.log` | 서버 로그 | 143571 | `edce1f50078ebc348800961d3d212f3032549648dbdef5571bce5504e878dfa5` |
| 보완 | 20261027T154352 | `pg65_evidence_20261027T154352/` | `record.json` | 생성 기록·검사 결과(d1 하위 사례·준비 연결 포함) | 9609 | `ad88e29f7e7e32764b6c4893c6013a0c206f17b15c75fc27b7100e3a8d8ff6c6` |
| 보완 | 20261027T154352 | `pg65_evidence_20261027T154352/` | `target.json` | 대상 사실 | 6422 | `4f575a2500fb99fa84380aac63c6348f20c7bd0b85c8c2fe2bd4c690dc21f4b6` |
| 보완 | 20261027T154352 | `pg65_evidence_20261027T154352/` | `server.log` | 서버 로그 | 40902 | `6eca8d4315d29939b0881fec8e3421b0f3cbb91d959be0025a7ca80f6ff8c4d5` |
| 시퀀스 S3 | 20261027T195331 | `pg65_evidence_20261027T195331/` | `record.json` | 생성 기록·검사 결과(권한 부여·회수 기록 포함) | 8786 | `9c0463456891be9d2440ef18dcaa131499c19e544ec021d5dac0daab48abd990` |
| 시퀀스 S3 | 20261027T195331 | `pg65_evidence_20261027T195331/` | `target.json` | 대상 사실 | 6421 | `80c2936f12fc2829a4ef76fb005d7c6ddb58272e7deadeb91b8ac432b167523a` |
| 시퀀스 S3 | 20261027T195331 | `pg65_evidence_20261027T195331/` | `server.log` | 서버 로그 | 45772 | `3fa229b8b48fcd7056098070a21e376852c2600cb4dff6d49551c27ad4a8b7d3` |

## 2. 대조 결과 (2026-10-27, 읽기 전용)

| 확인 | 1차 | 2차 | 보완 |
| --- | --- | --- | --- |
| 3개 파일 모두 있음 | 예 | 예 | 예 |
| 크기·해시가 REPORT 72·73·74절 기록과 같음(1·2차는 당시 앞 16자리) | 예 | 예 | 예 |
| `record.json` 실행 ID = 폴더 실행 ID = `target.json` 실행 ID | 예 | 예 | 예 |
| `target_written` 이벤트 1개, 그 SHA-256 = `target.json` 해시 | 예 | 예 | 예 |
| 서버 시작 PID 기록 1개 | 19340 | 10836 | 19924 |
| 검사 단계 기록 | 전체 21항목 | 전체 21항목 | `phase: supplement_d1`, 선택 a2·d1, 사후 확인 `d1_post`, "이전 21/21에 합산하지 않음" |
| 결과 기록 | G0 `fail`(`preparation_failure`), 21항목 기록 없음 | G0 `pass` + 21항목 모두 `pass` | G0·a2·d1·`d1_post` 모두 `pass` |
| 집계 | 실제 통과 0·미실행 21 | 실행기 기준 21/21 | 보완 2/2(G0·사후 확인 제외) |

- 빠진 파일·불일치 없음.
- 세 실행은 따로 집계한다. 21/21과 2/2를 합산하지 않으며, 1차의 G0 실패 기록은 그대로다.
- 2차 `record.json`의 d1 세부 결과에는 당시 판정 그대로 변조 사례가 `request_mismatch`로 남아 있고 계획 대상 사례는 없다(그때 d1 두 하위 경로 미검증, REPORT 73-1). 보완 실행 기록의 d1에는 네 하위 사례의 코드·호출 추적·거부 실행 연결 0·계획 준비 연결(`prep`)이 있다.


### 2-1. 시퀀스 USAGE 조정 S3 대조 (2026-10-27, 읽기 전용)

| 확인 | 시퀀스 S3(20261027T195331) |
| --- | --- |
| 3개 파일 모두 있음 | 예 |
| 크기·전체 SHA-256이 REPORT 78절 기록과 같음 | 예 |
| `record.json` 실행 ID = 폴더 실행 ID = `target.json` 실행 ID | 예 |
| `target_written` 이벤트 1개, 그 SHA-256 = `target.json` 해시 | 예 |
| 검사 단계 기록 | `phase: sequence_usage_recheck`, 선택 a1·a2·s1, 사후 확인 `seq_post`, "fixed partial run: not added to any earlier result" |
| 권한 변형 기록 | `c1_sequences` 적용(두 USAGE 부여) 1회, 원복(회수) 1회 |
| 결과 기록 | G0·a1·a2·s1·`seq_post` 모두 `pass` |
| 집계 | 3/3(a1·a2·s1, G0·사후 확인 제외). C12 21/21·보완 2/2와 합산하지 않음 |

- 빠진 파일·불일치 없음. 앞의 세 실행 폴더 9개 파일의 해시도 그대로다.

## 3. 실제로 확인한 범위 (요약)

- 정상 적용(2차 a1·a2·a3, 보완 a2): 계약 프로필로 두 역할 관측 통과, 개인·구독 카드 최초 적용, `blocked` 소개 기록, 다른 계정·범위 밖 행 불변.
- 권한(2차 b1·b2·b3): 계약 권한(`users` `SELECT(id)`·`UPDATE(updated_at)`)으로 잠금 문장 성공, `UPDATE(updated_at)` 회수 시 직접 잠금 탐침의 **서버 결과** `42501`과 CLI `observed_privileges_missing`, 초과 권한 3종 CLI `observed_privileges_excess`.
- 시퀀스(2차 c1): 두 실행 표 `id`가 BY DEFAULT identity. 두 시퀀스 USAGE를 회수한 상태에서 제품 `apply_plan` 직접 실행의 INSERT가 **성공**(관측 사실). 당시 계약 권한(`srs_migrate.WRITE_PRIVILEGES`)에는 두 시퀀스 USAGE가 **포함돼 있었고**, 당시 CLI가 회수 상태를 `observed_privileges_missing`(부족 권한)으로 거부한 것은 그 **옛 계약의 결과**다. 그 실행에서는 계약을 바꾸지 않았다. 이후 시퀀스 USAGE 조정(S1~S3)으로 두 USAGE는 계약에서 빠졌다(아래 시퀀스 S3 항목).
- 잠금·경합(2차 f1~f4): 같은 계정 경합에서 대기 상대 증명(**서버 결과** `pg_blocking_pids`, `transactionid`·`ShareLock` 대기)과 제품 잠금 아래 `migration_run_exists`, 다른 계정 같은 키의 **서버 결과** 고유 제약 오류, 거부된 실행에 귀속되는 변경 0, 오래된 계획 `plan_changed`.
- 판정 시각·부분 커밋(2차 e1~e3·g1·g2): 연결별 갱신 시각, 승인/근거 만료 구분, 배치 부분 처리, 카드 1 커밋 뒤 실제 권한 회수에 의한 다음 연결 거부.
- d1 정확한 거부 경로(보완): 다른 DB 승인 `preflight_db_identity_not_approved`, 변조 승인 `preflight_approval_signature_invalid`(실제 시험 OpenSSH 키 서명 검증), 다른 DB 계획 파일 `plan_file_target_mismatch`, 다른 계정 근거 `backup_evidence_account_mismatch`. 모두 **CLI 판정**(연결 전), 거부 실행의 두 역할 연결·인계·제품 호출 0.
- 구분: 승인·계획·근거 거부는 CLI 판정, 권한 오류·잠금 대기·고유 제약 오류는 서버 결과다. g3·g4는 시험 장치의 **주입** 검사이며 실제 장애 증거가 아니다.
- 시퀀스 USAGE 조정 S3(새 계약, 두 USAGE 없음): USAGE 없는 쓰기 역할로 실제 CLI·공급자·제품 경로의 정상 최초 적용(개인 3·구독 2, identity INSERT·snapshot 5·커서 끝·`completed`), 두 USAGE 부여 시 서버 관측에 따른 **공급자 판정** `observed_privileges_excess`(쓰기 연결 생성 1·인계 0·업무 문장 0, DB 불변), 회수 뒤 공급자 관측이 새 계약과 일치. 쓰기 역할의 두 USAGE 부재는 관리 연결 카탈로그 조회로도 확인.
- 옛 계약과 새 계약의 구분: C12 2차 c1(옛 계약, USAGE 포함)은 회수 상태를 부족 권한으로 거부했고 USAGE 없는 직접 실행이 성공함을 관측했다. 시퀀스 S3(새 계약, USAGE 제외)는 부여 상태를 초과 권한으로 거부한다. 두 결과는 서로 다른 계약 아래의 기록이며 하나로 합치지 않는다.

## 4. 제한과 미결

- C10 백업 근거는 시험 키로 서명한 합성 진술이며 `restore_verified`·`backup_artifact_checked`는 false다. 실제 백업·복원 검증이 아니다.
- 미검증·미구현 유지: 실제 커밋 응답 유실·OS·네트워크 장애, 재개·완료 재호출·상태 보정(미구현), 운영 신뢰 루트·실행 계정·운영 활성화. 시퀀스 권한은 PostgreSQL 18.6과 현재 최초 `apply` SQL 경로에서만 확인했고, 다른 PG 버전·다른 도구 경로로 일반화하지 않는다.
- **보존 미결**: 위 폴더는 세션 임시 폴더라 장기 보존 위치가 아니다. 장기 보존 위치와 보존 기간은 정해지지 않았다(사용자 결정 필요). 이 문서의 해시 목록은 지금 읽은 바이트를 적은 것일 뿐, 그것만으로 보존이나 진본성(누가 언제 만든 원본인지)을 보장하지 않는다.

## 5. 다음 최소 단위

- (완료) 시퀀스 USAGE 제거는 S1~S3로 마감했다(`OPS_APPLY_SEQUENCE_PRIVILEGE_PLAN.md` 8절). 이 문서의 1~4절은 그 결과까지 반영한다.

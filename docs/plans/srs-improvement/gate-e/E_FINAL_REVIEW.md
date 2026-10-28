# Gate E 마감 검토 (2026-10-21)

상태: **합성 검증 마감(기술 검토 완료 범위) · 운영 준비 미완료 · 운영 준비 로드맵 검토 대기.** 운영 준비 완료·릴리즈 승인·실제 사용자 이전·FSRS 기본 활성화가 아니다. 운영 공백과 순서는 `OPERATIONS_READINESS_PLAN.md`.
기준: 브랜치 `codex/fsrs-srs-replacement`, HEAD `e2c07f8`, 시작 시 미커밋 167개(보존). 스테이징·커밋·푸시·병합 없음.
마감 검토 단계에서는 제품 코드를 바꾸지 않았다. 마감 검토에서 바꾼 파일은 테스트 파일 3개(새 2, 수정 1)와 이 문서, `REPORT.md` 28절이다(7절). 그 뒤 F-1 보정에서 제품 파일 `backend/app/recovery.py` 하나와 테스트를 바꿨다(7-1절).

## 0. Gate E 상태 구분 (2026-10-21 문서 정리)

| 구분 | 범위 | 근거 |
| --- | --- | --- |
| 합성 검증 마감 | 2절 검사표의 "통과"·"조건부" 항목, 3절 통합 리허설(SQLite·로컬 PG), F-1 예방 보정(검토 완료) | 7절 실행 기록. 조건부 항목의 조건은 그대로 남는다 |
| 미검증 | 2절 "미검증" 항목(실제 HTTP·브라우저, E-4 단독 I6/I7), 3-3절, 다중 프로세스·운영 규모 | 실행 근거 없음 |
| 운영 준비 미완료 | 운영 대상 도구(5-3), 백업·복원, 계정 삭제 외부 절차(5-4), 운영 권한·실행 기록, 성능 기준, 업그레이드 운영 창 | `OPERATIONS_READINESS_PLAN.md` |
| 정책·운영 승인 대기 | 6절 | 승인으로 기록하지 않는다 |

## 1. 결론 요약

- 합성 자료 한 벌로 구 스키마 → 명시 전환 → 평가 → 최초 완료 → P-RB 복구 → completed 해제 → legacy 쓰기 재개까지 **SQLite와 실제 PG에서 통과**했다. 단계별 관측은 S1 이후 두 DB가 같다(DB 고유 차이 2건만 다름, 3-2).
- 형식 3 `restart.rollback_record_id` 정상·외부 참조 검사를 **상설 회귀 테스트**로 추가했고 두 DB에서 통과, 변형 4/4를 두 DB에서 검출했다.
- **결함 F-1(4절) — 예방 보정 검토 완료(2026-10-21)**: 해제 관문을 넘을 수 없는 계정이 B까지 진행돼 차단이 풀리지 않던 문제다. 사용자 결정(예방)에 따라 사전 확인·A·B가 관문 사전 조건(I1a·I2a·I4a·I5a·N·S)을 먼저 판정하도록 보정했고(`app/recovery.py`), Codex 검토를 마쳤다. 출시 차단 후보였던 "B 뒤 해제 불가" 경로는 새 복구에서는 A·B 전에 막힌다. **남는 것:** 보정 전에 B를 마친 정체 계정 구제(없음), N·S 관측 한계, 운영 미검증. 운영 적용 승인이 아니다.
- 운영 절차는 문서상 순서가 있으나 **운영 DB에 쓸 수 있는 도구는 P-RB CLI 하나뿐**이고, 명시 전환·모드 전환·정리 3종·계정 삭제·감사는 SQLite 파일 또는 로컬 테스트 PG 전용이다(5절).

## 2. 검사표 마감

분류: **통과**(이번 또는 기록된 실제 실행 근거) / **조건부**(통과했으나 조건·관측 한계가 붙음) / **미검증** / **정책·운영 승인 대기**.
근거 종류를 섞지 않는다: [S] SQLite, [P] 실제 로컬 PG 18.6, [R] 저장소 함수, [A] ASGI(TestClient·httpx), [H] 실제 HTTP 서버, [B] 브라우저.
"이번"은 2026-10-21 이 검토에서 실행한 것, 그 밖의 절 번호는 `REPORT.md`의 과거 실행이며 그 수치는 합산하지 않는다.

| ID | 분류 | 근거 | 남는 조건 |
| --- | --- | --- | --- |
| P-UP1 빈 DB init 2회 | 통과 | [S][P] 이번 PG 묶음, 13·14절 | - |
| P-UP2 구 스키마 업그레이드 | 통과 | [S][P][R] 이번 리허설 S1(기존 값 보존·재실행 무변화), 16-3 | 변경이 필요한 업그레이드는 강한 잠금·교착 2종(E-D13 A 범위 밖) → **운영 창 필요** |
| P-UP3 D-P1 FK 제거 | 통과 | [P] 11-4, 이번 PG 묶음 | 운영 카탈로그 미조회 |
| P-DEL1~3 카드 삭제·경합·재시도 | 통과 | [S][P][R][A] 11·16절, 이번 PG 묶음 | - |
| P-REV1 평가 원자성 | 통과 | [S][P][R] 16-4, 이번 PG 묶음 | - |
| P-REV2 재시도·응답 유실·만료 | 통과 | [S][P][A] 이번 리허설 S3(같은 바이트·쓰기 0·409), 17-6 | 실제 HTTP 미검증 |
| P-REV3 실제 경합 | 통과 | [P] 16-3 | 다중 서버·워커 미검증 |
| P-Q1 큐 / P-T1 서울 자정 | 통과 | [S][P][R][A] 16-6, 이번 PG 묶음 | - |
| P-M1 전환·중단·재개 | 통과 | [S][P][R] 이번 리허설 S2(중단 → 같은 키 재개 → 재실행 무쓰기) | 운영용 전환 CLI 없음(5-3) |
| P-M2 롤백·재전환·만료 정리 | 통과 | [S][P][R] 17-6, 이번 형식 3 테스트(실제 정리 도구로 형식 3 생성) | 정리 도구 운영 대상 불가(5-3) |
| P-M3 큰 수·손상 값 | 통과 | [S][P][R] 17-6 | - |
| P-C1 완료 판정 | 통과 | [S][P][R][A] 이번 리허설 S4(V3 최초 완료, 출처 `meaning-completion-v1`) | - |
| P-S1 U12 리허설 | 통과 | [S] U12, [P] 17-6 변형 | SQLite 식별 재구성 S1은 PG 해당 없음 |
| P-RB1 복구 순서 | 조건부 | [S][P][R][A] 이번 리허설 S5·S6, 24~27절 | N·S는 관측: PG에서 마지막 검사~커밋 사이 다른 계정 쓰기를 막지 않음. F-1 사전 차단 보정됨(I1a·I2a·I4a·I5a·N·S) |
| P-RB2 부분 실패·만료·차단 카드 | 조건부 | [S][P][R] B 실패 전체 롤백·snapshot 없는 카드 차단(이번 별도 사례) | 부분 복구 상태 처리·만료 계정 처리 **결정 대기** |
| 형식 3 `restart.rollback_record_id` | 통과 | [S][P] 이번 상설 테스트 2개, 변형 4/4 | 로그 공간으로 잘못 보는 변형은 id 값 겹침으로 미검출(4-3) |
| P-ACC1~3 계정 삭제·경합·지연 쓰기 | 조건부 | [S][P][R][A] E5B·E5C | 서버 DB 한정. 실제 HTTP 18사례·다중 프로세스 미검증 |
| P-ACC4 공유 덱 소유 계정 | 정책·운영 승인 대기 | 자동 삭제 보류만 확인 | 수동 처리 경로 없음 |
| E-4 I6/I7 단독 CLI | 미검증 | 통제된 삭제 리허설로만 비교 | 단독 실행은 `not_evaluated` |
| E-6 성능 | 조건부 | E6_REPORT 측정 | 병목은 후보일 뿐, 기준 수치 미정(E-D9) |
| 실제 HTTP 서버 [H]·브라우저 [B] | 미검증 | 이번 리허설은 ASGI | 프론트 미수정이라 빌드·브라우저 반복 안 함 |

## 3. 최종 합성 통합 리허설

파일: `backend/tests/test_e_final_rehearsal.py`(SQLite), `test_e_final_rehearsal_real.py`(실제 PG, 같은 단계).
앱 import 전에 `APP_ENV=test`와 세션 전용 `DATABASE_URL`을 지정했다. 시간은 앱 시계 하나(`now_utc`)로만 움직인다. 요청은 ASGI다.
계정 A가 전환·학습·복구 대상, B는 공유 덱 소유자(legacy)이며 계정 경계 대조군이다.

### 3-1. 단계와 결과 (두 DB 모두 통과)

| 단계 | 확인한 것 |
| --- | --- |
| S0 | 구 스키마(SRS 열·표 없음, 옛 CASCADE FK) + 합성 legacy 자료, 옛 앱의 최신 카드 하드 삭제 |
| S1 | 업그레이드, 재실행 시 카탈로그·행 무변화, 기존 값 보존. 삭제 id 재사용 방지(SQLite: `d2_card_identity --apply-rebuild` 별도 프로세스, PG: IDENTITY). 앱 삭제는 원장 1행, 다음 id는 더 큼 |
| S2 | dry run 무쓰기 → 1건 제한 적용 → 다음 배치 중 강제 실패(`failed`, 커서 보존) → 같은 키 재개(`completed`) → 같은 키 재실행 무쓰기(`already_applied`) |
| S3 | 개인 평가, 응답 유실 재시도 = 같은 바이트·쓰기 0, 오래된 버전 409 `card_version_conflict`, B의 요청 404, 구독 평가와 재시도 같은 바이트 |
| S4 | due 시각 평가 4회 뒤 V3 최초 완료(`first_completed_source`·`version_first_completed_version` = `meaning-completion-v1`) |
| S5 | preview `ready` → A(차단 active) → A의 평가·덱 쓰기 409 `account_writes_blocked`, B는 쓰기 가능, 정리 도구 3종 거부·쓰기 0 → 원자적 B(4개 카드 legacy) → 로그 id 목록·최초 평가일(신규 집계 근거)·완료 이력 불변 → verify `verified`(A·N·S 10개 pass) → completed 해제 |
| S6 | legacy 형식 평가 200(응답에 `srs` 없음), 덱 생성 200, 같은 해제 요청 재호출 `created False`·쓰기 문장 0 |
| S7 | 해제 뒤 정리 도구: 영수증 7개 만료 삭제(+10일 판정), snapshot 최소화 8개 이미 최소, 만료 정리 0건(기간 안) |
| 매 단계 | B의 계정 행 지문 불변(B 자신의 쓰기 뒤 기준 갱신), 추적 카드 4개 버전 비감소(최종 8·3·2·3), `GET /stats` 복구 전후 같음 |
| 별도 사례 | FSRS 모드에서 새로 만든 카드(snapshot 없음): preview가 `fsrs_card_without_snapshot`, A 거부, 차단 행 0 |

### 3-2. 두 DB 차이 (DB 고유, 불일치 아님)
- S0 로그 수 4 vs 3: PG는 옛 CASCADE FK가 하드 삭제 카드의 로그를 함께 지운다. SQLite는 FK pragma 없는 옛 설치처럼 로그가 남는다.
- S1 id 재사용 방지 수단: SQLite 재구성 도구 / PG IDENTITY.
- S1 이후 모든 단계의 관측 표(버전·엔진·출처·거부 코드·건수)는 같았다.

### 3-3. 리허설에서 검사하지 못한 것
- 만료 정리(prune)의 해제 뒤 실제 적용: 기간 안이라 대상 0건. 실행 자료가 없어 **미검증**(형식 3 테스트에서는 창 판정만 바꿔 실제 도구 경로로 적용했다).
- 해제 ↔ snapshot 최소화·만료 정리의 양쪽 순서 경합: 테스트 없음(영수증 정리 ↔ 해제만 기존 테스트 있음). **미검증**.
- 실제 HTTP·다중 워커·운영 규모 자료.

## 4. 결함과 관측

### F-1 (Gate E 마감에서 발견 → 2026-10-21 예방 보정 검토 완료) 해제 관문을 못 넘는 계정이 B까지 진행됨

**근거 구분**
- Claude 실행: SQLite·실제 로컬 PG 결과(아래 검증, 7-1·7-2절).
- Codex 독립 재실행: 관련 SQLite 검사 10개 통과(사용자 보고, 2026-10-21). 이 문서 작성자가 다시 돌리지 않았고, 개별 검사 이름은 이 문서에 기록하지 않았다. PG 재실행은 포함되지 않았다.
- 두 결과를 합산하지 않는다. 운영 DB·실제 사용자 자료에서는 확인하지 않았다.
- 원인: 해제 관문 A의 I1a(대상 고아 로그)가 **복구 전부터 fail**인데, 사전 확인(`assess`)은 이 관문을 보지 않았다. 그래서 preview `ready` → A·B 성공 → verify 영구 실패 → `completed`·`precheck_unrecoverable` 모두 거부, 차단이 남았다.
- 발생 경로: SQLite 구 설치(FK pragma 없음)에서 옛 앱이 카드를 하드 삭제하고 로그를 남긴 경우(원장 없음). 옛 PG는 CASCADE FK라 이 경로로는 생기지 않는다(운영 자료 미조회, 추정). 현재 스키마는 두 DB 모두 `review_logs`에 카드 FK가 없어, 앱 밖 삭제로 같은 상태가 생길 수 있다.
- 처리 방향(사용자 결정): **예방**. 고아 로그 삭제·원장 추정 생성·강제 해제 사유 추가는 하지 않았다.

**사전 조건 (B가 고치지 않고 복구 전부터 판정 가능한 관문 검사)** — `recovery.PRECONDITION_CHECKS`, 판정은 verify와 같은 `recovery_scope.account`·`inflow`·`sequence` 결과를 그대로 쓴다. `pass`가 아니면(fail·unknown·not_evaluated) 진행하지 않는다.

| 후보 | 입력 | B가 바꾸는가 | 사전 검사 | 거부 사유 |
| --- | --- | --- | --- | --- |
| I1a | 대상 개인 로그·카드·삭제 원장, 차단·진행 기록 일관성, 대상 snapshot의 실행 소속 | 아니오(로그·원장 무변경, B의 새 기록은 대상 실행 소속) | 포함 | `gate_precondition_I1a` |
| I2a | 대상 로그의 카드 소유, 구독 로그의 진도 행 | 아니오(진도 행 생성·삭제 없음) | 포함 | `gate_precondition_I2a` |
| I4a | 카드 id·생성 시각, 원장, 로그·영수증·snapshot 시각, 식별 표시 | 아니오 | 포함 | `gate_precondition_I4a` |
| N | 다른 계정 행의 대상 참조 | 아니오(다른 계정 무변경) | 포함 | `gate_precondition_N` |
| I5a | 카드 `evidence_from_log_id`, 영수증 `review_log_id`, snapshot·재시작의 로그 참조 | 아니오. `evidence_from_log_id`는 `migration.ROLLBACK_PRESERVED`라 B가 그대로 보존하고, B는 rollback 실행·snapshot만 추가한다(영수증·카드 생성 없음) | 포함(추가 보정) | `gate_precondition_I5a` |
| S | 전역 개인 카드 id sequence ≥ 모든 보존 참조 | 아니오. B의 snapshot 삽입은 snapshot 표의 id만 쓰고, 카드를 만들지 않아 개인 카드 id sequence는 움직이지 않는다 | 포함(추가 보정) | `gate_precondition_S` |
| I6/I7_recovery, completion_history, recovery_result, FSRS 0, legacy 모드 | 기준선·결과 | 사후 조건 | 제외 | - |

**동작**
- preview: 실패하면 `blocked`와 위 고정 사유. 정상 계정의 plan 지문은 그대로다(사유 없음).
- A: 계정 잠금 아래 `assess`에서 다시 판정, 거부 시 이번에 만든 차단·진행 기록이 트랜잭션과 함께 롤백. 원래 있던 차단은 그대로.
- B: 잠금 아래 첫 진행 표시(`changes_started`)·복구 쓰기 전에 `assess`에서 다시 판정. 거부 시 `prepared`·차단 유지, 쓰기 문장 0, `precheck_unrecoverable` 무변경 해제 가능.
- 로그·분류·예약·완료 이력·원장·snapshot은 고치거나 지우지 않는다. 다른 계정의 무관한 고아 로그는 진단 G(I1)만 fail이고 차단하지 않는다.

**검증** (`test_p_rb_recovery.py` F-1 6개, 두 DB 공용 / `test_e_final_rehearsal.py` 옛 설치 경로 1개, SQLite)
- 처음부터 고아: preview blocked, A 거부. A가 차단 INSERT 문장을 실행하지만 커밋된 변화 0(자료·차단·기록 지문 동일).
- preview 뒤 A 전 발생: A 거부, 커밋된 변화 0. 기존 차단이 있던 경우 그 차단 그대로.
- A 뒤 B 전 발생: B 거부, 쓰기 문장 0, `changes_started` 0, rollback 실행 0, 무변경 해제 성공.
- 진도 행 누락: `gate_precondition_I2a`로 차단.
- 정상: 원장으로 증명된 삭제 + 다른 계정 고아 로그 → ready → A → B → verify(G I1 fail) → completed 해제.
- 판정 일치: 사전 조건 값 = 같은 시점의 `account`·`inflow`·`sequence` 결과, 대상은 A 관문의 I1a·I2a·I4a·I5a와 N·S 전부.
- PG: 옛 설치 경로는 CASCADE로 재현 불가(건너뜀, 사유 기록). 현재 판정은 최신 합성 PG에서 앱 밖 행 삭제로 같은 고아 상태를 만들어 검사(FK 비활성화 없음, 현재 스키마에 카드 FK 없음).
- 변형(사전 검사 제거): SQLite 5개 검사 중 6실패, PG 4개 검사 중 5실패. I1a만 뺀 변형 5실패, I2a만 뺀 변형 1실패(SQLite).

**추가 보정: I5a·S 사전 차단 (2026-10-21)**
- 수정 전 재현(정상 회귀 테스트로 먼저 추가, `expectedFailure` 아님): 영수증 `review_log_id` 손상, 카드 `evidence_from_log_id` 손상, 개인 카드 sequence < 최대 보존 참조. 세 경우 모두 preview `ready` → B `applied` → verify `not_verified`(I5a 또는 S fail) → `completed`·`precheck_unrecoverable` 둘 다 `release_not_allowed`, 손상 값은 B 뒤에도 그대로였다. 새 테스트 하위 사례 12개 실패.
- 보정: 위 표대로 `PRECONDITION_CHECKS`에 I5a·S 추가. 해제 판정과 N·S의 관측 한계는 바꾸지 않았다.
- 검증(`test_p_rb_recovery.py` F-1b 4개, 두 DB 공용): 세 손상 × 처음부터 / preview 뒤 A 전(기존 차단 있음·없음) / A 뒤 B 전. 거부 시 손상 원자료 보존, 새 차단·기록 커밋 0, B 쓰기 문장 0, 무변경 해제 성공. 정상 참조·sequence 경계(최대 참조와 같음)·원장으로 증명된 삭제는 끝까지 복구·해제된다.
- PG sequence 손상은 장치가 소유한 합성 `vocab_items` sequence에만 `setval`(비트랜잭션)로 했고, 사례마다 장치의 identity 재시작으로 되돌렸다. 다른 객체는 건드리지 않았다.
- 변형: I5a 제외 → 영수증·증거 사례 8실패(SQLite·PG 같음), S 제외 → sequence 사례 4실패(SQLite·PG 같음).

**남는 제한**
- 이미 B를 마친 정체 계정의 구제는 범위 밖(새 해제 정책 없음).
- (정정) 첫 보정 때 "B가 카드 증거 참조를 복원한다"·"S는 B의 삽입과 얽힌다"고 적고 I5a·S를 뺐으나 틀렸다. 실제로는 둘 다 B가 고치지 않아 같은 정체가 재현됐고(추가 보정 절), 지금은 사전 조건이다.
- S는 전역 검사라 다른 계정 자료로 sequence가 뒤처져도 모든 계정의 복구가 사전 단계에서 막힌다(해제 관문과 같은 범위). sequence는 자동으로 고치지 않는다.
- N은 판정 시점의 관측이다. A~B, B~해제 사이 다른 계정 쓰기는 막지 않는다(기존 조건).
- 사전 조건 계산은 preview·A·B·재개 판정마다 계정 전체 검사를 한 번 더 한다. 대량 계정 성능은 측정하지 않았다.

### 관측(기존 조건, 재설계하지 않음)
- 4-1 N·S: 마지막 검사와 해제 커밋 사이 다른 계정 쓰기를 PG에서 막지 않는다(전역 잠금 미구현·미승인).
- 4-2 `prepare`가 거부될 때도 차단 행 INSERT 문장을 먼저 보낸 뒤 트랜잭션 전체를 롤백한다. 커밋된 쓰기는 0이다(별도 사례에서 계정 행 지문 불변 확인). "쓰기 문장 0"이 아니라 "커밋 0"이다.
- 4-3 형식 3 테스트는 `rollback_record_id`를 로그 공간으로 보는 옛 동작 변형을 검출하지 못한다. 합성 자료에서 snapshot id와 로그 id 값이 겹치기 때문이다. 공간 구분 자체는 27-3의 기존 테스트 범위다.
- 4-4 E-D13 A: 변경이 필요한 업그레이드 DDL은 강한 잠금을 잡고 알려진 교착 2종이 있다. 마감 검토 PG 묶음(7절, F-1 보정 전 실행)의 예상 실패 1이 이것이다. 운영 창이 필요하다.

## 5. 운영 절차 정적 점검 (DB 미접속, 문서 ↔ 실제 CLI)

### 5-1. 순서와 실제 도구

| 순서 | 문서(EXECUTION_PLAN 4·P_RB_PLAN·P_RB_TOOL_CONTRACT) | 실제 도구 | 상태 |
| --- | --- | --- | --- |
| 사전 백업 | 4-1-3: Neon 분기·시점 복구 또는 `pg_dump`, 빈 DB 복원 확인 | 없음 | **미작성**(방법·담당·복원 확인 절차) |
| 적용 대상 확인 | 승인된 계정 id 목록만 | 없음(목록 형식·승인 기록 미정) | 결정 대기 |
| 사전 검사 | 4-2: FK 목록, `started` 실행 0, I3~I5, 손상 값 dry run | `srs_invariant_audit.py`, d2 도구 dry run | **SQLite 파일·로컬 테스트 PG 전용** |
| 스키마 업그레이드 | 4-3-1 `init_db` | 앱 시작 | 교착 위험 → 운영 창 |
| 명시 전환 | 4-3-3 계정별 dry run → 적용 → 사후 검사 | **CLI 없음**(`migration.apply_plan`는 코드 호출만, `inspect_srs_migration.py`는 합성 SQLite 읽기 전용) | 운영 경로 없음 |
| 모드 전환 | 4-3-4 계정별 `srs_user_settings` | **제품·CLI 경로 없음**(운영 SQL만, 복구 B의 모드 CAS 제외) | 운영 경로 없음 |
| 차단 | P-RB A | `prb_recover.py prepare` | 앱 `DATABASE_URL` 대상(유일한 운영 대상 가능 도구) |
| dry-run | P-RB preview | `prb_recover.py preview` | 읽기 전용 |
| 적용 | P-RB B | `prb_recover.py recover` | 한 트랜잭션 |
| 사후 확인 | verify | `prb_recover.py verify` | A·N·S 관문 + G 진단 |
| 실패 복구 | B 실패 = 전체 롤백, A 차단 유지, `status`로 재개 판정 | `prb_recover.py status` | 부분 복구 처리 결정 대기 |
| 해제 | completed만(증명 필요) | `prb_recover.py release` | F-1 상태는 이제 A 전에 차단. 보정 전에 B를 마친 계정은 여전히 해제 불가 |

`prb_recover.py`는 대상 지정 인자가 없고 앱의 `DATABASE_URL`·`assert_safe_database_url`만 따른다(`APP_ENV=production`이면 Neon 허용). 허가 토큰의 발급·보관·폐기 절차는 문서에 없다.

### 5-2. 보존 기간과 카드 처리
- 영수증 7일: `d2_receipt_minimize.py --purge-expired`(+`--apply --confirm-user-id`). 판정 시각은 실행 시각이며 자동 실행 없음. 운영 대상 불가.
- 롤백 30일: apply 최초 `started_at` 기준, 정각 만료. 만료 뒤 롤백 거부(`rollback_window_closed`), 확인 불가는 `rollback_window_unverifiable`(추정하지 않음). 만료 정리는 `d2_snapshot_prune.py`(형식 3), 미사용 B안 허가는 보호. 운영 대상 불가.
- 만료·확인 불가·snapshot 없는 카드: preview가 차단 사유로 보고, A를 시작하지 않음(이번 별도 사례로 snapshot 없는 카드 확인). 그 계정의 FSRS 유지·해제 여부는 **결정 대기**(P_RB_PLAN 3절).
- 7일·30일은 제품 계약값이며 법정 보존기간이 아니다(E5_LEGAL_REVIEW).

### 5-3. 로컬 검증 전용과 운영 가능 구분

| 도구 | 대상 | 운영 사용 |
| --- | --- | --- |
| `prb_recover.py` | 앱 `DATABASE_URL` | 기술적으로 가능, **운영 실행 미승인** |
| `delete_account.py` | `--sqlite-db` 또는 `--local-test-postgres` | 불가(운영 대상 인자 없음) |
| `d2_receipt_minimize.py`·`d2_snapshot_minimize.py`·`d2_snapshot_prune.py` | 같음 | 불가 |
| `srs_invariant_audit.py` | 같음, 읽기 전용 | 불가. 단독 실행 I6/I7 `not_evaluated` |
| `d2_card_identity.py` | SQLite 파일만 | PG 해당 없음 |
| `inspect_srs_migration.py` | 합성 SQLite(`qa_srs_b2_*`)만 | 불가 |

비밀값 없는 명령 예시(로컬 합성 검증 형식일 뿐, 운영 실행 가능하다는 뜻이 아니다):
```text
python scripts/prb_recover.py preview --user-id <id> --recovery-key <key>
python scripts/prb_recover.py prepare --user-id <id> --recovery-key <key> --plan <64 hex>   # 계정 id 재입력·토큰 숨김 입력
python scripts/prb_recover.py status  --user-id <id> --recovery-key <key>
python scripts/d2_receipt_minimize.py --sqlite-db <합성.db> --user-id <id>                    # 기본은 읽기 전용 보고
python scripts/delete_account.py --sqlite-db <합성.db> --user-id <id>                         # 기본은 preview
```

### 5-4. 계정 삭제 절차의 미완료 상태
도구(E-5b)와 지연 쓰기 차단(E-5c)은 서버 DB 한정으로 합성 검증했다. 다음은 **없거나 미정**이다.
- 외부 삭제 요청 접수 창구, 본인 확인(도구의 계정 id 재입력은 본인 확인이 아님)
- 처리 결과·이의 통지(시행령 10일 기준 검토 필요)
- 앱 피드백·법정 보존 자료 분리 여부 검토(현재 앱 피드백이 있으면 자동 삭제 보류)
- 공유 덱 소유 계정의 수동 처리 경로(현재 자동 삭제 보류만)
- 백업·복제·분기·복원 뒤 재삭제와 파기 확인 절차(도구는 `server_db_only`)
- 운영 실행 승인과 실행 기록 방식

## 6. 운영 전 승인 항목 (모두 미승인, 승인으로 기록하지 않음)
- 보정 전에 B를 마친 정체 계정이 운영에 있는지 확인(운영 자료 미조회)과, 있다면 그 처리(새 해제 정책 없음, 결정 대기)
- E-D3 공유 덱 소유 계정, E-D5 피드백·법정 보존, E-D6 외부 창구·본인 확인·통지(보완안은 방향만, 세부·운영 미승인), E-D7, E-D9 성능 기준, E-D10 운영 전환 절차, E-D12 중 P-RB 항목 밖, E-D13 B/C
- 부분 복구 상태 처리, 만료·확인 불가 카드 계정 처리, 읽기 화면 차단 안내, P-ACC1~4 운영 처리
- 자동·강제 해제, 전역 잠금, 운영 백업 방법, 전환 대상 계정 목록, 운영 전환·복구·삭제 실행, 기본 FSRS 활성화

## 7. 이번 실행 근거

변경 파일:
- 새 `backend/tests/test_e_final_rehearsal.py`, `backend/tests/test_e_final_rehearsal_real.py`
- 수정 `backend/tests/test_p_rb_recovery.py`(형식 3 상설 테스트 2개와 보조 함수 추가, 기존 테스트 불변)
- 새 이 문서, `REPORT.md` 28절 추가

| 검사 | 근거 종류 | 결과 |
| --- | --- | --- |
| 형식 3 상설 테스트 2개 | [S][P] | 각 DB 2/2 통과. 변형 4종(A 검사 생략, N 검사 생략, 카드 대조 생략, rollback 종류 대조 생략) SQLite 4/4·PG 4/4 검출 |
| 통합 리허설 + 별도 사례 | [S][P][R][A] | (F-1 보정 전 기록) SQLite 2 통과 + 예상 실패 1(F-1), PG 2 통과 + 건너뜀 1(F-1 SQLite 전용). 보정 뒤 결과는 7-1 |
| 백엔드 전체(PG opt-in 해제) | [S] | (F-1 보정 전 기록) 1330 실행: 1100 통과, 건너뜀 229(PG 전용·opt-in 없음), 예상 실패 1(F-1). 약 304초 |
| 기존 회귀 스크립트 9종 | [S] | 모두 rc=0(DB 보호, PG boolean 호환, lexeme 로그·SRS 상태·통계, 공유 덱 공개 저장·SRS·저장, JLPT 패키지 안전). 전용 임시 폴더 사용 후 제거 |
| 실제 PG 묶음 | [P] | `test_*_real.py` 16개 모듈 + `test_postgres_cursor`·`test_srs_e2c_connection`: 214 실행, 210 통과, 건너뜀 3(F-1 SQLite 전용 1, 트리거·뷰는 E-1 장치가 함수·뷰 생성을 거부해 미실행 2), 예상 실패 1(업그레이드 교착 알려진 위험). 약 18분. 제외: `_srs_pg_suite.py`(기존 SQLite 모듈의 PG 대체 실행, E-2b·E-2c 근거만 있고 이번 미실행), `e6_read_benchmark`(성능 측정, 마감 범위 밖) |
| 프론트 테스트·타입 검사 | - | 159/159, typecheck rc=0 |
| diff 검사·스테이징 | - | `git diff --check` rc=0, 스테이징 0, 새·수정 테스트 파일 뒤 공백·탭 0 |
| 빌드·브라우저 | - | 프론트 미수정이라 실행하지 않음 |

정리: 이번에 시작한 PG(PID 9940, `C:/JV_Tools/pgsql-18.6/pgsql/bin/postgres.exe`, 자료 `C:/JV_Tools/pgdata-e2`)만 소유 관계·함수 0, 다른 접속 0을 확인하고 `pg_ctl stop`으로 껐다. 55432 리스너 없음. 변형 검사용 복사본·탐색 스크립트·회귀 임시 DB(작업 임시 폴더)는 삭제했다. 설치·자료 폴더, `fsrs_dist`, 기존 임시 폴더 19개, 다른 도구의 변경은 그대로다.

### 7-1. F-1 사전 차단 보정 (2026-10-21)

변경 파일:
- 제품 `backend/app/recovery.py`: `PRECONDITION_CHECKS`·`gate_preconditions` 추가, `assess`가 실패한 사전 조건을 `gate_precondition_<검사>` 사유로 추가(다른 경로 무변경)
- 테스트 `backend/tests/test_p_rb_recovery.py`(F-1 6개와 보조 함수), `test_e_final_rehearsal.py`(`expectedFailure` → 정상 검사), `test_e_final_rehearsal_real.py`(설명만)

| 검사 | 근거 종류 | 결과 |
| --- | --- | --- |
| 수정 전 재현 | [S] | 옛 설치 재현 테스트 실패(`'ready' == 'ready'`) |
| F-1 집중 + 복구·차단·계정 쓰기·삭제·감사 회귀 | [S][R][A] | 312 실행, 312 통과 |
| 복구·차단 실제 PG 묶음 | [P][R] | 109 실행, 107 통과, 건너뜀 2(트리거·뷰: E-1 장치가 함수·뷰 생성 거부) |
| 통합 리허설 | [S] / [P] | SQLite 3/3 통과 / PG 2 통과·건너뜀 1(옛 설치 경로 SQLite 전용) |
| 변형(사전 검사 제거) | [S] / [P] | 6실패 / 5실패, 그 밖에 I1a 제외 5실패·I2a 제외 1실패(SQLite) |
| 백엔드 전체(PG opt-in 해제) | [S] | 1342 실행: 1107 통과, 건너뜀 235(PG 전용·opt-in 없음), 예상 실패 0. 약 304초 |
| 프론트·빌드 | - | 프론트 미수정, 지시대로 다시 실행하지 않음 |

이번에 켠 PG(PID 67492, 같은 실행 파일·자료 경로)만 소유 관계·함수 0, 다른 접속 0 확인 뒤 종료, 55432 리스너 없음. 변형용 복사본은 작업 임시 폴더에서 지웠다.

### 7-2. F-1 추가 보정: I5a·S 사전 차단 (2026-10-21)

변경 파일:
- 제품 `backend/app/recovery.py`: `PRECONDITION_CHECKS`에 I5a·S 추가, `gate_preconditions`가 기존 `recovery_scope.sequence` 결과를 함께 반환, 설명 주석 정정
- 테스트 `backend/tests/test_p_rb_recovery.py`: F-1b 4개와 손상 보조 함수, 판정 일치 테스트를 6개 검사 전체로 확장(기존 기대값 완화 없음)

| 검사 | 근거 종류 | 결과 |
| --- | --- | --- |
| 수정 전 재현 | [S] | 새 테스트 하위 사례 12개 실패. 세 손상 모두 B applied → 해제 불가, 손상 값 유지 |
| 복구·차단·통합 리허설 | [S][R][A] | 127 실행, 127 통과 |
| 계정 삭제·쓰기 경계·감사 회귀 | [S][R][A] | 192 실행, 192 통과 |
| 복구·차단 실제 PG 묶음 | [P][R] | 113 실행, 111 통과, 건너뜀 2(트리거·뷰: E-1 장치가 함수·뷰 생성 거부) |
| 변형 | [S] / [P] | I5a 제외: 영수증·증거 8실패 / 8실패. S 제외: sequence 4실패 / 4실패 |
| 백엔드 전체·프론트·빌드 | - | 지시대로 이번 보정에서 반복하지 않음(직전 전체 1342는 이 보정 전) |

이번에 켠 PG(PID 118712, 같은 실행 파일·자료 경로)만 소유 관계·함수 0, 다른 접속 0 확인 뒤 종료, 55432 리스너 없음. 변형용 복사본과 탐색 스크립트는 작업 임시 폴더에서 지웠다.

## 8. 다음 작업 순서

운영 준비 순서와 완료 기준은 `OPERATIONS_READINESS_PLAN.md`로 옮겼다. 첫 단위는 운영 도구 안전 계약의 **설계**다(구현·DB 연결·권한 부여 없음).

운영 준비 로드맵 검토 대기.

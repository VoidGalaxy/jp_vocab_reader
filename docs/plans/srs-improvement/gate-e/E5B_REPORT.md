# E-5b 운영자용 계정 삭제 도구 결과

2026-10-19 · `codex/fsrs-srs-replacement` · HEAD `e2c07f8` · 검토 대기.

계약은 구현 전에 `E5B_CONTRACT.md`로 고정했다. 근거는 승인된 법률 보완안(APPROVAL_REQUEST 1절, `E5_LEGAL_REVIEW_KR.md`)과 E-5a 쓰기 경계(`E5A_CONTRACT.md`·`E5A_REPORT.md`)다. E-5a 테스트 fixture의 `erase_all_for_test`는 제품 절차로 복사하지 않았다.

이번에 하지 않은 것:
- 실제 계정 삭제, 운영·Neon·기존 `vocab.db` 접속
- 기본 FSRS 활성화
- 스테이징·커밋·푸시·병합

## 1. 변경 파일

| 파일 | 내용 |
| --- | --- |
| 새 `backend/app/account_deletion.py` | 미리보기·적용 함수. 앱 라우트에 연결하지 않았다 |
| 새 `backend/scripts/delete_account.py` | 운영자 CLI. `--sqlite-db` 또는 `--local-test-postgres`(E-2c 대상, 표식 nonce·OID 확인 포함) 중 하나 |
| 새 `backend/tests/_e5b_fixture.py` | 앱 저장소·SRS 경로로 만든 합성 계정 |
| 새 `backend/tests/test_e5b_account_deletion.py` | SQLite 25개 |
| 새 `backend/tests/test_e5b_account_deletion_real.py` | 실제 PG 5개 |
| 새 `docs/.../gate-e/E5B_CONTRACT.md`, 이 보고서, REPORT 22절 | 문서 |

기존 제품 파일·스키마·API·프론트는 바꾸지 않았다. E-5b 시작 뒤 수정 시각이 바뀐 파일은 위 6개뿐이다.

## 2. 동작

- **기본은 미리보기**다. 하나의 읽기 전용 snapshot에서 표별 건수, 고정 차단 사유, 계획 지문(대상 행 id 집합의 sha256)을 낸다. 쓰기는 없다.
- **적용에 필요한 것**: `--apply`, 같은 값의 `--confirm-user-id`, 미리보기의 지문 `--expect-plan`. 계정 번호 재입력은 실행 실수 방지일 뿐, 요청자 본인 확인이 아니다.
- **적용 절차**:
  1. 같은 저장 연결에서 E-5a 공용 잠금 `begin_account_write`를 잡는다(SQLite BEGIN IMMEDIATE, PG users 행 FOR UPDATE).
  2. PG는 대상의 덱·카드 행도 FOR UPDATE로 잠근다. 다른 계정이 새 참조를 만들지 못하게 하기 위해서다.
  3. 잠금 뒤 계획을 다시 계산한다. 차단 사유가 있거나 지문이 다르면 쓰기 없이 끝낸다.
- **삭제 순서**(명시 문장, 대상 행만 고른다):
  1. srs_evidence_restarts
  2. srs_migration_snapshots
  3. srs_migration_runs(scope 소유 확인된 id)
  4. srs_review_receipts·srs_card_deletions·srs_card_identity_flags·srs_user_settings
  5. review_logs·lexeme_review_logs
  6. user_word_progress·user_deck_subscriptions·shared_deck_imports
  7. meaning_feedback
  8. vocab_items·custom_terms
  9. decks
  10. users
- **삭제 뒤 검사**:
  - 각 문장의 삭제 행 수가 계획과 다르면 실패한다.
  - 커밋 전 같은 transaction에서 잔존 검사를 한다: 대상 행·대상 실행·삭제된 실행의 기록 0, 소유 공유 덱 0. SQLite는 공유·전역 표 건수도 같은지 본다.
  - 실패하면 전체 롤백한다.
  - CASCADE·SET NULL로 범위를 정하지 않는다. 일반 카드 삭제의 원장·내용 최소화·7일/30일 정리는 쓰지 않는다.
- **명시 허용 목록**:
  - 표 24개
  - 대상 표의 `user_id`·키 열
  - 실제 FK(SQLite 6개, PG 30개, 삭제 동작 포함). 실제 카탈로그에서 읽어 확인했다.
  - 사용자 트리거 0
  - 다르면 `schema_unverified`로 막는다.
- **출력**:
  - 들어가는 것: 상태, 표별 건수, 고정 사유, 지문, `server_db_only: true`
  - 들어가지 않는 것: 이메일·단어·뜻·예문·JSON 본문·토큰·연결 문자열·원시 오류
  - 종료 코드: 0 preview·deleted, 1 failed, 2 인자·대상 거부, 3 blocked, 4 account_not_found, 5 plan_changed

## 3. 적용 차단 조건

| 사유 | 조건 |
| --- | --- |
| `shared_deck_owner_review` | 공유 덱을 하나라도 소유(공개·비공개, 구독자 유무 무관). 자동 삭제만 중단하고 별도 검토 대상으로 보고한다. 거절도 완료도 아니다 |
| `app_feedback_retention_review` | 앱 피드백이 있다. 거래 불만·분쟁 기록 해당 여부를 코드로 추정하지 않는다 |
| `migration_run_in_progress` | 대상의 started 실행이 있다 |
| `run_ownership_unverifiable` | 어떤 실행이든 scope 소유를 읽을 수 없다(손상 JSON, 중복 키, 소유 없음, 잘못된 타입·범위) |
| `cross_account_reference` | snapshot·재시작·덱·가져오기·발행 원본·카드 id·로그 참조에서 다른 계정 자료와 섞였다 |
| `schema_unverified` | 표·열·FK·트리거가 허용 목록과 다르다 |

- `account_not_found`·`plan_changed`도 쓰기 0으로 끝난다.
- **결정이 필요한 점**: 앱 피드백을 차단으로 둔 것은 "확인 불가 자료는 막는다"는 지시에 따른 기본값이다. 앱 피드백이 있는 계정은 보존 판단이 정해질 때까지 이 도구로 지울 수 없다. 뜻 피드백(사전 뜻 수정 제안)은 삭제 대상으로 다룬다.

## 4. 검증

### SQLite (합성, `backend/jp_vocab_e5b_*` 세션 파일): 25개 통과

**미리보기·적용·재실행**
- 미리보기 전후 파일 바이트가 같고, 출력에 내용이 없다.
- 대상 계정의 모든 표(공유 덱 제외 16개 + 실행 + users)에 행이 있는 상태에서 적용했다.
  - 대상 행은 0이 됐다.
  - 다른 계정·dev 계정·전역 행은 전부 동일했다.
  - 공유·전역 자료는 무변경이었다.
- 재실행과 삭제 뒤 미리보기는 `account_not_found`이고 파일 바이트가 같다.
- 미리보기 뒤 카드가 추가되면 `plan_changed`이고 쓰기 0이다. 새 미리보기로 적용하면 삭제된다.

**입력 검사**
- 확인 계정 불일치, 잘못된 지문(빈 값·63자·None), 잘못된 id(0·음수·bool·2^63·문자열)를 모두 거부한다.

**차단**
- 공유 덱: 공개, 공개+구독자, 비공개, 비공개+구독자
- 앱 피드백, started 실행
- 실행 소유 손상 5종
- 섞임 6종: 다른 계정 카드가 대상 덱에 있음, 다른 계정 snapshot이 대상 실행에 있음, 재시작의 원 snapshot 불일치, 다른 계정 뜻 피드백이 대상 카드를 가리킴, 다른 계정 로그가 대상 카드를 가리킴, 대상 영수증이 다른 계정 로그를 가리킴
- 스키마: 추가 표, 트리거
- 모두 쓰기 0이다.

**실패**
- 삭제 17단계 각각에 실패를 주입했다. 잔존 검사 실패, 삭제 수 불일치, commit 실패도 주입했다.
- 모두 `failed`이고 전체 롤백됐다(파일 바이트 동일).

**실제 CLI(하위 프로세스)**
- 미리보기가 끝나도 파일 바이트가 그대로다.
- 다음은 모두 종료 코드 2로 거부한다: `--apply`만 준 경우, 지문 없음, 다른 계정 확인.
- 오래된 지문은 5, 적용은 0, 재실행은 4다.
- 공유 덱 소유 계정은 3이다.
- 출력에 내용 문자열이 없다.

**경합 5종 × 두 순서**(실제 별도 연결·스레드; 첫 작업이 BEGIN IMMEDIATE를 쥐고, 둘째가 요청한 뒤 0.3초 동안 끝나지 않음을 확인)
- 대상 작업: 평가, 단어 생성, 구독, 발행, 이전 적용
- 삭제 먼저: 둘째 작업은 `account_not_found`(404)이고, 대상 잔존 0, 다른 계정 불변이다.
- 쓰기 먼저:
  - 평가·단어 생성·구독은 `plan_changed`다. 쓰기는 유지되고, 새 미리보기로 삭제된다.
  - 발행은 공유 덱 소유가 되어 `blocked`다.
  - 이전 적용은 실행이 여러 transaction이라 `blocked`(started 실행) 또는 `plan_changed`다. 둘 다 쓰기 0이다.

**변형 검사**: 메모리 변형 4종(삭제 순서에서 표 하나 제거, 섞임 검사 제거, 공유 덱 차단 제거, 스키마 검사 무력화)을 해당 테스트가 모두 잡았다. 파일은 변형하지 않았다.

### 실제 PG (보호된 로컬 18.6, E-1 표식·OID·소유 목록, 제한 역할): 5개 통과

- 미리보기 무변경: 모든 소유 표의 ctid·xmin·값 지문이 같다.
- 오래된 계획은 `plan_changed`이고 무변경이다.
- 적용 결과: 대상 0, 다른 계정·전역 불변. 재실행 `account_not_found`, 무변경.
- 차단 7종은 쓰기 0이다: 공유 덱 3상태, 앱 피드백, started 실행, 섞임 2종.
- 삭제 17단계 실패와 commit 실패는 모두 전체 롤백됐다.
- 경합 5종 × 두 순서 모두에서, 둘째 작업의 backend가 첫 작업 backend를 기다린 것을 `pg_locks`·`pg_blocking_pids`로 증명했다(transactionid ShareLock). 결과 판정은 SQLite와 같다. 이번 실행에서 이전 적용 먼저는 `blocked`(started 실행)였다.
- 실제 CLI: 미리보기 무변경, 확인 없는 적용 거부, 적용, 재실행 4. 출력에 URL·역할·포트·표식 nonce·내용이 없다.
- PG에서 추가 표·트리거 차단은 실행하지 않았다(미실행). 보호 장치가 소유 밖 객체를 허용하지 않기 때문이다. 대신 실제 FK 30개가 허용 목록과 같을 때만 적용 가능하며, 위 모든 적용이 그 검사를 통과했다.

### 근거 구분

| 구분 | SQLite | PG |
| --- | --- | --- |
| 저장소(함수) | 미리보기·적용·차단·실패·경합 | 같음(스키마 차단 제외) |
| 실제 CLI | 하위 프로세스 | 하위 프로세스 |
| API·HTTP | 없음(이 도구는 API가 아님). 삭제 뒤 HTTP 거부는 E-5a 검사의 범위 | 같음 |

### 회귀

| 검사 | 결과 |
| --- | --- |
| 백엔드 전체(PG opt-in 해제) | **978개 실행: 907개 통과·71개 건너뜀**. E-5a 948/66 대비 +30(새 25, PG 전용 5 건너뜀) |
| 실제 PG 묶음(모든 `*_real` 모듈 + 커서·E-2c 단위) | **64개 통과**, 예상 실패 1(알려진 실제 변경 시작 ↔ 평가 교착), 건너뜀 0. E-5a PG 4개 포함 |
| 회귀 스크립트 | 9종 rc=0. 전용 임시 폴더를 쓰고 제거 |
| 프론트 | 159/159, 타입 검사 통과. 프론트를 바꾸지 않아 빌드는 반복하지 않음 |
| diff 검사 | 통과(기존 CRLF 경고만). 새 파일 뒤 공백·탭 0 |

## 5. 서버 DB 잔존 0과 전체 파기의 구분

이 도구의 `deleted`는 **서버 DB의 논리 삭제와 같은 transaction 안의 잔존 0**이다. 다음의 파기는 증명하지 않는다.
- PG WAL·복제본·분기·백업·덤프·다운로드 사본
- SQLite 파일의 해제 페이지(VACUUM 전)
- 브라우저 저장소의 읽기 세션·학습 계획 선택값

출력의 `server_db_only: true`가 이 구분을 표시한다.

## 6. 남은 작업 (이번 범위 밖)

- 요청 창구, 본인·대리인 확인(시행령 제46조), 10일 결과 통지, 이의 절차
- 법정 보존 판단: 거래·분쟁 기록 해당 여부, 앱 피드백 처리, 분리보관 방식. 새 보존기간은 정하지 않았다.
- 공유 덱 소유자 수동 처리: 이전·식별정보 분리·내용 삭제 중 선택. 무기한 대기 금지
- 백업·복제본의 보존 설정·만료·파기 확인, 복원 시 삭제 재적용 절차
- 파기 증적의 최소 기록·접근 통제·보유 기준
- 운영 대상 실행 승인. E-5c 전체 경로 경합(인증 직후 삭제 등)
- P-RB 복구(E-D12), 실제 변경 업그레이드 교착, E-6·E-7

## 7. 정리

- 이번에 시작한 로컬 PG만 PID·실행 파일·자료 경로를 확인한 뒤 종료했다. 55432 리스너 없음.
- 종료 전 테스트 DB 사용자 객체 0과 빈 DB 보호 검사 통과를 확인했다.
- `vocab.db` 수정 시각 불변(8월 23일). `jp_vocab_c1_*` 19개 그대로, 다른 `jp_vocab_*` 임시 폴더 0.
- 기존 변경·미추적 자료는 보존했다. 스테이징·커밋·푸시·병합 없음.

(위 1~7절은 최초 E-5b 결과다. 검토 보정은 8절.)

## 8. 검토 결함 두 건 보정 (2026-10-19)

사용자 지시(13:31Z)로 아래 두 결함만 고쳤다. 다음 단계로 넘어가지 않았다. 앱 피드백은 계속 `app_feedback_retention_review`로 자동 삭제를 보류한다. 보존 판단·수동 검토 절차는 구현하지 않았다.

### 8-1. 수정 전 재현

**P1 FK 구조 검증 누락**
- 합성 SQLite에서 `srs_user_settings.user_id → users(id)`를 `users(email)`로 바꾸고, 대상 계정의 email을 다른 계정의 설정 키와 같게 맞췄다.
- 미리보기는 `eligible: true`였고, 적용은 `deleted`였다.
- 다른 계정의 설정 행이 1 → 0으로 CASCADE 삭제됐다.
- 같은 FK를 하나 더 둔 경우(SQLite 표 재구성, 실제 PG `ADD CONSTRAINT`)도 통과했다. 기존 비교가 열 단위 집합이라 중복 제약이 합쳐졌기 때문이다.

**P2 재시작 경계 소유권 누락**
- 다음 경우 모두 차단되지 않았다(SQLite·실제 PG 모두).
  - 다른 계정의 재시작 기록이 대상 계정의 로그를 `previous_boundary`·`new_boundary`로 가리킴
  - 대상의 유효한 재시작 기록이 경계 하나만 다른 계정 로그로 바뀜

**새 회귀 테스트의 수정 전 결과**: SQLite 6건 실패, 실제 PG 5건 실패, 모킹 2건 오류(비교 함수 없음). 합성 SQLite 재현 스크립트는 세션 임시 폴더에서 실행한 뒤 지웠다.

### 8-2. 수정 (`backend/app/account_deletion.py`만)

**P1**
- FK를 **제약 하나 = 항목 하나**로 읽는다: (출발 스키마, 출발 표, 키 순서 출발 열들, 참조 스키마, 참조 표, 키 순서 참조 열들, ON DELETE).
- 목록으로 비교하므로 중복·누락·복합키 개수와 순서·참조 열·참조 스키마 차이가 모두 불일치다.
- PG는 public에서 출발하거나 public을 가리키는 모든 FK를 카탈로그에서 키 순서대로 읽는다.
- SQLite는 `PRAGMA foreign_key_list`를 제약 id로 묶는다.
- 허용 구조(SQLite 6, PG 30)는 앱 스키마 코드와 실제 카탈로그를 대조한 명시 목록이다.
- 불일치는 기존 `schema_unverified`로 쓰기 없이 막는다. 도구는 FK를 고치거나 스키마를 복구하지 않는다.

**P2**
- 재시작 기록의 두 경계를 카드 종류에 맞는 로그 표로 해석한다(`personal` → `review_logs`, `lexeme` → `lexeme_review_logs`).
- 존재하는 로그와 재시작 기록 중 하나만 대상의 것이면 기존 `cross_account_reference`로 막는다.
- 같은 숫자 id의 다른 로그 표 행은 참조로 보지 않는다.
- 로그가 없는 경계(0·NULL·삭제된 로그)는 연결이 아니며, 정상화하거나 지우지 않는다. 생성 코드 `reviews._restart_evidence_boundary`는 두 경계를 그 카드 자신의 로그로 저장한다.
- 기존 snapshot 소유권, 카드 증거 경계, 영수증 로그 참조 검사는 그대로다.

계약 `E5B_CONTRACT.md` 3절 표, 3-1, 3-2를 보정했다.

**다른 증거 참조 대조 결과(보고만)**: migration snapshot의 `legacy_json` 안 로그 참조는 섞임 검사가 아직 해석하지 않는다. 대상은 `last_log_id`, `baseline.last_log_id`, `restart.previous_boundary`, `card.evidence_from_log_id`다. 손상 JSON의 처리 기준이 필요한 추가 정책이라 이번에 구현하지 않았다. E-4 감사(I5)는 이 참조를 검사한다.

### 8-3. 테스트 (수정 후)

| 구분 | 내용 | 결과 |
| --- | --- | --- |
| SQLite (실제, 세션 파일) | P1: 참조 열 변경(다른 계정 설정 보존), 삭제 동작 변경, 중복 제약, 복합키, 정상 구조 / P2: 다른 계정 → 대상 로그(두 경계), 대상 → 다른 계정 로그(두 경계), 같은 숫자의 다른 로그 표, 없는 로그, 대상 자신의 재시작 | 새 12개 포함 E-5b **37개 통과**. 차단 시 모든 행·파일 바이트 동일 |
| 모킹(카탈로그 행을 자료로) | PG 참조 스키마·출발 스키마 변경, 참조 열·출발 열, 삭제 동작, 복합키와 열 순서, 중복, 누락 | 2개 통과 |
| 실제 PG (보호 장치, 관리 DDL 단계, 복원 확인) | P1: 중복 제약, 삭제 동작 변경, 다른 출발·참조 열 추가(`NOT VALID`) / P2: 네 방향, 같은 숫자의 다른 로그 표, 없는 로그 | 새 2개 포함 E-5b **7개 통과**. 차단 시 ctid·xmin 지문과 행 동일 |
| 변형 검사(메모리) | FK 집합 비교, 참조 열 무시, 참조 스키마 무시(모킹), 경계 검사 제거, 기존 E-5b 3종 | **10/10 검출** |

**실제 PG 미검증**
- 다른 스키마 참조 표, 순수 참조 열만 바꾼 FK: 보호 장치가 소유 밖 스키마·객체를 허용하지 않고, users에 다른 정수 유일 열이 없다. 모킹으로만 확인했다.
- 복합 FK: SQLite 실제와 모킹으로 확인했다.

### 8-4. 회귀

| 검사 | 결과 |
| --- | --- |
| 백엔드 전체(PG opt-in 해제) | **992개 실행: 919개 통과·73개 건너뜀**(+12 SQLite, +2 PG 전용) |
| 실제 PG 묶음(모든 `*_real` + 커서·E-2c 단위) | **66개 통과**, 예상 실패 1(알려진 업그레이드 교착), 건너뜀 0. E-5a·E-5b 포함 |
| 회귀 스크립트 | 9종 rc=0. 전용 임시 폴더를 쓰고 제거 |
| 프론트 | 159/159, 타입 검사 통과. 프론트 미수정이라 빌드 생략 |
| diff 검사 | 통과(기존 CRLF 경고만). 수정 파일 뒤 공백·탭 0 |

### 8-5. 변경 파일과 정리

- 제품: `backend/app/account_deletion.py`
- 테스트:
  - `backend/tests/test_e5b_account_deletion.py`
  - `backend/tests/test_e5b_account_deletion_real.py`
  - `backend/tests/_e5b_fixture.py`(대상 재시작 기록의 경계를 생성 코드처럼 그 카드의 실제 로그로 변경)
- 문서: `E5B_CONTRACT.md`, 이 보고서, REPORT 22절
- 실제 PG 정리: 정상 teardown 뒤 빈 DB 보호 검사로 사용자 객체 0을 확인했다. 이번에 시작한 서버만 PID·실행 파일·자료 경로를 확인한 뒤 종료했고, 55432 리스너는 없다.
- `vocab.db` 불변, `jp_vocab_c1_*` 19개 그대로, 다른 `jp_vocab_*` 임시 폴더 0. 스테이징·커밋·푸시·병합 없음.


## 9. snapshot 내부 로그 참조 검사 보강 (2026-10-20)

사용자 지시(2026-10-19 14:20Z, 16:46Z "이어서")에 따른 보강이다.
- 앞선 FK·재시작 경계 보정은 Codex 재검토를 통과했다. 그 재검토에서는 PG를 다시 실행하지 않았다.
- 이번에도 앱 피드백·공유 덱 소유 보류, API·화면 없음, 새 보존기간·수동 절차 없음은 그대로다.

### 9-1. 계약 (코드 변경 전 고정, `E5B_CONTRACT.md` 3-3)

| 기록 | 형식 | 참조 필드 → 대상 |
| --- | --- | --- |
| apply | 1·2·3 | `last_log_id`(필수) → 로그 |
| apply | 1·2·3 | `restart.previous_boundary` → 로그 |
| apply | 1·2·3 | `restart.rollback_record_id` → snapshot 행 |
| apply·rollback | 1 | `card.evidence_from_log_id` → 로그 |
| rollback | 1·2 | `baseline.last_log_id`(필수) → 로그 |

- 로그 표는 행의 `card_kind`로 고른다(개인 `review_logs`, 구독 `lexeme_review_logs`).
- 근거 코드: `_record_shape`·`_pruned_shape`·`_rollback_input`·`_read_rollback_record`, `restoration.restart_permission`·`proven_jump`, `reviews._conversion_start`, E-4 `log_references`.
  - `restart.rollback_record_id`는 실제 소비 코드(`restart_permission`)가 읽는 참조라서 함께 다뤘다.
- 정상 생략: restart 없음, 형식 2·3의 카드 증거 필드 없음, 형식 1 증거 NULL. 손상이 아니다.
- 0·없는 로그:
  - 값 0은 참조 없음이다(`last_log_id`는 로그가 없을 때 0으로 저장).
  - 해당 표에 없는 id도 참조가 아니다.
  - 고치거나 지우지 않는다.
- 연결: 존재하는 대상 행과 snapshot 중 하나만 삭제 대상 계정의 것이면 연결이다. 기존 `cross_account_reference`로 차단한다.
- 해석 불가: 새 고정 사유 `snapshot_reference_unverifiable`로 보류한다. 계정 간 참조로 단정하지 않는다.
  - JSON 손상, 중복 키, 지나친 중첩, 객체 아님
  - 알 수 없는 형식, rollback 형식 3
  - 필수 필드 누락, 모르는 최상위 키
  - 0~2^63−1 정수가 아닌 값(bool·문자열·실수·음수·과대 정수)
  - restart·baseline·card 모양 오류, 부모 실행 모드 불명
- 관련 없음을 증명하는 경우: 해석 불가 기록이 대상의 것이 아니고, 대상에게 그 카드 종류의 로그와 snapshot이 모두 없으면 보류 사유가 아니다.

### 9-2. 구현 (`backend/app/account_deletion.py`만)

- `_snapshot_refs`: 기록에서 참조 값만 읽는다. 최소화·복구·삭제 코드를 쓰지 않으며, 값을 다시 만들거나 고치지 않는다. 모든 이상은 내부 예외로 받아 고정 사유가 되고, 처리되지 않은 예외로 끝나지 않는다.
- `_snapshot_references`:
  - 모든 snapshot을 부모 실행 모드와 함께 읽는다.
  - 참조 로그는 카드 종류별 표에서 id 묶음으로 소유자를 조회한다.
  - 참조 snapshot은 행 소유자와 비교한다.
  - 양방향 연결 수와, 관련성을 배제할 수 없는 해석 불가 수를 돌려준다.
- `_plan`(미리보기와 잠금 뒤 재계산 공용)에서 연결은 `cross_account_reference`, 해석 불가는 `snapshot_reference_unverifiable`이다.
- `observed.unreadable_snapshot_references` 건수를 추가했다. 적용 중 확인 실패는 기존대로 전체 롤백이다.

### 9-3. 수정 전후

| 구분 | 수정 전 | 수정 후 |
| --- | --- | --- |
| SQLite 새 검사 6개 | 연결 12건·해석 불가 16건 이상·관련 없음 증명·미리보기 뒤 변경이 모두 실패. 정상값 검사만 통과 | **47개 전부 통과**(기존 37 + 새 6 + 경합 4) |
| 실제 PG 새 검사 1개 | 새 검사를 메모리에서 끈 상태로 실행하면 하위 12건 실패 | **통과** |

- 차단·보류 시 모든 행, SQLite 파일 바이트, PG ctid·xmin 지문이 같다.
- 정상 삭제 시 다른 계정·공유·전역 자료가 보존된다.

### 9-4. 시험 범위와 결과

**SQLite (실제, 세션 파일)**
- 연결:
  - 다른 계정 → 대상: apply 형식 1·2·3의 `last_log_id`, restart 두 필드, rollback 형식 1·2의 baseline, 형식 1 카드 증거, 구독 로그
  - 대상 → 다른 계정: `last_log_id`, restart, 형식 1 증거
- 비연결: 다른 표의 같은 id, 없는 로그, 0, 형식별 정상 생략
- 해석 불가 18가지: 정상 기록과 섞은 16가지, rollback 형식 3, 대상 자신의 손상 기록
- 관련 없음 증명: 로그·기록이 없는 계정은 손상 기록이 있어도 삭제 가능하다. 손상 기록은 그대로 남는다.
- 미리보기 뒤 참조가 추가되면 잠금 뒤 차단된다.
- 이전 적용·롤백·재전환과 삭제의 실제 겹침 두 순서: 삭제 먼저는 404이고, 쓰기 먼저는 `plan_changed` 또는 `blocked`(진행 중 실행)이다. 둘 다 쓰기 0이다.

**실제 PG (보호 장치·소유 증명)**
- 연결 5가지, 해석 불가 6가지, 비연결, 미리보기 뒤 변경
- 롤백·재전환과 삭제 경합 두 순서에서 대기 상대를 증명했다(transactionid ShareLock). 이번 실행의 결과는 롤백 먼저 `plan_changed`, 재전환 먼저 `blocked`였다.

**모킹**: 이번 보강에는 없다. 모든 사례를 실제 DB에서 실행했다.

**PG 미실행**: 형식 1 카드 증거, 형식 3, 실수·음수 등 해석 불가 일부(SQLite로만 확인). 같은 판정 코드이며 DB 차이는 JSON 문자열 저장뿐이다.

**변형 검사**
- 새 검사: 끄기, 카드 종류별 표 무시, 해석 불가 무시, rollback_record_id 무시 → **7/7 검출**
- 기존 변형 → **10/10 검출**

### 9-5. 회귀

| 검사 | 결과 |
| --- | --- |
| 백엔드 전체(PG opt-in 해제) | **1003개 실행: 929개 통과·74개 건너뜀**(+10 SQLite, +1 PG 전용) |
| 실제 PG 묶음 | **67개 통과**, 예상 실패 1(알려진 업그레이드 교착), 건너뜀 0. E-5a·E-5b 포함 |
| 회귀 스크립트 | 9종 rc=0. 전용 임시 폴더를 쓰고 제거 |
| 프론트 | 159/159, 타입 검사 통과. 미수정이라 빌드 생략 |
| diff 검사 | 통과(기존 CRLF 경고만). 수정 파일 뒤 공백·탭 0 |

### 9-6. 변경 파일과 정리

- 제품: `backend/app/account_deletion.py`
- 테스트: `backend/tests/test_e5b_account_deletion.py`, `backend/tests/test_e5b_account_deletion_real.py`
- 문서: `E5B_CONTRACT.md`(3절 표, 3-2, 3-3), 이 보고서, REPORT 22-2
- 정리:
  - 테스트 DB 사용자 객체 0과 빈 DB 보호 검사 통과를 확인했다.
  - 이번에 시작한 PG만 PID·실행 파일·자료 경로를 확인한 뒤 종료했다. 55432 리스너 없음.
  - `vocab.db` 불변, c1 폴더 19개 그대로, 다른 임시 폴더 0.
  - 스테이징·커밋·푸시·병합 없음.
- 운영상 결과: 손상 snapshot이 하나라도 있으면, 그와 관련성을 배제할 수 없는 계정의 자동 삭제가 보류된다. 손상 기록의 처리 방법은 이번 범위가 아니다.

E-5b 재검토 대기. E-5 전체 완료나 운영 삭제 준비 완료가 아니다.

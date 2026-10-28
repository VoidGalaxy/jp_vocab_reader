# E-5b 운영자용 계정 삭제 도구 계약

2026-10-19 · `codex/fsrs-srs-replacement` · HEAD `e2c07f8` · 구현 전 고정.

근거:
- 사용자 E-5b 작업지시(12:16Z)
- 승인된 법률 보완안: APPROVAL_REQUEST 1절, `E5_LEGAL_REVIEW_KR.md`
- E-5a 쓰기 경계: `E5A_CONTRACT.md`·`E5A_REPORT.md`
- CONTRACT 4-2·4-3·4-4·4-6

과거 문서의 "미승인" 표시와 원래의 무기한 탈퇴 차단안(E-D3 안 1)은 최신 계약이 아니다. 보완안이 우선한다.

이 도구는 **서버 DB의 논리 삭제**만 한다. 다음은 이 도구의 범위 밖이다.
- 요청 접수, 본인·대리인 확인, 결과 통지, 이의 제기
- 법정 보존 판단
- 공유 덱의 최종 처리
- 백업·복제본·WAL·다운로드 사본·브라우저 저장소 파기

## 1. 입력과 대상

- 운영자 CLI `backend/scripts/delete_account.py` 하나만 둔다. API·화면은 없다.
- 대상 DB는 둘 중 정확히 하나다.
  - `--sqlite-db`: 명시한 기존 `.db` 파일
  - `--local-test-postgres`: E-2c의 보호된 로컬 테스트 PG
- 기본 `DATABASE_URL`·`.env`·원격 URL로 가는 경로는 없다. 범용 PG 접속·운영용 우회 옵션도 추가하지 않는다.
- 필수 인자: `--user-id`(양의 정수).
- 적용 인자:
  - `--apply`
  - `--confirm-user-id`: `--user-id`와 같아야 한다
  - `--expect-plan`: 미리보기가 출력한 계획 지문
- 계정 번호 재입력은 **실행 실수 방지**다. 요청자 본인 확인을 대신하지 않는다. 본인 확인은 외부 절차의 몫이며, 도구는 그 결과를 검증하지 않는다.

## 2. 미리보기 (기본, 쓰기 없음)

- 하나의 읽기 전용 snapshot에서 다음을 계산한다(SQLite `query_only`, PG `READ ONLY REPEATABLE READ`).
  - 대상 계정의 표별 건수
  - 차단 사유
  - 계획 지문
- 계획 지문은 대상 자료의 행 id 집합(표별 정렬)과 차단 관련 건수로 만든 sha256이다. 내용은 넣지 않는다. 미리보기 뒤 대상 행이 생기거나 사라지면 지문이 바뀐다.
- 적용 가능 여부(`eligible`)는 차단 사유가 0일 때만 참이다.

## 3. 적용 차단 조건 (하나라도 있으면 쓰기 없이 `blocked`)

| 사유 코드 | 조건 | 처리 |
| --- | --- | --- |
| `schema_unverified` | 표 목록, 대상 표의 `user_id` 열, 사용자 트리거, 실제 FK가 명시 허용 구조와 다르다. FK는 **제약 단위**로 비교한다(3-2) | 모르는 표·관계를 조용히 건너뛰지 않는다. FK를 고치거나 스키마를 복구하지 않는다 |
| `shared_deck_owner_review` | 계정이 공유 덱을 하나라도 소유한다(공개·비공개, 구독자 유무와 무관) | 자동 삭제만 중단하고 **별도 검토 대상**으로 보고한다. 영구 거절도 삭제 완료도 아니다 |
| `app_feedback_retention_review` | 계정의 `app_feedback` 행이 있다 | 법정 보존(거래 불만·분쟁 기록 등) 해당 여부를 코드로 추정하지 않는다. 확인 불가로 보고 막는다 |
| `migration_run_in_progress` | 대상 계정의 `started` 이전 실행이 있다 | 진행 중 자료를 지우지 않는다 |
| `run_ownership_unverifiable` | 어떤 실행이든 `scope_json`의 소유 계정을 읽을 수 없다 | 대상 실행을 확정할 수 없다 |
| `cross_account_reference` | 대상 자료와 다른 계정 자료가 서로 가리킨다(아래 3-1) | 삭제 범위를 넓히지 않고 중단한다 |
| `snapshot_reference_unverifiable` | 대상과 관련성을 배제할 수 없는 snapshot 기록의 참조를 해석할 수 없다(3-3) | 계정 간 참조로 단정하지 않고 보류한다. 기록을 고치지 않는다 |

3-1. 섞임 검사 (대상 = T):
- snapshot의 `user_id`와 부모 실행 소유자 중 하나만 T이거나, 부모를 확인할 수 없다.
- 증거 재시작의 `user_id`와 원 snapshot의 `user_id` 중 하나만 T이다.
- 증거 재시작의 `previous_boundary`·`new_boundary`가 가리키는 로그(카드 종류에 맞는 로그 표: `personal` → `review_logs`, `lexeme` → `lexeme_review_logs`)와 재시작 기록 중 하나만 T의 것이다(E-5b 검토 보정 P2).
  - 같은 숫자 id의 다른 로그 표 행은 참조가 아니다.
  - 로그가 없는 경계(0·NULL·삭제된 로그)는 연결이 아니다. 판정만 하며 정상화하거나 지우지 않는다.
  - 생성 코드(`reviews._restart_evidence_boundary`)는 두 경계를 모두 그 카드 자신의 로그로 저장한다.
- T의 덱에 다른 계정의 카드·용어가 있거나, 다른 계정의 가져오기 기록이 T의 덱을 가리킨다.
- 다른 계정의 공유 덱이 T의 덱에서 발행됐다고 표시된다.
- 다른 계정의 로그·영수증·원장·표시·재시작·뜻 피드백이 T의 카드 id를 가리킨다(`personal`).
- T의 카드·영수증이 다른 계정의 로그를 증거·로그로 가리키거나, 그 반대이다.

3-2. FK 구조 비교 (E-5b 검토 보정 P1):
- 제약 하나를 항목 하나로 본다: (출발 스키마, 출발 표, 키 순서의 출발 열들, 참조 스키마, 참조 표, 키 순서의 참조 열들, ON DELETE).
- 목록으로 비교한다. 중복 제약, 복합키의 열 개수·순서, 참조 열·참조 스키마가 다르면 불일치다.
- PG는 public에서 출발하거나 public을 가리키는 모든 FK를 읽는다. 같은 이름의 다른 스키마 표는 정상으로 인정하지 않는다.
- SQLite는 `PRAGMA foreign_key_list`를 제약 id로 묶는다(스키마는 `main`).
- 허용 구조는 앱 스키마 코드와, 새 SQLite 파일·보호된 로컬 PG의 실제 카탈로그를 대조해 정했다.
- snapshot `legacy_json` 안의 참조는 3-3에서 다룬다(E-5b 보강).

3-3. snapshot 내부 참조 (E-5b 보강, 2026-10-20 구현 전 고정)

- **대상 기록**: `srs_migration_snapshots`의 모든 행. 기록 종류는 부모 실행의 `mode`(apply·rollback)로 정한다. 로그 표는 행의 `card_kind`로 정한다(`personal` → `review_logs`, `lexeme` → `lexeme_review_logs`).
- **형식**: `legacy_json`에 `format`이 없으면 형식 1, 2와 3은 그 값이다. 형식 3은 apply 기록만 있다.

| 기록 | 형식 | 참조 필드 | 대상 |
| --- | --- | --- | --- |
| apply | 1·2·3 | `last_log_id`(필수) | 로그 |
| apply | 1·2·3 | `restart.previous_boundary`(restart가 있을 때) | 로그 |
| apply | 1·2·3 | `restart.rollback_record_id`(restart가 있을 때) | snapshot 행 |
| apply·rollback | 1 | `card.evidence_from_log_id`(카드 행 사본에 있을 때) | 로그 |
| rollback | 1·2 | `baseline.last_log_id`(필수) | 로그 |

- **근거 코드**: `migration._record_shape`·`_pruned_shape`·`_rollback_input`·`_read_rollback_record`, `restoration.restart_permission`·`proven_jump`, `reviews._conversion_start`, E-4 `invariant_audit.log_references`.
- **정상 생략**:
  - restart가 없는 apply 기록
  - 형식 2·3 카드에 `evidence_from_log_id`가 없는 것(형식 2·3은 그 필드를 남기지 않는다)
  - 형식 1 카드의 `evidence_from_log_id`가 NULL인 것
  - 이 경우들은 손상이 아니다.
- **0·없는 로그**:
  - 값 0은 "참조 없음"이다. `last_log_id`·`baseline.last_log_id`는 로그가 없을 때 0으로 저장된다. 같은 규칙을 나머지 필드에도 적용한다.
  - 해당 표에 없는 id도 참조가 아니다.
  - 둘 다 판정만 하며 고치거나 지우지 않는다.
- **연결(차단, 기존 `cross_account_reference`)**: 존재하는 참조 대상(로그 또는 snapshot)과 그 snapshot 행 중 하나만 대상 계정의 것이면 연결이다. 같은 숫자의 다른 로그 표 행은 참조가 아니다.
- **해석 불가**(새 고정 사유 `snapshot_reference_unverifiable`, 보류):
  - JSON을 읽을 수 없다: 깨진 JSON, 중복 키, 지나친 중첩
  - 최상위가 객체가 아니다
  - 형식 값을 모른다, 또는 rollback 기록이 형식 3이다
  - 필수 참조 필드가 없다, 또는 기록 종류에 없는 최상위 키가 있다
  - 참조 값이 0 이상 2^63−1 이하 정수가 아니다(bool·문자열·실수·과대 정수 포함)
  - restart·baseline·card가 객체가 아니다, 또는 restart의 키 집합이 다르다
  - 부모 실행의 `mode`를 모른다
  - 이 경우 계정 간 참조가 있다고 단정하지 않는다. 안전을 증명하지 못한 것으로 보고 자동 삭제만 보류한다.
- **관련 없음을 증명할 수 있는 경우**: 해석 불가 기록이 대상 계정의 것이 아니고, 대상 계정에 그 카드 종류의 로그와 snapshot이 모두 없으면, 그 기록은 대상과 연결될 수 없으므로 보류 사유가 아니다. 그 밖의 해석 불가 기록은 관련성을 배제할 수 없다. 대상 계정의 기록이거나, 대상에 해당 로그·snapshot이 있는 경우다.
- **하지 않는 것**:
  - snapshot·로그·지문·증명·허가 값의 수정·정규화·삭제
  - 최소화·복구·만료 정리 코드의 실행
  - 다른 계정으로 삭제 범위 확대
- **같은 검사 위치**: 미리보기와 잠금 뒤 재계산에서 같은 검사를 쓴다. 적용 중 검사 실패는 전체 롤백이다.

계정이 없으면 차단이 아니라 `account_not_found`다.

## 4. 적용

1. 같은 저장 연결에서 E-5a 공용 잠금 `begin_account_write`를 잡는다. SQLite는 BEGIN IMMEDIATE, PG는 users 행 FOR UPDATE이고, 커밋·롤백까지 유지한다.
2. 잠금 뒤 READ COMMITTED 최신 자료로 미리보기와 같은 계산을 다시 한다.
   - 계정 없음: `account_not_found`
   - 차단 사유 있음: `blocked`
   - 지문이 `--expect-plan`과 다름: `plan_changed`
   - 셋 모두 쓰기 0으로 끝난다.
3. 삭제 순서. 의존 순서를 명시하며, 각 문장은 T의 행만 고른다.
   1. `srs_evidence_restarts`
   2. `srs_migration_snapshots`
   3. `srs_migration_runs`(소유 확인된 T 실행 id)
   4. `srs_review_receipts`, `srs_card_deletions`, `srs_card_identity_flags`, `srs_user_settings`
   5. `review_logs`, `lexeme_review_logs`
   6. `user_word_progress`, `user_deck_subscriptions`, `shared_deck_imports`
   7. `meaning_feedback`
   8. `vocab_items`, `custom_terms`
   9. `decks`
   10. `users`
4. 각 문장의 삭제 행 수가 잠금 뒤 계산한 계획 건수와 다르면 실패로 처리한다.
5. 같은 transaction에서 잔존 검사를 한다(CONTRACT 4-6).
   - 모든 대상 표의 T 행 0
   - T 소유 실행 0
   - T를 가리키는 영수증·원장·표시·재시작 0
   - 위 섞임 검사 0
   - 공유·전역 자료(lexemes, 공유 덱과 하위, 설정 버전) 건수 무변경
   - 하나라도 어긋나면 전체 롤백하고 `failed`
6. 커밋. 결과는 `deleted`와 표별 삭제 건수다.

- CASCADE·SET NULL에 기대어 범위를 정하지 않는다. 모든 삭제는 명시 문장으로 하고, users 삭제 시점에는 남은 참조 행이 0이어야 한다.
- 중간 예외·DB·잠금·커밋 오류는 전체 롤백 후 `failed`(오류 형식명만)로 끝난다. 정상 결과나 차단으로 바꾸지 않는다.
- 다른 계정·공유 원본 lexeme·전역 설정은 바꾸지 않는다.
- 카드 삭제용 원장 기록·내용 최소화·7일/30일 정리는 이 절차에서 쓰지 않는다. 탈퇴 삭제는 원장도 남기지 않는다(CONTRACT 4-2).

## 5. 재실행과 오래된 계획

- 삭제 뒤 같은 입력으로 다시 실행하면 `account_not_found`이고 쓰기 0이다. 자료를 다시 만들지 않는다.
- 미리보기 뒤 자료가 바뀌면 `plan_changed`이다. 다시 미리보기한 뒤 새 지문으로 적용한다.

## 6. 출력

- 표준 출력 JSON 1개:
  - `status`: `preview`·`deleted`·`blocked`·`account_not_found`·`plan_changed`·`failed`
  - `user_id`, `applied`, `eligible`, `reasons`(고정 코드), `counts`(표별 건수), `plan`(지문)
  - `failed`일 때 `error`(형식명)
  - `database`: 파일 이름 또는 `local_test_postgres`
  - `server_db_only: true`: 서버 DB 논리 삭제일 뿐 백업·복제본·브라우저 파기 완료가 아니라는 표시
- 이메일·단어·뜻·예문·JSON 본문·토큰·연결 문자열·원시 오류는 넣지 않는다.
- 종료 코드:
  - 0: preview·deleted
  - 1: failed
  - 2: 인자·대상 거부
  - 3: blocked
  - 4: account_not_found
  - 5: plan_changed

## 7. 검증 계획

- **SQLite (합성, 세션 전용 파일)**
  - dry-run의 행·파일 무변경
  - 정상 삭제, 다른 계정 불변, 잔존 0, 재실행
  - 각 차단 사유, 손상·미지원 자료
  - 단계별 실패 주입과 전체 롤백
  - 오래된 계획, 실제 CLI
- **PG (E-1/E-2 보호 장치, 제한 역할, 실행 표식·소유 목록)**
  - 위와 같은 항목
  - 실제 겹친 실행 양쪽 순서와 대기 상대 증명: 삭제 ↔ 평가·단어 생성·구독·발행·이전 적용
  - 실제 CLI
- **회귀**: E-5a, SRS·이전·삭제·학습계획·공유, 백엔드 전체, 프론트 테스트·타입 검사, diff

## 8. 남은 운영 작업 (도구 밖)

- 요청 창구, 본인·대리인 확인, 10일 결과 통지, 이의 절차
- 법정 보존 판단: 거래·분쟁 기록 해당 여부, 분리보관 방식·기간. 새 기간은 정하지 않는다.
- 공유 덱 소유자의 수동 처리 경로: 이전·식별정보 분리·내용 삭제 중 선택
- 앱 피드백의 보존 판단
- 백업·복제본·WAL·다운로드 사본의 만료·파기 확인, 복원 시 삭제 재적용
- 브라우저 저장소 안내
- 파기 증적의 최소 기록과 접근 통제
- 운영 대상 실행은 별도 승인

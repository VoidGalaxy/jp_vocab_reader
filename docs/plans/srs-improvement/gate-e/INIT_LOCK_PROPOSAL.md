# 앱 시작 init_db와 평가의 교착 — 최소 수정안 (2026-10-18 작성, **2026-10-19 A안 승인**, 구현은 REPORT 13절)

근거: Codex 검토 `E3_REVIEW_CODEX.md` P1, REPORT 12절의 실제 PG 18.6 재현(`backend/tests/test_srs_e3_init_race_real.py`).
**제품 코드는 바꾸지 않았다. 아래는 승인 요청용 설계다.**

## 1. 무엇이 확인됐나
- 앱은 시작할 때마다 `init_db → ensure_schema`를 한 트랜잭션으로 실행한다. 스키마가 이미 최신이어도 같다.
- 무변경 init_db가 잡는 표 잠금을 실제로 측정했다(REPORT 12-3).
  - `create_postgres_tables` 직후:
    - `CREATE INDEX IF NOT EXISTS` 때문에 ShareLock: vocab_items, user_word_progress, review_logs, lexeme_review_logs, shared_decks, user_deck_subscriptions, meaning_feedback, app_feedback 등
    - `ALTER TABLE shared_deck_words ADD COLUMN IF NOT EXISTS ...` 때문에 AccessExclusiveLock: shared_deck_words
  - `ensure_srs_schema`의 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 때문에 AccessExclusiveLock: vocab_items, user_word_progress, review_logs, lexeme_review_logs, srs_card_deletions
  - 즉 할 일이 없는 시작에서도 약한 잠금을 먼저 잡고, 같은 표나 다른 표에 강한 잠금을 나중에 잡는다.
- 그 사이에 들어온 평가와 교착한다(실제 재현, 현재 경로와 E-3 FK 제거 비활성 대조군 모두 같음).

| 교착 | 순서 | 대기 그래프 (서버 기록) | 실패한 작업 | 결과 |
| --- | --- | --- | --- | --- |
| 구독 평가 | init_db가 먼저(create_postgres_tables 직후) | 평가: `user_word_progress` 행 잠금 보유, `shared_deck_words` RowShareLock 대기(구독 권한 확인 `FOR SHARE`). init_db: `shared_deck_words` AccessExclusive 보유, `user_word_progress` AccessExclusive 대기 | 평가(DeadlockDetected) | 평가 롤백, 로그 추가 0. init_db 성공 |
| 개인 평가 | init_db가 먼저(같은 위치) | init_db: `vocab_items` ShareLock 보유 뒤 AccessExclusive 대기. 평가: `vocab_items` 행 잠금(RowShare) 보유, RowExclusive(UPDATE) 대기 | init_db(DeadlockDetected) | init_db 전체 롤백(옛 FK 그대로), 평가 커밋 |

- 평가가 먼저면(평가가 로그 INSERT 뒤 멈춤) 두 종류 모두 정상이었다. init_db가 기다렸다가 진행했다.
- 구독 최초 평가는 이번 위치에서 교착하지 않았다. 다른 시점의 교착 가능성은 확인하지 않았다.
- E-3 보정(FK 제거 함수가 카드 → 로그 순서로 처음부터 배타 잠금)은 함수 안의 멈춤 위치만 보호한다. 위 두 교착은 그 함수 **이전**의 기존 DDL에서 생긴다. 그래서 **E-3 신규 회귀가 아니라 기존 위험**이다. 단, 기존 출시 차단 목록에 넣는다.

## 2. 원인
init_db 한 트랜잭션 안의 잠금 순서와 강도다.
- `create_postgres_tables`: 여러 표에 Share(인덱스 확인), `shared_deck_words`에 AccessExclusive
- (E-3) `drop_personal_log_card_fk`: 할 일이 있을 때만 vocab_items → review_logs AccessExclusive
- `ensure_srs_schema`: vocab_items → user_word_progress → review_logs → lexeme_review_logs → srs_card_deletions AccessExclusive

앱의 평가 경로 순서와 비교하면:
- 개인 평가: users 행 → vocab_items 행 → review_logs
- 구독 평가: users 행 → user_word_progress 행 → user_deck_subscriptions·shared_deck_words `FOR SHARE` → lexeme_review_logs

init_db는 약한 잠금을 먼저 잡고 나중에 올리며(Share → AccessExclusive), 앱과 다른 표 순서로 잡는다.

## 3. 대안 비교
| 안 | 내용 | 효과 | 한계·위험 |
| --- | --- | --- | --- |
| **A. 불필요한 DDL 건너뛰기 (권장)** | PG 경로에서 각 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`와 `CREATE INDEX IF NOT EXISTS` 전에 카탈로그(`pg_attribute`·`pg_indexes`)를 읽어, 이미 있으면 실행하지 않는다. SQLite 경로는 이미 열 존재를 확인하고 있다(`_add_columns`) | 스키마가 최신인 평상시 시작(재시작·다중 작업자 시작)은 표 잠금을 잡지 않아 두 교착이 사라진다. 기능·정책 변화 없음 | 실제로 열·인덱스를 더하는 업그레이드 시작에는 여전히 강한 잠금이 필요하다(아래 B와 운영 절차로 다룸) |
| B. 실제 변경이 있을 때만 정해진 순서·시간 제한으로 잠금 | 필요한 DDL 목록을 먼저 계산하고, 비어 있지 않으면 대상 표를 고정 순서로 한 번에 AccessExclusive 잠금(시간 제한) 뒤 실행 | 업그레이드 시작의 교착 가능성을 줄인다 | 앱 경로마다 순서가 달라(개인·구독) 모든 교착을 막는 단일 순서는 없다. 잠금 대기 중 시간 초과로 시작 실패 가능 → 운영 창에서 실행해야 함 |
| C. 스키마 업그레이드를 앱 시작에서 분리 | 별도 명령으로 배포 전에 실행하고, 앱 시작은 확인만 | 근본 해결 | 배포·운영 절차 변경이 크다(이번 범위 밖) |
| D. init_db 전체에 lock_timeout | 대기를 제한 | 무한 대기는 막지만 교착 자체는 그대로(교착 감지 1초가 먼저) | 문제를 숨긴다 |
| 하지 말 것 | 계정 잠금·구독 권한 확인 약화, 전체 요청 직렬화, 무한 재시도 | - | 지시로 금지 |

**권장: A를 최소 수정으로 먼저 하고, 실제 변경이 있는 업그레이드는 운영 절차(정해진 창, 트래픽 차단 또는 저부하)로 다룬다.** B·C는 후속 결정으로 둔다.

## 4. A의 변경 지점과 영향
- 변경 지점:
  - `backend/app/database.py` `create_postgres_tables`: `ALTER TABLE shared_deck_words ADD COLUMN IF NOT EXISTS ...`(현재 1057행 부근)와 PG의 `CREATE INDEX IF NOT EXISTS` 문장들
  - `backend/app/srs/schema.py`: `_add_columns`의 PG 분기(현재는 무조건 `ADD COLUMN IF NOT EXISTS`), `INDEXES` 실행부
  - 공통 함수 하나: "열/인덱스가 없을 때만 실행"
- 새 스키마: 처음 생성 경로는 같다(빈 DB라 경합 대상이 없음).
- 기존 스키마(최신): 시작 시 카탈로그 읽기와 데이터 시드 DML만 남는다. 측정상 DML은 decks·vocab_items 등에 RowExclusive를 잡는데, 이는 평가의 행 잠금과 충돌하지 않는다.
- 기존 스키마(업그레이드 필요): 해당 표만 강한 잠금을 잡는다. 운영 창이 필요하다(EXECUTION_PLAN 4절).
- 다중 작업자 시작: 최신 스키마면 작업자끼리 서로 막지 않는다.
- 개인·구독 평가 로직, 계정 잠금, 구독 권한 확인, SRS 정책, E-3 로그 보존은 변하지 않는다.

## 5. 필요한 승인과 회귀 검사
- 승인: **제품 초기화 코드 변경**("PG init_db의 무변경 DDL 건너뛰기", A안). 운영 적용은 별도 승인.
- 회귀 검사:
  - 실제 PG에서 무변경 init_db의 표 잠금이 0인지(`test_init_db_lock_footprint`를 판정 검사로 전환)
  - 초기화 경합 매트릭스에서 known 교착 0(현재 `expectedFailure` 검사가 통과로 바뀌는 것을 검토 뒤 정상 검사로 전환)
  - 열·인덱스가 하나 빠진 기존 스키마에서 그것만 추가되는지, 재실행 무변경인지
  - E-3 FK 제거, E-2 다섯 단계, SQLite 전체 회귀, 회귀 스크립트 9종

## 6. 구현 계약 (A안, 2026-10-19 승인 뒤 구현 전 고정)

대상은 PG 초기화 경로의 **열 추가**(`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`)와 **인덱스 생성**(`CREATE [UNIQUE] INDEX IF NOT EXISTS`)뿐이다. `CREATE TABLE IF NOT EXISTS`는 기존 표에 잠금을 잡지 않는 것으로 측정됐으므로 그대로 둔다. SQLite 경로는 바꾸지 않는다.

**열** (`shared_deck_words`의 추가 열 5개, SRS 카드·로그 열, 삭제 원장 증거 열)
- 읽는 것: 대상 표를 DDL과 같은 방식(search path)으로 해석한 `to_regclass(표)`에 대해 `pg_attribute`(삭제되지 않은 열)의 이름·`format_type`·`attnotnull`.
- 기대값: 기존 정의 문자열의 첫 두 요소(열 이름, 타입 TEXT/INTEGER/DOUBLE PRECISION)와 `NOT NULL` 여부. 이 외의 기본값·CHECK는 비교하지 않는다. 예전 `ADD COLUMN IF NOT EXISTS`도 기존 열의 기본값·CHECK를 확인하지 않았다(한계로 기록).
- 판정:
  - 모두 있고 타입·NOT NULL이 맞으면 DDL을 실행하지 않는다.
  - 없는 열이 있으면, 그 열들만 기존 정의 그대로 한 문장의 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`로 추가한다. 실행 뒤 다시 읽어 모두 맞는지 확인한다.
  - 있는데 타입·NOT NULL이 다르거나, 대상 표가 없으면 `SchemaUpgradeError`로 중단한다. 같은 트랜잭션 전체가 롤백된다. 타입 변경·DROP은 하지 않는다.

**인덱스** (`create_postgres_tables`의 15개, SRS `INDEXES` 6개)
- 기대값: 기존 문장에서 이름·대상 표·열 목록·UNIQUE 여부를 좁은 정규식으로 읽는다. 모든 문장이 `CREATE [UNIQUE] INDEX IF NOT EXISTS 이름 ON 표(열, ...)` 형태이며, 다른 형태면 프로그래밍 오류로 중단한다.
- 읽는 것: 대상 표의 스키마에서 그 이름의 관계(`pg_class`)와 `pg_index`(대상 표 oid, `indisvalid`, `indisready`, `indisunique`, 식·조건 없음, 키 열 이름 순서), 접근 방식(btree).
- 판정:
  - 이름의 관계가 없으면 기존 문장을 그대로 실행하고, 실행 뒤 같은 확인을 통과해야 한다.
  - 있고 모든 조건이 맞으면 실행하지 않는다.
  - 다른 종류의 관계, 다른 표의 인덱스, 무효·미준비 인덱스, UNIQUE·열·식·조건·접근 방식이 다르면 `SchemaUpgradeError`로 중단한다. DROP·재생성·REINDEX는 하지 않는다.

**공통**
- 필요한 변경을 건너뛰고 성공 처리하지 않는다(실행 뒤 확인).
- 실제 변경이 필요한 업그레이드는 여전히 강한 잠금을 잡는다. 동시 요청과의 교착 위험이 남으므로 운영 창·별도 절차가 필요하다(이번 승인 범위 밖).
- 성공 기준: 최신 스키마의 `init_db`가 이 DDL 때문에 Share·AccessExclusive 등 강한 표 잠금을 잡지 않는다. 조회·시드 DML의 정상 잠금은 남는다.

## 7. 인덱스 정의 판정 보정 (2026-10-19, Codex)

E13_REVIEW_CODEX의 두 지적에 대해 사용자가 Codex에 직접 보정을 요청했다. A안의 정의 일치 조건을 구현에서 빠짐없이 확인하는 보정이며, 다른 SRS 정책이나 운영 적용 승인으로 확대하지 않는다.

- 기존 문장은 일반 검색 키만 선언하며 INCLUDE·정렬 옵션·연산자 클래스·COLLATE를 지정하지 않는다.
- 따라서 `indnkeyatts`와 `indnatts`가 모두 기대 열 수와 같아야 한다. INCLUDE 열을 검색 키로 간주하지 않는다.
- 각 검색 키의 `indoption`은 기본값 0, opclass는 같은 접근 방식·열 타입의 기본 opclass여야 한다. `indcollation`은 해당 열의 `attcollation`과 같아야 한다.
- 기존 대상 표·유효성·준비 상태·UNIQUE·열 순서·식·조건·btree 판정도 유지한다.
- 불일치는 기존 `index_definition_mismatch`로 중단한다. 원래 객체·행은 보존하며 자동 DROP·재생성·REINDEX는 하지 않는다.
- 테스트의 동시 DDL 기록기는 작업자 밖에서 한 번만 설치·복원하고, 짧은 기록 잠금으로 스레드·연결별 관측을 분리한다. 실제 DB 실행을 이 잠금 안에서 직렬화하지 않는다.

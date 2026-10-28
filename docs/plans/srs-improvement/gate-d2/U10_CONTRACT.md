# Gate D-2 U10 계약 초안: snapshot 내용 최소화와 롤백 기간 (U10-0, 승인 대기)

작성: 2026-10-14. 브랜치 `codex/fsrs-srs-replacement`, HEAD `e2c07f8`(미커밋 작업 위). 이 문서는 설계·계약안이며 제품 코드·스키마·자료는 바꾸지 않았다. **PostgreSQL은 미검증·출시 차단이다.**

D-P4a(snapshot 최소 필드)·D-P4b(롤백 가능 기간 30일, 5절 후속 기준)는 U8 이전에 쓰였다. 그 뒤 U8이 snapshot·실행 기록에 세 가지 새 의존성을 만들었다: 재전환 복원, 버전 공백 증명(`restoration.proven_jump`), B안 첫 평가 허가(`restoration.restart_permission`). 예전 최소 필드 목록과 "기간이 지나면 snapshot을 지운다"는 그대로 적용할 수 없다(근거: 3절, REPORT 26절 재현).

## 1. 기록 종류

| 기록 | 위치 | 쓰는 곳 |
| --- | --- | --- |
| 전환 snapshot (apply) | `srs_migration_snapshots`, 실행 `mode='apply'` | 최초 전환·재전환 적용(`migration.apply_plan`, `migration.py:451`) |
| 롤백 기록 | 같은 표, 실행 `mode='rollback'` | `migration.rollback_plan`(`migration.py:567`) |
| 실행 | `srs_migration_runs` (`scope_json`, `summary_json`, `status`, 시각) | `_run_id`, `apply_plan`, `rollback_plan` |
| 경계 교체 기록 | `srs_evidence_restarts` | B안 첫 평가(`reviews._restart_evidence_boundary`) |

## 2. 분류

- **C. 삭제할 내용 사본**: 카드 내용과, 어떤 코드도 읽지 않는 카드 행 복사분.
- **R. 기간 내 롤백 자료**: 롤백 실행이나 재전환 복원에만 쓰인다. 기간이 지나면 지워도 된다.
- **P. 재전환·첫 평가 허가 자료**: 아직 쓰지 않은 B안 허가와 최근 전환·롤백 판정. 쓰이거나 대체될 때까지 필요하다.
- **L. 장기 무결성 증명**: 증거 구간의 버전 공백 증명, 과거 전환 여부, ID 참조·식별 검사. 카드가 있는 한 필요하다.

## 3. 필드별 의존성 표 (실제 읽는 곳)

### 3-1. 전환 snapshot (apply)

| 필드 | 읽는 곳 | 용도 | 분류 |
| --- | --- | --- | --- |
| 열 `user_id`, `card_kind`, `card_ref`, `run_id` | `_was_converted`(`migration.py:238`), `_latest_rollback_record`(`:246`), `restoration._records`(`restoration.py:59`), `rollback_plan` | 카드·실행 연결 | L |
| 열 `card_version_before` | `rollback_plan`(`:529`, `:546`), `proven_jump`(`restoration.py:78~106`), `restart_permission`(`:134`) | 롤백 버전 검사, 증명, 허가 | R+L+P |
| 열 `created_at` | `identity.scan_identity`(`identity.py:361`, snapshot 조회 `:426`) | snapshot이 카드보다 먼저인지(식별 신호) | L |
| `legacy_json.card` 내용: `surface`, `base_form`, `reading`, `part_of_speech`, `normalized_form`, `meaning_ko`, `dictionary_gloss`, `quality_tag`, `context_explanation_ko`, `example_sentence` | 없음 | - | **C** |
| `legacy_json.card`: `deck_id`, `status`, `correct_count`, `wrong_count`, `last_reviewed_at`, `updated_at`, `history_intro_*`, `evidence_from_log_id`, (구독) 진도 행 나머지 | 없음(경계·표시는 `ROLLBACK_PRESERVED`로 복원하지 않음) | - | **C** |
| `legacy_json.card.id` (개인) | `identity._snapshot_ids`(`identity.py:131`) — 없으면 ID 참조 조사가 중단(재현 D) | ID 참조 | L |
| `legacy_json.card.created_at` | `identity.scan_identity`(`identity.py:426~436`) | 다른 카드 snapshot 판정 | L |
| `legacy_json.card.review_level`, `next_review_at` | `rollback_plan`(`:543`) | legacy 예약 재계산 시작점 | R |
| `legacy_json.card.srs_*`(엔진·설정·상태 6열·유효 예정·참여·중지 사유·품질·플래그) | `rollback_plan`(`:551`) | 롤백 뒤 엔진 열 | R |
| `legacy_json.card.completion_metric_version`, `first_completed_at` | `rollback_plan`(`:556`) | 카드 값이 없을 때만 대체 | R |
| `legacy_json.card.srs_card_version`, `srs_engine` | `proven_jump`(`restoration.py:106`) | 재전환 직전 카드가 그 버전의 legacy였는지 | L(재전환 snapshot만) |
| `legacy_json.last_log_id` | `rollback_plan`(`:527`), `proven_jump`(`:105`), `restart_permission`(`:139`) | 이후 로그 범위, 증명, 허가 | R+L+P |
| `legacy_json.restart` | `restart_permission`(`:130`) | B안 허가 | P(쓰기 전) → L(추적) |
| 열 `srs_after_json`(쓴 값) | `proven_jump`(`_state`, 유효 예정), `restart_permission`(상태 없음 확인) | 증명, 허가 | L+P |
| 열 `srs_before_json` | 없음(항상 "null") | - | C |
| 열 `history_quality`, `history_flags` | 없음 | 정보용 | 선택(내용 아님) |

### 3-2. 롤백 기록

| 필드 | 읽는 곳 | 용도 | 분류 |
| --- | --- | --- | --- |
| 열 `card_version_before` | `proven_jump`(`restoration.py:78~89`) | 롤백 직전 버전 | L |
| 열 `srs_before_json`(롤백 직전 FSRS 13열) | `_read_rollback_record`(`migration.py:263`), `proven_jump`(`_state`, 유효 예정) | 재전환 복원, 증명 | R(복원) + L(증명) |
| `legacy_json.baseline.card_version`, `last_log_id` | `_reconvert_candidate`(`:312`), `proven_jump`(`:93~94`) | 변경 판정, 증명 | R + L |
| `legacy_json.baseline.card_fingerprint`, `logs_fingerprint` | `_reconvert_candidate`(`:313`) | 변경 판정(해시값이지 내용 아님) | R |
| `legacy_json.card`(롤백 직후 행 전체) | `identity._snapshot_ids`가 `card.id`만, `scan_identity`가 `card.created_at`만 | ID 참조·식별 | `id`·`created_at`만 L, 나머지는 **C** |
| 열 `srs_after_json`(롤백이 쓴 값) | 없음 | - | C |

### 3-3. 실행

| 필드 | 읽는 곳 | 용도 | 분류 |
| --- | --- | --- | --- |
| `mode`, `status` | `rollback_plan`, `_latest_rollback_record`, `proven_jump`, `restart_permission`, `_undone_by_completed_rollback` | 완료·중단 해석 | L |
| `scope_json`(apply: 계정·설정·카드별 지문·값·플래그) | `_run_id`(재개 일치, `migration.py:374`), `identity._run_ids`(`identity.py:106`) | 재개, ID 참조 | 진행 중 R, 이후 L(`cards`의 kind·ref_id만 필요) |
| `scope_json`(rollback: `user_id`, `source_run_id`) | `_undone_by_completed_rollback`(`restoration.py:68`), `identity._run_ids` | 증명, ID 참조 | L |
| `summary_json`(커서·결과) | 재개(`apply_plan:401`), 같은 롤백 키 재호출(`rollback_plan:511`), `identity._run_ids` | 재개·멱등, ID 참조 | 진행 중 R, 이후 L |
| `config_version` | `rollback_plan`(`:528`) | 롤백 충돌 검사 | R |
| `started_at`, `finished_at` | 지금은 없음 | 만료 기산점 후보 | (U10 신규) |

- 실행 기록에는 카드 내용이 없다. `scope_json.cards[].values`는 SRS 값이다.

### 3-4. 경계 교체 기록 (`srs_evidence_restarts`)
- 모든 열이 L이다(id·버전만, 내용 없음). user FK CASCADE.
- 이 행이 있으면 해당 snapshot의 B안 허가는 "사용됨"이다(`restart_permission`, `reviews._restart_evidence_boundary`).

## 4. 제안: 명시적 최소 형식 (형식 버전 2)
카드 행 전체 복사를 그만두고 아래 키만 쓴다. `legacy_json`에 `"format": 2`를 둔다.
- **apply snapshot `legacy_json`**
  - `card`: 개인일 때 `id`, `created_at`, `review_level`, `next_review_at`, `completion_metric_version`, `first_completed_at`, `srs_card_version`, `srs_engine`, 그리고 롤백이 복원할 `srs_*` 명시 목록(엔진·설정·상태 6열·유효 예정·참여·중지 사유·품질·플래그).
  - `last_log_id`, (B안) `restart`.
- **rollback 기록 `legacy_json`**: `card`(`id`, `created_at`), `baseline`(4키). `srs_before_json`(13열)은 그대로 두고, `srs_after_json`은 `"null"`로 둔다.
- **롤백 필수 필드 검증(결함 보정 포함)**
  - 지금 `rollback_plan`은 snapshot의 `card`에 있는 `srs_*` 키만 복원한다. 키가 없으면 조용히 건너뛰어, "rolled_back"이라 보고하고도 카드가 FSRS로 남는다(재현 E).
  - 형식과 무관하게 필수 키가 모두 있을 때만 롤백하고, 없으면 그 카드를 `blocked`(사유 `snapshot_incomplete`)로 둔다.
- 읽기 호환: 형식 1(현재 전체 행)과 2를 모두 읽는다. 쓰기는 2만 쓴다.

## 5. 롤백 기간·만료 계약 초안

> **현행 계약은 11절(U10-d, 2026-10-16 승인)과 12절(U10-e)입니다. 이 절은 초안으로만 남기며, 11·12절과 다르면 11·12절이 우선합니다.** 기산점(`finished_at` → 최초 `started_at`), 확인 불가 처리(롤백 가능 유지 → 거부), 오류 이름(`rollback_window_closed` 하나 → 11-3의 4개)이 바뀌었습니다.

| 항목 | 권장안 |
| --- | --- |
| 기간 | 30일(5절 후속 기준) |
| 기산점 | apply 실행의 `finished_at`. 진행 중·실패 실행은 그 실행의 마지막 snapshot `created_at` |
| 경계 | 서버 시각 기준 기산점 후 30×24시간 **미만**이면 롤백 가능, **이상**이면 닫힘 |
| 시각 누락·손상·미래 | 만료로 보지 않음(롤백 가능 유지), 정리 대상에서 제외, 도구가 보고 |
| `completed` | 기간 안 롤백 가능 |
| `started`(배치 진행 중·부분 적용) | 적용된 카드만 기간 안 롤백 가능(지금과 같음) |
| `failed` | 적용된 카드만 기간 안 롤백 가능 |
| `aborted` | 이미 롤백된 실행이라 대상 아님(지금과 같음) |
| 롤백 기록의 재전환 용도 | 별도 기간(승인 항목 A6) |

- **권한 만료와 물리 정리 분리**: `rollback_plan`이 호출 시점에 기산점·기간을 계산해 닫힌 실행을 `rollback_window_closed`로 거부한다. 정리 도구를 실행하지 않아도 계약이 같다.
- **`status='expired'`를 쓰지 않는다**
  - `status` CHECK 제약이 거부한다(재현 C). 바꾸려면 스키마를 바꿔야 한다.
  - 더 중요하게, `proven_jump`·`restart_permission`·`_undone_by_completed_rollback`이 `completed`·`started`·`aborted`로 증명을 해석한다. 상태를 바꾸면 이미 성립한 증명이 깨진다.
  - 만료는 상태가 아니라 시각에서 계산한다.
- **다른 실행에 영향 없음**: 기간은 실행별로 계산한다. 정상 복원·B안·평가는 롤백 권한과 무관하게 증명(L)·허가(P) 필드만 읽으므로 막히지 않는다.

## 6. U8 증명·허가 보존
- `proven_jump`가 계속 성립하려면, 증명에 쓰인 롤백 기록·재전환 snapshot의 L 필드와 실행 `mode`·`status`·rollback scope가 남아야 한다(3절). 이를 지우면 다음 평가부터 증거 불완전이 된다(재현 A).
- **허가 구분**
  - 사용됨: `srs_evidence_restarts.source_snapshot_id`가 그 snapshot이다.
  - 미사용: 카드의 최신 apply snapshot에 `restart`가 있고 교체 기록이 없다.
  - 미사용 허가의 P 필드(`restart`, `last_log_id`, `card_version_before`, `srs_after_json`, 실행 상태, 근거 롤백 기록의 존재·상태)는 기간과 무관하게 남긴다. 그러지 않으면 첫 평가를 미룬 B안 카드가 출제되지만 평가는 409가 된다(재현 G).
- **`_was_converted`·최근 전환 탐지**: apply snapshot 행이 하나라도 남아야 한다. 모두 지우면 롤백된 카드가 최초 전환 경로로 가서 이력 재생으로 판정된다(재현 B).
- **오래된 허가 부활 방지**: `restart_permission`은 "가장 최근 apply snapshot"만 본다. 최신 행을 지우면 이전 행이 최신이 되어 오래된 허가가 살아날 수 있다. 따라서 **apply snapshot 행은 지우지 않고 필드만 줄인다**. 롤백 기록 행도 증명이 쓰는 동안 같다.
- **저장 위치 선택지**

| 안 | 내용 | 장점 | 단점·변경 범위 |
| --- | --- | --- | --- |
| A(권장) | 같은 표에 형식 2 최소 행을 남기고, 기간이 지나면 R 필드만 지운다 | 읽는 코드가 그대로(형식 분기만), 순서·id 보존으로 부활 위험 없음 | 표 이름이 "snapshot"인데 증명 저장소 역할을 겸함 |
| B | 별도 `srs_restore_proofs`·`srs_conversion_markers` 표로 L·P를 옮기고 snapshot 행은 기간 뒤 삭제 | 역할 분리, 기간 뒤 snapshot 완전 삭제(D-P4b 문구 그대로) | 스키마 2개 추가, `proven_jump`·`restart_permission`·`_was_converted`·identity 재작성, 이전 작업과 경합 검증 필요 |

- **무기한 보존**: L 필드는 카드가 있는 한 필요하다(증거 구간에 기간이 없음). 내용은 없다(id·버전·SRS 수치·시각·해시). 승인 항목 A2로 둔다.
- 만료된 복구 자료(R)를 되살리거나, 원로그를 고쳐 증명을 대신하지 않는다.

## 7. 삭제·계정·기존 자료
- **카드·덱 삭제**: 그 카드(계정 + 종류 + id)의 snapshot·롤백 기록에서 C 필드만 지운다. 같은 삭제 트랜잭션에서 원값 CAS로 처리한다(U9 영수증과 같은 구조).
  - L 필드는 남긴다. ID 참조 조사가 `card.id`를 쓰고, 삭제 카드의 로그는 남는다.
  - **U9의 "손상 영수증 행 삭제" 예외는 자동 확대하지 않는다.** 손상 snapshot은 승인 항목 A8이다.
- **계정 삭제**
  - 앱에 계정 삭제 경로가 없다(호출처 없음).
  - FK: `srs_migration_snapshots.user_id`는 FK 없음, `srs_migration_runs`는 계정 열 없음(`scope_json` 안), `srs_evidence_restarts`·영수증은 CASCADE.
  - 계정을 지우면 snapshot·실행 기록이 남는다. D-P5(E 단계) 절차에 포함해야 한다(A9).
- **기존 자료(형식 1) 최소화 도구**
  - U9 도구와 같은 계약: 명시 SQLite 파일, 기본 dry-run, 계정 확인, 행별 원값 CAS, id 순 배치·재실행·`--after-id` 재개.
  - 손상·알 수 없는 형식은 보고만 한다. 보고에는 id·필드 이름·사유만 남기고, 원문을 파일·로그·백업에 복제하지 않는다.
  - 형식 1 → 2 변환 전후로 롤백 결과(예약·레벨·`srs_*`·완료 이력)가 같아야 한다(P12).

## 8. 승인 항목

| # | 결정 | 권장안 | 대안 | 사용자 영향 |
| --- | --- | --- | --- | --- |
| A1 | 최소 필드 | 4절 형식 2 | D-P4a 원안 그대로 | 없음(내부) |
| A2 | D-P4b "snapshot을 지운다"의 수정 | 기간 뒤 R 필드만 지우고 L·P는 카드가 있는 동안 보존(내용 없음) | 별도 증명 표(6절 B안) 뒤 snapshot 삭제 | 없음. 원안대로 지우면 복원·B안 카드의 증거가 불완전해지거나 평가가 409가 됨 |
| A3 | 기산점·경계 | apply `finished_at`(진행 중·실패는 마지막 snapshot), 30×24시간 미만 가능 | `started_at` / 카드별 snapshot 시각 | 전환 30일 뒤 그 전환은 되돌릴 수 없음 |
| A4 | 상태별 규칙 | 5절 표 | - | - |
| A5 | 시각 이상 | 만료로 보지 않고 보고 | 롤백 차단 | 운영자 확인 필요 |
| A6 | 롤백 기록의 재전환 용도 기간 | 기간 없음(복원 필드는 R이지만 재전환 판정에 계속 필요, 내용 없음) | 30일 뒤 R 제거 → 그 카드는 변경 카드처럼 상태 없음/B안 | 권장안: 오래 legacy로 둔 카드도 FSRS 상태를 되찾음 |
| A7 | 증명 저장 위치 | 같은 표(6절 A안) | 별도 표(B안) | 없음 |
| A8 | 손상 snapshot이 있는 카드 삭제 | 그 카드의 손상 snapshot 행 삭제 후 진행(카드 삭제 전용) | 삭제 차단 / 손상 원문 유지 | 권장안: 삭제가 막히지 않음 |
| A9 | 계정 삭제 시 snapshot·실행 기록 | D-P5에 포함(전부 삭제) | 익명 보존 | E 단계 |
| A10 | 롤백 필수 필드 검증(결함) | 4절대로 보정 | - | 없음(손상 snapshot이 조용히 잘못 롤백되지 않음) |

## 9. 계약 보정 (2026-10-14 지시, U10-c0·U10-a 착수와 함께)

### 9-1. A3·A4: 기산점과 부분 실행
- **기산점은 apply 실행의 `started_at`**으로 바꾼다(8절 A3의 `finished_at` 권장을 대체).
  - `started_at`은 실행을 만들 때 한 번 쓰이고 재개·완료로 바뀌지 않는다. 재개나 완료 시각 갱신이 만료된 롤백 권한을 다시 여는 일이 없다.
  - 대가: 긴 배치 실행의 뒤쪽 카드는 롤백 기간이 그만큼 짧다.
- **만료된 부분 실행(`started`·`failed`)은 같은 `run_key`로 재개하지 않는다.** `apply_plan`이 그 키를 거부하고(U10-d에서 구현, 오류 코드는 그때 정함), 남은 카드는 새 계획·새 실행으로 진행한다.
- **완료된 작업의 같은 키 재호출과 실제 재개를 구분한다.** 완료된 apply·rollback 키를 다시 부르면 저장된 결과만 돌려준다. 쓰기는 없고 만료와 무관하다(지금 동작 유지). 기간이 지난 실행에 쓰기가 생기는 재개는 거부한다.

### 9-2. A5: 기산 시각 확인 불가
- `started_at`이 없거나 해석 불가이거나 서버 시각보다 미래면 **확인 불가**다.
- 그 실행의 롤백은 거부하고, 기간 후 정리에서도 제외한 뒤 보고한다. 만료로 추정하거나 날짜를 보정하지 않는다(8절 A5의 "롤백 가능 유지" 권장을 대체).

### 9-3. A2·A6: 기간 후 제거 필드 (필드별, R이라는 분류만으로 일괄 제거하지 않음)

| 기록 | 필드 | 기간 후 | 근거 |
| --- | --- | --- | --- |
| apply snapshot | `card.review_level`, `next_review_at`, `completion_metric_version`, `first_completed_at` | 제거 | 롤백만 읽음(`_rollback_input`) |
| apply snapshot | `card.srs_*` 중 `srs_engine`을 뺀 12개(설정·상태 6열·유효 예정·참여·중지 사유·품질·플래그) | 제거 | 롤백만 읽음 |
| apply snapshot | `card.srs_engine`, `card.srs_card_version` | 보존 | `proven_jump`(재전환 직전 legacy·버전) |
| apply snapshot | `card.id`, `card.lexeme_id`, `card.created_at` | 보존 | ID 참조·식별 검사 |
| apply snapshot | `last_log_id`, `restart`, 열 `card_version_before`, 열 `srs_after_json` | 보존 | 증명·허가 |
| rollback 기록 | `srs_before_json`, `baseline` 4키, 열 `card_version_before`, `card.id`·`created_at` | 보존 | 재전환 복원(A6: 기간 없음)·증명·식별 |
| rollback 기록 | 열 `srs_after_json`(롤백이 쓴 값) | 제거 가능 | 어떤 코드도 읽지 않음(내용 없음) |
| 실행(apply) | `scope_json.cards[]`의 `card`·`logs`(지문)·`values`·`flags`·`quality`·`version`·`last_log_id` | 제거 | 같은 키 재개 비교에만 쓰임, 만료 실행은 재개 금지(9-1) |
| 실행(apply) | `scope_json.cards[]`의 `kind`·`ref_id`, `user_id` | 보존 | ID 참조(`identity._run_ids`)·계정 확인 |
| 실행 | `summary_json`(커서·결과), `mode`, `status`, `config_version`, 시각 | 보존 | 같은 키 재호출 결과, ID 참조, 증명 해석 |
| 경계 교체 기록 | 전부 | 보존 | 증명·사용 이력 |

- 미사용 B안 허가가 걸린 apply snapshot(카드의 최신 apply 기록에 `restart`가 있고 교체 기록이 없음)은 위 "제거"도 하지 않는다. 그 카드가 첫 평가 전에 다시 롤백될 수 있기 때문이다.
- 실제 제거는 U10-e에서 구현한다. 이번에는 문서에만 반영한다.

### 9-4. A8 확정
- 사용자가 확정 삭제하는 개인 카드의 손상·미지원 snapshot 행 삭제만 허용한다(U10-a에서 구현, `migration.strip_card_snapshots`). 일반 정리 도구에는 확대하지 않는다.

### 9-5. U10-a 구현과의 차이
- 4절 제안과 달리 rollback 기록의 `srs_after_json`은 그대로 쓴다. 내용이 없고 정리는 U10-e 범위다.
- 롤백이 복원하는 엔진 열은 형식과 무관하게 `RESTORE_REQUIRED` 13열로 고정했다. 형식 1에서도 결과는 같다.

## 10. U10-c0·a 검토 보정 (2026-10-15)

### 10-1. 기산점의 지위
- 9-1의 `started_at` 기산점은 **문서상의 정책안**이다. U10-d 착수 전에 승인받을 항목(A3')으로 남긴다. 아직 어떤 코드도 기간을 계산하지 않는다.

### 10-2. 기록 종류별 허용 구조 (`migration._record_shape`, `_srs_columns_shape`)

| 기록 | 형식 | 최상위 키 | `card` 키 |
| --- | --- | --- | --- |
| apply | 1 | `card`, `last_log_id`, 선택 `restart` | 카드 표의 열 이름만(개인 `vocab_items`, 구독 `user_word_progress`) |
| apply | 2 | `format`(=2), `card`, `last_log_id`, 선택 `restart` | `APPLY_CARD_FIELDS[종류]`만 |
| rollback | 1 | `card`, `baseline` | 카드 표의 열 이름만 |
| rollback | 2 | `format`(=2), `card`, `baseline` | `ROLLBACK_CARD_FIELDS[종류]`만 |

- **공통 조건**
  - `card`의 식별값이 기록의 `card_ref`와 같아야 한다(개인 `id`, 구독 `lexeme_id`).
  - `last_log_id`는 0 이상 정수다.
  - `restart`는 정확히 `previous_boundary`·`rollback_record_id` 두 키이고 둘 다 0 이상 정수다.
  - `baseline`은 정확히 4키다: `card_version`·`last_log_id`는 0 이상 정수, 지문 2개는 문자열.
- **SRS JSON 열**
  - apply: `srs_before_json`은 JSON null, `srs_after_json`은 `srs_*` 13열 + `completion_metric_version`·`first_completed_at` 안의 키만.
  - rollback: `srs_before_json`은 정확히 13열, `srs_after_json`은 13열 + 롤백 입력 4키 안의 키만.
- **정상 기록 재구성**: 삭제 경로에서 정상 기록은 허용 필드만으로 **새 객체**를 만든다. 알 수 없는 키는 옮기지 않고, 값은 그대로 둔다. `format: 2` 표시가 있어도 구조가 위와 정확히 같아야 "이미 최소"로 본다.
- **미지원 구조**: 어떤 조건이든 어긋나면 미지원이다.
  - 사용자가 확정 삭제하는 카드에서만 그 행을 삭제한다(A8).
  - 롤백에서는 `blocked`(`snapshot_incomplete`)이고 쓰지 않는다.
  - 조회·재전환 판정·일반 정리에서는 삭제하거나 복구하지 않는다.

### 10-3. 롤백이 복원하는 값의 검증 (`migration._restorable`)

| 값 | 허용 |
| --- | --- |
| `review_level` | 0 이상 정수(불리언 아님) |
| `next_review_at`, `first_completed_at` | NULL 또는 시간대 있는 실제 시각(Z·+hh:mm·−hh:mm 모두 같은 순간이면 정상) |
| `completion_metric_version` | NULL 또는 비지 않은 문자열 |
| `srs_engine` | `legacy`(전환 전 카드) |
| `srs_config_version` | NULL 또는 비지 않은 문자열 |
| `srs_state` | NULL 또는 1·2·3 |
| `srs_step` | NULL 또는 0 이상 정수 |
| `srs_stability`, `srs_difficulty` | NULL 또는 유한한 수(불리언·문자열·NaN·무한 아님) |
| `srs_due_at`, `srs_last_review_at`, `srs_effective_due_at` | NULL 또는 시간대 있는 실제 시각 |
| `srs_participation` | NULL, `active`, `paused` |
| `srs_pause_reason` | NULL 또는 문자열 |
| `srs_history_quality` | NULL, `complete`, `incomplete`, `fresh` |
| `srs_history_flags` | NULL 또는 문자열 목록을 담은 JSON 텍스트 |
| `srs_card_version`(있을 때) | 0 이상 정수 |

- 전환 전 카드는 legacy이므로 "엔진 상태가 모두 있어야 한다" 같은 FSRS 카드 조건은 요구하지 않는다.
- 키 누락은 차단, 열이 허용하는 NULL은 통과다. 손상 값을 추정·기본값·형 변환으로 고치지 않는다.
- DB 제약이나 바인딩 오류보다 먼저, 카드를 쓰기 전에 판정한다.

### 10-4. 값의 타입·중첩 구조 (2026-10-15 보정)
- 10-2의 키 판정에 더해, 남기는 모든 값이 필드별 값 계약(`migration._FIELD_OK`, REPORT 29-2 표)을 지켜야 정상 기록이다. 스칼라 자리의 객체·배열·자유 문장은 미지원이다.
- SRS JSON 열은 열마다 의미가 다르다: apply 결과는 `fsrs`, rollback 직전 투영은 `fsrs`, rollback이 쓴 투영은 `legacy`. apply `card`는 전환 전 legacy 카드다.
- 재구성 갱신의 원값 CAS는 판정에 쓴 `legacy_json`·`srs_before_json`·`srs_after_json`을 모두 비교한다.

### 10-5. 지문 형식 (2026-10-15 보정)
- rollback 기록 `baseline.card_fingerprint`·`logs_fingerprint`는 생성 코드(`hexdigest`)와 같은 소문자 16진수 64자리만 정상이다. 대문자·다른 길이·문장·비문자열은 미지원이다(삭제 경로에서 A8, 롤백 입력에는 해당 없음).

## 11. U10-d 롤백 기간(논리 만료) 확정 계약 (2026-10-16)

### 11-1. 승인 근거
- 2026-10-16 사용자 승인(A3'): "롤백 기간은 apply 실행의 최초 `started_at`부터 30×24시간". 정각부터 만료이고, 재개·완료로 연장하지 않는다.
- 기산 시각 누락·손상·시간대 없음·미래 시각은 확인 불가로 구분하고, 새로운 롤백·재개를 쓰기 전에 거부한다.
- 완료된 같은 키의 재호출은 기존 계약대로 저장 결과만 반환하고 쓰지 않는다.
- 이 절은 5절 초안의 기산점(`finished_at`)과 9-2 이전의 "확인 불가는 롤백 가능 유지" 권장을 대체한다.

### 11-2. 기간 판정 (`migration.rollback_window(started_at, now)`)
- 입력은 apply 실행 행의 `started_at` 원문과 서버 시각(`now_utc()`, UTC 순간)이다. 서울 날짜·문자열 순서로 비교하지 않는다.
- `started_at`은 `goals.read_utc`로 읽는다. 시간대가 있는 ISO 8601만 읽으며(`Z`, `+hh:mm`, `-hh:mm`), 같은 UTC 순간이면 표기와 무관하게 같은 결과다.

| `started_at` | 판정 |
| --- | --- |
| 읽을 수 있고 `now - started < 30×24시간` | `open`(기간 내) |
| 읽을 수 있고 `now - started >= 30×24시간` (정각 포함) | `expired` |
| NULL·빈 값·문자열 아님·해석 불가·시간대 없음 | `unverifiable` |
| 읽을 수 있지만 `now`보다 미래 | `unverifiable` |

- 판정은 계산만 한다. 만료로 추정하거나 시각을 보정하지 않는다. 실행 행의 `status`·`started_at`·`finished_at`은 바꾸지 않고, `status='expired'`도 추가하지 않는다.
- snapshot·실행 기록·증명·허가 필드는 지우지 않는다. 물리 정리는 U10-e다.

### 11-3. 오류 계약 (모두 새 코드, `SrsWriteError`, HTTP 상태 409, 운영 함수 전용)

| 코드 | 언제 |
| --- | --- |
| `rollback_window_closed` | 새 롤백 키인데 원본 apply 실행이 `expired` |
| `rollback_window_unverifiable` | 새 롤백 키인데 원본 apply 실행이 `unverifiable` |
| `migration_resume_window_closed` | 같은 키 apply 재개에 남은 카드가 있는데 실행이 `expired`. 재개 중 카드 단위 재확인에서 만료된 경우도 같다 |
| `migration_resume_window_unverifiable` | 같은 경우인데 실행이 `unverifiable` |

- 기존 코드(`migration_run_conflict`, `migration_run_closed`, `migration_run_not_found`, `migration_cursor_conflict` 등)의 의미는 바꾸지 않는다.
- 판정 순서: 키 형식 → 원본·계정 확인 → 같은 키의 기존 실행이면 요청 일치 확인(`migration_run_conflict`) → 완료면 저장 결과 반환 → 그 뒤에만 기간 판정.
  - 그래서 다른 요청의 키 재사용은 기간과 무관하게 계속 `migration_run_conflict`다.

### 11-4. 상태별 처리

| 호출 | 실행 상태 | 기간 내 | 만료·확인 불가 |
| --- | --- | --- | --- |
| 같은 키 롤백 재호출 | 롤백 `completed` | 저장 결과, 쓰기 0 | 저장 결과, 쓰기 0 |
| 새 키 롤백 | 원본 `completed`·`started`·`failed`·`aborted` | 지금과 같음(적용된 카드만 대상, 원본은 `aborted`로 바뀜) | 거부, 쓰기 0 |
| 같은 키 apply 재호출 | `completed`(남은 카드 없음) | 저장 결과, 쓰기 0 | 저장 결과, 쓰기 0 |
| 같은 키 apply 재개 | `started`·`failed`, 남은 카드 있음 | 지금과 같이 재개 | 거부, 쓰기 0. 커밋된 카드는 그대로 |
| 같은 키 apply | `started`·`failed`, 남은 카드 없음 | 저장 결과, 쓰기 0(지금과 같음) | 저장 결과, 쓰기 0 |
| 같은 키 apply | `aborted` | `migration_run_closed`(지금과 같음) | 같음 |
| 새 키 apply | 없음 | 새 실행, `started_at`=지금 | 해당 없음 |

- 롤백 실행은 한 트랜잭션으로 만들고 완료하므로, 롤백 키에는 `completed` 외 상태가 남지 않는다.
- 남은 카드는 운영자가 새 계획·새 키로 처리한다. 자동 실행·자동 이전은 없다.

### 11-5. 실제 쓰기 단위와 재확인
- **롤백**: 계정 쓰기 잠금 1회 안의 한 트랜잭션이다. 잠금을 얻은 뒤 서버 시각을 한 번 읽어 기간을 판정하고, 같은 시각을 실행 행·기록 시각에 쓴다. 잠금 대기 중 만료됐으면 거부되고 아무것도 쓰지 않는다.
- **apply**: 실행 확인 트랜잭션 1개 + 카드 1장마다 트랜잭션 1개 + 완료 표시 1개.
  - 실행 확인: 잠금 뒤 서버 시각으로 판정한다. 재개 거부면 실행 행을 만들거나 바꾸지 않는다.
  - 카드 단위: 매번 잠금을 얻은 뒤 서버 시각을 한 번 읽어 다시 판정하고, 그 카드의 설정·기록 시각에 같은 시각을 쓴다. 만료됐으면 그 카드부터 쓰지 않고 오류를 낸다. 이때 실행을 `failed`로 바꾸지 않는다. 앞서 커밋된 카드는 되돌리지 않는다.
  - 완료 표시: 모든 카드가 이미 커밋된 뒤의 상태 기록이라 기간과 무관하다. 기간을 연장하지 않는다.
- 판정에 쓰는 시각은 서버 시각뿐이다. 호출자가 넘긴 시각은 쓰지 않는다.

### 11-6. 영향 없는 것
- 정상 재전환 복원과 B안 허가는 원본 apply의 롤백 만료로 무효화하지 않는다. 재전환은 새 apply 실행이고, 복원·허가·증명은 기록의 증명(L)·허가(P) 필드만 읽는다. 오래된 미사용 허가도 폐기하지 않는다.
- 평가 경로, 다른 실행·계정의 롤백, legacy 동작은 바뀌지 않는다.
- `aborted` 원본의 새 키 롤백은 지금 코드가 막지 않는다(5절 초안 표의 "대상 아님"과 다름). U10-d는 그 동작을 바꾸지 않고 기간만 더한다.

## 12. U10-e 기간 후 롤백 전용 필드 정리 (2026-10-16, 구현 전 고정)

### 12-1. 실제 읽기 경로 대조 (기간이 지난 apply 실행 기준)
| 읽는 곳 | 읽는 값 | 기간 후에도 필요 |
| --- | --- | --- |
| `rollback_plan` → `_rollback_input`·`_restorable` | apply 기록 `card`의 복원 입력 4개 + `srs_*` 13개 | 아니오. 11절 기간 판정이 기록을 읽기 전에 거부 |
| `restoration.proven_jump` | apply 기록 `card.srs_engine`·`card.srs_card_version`·`last_log_id`, 열 `srs_after_json`·`card_version_before`, 실행 `status` | 예 |
| `restoration.restart_permission` | 최신 apply 기록 `restart`·`last_log_id`, 열 `srs_after_json`·`card_version_before`, 실행 `status` | 예 |
| `identity._snapshot_ids`·`scan_identity` | 기록 `card.id`·`card.created_at`, 열 `created_at` | 예 |
| `identity._run_ids` | 실행 `scope_json.user_id`·`cards[].kind`·`cards[].ref_id`, `summary_json` | 예 |
| `rollback_plan` | 원본 실행 `scope_json.user_id` | 예 |
| `_run_id` (같은 키 요청 일치) | 실행 `scope_json` **원문 전체**를 새 요청과 문자열 비교 | 예. 아래 12-3 |
| U10-b 도구, 확정 삭제(`strip_card_snapshots`) | 공용 판정 `_record_shape` | 예. 정리된 기록을 정상으로 읽어야 함(12-4) |

### 12-2. 제거·보존 필드
| 기록 | 필드 | U10-e |
| --- | --- | --- |
| apply snapshot `card` | `review_level`, `next_review_at`, `completion_metric_version`, `first_completed_at` | 제거 |
| apply snapshot `card` | `srs_config_version`, `srs_state`, `srs_step`, `srs_stability`, `srs_difficulty`, `srs_due_at`, `srs_last_review_at`, `srs_effective_due_at`, `srs_participation`, `srs_pause_reason`, `srs_history_quality`, `srs_history_flags` (명시 12개) | 제거 |
| apply snapshot `card` | `id`, `lexeme_id`(구독), `created_at`, `srs_card_version`, `srs_engine` | 보존 |
| apply snapshot | `last_log_id`, `restart`, 열 `card_version_before`·`srs_before_json`·`srs_after_json`·`history_*`·`created_at` | 보존 |
| apply 실행 `scope_json.cards[]` | `card`, `logs`, `values`, `flags`, `quality`, `version`, `last_log_id` | 제거(요청 식별은 12-3의 해시로 보존) |
| apply 실행 | `scope_json.user_id`·`config_version`·`cards[].kind`·`ref_id`, `summary_json`, `mode`, `status`, `config_version`, 모든 시각, `run_key` | 보존 |
| rollback 기록 | `srs_before_json`, `baseline`, `card.id`·`lexeme_id`·`created_at`, 열 전부 | 보존(기간 없음, A6) |
| rollback 기록 | 열 `srs_after_json`(롤백이 쓴 값) | **이번에는 보존.** 9-3은 "제거 가능"이지만 rollback 기록에는 기간이 없어(A6) 정리 시점이 정해지지 않았다. 시점을 정하는 것은 별도 승인 항목이다 |
| rollback 실행, 경계 교체 기록(`srs_evidence_restarts`) | 전부 | 보존 |

- `srs_*`를 일괄로 지우지 않는다. 위 명시 목록만 지운다.
- 행 삭제, `status` 변경·`'expired'`, 시각 갱신, 카드·로그·완료 기록 변경은 없다.

### 12-3. 실행 `scope_json` 축소와 요청 식별 보존
- 축소 형식:
  ```
  {"format": 2, "user_id": <int>, "config_version": <str>,
   "cards": [{"kind": ..., "ref_id": ...}, ...],          # 원래 순서 그대로
   "request_sha256": sha256(원래 scope_json 원문 UTF-8)}  # 소문자 16진수 64자리
  ```
- 읽기 호환(`_run_id`): 저장값이 원문이면 지금처럼 문자열 비교한다. 저장값이 축소 형식이면 새 요청의 `scope_json` 원문 해시를 `request_sha256`과 비교한다. 원문이 같으면 해시가 같으므로, 완료된 키 재호출(저장 결과 반환, 쓰기 0)과 다른 요청의 키 재사용(`migration_run_conflict`) 판별이 정리 전후 같다.
  - `mode`·`config_version` 비교, `aborted` 거부, 11절 기간 판정 순서는 바뀌지 않는다.
- 축소는 원문이 정확히 `{user_id, config_version, cards}` 구조이고 각 카드 항목이 알려진 9개 키만 가질 때만 한다. 그 밖의 구조는 원값을 그대로 두고 `unsupported_scope`로 보고한다.

### 12-4. 정리된 apply 기록 형식(형식 3)과 읽기 호환
- 형식: `{"format": 3, "card": {id, [lexeme_id], created_at, srs_card_version, srs_engine}, "last_log_id": <int>, ["restart": {...}]}`.
- 공용 판정 `_record_shape`가 apply 기록의 형식 3을 정상으로 읽는다. 다섯(구독은 여섯) 필드가 **모두** 있어야 하고 값 계약은 기존 `_FIELD_OK`(apply 카드의 `srs_engine`은 `legacy`)를 그대로 쓴다. rollback 기록의 형식 3은 미지원이다.
  - 결과: U10-b 도구는 "이미 최소"로, 확정 삭제는 "정상 최소 구조"로 보고 그대로 둔다(A8 대상 아님).
  - 롤백 입력(`_restorable`)은 형식 3을 복원 불가로 본다. 다만 11절 기간 판정이 먼저 거부하므로 그 경로에 도달하지 않는다. 서버 시각이 거꾸로 가는 등으로 도달하더라도 `snapshot_incomplete` 차단이지 잘못된 복원이 아니다.
- 손상·미지원·형식 1·2인데 보존 필드나 복원 입력이 빠진 기록(증거 부족)은 형식 3으로 만들지 않는다. 원값 유지, 사유 보고.

### 12-5. 대상과 보호
- 대상: 지정 계정의 apply 실행 중 11절 `rollback_window`가 `expired`인 것. `open`은 건너뛰고, `unverifiable`은 원값 유지·정리 제외·보고한다.
- 보호(정리 제외·보고): 카드의 **최신** apply 기록에 `restart`가 있고 `srs_evidence_restarts`에 그 기록을 쓴 행이 없으면(미사용 B안 허가) 그 기록은 줄이지 않는다. 그 기록의 실행(부모)은 `scope_json`도 줄이지 않는다(보수적 보호).
  - 이미 쓰였거나 최신이 아닌 옛 허가의 `restart`는 지우지 않는다(보존 필드). `restart_permission`은 최신 기록만 보므로 정리로 옛 허가가 되살아나지 않는다.

### 12-6. 도구 실행 계약 (`scripts/d2_snapshot_prune.py` → `migration.prune_expired_runs`)
- U10-b와 같은 안전장치: 명시한 기존 `.db`만, 기본 읽기 전용 dry-run, `--apply`와 같은 값의 `--confirm-user-id`, DB 생성·`init_db`·기본 DB 대체·PostgreSQL 없음.
- 단위: apply 실행 id 순. 시작 시 최대 실행 id를 상한으로 고정한다. 한 배치(기본 50실행) = 잠금 1회·트랜잭션 1개. 배치 안에서 실행마다 잠금 뒤 서버 시각 한 번으로 기간을 판정하고, 보호·대상 상태를 다시 판정한다.
- 쓰기: 판정한 원값 전체를 CAS로 비교한다. snapshot은 `legacy_json`·`srs_before_json`·`srs_after_json`과 부모 실행 `started_at`, 실행은 `scope_json`·`started_at`. 불일치는 덮어쓰지 않고 충돌로 보고하며, 다음 실행이 다시 판정한다.
- 실패하면 그 배치 전체를 롤백한다. 커서는 커밋 뒤에만 전진한다. 실행 전체는 배치 단위로만 원자적이다. 재실행은 멱등(형식 3·축소 scope는 "이미 정리")이다.
- 보고: 실행·기록 id, 종류, 필드·키 이름, 사유, 집계, 커서·상한만. 원문·뜻·예문·JSON 값은 출력·백업하지 않는다.

### 12-7. 실행 scope 값 계약 (2026-10-17 보정, `_full_scope`·`_reduced_scope`)
기준은 `_plan_json`과 `inspect_card`의 실제 후보입니다. 키 이름만이 아니라 값의 타입·허용값·중첩 구조를 봅니다.

| 위치 | 원본 scope | 축소 scope |
| --- | --- | --- |
| 최상위 키 | 정확히 `user_id`, `config_version`, `cards` | 정확히 `format`(=2), `user_id`, `config_version`, `cards`, `request_sha256` |
| `user_id` | 양의 정수(불리언 아님) | 같음 |
| `config_version` | 토큰(`[A-Za-z0-9_.:-]{1,64}`)이고 **부모 실행 행의 `config_version`과 같음** | 같음 |
| `cards` | 비어 있지 않은 목록, `(kind, ref_id)` 중복 없음 | 같음 |
| `cards[].kind` / `ref_id` | `personal`·`lexeme` / 양의 정수 | 같음, 카드 항목 키는 이 둘뿐 |
| `cards[].card` / `version` | 소문자 SHA-256 64자리 / 0 이상 정수. 둘 다 NULL은 카드가 없는 `unavailable` 후보만 | 없음 |
| `cards[].logs` | 소문자 SHA-256 64자리 | 없음 |
| `cards[].quality` | `complete`·`incomplete`·`fresh`(이력 판정) 또는 `unavailable`·`already_fsrs`·`identity_unknown`·`reconvert_blocked` | 없음 |
| `cards[].flags` | 토큰 목록(빈 목록 허용) | 없음 |
| `cards[].last_log_id` | 0 이상 정수 | 없음 |
| `cards[].values` | NULL 또는 JSON 텍스트. 텍스트는 apply 기록 `srs_after_json` 계약과 같습니다: 알려진 열 이름만, `srs_engine`=`fsrs`, `srs_config_version`=scope 설정, 열별 값 규칙(`_fields_ok`). 상태 없음(NULL 상태)도 정상. 이력 판정 품질에서만 값이 있고, 차단 4종은 NULL | 없음 |
| `request_sha256` | 없음 | 소문자 SHA-256 64자리 |

- NULL `values`(차단·`incomplete` 차단·`unavailable`)와 상태 없음 전환(U5·B안)은 정상입니다. 모든 후보에 완전한 FSRS 상태를 요구하지 않습니다.
- 판정은 예외 없이 참·거짓으로 끝납니다. 저장 자료 판정에 `assert`를 쓰지 않으므로 `python -O`에서도 같습니다. 값을 추정·변환·기본값으로 고치지 않고, 손상 원문을 해시로 바꿔 정상화하지 않습니다.
- 실행마다 scope를 **연결 기록보다 먼저** 판정합니다. 원본·축소 모두 아니면 그 실행의 scope와 모든 apply 기록을 원값 그대로 두고 `unsupported_scope`만 보고한 뒤 다음 실행으로 갑니다. 축소 결과가 재판정을 통과하지 못해도 같습니다(`reduction_unverified`).
- 같은 키 호출(`_run_id`)의 축소 scope 판정도 같은 함수(부모 실행 설정 포함)를 씁니다. 손상된 축소 scope는 요청을 식별하지 못하므로 `migration_run_conflict`입니다(새 오류 없음).

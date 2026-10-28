# U11 B안 설계: V3 서버 판정과 최초 완료 출처 보존 (2026-10-17, 검토 대기)

제품 코드·스키마는 바꾸지 않았다. 실제 자료에는 접근하지 않았다. 이 문서는 구현 전에 검토받을 저장 계약이다.

## 0. 확정 범위 (2026-10-17 사용자 승인)
- V3 `meaning-completion-v1`: Review 상태, S ≥ 30일, 마지막 Again 이후 성공(hard·good·easy) 서울 날짜 3개 이상, 그 성공 중 직전 실제 평가와 UTC 7×24시간 이상 떨어진 것 2회 이상.
- 새 실제 FSRS 평가에서만 서버가 판정한다. 조회·앱 시작·이전 도구는 소급 완료·백필을 만들지 않는다.
- 완료 수치·완료 ETA는 화면에 노출하지 않는다(D-C2 유지).
- 기존 최초 완료 시각·draft 기록·영수증은 보존한다. 출처 보존은 B안(별도 저장)이다.

## 1. 조사 결과: 완료 값이 쓰이고 읽히는 곳

| 경로 | 지금 동작 | B안에서 |
| --- | --- | --- |
| FSRS 평가 `reviews.record_fsrs_review` (개인·구독, 구독 첫 평가 포함 **유일한 평가 쓰기 지점**) | 카드 `completion_metric_version` = 이번 판정 버전으로 덮어씀. `first_completed_at` = 기존 값, 없고 완료면 이번 평가 시각 | 2절 규칙으로 새 열을 같은 트랜잭션에서 씀 |
| 평가 응답·영수증 | `completed`, `completion_metric_version`(현재 판정), `srs.completion_status`, `srs.needs_relearning`, `srs.first_completed_at` | 3-3 |
| 전환 `migration.inspect_card`(완전한 legacy 이력) | legacy 이력을 재생해 `first_completed_at`을 만들고 `completion_metric_version`=draft를 씀(161~171행) | **소급 완료 금지**: 전환은 완료 값을 쓰지 않음(4-1) |
| 불완전 전환·B안 재전환(`_incomplete_candidate`) | 완료 값을 쓰지 않음 | 그대로 |
| 정상 복원 재전환(`_reconvert_candidate`) | `RESTORE_REQUIRED` 13열만 씀(완료 값 없음) | 그대로 |
| 롤백 `rollback_plan` | `completion_metric_version`·`first_completed_at` = 카드 값 또는 snapshot 값(`card or before`) | 새 열은 쓰지 않음(롤백 보존 열) |
| B안 증거 재시작 `_restart_evidence_boundary` | `evidence_from_log_id`만 씀 | 그대로. 새 구간은 V3 판정 증거만 바꾸고 완료 이력은 건드리지 않음 |
| U10 snapshot(형식 2·3), U10-b 최소화, U10-e 정리 | 고정 필드 목록(`APPLY_CARD_FIELDS`, `PRUNED_APPLY_CARD_FIELDS`)만 다룸. 새 열은 목록에 없음 | 새 열은 snapshot에 들어가지도, 지워지지도 않음(4-3) |
| 카드·덱 삭제 | 행과 함께 사라짐. 삭제 원장은 U4 학습 표시만 복사 | 그대로(새 열은 원장에 복사하지 않음) |
| legacy 계정 평가(`vocab_repository`·`lexeme_repository` legacy 경로) | 완료 값을 쓰지 않음 | 그대로 |
| 화면(프론트) | 완료 값을 읽지 않음 | 그대로(노출 없음 점검을 검사표에 포함) |

## 2. 최소 구조 제안

### 2-1. 열 (카드 두 표 `vocab_items`, `user_word_progress`에 같은 3개, 모두 NULL 허용 TEXT)

| 열 | 뜻 | 쓰는 곳·시점 |
| --- | --- | --- |
| `completion_metric_version` (기존) | **현재 판정 버전**: 마지막 FSRS 평가가 쓴 판정 기준. 뜻 유지 | 평가마다(지금과 같음) |
| `first_completed_at` (기존) | **최초 완료 이력**: 어떤 기준이든 처음 완료로 기록된 시각. 지우지 않음. 뜻 유지 | NULL일 때 첫 완료 평가에서 한 번 |
| `first_completed_source` (신규) | `first_completed_at`의 출처: 그 완료를 만든 판정 버전 토큰, 또는 예약값 `source_missing`·`source_unknown` | `first_completed_at`을 처음 쓸 때 같은 값으로 한 번. 기존 자료는 3-2의 "출처 고정"에서 한 번 |
| `version_first_completed_at` (신규) | **현재 기준의 최초 완료**: `version_first_completed_version` 기준으로 처음 완료된 평가 시각 | 그 기준으로 처음 완료된 평가에서 한 번 |
| `version_first_completed_version` (신규) | 위 시각의 판정 버전 | 위와 같은 쓰기 |

- 과거 최초 완료와 현재 버전의 최초 완료를 다른 열에 둔다. 그래서 draft 완료가 V3 완료로 바뀌어 보이는 일이 없다.
- 예약값 두 개는 `[A-Za-z0-9_.:-]` 토큰이지만 판정 버전 이름으로는 쓰지 않는다(`meaning-completion-` 접두가 없음).
- 다음 기준(V4)이 생기면 `version_first_completed_*` 쌍은 V4 첫 완료 때 V4로 바뀐다. 그 시점에 V3 첫 완료 시각을 따로 남길지는 V4 설계에서 정한다(이번 범위 밖, 열린 항목 7-3).

### 2-2. 대안과 고르지 않은 이유
- 버전별 이력 표(카드·버전마다 한 행): 여러 기준을 모두 남길 수 있지만 표·삭제 연동·식별 검사·PG 이전이 더 커진다. 지금 필요한 건 draft와 V3 두 개뿐이라 열 3개로 충분하다.
- `first_completed_source`만 추가: draft 최초 완료가 있는 카드가 V3를 충족한 시각을 남길 곳이 없다(요구 2 불충족).

## 3. 판정·기록 계약

### 3-1. 평가 한 번의 처리 (모두 평가 트랜잭션 안, 계정 쓰기 잠금 + 카드 버전 CAS)
1. 영수증이 있으면 저장된 응답을 그대로 돌려준다(아래 단계 없음, 기준 변경 전후 무관).
2. V3로 현재 상태를 판정한다(기존 U7 경계·B안 재시작·엔진 재생 검증·로그 연결·버전 공백 증명을 그대로 거친 증거만).
3. **출처 고정**: `first_completed_at`이 있고 `first_completed_source`가 NULL이면, `completion_metric_version`을 덮어쓰기 **전에** 3-2 표로 출처를 정해 한 번 쓴다.
4. `completion_metric_version` = V3.
5. 판정이 COMPLETED면:
   - `first_completed_at`이 NULL이면 이번 평가 시각과 `first_completed_source`=V3를 쓴다.
   - `version_first_completed_version`이 V3가 아니거나 NULL이면 `version_first_completed_at`=이번 평가 시각, `version_first_completed_version`=V3를 쓴다.
6. `needs_relearning` = `version_first_completed_version`=V3이고 `version_first_completed_at`이 있으며 이번 판정이 NOT_COMPLETED. UNKNOWN(불완전 증거)은 재학습으로 보지 않는다(지금과 같음).
- 같은 평가에서 2~6을 계산하고 `update_card`(버전 CAS) 한 번으로 쓴다. 쓰기 전 카드 행은 잠금 아래에서 읽은 값이다. 동시 평가는 잠금으로 직렬화되고, 늦은 쪽은 CAS로 409가 된다. 그래서 출처·최초 완료가 두 번 쓰이거나 덮이지 않는다.

### 3-2. 기존 자료의 출처 (백필 없음, 다음 실제 평가에서만 한 번 고정)

| 기존 카드 상태 (U11 반영 전 값) | 분류 | `first_completed_source`에 쓰는 값 |
| --- | --- | --- |
| `first_completed_at` NULL | 최초 완료 없음 | 쓰지 않음(NULL 유지) |
| `first_completed_at`이 읽을 수 있는 시각 + `completion_metric_version` = `meaning-completion-v1-draft` | **확인됨** | `meaning-completion-v1-draft` |
| `first_completed_at`이 읽을 수 있는 시각 + `completion_metric_version` NULL | **누락됨** | `source_missing` |
| `first_completed_at`이 읽을 수 없거나, 버전이 draft가 아닌 다른 값 | **알 수 없음** | `source_unknown` |

- "확인됨"의 근거: U11 전에 완료를 쓴 판정은 draft 하나뿐이다(평가·전환·롤백 모두 draft 또는 카드 값 보존). 같은 카드에서 버전 열이 draft로 덮어써져 있어도 출처가 바뀌지 않는다.
- 이 고정이 없으면 다음 평가가 `completion_metric_version`을 V3로 덮어써 근거가 사라진다. 그래서 고정은 3-1의 3단계, 덮어쓰기 바로 앞에서만 한다.
- 조회·앱 시작·도구는 고정하지 않는다. 평가를 받지 않은 기존 카드는 `first_completed_source` NULL로 남는다. 읽는 쪽은 "아직 고정 전"으로 해석하고 3-2 표를 같은 방식으로 적용할 수 있다(쓰지는 않음).
- 시각·출처를 추정해 채우지 않는다. 읽을 수 없는 `first_completed_at`은 고치지 않고 `source_unknown`으로만 표시한다.

### 3-3. 응답 (형태는 그대로, 새 판정에서 뜻을 고정)
- `completed`·`completion_metric_version`·`srs.completion_status`: 이번 V3 판정(지금과 같은 뜻).
- `srs.first_completed_at`: **현재 판정 기준의 최초 완료**(`version_first_completed_version`이 현재 버전일 때의 `version_first_completed_at`, 아니면 null). draft 최초 완료 시각을 V3 응답에 섞지 않는다.
  - 대안: 지금처럼 "어떤 기준이든 최초 완료"로 두기. 그러면 V3 응답에 draft 시각이 출처 없이 실린다. 권장하지 않음(결정 항목 7-1).
- `srs.needs_relearning`: 3-1의 6단계.
- 응답 모델(`FsrsReviewResult`, extra=forbid)과 영수증 정본은 바꾸지 않는다. 이미 저장된 draft 영수증은 같은 바이트로 재생된다.

### 3-4. 버전별 처리표 (이번 평가가 V3일 때)

| # | 평가 전 카드 | 이번 V3 판정 | 평가 뒤 `first_completed_at` / `source` | `version_first_*` | 응답 `first_completed_at` | `needs_relearning` |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 완료 이력 없음 | 미완료·확인 불가 | NULL / NULL | NULL | null | false |
| 2 | 완료 이력 없음 | 완료(시각 t) | t / V3 | t, V3 | t | false |
| 3 | V3 최초 완료 t | 미완료 | t / V3 | t, V3 | t | **true** |
| 4 | V3 최초 완료 t | 확인 불가(불완전 증거) | t / V3 | t, V3 | t | false |
| 5 | V3 최초 완료 t | 다시 완료 | t / V3 | t, V3 | t | false |
| 6 | draft 최초 완료 d (출처 고정 전) | 미완료 | d / draft(이번에 고정) | NULL | null | **false**(draft만으로 V3 재학습 아님) |
| 7 | draft 최초 완료 d | 완료(t) | d / draft | t, V3 | t | false |
| 8 | draft 최초 완료 d, V3 첫 완료 t | 미완료 | d / draft | t, V3 | t | true |
| 9 | 최초 완료 d, 버전 NULL | 아무거나 | d / `source_missing` | 6·7과 같음 | 6·7과 같음 | 6·7과 같음 |
| 10 | 최초 완료 읽을 수 없음 | 아무거나 | 원값 / `source_unknown` | 6·7과 같음 | 6·7과 같음 | 6·7과 같음 |

- 일시 중지(참여 `paused`) 카드도 평가를 받으면 같은 표를 따른다(지금 평가 경로는 참여를 `active`로 판정함, 변경 없음).
- 완료는 복습 종료가 아니다. 예약·학습 단계·유지율은 바꾸지 않는다.

## 4. 다른 경로에서의 보존

### 4-1. 전환(apply_plan) — 소급 완료 금지
- 완전한 legacy 이력 전환도 `completion_metric_version`·`first_completed_at`·새 열을 **쓰지 않는다**. 재생은 FSRS 상태 계산에만 쓴다.
- 영향: 전환 후보의 `values`에서 완료 두 키가 빠진다. 그 결과 다음이 따라 바뀌며, 구현 때 회귀로 고정한다.
  - apply 기록 `srs_after_json`, 실행 scope의 `values`. 둘 다 `_APPLY_VALUE_KEYS`의 부분집합이라 기존 판정 계약 안이다.
  - 기존 전환 테스트의 기대값 일부.
- 이미 전환된 카드의 기존 완료 값은 그대로 둔다(일괄 수정 없음).

### 4-2. 롤백·재전환·B안
- 새 열 3개를 `ROLLBACK_PRESERVED`에 넣는다. 롤백·재전환이 쓰지 않고, rollback 기록 `srs_before_json`에도 들어가지 않는다(`_read_rollback_record` 검사가 이미 이 집합을 거부한다).
- 롤백의 기존 두 열은 지금처럼 `card or before`다. 카드 값이 있으면 그대로이므로 최초 완료가 사라지거나 바뀌지 않는다.
- 정상 복원·상태 없음 재전환·B안 재시작은 완료 값을 쓰지 않는다. 재시작 뒤 새 구간의 V3 판정이 완료되면 3-1의 5단계만 따른다. 옛 구간 성공은 증거에 섞이지 않는다(U7·B안 규칙 그대로).

### 4-3. U10 도구·snapshot
- 새 열은 `APPLY_CARD_FIELDS`·`ROLLBACK_CARD_FIELDS`·`PRUNED_APPLY_CARD_FIELDS`·`_APPLY_VALUE_KEYS`에 넣지 않는다. snapshot·실행 scope에 들어가지 않으므로 U10-b 최소화·U10-e 정리가 건드릴 일이 없다.
- 형식 1 기록의 허용 키는 "카드 표 열"이다. 새 열을 추가해도 옛 형식 1 기록에는 그 키가 없으므로 판정이 바뀌지 않는다(구현 때 확인).

### 4-4. 영수증·원로그
- 영수증·원로그·snapshot을 새 기준으로 일괄 수정하지 않는다. 같은 request_id 재시도는 저장된 처음 응답을 그대로 돌려준다(draft 시절 영수증 포함).

## 5. SQLite·PostgreSQL

| 항목 | SQLite | PostgreSQL |
| --- | --- | --- |
| 추가 | `ensure_srs_schema`의 `card_columns`에 3열 추가 → 기존 `_add_columns`(ADD COLUMN, 없을 때만) | 같은 함수가 `ADD COLUMN IF NOT EXISTS` |
| 정의 | `first_completed_source TEXT`, `version_first_completed_at TEXT`, `version_first_completed_version TEXT` | 같음 |
| 제약(권장) | `CHECK ((version_first_completed_at IS NULL) = (version_first_completed_version IS NULL))`. SQLite ADD COLUMN의 CHECK는 기존 행에 소급 검사되지 않으나 기존 행은 모두 NULL이라 무관 | 같은 CHECK. 기존 행 NULL이라 통과 |
| 기존 행 | 모두 NULL(백필 없음). NULL의 뜻은 3-2 | 같음 |
| 원자성 | 평가 트랜잭션 1개(BEGIN IMMEDIATE) | 같은 트랜잭션, 계정 행 `FOR UPDATE` |

- PostgreSQL은 이번에도 실행하지 않는다. **미검증·출시 차단**이다.

## 6. 구현 때의 검사표 (승인 후)
- V3 판정: 각 조건의 직전·정각·직후(S 30일, 7×24시간), 서울 자정 경계, `Z`·양수·음수 오프셋, 같은 날 반복 성공, Again 초기화. "성공 날짜 3개 + 긴 간격 1회" 거부, "긴 간격 2회 + 날짜 2개" 거부.
- 처리표 3-4의 10행: 개인·구독 각각. 이후 실패·재참여 포함.
- 출처 고정: 확인됨·누락됨·알 수 없음 3종. 고정은 평가에서만 일어나고 조회·앱 시작·U10 도구·전환·롤백에서는 0건. 두 번째 평가가 출처를 바꾸지 않음.
- 증거 보호: 불완전 이력·손상 로그·변조 snapshot·설명 없는 버전 공백에서 완료 0. U7 경계·B안 재시작 뒤 옛 구간 성공 미반영.
- 경로 보존: 전환(소급 완료 0)·롤백·정상 복원·반복 B안·U10-b·U10-e 뒤 평가에서 세 열과 기존 두 열이 처리표대로.
- 재시도·동시성: 기준 변경 전 영수증 재시도는 같은 바이트. 같은 카드 동시 평가 두 순서(잠금·CAS)에서 최초 완료·출처가 한 번만 기록됨. 실패 주입 시 전부 롤백.
- 스키마: 빈 DB·기존 DB(합성)에서 열 추가가 멱등이고 기존 행이 NULL. 형식 1 기록 판정 불변.
- 시뮬레이션: 고정 시뮬레이션을 실제 엔진으로 다시 실행하고 문서 수치(보통 59일·쉬움 74일·혼합 29일)와 비교. 다르면 원인을 보고하고 기준은 바꾸지 않는다. 합성 결과는 학습 효과·기억률의 증거가 아님을 적는다.
- 격리 API: 판정·재시도 응답 확인. 프론트에서 완료 값이 쓰이지 않음을 점검. 백엔드 전체, U7~U10 회귀, SRS 스크립트 9종, 프론트 테스트·타입 검사·diff 검사.

## 7. 결정해 주실 것
1. 응답 `srs.first_completed_at`의 뜻: **현재 기준의 최초 완료**(권장) / 지금처럼 기준 무관 최초 완료.
2. 새 열 이름과 예약값: `first_completed_source`(`source_missing`·`source_unknown`), `version_first_completed_at`·`version_first_completed_version`. 다른 이름을 원하시면 알려 주세요.
3. 다음 기준(V4) 때 `version_first_completed_*`가 V4로 바뀌는 것(V3 첫 완료 시각은 그때 별도 설계)을 받아들일지.
4. 전환에서 완료 값 쓰기를 없애는 것(4-1). 기존 전환 테스트 기대값 일부가 바뀐다.
5. 출처 고정을 "다음 실제 평가에서 한 번"으로 하는 것(3-2). 별도 일회성 도구로 미리 고정하는 안은 백필에 해당해 제외했다.

## 8. 확정 계약 (2026-10-17 결정 반영, 구현 기준)

### 8-1. 결정
1. 응답 `srs.first_completed_at` = 현재 판정 기준(V3)의 최초 완료(`version_first_completed_*`가 유효한 V3 쌍일 때의 시각, 아니면 null). 기존 draft 영수증의 재시도는 저장된 원래 바이트 그대로다.
2. 새 열 3개와 예약값 `source_missing`·`source_unknown`을 쓴다. `version_first_completed_at`·`version_first_completed_version`은 함께 NULL이거나 함께 유효해야 한다(DB CHECK + 코드 판정).
3. **V3만 구현한다.** `version_first_completed_*`는 비어 있을 때만 V3로 쓴다. 다른 버전이 들어 있으면 덮어쓰지 않는다(V4 자동 덮어쓰기 없음). 향후 버전 전환은 별도 설계·승인 대상이다.
4. 전환은 legacy 이력 재생으로 완료 값을 만들지 않는다. FSRS 상태 계산은 그대로 하고, 카드에 이미 있는 완료 이력은 그대로 둔다.
5. 출처는 다음 실제 평가에서, 기존 `completion_metric_version`을 덮어쓰기 직전에 한 번만 고정한다. 조회·앱 시작·도구는 쓰지 않는다.
6. `needs_relearning`은 유효한 V3 최초 완료가 있을 때만 계산한다(그 뒤 현재 판정이 미완료면 true). draft 완료만으로는 V3 재학습이 아니다.

### 8-2. 카드 지문 호환 (일괄 재작성 없음)
- 카드 지문은 `migration._card_print` 한 곳에서만 만든다. U4 학습 표시 열을 빼고 카드 행 전체를 해시한다. 쓰는 곳은 전환 후보 비교, 실행 scope `card`, rollback 기록 `baseline.card_fingerprint`이다.
- 새 열 3개도 같은 방식으로 지문에서 뺀다(`COMPLETION_HISTORY_COLUMNS`).
  - 열이 없던 시절에 만든 지문은 그 열이 없는 카드 행의 해시다. 새 코드는 같은 카드에서 그 열을 빼고 해시하므로 값이 같다. 그래서 변경 없는 카드가 "롤백 후 변경됨"이 되지 않는다.
  - 기존 snapshot·실행 scope·rollback 기록의 지문은 다시 쓰지 않는다.
- 빼도 되는 이유: 새 열은 FSRS 평가에서만 바뀐다. 평가는 카드 버전·로그를 함께 바꾸므로 baseline의 카드 버전·로그 지문 비교가 이미 그 변경을 잡는다.
- 검증: 열 추가 **전** 스키마로 만든 합성 DB에서 전환·평가·롤백을 하고, 그 기록을 그대로 둔 채 열을 추가(업그레이드)한다. 그 뒤 정상 복원 재전환과 버전 공백 증명이 유지되는지 확인한다.

### 8-3. 저장 값 판정과 손상 처리 (평가는 실패시키지 않고, 조용히 덮어쓰지 않음)

| 값 | 정상 | 손상·미지원일 때 |
| --- | --- | --- |
| `first_completed_at` | NULL 또는 시간대 있는 ISO 시각(`goals.read_utc`) | 원값 유지. 시각을 파싱하지 않고도 평가가 끝난다(지금의 `fromisoformat` 의존 제거). 출처를 고정할 때 `source_unknown` |
| `first_completed_source` | NULL(고정 전), draft, V3, `source_missing`, `source_unknown` | 원값 유지. 다시 고정하지 않음 |
| `first_completed_at` NULL + 출처 있음(불일치) | - | 둘 다 유지. 최초 완료 이력을 새로 쓰지 않음(현재 기준 쌍은 따로 판정) |
| `version_first_completed_*` | 둘 다 NULL, 또는 읽을 수 있는 시각 + `meaning-completion-v1` | 원값 유지·덮어쓰지 않음. 이번 평가에서 현재 기준 최초 완료는 "없음"으로 응답(`first_completed_at` null)하고 `needs_relearning`=false. 완료여도 쌍을 쓰지 않음 |

- 손상은 평가 요청을 막지 않는다. 새 오류 코드도 없다. 판정·예약·로그·영수증은 정상으로 기록된다.
- 한쪽만 NULL인 쌍은 DB CHECK가 새 쓰기를 막는다. PostgreSQL에서 CHECK 없이 들어온 경우에도 위 "손상" 처리를 따른다.

### 8-4. 버전별 처리표 (확정, V3 평가 한 번)
3-4 표와 같다. 다만 4·10행의 "확인 불가"와 8-3의 손상 쌍 행이 추가된다.
- 손상·미지원 쌍이 있는 카드: 평가 뒤 쌍은 원값, 응답 `first_completed_at` null, `needs_relearning` false.
- 최초 완료 이력(`first_completed_at`·출처)은 3-2 규칙대로만 바뀐다.

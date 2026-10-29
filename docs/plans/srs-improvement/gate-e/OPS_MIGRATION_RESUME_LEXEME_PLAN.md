# 구독(어휘) 카드 `resume` 검증 계획 (2026-10-28 작성, 2026-10-29 L-1·L-2 검증 마감)

**현재 상태(2026-10-29)**: L-1 합성 구현·검토 마감(8절), L-2 실제 PostgreSQL 18.6 검증 L1~L9 9/9와 R2 정리·로컬 증거 보관을 독립 대조했다(9절). LQ3는 9절의 시험 대상 한정 승인에 따라 `True`이며, 승인 없는 분기는 가짜 보호 검사에서 명시적으로 확인한다. LQ1 경합·실제 장애·운영 활성화는 이번 마감에 포함하지 않는다.

작성 당시 상태: 계획만 있다. 코드·권한·지문·기대 상수를 바꾸지 않았고, 검사 실행, PG·DB 접속, 키 생성, 증거 작업도 하지 않았다. 아래 L-1·L-2와 대상 값은 모두 **승인 전**이다.

표기:
- **[코드 확인]** 이번에 정적으로 읽어 확인한 제품·시험 코드 사실
- **[제안 기대]** 계약과 코드에서 미리 정한 기대값. 관측된 결과에 맞춰 정하지 않는다
- **[미검증]** 실제 PostgreSQL에서 확인하지 않은 것

새 정책이나 판정 엔진은 만들지 않는다. 승인·계획 파일·근거 결속(RS2b·RS3), 공급자 관측·재판정, 잠금 아래 9개 값 대조(P2), 상태 판정(`judge_status`), 기간·만료 규칙은 `OPS_MIGRATION_RESUME_PLAN.md`의 계약을 그대로 쓴다.

## 0. 이미 확인한 것과 아직 확인하지 않은 것

| 범위 | 확인된 증거 | 구독 카드에 대해 말할 수 있는 것 |
| --- | --- | --- |
| 개인 카드 `resume` | RS4 2차 25/25·보완 3/3(PostgreSQL 18.6, 개인 p1~p3, `OPS_MIGRATION_RESUME_REAL_PG_EVIDENCE.md`) | **없음**. 이 결과를 구독 카드 검증 증거로 합산하지 않는다 |
| 구독 카드 **최초** `apply` | C12 a2·S3 a2(실제 PG): 개인 3 + 구독 어휘 2를 한 번에 적용, 종료 0 | 최초 적용 경로의 쓰기 권한·SQL만. 재개(기존 실행·커서 이어 처리)가 아니다 |
| 구독 카드 **재개** | 없음. 합성 `resume` 검사(SQLite 19개·공급자 9개)와 RS2 제품 검사는 개인 카드만 쓴다(`lexeme` 0건, [코드 확인]) | **[미검증]**(합성·실제 모두) |
| 구독 상실 시 최초 적용 | 합성 SQLite `test_srs_d2_convert.py::test_lost_subscription_after_preview_is_a_conflict`: 미리보기 뒤 구독을 비활성화하면 `conflict`, 카드 그대로 | 재개 중 구독 상실의 동작은 **[미검증]** |

## 1. 정적으로 확인한 코드 사실 [코드 확인]

| 항목 | 위치 | 사실 |
| --- | --- | --- |
| 카드 식별 | `app/srs/storage.card_location` | 구독 카드 `CardKey("lexeme", user_id, lexeme_id)` → `user_word_progress WHERE user_id = ? AND lexeme_id = ?`. 개인 카드는 `vocab_items WHERE user_id = ? AND id = ?` |
| 기록 | `storage.load_logs` | 구독 카드는 `lexeme_review_logs WHERE user_id = ? AND lexeme_id = ?`(시간 열 `created_at`) |
| 접근 판정 | `migration._authorized` | 구독 카드는 `shared_deck_words`와 `user_deck_subscriptions`(`is_active = TRUE`)를 잇는 SELECT로 판정한다. **잠금이 없다**(`FOR SHARE` 없음). 리뷰 쓰기 경로의 `storage.require_subscription`은 PostgreSQL에서 `FOR SHARE OF subscriptions, words`로 잠근다 |
| 재판정 | `migration.inspect_card(..., for_update=True)` | 카드 행 `FOR UPDATE` 뒤 `_authorized`가 거짓이면 후보 품질이 `unavailable`이 되어 계획 후보와 달라지고, 카드 연결은 `conflict`로 기록하며 카드를 쓰지 않는다 |
| 쓰기 | `storage.update_card`, `history_intro.record_intro` | `user_word_progress`의 계약 열 UPDATE(`srs_card_version` CAS), 소개 기록은 같은 표의 두 열 |
| snapshot | `apply_plan` 카드 연결 | `srs_migration_snapshots(run_id, user_id, card_kind = 'lexeme', card_ref = lexeme_id, …)`, `UNIQUE(run_id, card_kind, card_ref)`. 재개 때 snapshot이 있으면 `already_applied` |
| 계획 순서 | `migration._scope` | 카드를 `(kind, ref_id)`로 정렬한다. `"lexeme" < "personal"`이므로 혼합 범위에서는 구독 카드가 먼저 처리된다 |
| 구독 해제 경로 | `app/repositories` 검색 | 앱에는 구독 비활성화·덱 단어 제거 경로가 없다(활성화 UPDATE만 있음). 기존 합성 검사도 "no unsubscribe path exists in the app"이라고 적고 데이터로 바꾼다 |
| 권한 계약 | `srs_migrate.READ_PRIVILEGES`·`WRITE_PRIVILEGES` | `user_word_progress`·`lexeme_review_logs`·`shared_deck_words`·`user_deck_subscriptions` SELECT, `user_word_progress` 계약 18열 UPDATE(개인 카드와 같은 열 목록). 시퀀스 USAGE 없음 |
| RS4 실행기 | `tests/_ops_resume_real.py` | `CARDS = ("p1", "p2", "p3")`, `Harness.case`가 구독 카드 목록을 `[]`로 만든다. 합성 자료(SEED)에는 계정 a·b·c가 같은 공유 덱을 구독하는 어휘 l1·l2가 있다. 같은 lexeme을 가진 다른 계정 행이 이미 존재한다 |

### 1-1. 코드 확인에서 나온 확인 필요 사항 (판정 아님)

- 재개 카드 연결은 구독 판정에서 구독·덱 단어 행을 잠그지 않는다. 그래서 판정 뒤 커밋 전에 다른 트랜잭션이 구독을 비활성화하면 그 변경을 막지 못할 수 있다. 리뷰 경로와 다른 점이다.
- 계약 문서는 이 경우의 기대를 정하지 않았다. 이 계획에서는 **기대값을 정하지 않고 결정 항목 LQ1로 남긴다**. 관측 결과로 기대를 정하지 않는다.
- 앱에 구독 해제 경로가 없으므로 운영 영향은 데이터 직접 변경이나 향후 기능에 달려 있다.

## 2. 최소 검사표

- 합성(L-1)과 실제 PG(L-2)를 같은 표로 정하되, 증거는 따로 집계한다.
- 기대값은 1절 코드 사실과 RESUME 계약에서 미리 정했다.
- 카드 이름: 계정 a의 구독 어휘 l1·l2, 개인 p1. 모든 대응은 반환 순서가 아니라 `(kind, user_id, ref_id)` 키로 한다.

| ID | 항목 | 초기 상태 | 절차 | [제안 기대] |
| --- | --- | --- | --- | --- |
| L1 | 부분 처리 구독 실행 재개 | 범위 l1·l2, 배치 1 최초 적용 → `started`, 커서 1 | 배치 2 재개 | 종료 0. l1은 `already_applied`(값·버전·snapshot 그대로), l2는 `applied`(버전 +1, snapshot 1 추가, `card_kind = 'lexeme'`), 실행 `completed` |
| L2 | `failed` 구독 실행 재개 | 범위 l1·l2, 둘째 카드 연결 뒤 **주입** 예외 → `failed`, 커서 1 | 재개 | L1과 같음. 상태가 `failed`에서 첫 카드 커밋 때 `started`로 돌아간 뒤 `completed`. 주입은 실제 장애 증거가 아님 |
| L3 | 혼합 범위의 키 대응 | 범위 l1·l2·p1. 제품 순서는 l1·l2·p1. 배치 1 → 커서 1 | 배치 3 재개 | 결과 `already_applied` 1·`applied` 2. 처리 순서와 결과 목록이 키 `lexeme:l1`, `lexeme:l2`, `personal:p1` 순서와 같고, snapshot의 `(card_kind, card_ref)`가 각 카드 키와 같음. 이름은 반환 순서로 붙이지 않음 |
| L4 | 다른 계정 같은 lexeme 불변 | L1·L2·L3 | 각 실행 전후 관리 연결 비교 | 계정 b·c의 같은 `lexeme_id`를 가진 `user_word_progress` 행과 `lexeme_review_logs`, 계정 a의 범위 밖 카드(p4·p5)가 내용 해시 기준으로 불변 |
| L5 | 잠금 아래 9개 값 | L1·L2 | 사전 조회·잠금 아래·관리 연결 계산 | 세 값 일치(9개 키), RS4 보완 형식으로 기록에 보존 |
| L6 | 재개 전 구독 상실 | 범위 l1·l2, 커서 1. 재개 전 계정 a의 구독을 비활성화(관리자 자료 변경, 닫힌 목록) | 재개 | 사전 조회는 상태만 보므로 진행하고, P2 대조도 통과한다. l1은 snapshot이 있어 `already_applied`. l2는 재판정에서 `unavailable` ≠ 계획 → `conflict`이고 카드 쓰기 0. 실행 `completed`, 종료 **5**(conflict 포함). l2 행은 불변 |
| L7 | 재개 전 덱 단어 제거 | L6과 같되 공유 덱에서 l2 단어 행 제거(관리자 자료 변경) | 재개 | L6과 같음(l2 `conflict`, 종료 5, l2 불변) |
| L8 | 카드 사이 쓰기 권한 회수 | 범위 l1·l2·p1, 커서 1. 첫 남은 카드(l2) 커밋 뒤 쓰기 역할의 `user_word_progress` 계약 열 하나 UPDATE를 회수(권한 변형, 닫힌 목록과 원복) | 배치 3 재개 | p1은 `vocab_items`라 회수와 무관하다. **다음 연결의 관측에서** `observed_privileges_missing`이 나서 1·`after_start`·`uncertain`·`status_required`. l2 커밋 유지, p1 불변. 원복 뒤 관측이 계약과 같음 |
| L9 | 구독 카드 읽기 권한 누락 | 읽기 역할 `user_deck_subscriptions` SELECT 회수(변형·원복) | 재개 | `observed_privileges_missing` 4, 읽기 관측 후 거부, 쓰기 연결 0, DB 불변 |

- 제외(결정 항목): 재개 카드 연결이 구독을 판정한 뒤 커밋하기 전의 구독 비활성화 경합(1-1, LQ1). 시각 순서만으로 결과를 말하지 않는다.
- 완료·커서 끝·닫힘·손상·소유 불명·만료·결속 거부는 카드 종류와 무관한 CLI 경로이므로 이번 표에 다시 넣지 않는다. 이 사항들은 RS4 실제 증거가 개인 카드 범위에서 다뤘다. 구독 카드 범위의 같은 판정은 [미검증]으로 남긴다.

## 3. 장치 재사용과 추가 코드 (L-1에서 구현, 승인 전)

| 구분 | 내용 |
| --- | --- |
| 그대로 재사용 | `_ops_real_layout`의 닫힌 배치·대상 확인·관리 연결·계수·정지점·기록 재읽기, RS4 `ResumeTracked`·`Values`·r0 탐침·9개 값 기록 형식, G0의 카드 키 대응(`quality_names`·`name_qualities`: l1·l2 이름 이미 포함), SEED(계정 a·b·c와 l1·l2 구독) |
| 추가(시험 코드만) | ① `Harness.case`에 고정 카드 집합 인자(예: `("l1", "l2")`, `("l1", "l2", "p1")`)를 추가하고 키로 요청을 만든다. 기존 RS4 기본값 p1~p3은 바꾸지 않는다 ② 구독 카드용 `run_facts`(이미 `user_id` + `lexeme_id`로 제한됨) 사용과, L4용 다른 계정 같은 lexeme 행·로그 해시 ③ 닫힌 관리자 변경 2종(구독 비활성화, 덱 단어 제거)과 닫힌 권한 변형 2종(쓰기 `UPDATE(srs_state) ON user_word_progress`, 읽기 `SELECT ON user_deck_subscriptions`)과 원복 ④ 새 고정 진입점 `check-lexeme`(검사 L1~L9, 실패 시 중단·종료 1, 기존 `check`·`check-values` 불변) |
| 합성 검사(L-1) | SQLite 실제 제품으로 L1~L3·L4·L6·L7(재개 경로)을 확인하는 새 검사 파일. 공급자 경로 가짜 검사에 구독 카드 연결 1건. 실행기 가짜 보호 검사(새 진입점의 순서·집계·중단, 변형·관리자 변경 닫힌 목록, 키 대응) |
| 제품 코드 | 바꾸지 않는다. LQ1 결정 전에는 잠금 추가 등 제품 변경을 제안만 한다 |

## 4. 대상·자료·정리 (L-2 제안, 대상 값은 승인 전)

| 항목 | 제안 |
| --- | --- |
| 대상 | 새 닫힌 프리셋 `PG67_RESUME_LEXEME`: `C:/JV_Tools/pg67`, 포트 55512, 역할 `jpvl_admin`·`jpvl_owner`·`jpvl_read`·`jpvl_write`, DB `jp_vocab_test_resume_lex_tpl` + 검사별 DB(L1~L3, L6~L9). PG66 프리셋·기록과 분리한다(PG66 증거 결속 보존) |
| 자료 | 기존 SEED 그대로(계정 a·b·c, l1·l2 공유 덱 구독). 의도한 품질 l1·l2 변환 가능을 G0에서 확인한다. 다르면 준비 실패로 멈추고 자료·기대를 바꾸지 않는다 |
| 관문 | G0(대상·식별·품질), G1(검사 DB마다 실제 최초 적용으로 초기 상태를 만들고 관리 연결로 확인. L2는 주입). 통과 수 제외 |
| 정리 | RS4와 같은 R2(기록 대조 일치 시에만 서버 정지·`pg67` 삭제). 증거는 새 실행 폴더에 두고 크기·SHA-256을 기록한다. 장기 보존은 Q5 정책(E1·E3·E4)에 따른 별도 승인 |

## 5. 승인 단위 (모두 승인 전)

| 단위 | 범위 | 하지 않는 것 |
| --- | --- | --- |
| **L-1** 합성 구현·검사 | 3절 추가 시험 코드, SQLite 실제 제품 검사, 공급자 가짜 검사, 실행기 가짜 보호 검사. 새 프리셋은 코드에만 추가하고 실행하지 않는다 | 제품 코드 변경, PG 실행, 키·인증서 생성 |
| **L-2** 실제 로컬 PG | `PG67_RESUME_LEXEME`에서 `prepare` → `check-lexeme` → `cleanup` 한 차례. 닫힌 관리자 변경(L6·L7)과 권한 변형(L8·L9)·원복 포함 | 기대값 수정, 현장 보정, 다른 대상 |

## 6. 결정 항목 (승인 아님)

| 번호 | 질문 | 권장 |
| --- | --- | --- |
| LQ1 | 재개 카드 연결이 구독 판정을 잠그지 않는 차이(1-1)를 어떻게 다룰지 | 이번 검증에서는 기대값을 정하지 않고 범위 밖으로 둔다. 별도 제품 계약 검토(리뷰 경로처럼 `FOR SHARE`)를 제안한다 |
| LQ2 | 대상 값(4절) | 제안 값 |
| LQ3 | L6·L7 관리자 자료 변경, L8·L9 권한 변형 허용 | 닫힌 목록으로 허용 |

## 7. 검토 보완과 결정 기록 (2026-10-29 사용자, L-1 코드보다 먼저 기록)

### 7-1. PG67 배치 객체와 대상 전달 (L-1 범위)

- `_ops_real_layout`은 지금 PG65·PG66 객체만 받는다. L-1에서 바꾸는 범위는 다음과 같다.
  - `_ops_pg62`에 닫힌 프리셋 `PG67_RESUME_LEXEME`와 그 검사 ID 목록을 추가한다(4절 제안 값). `PRESETS`에 한 개를 더하므로, 닫힌 목록을 단언하는 기존 검사의 기대 목록 갱신은 이 계약 변경에 따른 것이며 주석으로 남긴다.
  - `_ops_real_layout`에 닫힌 배치 객체 `PG67`(소유 역할 `jpvl_owner`, 7-3의 권한 변형 2종)을 추가하고 `LAYOUTS`에 등록한다. 기존 PG65·PG66 객체·값·함수는 바꾸지 않는다.
  - 대상은 **명시 인자로만** 전달한다. 새 실행기 `tests/_ops_resume_lexeme_real.py`는 자기 상수 `LAYOUT = lay.PG67`을 공통 함수에 넘긴다. 기존 실행기(`_ops_apply_real.py`·`_ops_resume_real.py`)의 전역 `T`·역할·DB 목록은 바꾸거나 바꿔치기하지 않는다(monkeypatch 금지).
  - 기존 실행기의 공개 명령(`check`·`check-values` 등)·검사 목록·판정·기대값은 그대로다. PG65 보존은 기존 보존 기준(`ops_pg65_preserve.json`) 대조 검사로 다시 확인한다.
- 실행기 재사용: `_ops_resume_real`의 대상 무관 계측(`ResumeTracked`·`ReadCursor`·`Values`·`summary_facts`·`resume_attribution`·9개 값 키)만 import해 쓴다. PG66에 묶인 `Harness`·관리 연결 래퍼는 쓰지 않고, 새 실행기에 PG67용 판을 둔다.

### 7-2. 서명 키와 가짜 서명

- L-1에서는 **시험 전용 임시 OpenSSH 서명 키**(기존 `test_ops_signature.Keys`, 임시 폴더에서 생성·사용 후 삭제)를 쓸 수 있다.
- 사용자 키·운영 키·ssh-agent는 쓰지 않는다. PG·TLS 키나 인증서는 만들지 않는다.
- 기록 구분:
  - **실제 시험 키 서명**: OS `ssh-keygen`으로 임시 키를 만들고 서명·검증한 경우(SQLite 제품 검사·공급자 경로 검사의 승인·근거)
  - **가짜 서명 검증**: 서명 검증을 대체한 경우(이번 L-1에서는 쓰지 않을 계획이다. 쓰게 되면 해당 검사에 명시한다)

### 7-3. 결정 (2026-10-29)

- **LQ1**: 구독 판정 뒤 비활성화 경합은 이번 검증에서 제외한다. 잠금 차이(1-1)와 미검증은 그대로 두고, 안전성이 확인됐다고 표현하지 않는다. 제품 잠금은 바꾸지 않는다.
- **LQ2**: 제안된 PG67 대상 값(`C:/JV_Tools/pg67`, 55512, `jpvl_*`, `jp_vocab_test_resume_lex_*`)을 시험 코드에 등록하는 것만 승인됐다. 실제 폴더·클러스터·역할·DB는 만들지 않는다.
- **LQ3**: 관리자 변경 2종(구독 비활성화, 덱 단어 제거)과 권한 변형 2종(쓰기 `UPDATE(srs_state) ON user_word_progress` 회수, 읽기 `SELECT ON user_deck_subscriptions` 회수)을 닫힌 시험 코드와 가짜 검사로 구현하는 것만 승인됐다. 실제 적용·원복은 L-2 별도 승인이다.

### 7-4. L1~L9 판정 문구 보완

- L6·L7의 "쓰기 0"은 **해당 카드(l2) 행의 쓰기 0**이다. 실행 요약(`summary_json`)·커서·완료 표시(`status`·`finished_at`) 갱신은 정상 동작으로 따로 확인한다.
- L8은 두 가지를 따로 확인한다. ① 앞 구독 카드(l2) 커밋 보존 ② 다음 연결(p1)의 공급자 관측 거부(`observed_privileges_missing`, 연결 생성 1·인계 0).
- L5는 사전 조회·잠금 아래·관리 연결 독립 계산의 9개 값을 고정 사본으로 저장하고, 실제 기록 재읽기로 보존을 확인한다(RS4 보완 형식과 같음).
- `check-lexeme`의 범위·순서·집계는 코드에 고정한다. G0 → G1 → L1~L9 → 사후 확인 순서이고, 관문과 사후 확인은 통과 수에서 제외한다. 첫 실패에서 후속 검사를 멈추고, 저장·재읽기가 확인된 통과만 센다.

## 8. L-1 결과 (2026-10-29, 합성·가짜 검사만, 실제 PG 없음)

### 8-1. 변경 파일

- `backend/tests/_ops_pg62.py`: 닫힌 프리셋 `PG67_RESUME_LEXEME` 추가(값만 등록, 실제 생성 없음)
- `backend/tests/_ops_real_layout.py`: 닫힌 배치 `PG67`과 권한 변형 2종 추가, `LAYOUTS`에 등록
- 닫힌 목록 단언 4곳(`test_ops_apply_real_guard.py`, `test_ops_audit_real_guard.py`, `test_ops_backup_real_guard.py`, `test_ops_real_layout.py`)을 계약 변경(한 개 추가)에 맞춰 갱신했다. `test_ops_real_layout.py`에는 PG67 분리·역할 판정 검사를 더했다.
- 새 파일:
  - 실행기 `backend/tests/_ops_resume_lexeme_real.py`(진입점 `prepare`·`check-lexeme`·`cleanup`)
  - `test_srs_migrate_resume_lexeme_sqlite.py`(6), `test_srs_migrate_resume_lexeme_provider.py`(3), `test_ops_resume_lexeme_real_guard.py`(18)
- 제품·CLI·공통 승인 형식·권한 계약·스키마는 바꾸지 않았다. 기존 실행기(`_ops_apply_real.py`·`_ops_resume_real.py`)도 바꾸지 않았다.

### 8-2. PG65·PG66 보존 근거

- HEAD(`5d508a4`)의 `_ops_pg62.py`·`_ops_real_layout.py`와 현재 파일로 각각 PG65·PG66 배치를 계산해 비교했다(연결 없음, 안전 환경 고정). 비교 항목은 대상 값, 검사 DB, 관리 연결 허용 DB, 역할, GRANT 문장(전 검사 DB), 기대 프로필 지문, 권한 변형 문장, HBA, 설정 문자열이며, 출력 JSON이 바이트 단위로 같았다.
- PG65는 기존 보존 기준 파일 대조(`test_ops_real_layout.py`)로도 확인했다.
- C12·RS4 보호 검사는 기대값을 바꾸지 않고 통과했다(닫힌 목록 단언만 갱신).

### 8-3. L1~L9 합성 검증 범위

| ID | 실제 제품 + 합성 SQLite | 공급자 경로(가짜 서버) | 실행기(PG 없는 가짜) |
| --- | --- | --- | --- |
| L1 부분 처리 재개 | 통과: l1 보존, l2만 처리, snapshot `lexeme` 키, 결과 순서 키 대응, `completed` | - | 순서·기대값 고정 |
| L2 `failed` 재개 | 통과(초기 `failed`는 **주입**) | - | 고정 |
| L3 혼합 범위 | 통과: 제품 순서 l1·l2·p1, 결과·snapshot을 `(kind, user, ref)`로 대응 | 통과: 혼합 계획의 모든 연결이 관측·재판정 뒤 인계 | 실제 `Harness.case`로 혼합 집합의 요청·계획·A₀ 결속과 목록 공유 확인(가짜 연결) |
| L4 같은 lexeme 다른 계정 | 통과: 다른 계정의 같은 lexeme 진행 행·로그·범위 밖 카드 불변(L1·L2·L3·L6·L7) | - | L1~L3 기록을 읽는 판정 |
| L5 9개 값 | 통과: 사전 조회 = 잠금 아래 = 독립 계산(9개 키) | 통과: 기대 진행 값 전달 | 실제 기록 저장·재읽기로 여섯 딕셔너리 보존, 누락·불일치·기록 실패는 통과 아님 |
| L6 구독 비활성화 | 통과: l2 **카드 행 쓰기 0**·snapshot 없음, 결과 `conflict`, 종료 5. 실행 요약·커서·완료는 정상 갱신 | - | 닫힌 관리자 변경(계정 a·l2만), LQ3 전 잠금 |
| L7 덱 단어 제거 | 통과(L6과 같음) | - | 위와 같음 |
| L8 카드 사이 권한 회수 | - | 통과: 앞 연결 커밋 유지, 다음 연결은 관측 후 거부(연결 1·인계 0), 1·`after_start` | 닫힌 변형·원복 문장, 기대 계수(생성 4·인계 2·커밋 2, 실패 표시 연결도 거부) 고정 |
| L9 읽기 권한 누락 | - | 통과: 상태 읽기 관측 후 거부 4, 쓰기 연결 0 | 닫힌 변형·원복 문장 |

### 8-4. 실제와 가짜의 구분

- **실제**: SQLite 검사의 제품 함수(`dry_run`·`apply_plan`·`run_progress_values`)와 CLI `run_apply`·`run_resume`(사전 검사·사슬·근거·계획 파일·`read_status`·`judge_status`)
- **실제 시험 키 서명**: 시험 전용 임시 OpenSSH 키(`test_ops_signature.Keys`, OS `ssh-keygen`)로 서명·검증했고, 키는 검사 뒤 지웠다. 가짜 서명 검증은 쓰지 않았다.
- **주입**: L2의 초기 `failed`, L6·L7의 관리자 행 변경(앱에 해당 경로 없음)
- **가짜**: 공급자 경로 검사의 드라이버·서버 응답과 `apply_plan` 대체본, 실행기 검사의 연결·공급자·제품 본문·인증서 내용
- 개인 카드 RS4 결과(25/25·3/3)는 합산하지 않았다.
- 실제 PG 연결·서버·관리·리스너 조회는 모든 가짜 검사에서 호출 즉시 실패하게 막았고, 새 프로세스는 최초 app import 전에 안전 환경 세 값을 고정했다.

### 8-5. 남은 미검증

- 실제 PostgreSQL에서의 구독 카드 재개 전부(L-2): 잠금, 권한 관측, 실제 관리자 변경·권한 변형과 원복
- LQ1: 구독 판정 뒤 비활성화 경합. 잠금 차이가 남아 있고, 안전성은 확인되지 않았다.
- 실제 장애, 운영 실행

### 8-6. 실행기 판정 보정 (2026-10-29, 검토 지적 3건, 실제 PG 없음)

8-1~8-5의 기록과 305개 결과는 그대로 둔다. 바꾼 파일은 `_ops_resume_lexeme_real.py`와 `test_ops_resume_lexeme_real_guard.py` 두 개다. 공통 모듈, 기존 실행기, 제품, CLI, 공급자, 승인 형식, 권한 계약, 스키마는 바꾸지 않았다. `LQ3_CHANGES_APPROVED`는 `None` 그대로다.

**결함 1. CLI 결과만 보고 통과하던 L1~L3·L8**

- 보정 전에는 CLI 결과·결과 순서·snapshot 키가 정상이면 통과했다. DB가 `started`·cursor 1이고 남은 카드가 그대로여도 통과했다(회귀로 확인).
- G1이 사례마다 관리 조회 기준선을 남긴다(`Harness.state`): 실행 행, 카드별 버전·엔진·행 전체, snapshot 행 전체(`card_version_before` 포함). 이 기준선은 초기 계획의 카드 버전과 계약으로 다시 확인한다. 이미 처리된 카드는 계획 버전 + 1과 `fsrs`, 남은 카드는 계획 버전과 `legacy`, snapshot은 처리된 키만 있어야 한다.
- L1~L3은 관리 조회 결과를 다음과 대조한다.
  - 실행 행 1개, `completed`, `finished_at` 있음, 최종 cursor = 계획 카드 수
  - 새로 처리된 카드는 `fsrs`, 버전 = 계획 버전 + 1, 행이 바뀌었고, 새 snapshot의 `card_version_before` = 계획 버전
  - 앞서 처리된 카드는 기준선과 같다(버전·엔진·행 전체). 기존 snapshot 행도 내용까지 같다.
  - snapshot 키 = 기준선 키 + 새로 처리된 키(개수 포함)
- L8은 같은 함수로 부분 커밋 상태를 대조한다: l2만 변환(버전 + 1), l1·p1은 기준선과 같음, 실행 행 `started`·cursor 2·`finished_at` 없음. 실패 표시 연결도 같은 관측에서 거부되므로 `failed`로 바뀌지 않는다(계약과 `apply_plan` 예외 분기).
- L8의 CLI 보고(`after_start`·`uncertain`·`status_required`, 종료 1)는 따로 판정한다. 기록도 `check_run`(CLI 보고)과 `check_admin_state`(관리 조회 상태)로 나눈다.
- 기대값은 실행 뒤 관측에서 가져오지 않는다. 기준선이 계획과 어긋나면 실행 판정 전에 `harness_defect`로 멈춘다.

**결함 2. L4가 계정 c를 보지 않던 문제**

- `outside`는 계정 b와 c 각각의 개인 카드 전부와 진행 행 전부를 읽는다. 두 계정 모두 사례의 lexeme에 대한 진행 행이 있어야 하며, 없으면 `harness_defect`다. 계정 a의 범위 밖 카드와 lexeme 로그 전부도 그대로 본다.
- 계정 값은 SQL에 바인딩한다. 결과는 `계정:종류:id`·`log:id` 키 사전으로 비교한다.
- 회귀: 실제 `Harness.outside`에 가짜 관리 연결을 붙였다. 이 연결은 바인딩된 계정만 돌려주고, 문장에 계정 값이 들어가면 실패한다. b는 그대로 두고 c의 같은 lexeme 행만 바꾸면 보정 전에는 통과했고, 지금은 실패한다. 이 가짜 연결은 실행기의 두 문장 형태만 흉내 낸다. 실제 PG 검증이 아니다.

**결함 3. 원복 뒤 재관측이 없던 L8·L9**

- 원복 SQL 뒤에 바꿨던 역할(L8 쓰기, L9 읽기)을 실제 공급자 경로로 다시 관측한다(`Harness.observe_role`). 경로는 제품 연결자, 계수 연결자, 업무 행렬 드라이버이고, 연결은 넘겨받은 뒤 쓰지 않고 닫는다. 새 `Counts`를 쓰므로 원래 실행 계수에 섞이지 않는다.
- 통과 조건: 결과 `matches_contract`, 계수 생성 1·인계 1·문장 0·쓰기 0·커밋 0
- 나머지는 모두 `harness_defect`로 처리하고 이후 검사를 멈춘다. 원복 실패, 관측 예외, 관측 없음, 권한 누락·초과, 제품 문장 또는 쓰기가 해당한다. GRANT 성공이나 이벤트 기록만으로 원복을 인정하지 않는다.
- 기록은 원래 실행(`check_run`)과 재관측(`revert_observation`: 역할·결과·계수)을 따로 남긴다. 재관측 실패는 통과로 세지 않는다.

**검사 (가짜만, PG·관리·리스너 호출은 즉시 실패)**

- 보정 전 재현: 새 회귀 15개를 보정 전 실행기에 돌렸다. 34개 하위 사례가 실패하고 3개가 오류였다.
  - 결함 1: 보고된 사례(`started`·cursor 1·l2 그대로) 포함
  - 결함 2: "c만 변경" 포함
  - 결함 3: 재관측 없음, 이후 검사 계속 진행
  - 정상 사례 3개는 보정 전에도 통과했다.
  - 보정 전 실패에는 가짜 연결의 한계로 생긴 것이 하나 있다. 계정 a의 p5 하위 사례는 옛 OR 문장을 가짜 연결이 흉내 내지 못해 실패했다.
- 추가한 검사(16개):
  - `AdminState` 4, `L8State` 4, `Outside` 4, `RevertObservation` 3
  - `LexemeCasePath`에 실제 `observe_role` 경로 1개: 읽기·쓰기 모두 `matches_contract`·생성 1·인계 1, 거부 시 생성 1·인계 0, 관측마다 새 계수
- 결과: `test_ops_resume_lexeme_real_guard.py` 34개 통과. 단독 실행과 루트 discovery 모두 통과했고 `-X dev` `ResourceWarning`은 0이다. 기록 저장과 재읽기, 실패 시 `not_run` 기록을 확인했고, 이번 임시 자료는 남지 않았다.
- 공통 모듈과 기존 실행기를 바꾸지 않았으므로 305개 묶음은 다시 돌리지 않았다.
- 실제 PG에서의 기준선·관리 조회·재관측은 검증하지 않았다(L-2).

### 8-7. 원복 재관측의 commit 계수 보정 (2026-10-29, 검토 지적 1건, 실제 PG 없음)

8-6의 기록과 34개 결과는 당시 결과로 그대로 둔다. 바꾼 파일은 이번에도 `_ops_resume_lexeme_real.py`와 `test_ops_resume_lexeme_real_guard.py` 두 개다. `_ops_product_connect.py`·`_ops_adapter.py`·`_ops_provider.py`·`_ops_real_layout.py`, 제품, CLI, 승인 형식, 권한 계약, 스키마는 바꾸지 않았다. `LQ3_CHANGES_APPROVED`는 `None` 그대로다.

**결함**

- 8-6의 `Harness.observe_role`은 CLI의 제품 연결자(`ProductConnector`)로 연결을 받아 `with connect(...): pass`로 닫았다. `ProductConnection`은 정상 종료하면 본문이 비어 있어도 commit을 호출한다(계약 6-2, 변경 금지). 그래서 정상 원복도 계수가 생성 1·인계 1·문장 0·쓰기 0·커밋 1이 되어 `REOBSERVED`(커밋 0)와 맞지 않았다.
- 8-6의 경로 검사는 공급자 뒤를 close만 하는 대체본으로 바꿔 이 충돌을 놓쳤다. 그 검사는 삭제하고 아래 회귀로 대체했다.

**보정**

- 관측 전용 경로: 실제 어댑터의 공개 진입점 `provide_with_adapter`로 연결을 한 번 받고(`Handoff.take()`), 업무 컨텍스트 없이 한 번 닫는다(commit·rollback 없음). 서명 사전 검사, 대상·TLS 인자와 인증서 사본, 관측, 판정, 연결 후 재판정은 모두 공급자가 그대로 수행한다. `ar.fix_app_environment()`도 제품 연결자와 같이 먼저 호출한다.
- 계수: 새 `Counts`와 새 추적 목록을 쓰고, 드라이버는 실행과 같은 업무 행렬·연결 후 대상 확인 드라이버다. 인계를 받은 뒤 추적 연결을 활성화하고 `handed`를 1 올린다. 그 뒤 문장·commit이 있으면 그대로 계수된다. commit 계수를 숨기거나 초기화하지 않았고 `REOBSERVED`의 0회 기준도 그대로다.
- 결과 판정:
  - 공급자 거부(권한 누락·초과, 연결 실패 등)와 인계 실패는 그 고정 코드다. 받지 못한 연결도 닫는다.
  - 인계 요약의 접근이 역할과 다르면 `connection_access_mismatch`다.
  - 닫기가 실패하거나 닫힘이 확인되지 않으면 `connection_close_unconfirmed`다.
  - `matches_contract`는 인계를 받고 닫힘까지 확인된 경우뿐이다.
- `revert_and_observe`의 중단 규칙(원복 실패·관측 예외·불일치는 `harness_defect`, 이후 검사 중단, `revert_observation` 별도 기록)은 바꾸지 않았다.

**검사 (가짜 서버만, PG·관리·리스너 호출은 즉시 실패)**

- 새 `RevertObservationPath` 4개. 실제 `Harness.case`와 `observe_role`, 실제 어댑터·공급자·관측기·판정·서명(시험 전용 임시 OpenSSH 키)을 쓴다. 가짜는 가드 드라이버가 돌려주는 연결(`ObservationServer`) 하나다. 이 연결은 연결 후 대상 사실과, 사례의 계약 프로필로 만든 카탈로그 응답, 트랜잭션 상태, commit 계수만 흉내 낸다.
- 보정 전 재현: 같은 회귀를 보정 전 실행기에 돌렸다. 읽기·쓰기 모두 `matches_contract`이면서 계수 생성 1·인계 1·문장 0·쓰기 0·커밋 1로 실패했다. 닫기 실패 사례도 커밋 1로 실패했고, 인계 실패는 처리되지 않은 예외(오류)였다.
- 보정 후:
  - 정상: 읽기·쓰기 모두 `matches_contract`, 생성 1·인계 1·문장 0·쓰기 0·커밋 0. 가짜 서버가 받은 commit은 0이고, 공급자의 관측 ROLLBACK 뒤 받은 것은 CLOSE 하나뿐이다. 관측마다 새 계수를 쓴다.
  - 쓰기 UPDATE 누락·users UPDATE 초과, 읽기 SELECT 누락·vocab_items UPDATE 초과: 각 고정 코드, 생성 1·인계 0·커밋 0, 연결 닫힘
  - 연결 실패: `connect_failed`, 생성 0. 인계 실패: `handoff_already_taken`, 인계 0·커밋 0. 닫기 실패: `connection_close_unconfirmed`(통과 아님)
  - `revert_and_observe`에 실제 관측을 붙이면 권한 누락과 닫기 실패 모두 `harness_defect`로 멈추고, `revert_observation`은 일치가 아닌 결과로 한 번 기록된다.
- 결과: `test_ops_resume_lexeme_real_guard.py` 37개 통과(기존 34 − 대체한 1 + 새 4). 단독 실행과 루트 discovery 모두 통과했고, 외부 `PYTHONPATH` 없이 돌렸다. `-X dev` `ResourceWarning`은 0이다. 직접 영향받는 `test_srs_migrate_resume_lexeme_provider.py` 3개와 `test_srs_migrate_resume_lexeme_sqlite.py` 6개도 통과했다. 공통 모듈과 기존 실행기를 바꾸지 않았으므로 305개 묶음은 다시 돌리지 않았다.
- 실제 PG에서 원복 뒤 재관측이 생성 1·인계 1·문장 0·쓰기 0·커밋 0이 되는지는 검증하지 않았다(L-2).

구독 카드 resume L-1 원복 재관측 보정 재검토 대기.

### 8-8. L-1 독립 재검토 마감 (2026-10-29)

- 원복 재관측은 실제 어댑터·공급자의 공개 인계를 한 번 받아 닫으며, 제품 연결 컨텍스트의 정상 종료 commit을 거치지 않는다.
- 독립 집중 검사: 실행기 보호 37 + 공급자 경로 3 + SQLite 제품 6 = 46개 통과, 오류·실패·건너뜀 0, ResourceWarning 0.
- 전체 305개 묶음은 초기 L-1 검토 때 통과한 당시 기록으로 보존하며 이번 보정 후 반복하지 않았다.
- L-1 합성 범위만 마감한다. 실제 PG의 SQL·잠금·권한·관리 변경 및 원복(L-2), LQ1 경합, 실제 장애·운영은 미검증이다. LQ3 승인값은 None이다.

## 9. L-2 실제 로컬 PG 검증 승인 기록 (2026-10-29 사용자 승인, 실행 전 기록)

- 기준 체크포인트: `de67ed0`(브랜치 `codex/fsrs-srs-replacement`). 실행 전 확인: HEAD `de67ed0`, 백엔드·문서 미커밋 변경 없음(다른 미추적 자료는 그대로 둠). `C:/JV_Tools/pg67` 없음, 포트 55512 리스너 없음.
- 승인 범위: 닫힌 프리셋 `PG67_RESUME_LEXEME`만 사용한다. 대상은 `C:/JV_Tools/pg67`, localhost:55512, `jpvl_*` 역할과 `jp_vocab_test_resume_lex_*` DB다. 시험용 클러스터·TLS 인증서·서명 키·역할·DB·스키마·합성 자료 준비를 포함한다. 실행은 `prepare` 1회, `check-lexeme` 1회, `cleanup`(R2) 1회다. 기존 클러스터나 다른 DB는 재사용하지 않는다.
- LQ3 실제 변경 승인: 이번 시험 대상에서만 닫힌 관리자 변경 2종(L6 구독 비활성화, L7 덱 단어 제거)과 권한 변형 2종(L8 쓰기 역할의 `user_word_progress` UPDATE(`srs_state`) 회수·원복, L9 읽기 역할의 `user_deck_subscriptions` SELECT 회수·원복)을 승인한다. 코드 변경은 `_ops_resume_lexeme_real.py`의 `LQ3_CHANGES_APPROVED`를 `None`에서 `True`로 바꾸는 한 줄뿐이다.
- 제외: LQ1(구독 판정 뒤 비활성화 경합). 제품 잠금은 바꾸지 않는다.
- 집계: G0 → G1 → L1~L9 → 사후 확인 고정 순서. 관문과 사후 확인은 통과 수에서 제외하고, 개인 카드 RS4나 합성 검사 결과와 합산하지 않는다. G1의 L2 `failed` 상태는 시험 장치 주입이다.
- 중단: 첫 준비 실패·시험 장치 결함·기대값 불일치·기록 실패에서 멈춘다. 현장 보정·재실행은 하지 않는다. 결과와 무관하게 기록과 현재 대상을 대조한 뒤 R2 정리를 한다. 소유가 불명확한 잔존물은 삭제하지 않고 보고한다.
- 증거: 새 실행 ID의 기록·대상·서버 로그·단계별 표준 출력의 크기와 SHA-256을 남기고, `C:/JV_Evidence/pg67/<실행 ID>/`에 덮어쓰기 없이 복사·재대조한 뒤 실행별 `custody.json`을 쓴다. 기존 루트 ACL은 바꾸지 않고, 상속 ACL이 기존 허용 정책과 다르면 보관을 중단한다. 보존은 인수 완료일부터 1년이며 자동 삭제·예약 작업은 없다. 임시 원본은 지우지 않고, 별도 사본은 계속 보류한다.
- 유지: C10 `restore_verified`·`backup_artifact_checked`는 `false`다. 운영 활성화나 Gate E 전체 완료가 아니다.

### 9-1. L-2 실행 결과 (2026-10-29, 실행 ID `20261029T082441`, PostgreSQL 18.6, 합성 자료만)

- 실행: `prepare` 1회(종료 0) → `check-lexeme` 1회(종료 0) → `cleanup` 1회(종료 0). 재실행·현장 보정은 없다. 코드 변경은 LQ3 한 줄뿐이다.
- 집계: G0·G1·사후 확인은 통과로 기록했지만 수에서 뺐다. 본 검사는 **L1~L9 9/9**이다. 개인 카드 RS4 결과나 합성 검사와 합산하지 않는다.
- 실제와 주입의 구분: G1의 L2 DB `failed` 상태(`injected: true`)는 시험 장치 주입이다. L6·L7의 관리자 변경과 L8·L9의 권한 회수는 승인된 닫힌 변경을 이 시험 DB에만 적용한 것이며, 실제 장애가 아니다. 나머지 G1 실행(`started`·cursor 1)은 실제 최초 `apply` 배치 1의 결과다.
- 핵심 증거(`record.json`):
  - L1~L3: 실행기가 관리 조회로 `completed`·`finished_at`·최종 cursor, 새 카드의 버전 + 1·`fsrs`, 앞 카드와 기존 snapshot 보존, 정확한 snapshot 키를 대조해 통과했다. 쓰기 계수 L1·L2 생성 3·인계 3·커밋 3, L3 생성 4·인계 4·커밋 4다.
  - L4: l1·l2·l3 DB에서 계정 b·c와 계정 a의 범위 밖 자료가 불변이다.
  - L5: l1·l2 각각 `pre_read`·`under_lock`·`admin_values` 여섯 딕셔너리가 모두 9개 키를 가지며, 실행별 세 값이 일치한다.
  - L6(구독 비활성화)·L7(덱 단어 제거): 해당 카드 쓰기 0과 실행 기록 갱신으로 통과했다(쓰기 생성 3·커밋 3, 업무 쓰기 2는 실행 기록).
  - L8: 관리 조회 상태 `started`·cursor 2·미완료 실행 1개(l2 커밋 보존)와, CLI 보고(`observed_privileges_missing`·`after_start`·`uncertain`·`status_required`·종료 1)를 따로 기록했다. 쓰기 생성 4·인계 2(다음 연결 거부)다.
  - L9: 읽기 생성 1·인계 0, 쓰기 생성 0, CLI `observed_privileges_missing`·`before_first_write`·종료 4다.
  - L8·L9 원복 뒤 실제 공급자 재관측: 두 역할 모두 `matches_contract`, 별도 계수 생성 1·인계 1·문장 0·쓰기 0·커밋 0이다.
  - 사후 확인: 업무 세션 0, idle in transaction 0이다.
- R2 정리: 실행기가 기록과 살아 있는 대상(PID 20576·실행 파일·데이터 경로·system identifier·DB·역할 OID·업무 세션 0)을 대조한 뒤 서버를 멈추고 `C:/JV_Tools/pg67`을 지웠다. 정리 뒤 확인: 폴더 없음, 55512 리스너 0, PID 20576 없음, 비밀 임시 폴더 없음. `C:/JV_Tools`의 다른 항목(`pgdata-e2`·`pgsql-18.6`)은 그대로다. 소유 불명 잔존물은 없다.
- 증거 보관: 아래 6개를 `C:/JV_Evidence/pg67/20261029T082441/`에 덮어쓰기 없이 복사하고 다시 읽어 이름·크기·SHA-256을 대조했다. 새 폴더·파일은 기존 루트의 세 주체 상속 전체 권한만 가진다(루트 ACL 변경 없음). `record.json`은 R2가 실행 폴더를 지우기 전에 복사했으므로, 정리 결과는 `cleanup_stdout.log`로만 남는다.

| 파일 | 크기 | SHA-256 |
| --- | --- | --- |
| `record.json` | 13754 | `fc6a7eec6cd6b954c2478bdd7e90ca73b175fac35a9731c30dfa9d67846242b6` |
| `target.json` | 2932 | `e6158aaa96a4d1527f47534007336f33f10fbc29bce42ec30280a556bcca8d6c` |
| `server.log` | 89421 | `c6f2e27991eda053b1932719565ff45190549b4988b8e680320701cec66cb9e6` |
| `prepare_stdout.log` | 10 | `aba1a6c58bc0c175b5a77d0a73a018cd667b7cd07efa6a1f0bd1fa001e07635c` |
| `check_lexeme_stdout.log` | 152 | `6ff33d29baabe15bf9ed0b437fe7baad4cf8fda8d3f7cd5d5aa0976eeecadf58` |
| `cleanup_stdout.log` | 9 | `0bc45c233f73cbda235d24a54875b48f859538adfff9d3f387cb39dbc791c9ba` |

- 인수 기록: `C:/JV_Evidence/pg67/20261029T082441/custody.json`(3899바이트, SHA-256 `4007c29fd1964e291712ebbf5e9c91faf3304926cc040ce308e0f07287c8490b`, 재읽기 일치). 보존 기산 2026-10-29, 기한 2027-10-29, 재검토 2027-09-29다. 자동 삭제·예약 작업은 없다. 임시 원본은 세션 임시 폴더 `pg67_evidence_20261029T082441`에 그대로 두었고, 별도 사본은 보류다. 기존 RS4 증거와 `custody.json`(`9df9d9a8…a94062`)은 바뀌지 않았다.
- 비밀값 확인: 6개 파일에 DSN·비밀번호·개인 키·SQL 매개값 형태 0건이다. 서버 로그에는 연결·종료 기록만 있고 ERROR·FATAL은 0건이다.
- 남은 미검증: LQ1(구독 판정 뒤 비활성화 경합), 실제 장애(커밋 응답 유실·서버 강제 종료 등), 실제 백업·복원(C10 `restore_verified`·`backup_artifact_checked`는 `false`), 완료 재호출·상태 보정, 운영 활성화. 이 결과는 Gate E 전체 완료가 아니다.

구독 카드 resume L-2 검증 범위 마감. 독립 검토와 체크포인트 기록은 REPORT 99절을 참조한다.

## 10. LQ1 경합 계약 계획 (2026-10-29, 문서만, 승인 전)

- LQ1(구독 판정 뒤 비활성화·덱 단어 제거 경합)은 별도 계획 `OPS_MIGRATION_RESUME_LEXEME_RACE_PLAN.md`로 분리했다. 정적 계획 검토는 마쳤으나 정책(LQ1-a~f)은 모두 미결이다. 제품·권한·검사는 바꾸거나 실행하지 않았다. 9-1절 L-2 결과는 이 경합의 증거가 아니다.
- 2026-10-29: LQ1-a~f 정책 방향을 확정했다(경합 계획 9절: 커밋 시점 접근 유지, 커밋 뒤 상실은 보고만, 현행 접근 의미, 관리자 변경 동결은 절차일 뿐임, 열 단위 `UPDATE` 한 열씩 수용, C-1 채택). 제품·권한 계약안(경합 계획 10절)은 검토 대기다. 구현·GRANT·검사는 승인되지 않았다.
- 2026-10-29: 계약안 검토 보정을 반영했다(경합 계획 10-5·10-6·10-6-1·10-8·10-11). manifest 지문 변경은 바뀐 파일이 실제 등록돼 있을 때만 생긴다. 배포 전 전체 미완료 실행 목록 확인과 커밋 뒤 접근 상실 점검은 미구현이다. 계약 재검토 대기.
- 2026-10-29: 계약안의 독립 정적 검토를 마쳤다(경합 계획 10-12). 배포 전 목록에서 원시 종료 상태만으로 실행을 제외하지 않도록 보강했다. 두 열과 D-L1~D-L3는 여전히 미결이며 구현·검사·GRANT·실제 PG는 승인되지 않았다.
- 2026-10-29: 두 권한 열과 D-L1~D-L3를 확정했고, PG 없는 최소 구현·합성 검사를 마쳤다(경합 계획 11절, REPORT 104). 실제 PG·GRANT·배포는 승인되지 않았고 미검증이다. 구현 검토 대기.
- 2026-10-29: 최소 합성 구현의 독립 검토를 마쳤다(경합 계획 11-4, REPORT 104-1). 집중 검사 59개 통과이며 기존 CLI 권한표도 두 열 추가와 맞췄다. 실제 PG 경합 검증·GRANT·운영 배포는 여전히 별도 승인 범위다.

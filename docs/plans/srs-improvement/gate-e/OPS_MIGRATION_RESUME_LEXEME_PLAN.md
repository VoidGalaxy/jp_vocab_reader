# 구독(어휘) 카드 `resume` 검증 계획 (2026-10-28 작성, 문서만, 계약 검토 대기)

**상태**: 계획만 있다. 코드·권한·지문·기대 상수를 바꾸지 않았고, 검사 실행, PG·DB 접속, 키 생성, 증거 작업도 하지 않았다. 아래 L-1·L-2와 대상 값은 모두 **승인 전**이다.

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

구독 카드 resume 계약 검토 대기.

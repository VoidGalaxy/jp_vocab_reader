# Gate C-1 검사표 (구현 시 실행, 지금은 미실행)

작성: 2026-10-09 (v0.1), 보정 v0.2: 2026-10-09. 계약 `CONTRACT.md` v0.2, 계획 `IMPLEMENTATION_PLAN.md` v0.2.

- 모든 DB 검사는 세션 전용 SQLite에서 한다.
- PG 검사는 보호 검사를 통과한 빈 로컬 테스트 DB가 있을 때만 실행한다. 없으면 "미검증"으로 기록한다.
- **고정 시계**: 테스트는 `server_now`를 주입할 수 있어야 한다(`now` 인자 또는 모듈 수준 시계 함수 패치). 실제 시계에 기대는 경계 검사는 쓰지 않는다.
- 커서 서명용 비밀값은 테스트 전용 값을 주입한다.

## 1. 전역 정렬

정렬 키는 `K = (bucket, sort_time, kind_rank, seq, ref_id)`이다.

| ID | 준비 | 기대 |
| --- | --- | --- |
| S1 | 개인 Review due(10:00), 구독 Learning due(10:05), 구독 Review due(09:00), 개인 신규 1 | 구독 Learning → 구독 Review(09:00) → 개인 Review(10:00) → 개인 신규 |
| S2 | 개인 Relearning due와 구독 Learning due가 같은 시각 | 같은 bucket 0. `kind_rank`(개인 먼저), `ref_id` 순. 매번 같은 순서 |
| S3 | bucket 0 카드 30장, bucket 1 카드 30장, `limit=20` | 20장 모두 bucket 0. bucket 1은 다음 페이지 |
| S4 | 개인 due 50장(나중 시각), 구독 due 5장(이른 시각), `limit=10` | 구독 5장 + 개인 5장(시각순). 종류별 LIMIT 후 이어 붙였다면 실패하는 배치 |
| S5 | Review 카드의 `srs_due_at`과 `srs_effective_due_at`이 다름 | 버킷·순서는 `effective_due_at` 기준 |
| S6 | 같은 구독 덱의 신규 lexeme 3개, `imported_at` 같음, `sort_order` 3·1·2 | `seq`(sort_order) 1→2→3 순. 응답 `sort_key`의 4번째 값과 일치 |
| S7 | 신규 개인(created_at 08:00)과 신규 구독(문맥 덱 imported_at 07:00) | 구독 먼저(sort_time), 그다음 개인 |
| S8 | lexeme X가 덱 3(sort_order 9)과 덱 7(sort_order 1)에 있음, `scope=all` | 문맥 덱 3, `seq=9`. 덱 7 scope에서는 `seq=1` |

## 2. 중복 제거와 정체성

| ID | 준비 | 기대 |
| --- | --- | --- |
| D1 | lexeme X가 구독 덱 A(id 3)와 B(id 7)에 모두 있음, due | `scope=all`의 응답·모든 집계에 1장. `review.shared_deck_id = 3` |
| D2 | D1 + `scope=subscribed_deck&deck_id=7` | 1장, 문맥 7 |
| D3 | 개인 카드 "猫"와 구독 lexeme "猫"가 모두 due | 2장. 각자 card_id·평가 URL |
| D4 | 개인 vocab_item 5와 lexeme 5가 모두 due | 서로 다른 항목. `card_kind`로 구분 |
| D5 | X가 A와 B에서 모두 신규 후보 | `new_available` 1 |

## 3. 필터를 LIMIT 전에 적용

| ID | 준비 | 기대 |
| --- | --- | --- |
| F1 | 정렬상 앞쪽에 paused 30장, 뒤에 active due 5장, `limit=5` | active 5장. `paused=30` |
| F2 | 앞쪽에 legacy 카드 20장(due), 뒤에 FSRS due 3장 | FSRS 3장. `not_converted=20` |
| F3 | 앞쪽에 불완전 이력 카드(FSRS·상태 없음·이력 있음) | 출제 안 함, `blocked_history` |
| F4 | 앞쪽에 S가 NaN이거나 상태 열이 일부만 있는 FSRS 카드 10장, 뒤에 정상 due 3장, `limit=3` | 정상 3장(페이지가 덜 차지 않음). `invalid_state=10` |
| F5 | 자기분류 known인 active FSRS due 카드 | 출제됨. 응답 `status=known` |
| F6 | 완료 판정이 completed인 Review 카드가 due | 출제됨(유지 복습). 응답에 완료 필드 없음 |

## 4. 범주 분류와 집계 불변식

| ID | 준비 | 기대 |
| --- | --- | --- |
| A1 | 11개 범주를 하나 이상씩 섞은 범위 | 각 카드가 정확히 한 범주. 12개 집계 필드 합 = `total_in_scope` |
| A2 | **미평가 legacy 개인 카드**(새로 담은 단어, 로그 0) | `not_converted`에 포함. `new_available`에 없음 |
| A3 | 상태만 바꾼 legacy 구독 progress 행(로그 0) | `not_converted` |
| A4 | `srs_config_version`이 다른 FSRS 카드 | `unsupported_config` |
| A5 | 참여 NULL인 FSRS 카드 / 참여 값 이상 | `invalid_state` |
| A6 | 엔진 상태는 있는데 `srs_effective_due_at` NULL | `missing_due`(예약 추정 안 함) |
| A7 | 시각 문자열이 정규 형식이 아님(`Z` 표기, 시간대 없음 등) | `invalid_state`, 출제 안 함 |
| A8 | 덱에 progress 행 없는 lexeme 40개 + FSRS 신규 progress 3개 | `new_unmaterialized=40`, `new_available=3`. 두 범주에 겹치는 lexeme 0 |
| A9 | paused이면서 상태도 깨진 카드 | `invalid_state`(먼저 맞는 범주). 두 번 세지 않음 |
| A10 | 범위 밖 카드(구독 해제·다른 계정·삭제) | 어느 범주에도 없음 |
| A11 | `new_allowed_now` | `min(new_available, 허용량)`이며 합계에 포함되지 않음 |

## 5. 권한과 권한 상실

| ID | 준비 | 기대 |
| --- | --- | --- |
| P1 | 다른 계정의 개인 덱 id로 `scope=personal_deck` | 404 `deck not found`, DB 무변화 |
| P2 | 구독하지 않은 공개 덱 id로 `scope=subscribed_deck` | 404 |
| P3 | 구독 해제 뒤 `scope=all` | 그 덱 단어가 응답·집계에서 사라짐(다른 활성 구독 덱에도 있으면 그 덱 문맥으로 남음) |
| P4 | 덱에서 lexeme 삭제 | 사라짐 |
| P5 | 덱 소유자가 비공개로 전환, 사용자는 활성 구독 유지 | 기존 규칙대로 계속 출제 |
| P6 | 개인 카드 삭제 | 사라짐 |
| P7 | 첫 페이지 뒤 구독 해제, 커서로 다음 페이지 | 해제된 덱 단어 없음(조건은 매 요청 다시 평가) |
| P8 | 로그인 없음 | 401 |
| P9 | legacy 모드 계정(설정 행 없음 / legacy / shadow) | 409 `srs_mode_not_fsrs`. 기존 `/study-items` 결과는 변경 전과 같음 |

## 6. 자정·시간대

| ID | 준비 | 기대 |
| --- | --- | --- |
| M1 | 서울 23:59(UTC 14:59)에 신규 3개 첫 평가, 목표 5 | `introduced_today=3`, `account_remaining=2` |
| M2 | M1 다음 `server_now` = 서울 00:01 | `seoul_date` 다음 날, `introduced_today=0`, `account_remaining=5` |
| M3 | UTC 날짜가 같고 서울 날짜가 다른 두 첫 평가(14:59, 15:01 UTC) | 서로 다른 날에 1개씩 |
| M4 | due 시각이 서울 자정을 넘음 | 버킷 판정은 UTC 비교만 |
| M5 | 23:59에 받은 커서로 00:01에 다음 페이지 | 409 `cursor_stale`(서울 날짜 변경). 첫 페이지 재조회는 200 |

## 7. 신규 목표

| ID | 준비 | 기대 |
| --- | --- | --- |
| G1 | 목표 20, 오늘 신규 0, 후보 50, `limit=100`, `mode=new` | 신규 20장 |
| G2 | 목표 20, 오늘 신규 20 | 신규 0장. due는 그대로 |
| G3 | **목표 초과**: 두 창이 각각 신규 20장을 받은 뒤 모두 평가(평가 함수 직접 40회) | 40회 모두 성공(거부 없음). 다음 조회 `introduced_today=40`, `account_remaining=0`, 신규 0장, `is_strict_limit=false` |
| G4 | 같은 카드 재평가, 같은 request_id 재시도 | `introduced_today` 증가 없음 |
| G5 | 첫 평가가 Again | 신규 1개 |
| G6 | B-2 이전 apply로 legacy 이력 카드 전환 | 오늘 신규 증가 없음 |
| G7 | 계획 덱 Q=10, 그 덱 오늘 신규 4, 계정 목표 20·오늘 신규 18 | `plan_remaining=6`, `account_remaining=2`, 신규 2장 |
| G8 | 목표 0 | 신규 0장, due는 그대로 |
| G9 | `extra_new=5` 전송 | 400 `unsupported_parameter`. 응답·DB 무변화 |
| G10 | **추가량 비소진 재현(반례 기록용)**: 순수 함수로 "요청별 extra 더하기" 식에 introduced 20→25→30, extra 5를 차례로 넣음 | 매번 허용 5. 이 식을 채택하지 않은 이유를 테스트 주석에 남김(구현 코드에는 없음) |
| G11 | 개인·구독 같은 표제어를 각각 첫 평가 | 신규 2개 |
| G12 | 큐의 `introduced_today` vs 같은 시각 평가 응답의 `srs.introduced_today` | 같은 값(정의 공유) |
| G13 | 삭제된 개인 카드의 오늘 첫 평가(SQLite) | 계속 1로 셈. PG는 [미정] |
| G14 | `srs_user_settings` 행 없음 | 목표 20, `settings_version` 0으로 읽음. 행 생성 0 |

## 8. 커서

| ID | 준비 | 기대 |
| --- | --- | --- |
| C1 | due 45장, `limit=20`로 3페이지 | 중복·누락 없이 45장(그사이 변경 없음) |
| C2 | 1페이지 뒤 1페이지의 카드 하나를 평가 | 2페이지에 영향 없음(이미 지난 키) |
| C3 | 1페이지 뒤, 지난 키보다 앞에 새 due 카드가 생김 | 2페이지에 안 나옴(문서화된 비보장). 첫 페이지 재조회 시 나옴 |
| C4 | **신규 6 = 4 + 2**: 허용 6, due 0, `limit=4`, 후보 9 | 1페이지 n1–n4, 2페이지 n5–n6, 3페이지 없음(`next_cursor=null`). 잘못된 순서(잔여량 먼저)였다면 2페이지가 비는 배치 |
| C5 | C4에서 1페이지 뒤 n1–n4를 평가해 `introduced_today`가 4 늘어남 | 2페이지는 여전히 n5–n6(첫 페이지 허용량 고정). 새 첫 페이지 조회는 허용량을 다시 계산 |
| C6 | 서명 바이트 1개 변조 / payload 1글자 변조 | 400 `invalid_cursor` |
| C7 | 2,049바이트 커서, base64 오류, JSON 아님, 필드 누락, 필드 범위 밖(`new_served > new_allowed0`, 음수 ref_id, bucket 3) | 400 `invalid_cursor`. 서명이 맞게 만든 테스트 커서도 범위 검사로 거부 |
| C8 | 계정 A의 커서를 계정 B가 사용 | 409 `cursor_stale`(uid 불일치). 응답에 A의 카드 없음 |
| C9 | 커서를 다른 scope·deck_id·mode·status(순서만 다른 status는 같은 것으로 정규화) | 다른 조건은 409, 순서만 다르면 통과 |
| C10 | 첫 페이지 뒤 계정 목표·`settings_version` 변경 / `plan_daily_new` 다른 값 | 409 `cursor_stale` |
| C11 | 엔진 설정 버전이 바뀐 상태로 기존 커서 사용 | 409 |
| C12 | 발급 후 15분 1초 지난 커서 | 409 |
| C13 | 커서 오류 메시지 | 비밀값, 서명, 다른 계정 정보 없음 |

## 9. 조회 쓰기 0

| ID | 준비 | 기대 |
| --- | --- | --- |
| W1 | 모든 mode·scope·커서 조합으로 조회 전후 비교 | 모든 테이블의 행 수와 행 지문(B-2 지문 함수) 동일. 특히 `user_word_progress`, 두 로그, `srs_review_receipts`, `srs_config_versions`, `srs_user_settings` |
| W2 | 읽기 전용 연결에 쓰기 주입 | 예외(B-2와 같은 방식) |
| W3 | progress 행 없는 lexeme이 있는 덱 조회 | progress 행 생성 0 |
| W4 | SQLite DB 파일 바이트 비교 | 조회 전후 동일 |
| W5 | 400·404·409 오류 응답 경로 | 쓰기 0 |

## 10. 연습 모드

| ID | 준비 | 기대 |
| --- | --- | --- |
| R1 | `mode=practice&status=uncertain` | 분류 uncertain인 active·정상 상태 카드만(due 무관). 모두 `practice_only: true`, `review: null` |
| R2 | 연습 결과 | 평가 API 경로가 응답에 없음. 카드·로그 무변화(W1 재사용) |
| R3 | `mode=today&status=…` | 400 |
| R4 | 신규·paused·blocked·invalid 카드 | 연습 대상에서 제외 |

## 11. 기존 동작 보존(legacy 회귀)

| ID | 대상 | 기대 |
| --- | --- | --- |
| L1 | 백엔드 전체 `unittest discover` | 기존 수 + 새 테스트 통과. PG 건너뜀은 미검증으로 표시 |
| L2 | `audit_current_srs.py` | 15/15 |
| L3 | 기존 회귀 스크립트 7개(B-1·B-2와 같은 목록) | 모두 통과 |
| L4 | `/study-items`, `/study-items/lexemes`(due_only·limit·first_review_only 조합), `/vocab-items` 정렬 | 구현 전 저장한 응답과 바이트 동일(같은 합성 DB, 같은 시계) |
| L5 | legacy 평가 2종 | B-2 이후 결과와 동일 |
| L6 | `introduced_on` 분리 전후 | 같은 합성 이력에서 같은 값 |
| L7 | **`recent` 무변경** | `frontend/` 파일 diff 0. `page.tsx`의 `recent` 경로와 `recentlySavedVocabItemIds` 처리 그대로 |
| L8 | 프론트 `npm test`, `npm run typecheck` | 통과 |
| L9 | `git diff --check` | 깨끗함 |

## 12. 구현 후에도 미검증으로 남을 항목

- PostgreSQL 실행: 로컬 PG가 없으면 SQL 이식성은 소스 검토뿐이다.
- 실제 브라우저 세션, 재시도, 대기 카드 화면: C-2 범위.
- 1천·1만 카드 성능: Gate E 범위.

## 13. 보정 내역 (v0.2)

- 추가: S6–S8(seq·문맥 덱 정렬), F4(깨진 상태가 페이지를 덜 채우지 않음), A1–A11(11개 범주·합계 불변식·미평가 legacy), G9·G10(`extra_new` 거부와 비소진 반례), G14(설정 행 없음), C4–C13(6=4+2, 허용량 고정, 변조·길이·범위·계정·조건·수명), W5, L6·L7(`recent` 무변경).
- 바뀜: v0.1의 G9(extra_new 적용)는 거부 검사로, M5(자정 넘긴 커서 유지)는 409로, 커서 불일치 항목은 C8–C12로 세분했다.

## 14. 손상된 평가 시각 (승인 2026-10-09, 구현·실행 완료 — 결과는 아래 14-1)

| ID | 준비 | 기대 |
| --- | --- | --- |
| T1 | 개인 로그 `reviewed_at = 'garbage'` | 큐 200, `introduced_today_status=unknown`, 신규 0, due 유지, 원로그 무변경 |
| T2 | 구독 로그 `created_at = 'garbage'` | T1과 같음 |
| T3 | 빈 문자열 `''`(개인·구독 각각) | T1과 같음. 문자열 MIN으로 "첫 평가"가 되는 일 없음 |
| T4 | 시간대 없는 값 `2026-10-09 00:00:00` | 확인 불가로 처리(500 아님) |
| T5 | `Z` 표기 `2026-10-09T00:00:00Z` | 승인 6-5 결과에 따름(권장: 정상으로 셈) |
| T6 | 정상 로그 뒤에 문자열 순서가 늦은 손상 로그(`garbage`) | 그 카드도 확인 불가(MIN이 가리지 않음) |
| T7 | 삭제된 개인 카드의 손상 로그(SQLite) | 계정 신규 확인 불가. PG는 [미정] |
| T8 | 다른 카드 손상 상태에서 FSRS 평가 | 200, 평가 저장, 영수증 `introduced_today=null`·`status=unknown` |
| T9 | 평가하는 카드 자신의 로그 손상 | 409 `review_history_unreadable`, 쓰기 0 |
| T10 | T8 요청 재시도 | 처음 영수증 그대로 |
| T11 | 덱 scope 밖 카드만 손상 | `introduced_today_in_scope_status=exact`, 계정 쪽은 unknown, 신규 0 |
| T12 | 손상 → 정상 복구 뒤 이전 커서 | 409 `cursor_stale` |
| T13 | 모든 경우 | 원로그 삭제·수정 0, 조회 쓰기 0 |

## 15. 학습 단계 범위 (C-1 보정, 구현·실행 완료)

| ID | 준비 | 기대 | 결과 |
| --- | --- | --- | --- |
| K1 | Learning step 0·1, Relearning step 0 | 출제됨, 평가는 라이브러리 규칙대로(0→1, 1→Review, Again→0, Relearning Good→Review, Hard→유지) | 통과 |
| K2 | Learning step 2·999, Relearning step 1 | `invalid_state`로 셈, 출제 안 함, 합계 불변식 유지 | 통과 |
| K3 | 개인 Learning 999, 구독 Relearning 1을 API로 평가 | 409 `invalid_engine_state`, 카드·로그·영수증·progress·DB 바이트 무변경 | 통과 |
| K4 | 엔진 직접 호출 | 범위 밖 step은 `SrsEngineError`, 범위 안은 정상 | 통과 |

### 14-1. 실행 결과 (`QueueCorruptTimeTests`, 11개 통과)

| ID | 결과 |
| --- | --- |
| T1–T4 | 통과. 개인·구독 `garbage`, `''`, 시간대 없는 두 형식 모두 API 200, 신규 확인 불가·하한·due 유지, 원로그 행 동일 |
| T5 | 통과. `Z`와 `+12:00` 오프셋을 실제 시각으로 비교. 문자열 MIN이면 오늘로 셌을 카드를 어제로 정확히 셈. 서울 자정 직전(23:59:59) 로그는 어제 |
| T6 | 통과. 정상 로그 뒤 `garbage`가 있어도 확인 불가 |
| T7 | 통과(SQLite). 삭제된 카드의 손상 로그도 계정 확인 불가 |
| T8 | 통과. 다른 카드 손상 중 정상 카드 평가 200, 응답·영수증에 null·unknown·하한 |
| T9 | 통과. 개인·구독 자기 이력 손상 → 409 `review_history_unreadable`, DB 행·파일 바이트 동일 |
| T10 | 통과. 손상 복구 뒤 같은 요청 재시도 = 처음 응답, 다른 payload 409 |
| T11 | 통과. scope 정상·계정 확인 불가 → 신규 0. scope 손상 시 `plan_remaining` null |
| T12 | 통과. 정상→손상, 손상→정상 모두 이전 커서 409 |
| T13 | 통과. 모든 경우 원로그 무변경 |
| 추가 | 손상 카드 자신 `invalid_state`·합계 불변식, 완료 판정 이벤트 실제 시각순(문자열 순서가 반대인 로그), 롤백 도구는 해석 예외로 전체 트랜잭션 버림(DB 동일) |

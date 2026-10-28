# Gate C-2 구현 계획 (승인 전)

작성: 2026-10-10 (v0.1), 보정 v0.2: 2026-10-10. 계약 `CONTRACT.md` v0.2, 검사 `TEST_MATRIX.md` v0.2.
상태: **계획만 작성. 제품 코드·스키마 변경 없음.** `CONTRACT.md` 7절 승인 뒤 시작한다. 승인되지 않은 항목은 해당 작업을 건너뛰고 보고한다.

## 1. 단계

| 단계 | 내용 | 끝나는 조건 |
| --- | --- | --- |
| **C-2a 서버** | 새 개인 카드 초기값, 구독 최초 평가(요청 정체성·원자적 생성), 큐 `exclude_card`, 생성 경로 준비 뒤 미생성 카드 출제, (R2 승인 시) `mode=selected` | TEST_MATRIX 3·4·5절의 S·A 항목 통과, 보고 후 사용자 검토 |
| **C-2b 클라이언트 순수** | `studySession.ts`: 시도 고정·결과 적용·응답별 전이, 회차 미루기 집계, 주 상태 우선순위, 활성 회차 판정 | TEST_MATRIX 1·2·3절의 U 항목 통과 |
| **C-2c 클라이언트 연결** | 모드 판별, 동적 큐 회차, 평가 시도, 대기·미룸, 연습, 계획 실행기, (승인 시) recent R2 | TEST_MATRIX B 항목 통과, 보고 후 사용자 검토 |

C-2a는 클라이언트 없이 단독으로 검증·보고한다. C-2b·C-2c는 C-2a 검토 뒤에 시작한다.

제외: 불완전 이력 초기화, PostgreSQL 로그 보존·실행, 완료 기준, 추가 신규량·목표 우회, 설정·목표 변경 API, 보류·재참여 API, 기본 FSRS 활성화, 실제 사용자 이전, 새 저장 키, 디자인 재작업·새 에셋.

## 2. C-2a 서버 변경 예정

| 파일 | 변경 |
| --- | --- |
| `backend/app/srs/goals.py`(또는 새 `srs/settings.py`) | `account_mode(connection, user_id)` 읽기 함수 |
| `backend/app/srs/storage.py` | `fresh_fsrs_columns()`: 새 카드 초기값 한 곳 |
| `backend/app/repositories/vocab_repository.py` | `create_or_update_vocab_item`의 INSERT 경로만 FSRS 계정이면 초기값. UPDATE 경로 무변경 |
| `backend/app/repositories/deck_package_repository.py`, `shared_deck_repository.py` | 가져오기·복사 INSERT에 같은 초기값(FSRS 계정만) |
| `backend/app/main.py` | 구독 평가 라우트: `"expected_card_version" in body.model_fields_set and value is None`이면 `FIRST_REVIEW` 표시를 넘김. 개인 라우트에서 명시적 null은 422 |
| `backend/app/repositories/lexeme_repository.py` | `FIRST_REVIEW`이면 `get_or_create_progress`를 부르지 않고 CONTRACT 3-2 순서(잠금 → lexeme → 구독 → 영수증 → 모드 → 행 확인 → 생성·평가). 그 밖의 요청은 순서·동작 무변경 |
| `backend/app/srs/reviews.py` | 생성 직후 평가: 내부 CAS 0, 영수증 해시는 원래 payload(`expected_card_version: None`). `request_hash`가 None을 그대로 직렬화하는지 확인 |
| `backend/app/srs/queue.py` | `exclude_card`(최대 100, LIMIT 전 출제 후보에서 제외, 범주 집계 불변, `excluded_by_request`, `next_due_at_excluded`, 커서 바인딩에 포함). 생성 경로 활성화 표시가 켜진 뒤에만 `new_unmaterialized` 카드를 신규 버킷 후보로. (R2) `mode=selected`(개인 id 최대 200, 목표 적용) |
| `backend/app/srs/queue_cursor.py` | 바인딩에 정규화한 제외 목록 해시 추가 |
| `backend/tests/test_srs_c2_server.py`(신규) | S·A 검사 |

순서:
1. 초기값 함수와 개인 카드 세 경로. legacy 계정·UPDATE 불변 검사 먼저.
2. 요청 정체성: 누락 vs 명시적 null 판별, 개인 URL null 422.
3. 구독 최초 평가 트랜잭션. 재시도, null↔0 충돌, 동시 두 요청(실제 스레드·별도 연결), 실패 주입 롤백, 구독 상실, legacy 계정.
4. 큐 `exclude_card`. 앞 10개 전부 제외 시 뒤 카드 반환, 범주 합계 불변.
5. 3단계 통과 뒤 미생성 카드 출제 활성화. 범주·정렬·커서 검사 재실행.
6. (R2 승인 시) `mode=selected`.
7. C-1·B-2·B-1 전체와 회귀 스크립트·감사.

## 3. C-2b·C-2c 클라이언트 변경 예정

| 파일 | 변경 |
| --- | --- |
| `frontend/components/studySession.ts`(신규, 순수) | 시도 객체, 결과 적용 4조건, 응답별 전이, 회차 미루기 집계(200 + 결과 단계 Learning·Relearning만 셈, 3회 → 제외), 주 상태 우선순위(CONTRACT 2-4), 활성 회차 판정 |
| `frontend/components/studySession.test.mts`(신규) | U 검사 |
| `frontend/app/page.tsx` | 모드 판별(409 `srs_mode_not_fsrs`만 legacy), `/study-queue` 어댑터(`exclude_card` 포함), 평가 시도 사용(legacy 계정은 기존 함수), 대기 타이머·앱 복귀, `beforeunload`(전송 중·결과 미확정일 때만 등록), 계획 실행기 어댑터(`inProgress` = 활성 회차) |
| `frontend/components/StudySection.tsx` | 최소 props: 시도 상태, 주 상태·보조 줄, 신규 목표 줄, 연습 표시. 기존 지면 유지 |
| `frontend/components/types.ts` | 큐 응답 타입 |
| `frontend/package.json` | `test`에 새 테스트 추가 |

바꾸지 않는 것: 읽기 저장 v3·학습 계획 저장 키, `planStudyLauncher.ts` 보호 규칙, legacy 계정 화면 경로, 에셋.

## 4. 중단 조건

- legacy 계정의 복습 화면·요청·응답이 바뀜. legacy 구독 평가(`expected_card_version` 키 없음)의 처리 순서가 바뀜.
- 기존 저장 키를 바꾸거나 새 키가 필요해짐.
- 늦은 응답이 새 계정·회차의 카드·진행 수·버튼·미루기 집계를 바꾸는 사례가 남음.
- 409를 받아 자동 재평가하는 경로가 생김.
- 구독 최초 평가에서 progress·로그·영수증 중 하나라도 중복되거나 일부만 남음. 누락된 필드를 null로 해석함.
- 큐가 생성 경로 없이 미생성 카드를 내보냄. `exclude_card`가 범주 집계를 바꾸거나 LIMIT 뒤에 적용됨.
- 신규 수 null·unknown을 0으로 보여 줌. 회차 화면에 "학습 완료"가 나타남.
- 연습에서 평가 POST·로그·영수증·카드 변경이 생김.
- FSRS 계정의 기존 legacy·불완전 이력 카드가 자동으로 바뀜.
- 409 `srs_mode_not_fsrs` 외의 오류로 legacy 전환이 일어남.
- 스키마 변경이 필요해짐(인덱스 포함).

## 5. 실행 안전

- 백엔드 테스트·스크립트·QA 서버는 import 전에 세션 전용 SQLite `DATABASE_URL`과 로컬 `APP_ENV`를 지정한다. Neon·운영·기존 로컬 DB에 접근하지 않는다.
- QA 서버는 기존 서버와 다른 포트에서 띄우고, 직접 띄운 서버·임시 DB·QA origin 저장 키만 정리한다.
- PostgreSQL은 보호 검사를 통과한 빈 로컬 테스트 DB만 쓴다. 없으면 미검증으로 보고한다.

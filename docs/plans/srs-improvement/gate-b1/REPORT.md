# Gate B-1 보고: 엔진 어댑터·완료 판정·추가형 저장 구조

작성: 2026-10-09, 보정: 2026-10-09(11절). 승인 근거: `APPROVAL_2026-10-09.md`. 시뮬레이션 상세: `SIMULATION.md`.
범위: Gate B-1만. 평가 API 전환, 동적 큐, 자료 이전 실행, 신규 목표 집행, 화면 변경, 운영 활성화는 하지 않았다. **스테이징·커밋·푸시·병합 없음. Gate B-2 미착수.**

## 0. 시작 상태

| 항목 | 값 |
| --- | --- |
| 시작 브랜치 / HEAD | `main` / `e2c07f8bcc534713587f628cf3f8f9f798bb2e5a` |
| 작업 브랜치 | `codex/fsrs-srs-replacement` 새로 생성(같은 HEAD에서). 다른 브랜치 전환·삭제 없음 |
| AGENTS.md | 저장소에 없음 |
| 기존 변경 | `docs/roadmap.md` 수정, 에셋·목업·`references/plans/`·`frontend/tsconfig.tsbuildinfo`·`docs/plans/srs-improvement/` 미추적. 손대지 않고 그대로 둠 |

## 1. 변경 파일

| 파일 | 내용 |
| --- | --- |
| `backend/requirements.txt` | `fsrs==6.3.2` 한 줄 추가 |
| `backend/app/database.py` | `ensure_srs_schema` import 1줄, `ensure_schema`의 PG·SQLite 분기에서 각 1회 호출(+주석). 그 외 변경 없음 |
| `backend/app/srs/__init__.py` (신규) | 패키지 설명. 엔진을 import하지 않음 |
| `backend/app/srs/engine.py` (신규) | 순수 엔진 어댑터 |
| `backend/app/srs/completion.py` (신규) | 학습 완료 판정 초안, 재생 도우미 |
| `backend/app/srs/schema.py` (신규) | SQLite/PG 추가형 컬럼·테이블·인덱스 |
| `backend/tests/test_srs_engine.py` (신규) | 엔진 26개 (보정 후) |
| `backend/tests/test_srs_completion.py` (신규) | 완료 판정 21개 (보정 후) |
| `backend/tests/test_srs_schema.py` (신규) | 스키마·보존·legacy 4개 + PG 1개(opt-in) |
| `backend/scripts/simulate_srs_completion.py` (신규) | 합성 시뮬레이션 재현 스크립트 |
| `docs/plans/srs-improvement/gate-b1/REPORT.md`, `SIMULATION.md` (신규) | 이 보고와 시뮬레이션 결과 |

`frontend/`, `page.tsx`, 학습 계획·통계·읽기 저장 v3, 기존 평가·출제 경로, 기존 테스트 기대값은 바꾸지 않았다.

## 2. fsrs 6.3.2 설치·확인 [실행 확인]

- `pip download fsrs==6.3.2 --no-deps --only-binary=:all:` → wheel sha256 `bc55066c821164b1cff6d75b17a3ed8e86cfd45789e3d775cfcb895319ce9ba4`. Gate A에서 기록한 PyPI 값과 일치.
- `pip install --no-deps --require-hashes --no-index` 로 그 wheel만 설치. `pip show`: 6.3.2, MIT License, Requires typing-extensions(이미 4.16.0 설치). `pip check` 이상 없음.
- optimizer extra(torch/numpy/pandas) 미설치 확인(`import torch` 실패).
- 로컬 Python 3.14.6에서 import·실행 정상. 실행 결과 기본 파라미터 21개, decay 0.1542.
- `requirements.txt`는 버전만 고정했다(해시 고정 아님). 배포 시 해시까지 고정할지는 선택 사항.
- **운영 Python 버전: 미확인.** 저장소에 `runtime.txt`·`.python-version`·`render.yaml`이 없고 `Procfile`만 있다. Render 쪽 설정은 보지 않았다(운영 환경 변경·조회 없음). fsrs 요구 조건은 Python >=3.10.

## 3. 엔진 어댑터 (`app/srs/engine.py`)

- 설정 `DEFAULT_CONFIG`: 라이브러리 기본 파라미터, 유지율 0.90, 학습 (60초, 600초), 재학습 (600초), 최대 365일, fuzz 끔. `config_version = fsrs-6.3.2-a1-362bc5407f76` (라이브러리·어댑터 버전과 설정 JSON의 sha256 앞 12자리). 설정이 하나라도 바뀌면 버전이 바뀐다.
- `build_scheduler`는 설치 버전이 6.3.2가 아니거나 fuzz가 켜진 설정이면 거부하고, 만든 scheduler의 설정이 config와 같은지 확인한다. `review()`는 외부 scheduler를 받지 않고 기록할 config로만 계산한다(11절).
- `review(key, state, rating, reviewed_at)`: 시각·상태를 인자로만 받는 순수 함수. 시계·난수·DB 접근 없음. 간격·S·D는 라이브러리 계산 그대로이며 손으로 만든 식이나 보정이 없다.
- 미학습 카드는 `state=None`. 라이브러리에는 New 상태가 없으므로(새 Card는 Learning/0, 즉시 due) 제품 쪽 '신규 후보'와 섞이지 않게 분리했다.
- 카드 정체성은 `CardKey(kind, user_id, ref_id)`. 라이브러리의 정수 card_id는 로그 표시용일 뿐이며, 개인 5번과 구독 lexeme 5번은 별개 결과를 낸다(테스트).
- 입력 검증: tz 없는 시각, 직전 평가보다 이른 시각, 알 수 없는 등급, Review인데 step 있음, NaN/범위 밖 S·D, due < last_review, 잘못된 kind/ID → `SrsEngineError`, 계산 없음. KST 등 다른 tz는 같은 순간의 UTC로 바꿔 계산.
- 직렬화: `state_to_dict/json` ↔ `state_from_dict/json`. 키가 정확히 6개가 아니거나 값이 잘못되면 거부. 역직렬화한 상태로 이어서 평가해도 결과 동일(테스트).

실제 엔진 결과(첫 평가, `test_srs_engine.py`):

| 미학습 카드 첫 평가 | 단계 | 다음 |
| --- | --- | --- |
| 다시 | Learning/0 | 1분 |
| 어려움 | Learning/0 | 5분 30초 |
| 보통 | Learning/1 | 10분, 그 시각 보통이면 Review 진입 후 2일 |
| 쉬움 | Review | 8일 |

그 외 실행 확인: Review 다시 → Relearning/0 10분(S 감소), Relearning 어려움 15분, 보통이면 Review 복귀. 같은 카드 재평가가 24시간 미만이면 UTC·서울 자정을 넘어도 단기 안정도 경로를 탄다(달력 날짜가 아니라 경과 시간 기준). 200일 연체 후 보통과 연속 쉬움 모두 간격 365일을 넘지 않는다. fuzz를 껐으므로 같은 입력은 같은 결과.

## 4. 학습 완료 판정 (`app/srs/completion.py`) — 테스트용 초안

`METRIC_VERSION = meaning-completion-v1-draft`. C1 Review, C2 S>=30일, C3 마지막 다시 이후 서울 날짜 2개에서 성공(어려움 포함), C4 그중 1회 이상은 바로 앞 평가와 UTC 7×24시간 이상 간격.

- 결과는 `completed / not_completed / unknown` 세 가지다. 증거가 완전하고 마지막 평가 시각이 상태와 맞으면 완료 또는 미완료로 정한다. 불완전하면 C3·C4를 증명된 것으로 보지 않는다. 현재 상태가 C1·C2를 못 넘을 때만 미완료, 그 밖은 `unknown`이며 **완료는 반환하지 않는다**(11절에서 보정).
- 엔진 상태가 없거나 상태와 마지막 평가 시각이 맞지 않으면 `unknown`.
- `summarize_completion`: `first_completed_at`은 이후 실패·보류·재개로 지워지지 않는다. 실패하면 `needs_relearning`, 보류하면 진도 분자에서 빠지고(`counts_toward_progress=False`), 재개하면 다시 센다.
- 테스트로 확인한 경계: 첫 쉬움 1회와 같은 날 반복은 미완료, 7일 정확히는 인정·1초 모자라면 불인정, 간격은 "바로 앞 평가"에서 잰다, 다시 이전 성공은 무효, 어려움도 성공, 서울 23:59와 00:01은 다른 날짜(같은 UTC 날짜여도), 순서가 뒤바뀐 기록은 거부.

## 5. 합성 시뮬레이션 결과 [실행 확인, 합성 패턴]

실제 엔진으로 첫 평가부터 매 평가 뒤 완료를 판정했다. 평가 패턴은 가상이다. 아래 수치는 스케줄러와 완료 규칙의 동작이며 **학습 효과가 아니다.** 상세 행은 `SIMULATION.md`.

| 시나리오 | 결과 | 평가 수 | 경과 | 그때 S |
| --- | --- | --- | --- | --- |
| 매번 due에 보통 | 도달 | 4 | 13일 | 46.3일 |
| 매번 due에 쉬움 | 도달 | 2 | 8일 | 65.6일 |
| 첫 평가부터 매번 어려움 | **미도달 (40회 관측 종료)** | 40 | 0.1일 | 1.3일 |
| 보통 2회로 Review 진입 후 매번 어려움 | 도달 | 5 | 29일 | 35.8일 |
| 첫 평가 다시, 이후 보통 | 도달 | 7 | 29일 | 48.3일 |
| 4번째만 다시, 나머지 보통 | 도달 | 9 | 60일 | 59.7일 |
| 보통으로 완료(4번째) 직후 다시, 이후 보통 | 도달 → 미완료 → 재도달 | 9 | 89일 | 41.7일 |
| 어려움·보통 번갈아 | 도달 | 9 | 46일 | 33.9일 |
| 매번 due보다 3일 늦게 보통 | 도달 | 3 | 20일 | 63.2일 |
| 같은 날 10분마다 보통 20회 | **미도달 (관측 종료)** | 20 | 0.1일 | 2.3일 |

관찰:
1. **쉬움 두 번이면 8일 만에 완료**된다. 첫 쉬움 → 8일 뒤 쉬움에서 S 65.6일, 서울 날짜 2개, 8일 간격이 모두 충족된다. "첫 쉬움 한 번으로는 완료 불가"는 지켜지지만, 기준이 꽤 빨리 충족된다.
2. 보통만 누르면 4번째 평가(13일째)에서 S가 10.97일 → 46.3일로 뛰며 네 조건이 동시에 충족됐다. 3번째까지는 S와 7일 간격 조건이 함께 막고 있었다.
3. **학습 단계에서 어려움만 누르면 단계를 벗어나지 못한다.** 6.3.2 규칙상 Learning에서 어려움은 단계를 유지하므로(0단계 5.5분, 1단계 10분) 카드가 계속 짧은 간격으로 돌아온다. 엔진을 고칠 일은 아니지만, Gate C 큐·화면에서 이 반복을 어떻게 보여 줄지 정해야 한다.
4. 같은 날 반복은 S가 거의 오르지 않고 C3·C4로도 막혀 완료되지 않는다.
5. 완료 후 다시를 누르면 현재 완료에서 빠지고(`first_completed_at` 유지), 보통을 이어 가면 4회·30일 뒤 재완료된다.

## 6. 추가형 저장 구조 (`app/srs/schema.py`)

`init_db()`의 기존 스키마 생성 뒤에 멱등으로 실행된다. 기존 행을 고치거나 채우거나 지우지 않는다.

카드 테이블 `vocab_items`(개인), `user_word_progress`(구독)에 추가:

| 컬럼 | 제약·기본값 | 용도 |
| --- | --- | --- |
| `srs_engine` | NOT NULL DEFAULT 'legacy', CHECK legacy/fsrs | 모든 기존 카드는 legacy |
| `srs_config_version` | NULL | 계산 설정 |
| `srs_state` | NULL, CHECK 1/2/3 (fsrs.State 값) | NULL = 미학습/FSRS 아님 |
| `srs_step` | NULL, CHECK >= 0 | |
| `srs_stability`, `srs_difficulty` | REAL(PG DOUBLE PRECISION) NULL | |
| `srs_due_at`, `srs_effective_due_at`, `srs_last_review_at` | TEXT NULL (기존과 같은 UTC ISO 텍스트) | 계산 due와 실제 출제 due 분리(기존 예약 보호용) |
| `srs_card_version` | NOT NULL DEFAULT 0 | 이후 CAS용 |
| `srs_participation` | NULL, CHECK active/paused | **NULL = 아직 이전 안 됨.** 스키마가 known을 보류로 옮기지 않는다 |
| `srs_pause_reason` | NULL | |
| `srs_history_quality` | NULL, CHECK complete/incomplete/fresh | |
| `srs_history_flags` | NULL | 의심 표시(판정에 쓰지 않음) |
| `completion_metric_version`, `first_completed_at` | NULL | |

로그 테이블 `review_logs`, `lexeme_review_logs`에 모두 NULL 허용 컬럼 추가: `request_id`, `srs_engine`, `srs_config_version`, `card_version_before`, `srs_before_json`, `srs_after_json`, `seoul_date`, `is_first_review`. 기존 로그 한 행은 여전히 평가 한 회다.

새 테이블(시작 시 행을 만들지 않음):
- `srs_config_versions`: 설정 버전 → JSON(재현용).
- `srs_user_settings`: user_id PK(FK users), `srs_mode` legacy/shadow/fsrs 기본 legacy, `daily_new_goal` 기본 20·CHECK 0~500, `settings_version`. 행이 없으면 legacy.
- `srs_review_receipts`: UNIQUE(user_id, request_id), card_kind personal/lexeme, request_hash, response_json, review_log_id.
- `srs_migration_runs`: run_key UNIQUE, mode dry_run/apply/rollback, status, scope·엔진·설정 버전, summary.
- `srs_migration_snapshots`: run별 카드 legacy JSON·SRS 전후·이력 품질·의심 표시, UNIQUE(run_id, card_kind, card_ref).
- 신규 예약 테이블은 만들지 않았다(승인 6번, S2 후속).

인덱스: 두 카드 테이블 `(user_id, srs_engine, srs_participation, srs_effective_due_at)`, 로그 `(user_id, 카드, 시각, id)`(이력 재생 순서), 스냅샷 카드 조회.

주의(기존 코드 관찰):
- SQLite의 `migrate_vocab_unique_constraint`는 아주 오래된 UNIQUE 형식 DB에서 `vocab_items`를 다시 만든다. SRS 스키마는 그 뒤에 실행되므로 컬럼은 다시 붙지만, 그 재구성 경로가 SRS 값을 옮기지는 않는다. 해당 형식의 DB는 SRS 값이 생기기 전 시대의 것이라 이번 범위에서는 영향이 없다.
- PG의 기존 `review_logs`는 `vocab_items` 삭제 시 CASCADE로 지워진다(기존 동작, 이번에 바꾸지 않음). 이전 계약의 "삭제된 카드 로그 보존"은 SQLite에서만 그대로 성립한다. Gate B-2에서 다룰 위험으로 남긴다.

## 7. 자료 보존·legacy 검증 [실행 확인, 합성 SQLite]

`test_srs_schema.py`:
- **업그레이드 보존**: SRS 스키마 없이 `init_db()` → 실제 저장소 함수로 개인 3장(unknown/uncertain/known, 평가 3건)과 구독 3단어(쉬움→known 자동, 다시, 수동 known)를 만든다 → 스냅샷 → 새 코드로 `init_db()` 2회 → users·decks·vocab_items·lexemes·shared_decks·shared_deck_words·구독·progress·두 로그 테이블의 **기존 컬럼 값이 모든 행에서 동일**. 새 컬럼은 legacy/NULL/0, known은 known 그대로이고 participation은 NULL. 새 테이블 행 0.
- **새 DB·재실행**: 컬럼·테이블 생성, 재실행 멱등, 예약 테이블 없음, 시작 시 행 생성 없음.
- **제약**: 잘못된 engine/state/step/participation/quality, 하루 목표 501, 같은 request_id 영수증 중복이 모두 거부됨. 설정 행 기본값 legacy/20.
- **legacy 평가 불변**: 업그레이드 뒤 개인 평가 결과가 `compute_review_schedule`과 같고, 구독 평가의 기존 자동 분류도 그대로다. 평가 뒤에도 SRS 컬럼은 legacy/NULL/0, 로그 새 컬럼은 NULL이다.

## 8. 테스트·회귀 실행 결과

| 실행 | 결과 |
| --- | --- |
| `python -m unittest discover -s tests` (백엔드 전체) | 보정 후 107개 통과, 1개 건너뜀(PG opt-in). 보정 전 97개 |
| 그중 새 테스트 | 보정 후 엔진 26, 완료 21, 스키마 4 통과 / PG 1 건너뜀 |
| `docs/plans/srs-improvement/audit_current_srs.py` | 15/15 (현재 legacy 동작 그대로) |
| `check_shared_deck_srs_regression`, `check_lexeme_srs_status_policy_regression`, `check_lexeme_review_logs_regression`, `check_lexeme_stats_regression`, `check_postgres_boolean_sql_compat`, `smoke_test_shared_lexeme_progress`, `check_database_safety_guard` | 7개 모두 exit 0, FAIL 없음 |
| 프론트 `npm test` | 73개 통과 |
| 프론트 `npm run typecheck` | 오류 없음 |
| `git diff --check` + 새 파일 끝 공백 검사 | 깨끗함 |

프론트를 수정하지 않았으므로 build는 실행하지 않았다.
모든 DB 실행은 세션 전용 SQLite로만 했다. 테스트·스크립트는 각자 임시 파일로 `DATABASE_URL`을 덮어쓰고, 셸에도 미리 스크래치 SQLite를 지정했다. Neon·운영·`backend/vocab.db`·기존 로컬 DB에는 접근하지 않았다. 서버는 띄우지 않았다.
정리: 이번 실행으로 새로 생긴 임시 DB 5개와 로그를 지웠다. 실행 전부터 있던 같은 이름의 회귀용 임시 DB 2개는 그대로 두었다. wheel 사본은 세션 스크래치에만 있다.

## 9. 재승인이 필요한 항목

1. **학습 완료 기준 v1** (시뮬레이션 5절 근거): 쉬움 2회·8일, 보통 4회·13일이면 완료된다. 이대로 둘지, S 문턱·성공 날짜 수·간격 조건을 올릴지 결정이 필요하다.
2. **학습 단계에서 반복 어려움**: 엔진 규칙상 단계를 벗어나지 못한다. Gate C에서 큐가 이 카드를 어떻게 다룰지(같은 세션 반복 상한, 안내 문구 등) 정해야 한다. 엔진 동작은 바꾸지 않는다.
3. 표시용 `METRIC_VERSION`은 `meaning-completion-v1-draft`로 두었다. 재승인 뒤 `-draft`를 뗀다.

## 10. 미검증과 다음 단계 위험

- **PostgreSQL**: 이 기기에 로컬 PostgreSQL이 없다(서비스·5432 포트·psql 없음). PG DDL은 작성했고 opt-in 테스트(`SRS_SCHEMA_TEST_POSTGRES_URL`, 기존 보호 검사 사용)도 넣었지만 **실행하지 않았다.** 설치나 원격 우회도 하지 않았다.
- **운영 Python 버전**: 미확인(2절).
- 평가 API·영수증·CAS·이전 도구는 구조만 있고 연결하지 않았다(Gate B-2).
- PG 로그 CASCADE 삭제와 이전 계약의 차이(6절).
- `requirements.txt`의 해시 미고정.
- 실제 학습 효과·예측 정확도는 합성 데이터로 판단하지 않았다.

## 11. 보정 (2026-10-09)

두 결함을 보정 전 코드에서 재현한 뒤 고쳤다. 완료 네 조건과 엔진 설정(6.3.2, 0.90, 1분·10분, 재학습 10분, 365일, fuzz 끔)은 바꾸지 않았다. 완료 기준은 여전히 시뮬레이션용 초안이며, 이번 보정은 기준 승인이 아니다. 운영 경로는 legacy 그대로다.

### 11-1. 불완전 이력의 완료 오판정

- 재현 [실행 확인, 보정 전 코드]: 쉬움 → 6일 뒤 어려움 → 8일째 쉬움. 실제 엔진 상태는 Review, S 34.8일. 전체 이력으로는 `not_completed`(실제 간격 6일·2일). 가운데 어려움을 빼고 `evidence_complete=False`로 넘기면 `completed`. 빠진 평가 때문에 직전 간격을 8일로 오인했다.
- 원인: 불완전 이력에서도 남아 있는 평가만으로 C3·C4가 충족되면 완료로 판정했다. 빠진 평가가 다시(Again), 성공 날짜, 더 짧은 직전 간격을 가릴 수 있다는 점을 반영하지 못했다.
- 변경 계약: 불완전 이력에서는 성공 날짜, 직전 평가 간격, 마지막 다시 이후 이력을 증명된 것으로 보지 않는다(`success_dates_ok`·`spaced_success_ok` = 미확인). 신뢰 가능한 현재 상태가 C1(Review)·C2(S>=30)를 못 넘으면 `not_completed`, 그 밖은 `unknown`이며 `completed`는 반환하지 않는다. 증거가 완전해도 마지막 평가 시각이 상태와 다르면 `unknown`이다. 신뢰 가능한 연속 구간을 증명하는 기능은 추가하지 않았다.
- 기존 테스트 수정: 일부 이력만으로 완료를 허용하던 `test_partial_evidence_that_already_proves_completion`을 `test_partial_evidence_never_proves_completion`(결과 `unknown`)으로 바꿨다.
- 추가 회귀 5개(`IncompleteHistoryRegressionTests`): 중간 평가 누락으로 생긴 거짓 7일 간격(보고된 사례), 중간 다시 누락, 오래된 이력과 최신 상태의 불일치(완전·불완전 모두 완료 아님), 불완전 이력의 확인 불가와 명백한 미완료, 완전한 정상 이력의 완료와 최초 완료 기록 보존.

### 11-2. 엔진 설정과 기록 설정 불일치

- 재현 [실행 확인, 보정 전 코드]: 유지율 0.99로 만든 scheduler를 기본 config와 함께 `review()`에 넘기면 0.99 기준 예약(3일)이 계산되는데, 결과의 `config_version`은 기본 설정 값으로 기록됐다.
- 원인: `review()`가 계산에는 외부 scheduler를 쓰고, 기록에는 별도 인자 config를 썼다.
- 변경 계약: `review()`의 `scheduler` 인자를 없앴다. 계산은 기록하는 바로 그 config로 만든 scheduler로만 한다. 이 scheduler는 config를 키로 하는 모듈 내부 캐시에 두며 밖으로 내주지 않는다. `build_scheduler`는 라이브러리 버전 검사 후 fuzz가 켜진 config를 거부하고, 만든 scheduler의 설정(`to_dict`)이 config와 같은지 확인한다. `preview_due`, `retrievability`, `replay_with_completion`, 시뮬레이션 스크립트도 같은 경로를 쓴다. 라이브러리 수식은 다시 구현하지 않았다.
- 추가 회귀 5개(`ConfigSourceTests`): 외부 scheduler 인자 거부, 0.99 config의 예약·기록 버전이 그 config와 일치(라이브러리 직접 계산과 같은 due, 기본 설정보다 이른 due), scheduler 설정 = config, fuzz config 거부, 버전이 다르면 첫 평가 전에 거부.

### 11-3. 검사 결과 [실행 확인]

| 실행 | 결과 |
| --- | --- |
| `tests/test_srs_engine.py` | 26개 통과 (기존 21 + 회귀 5) |
| `tests/test_srs_completion.py` | 21개 통과 (기존 16, 1개 계약 수정 + 회귀 5) |
| `python -m unittest discover -s tests` | 107개 통과, PG 1개 건너뜀 |
| `audit_current_srs.py` | 15/15 (legacy 그대로) |
| `simulate_srs_completion.py` | `SIMULATION.md`와 결과 동일(완전 이력만 쓰므로 영향 없음) |
| `git diff --check` + 새 파일 끝 공백 | 깨끗함 |

저장 구조(`schema.py`, `database.py`)는 이번에 건드리지 않았다. SQLite 업그레이드 보존과 기존 평가 회귀는 전체 실행에 포함된 `test_srs_schema.py` 4개로 다시 통과했다. 프론트는 바꾸지 않아 프론트 테스트는 다시 돌리지 않았다. 모든 실행은 세션 전용 SQLite만 썼고, 이번 실행으로 생긴 임시 DB는 지웠다.

### 11-4. 미검증과 후속 필수 과제(이번에 구현하지 않음)

- PostgreSQL 스키마 실행: 여전히 미검증(로컬 PG 없음).
- **PostgreSQL 로그 보존**: PG의 `review_logs`는 `vocab_items` 삭제 시 CASCADE로 지워진다. 이력 보존 계약과 맞추는 작업은 후속 필수 과제다.
- **학습 단계 반복 어려움의 세션 보호**: Learning에서 어려움을 반복하면 단계를 벗어나지 못한다(5절 관찰 3). 큐·세션에서 다루는 작업은 후속 필수 과제다.
- 운영 Python 버전 미확인, 완료 기준 재승인 대기(9절)는 그대로다.

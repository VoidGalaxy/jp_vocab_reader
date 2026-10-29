# 구독 카드 접근 판정 잠금(LQ1) 실제 로컬 PG 검증 계획 (2026-10-29, PG18.6 로컬 검증·독립 검토 마감)

**현재 상태(2026-10-29)**: V1 합성 검토와 V2~V4의 PostgreSQL 18.6 실제 로컬 검증·정리·보관을 독립 검토했다(13~15절). 실행 `20261029T170041`의 본 검사 24/24, D1 분기 P, 관문·사후 확인 통과를 확인했다. `LQ4_CHANGES_APPROVED = True`는 14절의 1회 실행 승인 기록이며 재실행·운영 허가가 아니다. 미검증 범위는 14-1·15절에 유지한다.

최초 작성 기준 체크포인트는 `ed247c1`(브랜치 `codex/fsrs-srs-replacement`)이다. 1~10절은 작성 당시 계획과 정적 검토 기록이며, 뒤의 결정·구현·실제 실행 기록으로 현재 상태를 구분한다. V1은 가짜 서버와 시험 전용 임시 OpenSSH 키를 썼고, 실제 PG 준비·검사·GRANT는 14절 승인에 따른 별도 실행이었다.

정책·계약은 `OPS_MIGRATION_RESUME_LEXEME_RACE_PLAN.md` 9절(LQ1-a~f)과 11절(구현 계약: 쓰기 경로의 `ORDER BY subscriptions.id, words.id LIMIT 1 FOR SHARE OF subscriptions, words`, 5초 `lock_timeout`의 비완화·복원 규칙, `55P03` → `migration_access_lock_timeout`, `40P01` → `migration_access_deadlock`, 두 열 `UPDATE` 권한)을 그대로 따른다. 여기서 다시 정의하거나 완화하지 않는다. 5초는 **잠금 하나를 얻는 대기의 상한**이다. 카드 처리 전체 시간이나, 그 앞 단계인 `users`·카드 잠금의 대기를 제한한다고 판정하지 않는다.

이 계획의 결과는 L-2(9/9)·RS4·C12 결과와 합산하지 않는다.

표기: **[코드]** 정적으로 확인한 사실, **[제안]** 승인 전 제안, **[미검증]** 아직 확인하지 않은 것.

## 1. 대상 후보 [제안]

| 항목 | 제안 값 | 정적 충돌 확인 [코드] |
| --- | --- | --- |
| 프리셋 | `PG68_LEXEME_ACCESS_LOCK`(`_ops_pg62.py`의 `Target`, `PRESETS`에 등록) | `PRESETS`에는 PG62~PG67만 있다. 이름 `pg68`은 저장소 어디에도 없다 |
| 폴더 | `C:/JV_Tools/pg68`(`data`·`tls`·`runs`) | `C:/JV_Tools`에는 `pgdata-e2`, `pgsql-18.6`, 설치 zip만 있다. `pg68`은 없다 |
| 포트 | 55522 | 코드에 등록된 포트는 55432(`pgdata-e2`, 그 `postgresql.conf`), 55462·55463·55472·55473·55482·55483·55492·55502·55512다. 55522는 없다. 실제 리스너 여부는 준비 단계의 기존 검사로 다시 확인한다 |
| 관리자 역할 | `jpvk_admin`(부트스트랩) | 기존 접두사는 `jpva_`·`jpvb_`·`jpvl_`·`jpvm_`·`jpvr_`다. `jpvk_`는 없다 |
| 소유자 역할 | `jpvk_owner` | 위와 같다 |
| 업무 역할 | `jpvk_read`, `jpvk_write` | 위와 같다 |
| 템플릿 DB | `jp_vocab_test_access_lock_tpl` | `access_lock_` 이름은 없다. 기존 이름은 `_62a/b`·`audit_`·`br_`·`apply_`·`resume_`·`resume_lex_`다 |
| 검사 DB | `jp_vocab_test_access_lock_<검사 ID>`(4절 ID) | 위와 같다 |
| 대상 문서 | `docs/plans/srs-improvement/gate-e/PG68_TARGET.md` | 없음. 실행기 구현 단위에서 함께 만든다 |

등록은 값만 정한다. 등록으로는 아무것도 만들어지지 않는다(PG67과 같다).

## 2. 시험 장치 설계

### 2-1. 재사용 범위 [코드 확인]

| 장치 | 위치 | 대상 결속 방식 | 재사용 판단 |
| --- | --- | --- | --- |
| `Target`·`preset`·`Record`·`single_run`·`Guard`·`server_is_ours`·`listener_pids`·`admin_connect`·`pg_environment_present` | `tests/_ops_pg62.py` | 대상 객체를 인자로 받는다. `preset`은 등록된 객체 자체만 허용한다(같은 값의 복사본은 거부) | 새 `Target` **등록**이 필요하다. 함수는 바꾸지 않는다 |
| `Layout`·`layout()`·`LAYOUTS` | `tests/_ops_real_layout.py` | `layout()`이 등록된 객체만 허용한다 | 새 `Layout` **등록**(`PG68`)과 `LAYOUTS` 추가가 필요하다 |
| `expected_profiles`·`contract_grants`·`grant_statements`·`variant_statements`·`require_target_bound`·`require_ours`·`business_check`·`post_connect_check`·`admin`·`hba`·`conf`·`prepare`·`cleanup`(R2) | `_ops_real_layout.py` | 모두 `Layout`을 첫 인자로 받는다. 대상 전역값을 읽지 않는다 | 그대로 재사용한다(PG67 실행기와 같은 방식) |
| `build_template` | `_ops_real_layout.py` | `Layout`을 받지만 공통 `SEED`만 넣는다(모든 대상에 같은 자료) | 그대로 호출한다. 두 번째 덱 자료는 **공통 `SEED`를 바꾸지 않고**, PG68 실행기의 자체 `build_fn`이 `build_template` 뒤에 별도 문장으로 넣고 별도 이벤트로 기록한다. 공통 `SEED`를 바꾸면 PG65~67 템플릿이 바뀌므로 금지한다. **템플릿에 넣은 자료는 모든 복제 DB로 전달된다.** 그래서 두 번째 경로는 템플릿에서 비활성으로 만들고, 정해진 DB에서만 준비 단계에 활성화한다(4-0) |
| `Counts`·`Tracked`·`TrackedCursor`·`counted_connector`·`RunScopes` | `_ops_real_layout.py` | `Layout`을 받는다. 스레드마다 계수를 나눈다 | 재사용한다. SQLSTATE 기록(2-3)은 PG68 실행기의 하위 클래스로만 더한다 |
| `Pause`·`wait_blocked`·`race` | `_ops_real_layout.py` | 대상 무관 | `Pause`·`wait_blocked`는 재사용한다. `race`는 동작 참조이며 PG68의 실행 조정은 2-5의 전용 함수가 맡는다. 기존 `race`는 수정하지 않는다 |
| `run_recorded`(저장·재읽기 뒤에만 통과), `content_hashes`, `run_facts` | `_ops_real_layout.py` | 대상 무관 | 재사용한다 |
| `ResumeTracked`·`label`·`Values` | `tests/_ops_resume_real.py` | 대상 무관 계측만(PG67 실행기도 이 부분만 쓴다) | 재사용한다 |
| `Harness`(case·resume_inputs·driver·state·outside·observe_role·`revert_and_observe`) | `tests/_ops_resume_lexeme_real.py` | 모듈 상수 `LAYOUT = lay.PG67`, `T`, `CHECK_DB`, `RUN_KEY`, 카드 이름 집합에 묶여 있다 | **import만으로는 재사용할 수 없다.** 대상 전역값을 바꿔치기하지 않는다. 필요한 메서드는 PG68 실행기에 같은 규칙으로 새로 둔다. 공통으로 뺄 가치가 있는 것(예: `observation_close`)은 별도 분리 단위로 제안만 한다 |

### 2-2. 후속 시험 코드의 변경 파일 [제안]

- `tests/_ops_pg62.py`: `PG68_LEXEME_ACCESS_LOCK_CHECK_IDS`, `PG68_LEXEME_ACCESS_LOCK`, `PRESETS`에 추가(등록만).
- `tests/_ops_real_layout.py`: `PG68_VARIANTS`·`PG68_VARIANT_DATABASES`(3절의 닫힌 권한 변형), `PG68 = Layout(...)`, `LAYOUTS`에 추가. 공통 함수·`SEED`·`WAIT_LIMIT`은 바꾸지 않는다.
- 새 `tests/_ops_access_lock_real.py`: 명시 실행(`prepare`·`check-access-lock`·`cleanup`), discovery·import로는 아무것도 하지 않는다. 승인 상수 `LQ4_CHANGES_APPROVED: bool | None = None`(관리자 변경·권한 변형용, 값 변경은 별도 승인).
- 새 `tests/test_ops_access_lock_real_guard.py`: PG·프로세스·키 생성·리스너·관리 연결을 막은 가짜 보호 검사.
- 새 `docs/plans/srs-improvement/gate-e/PG68_TARGET.md`: 대상 문서(배포 manifest에 등록되는 파일).
- PG65·66·67 보존 확인(정정): "기존 검사 수정 없이 통과"는 성립하지 않는다. [코드] 닫힌 목록 전체를 단언하는 곳이 있어, PG68 등록 때 그 목록 단언만 바뀌어야 한다.
  - 변경 허용(목록 끝에 새 객체 하나를 더하는 것만):
    - `tests/test_ops_apply_real_guard.py:89` `g.PRESETS` 전체 튜플
    - `tests/test_ops_audit_real_guard.py:85` `g.PRESETS` 전체 튜플
    - `tests/test_ops_backup_real_guard.py:56` `g.PRESETS` 전체 튜플
    - `tests/test_ops_real_layout.py:102` `lay.LAYOUTS` 전체 튜플
  - 바꾸지 않는 것: 기존 객체의 값·순서, 대상 보호(복사본 거부·이름 분리), GRANT, 프로필, 권한 변형, 기준 파일(`ops_pg65_preserve.json`과 해시), 그 밖의 기대값. 새 대상 등록을 이유로 보호 기대값을 완화하거나 목록 단언을 지우지 않는다.
  - 변경 없이 더 엄격해지는 것: `test_ops_real_layout.py:121`·`:137`의 PG66·PG67 이름 분리 검사는 `g.PRESETS`를 순회하므로, PG68이 등록되면 자동으로 PG68과의 분리까지 검사한다.
  - 나머지 보호 검사(`test_ops_resume_real_guard.py`, `test_ops_resume_lexeme_real_guard.py`, `test_ops_real_layout.py`의 다른 항목)는 수정 없이 통과해야 한다. 새 보호 검사는 PG68의 이름이 다른 모든 프리셋과 분리되는지 같은 방식으로 단언한다.

### 2-3. 실제 경로와 정지점 [제안]

- 실제 경로: 실제 CLI(`run_dry_run`·`run_apply`·`run_resume`), 실제 공급자(어댑터·관측·판정·재판정), 실제 제품 `apply_plan`·`_authorized`를 쓴다. 승인·서명은 기존 합성 방식(시험 전용 임시 OpenSSH 키)이다.
- 정지점: 기존 `Pause` 훅(`Tracked.run`의 문장 실행 **뒤** 호출)을 쓴다. 정지점은 원래 함수를 호출하고, 반환값·예외를 바꾸지 않는다.
  - 판정 전: 카드 `FOR UPDATE` 문장(`SELECT * FROM user_word_progress … FOR UPDATE`) 뒤
  - 판정 뒤·쓰기 전: 접근 잠금 문장(`… FOR SHARE OF subscriptions, words`) 뒤
  - 쓰기 뒤·커밋 전: 실행 요약 `UPDATE srs_migration_runs SET summary_json …` 뒤(카드 트랜잭션의 마지막 문장)
- SQLSTATE 기록: PG68 실행기의 `Tracked` 하위 클래스가 업무 문장의 예외에서 `sqlstate`만 기록하고, 같은 예외를 그대로 다시 던진다. 드라이버 원문은 기록하지 않는다.
- 설정 문장 기록: 같은 하위 클래스가 `set_config('lock_timeout', …)` 문장의 매개값(설정 값, 비밀 아님)과 성공 여부를 기록한다. 업무 트랜잭션 안에서 상태를 읽는 탐침 SQL은 넣지 않는다(실패하면 업무 트랜잭션이 깨진다, 6절 결정 E5).

### 2-4. 계수·기록의 분리와 탐침 규칙 [제안]

- 계수는 넷으로 나눈다.
  - 관측: 공급자의 관측 문장. 기존처럼 인계 전이라 업무 계수에 들지 않는다.
  - 업무: 인계 뒤 제품 문장·쓰기·커밋. 기존 `Counts`
  - 관리자 변경: 관리 연결 이벤트. 변경 이름, 대상 행 키, 문장 이름, 영향 행 수, 커밋·롤백
  - 탐침: 별도 관리 연결의 `pg_blocking_pids`·`pg_locks`·`pg_stat_activity` 읽기. 업무 연결에서는 실행하지 않는다.
- 기록 이벤트도 나눈다: `check_run`(CLI 보고), `check_admin_state`(관리 조회 상태), `admin_change`, `lock_wait_proof`, `sqlstate_seen`, `revert_observation`(원복 뒤 공급자 재관측, 별도 계수).
- 탐침 규칙:
  - 탐침 예외는 기록만 하고 업무 스레드로 전달하지 않는다. 그 검사는 탐침이 끝난 뒤 `harness_defect`로 판정한다.
  - 탐침 실패가 있어도 정지점은 반드시 해제하고, 스레드는 `join`하고, 업무 연결의 원래 종료(커밋·롤백·닫기)는 제품 경로가 하도록 둔다. 탐침이 업무 연결을 닫거나 롤백하지 않는다.
  - 업무 스레드의 원래 예외는 그대로 보존해 판정에 쓴다. 탐침 예외로 덮지 않는다.
  - 기한(`WAIT_LIMIT`) 안에 스레드가 끝나지 않으면 2-5에 따라 소유 연결 닫기 뒤 제한된 추가 join으로 종료를 재확인한다. 끝내 확인되지 않으면 `harness_defect`와 정리 미완료로 기록하고 파괴적 정리를 막는다.

### 2-5. 작업 스레드 종료 확인 [코드 확인 + 제안]

- [코드] 기존 `race`(`_ops_real_layout.py`)는 `finally`에서 정지점을 해제하고 각 스레드를 `join(limit)`한다. 그래도 살아 있는 스레드가 있으면 호출자가 준 `close_all()`로 연결을 닫고 곧바로 `CheckFailed("harness_defect", "a contention thread did not end")`를 낸다. 닫은 뒤 스레드가 실제로 끝났는지는 다시 확인하지 않는다. PG67 실행기는 `close_all`에 하네스의 모든 연결 닫기를 넘긴다.
- PG68에 필요한 종료 절차 [제안]:
  1. 정지점을 해제한다(성공·실패·예외 모든 경로).
  2. 각 작업 스레드를 제한된 시간(`WAIT_LIMIT`)으로 `join`한다.
  3. 끝나지 않은 스레드가 있으면, **이번 검사가 소유한 연결만** 닫는다. 대상은 그 검사의 추적 업무 연결, 그 검사가 연 관리 변경 연결, 탐침 연결이다. 다른 검사·다른 프로세스의 연결은 건드리지 않는다.
  4. 다시 제한된 시간으로 `join`하고, `is_alive()`로 실제 종료를 확인한다.
  5. 끝내 확인하지 못하면 다음을 기록한다: `thread_not_ended`(스레드 이름), 남은 업무·관리 세션(탐침이 가능하면 `pg_stat_activity`의 PID·상태, 원문 없이), 닫기 시도 결과. 그 검사는 통과가 아니며, 이후 검사는 `not_run`이다. 실행 전체를 "정리 미완료"로 표시한다.
  6. 정리 미완료 표시가 있으면 R2는 파괴적 단계(서버 정지 뒤 폴더 삭제)로 가지 않고 멈춰 보고한다. 기존 R2의 "업무 세션 0" 대조도 그대로 적용한다.
- 기록을 셋으로 나눈다: 원래 업무 결과(반환값 또는 업무 예외·중단의 종류), 탐침 결과, 정리 결과(해제·join·닫기·재확인). 정리 실패로 업무 결과를 덮지 않고, 업무 예외로 정리 실패를 숨기지 않는다.
- 하지 않는 것: 다른 프로세스 종료, 스레드 강제 종료, 무한 재시도, 성공·정리 완료로의 보고.
- 후속 변경 위치(이번에는 수정하지 않음): PG68 실행기 안의 경합 실행 함수(`race`를 바꾸지 않고 같은 규칙에 2단계 확인을 더한 PG68 전용 함수), PG68 `cleanup` 진입부의 정리 미완료 기록 확인. 공통 `race`를 바꾸려면 PG65~67 보존 검사를 포함한 별도 단위로 다룬다.

## 3. 닫힌 관리자 변경·권한 변형 [제안, 실행 승인 전]

모두 PG68 검사 DB에서만, 바인딩된 행 키로 실행한다.

- 자료 변경
  - `subscription_deactivate(deck)`: 계정 a의 그 덱 구독 `is_active = FALSE`(커밋, 또는 보유)
  - `subscription_reactivate(deck)`: 원복
  - `deck_word_remove(deck, lexeme)`: 그 덱의 단어 행 하나를 키(`shared_deck_id`, `lexeme_id`)로 삭제한다(커밋, 또는 미커밋 보유). 삭제 전에 그 행 전체(`id` 포함 모든 열, 행 텍스트)를 기록한다.
  - `deck_word_restore(deck, lexeme)`: 기록한 원래 `id`와 모든 열 값으로 다시 넣는다. 원복 확인: 같은 키의 행이 정확히 하나이고, 행 텍스트가 기록과 같으며, 그 DB의 계정 a 활성 경로 수가 4-0의 "본 검사 시작" 값으로 돌아왔다. 하나라도 다르면 `harness_defect`로 멈춘다
  - `path_row_hold(deck)`: 구독 행을 `SELECT … FOR UPDATE`로 잡고 커밋하지 않고 보유(대기 초과·선행 보유용). 롤백으로 해제한다
  - `card_row_request(lexeme)`: 교착 검사에서 관리 트랜잭션이 계정 a의 그 카드 행을 `SELECT … FOR UPDATE`로 요청
- 역할 설정: `ALTER ROLE jpvk_write IN DATABASE <db> SET lock_timeout = '10s'` / `'2s'` / `'5s'`, 원복은 `RESET lock_timeout`. 관측 프로필에는 `lock_timeout`이 들어가지 않는다([코드] 관측기 세션 항목). 공급자의 관측용 `SET LOCAL lock_timeout`은 관측 트랜잭션 롤백으로 사라진다.
- 권한 변형:
  - `k2a`: `REVOKE UPDATE (updated_at) ON public.user_deck_subscriptions FROM jpvk_write` / 원복 GRANT
  - `k2b`: `REVOKE UPDATE (created_at) ON public.shared_deck_words FROM jpvk_write` / 원복 GRANT
  - `k3`: `GRANT UPDATE ON public.user_deck_subscriptions TO jpvk_write`(초과) / 원복 REVOKE
- 교착 희생자 유도(6절 결정 E3): 관리 연결에 한해 `SET LOCAL deadlock_timeout = '60s'`(부트스트랩 관리자, 시험 DB만)
- 원복 뒤에는 바꿨던 역할을 실제 공급자 경로로 다시 관측한다. 계수는 생성 1·인계 1·문장 0·쓰기 0·커밋 0이어야 한다(PG67 `REOBSERVED`와 같은 규칙).

## 4. 최소 실제 검사표 [제안]

공통: 대상 카드는 계정 a의 구독 카드 l1, l2다. G1에서 최초 `apply` 배치 1로 l1을 커밋해 재개 기준 상태(`started`, cursor 1)를 만들고, 본 검사는 l2를 처리하는 명시적 `resume`(배치 1)이다. 기대값은 계약·코드·G1 기준선에서 미리 정한다. 실행 결과로 기대값을 만들지 않는다.

모든 본 검사의 공통 확인(별도 항목으로 기록): l1 행·버전·snapshot 보존, 실행 행 상태·cursor·`finished_at`, snapshot 키, l2 버전·엔진, 업무 계수에서 `user_deck_subscriptions`·`shared_deck_words` `UPDATE` 0, 계정 b·c와 범위 밖 자료 불변(키 대조).

### 4-0. 검사별 접근 경로 수 [제안]

자료 배치:

- 덱 A: 공통 `SEED`의 공유 덱. 단어 l1·l2를 포함하고 계정 a·b·c가 활성 구독한다(현행).
- 덱 B: PG68 `build_fn`이 템플릿에 만든다. 단어 행은 **l2 하나만** 넣는다. 계정 a의 B 구독 행은 **`is_active = FALSE`**로 만든다. 계정 b·c는 B를 구독하지 않는다. 템플릿의 모든 행은 복제 DB로 전달되므로, 모든 DB에서 l2의 활성 경로는 처음에 A 하나다.
- 두 경로 활성화: 준비(V2) 단계에서 복제 직후, 닫힌 목록의 DB(`r6`·`c1a`·`c1b`·`w1b`·`w2b`)에서만 계정 a의 B 구독을 `is_active = TRUE`로 바꾼다. DB 이름과 행 키를 이벤트로 기록한다. G1 이전에 끝낸다.
- G1 이후 허용하는 변경: 각 검사 자신의 닫힌 관리자 변경(3절)과 그 원복뿐이다. 경로 수를 맞추려고 자료를 고치지 않는다.
- 판정: G0과 G1이 각 DB에서 계정 a의 l2 활성 경로(구독 행 id, 단어 행 id 쌍)를 관리 조회로 세고 행 키까지 대조한다. l1의 경로는 모든 DB에서 A 하나다. 아래 표와 다르면 본 검사 전에 `preparation_failure`로 멈춘다. 실행 결과를 보고 자료나 기대값을 맞추지 않는다.

| 검사 DB | G1 시점 l2 경로 | 본 검사 시작(검사 자신의 변경 전) | 비고 |
| --- | --- | --- | --- |
| `k1`·`k2a`·`k2b`·`k3` | 1 (A) | 1 | 단일 경로 |
| `s1`·`s2`·`s3`·(`s3b`)·`s4` | 1 | 1 | `s4`는 자신의 실행 전 비활성화로 0이 된다 |
| `r1`·`r2`·`r3`·`r4a`·`r4b`·`r5` | 1 | 1 | 단일 경로 |
| `r6` | 2 (A·B) | 2 | 자신의 실행 전 A 비활성화로 1(B)이 된다 |
| `c1a`·`c1b` | 2 | 2 | 두 경로 필수 |
| `w1a`·`w2a` | 1 | 1 | 단일 경로 삭제 경합 |
| `w1b`·`w2b` | 2 | 2 | 대체 경로가 있는 삭제 경합 |
| `t1`·`d1` | 1 | 1 | 단일 경로(대기 초과·교착이 다른 경로로 빠지지 않게) |

### 4-1. 관문 (통과 수에서 제외)

| ID | 내용 | 기대 |
| --- | --- | --- |
| G0 | 대상 식별(PID·실행 파일·데이터 경로·리스너·OID·식별값), 스키마, 합성 자료(덱 B 포함)·품질, 계약 GRANT(두 열 포함), DB별 l1·l2 활성 경로 수와 행 키(4-0 표) | 모두 기록·표와 일치. 실패 시 본 검사 미실행 |
| G1 | 각 검사 DB에서 실제 계획 dry-run(읽기)과 최초 `apply`(배치 1), 뒤이어 경로 수·행 키 재확인 | 각 DB가 `started`·cursor 1·l1 변환·snapshot l1이고 경로 수가 4-0 표와 같음. 실패 시 본 검사 미실행 |

### 4-2. 본 검사 (23개, E4 채택 시 24개)

| ID | 검사 | 순서·조작 | 기대(계약·코드에서) |
| --- | --- | --- | --- |
| K1 | 새 최소 권한으로 성공 | 변경 없음 | 공급자가 두 열 권한만 더한 프로필로 인계. l2 `applied`, 종료 0. 두 접근 테이블 업무 `UPDATE` 0 |
| K2a | `updated_at` 권한 누락 | 권한 변형 `k2a` 뒤 `resume` → 원복·재관측 | `observed_privileges_missing`, 인계 전 거부, 쓰기 0 |
| K2b | `created_at` 권한 누락 | `k2b` | 같음 |
| K3 | 초과 권한 | `k3` | `observed_privileges_excess`, 인계 전 거부 |
| S1 | 기존 0 | 역할 설정 없음 | `set_config('lock_timeout','5000ms',true)` 전송·성공, 잠금 문장 뒤 원래 값 `0`으로 복원 전송·성공, l2 `applied` |
| S2 | 기존 10초 | 역할 설정 `10s` → 원복 | 5000ms로 줄이고 `10s`로 복원 |
| S3 | 기존 2초(5초 이하) | 역할 설정 `2s` | `set_config` 전송 없음(완화 없음). 5초 정각은 S3b로 같은 판정 |
| S4 | 0행에서도 복원 | 실행 전 `subscription_deactivate` | 5000ms 설정·복원 모두 전송, l2 `conflict`(쓰기 0), cursor 2, 완료 종료 5 |
| R1 | 판정 전 변경 | 정지점 "판정 전"에서 관리자가 비활성화 커밋 → 해제 | l2 `conflict`, 쓰기 0 |
| R2 | 판정 뒤·쓰기 전 변경 | 정지점 "판정 뒤"에서 관리자 비활성화 시도(별도 스레드) → 대기 증명 → 해제 | 관리자 대기(5절 증거), l2 `applied` 커밋 뒤 관리자 진행·커밋 |
| R3 | 쓰기 뒤·커밋 전 변경 | 정지점 "커밋 전"에서 같은 시도 | R2와 같다 |
| R4a | 변경이 먼저 보유 → 커밋 | `path_row_hold`가 아닌 비활성화 미커밋 보유 → `resume` 시작 → 제품 대기 증명 → 관리자 커밋 | 재평가 뒤 남은 경로 없음 → l2 `conflict`, 쓰기 0 |
| R4b | 변경이 먼저 보유 → 롤백 | R4a와 같고 관리자 롤백 | 원래 행 잠금 → l2 `applied` |
| R5 | 커밋 뒤 접근 상실 | l2 완료 뒤 비활성화 | l2 변환 유지, 실행 `completed`, 자동 롤백·보정 없음 |
| R6 | 활성 경로 둘 | 두 번째 덱 구독 상태에서 첫 덱만 실행 전 비활성화 | 접근 유지 → l2 `applied` |
| C1a | 반환 경로만 잠김 | 경로 둘. 정지점 "판정 뒤"에서 관리자 A(낮은 `subscriptions.id`) 변경 시도 / B 변경 시도 | A 시도는 대기(증명), B 시도는 대기 없이 커밋 완료(정지점 보유 중), 해제 뒤 l2 `applied` |
| C1b | 첫 경로가 재평가로 빠짐 | 관리자 A 비활성화 미커밋 보유 → `resume` → 제품 대기 증명 → 관리자 커밋 → 제품이 "판정 뒤" 정지점 도달 → 관리자 B 변경 시도 | B 시도가 제품에 막힘(증명) = B가 잠김. 해제 뒤 l2 `applied` |
| T1 | 실제 잠금 대기 초과 | `path_row_hold(A)`(경로 하나) 보유 → `resume` → 제품 대기 증명 → 보유 유지 | 서버 SQLSTATE `55P03`(기록), 제품 코드 `migration_access_lock_timeout`. CLI `failed`·`after_start`·`uncertain`·`status_required`·종료 1. l2 쓰기 0(카드 롤백), cursor 1, 실행 `failed`, snapshot l1만, l1 보존. 잠금 문장 뒤 복원 `set_config` 전송 없음. 이후 관리자 롤백 → **명시적** `resume`(새 승인) → 완료 |
| D1 | 실제 교착 | 6절 결정 E3을 따라 5절 4-2 분기 | 분기별 기대는 5-2 |
| W1a | 잠금 뒤 덱 단어 삭제(단일 경로) | 정지점 "판정 뒤"(A 경로 잠금)에서 관리자가 A-l2 단어 행 삭제 시도(별도 스레드) → 대기 증명 → 해제 | 관리자 대기, l2 `applied` 커밋 뒤 삭제 진행·커밋. 이후 l2 경로 0(커밋 뒤 상실, LQ1-b: 변환 유지·자동 롤백 없음) |
| W1b | 잠금 뒤 덱 단어 삭제(대체 경로 있음) | 경로 A·B. 같은 순서로 A-l2 삭제 시도 | 관리자 대기, l2 `applied`, 삭제 진행. 이후 l2 경로 1(B) |
| W2a | 삭제 먼저 보유(단일 경로) | 관리자 A-l2 삭제 미커밋 보유 → `resume` → 제품 대기 증명 → 관리자 커밋 | 재평가에서 삭제된 행은 무시되고 남은 경로 없음 → l2 `conflict`, 쓰기 0, cursor 2 |
| W2b | 삭제 먼저 보유(대체 경로 있음) | 경로 A·B. 같은 순서 | 재평가 뒤 B 경로를 잠금 → l2 `applied` |

수: 본 검사 23개(K 4, S 4, R 7, C 2, T 1, D 1, W 4). 삭제 경합 W1a·W1b·W2a·W2b는 **독립 검사**다. S3b를 포함하면 24개다(결정 E4). 관문 2개와 사후 확인은 수에서 제외한다.

위 23·24개는 D1 포함을 전제로 한다. 선택별 집계는 D1 제외·S3b 제외 22개, D1 포함·S3b 제외 23개, D1 제외·S3b 포함 23개, 둘 다 포함 24개다. E3·E4 확정 후 실행기의 고정 목록과 집계를 맞추며, 실행 인자나 환경 변수로 선택하게 하지 않는다.

필수 하위 사례 규칙: 한 검사 안의 필수 하위 사례(예: C1a의 A 시도 대기와 B 시도 비대기, W·R2·R3의 관리자 대기 증명과 제품 커밋 순서, 모든 검사의 공통 확인, 원복 확인)는 각각 `subcase` 이벤트로 저장한다. 상위 검사는 모든 필수 하위 사례가 저장·재읽기로 확인되고 그 검사 결과 자체도 저장·재읽기로 확인됐을 때만 통과로 센다. 하나라도 빠지면 그 검사는 실패이며 첫 실패 중단 규칙을 따른다.

W 검사의 추가 확인(공통 확인과 별도 기록): 카드(l2 버전·엔진), snapshot 키, cursor·실행 상태, l1 보존, 관리자 변경 귀속(관리자 이벤트의 삭제 1행·키, 업무 계수의 두 접근 테이블 `UPDATE`·`DELETE` 0), 원복 확인(3절 `deck_word_restore` 기준).

### 4-3. 사후 확인 (수에서 제외)

- 모든 검사 DB의 계정 b·c와 범위 밖 자료가 기준선과 같다(키 대조).
- 모든 자료 변경·역할 설정·권한 변형의 원복과, 바꿨던 역할의 공급자 재관측(1·1·0·0·0)
- 업무 세션 0, idle in transaction 0, 미승인 잠금 0(`pg_locks.granted = false` 없음)
- 미해제 정지점 0, 살아 있는 작업 스레드 0

## 5. 대기·교착 증거 [제안]

### 5-1. 대기 증명

- 시간 지연만으로 대기를 선언하지 않는다. T1의 5초 경과 측정은 보조 기록일 뿐이다.
- 근거(별도 관리 탐침 연결, 정지점 순서에 맞춰):
  - 대기 연결 PID: 업무 연결은 `Tracked.pending_pid`, 관리 연결은 그 연결이 기록한 `pg_backend_pid()`
  - `pg_blocking_pids(대기 PID)`에 차단 연결 PID가 정확히 들어 있음(`wait_blocked` 재사용)
  - 대기 PID의 `pg_locks` 중 `granted = false`인 행의 `locktype`·`mode`·`transactionid`(또는 `relation`·`tuple`)
  - 차단 연결의 트랜잭션 ID(차단 쪽이 업무 연결이면 정지점에서 탐침 연결이 `pg_stat_activity.backend_xid`로 읽는다. 관리 연결이면 그 연결이 `pg_current_xact_id_if_assigned()`로 기록한다)
- 행 잠금 대기는 보통 보유 트랜잭션 ID 대기(`locktype = 'transactionid'`)로 나타나며, `relation`은 NULL일 수 있다. 대상 relation을 필수 조건으로 두지 않는다. 대기 행의 `transactionid`가 차단 트랜잭션 ID와 같아야 한다.
- 대상 행과의 연결은 기록으로 한다: 정지점 이름과 순서, 각 연결이 실행한 고정 문장 이름, 바인딩한 행 키(계정·덱·lexeme), 영향 행 수. 하나라도 빠지면 판정하지 않고 `harness_defect`로 멈춘다.
- "대기 없음"(C1a의 B)의 근거: 정지점이 보유 중인 동안 관리 연결의 `UPDATE`·`COMMIT`이 반환됐고, 그 사이 탐침에서 관리 PID에 `granted = false` 잠금이 없었다.

### 5-2. 교착(D1)

- 순서: 관리 트랜잭션이 경로 A 구독 행을 갱신(미커밋) → 제품 `resume`이 `users`·카드 행을 잡고 접근 잠금에서 대기(증명) → 관리 트랜잭션이 같은 계정의 l2 카드 행을 `FOR UPDATE`로 요청 → 순환.
- 희생자는 특정 연결로 단정하지 않는다. 결과 분기를 미리 정하고, 실제 희생자는 서버 근거(어느 연결이 `40P01`을 받았는지: 업무는 `sqlstate_seen`, 관리는 그 연결의 예외 SQLSTATE, 서버 로그의 교착 기록)로 확인한다.
  - 분기 P(제품 희생): 서버 `40P01` → 제품 코드 `migration_access_deadlock`, CLI `failed`·`after_start`·`uncertain`·`status_required`·종료 1, l2 쓰기 0, cursor 1, `failed`, l1 보존. 관리 트랜잭션은 이어서 카드 행을 얻고 롤백한다.
  - 분기 A(관리 희생): 관리 연결이 `40P01`을 받고 롤백 → 제품은 원래 행 잠금으로 진행 → l2 `applied`. 이 분기는 **제품의 실제 `40P01` 처리를 검증한 것으로 세지 않는다.** 결과는 "교착 발생·관리 희생"으로 기록한다.
  - 그 밖(교착 없음, 둘 다 실패, 대기 초과 먼저 발생): 기대 불일치 또는 `harness_defect`로 멈춘다.
- 원하는 희생자가 나올 때까지 반복하지 않는다. D1은 한 번만 실행한다.
- 희생자 유도(결정 E3): 관리 연결에만 `SET LOCAL deadlock_timeout = '60s'`를 두면, 순환이 제품의 교착 검사 시점(기본 1초) 전에 만들어질 때 제품 쪽이 먼저 교착을 감지할 가능성이 크다. 이것은 가능성일 뿐 보장이 아니다. 순환이 늦게 만들어지면 제품은 5초 대기 초과(`55P03`)를 먼저 받을 수 있다. 그 경우도 위 분기로 판정한다.

### 5-3. 결과 출처 표시

결과마다 출처를 따로 적는다: 실제 서버 오류(SQLSTATE 기록), 시험 장치 주입(G1 등), CLI·공급자 거부(고정 코드, 인계 전후 구분), 제품 고정 코드.

## 6. 결정 항목 [제안, 미결]

| ID | 항목 | 권장안 |
| --- | --- | --- |
| E1 | 대상 값(1절) 확정 | 1절 값 |
| E2 | 두 번째 덱 자료를 PG68 실행기 자체 `build_fn`으로 추가(B 구독은 템플릿에서 비활성, 4-0의 DB만 준비 단계에서 활성화) | 공통 `SEED`는 그대로 둔다 |
| E3 | D1 희생자 유도용 관리 연결 `deadlock_timeout` 상향 허용, D1 포함 여부 | 포함하되 분기 A는 제품 `40P01` 미검증으로 기록. 포함하지 않으면 제품 `40P01` 처리는 실제 PG 미검증으로 남는다 |
| E4 | S3b(정확히 5초) 포함 여부 | 포함(경계가 계약 문장 "5초보다 길 때만"과 직접 맞닿음). 포함 시 본 검사 24개 |
| E5 | 업무 트랜잭션 안 설정 상태 탐침 | 넣지 않는다. 설정은 전송된 `set_config` 문장과 성공으로만 판정하고, 서버 설정값 자체는 미검증으로 남긴다 |
| E6 | 실행기 승인 상수 이름·값 | `LQ4_CHANGES_APPROVED = None`, 실제 실행 승인 때만 `True` 한 줄 변경 |

## 7. 승인 단위 [제안]

1. **V1 시험 코드와 가짜 보호 검사**: 2-2의 파일. 등록·실행기·가짜 검사만 하고 PG는 없다. 2-2의 닫힌 목록 단언 네 곳만 바꿀 수 있고, 그 밖의 PG65·66·67 보존 검사는 수정 없이 통과해야 한다. 2-5의 종료 절차와 4-0의 경로 수 판정을 가짜 검사로 고정한다.
2. **V2 준비**: 클러스터·TLS·역할·DB·스키마·합성 자료(두 번째 덱 포함)·계약 GRANT. `prepare` 1회.
3. **V3 실제 검사**: G0 → G1 → 본 검사 → 사후 확인, 3절의 닫힌 관리자 변경·권한 변형·원복 포함. `check-access-lock` 1회. `LQ4_CHANGES_APPROVED = True` 한 줄.
4. **V4 정리·보관**: 기록 대조 뒤 R2 `cleanup` 1회, 증거를 `C:/JV_Evidence/pg68/<실행 ID>/`에 덮어쓰기 없이 복사·재대조, 실행별 `custody.json`(기존 ACL 정책과 같아야 하며 다르면 중단).

V2~V4는 같은 승인 메시지에 묶을 수 있지만, 실행 순서와 실패 시 중단은 아래를 따른다.

### 7-1. 중단·기록 규칙

- 첫 실패에서 멈춘다: 준비 실패, 관문 실패, `harness_defect`, 기대 불일치, 기록 저장·재읽기 실패 모두 같다. 남은 검사는 `not_run`으로 기록한다.
- 통과는 `run_recorded`처럼 저장 뒤 다시 읽어 확인한 것만 센다. 관문·사후 확인은 별도로 기록하고 수에서 뺀다.
- 정지점은 모든 경로(성공·실패·예외)에서 해제하고, 작업 스레드는 2-5의 절차로 종료를 확인한다. 끝내 확인하지 못하면 성공·정리 완료로 보고하지 않고, 잔존 스레드·세션을 기록하고, R2의 파괴적 정리를 멈춘다.
- 현장 보정·재실행은 하지 않는다(코드·SQL·자료·기대값).
- 정리(R2): 결과와 무관하게 기록과 살아 있는 대상(PID·실행 파일·경로·리스너·system identifier·DB·역할 OID·업무 세션 0)을 대조한 뒤에만 정리한다. 대조가 다르거나, 소유가 불명확한 잔존물이 있거나, 미해제 잠금·세션이 있으면 자동 삭제·다른 프로세스 종료·CASCADE 없이 멈추고 보고한다.
- 증거에는 비밀번호·개인 키·DSN·접속 오류 원문·SQL 바인딩 로그를 넣지 않는다. SQLSTATE와 고정 코드만 넣는다.

## 8. 미검증으로 남는 것

- 이 계획을 실행해도: 운영 환경·운영 데이터, 실제 커밋 응답 유실·서버 강제 종료, `users`·카드 잠금 단계의 대기 시간, 분기 A일 때 제품의 `40P01` 처리, 서버 설정값 자체(E5), 실제 백업·복원(C10 플래그 `false` 유지).
- 계획 검토 대기.

## 9. 계획 검토 보정 기록 (2026-10-29, 문서만)

- 4-0 추가: 템플릿 자료가 복제 DB로 전달되는 점을 반영해, 덱 B 구독을 템플릿에서 비활성으로 두고 닫힌 DB에서만 준비 단계에 활성화한다. 검사별 G1·본 검사 시작 경로 수를 표로 고정했다. G0·G1은 경로 수와 행 키를 대조하고, 다르면 중단한다.
- 삭제 경합 W1a·W1b·W2a·W2b를 독립 검사로 추가했다(본 검사 23개, S3b 포함 시 24개). 필수 하위 사례가 모두 저장·재읽기돼야 상위 검사를 통과로 센다. 삭제 원복은 기록한 원래 `id`·행 값으로 하고, 확인 기준을 3절에 적었다.
- 2-5 추가: 기존 `race`는 join 기한 초과 뒤 연결을 닫고 곧바로 예외를 내며, 닫은 뒤 종료를 다시 확인하지 않는다. PG68에서는 해제 → 제한 join → 소유 연결만 닫기 → 제한 재join·종료 확인 순서로 하고, 미확인 시 성공·정리 완료로 보고하지 않으며 R2 파괴적 정리를 멈춘다. 공통 함수·실행기는 이번에 수정하지 않았다.
- 2-2 정정: 닫힌 목록 전체를 단언하는 네 곳(`PRESETS` 세 곳, `LAYOUTS` 한 곳)만 끝에 PG68을 더하는 변경을 허용한다. 그 밖의 보호 기대값·기준 파일은 바꾸지 않는다.
- E1~E6은 계속 미결이다. LQ1 정책·구현 계약은 바꾸지 않았다. 계획 재검토 대기.

## 10. 독립 정적 재검토 마감 (2026-10-29)

- 검사별 경로 수와 G0·G1 대조, 덱 단어 삭제 경합 네 건과 원복, 종료 미확인 시 파괴적 정리 차단, 닫힌 목록 단언 네 곳만의 변경 허용을 확인했다. 앞선 네 지적 사항은 해소됐다.
- 재사용 표와 탐침 절의 남은 `race` 문구를 PG68 전용 종료 조정 함수와 맞췄다. E3·E4 선택에 따른 22~24개 집계도 명시했다. 정책 선택이나 실행 범위를 새로 승인한 것은 아니다.
- 문서 정적 검토만 마감한다. E1~E6 결정과 V1 시험 코드·가짜 검사, V2~V4 실제 준비·검사·정리는 별도 승인이 필요하다. 실제 PG의 잠금·설정·대기·교착과 8절의 미검증 범위는 그대로다. REPORT 106-1절을 참조한다.

## 11. E1~E6 결정 기록 (2026-10-29 사용자 결정, 기준 `86af46b`, V1 구현 전 기록)

- E1: 1절 대상 값을 채택한다. `PG68_LEXEME_ACCESS_LOCK`, `C:/JV_Tools/pg68`, 포트 55522, 역할 `jpvk_admin`·`jpvk_owner`·`jpvk_read`·`jpvk_write`, DB `jp_vocab_test_access_lock_*`.
- E2: 공통 `SEED`는 유지한다. PG68 전용 `build_fn`이 덱 B(단어 l2 하나)와 계정 a의 비활성 B 구독을 만든다. 4-0의 다섯 DB(`r6`·`c1a`·`c1b`·`w1b`·`w2b`)에서만 G1 전에 활성화한다.
- E3: D1을 포함한다. 향후 실제 실행에서는 관리자 연결에만 트랜잭션 범위 `deadlock_timeout = '60s'`를 쓰는 설계를 채택한다. 실제 설정 실행은 이번 승인에 들어 있지 않다. 희생자는 단정하지 않는다. 관리자가 희생되면 제품의 실제 `40P01` 처리는 미검증이다. 원하는 희생자가 나올 때까지 반복하지 않는다.
- E4: S3b(정확히 5초)를 포함한다. 본 검사는 고정 24개다.
- E5: 업무 트랜잭션에 설정 탐침 SQL을 넣지 않는다. 실제 실행 때는 보낸 `set_config` 문장·인자·성공 여부만 기록한다. 따로 읽지 않은 서버 설정값을 실측했다고 보고하지 않는다.
- E6: V1의 `LQ4_CHANGES_APPROVED`는 `None`이다. 실제 변경 승인 전에는 `check-access-lock`이 G0 전에 종료 1로 멈춘다.
- 승인 범위: E1~E6 문서 확정과 V1(시험 코드·PG 없는 가짜 보호 검사)뿐이다. V2 준비, V3 실제 검사, V4 정리·보관은 승인되지 않았다.

## 12. V1 구현과 가짜 보호 검사 결과 (2026-10-29, PG 없음)

### 12-1. 변경 파일

- `backend/tests/_ops_pg62.py`
  - `PG68_LEXEME_ACCESS_LOCK_CHECK_IDS`(24개)와 `PG68_LEXEME_ACCESS_LOCK`를 등록하고, `PRESETS` 끝에 추가했다(등록만).
- `backend/tests/_ops_real_layout.py`
  - `PG68_VARIANTS`와 `PG68_VARIANT_DATABASES`를 추가했다. 권한 변형 3개(`k2a`·`k2b`·`k3`)와 역할 설정 3개(`s2` 10초, `s3` 2초, `s3b` 5초)이며, 각각 원복 문장이 있다.
  - `k3` 원복은 테이블 단위 REVOKE가 열 권한까지 지우므로, `updated_at` 열 권한을 다시 GRANT한다.
  - `PG68` 레이아웃을 만들고 `LAYOUTS` 끝에 추가했다. 공통 함수·`SEED`·`race`·`WAIT_LIMIT`은 바꾸지 않았다.
- 새 `backend/tests/_ops_access_lock_real.py`: PG68 실행기
  - 실행 명령은 `prepare`·`check-access-lock`·`cleanup` 세 단어만 받는다. 인자·환경 변수로 대상·역할·DB·검사 범위·반복을 고를 수 없다.
  - `LQ4_CHANGES_APPROVED = None`이다.
  - PG67 실행기의 모듈 값은 import하거나 바꿔치기하지 않는다. RS4 실행기에서는 대상 무관 계측만 쓴다.
- 새 `backend/tests/test_ops_access_lock_real_guard.py`: 가짜 보호 검사 33개
- 닫힌 목록 단언 네 곳: `test_ops_apply_real_guard.py`·`test_ops_audit_real_guard.py`·`test_ops_backup_real_guard.py`의 `PRESETS`와 `test_ops_real_layout.py`의 `LAYOUTS`. 끝에 PG68을 더하고 주석만 바꿨다. 다른 기대값·기준 파일은 그대로다.
- 새 `docs/plans/srs-improvement/gate-e/PG68_TARGET.md`: 대상 값 문서

### 12-2. 실행기 배선 (실제 경로)

- 준비(`prepare`)
  - 공통 `lay.prepare`에 PG68 `build_fn`을 넘긴다. 이 함수는 공통 `build_template`을 실행한 뒤 덱 B(단어 l2 하나)와 계정 a의 비활성 B 구독을 만들고, `access_paths_seeded` 이벤트로 기록한다.
  - 경로 행 id(`sub_a`·`sub_b`·`word_a_l1`·`word_a_l2`·`word_b_l2`)는 `target.json`의 `synthetic.access`에 남긴다.
  - 그 뒤 다섯 DB에서만 B 구독을 활성화하고 `second_path_enabled`로 기록한다. G1보다 먼저다.
- G0
  - 대상 OID·식별값, 24개 DB의 l1·l2 활성 경로와 행 키(4-0 표), 두 열 계약 GRANT(`has_column_privilege`), 템플릿 품질을 확인한다.
  - 다르면 `preparation_failure`로 멈추고 본 검사는 실행하지 않는다.
- G1
  - DB마다 실제 `Harness.case`(CLI dry-run과 실제 사전 검사·서명)와 최초 `apply`(배치 1)를 실행한다.
  - 그 뒤 기준선(`started`·cursor 1·l1 변환·l2 계획 버전)과 경로 수·행 키를 다시 확인한다.
- 본 검사
  - 24개 모두 실제 CLI `run_resume`(배치 1), 어댑터, 공급자, 제품 `apply_plan`을 거친다.
  - 기대값은 G1 기준선·최초 계획·계약에서 계산한다.
  - 모든 검사는 공통 하위 사례(`cli`·`admin_state`·`settings`·`access_writes`·`outside`)와 검사별 필수 하위 사례를 `subcase`로 저장하고, 기록을 다시 읽어 모두 확인돼야 통과한다.
- 계측
  - `AccessTracked`(`ResumeTracked` 하위 클래스)는 인계 뒤에만 다음을 기록한다: `set_config('lock_timeout', …)`의 값과 성공 여부, 실패한 문장의 SQLSTATE(원문 없이), 두 접근 테이블에 대한 쓰기.
  - 반환값과 예외는 그대로 넘긴다. 업무 트랜잭션 안의 설정 탐침은 없다(E5).
- 계수 분리
  - 업무는 `Counts`, 관리자 변경은 `admin_change`, 탐침은 별도 관리 연결의 `lock_wait_proof`, 원복 재관측은 별도 계수의 `revert_observation`(1·1·0·0·0)로 나눈다.
  - CLI 보고는 `check_run`, 관리 조회 상태는 `check_admin_state`에 둔다.
- 대기 증명(`prove_wait`)
  - 대기 PID와 `pg_blocking_pids`에 차단 PID가 들어 있는지 본다.
  - 대기 PID의 미승인 잠금 행의 `transactionid`가 차단 트랜잭션 ID와 같아야 한다. 업무 쪽은 `pg_stat_activity.backend_xid`, 관리 쪽은 `pg_current_xact_id_if_assigned()`로 얻는다. relation은 요구하지 않는다.
- D1
  - 관리 트랜잭션에만 `SET LOCAL deadlock_timeout = '60s'`를 둔다. 제품 대기를 증명한 뒤 카드 행을 요청한다.
  - 분기 판정은 `deadlock_branch`가 한다. P일 때만 `product_40p01_verified`가 참이다. 한 번만 실행한다.
- T1
  - 서버 SQLSTATE(`55P03`)와 제품 고정 코드, CLI 보고를 따로 기록한다. 그 뒤 새 승인 id로 명시적 `resume`을 한 번 한다.

### 12-3. 종료 확인 (2-5)

- `coordinate`
  - 정지점 해제 → 제한 join → 살아 있으면 이번 검사 소유 연결(추적 업무 연결·관리 변경 연결)만 닫기 → 제한 재join → `is_alive` 확인 순서다.
  - 업무 결과·탐침 결과·정리 결과를 `coordination` 이벤트에 나눠 남긴다.
  - 종료를 확인하지 못하면 `thread_not_ended`·`cleanup_incomplete`를 기록하고 `harness_defect`로 멈춘다.
  - 작업 스레드의 중단(`KeyboardInterrupt` 등)은 그대로 다시 던진다.
- 차단
  - `check-access-lock`과 `cleanup`은 시작할 때 기록을 디스크에서 다시 읽는다. 위 이벤트가 있거나 기록을 읽을 수 없으면 아무것도 지우지 않고 종료 1로 멈춘다.
  - 공통 `race`와 `lay.cleanup`은 바꾸지 않았다.

### 12-4. 가짜 보호 검사 (33개)

- 차단: 실제 PG 연결, `subprocess`, 키 생성, 리스너·프로세스 조회, 관리 연결, TLS 생성, PG 환경 변수. 별도 허용은 두 가지다. `Processes`(import·진입점)와 종료 미확인 cleanup 검사는 새 Python 프로세스를 쓴다. `CasePath`는 시험 전용 임시 OpenSSH 키로 실제 서명한다(서명 검증을 가짜로 바꾸지 않음).
- 확인한 것:
  - 대상·등록: 등록 객체 자체만 허용하고, 값이 같은 복제본(대상·레이아웃)은 거부한다. 이름이 다른 모든 프리셋과 분리돼 있다. 업무·관리 연결 행렬과 연결 직후 대상 재확인(불일치 시 닫고 거부), 계약 GRANT와 닫힌 변형.
  - 승인 전: 변형·관리자 변경·`check-access-lock`이 차단되고, import는 아무것도 하지 않는다. 진입점 종료 코드(1·2)를 새 프로세스로 확인했다.
  - 집계: 24개 목록·순서, 관문·사후 확인 집계 제외, 첫 실패 뒤 `not_run`, 기록 실패, 미완료(24 미만) 시 종료 1.
  - G0: 실제 `g0_gate`에 가짜 관리 조회를 붙였다. 경로 수 차이, 다른 행 키, 두 경로 누락 모두 본 검사 전에 멈춘다.
  - W 네 검사: 실제 검사 함수·`coordinate`·판정을 가짜 하네스에서 돌렸다. 필수 하위 사례 기록, 대기 증명, 관리자 귀속, 원복 확인을 확인했고, 원복 행 텍스트가 다르면 실패한다.
  - T1: 서버 SQLSTATE·제품 코드·CLI 구분, 명시적 재개 1회. 서버 SQLSTATE가 없으면 실패한다.
  - D1: 두 분기(P·A)와 무분기 사례, `product_40p01_verified` 기록.
  - 계수: 인계 전 문장 비계수, 설정 실패는 `ok: false`, SQLSTATE만 기록(원문 없음), 두 접근 테이블 쓰기 검출.
  - 원복 재관측: 두 역할 모두 1·1·0·0·0이고, 그 밖의 값은 실패한다.
  - 종료 조정: 정상, 탐침 실패, 업무 오류, 중단, 닫기 실패와 종료 미확인을 주입했다. 별도 cleanup 프로세스가 기록을 읽고 파괴적 정리를 거부한다.
  - 실제 배선(`CasePath`):
    - 대상 결속부터 CLI dry-run 진입, 계수 목록 공유(스코프와 드라이버가 같은 목록)까지 실제 `Harness` 초기화와 `Harness.case`를 실행했다.
    - 바꾼 경계는 세 곳이다: 가드 드라이버의 연결(가짜), 계획 dry-run의 공급자 뒤(드라이버를 한 번 부르고 인계), 제품 dry_run 본문(실제 계획 후보 반환).
    - `observe_role`은 실제 어댑터·공급자에 가짜 서버(계약 프로필 카탈로그)를 붙여, 두 역할 1·1·0·0·0과 권한 누락·초과 거부를 확인했다.
- 변형 확인: 설정 복원 누락, 대기 증명 생략, 재join 생략, cleanup 기록 무시, 두 경로 목록 오류를 각각 넣으면 해당 검사가 실패했다.
- 결과: 새 보호 검사 33개 통과(단독·루트 discovery, 외부 `PYTHONPATH` 없음, `-X dev` `ResourceWarning` 0).
- 직접 영향 묶음 통과: `test_ops_real_layout` 16, `test_ops_apply_real_guard` 96, `test_ops_audit_real_guard` 41, `test_ops_backup_real_guard` 42, `test_ops_resume_real_guard` 47, `test_ops_resume_lexeme_real_guard` 37, `test_srs_migration_access_lock` 15. 루트 discovery(`test_ops_*real*guard.py`)는 296개다.
- 이번 시험 자료(임시 폴더·키)는 남지 않았다. `C:/JV_Tools/pg68`은 없다.

### 12-5. 실제 PG 미검증

V1은 PG 없는 코드와 가짜 검사뿐이다. 다음은 실행하지 않았고 검증되지 않았다.

- 준비 SQL, 덱 B와 경로 활성화, 24개 검사의 실제 SQL·잠금·대기·`55P03`·`40P01`
- 관리자 `deadlock_timeout` 설정, 역할 설정의 `current_setting` 표기
- 실제 GRANT·REVOKE와 원복, R2 정리

가짜 SQL·가짜 서버·가짜 하네스 결과는 이 증거가 아니다. V2~V4는 승인되지 않았다. V1 검토 대기.

## 13. V1 검토 보정 (2026-10-29, PG 없음)

### 13-0. 경합 조정의 오류 우선순위 (코드 보정 전 고정)

`coordinate`가 끝에 무엇을 던질지는 아래 순서로 정한다. 어느 경우든 남은 정리를 모두 시도한 뒤에 던진다(정지점 해제, 제한 join, 소유 연결 닫기, 제한 재join, 기록). 각 단계의 추가 오류·중단은 기록하고 다음 단계로 넘어간다.

1. 작업 스레드의 업무 중단(`KeyboardInterrupt`·`SystemExit` 등 `Exception`이 아닌 것): 같은 객체를 그대로 던진다(`SystemExit` 값 보존, 예외 연쇄 제거).
2. 조정 중 하네스 자신의 중단(탐침·`between`·해제·닫기 중의 `KeyboardInterrupt` 등): 1이 없을 때만, 처음 생긴 것을 같은 객체로 던진다.
3. 종료 미확인(재join 뒤에도 살아 있는 스레드): `harness_defect`.
4. 정지점 시간 초과·미도달: `harness_defect`.
5. 탐침·하네스 일반 오류: `harness_defect`(종류 이름만 기록, 원문·연쇄 없음).
6. 작업 스레드의 일반 업무 오류(`Exception`): 던지지 않고 결과로 돌려 검사가 판정한다.

기록 규칙:

- 시작 전에 `coordination_started`(검사·토큰)를 저장한다. 이 저장이 실패하면 스레드를 시작하지 않는다.
- 종료가 확인된 경우에만 `coordination_ended`(같은 토큰)를 저장한다. 디스크에 짝 없는 시작이 있으면 `check-access-lock`과 `cleanup`은 진행하지 않는다(`coordination_unconfirmed`). 실패 기록 저장 자체가 실패해도 시작 기록이 남아 있으므로 안전한 정리로 간주되지 않는다.
- 업무 결과, 탐침 결과, 정리 결과는 `coordination` 이벤트에 나눠 남긴다.

### 13-1. 재현과 보정

변경 파일은 `backend/tests/_ops_access_lock_real.py`와 `backend/tests/test_ops_access_lock_real_guard.py` 두 개뿐이다. 공통 `Record`·`race`·`lay.cleanup`, 제품·CLI·공급자·권한 계약·기존 실행기, V1의 닫힌 등록과 목록 단언은 바꾸지 않았다.

- 결함 1(동시 기록 유실)
  - 재현: 첫 작성자를 메모리 갱신과 저장 사이에 멈추고 두 번째 작성자를 먼저 저장시켰다. 공통 `Record`에서는 두 `event`가 모두 성공했는데, 메모리에는 두 이벤트가 있고 디스크에는 첫 이벤트만 남았다(회귀에 증거로 남김).
  - 보정: PG68 전용 `LockedRecord`(공통 `Record` 하위 클래스)를 두었다. 메모리 갱신·저장·저장 실패 시 되돌리기 전체를 하나의 잠금으로 감싸므로, 되돌리기는 자기 항목만 지운다. 기록 재읽기(`read_saved`, `require_subcases`)와 `find`도 같은 잠금을 쓴다. `check-access-lock`은 이 기록을 쓴다.
  - 공통 `lay.run_recorded`의 재읽기는 주 스레드에서 경합 조정이 끝난 뒤에만 일어난다.
- 결함 2(정지점 시간 초과·C1a 오판)
  - 재현: B 변경도 제품이 끝날 때까지 막히는 가짜 서버에서, 정지점이 시간 초과로 풀린 뒤 B가 완료됐다. 그런데 `not release.is_set()`이 참이어서 C1a가 통과했다.
  - 보정: `HoldPause`에 명시적 보유 상태(`holding`, 시간 초과 시 거짓)와 `still_held()`를 두었다. C1a의 B와 R1의 관리자 커밋은 커밋이 끝난 시점에 `still_held()`와 영향 행 1, 커밋 완료를 기록한다.
  - `coordinate`는 시간 초과되거나 도달하지 않은 정지점을 `harness_defect`로 처리한다. 제품의 조기 종료는 기존 "정지점 미도달" 실패를 그대로 따른다. 이 판정은 정지점을 쓰는 다른 경합 검사(R2·R3·W1a·W1b·C1b)에도 같이 적용된다.
- 결함 3(정리 중 중단)
  - 재현: 업무 `SystemExit(9)`에 연결 닫기 중 `KeyboardInterrupt`가 겹친 경우와, 업무 `SystemExit(9)`에 탐침 일반 오류가 겹친 경우 모두 원래 업무 중단이 덮어써졌다.
  - 보정: 13-0의 우선순위를 따른다. 해제·join·닫기·재join의 각 단계는 오류나 중단이 나도 다음 단계로 진행한다. 업무 중단은 같은 객체로 다시 던진다(값 보존, 연쇄 제거).
  - 시작 전 `coordination_started`를 저장하고, 종료가 확인된 뒤에만 `coordination_ended`를 저장한다. 실패 기록 저장이 실패해도 짝 없는 시작이 디스크에 남으므로 `check-access-lock`과 별도 `cleanup` 프로세스가 진행을 거부한다.
  - `check-access-lock`은 검사 중 중단을 `not_run`(중단 종류·남은 검사)으로 기록한 뒤 같은 중단을 전파한다. 종료 코드는 그 `SystemExit` 값이다.
- 결함 4(R5·R6 관리자 변경)
  - 재현: 비활성화·재활성화가 영향 행 0이어도 R5·R6이 통과했다.
  - 보정: `admin_change`가 문장마다 영향 행 1과 커밋 완료를 하위 사례(`loss_rows`, `revert_rows`)로 요구한다. 변경 직후의 경로는 기록된 행 키로 계산한 기대값(`paths_for`)과 대조한다(`loss_paths`): R5는 경로 0, R6은 B 하나. 원복도 행 1과 4-0 경로 복귀를 요구한다. S4와 원복 도우미도 같은 규칙을 쓴다.

### 13-2. 검사 결과 (PG 없음)

- 새 회귀 14개(동시 기록 4, 정지점 3, 중단 4, 별도 cleanup 프로세스 1, 관리자 변경 2)
  - 보정 전 결과: 실패 7, 오류 8(하위 사례 포함)
  - 보정 전에도 통과한 것: 결함 증거용 공통 `Record` 유실 재현, 정상 C1a 경로, R5·R6 정상 변경
- 보정 후 가드 파일 47개 통과(V1 33 + 새 14). 단독 실행과 루트 discovery 모두 통과했고, 외부 `PYTHONPATH`는 없으며, `-X dev` `ResourceWarning` 0, 건너뜀 0이다.
- V1 검사 중 기대값을 갱신한 것은 세 곳이다. 모두 새 기록 항목이 생겨서 바뀐 것이다: 종료 미확인 시 `coordination_unconfirmed` 추가, 정상 종료의 시작·종료 이벤트, 정리 결과의 `release_errors`·`pauses`.
- V1 변형 5종은 계속 검출된다. 공통 코드를 바꾸지 않았으므로 294·296개 묶음은 반복하지 않았다.
- 실제·가짜 경계는 12-4와 같다. 시험 전용 임시 OpenSSH 키를 `CasePath`에서 생성·사용·정리했다(사용자 키·`.ssh`·`ssh-agent`·운영 신뢰 루트는 쓰지 않음). 실제 PG·관리 연결·TLS 생성·GRANT는 없고, V2~V4는 승인되지 않았다. V1 재검토 대기.

### 13-3. 최종 하네스 종료의 우선순위 (2026-10-29, 코드 보정 전 고정)

13-0의 우선순위를 `check_access_lock`의 최종 정리(`Harness.close`)까지 적용한다.

- 정리 단계는 순서대로 하나씩 시도한다: 정지점 해제 → 소유 연결 닫기(연결마다) → 시험 키 정리 → 이번 실행의 배포 임시 폴더 정리(삭제 뒤 부재 확인) → 메모리 비밀값 비우기. 어느 단계에서 일반 오류나 중단이 나도 뒤 단계를 건너뛰지 않는다. 다른 실행의 자원은 건드리지 않고, 재시도하지 않는다.
- 결과는 고정 단계 코드로만 남긴다. 실패한 단계는 `<단계>_failed`, 중단된 단계는 `<단계>_interrupted`, 확인되지 않은 폴더 정리는 `deploy_folder_unconfirmed`다. 원문·비밀값·예외 연쇄는 남기지 않는다.
- 던질 것의 우선순위:
  1. 정리 전에 이미 전파 중이던 최초 예외·중단: 같은 객체로 던진다(`SystemExit` 값 보존, 연쇄 제거). 정리 중 오류·중단이 이를 덮지 않는다.
  2. 원래 예외가 없을 때, 정리 중 최초 중단: 남은 정리를 마친 뒤 같은 객체로 던진다.
  3. 원래 예외도 중단도 없는데 실패·미확인이 있으면 `harness_defect`(종료 1)다. 정리 성공으로 보고하지 않는다.
- 차단 기록:
  - 실행 시작 전에 `final_cleanup_started`를 저장한다. 저장이 실패하면 검사를 시작하지 않는다.
  - 모든 단계가 확인됐을 때만 `final_cleanup_ended`를 저장한다.
  - 실패·미확인이면 `final_cleanup`(단계 코드)과 `cleanup_incomplete`를 저장한다. 이 저장이 실패해도 짝 없는 시작이 디스크에 남아 `final_cleanup_unconfirmed`로 차단된다.
- 바깥 `finally`에서 정리를 부르는 구조는 쓰지 않는다. 정리 결과를 받은 뒤 위 순서로 한 번만 던진다.

### 13-4. 최종 종료 보정 결과 (2026-10-29, PG 없음)

- 수정 전 재현: 실제 `main` → `check_access_lock` → `Harness.close` 경로를 썼다. 가짜로 바꾼 것은 `Harness.start`가 넣는 연결·키·배포 폴더·비밀값과 검사 함수뿐이다. k1의 업무 `SystemExit(9)`이 첫 연결 닫기의 `KeyboardInterrupt`로 덮였고, 두 번째 연결·키·폴더 정리와 비밀값 비우기가 생략됐다. 새 회귀 7개 모두 보정 전에 실패했다(하위 사례 포함 8건).
- 보정(`_ops_access_lock_real.py`):
  - `Harness.close`는 13-3의 단계를 하나씩 시도하고, 던지지 않는다. 결과는 고정 단계 코드와 중단 목록(`FinalCleanup`)으로 돌려준다.
  - `check_access_lock`은 바깥 `finally` 없이 원래 예외를 보관한다. 최종 정리를 마친 뒤 13-3 순서로 한 번만 던진다.
  - 시작 전 `final_cleanup_started`를, 확인된 종료 뒤에만 `final_cleanup_ended`를 저장한다. 실패 시 `final_cleanup`·`cleanup_incomplete`를 저장하며, 저장 실패도 짝 없는 시작으로 `final_cleanup_unconfirmed` 차단이 된다.
- 검사(`test_ops_access_lock_real_guard.py`, 새 `FinalClose` 7개):
  - 업무 `SystemExit(9)`과 닫기 중 `KeyboardInterrupt`: 같은 객체·값 9, 연쇄 없음. 두 번째 연결·키·폴더·비밀값 정리를 모두 시도했고, `not_run`과 차단 기록이 남는다.
  - 원래 `KeyboardInterrupt`에 키 정리 중 `SystemExit(3)`이 겹쳐도 원래 중단이 유지된다.
  - 시작 중 일반 오류가 전파될 때 닫기 중단과 키 정리 오류가 겹쳐도 원래 오류가 유지되고, 남은 정리를 시도한다.
  - 연결 닫기 실패 뒤 키 정리 실패·중단: 나머지 정리를 시도한다. 원래 예외가 없으면 정리 중단을 전파하고, 일반 실패는 종료 1(`final cleanup`)이며 정리 성공 기록이 없다.
  - 폴더가 남으면 `deploy_folder_unconfirmed`로 종료 1이다.
  - 정상 종료는 `final_cleanup_ended`가 남고 차단이 없다.
  - 실패 기록 저장이 실패해도 `final_cleanup_unconfirmed`로 차단된다.
  - 모든 사례에서 출력과 traceback에 합성 비밀값·원문이 없다.
- 기존 기대값 변경 두 곳(이유: `Harness.close`가 결과를 돌려주고 최종 기록이 생김): 가짜 하네스 두 개의 `close`를 확인된 `FinalCleanup()`으로 바꿨고, `not_run`이 마지막 이벤트라는 단언을 `not_run` 이벤트 내용 대조와 마지막 `final_cleanup_ended` 확인으로 바꿨다.
- 결과: 가드 54개 통과(이전 47 + 새 7). 단독 실행과 루트 discovery 모두 통과했고, `-X dev` `ResourceWarning` 0이다. V1 변형 5종도 계속 검출된다. 공통 코드는 바꾸지 않았으므로 294·296개 묶음은 반복하지 않았다.
- `CasePath`에서 시험 전용 임시 OpenSSH 키를 생성·사용·정리했다(사용자 키·`.ssh`·`ssh-agent`·운영 신뢰 루트는 쓰지 않음). 실제 PG·GRANT·V2~V4는 없다. V1 재검토 대기.

### 13-5. 독립 재검토와 부재 확인 단계 보완 (2026-10-29, PG 없음)

- 13-4의 종료 우선순위와 디스크 차단 기록을 대조했다. 추가로 폴더 삭제 뒤의 `os.path.lexists`가 단계 보호 밖에 남아 있었다. 실제 `main` → `check_access_lock` → `Harness.close`에서 이 조회에 중단을 주입하면 원래 `SystemExit(9)`이 덮이고 메모리 비밀값 비우기가 생략됐다.
- 13-3의 기존 계약대로 폴더 삭제와 부재 확인을 같은 `step("deploy_folder", ...)` 안에서 실행하도록 보완했다. 조회 오류·중단도 고정 단계 코드로 수집하며, 다음 폴더와 비밀값 비우기를 계속 시도한다. 기존 폴더 잔존 코드는 그대로다. 제품·공통 모듈·권한·승인 상수는 바꾸지 않았다.
- 회귀 1개(하위 사례 3개)를 추가했다. 원래 `SystemExit(9)` + 확인 중 `KeyboardInterrupt`, 원래 예외 없음 + 확인 중 `SystemExit(3)`, 확인 중 일반 오류를 실제 최종 종료 경로로 확인한다. 보완 전에는 세 사례 모두 비밀값 비우기 생략으로 실패했다. 보완 후에는 객체·종료값·연쇄 제거, 모든 정리 시도, 고정 코드, 미확인 기록과 cleanup 차단이 확인됐다.
- 독립 검사: 가드 55개(기존 54 + 새 1)가 단독 실행과 저장소 루트 discovery에서 각각 통과했다. 외부 `PYTHONPATH`와 PG 환경 변수를 제거하고 안전 환경 세 값을 고정했으며, `-X dev`에서 `ResourceWarning`은 0건이었다. 공통 코드가 바뀌지 않아 294·296개 묶음은 반복하지 않았다.
- 실제·가짜 경계는 12-4와 같다. `CasePath`의 시험 전용 임시 OpenSSH 키만 사용·정리했으며, 실제 PG·GRANT·V2~V4는 실행하지 않았다. V1 합성 검토만 마감한다. 12-5의 SQL·잠금·권한·실제 종료 미검증과 운영 차단은 유지한다. 이번 V1 관련 12개 파일만 작업 브랜치의 중간 커밋·푸시 대상으로 한다.

## 14. V2~V4 실제 로컬 PG 검증 승인 기록 (2026-10-29 사용자 승인, 실행 전 기록)

- 기준: 커밋 `2e71207`(브랜치 `codex/fsrs-srs-replacement`). 실행 전 확인: 백엔드·문서 미커밋 변경 없음, `C:/JV_Tools/pg68` 없음, 55522 리스너 없음, `C:/JV_Evidence/pg68` 없음, PG68 관련 임시 폴더 없음.
- 대상: `PG68_LEXEME_ACCESS_LOCK`, `C:/JV_Tools/pg68`, 포트 55522, 등록된 `jpvk_*` 역할과 검사 DB로 고정한다.
- 코드 변경: `_ops_access_lock_real.py`의 `LQ4_CHANGES_APPROVED`를 `None`에서 `True`로 바꾸는 한 줄만 허용한다.
- 승인: 시험 전용 임시 키·인증서, 새 클러스터·역할·DB·합성 자료, 계약 GRANT, 3절의 관리자 변경·역할 설정·권한 변형과 원복, E3의 관리자 트랜잭션 `deadlock_timeout`.
- 실행: `prepare` → `check-access-lock` → (안전 조건 충족 시) `cleanup`을 각 1회. 기존 폴더·리스너·기록이나 소유 불명 자원이 있으면 재사용·삭제하지 않고 멈춘다.
- 판정: 본 검사 고정 24개다. G0·G1·사후 확인은 수에서 뺀다. 과거 결과와 합산하지 않는다. 계약대로의 거부는 통과다. 첫 기대 불일치·관문 실패·시험 장치 결함·기록 실패에서 멈추고 나머지는 미실행으로 둔다. 현장 보정·재실행은 하지 않는다. D1은 P/A 분기를 그대로 판정하고 반복하지 않는다. 업무 트랜잭션 설정 탐침은 넣지 않는다.
- 정리·보관:
  - 디스크의 미확인 조정·최종 정리 기록, 미종료 스레드, 미해제 세션·잠금이 있으면 R2를 강행하지 않는다.
  - R2는 기록과 현재 대상이 일치할 때만 한다.
  - 실행 폴더 삭제 전에 원시 증거를 확보하고, 정리 결과는 별도 로그로 남긴다.
  - `C:/JV_Evidence/pg68/<실행 ID>/`에 덮어쓰기 없이 보관하고 다시 대조한 뒤 `custody.json`을 쓴다. ACL은 읽기 전용으로 확인만 하며, 다르면 중단한다.
- 유지: C10 `restore_verified`·`backup_artifact_checked`는 `false`다. 운영 준비 완료가 아니다.

### 14-1. 실행 결과 (2026-10-29, 실행 ID `20261029T170041`, PostgreSQL 18.6, 합성 자료만)

- 단계별 종료 코드: `prepare` 0 → `check-access-lock` 0 → `cleanup` 0. 각 1회만 실행했다. 재실행이나 현장 보정은 없었고, 코드 변경은 LQ4 한 줄뿐이다.
- 집계:
  - 본 검사 **24/24 통과**, 실패 0, 미실행 0
  - G0·G1·사후 확인은 통과했으며 수에서 뺐다. L-2·RS4·C12 결과와는 합산하지 않는다.
  - 음성 사례는 계약대로 거부돼 통과로 셌다: K2a·K2b `observed_privileges_missing`(종료 4), K3 `observed_privileges_excess`(종료 4).
- 준비:
  - 덱 B와 비활성 B 구독을 템플릿에 만들었다(`access_paths_seeded`). 다섯 DB에서만 B 구독(id 4)을 활성화했다(`second_path_enabled` 5건).
  - G0의 l2 경로 수는 4-0 표와 일치했다(두 경로 DB 다섯 곳은 2, 나머지는 1).
- 실제 서버 결과·CLI 판정·주입의 구분:
  - 서버 오류는 두 건뿐이다(서버 로그 ERROR 2건).
    - T1: `55P03`(lock timeout) → 제품 고정 코드 `migration_access_lock_timeout`. CLI는 `failed`·`after_start`·`uncertain`·`status_required`·종료 1로 보고했다. 그 뒤 새 승인 id로 명시적 재개 1회가 완료됐다.
    - D1: `40P01`(deadlock detected) → `migration_access_deadlock`. CLI 보고는 T1과 같다.
  - 시험 장치 주입은 없다(PG68 G1은 실제 최초 apply만 썼다).
- D1 분기: **P(제품 희생)**. 제품의 실제 `40P01` 처리가 검증됐다(`product_40p01_verified: true`, 관리 연결 SQLSTATE 없음). 서버 로그의 교착 보고도 제품 쪽 프로세스가 희생됐음을 보여 준다. 한 번만 실행했다.
- 설정 기록(E5: 전송·성공 기록만, 업무 트랜잭션 안의 서버 설정 탐침 없음):
  - 기본 0·10초: `5000ms` 설정과 원래 값 복원(`0`·`10s`)이 전송·성공했다. 복원 인자는 제품이 서버에서 읽은 이전 값이다. 복원 뒤의 서버 설정값은 따로 읽지 않았다.
  - 2초·정확히 5초: 설정 전송 없음(완화 없음).
  - 0행(S4·R4a·W2a): 설정과 복원이 모두 전송됐다.
  - 실패(T1·D1): `5000ms`만 전송됐고 복원 SQL은 없었다.
- 대기 증거: `lock_wait_proof` 13건. 대기 PID, `pg_blocking_pids`, 미승인 `transactionid` 잠금과 차단 트랜잭션 ID를 대조했다. 조정 13건은 시작·종료 기록이 모두 짝을 이룬다.
- 관리 조회(필수 하위 사례 187건 저장·재읽기):
  - 앞 카드(l1) 커밋과 snapshot 보존, l2의 버전 + 1과 `fsrs` 또는 무변경, cursor·실행 상태
  - 두 접근 테이블에 대한 업무 쓰기 0, 다른 계정·범위 밖 자료 불변
  - 관리자 변경 66건의 영향 행·직후 경로·원복
- 원복 재관측: K2a·K2b·K3·S2·S3·S3b의 쓰기 역할 6건 모두 `matches_contract`, 생성 1·인계 1·문장 0·쓰기 0·커밋 0이다.
- 사후 확인: 업무 세션 0, idle in transaction 0, 미승인 잠금 0, 정지점 7개 모두 해제, 작업 스레드 20개 모두 종료, 24개 DB의 경로 4-0 복귀, 다른 계정 자료 불변. `final_cleanup_ended`가 기록됐다.
- R2 정리:
  - 정리 전 기록에는 차단 사건이 없었다(`blocking_events` 빈 목록).
  - 실행기가 기록과 현재 대상(PID·실행 파일·경로·리스너·식별값·DB·역할 OID·업무 세션)을 대조한 뒤 정리했다.
  - 정리 뒤: `C:/JV_Tools/pg68` 없음, 55522 리스너 0, PID 6720 종료, 비밀 임시 폴더 없음. `pgdata-e2` 등 다른 항목은 그대로다.
- 증거 보관:
  - `record.json`은 정리 전에 복사했다. 정리 결과는 `cleanup_stdout.log`에만 있다.
  - `C:/JV_Evidence/pg68/20261029T170041/`에 6개 파일을 덮어쓰기 없이 복사하고 다시 읽어 대조했다. 기존 루트 ACL은 정책과 같았고(세 주체 상속), 변경하지 않았다.

| 파일 | 크기 | SHA-256 |
| --- | --- | --- |
| `record.json` | 87150 | `2302e6cf6f306e07dfbf37d8e3ac0d4f419a3ce40d48ee769dc2abb6dc65e55d` |
| `target.json` | 7806 | `98085096da8af13c69f38629aca75fac6e55b6a59b62464314698ded66b6dec7` |
| `server.log` | 415340 | `b6a3ee7a6e0f0e6dd93240f6709a651d4abbf882fbfcab8f0d30756320b9965e` |
| `prepare_stdout.log` | 10 | `aba1a6c58bc0c175b5a77d0a73a018cd667b7cd07efa6a1f0bd1fa001e07635c` |
| `check_access_lock_stdout.log` | 315 | `1d491a5bdf19dccf9b69673884f3c2caa95a70f93c370e3814b4adb716ecf3ac` |
| `cleanup_stdout.log` | 9 | `0bc45c233f73cbda235d24a54875b48f859538adfff9d3f387cb39dbc791c9ba` |

- `custody.json`: 3909바이트, SHA-256 `177e0d41fbe212572ebf452b1cee2cad04242046902e58beb75a11cce988694a`, 재읽기 일치. 보존 기한 2027-10-29, 자동 삭제 없음. 임시 원본은 세션 임시 폴더에 그대로 두었고 별도 사본은 보류다. RS4·PG67 보관본은 바뀌지 않았다.
- 비밀값 확인: 6개 파일에 DSN·비밀번호·개인 키·SCRAM 검증값 형태가 없다. 서버 로그의 교착 상세에는 문장 텍스트가 있지만, 매개값은 `$1`·`$2` 자리표시자로만 남고 바인딩 값은 없다.
- 시험 키: `check-access-lock`이 시험 전용 임시 OpenSSH 키를, `prepare`가 시험용 TLS 인증서를 만들어 쓰고 정리했다. 사용자 키·`.ssh`·`ssh-agent`·운영 신뢰 루트는 쓰지 않았다.
- 참고: `LQ4_CHANGES_APPROVED = True`이므로, 승인 전 상태를 단언하는 가드 검사(`test_changes_locked_until_v3`의 `None` 단언)는 이제 맞지 않는다. 이번에는 가드를 다시 돌리거나 고치지 않았다.
- 미검증: 운영 환경·운영 자료, 커밋 응답 유실·서버 강제 종료, `users`·카드 잠금 단계의 대기 시간, 복원 뒤 서버 설정값 자체, 실제 백업·복원(C10 `restore_verified`·`backup_artifact_checked`는 `false`). 이 결과는 운영 준비 완료가 아니다. 결과 검토 대기.

## 15. 독립 결과 검토와 마감 (2026-10-29, 실제 PG 재실행 없음)

- 범위: PostgreSQL 18.6·합성 자료·PG68의 구독 카드 접근 판정 잠금 경로다. 원시 증거는 읽기만 했으며, 과거 실행 결과와 합산하거나 소급하지 않았다.
- 보관 대조:
  - 14-1 표의 6개 파일과 `custody.json`의 크기·전체 SHA-256이 모두 일치한다. 인수 기록에 적힌 임시 출발본도 6/6 일치했다. 실행 ID, `target_written` 1건의 대상 파일 해시, `server_started` PID·실행 파일·데이터 경로·포트도 서로 맞는다.
  - 보관 루트의 명시적 ACL과 pg68·실행 폴더·6개 파일·인수 기록의 상속 ACL을 SID 기준으로 읽었다. 작업 사용자·SYSTEM·Administrators의 전체 권한만 있으며 정책 밖 주체가 없다. ACL·원본·보관본은 변경하지 않았다.
  - 연결 문자열·개인 키·SCRAM 검증자·비밀번호 대입 형태를 확인했고 0건이었다. 해시 일치는 동일 바이트의 확인이며 독립 진본성이나 보존 보증이 아니다. 별도 사본 보류와 임시 원본 유지 정책은 그대로다.
- 실행 대조:
  - 저장된 결과는 G0·G1·본 검사 24개·사후 확인의 정확한 순서로 모두 `pass`다. 본 검사는 24/24이며 관문·사후 확인은 수에서 제외한다.
  - 서로 다른 필수 하위 사례 187개가 모두 성공으로 보존됐다. 각 검사에 CLI·관리 상태·설정·접근 표 무쓰기·범위 밖 자료 확인이 있다. 관리자 변경 기록은 66건이다.
  - 대기 증거 13건의 대기 PID·보유 PID·트랜잭션 ID와 미승인 `transactionid` 잠금을 대조했다. 조정 시작·종료 13쌍과 최종 정리 시작·종료 1쌍의 토큰이 맞고 차단 기록은 없다. 모든 조정의 join이 확인됐고, 정지점을 둔 7건의 해제도 확인됐다.
  - 서버 오류는 T1 잠금 초과와 D1 교착 각 1건이다. 오류 PID가 해당 제품 대기 PID와 맞고, D1 서버 교착 그래프의 대기 PID·차단 PID·트랜잭션 ID도 기록과 일치한다. D1 분기 P 및 제품의 `40P01` 고정 코드 처리를 확인했다. T1의 명시적 재개 성공 기록도 있다.
  - 24개 설정 전송 기록이 미리 정한 기대값과 일치한다. 이것을 복원 후 서버 설정값의 실측으로 확대하지 않는다.
  - 원복 재관측 6건 모두 계약 일치와 정확한 계수 1·1·0·0·0이다. 사후 확인에는 세션·미승인 잠금 0, 정지점 7개·스레드 20개의 해제·종료가 기록돼 있다.
- 정리 대조: `cleanup_stdout.log`의 `cleaned`를 확인했고 현재 PG68 폴더·55522 리스너·PID 6720이 없다. 보관된 `record.json`은 정리 전 사본이라는 한계를 유지한다.
- 가드의 승인 전제 보정:
  - 실제 승인값이 `True`라 기존 `None` 단언이 실패하는 것을 확인했다. 현재 값은 `True`로 단언하고, `None`·`False`에 대한 명시적 거부 검사는 유지했다.
  - 새 프로세스 검사도 승인 전 기본값에 기대고 있었다. 자식 안에서 `None`을 명시한 뒤 실제 `__main__`을 실행하도록 바꿨다. 따라서 대상 조회·실제 PG 없이 기존 승인 전 차단과 종료 코드를 계속 검사한다. 실행기 본문은 추가 변경하지 않았다.
  - 가드 55개가 단독 실행·루트 discovery에서 각각 통과했다. 안전 환경 세 값을 고정하고 PG 환경 변수·외부 `PYTHONPATH`를 제거했으며 `-X dev`에서 ResourceWarning 0이다. CasePath 시험 전용 임시 OpenSSH 키만 사용·정리했다. PG·GRANT는 다시 실행하지 않았고 공통 회귀 묶음도 반복하지 않았다.
- 마감: 이 버전과 시험 경로의 실제 로컬 검증만 마감한다. 운영, 실제 장애, users·카드 잠금 단계의 대기, 복원 후 서버 설정값, 실제 백업·복원은 여전히 미검증이다. C10 두 플래그는 false이고 새 실제 실행·운영 활성화는 별도 승인 대상이다. REPORT 111-1을 참조한다.

# 구독 카드 접근 판정 잠금(LQ1) 실제 로컬 PG 검증 계획 (2026-10-29, 계획만·승인 전)

**현재 상태(2026-10-29)**: 계획의 독립 정적 검토를 마쳤다(10절). E1~E6과 V1~V4는 승인 전이며 실행기·검사·실제 PG 작업은 시작하지 않았다.

기준 체크포인트 `ed247c1`(브랜치 `codex/fsrs-srs-replacement`). 이 문서는 계획이다. 실행기 구현, 검사 실행, PG 접속·시작, 키 생성, 폴더·클러스터·역할·DB 생성, GRANT는 하지 않았다.

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

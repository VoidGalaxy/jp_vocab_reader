# Gate C-1 계약: 통합 복습 큐와 하루 신규 목표

작성: 2026-10-09 (v0.1), 보정 v0.2: 2026-10-09 (6절 보정 내역).
브랜치 `codex/fsrs-srs-replacement`(HEAD `e2c07f8` + B-1·B-2 미커밋 작업).
상태: **계약 검토·구현 준비 문서. 제품 코드·스키마 변경 없음. 승인 대기.**
근거: `APPROVAL_2026-10-09.md`, `gate-a/DECISIONS.md` 9절, `IMPLEMENTATION_CONTRACT.md` 4~5절, `gate-b2/REPORT.md`, 실제 코드(0절).

표기: **[확정]** 승인 기록에 있는 것, **[제안]** 이 문서의 권장안(승인 필요), **[미정]** 다른 결정에 묶여 있거나 후속 계약 대상인 것.

B-2는 합성 SQLite 검증 결과다. 이 문서는 PostgreSQL 전환 준비가 끝났다는 뜻이 아니다. 다음은 여전히 미승인이고, 이 문서가 그 승인을 대신하지 않는다.

- 불완전 이력 카드의 첫 FSRS 평가 초기화
- PostgreSQL 로그 보존
- 학습 완료 기준 재승인

## 0. 현재 코드에서 확인한 사실

### 0-1. 지금의 큐 (legacy, 바꾸지 않음)

| 경로 | 실제 동작 | 위치 |
| --- | --- | --- |
| `GET /study-items?deck_id=` | 개인 카드 중 status가 unknown/uncertain이고 `next_review_at`이 NULL이거나 지난 카드. 미평가와 예정이 섞이고 known은 빠짐. LIMIT 없음 | `vocab_repository.list_study_items` |
| `GET /study-items/lexemes` | 활성 구독 덱별로 조회해 덱 id 순으로 이어 붙이고 lexeme 중복 제거. `due_only`, `limit`, `first_review_only`. known은 SQL에서 제외(first_review_only면 포함) | `lexeme_repository.list_subscribed_lexeme_study_items` |
| 프론트 `fetchStudyItems` | 모드별로 위 두 경로와 `/vocab-items`를 조합. 개인과 구독을 **각각 받아 이어 붙임**(전역 정렬 없음) | `page.tsx:3662` |
| `recent` 모드 | 이 브라우저가 기억하는 "방금 담은" 개인 단어 id 목록으로 `/vocab-items`를 거름 | `page.tsx:3750` |
| 계획 실행기 | `new` / `today` 두 모드만 사용. 하루량으로 큐를 자르지 않음 | `planStudyLauncher.ts`, `page.tsx:3838` |

### 0-2. B-2 평가 경로에서 큐 계약에 영향을 주는 사실

- FSRS 카드 평가에는 `request_id`, `expected_card_version`, `session_id`가 필요하다. 개인 카드의 정체성은 `vocab_items.id`, 구독 카드는 계정 + lexeme이다(`app/srs/storage.py`).
- 구독 평가는 활성 구독과 덱 멤버십을 평가 시점에 다시 확인한다(`require_subscription`). legacy 쓰기 가드(`shared_deck_word_access_allowed`)는 공개 덱이면 구독 없이도 허용한다. 이 차이는 그대로 남아 있다.
- 미평가 lexeme의 첫 평가는 `get_or_create_progress`가 **legacy** 행을 만든다. FSRS 계정이어도 progress 행이 없는 구독 단어의 첫 평가는 legacy 카드로 기록된다. 이 쓰기 경로는 C-2에서 다룬다.
- 개인 카드를 새로 담는 경로도 SRS 필드를 건드리지 않는다. 그래서 새 카드는 `srs_engine='legacy'` 기본값으로 생긴다.
- 불완전 이력 카드(엔진 상태 없음 + 기존 기록 있음)의 FSRS 평가는 `history_initialization_requires_approval`, 보류 카드는 `card_paused`, 지원하지 않는 설정 버전은 `unsupported_config_version`, 깨진 엔진 상태는 `invalid_engine_state`/`incomplete_engine_state`로 거부된다.
- 신규 집계 `introduced_on`은 개인·구독 로그에서 카드별 첫 평가 시각의 서울 날짜를 센다. legacy 로그를 포함하고, SQLite에서는 삭제된 카드의 로그도 포함한다. 매 평가마다 계정의 모든 로그를 읽는다.
- `srs_user_settings`(srs_mode, daily_new_goal 기본 20, settings_version)는 스키마만 있다. 읽거나 쓰는 코드가 없다.

## 1. 네 가지 축은 서로 독립 [확정 방향, 승인 4]

| 축 | 값 | 큐에서의 역할 |
| --- | --- | --- |
| 자기분류 `status` | unknown / uncertain / known / unclassified | **출제 조건이 아니다.** 연습 모드의 필터로만 쓰고 응답에 표시한다 |
| 복습 참여 `srs_participation` | active / paused / NULL | active만 출제한다(3절 분류) |
| 학습 완료 | completed / not_completed / unknown | **큐 조건이 아니다.** 큐 응답에 넣지 않는다(진도 API의 일) |
| 신규 여부 | 유효한 첫 평가가 없음 | 신규 목표 집계와 신규 버킷 판정에만 쓴다 |

known이어도 참여 중이면 출제한다. 완료여도 due면 유지 복습으로 출제한다. 큐가 분류를 바꾸지 않는다.

## 2. `GET /study-queue` [제안]

### 2-1. 적용 범위와 호환

- 계정의 `srs_user_settings.srs_mode = 'fsrs'`일 때만 응답한다. 설정 행이 없거나 legacy·shadow 모드면 **409 `srs_mode_not_fsrs`**를 돌려준다. 클라이언트는 그때 기존 URL을 그대로 쓴다. 기본 동작은 계속 legacy다 [확정 방향].
- 기존 `GET /study-items`, `GET /study-items/lexemes`, `/vocab-items`와 프론트의 `recent` 동작은 요청·응답·정렬을 바꾸지 않는다.
- 로그인이 필요하다(401). dev 사용자로 대체하지 않는다. 학습 계획 진도 API(`required_user_id`)와 같은 기준이다.
- 조회 전용이다. 카드·progress·구독·로그·영수증·설정·config 행·신규 실적을 만들거나 바꾸지 않는다. 읽기 전용 연결(B-2의 `get_connection(read_only=True)`)을 쓴다.

### 2-2. 요청

| 매개변수 | 값 | 기본 | 검증 |
| --- | --- | --- | --- |
| `scope` | `all` / `personal_deck` / `subscribed_deck` | `all` | 그 밖의 값은 400 |
| `deck_id` | 1 이상 2^31-1 이하 정수 | – | `scope=all`이면 금지(400), 덱 scope면 필수 |
| `mode` | `today` / `new` / `practice` | `today` | 2-4 매핑 |
| `status` | `unknown` / `uncertain` / `known` / `unclassified` (반복 가능, 최대 4개) | – | `mode=practice`에서만 허용. 서버가 중복 제거 후 정렬해 정규화한다 |
| `limit` | 1~100 | 20 | 범위 밖은 400 |
| `cursor` | 2-6의 서명된 토큰 | – | 2-6 |
| `plan_daily_new` | 0~500 정수 | – | 이 기기 계획의 하루량 Q. 덱 scope에서만 허용 |

- 이번 계약에는 **`extra_new`가 없다**(4-3). 이 매개변수가 오면 무시하지 않고 400 `unsupported_parameter`로 거부한다. 클라이언트가 추가 학습이 적용된 것으로 오해하지 않게 하기 위해서다.
- 그 밖의 알 수 없는 매개변수는 기존 FastAPI 관례대로 무시한다.

### 2-3. 대상 카드 판정 순서 (모두 LIMIT 전에)

권한·범위·멤버십·중복 제거는 SQL에서, 범주 판정과 정렬은 범위 안 카드를 다 읽은 뒤 서버에서 한다. 어느 쪽이든 LIMIT은 마지막에 한 번만 건다(IMPLEMENTATION_PLAN 3절).

1. **계정**: 인증된 사용자만 대상이다. 다른 계정의 카드는 어떤 경로로도 나오지 않는다.
2. **범위 권한**:
   - 개인 덱: 이 계정이 소유한 덱이 아니면 404 `deck not found`(기존과 같은 문구).
   - 구독 덱: 활성 구독이 없으면 404. 비공개로 바뀐 덱도 기존 활성 구독자에게는 기존 규칙대로 허용한다.
   - `scope=all`: 소유한 개인 카드 전체 + 활성 구독 덱들의 lexeme 합집합.
3. **카드 멤버십**: 구독 lexeme은 지금 `shared_deck_words`에 들어 있어야 한다. 덱에서 빠진 단어나 구독이 해제된 단어는 범위 밖이다.
4. **분류**: 범위 안의 모든 카드를 3절의 범주 하나에 넣는다. 출제 범주(단기 due, 장기 due, 신규 후보)만 다음 단계로 간다.
5. **버킷과 정렬 키**: 2-5.
6. **전역 정렬 후 LIMIT**: 개인·구독을 한 집합으로 합친 뒤 2-5 정렬 키로 정렬하고 LIMIT을 적용한다. 종류별로 LIMIT을 건 뒤 이어 붙이지 않는다. 신규 버킷의 양 제한은 2-6-3 규칙을 따른다.

### 2-4. 기존 모드와의 연결

| 기존 모드 | 기존 동작 요약 | 새 큐 연결 [제안] | 차이 |
| --- | --- | --- | --- |
| `today` | 개인: unknown/uncertain 중 due 또는 미평가. 구독: due만(known 제외) | `mode=today`: 단기·장기 due 전체 + 신규(허용량만큼) | 분류로 거르지 않음. known도 참여 중이면 출제. 신규는 목표로 제한 |
| `new` | 개인: 미평가 전부. 구독: 30개 받아 unclassified만 / 계획: `first_review_only` 30개 | `mode=new`: 신규 버킷만, 허용량만큼 | 분류 무관. 상한 30 대신 목표와 `limit` |
| `unknown` | unknown(구독은 unclassified 포함) 전부, due 무관 | `mode=practice&status=unknown(&status=unclassified)` | **예약에 반영하지 않는 연습**(2-8) |
| `uncertain` | uncertain 전부, due 무관 | `mode=practice&status=uncertain` | 연습 |
| `all` | 개인 unknown+uncertain 전부 | `mode=practice` (status 생략 = 참여 중 전체) | 연습. 범위는 참여 active 카드 |
| `recent` | 방금 담은 특정 개인 단어 id 집합 | **새 큐로 연결하지 않는다.** 기존 동작·프론트 연결을 그대로 둔다 | FSRS에서의 의미는 C-2 승인 항목(아래) |
| 계획 `new` / `today` | 덱 scope, 하루량으로 자르지 않음 | 덱 scope + `mode=new` / `today` + `plan_daily_new=Q` | 계획 Q가 실제 신규 목표가 됨 [확정 방향, 승인 5] |

`recent`는 "방금 담은 특정 단어들"이라는 의도를 보존해야 하므로 일반 신규 큐로 흡수하지 않는다(v0.1의 흡수안 철회). 다음은 C-2에서 승인받을 항목이다 [미정].

- FSRS 계정에서 `recent` 세션이 예약을 바꾸는 실제 학습인지, 예약에 반영하지 않는 연습인지.
- 실제 학습이라면 그 첫 평가들이 하루 신규 목표를 쓰는지, 목표를 넘을 때 어떻게 할지.
- 특정 id 집합을 서버에서 어떻게 조회할지(예: 별도 매개변수). 이번 서버 큐에는 넣지 않는다.

`unknown`·`uncertain`·`all`은 지금 미래 예정 카드도 실제 평가로 기록한다(legacy의 조기 평가 경로). FSRS 계정에서는 연습으로 바뀐다. 화면 문구와 버튼 변경은 C-2 이후에 한다.

### 2-5. 버킷과 정렬 키

정렬 키는 다섯 값의 튜플이다. 정렬과 커서가 **같은 키**를 쓴다.

```text
K = (bucket, sort_time, kind_rank, seq, ref_id)
```

| 구성 | 단기 due (bucket 0) | 장기 due (bucket 1) | 신규 (bucket 2) |
| --- | --- | --- | --- |
| 조건 | 참여 active, `srs_state IN (1, 3)`, `srs_effective_due_at <= server_now` | 참여 active, `srs_state = 2`, `srs_effective_due_at <= server_now` | 3절의 신규 후보 |
| `sort_time` | `srs_effective_due_at` | `srs_effective_due_at` | 개인: `vocab_items.created_at` / 구독: 문맥 덱 구독의 `imported_at` |
| `kind_rank` | 개인 0, 구독 1 | 같음 | 같음 |
| `seq` | 0 | 0 | 개인 0 / 구독: 문맥 덱의 `shared_deck_words.sort_order` |
| `ref_id` | vocab_item id 또는 lexeme id | 같음 | 같음 |

- 문맥 덱: 덱 scope면 그 덱, `scope=all`이면 그 lexeme을 포함한 활성 구독 덱 중 가장 작은 id. 신규의 `sort_time`과 `seq`는 이 문맥 덱 기준이라 결정적이다.
- `sort_order`를 신규 정렬에 쓰므로 `seq`로 키와 커서에 포함한다. 같은 덱 같은 `imported_at`의 단어들이 덱 순서대로 나온다.
- 미래 대기(`srs_effective_due_at > server_now`)는 출제하지 않고 수와 `next_due_at`만 낸다.
- `sort_time`은 저장된 UTC ISO 문자열이다. SQL이 문자열로 비교하므로 모든 값이 같은 정규 형식(`YYYY-MM-DDTHH:MM:SS[.ffffff]+00:00`)이어야 한다. 정규 형식이 아니거나 해석할 수 없는 값을 가진 카드는 출제하지 않고 3절의 `invalid_state`로 센다. 구현 때 기존 데이터의 형식을 검사한다.
- Review 카드끼리 due 시각이 같을 때 고정 순서 반복을 피하는 섞기는 Gate C 범위 밖이다. 테스트와 커서를 위해 결정적 순서를 쓴다.

### 2-6. 커서

#### 2-6-1. 형식과 신뢰

커서는 클라이언트가 바꿀 수 있는 값이므로 **신뢰하지 않는다.**

- 형식: `base64url(payload_json) + "." + base64url(HMAC-SHA256(key, payload_json))`.
- 키: 서버 비밀(`JWT_SECRET_KEY`)에서 용도 문자열 `"study-queue-cursor/v1"`로 파생한 별도 키. 비밀값은 응답이나 로그에 남기지 않는다.
- 서명 검증을 먼저 한다. 그다음 서명이 맞아도 모든 필드를 다시 검증한다(키 회전, 구현 결함 대비).
- 전체 길이는 2,048바이트 이하. 넘거나, base64·JSON 해석에 실패하거나, 서명이 틀리면 **400 `invalid_cursor`**이다. 실패 원인은 응답에 자세히 쓰지 않는다.

| 필드 | 형식·범위 |
| --- | --- |
| `v` | 정수 1 |
| `uid` | 인증된 사용자 id와 같아야 함 |
| `scope`, `deck_id`, `mode`, `status` | 요청과 같은 정규화 값(status는 중복 제거·정렬된 목록) |
| `config_version` | 현재 엔진 설정 버전과 같아야 함, 128자 이하 |
| `seoul_date` | `YYYY-MM-DD`, 현재 서울 날짜와 같아야 함 |
| `goal_basis` | `{account_daily_goal 0~500, settings_version ≥0, plan_daily_new 0~500 또는 null, account_introduced_status exact/unknown, scope_introduced_status exact/unknown/null}` (상태 두 개는 손상 시각 보정에서 추가) |
| `server_now0` | UTC ISO 문자열, 현재 시각 이전이며 현재 시각과 15분 이내 [제안: 최대 수명] |
| `new_allowed0` | 0~500, 첫 페이지에서 계산한 신규 허용량 |
| `new_served` | 0 이상 `new_allowed0` 이하 |
| `last_key` | `[bucket 0~2, sort_time(정규 UTC ISO, 40자 이하), kind_rank 0~1, seq ≥0 정수, ref_id ≥1 정수]` |
| `iat` | 발급 시각(UTC ISO) |

#### 2-6-2. 무효화

다음 중 하나라도 현재 요청이나 서버 상태와 다르면 **409 `cursor_stale`**이다. 클라이언트는 커서를 버리고 첫 페이지부터 다시 조회한다.

- 인증 계정(`uid`)
- scope, deck_id, mode, 정규화한 status
- 엔진 설정 버전
- 서울 날짜(자정을 넘김)
- 목표 계산 조건: 계정 목표, `settings_version`, 요청의 `plan_daily_new`
- 커서 수명 15분 초과 [제안]

계정 모드가 legacy로 돌아갔으면 커서와 무관하게 409 `srs_mode_not_fsrs`이다.

#### 2-6-3. 페이지 계산과 신규 양

- 첫 페이지: `server_now0 = server_now`, `new_allowed0 = 4-2의 허용량`, `new_served = 0`.
- 다음 페이지: 버킷 판정 기준 시각은 `server_now0`를 그대로 쓴다. 신규 잔여량은 `new_allowed0 - new_served`이다. 첫 페이지 뒤에 사용자가 평가한 신규 때문에 `introduced_today`가 늘어도 허용량을 다시 계산하지 않는다. 그렇지 않으면 이미 낸 카드가 두 번 차감된다.
- 한 페이지는 다음 순서로 고른다.
  1. 정렬 키가 `last_key`보다 큰 출제 후보만 남긴다(키셋 조건).
  2. 그 안에서 신규 후보를 정렬 순서대로 `min(limit, 신규 잔여량)`개까지 고른다.
  3. due 후보와 합쳐 전역 정렬하고 `limit`개를 자른다.
  4. 반환한 신규 수를 `new_served`에 더한다.
- **금지**: 신규 후보 전체에서 앞쪽 N개를 먼저 자른 뒤 `last_key` 조건을 거는 방식. 다음 페이지가 비게 된다.

검산(신규 허용량 6, due 0, `limit=4`, 신규 후보 n1…n9가 키 순서):

| 단계 | 올바른 순서(키셋 → 잔여량) | 잘못된 순서(잔여량 → 키셋) |
| --- | --- | --- |
| 1페이지 | 잔여 6. 키셋 조건 없음 → n1…n9 중 min(4, 6)=4개: **n1–n4**. `new_served=4` | 잔여 6 → 앞 6개 n1–n6 → limit 4: n1–n4 |
| 2페이지 | 잔여 2. `> n4` → n5…n9 중 2개: **n5, n6**. `new_served=6` | 잔여 2 → 앞 2개 **n1, n2** → `> n4` 조건으로 모두 탈락 → **빈 페이지** |
| 3페이지 | 잔여 0 → 신규 없음. due도 없으면 `next_cursor=null` | – |

- `next_cursor`는 이번 페이지가 `limit`개로 꽉 찼고 남은 출제 후보(due, 또는 잔여 신규)가 있을 때만 준다.

#### 2-6-4. 보장하지 않는 것

큐는 계속 변한다.

- 페이지 사이에 평가된 카드는 빠진다.
- 새로 due가 된 카드가 이미 지나간 키 앞에 있으면 이번 페이징에는 나오지 않는다.
- 다른 창의 평가는 반영되지 않는다.

클라이언트는 커서를 고정 스냅샷으로 쓰지 않는다. 다음 카드 경계, 앱 복귀, 세션 재시작 때 첫 페이지를 다시 조회한다(C-2).

### 2-7. 응답

```jsonc
{
  "server_now": "2026-10-09T01:00:00+00:00",
  "seoul_date": "2026-10-09",
  "scheduler": {"engine": "fsrs", "config_version": "fsrs-6.3.2-a1-…"},
  "items": [
    {
      "card_kind": "personal",
      "card_id": 123,
      "card_version": 7,
      "bucket": "review_due",
      "sort_key": [1, "2026-10-08T22:00:00+00:00", 0, 0, 123],
      "srs": {"phase": "review", "step": null, "due_at": "…", "effective_due_at": "…", "last_review_at": "…"},
      "config_version": "fsrs-6.3.2-a1-…",
      "is_new": false,
      "practice_only": false,
      "status": "known",
      "participation": "active",
      "review": {"method": "POST", "path": "/study-items/123/review", "shared_deck_id": null},
      "content": {"surface": "…", "base_form": "…", "reading": "…", "part_of_speech": "…",
                  "meaning_ko": "…", "dictionary_gloss": "…", "example_sentence": "…",
                  "context_explanation_ko": "…", "jlpt_level": null},
      "source_label": "기본 단어장"
    }
  ],
  "counts": {
    "total_in_scope": 600,
    "learning_due": 2, "relearning_due": 1, "review_due": 14, "pending_later": 41,
    "new_available": 380, "new_unmaterialized": 120,
    "paused": 12, "not_converted": 25, "blocked_history": 3,
    "unsupported_config": 0, "invalid_state": 1, "missing_due": 1,
    "new_allowed_now": 6
  },
  "new_goal": {
    "account_daily_goal": 20, "introduced_today": 14, "account_remaining": 6,
    "plan_daily_new": null, "introduced_today_in_scope": null, "plan_remaining": null,
    "is_strict_limit": false
    // 손상 시각 보정 후 추가: introduced_today_status, introduced_today_at_least,
    // unreadable_review_time_cards, introduced_today_in_scope_status,
    // introduced_today_in_scope_at_least, new_blocked_reason (4-5)
  },
  "next_due_at": "2026-10-09T01:07:00+00:00",
  "next_cursor": null
}
```

- C-1 응답의 모든 항목은 실제 카드 행이 있는 FSRS 카드다. `card_version`은 항상 정수다. progress 행이 없는 구독 단어는 항목으로 나오지 않고 `new_unmaterialized`로만 센다(3절).
- `review.shared_deck_id`는 평가 URL에 필요한 구독 덱 문맥(2-5의 문맥 덱)이다. 출제 문맥일 뿐 카드 정체성이 아니다. 평가 시점에 구독이 사라졌으면 평가가 404로 끝나고, 클라이언트는 큐를 다시 조회한다.
- 같은 lexeme이 여러 구독 덱에 있어도 항목과 모든 수에서 1장이다. 개인 카드와 구독 카드는 표제어가 같아도 따로 센다.

### 2-8. 연습 모드 (자유 복습) [확정 방향, 승인 7]

- `mode=practice`는 참여 active이면서 엔진 상태가 정상인 카드(단기·장기 due, 미래 대기) 중 status 필터에 맞는 카드를 due와 무관하게 돌려준다.
- 모든 항목은 `practice_only: true`, `review: null`이다.
- 정렬 키는 2-5와 같은 다섯 값이다. bucket은 0으로 고정하고, `sort_time`은 `srs_effective_due_at`이다. 신규 목표를 쓰지 않는다.
- 신규 후보는 연습 대상에서 뺀다 [제안: 첫 평가는 실제 평가로 남겨야 하므로].
- 연습 결과를 기존 평가 API로 보내지 않는다. 연습 기록을 저장할지는 C-2 이후에 정한다 [미정].

### 2-9. 오류

| 상황 | 응답 |
| --- | --- |
| 로그인 안 함 | 401 |
| 계정이 FSRS 모드가 아님 | 409 `srs_mode_not_fsrs` (클라이언트는 기존 URL 사용) |
| 개인 덱이 없거나 다른 계정 소유 / 구독 덱에 활성 구독 없음 | 404 `deck not found` |
| 매개변수 형식·범위 오류, 허용되지 않는 조합 | 400 (`invalid scope`, `deck_id required`, `status requires practice` 등) |
| `extra_new` 전송 | 400 `unsupported_parameter` |
| 커서 해석·서명·길이·필드 범위 오류 | 400 `invalid_cursor` |
| 커서 조건 불일치·수명 초과·서울 날짜 변경 | 409 `cursor_stale` |
| 엔진 상태가 깨진 카드·형식이 맞지 않는 시각 | 그 카드만 3절 범주로 세고 응답은 200. 다른 카드 출제를 막지 않음 |

## 3. 범위 안 카드의 분류와 집계

범위 안의 모든 카드는 아래 범주 **정확히 하나**에 속한다. 위에서부터 차례로 판정하고, 먼저 맞는 범주에 넣는다. 그래서 범주끼리 겹치지 않는다.

| 순서 | 범주 (`counts` 필드) | 조건 | 출제 | 평가 |
| --- | --- | --- | --- | --- |
| 1 | `new_unmaterialized` | 범위 안 구독 lexeme인데 이 계정의 progress 행이 없음 | 안 함 | 지금은 첫 평가가 legacy 행을 만듦. FSRS 생성은 C-2 |
| 2 | `not_converted` | `srs_engine = 'legacy'`. **미평가 legacy 카드 포함**(새로 담은 개인 카드, 상태만 바꾼 구독 progress 행 등) | 안 함 | 기존 URL·legacy 규칙. 전환은 B-2 도구로만 |
| 3 | `unsupported_config` | FSRS인데 `srs_config_version`이 현재 지원 설정과 다름 | 안 함 | B-2가 거부 |
| 4 | `invalid_state` | FSRS인데 참여 값이 NULL·허용값 밖, 엔진 상태 열이 일부만 있거나 범위 밖(`load_state` 오류), Learning/Relearning step이 카드 설정의 단계 수 밖(C-1 보정), 카드 자신의 평가 로그 시각을 해석할 수 없음(손상 시각 보정), 시각 형식이 정규 형식이 아님 | 안 함 | B-2가 거부(`invalid_engine_state`) |
| 5 | `paused` | FSRS, `srs_participation = 'paused'` | 안 함 | B-2가 거부(`card_paused`) |
| 6 | `blocked_history` | FSRS, active, 엔진 상태 없음, `last_reviewed_at` 있음 또는 로그 있음 | 안 함 | 불완전 이력 승인 전 거부 [미정] |
| 7 | `missing_due` | FSRS, active, 엔진 상태 있음, `srs_effective_due_at`이 NULL | 안 함 | 예약을 추정하지 않음 |
| 8 | `learning_due` / `relearning_due` | FSRS, active, 상태 1 / 3, `effective_due_at <= server_now` | 단기 due | 가능 |
| 9 | `review_due` | FSRS, active, 상태 2, `effective_due_at <= server_now` | 장기 due | 가능 |
| 10 | `pending_later` | FSRS, active, 상태 있음, `effective_due_at > server_now` | 안 함 | 미래 대기 |
| 11 | `new_available` | FSRS, active, 엔진 상태 없음, `last_reviewed_at` 없음, 로그 0건 | 신규 버킷(허용량만큼) | 가능 |

관계와 불변식:

- `total_in_scope` = 범주 1~11의 집계 필드 12개(8은 `learning_due`·`relearning_due` 두 필드) 합계. 테스트에서 이 등식을 확인한다.
- `new_available`(11)과 `new_unmaterialized`(1)는 겹치지 않는다. 같은 lexeme이 두 범주에 동시에 들어갈 수 없다(progress 행 유무로 갈림).
- `new_allowed_now`는 범주가 아니라 `min(new_available, 4-2 허용량)`이다. 합계에 넣지 않는다.
- `next_due_at` = 범주 10의 `effective_due_at` 최솟값(없으면 null).
- 같은 lexeme은 여러 구독 덱에 있어도 한 범주에 1장이다. 개인과 구독은 각각 센다.
- 범위 밖(구독 해제, 덱에서 빠짐, 다른 계정, 삭제된 카드)은 어느 범주에도 넣지 않는다.
- 위 분류는 조회만으로 계산한다. progress 행 생성을 포함해 어떤 쓰기도 하지 않는다.

### 3-1. 이번 서버 조회 작업과 C-2의 경계

| 이번(C-1 구현 시) 서버 조회 | C-2(실제 세션) |
| --- | --- |
| `GET /study-queue` 읽기 전용, 판정·정렬·집계·커서 | 평가 시작 snapshot(accountEpoch, sessionId, cardKey, version, requestId) |
| 신규 목표 계산(읽기) | 같은 request_id 재시도, 409 처리, 응답 유실 확인 |
| progress 행 없는 lexeme 수 집계 | 첫 평가에서 FSRS progress 행 생성(쓰기). 그 뒤 신규 버킷에 합침 |
| – | 새로 담은 개인 카드의 FSRS 필드 초기값 |
| 연습 모드 목록 | 연습 화면·버튼(평가 API로 보내지 않음) |
| `next_due_at`, `pending_later` 제공 | 대기 카드 안내, 타이머, 다음 카드 경계 재조회 |
| – | `recent` 세션의 FSRS 의미와 목표 적용(2-4) |
| – | 학습 단계 반복 어려움의 세션 보호(후속 필수, B-1) |

## 4. 하루 신규 목표

### 4-1. 신규 1개의 정의 [확정, 승인 5 + B-2 구현]

- 로그 시각은 문자열이 아니라 실제 UTC 시각으로 읽어 비교한다(`goals.read_utc`). 시간대가 있는 ISO 값(`Z`, 다른 오프셋 포함)은 정상이다. 시간대 없음·빈 값·해석 불가 값은 읽을 수 없는 시각이다(손상 시각 보정, 4-5).

- 카드의 첫 실제 평가 1회를, 서버가 그 평가를 받은 시각의 **서울 날짜**에 신규 1개로 센다. 첫 Again도 1개다.
- 같은 카드의 다른 평가, 재시도(같은 request_id), 이전·롤백은 신규를 다시 쓰지 않는다. 이전은 평가 이벤트를 만들지 않는다.
- 개인은 vocab_item별, 구독은 계정 + lexeme별이다. 같은 표제어가 개인과 구독에 있으면 각각 1개다.
- legacy 시절의 첫 평가도 그 날짜에 이미 반영돼 있다. 오늘 전환해도 오늘 신규가 늘지 않는다.
- 삭제된 카드의 첫 평가: SQLite에서는 로그가 남아 계속 센다. PostgreSQL에서는 CASCADE로 로그가 사라져 빠진다. **[미정] PG 로그 보존 결정에 따라 값이 달라진다.**

### 4-2. 목표와 허용량 [확정 방향 + 제안]

```text
account_remaining = max(0, account_daily_goal - introduced_today)          # 계정 전체
plan_remaining    = max(0, plan_daily_new - introduced_today_in_scope)     # plan_daily_new가 있을 때만
new_allowed_now   = min(new_available, account_remaining, plan_remaining 또는 제한 없음)
```

- 계정 목표 기본값은 20이다 [확정, 승인 5]. 저장 위치는 `srs_user_settings.daily_new_goal`(0~500)이고, 행이 없으면 20이다. 이번 구현은 값을 **읽기만** 한다(4-3).
- 기기별 계획 Q는 이 브라우저의 로컬 계획이다. 서버에 저장하지 않고 요청마다 `plan_daily_new`로 보낸다. 서버는 그 덱 scope의 오늘 신규를 직접 세서 계획 잔여를 계산한다. Q가 계정 목표를 바꾸지 않는다 [확정 방향].
- `scope=all`의 `today`에는 계정 목표만 적용한다.
- **엄격한 상한이 아니다** [확정, 승인 5·6]. 서버는 어떤 카드가 화면에 실제로 표시됐는지 알 수 없다. 여러 창·기기가 각자 받아 둔 신규 카드를 평가하면 목표를 넘을 수 있고, 초과 폭도 보장하지 않는다.
- 이미 받은 카드의 평가는 목표 초과 때문에 거부하지 않는다(B-2도 거부하지 않는다). 초과한 뒤에는 다음 조회부터 신규가 0개다.
- 목표가 0이거나 이미 달성됐어도 단기·장기 due는 그대로 낸다.
- 예약·claim·TTL·엄격한 상한은 이번 범위가 아니다 [확정, 승인 6].

### 4-3. 이번 계약에서 뺀 것과 후속 계약 [미정]

**요청별 `extra_new` 제외.** 저장하지 않는 요청값으로 추가량을 주면 추가량이 소진되지 않는다. 검산(계정 목표 20, 클라이언트가 매번 `extra_new=5` 전송):

| 조회 | 그 시점 `introduced_today` | `account_remaining` | `+ extra_new` | 허용 | 사용자가 평가한 신규 |
| --- | --- | --- | --- | --- | --- |
| 1 | 20 (목표 달성) | 0 | 5 | 5 | 5 → 누적 25 |
| 2 | 25 | 0 | 5 | 5 | 5 → 누적 30 |
| 3 | 30 | 0 | 5 | 5 | 5 → 누적 35 |
| … | 계속 | 0 | 5 | 5 | 끝없이 늘어남 |

추가량이 서버 상태로 남지 않으므로 "5개 더"가 한 번에 끝나지 않는다. 같은 값을 반복 전송하면 목표가 사실상 없어진다. 또 `IMPLEMENTATION_CONTRACT.md` 5절의 **"명시 선택한 양의 버전 있는 추가 목표량"**과 충돌한다. 그 계약은 저장되고 버전이 있는 추가량을 전제로 한다. 따라서 이번 읽기 전용 큐 계약에서 `extra_new`를 뺀다(2-2에서 400). 다음은 후속 승인 항목이다.

- 서울 날짜별로 누적되는 추가 목표량의 저장 위치와 버전.
- "더 학습" 요청의 중복 방지(같은 요청을 두 번 보내도 한 번만 더함).
- 계정 목표와 기기 계획 목표 중 어디에 더하는지, 자정에 소멸하는지.

**`PATCH /srs/settings` 제외.** 계정 목표 변경 저장은 이번 구현에 넣지 않는다. 다음 항목을 묶어 별도 계약으로 다룬다.

- `daily_new_goal` 범위(0~500)와 `settings_version` CAS.
- 변경이 오늘 이미 받은 커서·큐에 주는 영향(2-6-2에 따라 커서 무효화).
- 설정 행이 없을 때 처음 만드는 규칙.
- `srs_mode` 변경과 분리할지 여부.

**신규 집계 성능.** `introduced_on`은 매번 계정 전체 로그를 읽는다. 큐 조회도 같은 정의를 써야 하므로 로그가 많아지면 느려진다. 인덱스나 집계 방식 변경은 스키마 승인이 필요하다(IMPLEMENTATION_PLAN 4절).

### 4-4. 시간대 [확정, 승인 9]

- 저장·엔진 시각은 UTC다. 버킷 판정은 `server_now`(UTC) 하나로 한다.
- 신규 집계의 날짜 경계는 Asia/Seoul 00:00이다(고정 +09:00, 기존 코드와 같다). 응답의 `seoul_date`는 `server_now` 기준이다.
- 23:59에 받은 신규 카드를 00:01에 평가하면 다음 날 신규 1개다. 서울 날짜가 바뀌면 이전 커서는 409이고 첫 페이지부터 다시 조회한다(2-6-2).
- 기존 `/stats`의 UTC 집계는 바꾸지 않는다(Gate D).

## 5. 승인이 필요한 항목

1. `GET /study-queue`를 FSRS 모드 계정 전용으로 두고, legacy 계정에는 409를 주며, 기존 URL과 `recent` 동작을 그대로 유지하는 방식.
2. 정렬 키 `(bucket, sort_time, kind_rank, seq, ref_id)`와 신규의 문맥 덱·`sort_order` 사용(2-5).
3. 서명된 커서, 무효화 조건(계정·범위·필터·설정·서울 날짜·목표 조건·15분 수명), 페이지별 신규 양 계산 순서(2-6).
4. 범위 안 카드의 11개 범주 분류와 집계 불변식(3절). 미평가 legacy 카드는 `not_converted`.
5. 모드 매핑(2-4): `unknown`/`uncertain`/`all`을 FSRS 계정에서 연습 모드로 바꾸는 것.
6. 하루 신규 목표 계산(4-2): 계정 목표는 읽기만, `plan_daily_new`는 요청마다 전송.

후속 계약으로 남긴 것: 날짜별 추가 목표량(4-3), `PATCH /srs/settings`(4-3), `recent`의 FSRS 의미와 목표 적용(2-4, C-2), 구독 신규 progress 생성과 새 개인 카드 초기값(C-2), 연습 기록 저장.

이 문서는 다음을 승인하지 않는다: 불완전 이력 초기화, PostgreSQL 로그 보존, 학습 완료 기준, 기본 FSRS 활성화, 실제 사용자 이전, 완료 지표 변경, known 재참여 API.

## 6. 보정 내역 (v0.2)

| 항목 | v0.1 | v0.2 |
| --- | --- | --- |
| 추가 학습 | 요청별 `extra_new`(저장 안 함)를 허용량에 더함 | 제외. 반복 전송 시 소진되지 않는 검산과 기존 "버전 있는 추가 목표량" 계약과의 충돌을 기록. 날짜별 누적·중복 방지·목표 관계는 후속(4-3). 요청에 오면 400 |
| 목표 변경 API | `PATCH /srs/settings`를 C-1에 넣을지 승인 요청 | 이번 구현에서 제외, 별도 계약 대상(4-3) |
| `recent` | 일반 신규 큐로 흡수 | 철회. 특정 id 집합 의도 보존, 기존 동작·프론트 연결 유지. FSRS 의미·목표 적용은 C-2 승인 항목(2-4) |
| 정렬 키 | `(bucket, sort_time, kind_rank, ref_id)`인데 신규에 `sort_order`를 언급 | `seq`(=sort_order)를 키와 커서에 포함하고 문맥 덱 기준을 명시(2-5) |
| 커서 | 서명 없는 base64 JSON, 범위·모드·status·설정만 대조 | HMAC 서명, 필드 형식·크기·범위 검증, 계정·필터·설정·서울 날짜·목표 조건·수명에 묶음, 변조 400·조건 변경 409(2-6) |
| 신규 페이지 | "new_served로 재사용 방지"만 기술 | 첫 페이지 허용량 고정, 키셋 먼저·잔여량 나중 순서와 6=4+2 검산(2-6-3) |
| 제외 카드 집계 | 일부 범주만, 미평가 legacy 누락, 잘못된 상태 미정의 | 11개 상호 배타 범주, `total_in_scope` 합계 불변식, `new_available`/`new_unmaterialized` 관계(3절) |
| progress 행 없는 구독 단어 | 응답 예시에 `materialized:false` 항목 | C-1 응답에는 나오지 않음을 일관되게 명시, 예시에서 제거 |

## 7. 손상된 평가 시각 계약 (2026-10-09 승인·구현)

근거: `CORRUPT_REVIEW_TIME_PROPOSAL.md` 6절 다섯 항목(승인됨). 4-5로 읽는다.

### 4-5. 읽을 수 없는 로그 시각

- 카드의 로그 시각 중 하나라도 읽을 수 없으면 그 카드의 첫 평가 날짜는 **확인 불가**다. 다른 정상 로그로 대신하지 않고, 로그를 지우거나 고치지 않는다.
- 신규 수는 `exact`(정수) 또는 `unknown`(값 null)이다. 확인된 정상 카드의 오늘 신규 수는 `*_at_least`(하한)로 함께 준다.
  - 계정 전체(`introduced_today*`): 삭제된 카드를 포함해 계정의 모든 로그로 계산한다.
  - 요청 덱 scope(`introduced_today_in_scope*`): 그 scope 카드로만 계산한다.
- 큐(HTTP 200 유지):
  - 계정 신규 수가 확인 불가면 `account_remaining = null`, 신규 0개, `new_blocked_reason = "review_time_unreadable"`. scope가 정상이어도 마찬가지다.
  - `plan_daily_new`가 있고 scope 신규 수가 확인 불가면 `plan_remaining = null`, 신규 0개.
  - 예정 복습·재학습·미래 대기는 그대로 낸다.
  - 손상 로그가 있는 카드 자신은 `invalid_state`(3절 범주 4).
  - `unreadable_review_time_cards`: 계정 전체에서 첫 평가 날짜를 알 수 없는 카드 수. 카드 id와 원래 값은 내보내지 않는다.
- 커서: 계정·scope 확인 상태가 `goal_basis`에 들어간다. 상태가 바뀌면 이전 커서는 409 `cursor_stale`이다. 손상이 생긴 뒤 이미 받은 커서로 신규를 더 받을 수 없다.
- B-2 평가:
  - 다른 카드의 시각 손상은 평가를 막지 않는다. 응답과 영수증의 `srs`에 `introduced_today: null`, `introduced_today_status: "unknown"`, `introduced_today_at_least`를 기록한다(정확하면 정수와 `exact`).
  - 평가 대상 카드 자신의 로그 시각을 읽을 수 없으면, 엔진 실행과 모든 쓰기 전에 **409 `review_history_unreadable`**이다.
  - 순서: 현재 권한 → 기존 영수증 → 새 평가 검사(자기 이력 시각 포함). 성공한 같은 요청은 이후 로그 상태가 바뀌어도 처음 저장한 응답을 그대로 돌려준다. 다른 payload는 409다.
  - 완료 판정에 넘기는 이벤트는 실제 시각(그다음 로그 id) 순이다. 완료 기준과 이력 완전성(`srs_history_quality`) 판정은 바뀌지 않는다. 시각이 읽힌다는 이유만으로 이력을 완전하다고 보지 않는다.
- 큐 정렬용 카드 시각(`effective_due_at`, 신규의 `created_at`/`imported_at`)은 기존대로 정규 형식만 인정한다(2-5).
- 롤백 도구는 바꾸지 않았다. 사후 로그 시각이 손상되면 해석 예외로 롤백 트랜잭션 전체가 버려진다(부분 롤백 없음, 실행 확인).

# Gate B 저장 계약: 읽기 원문·상태의 기기 저장

작성: 2026-10-08. 브랜치 `codex/reading-storage-boundary`, HEAD `c4dd25c`. Gate A 보고([REPORT](../gate-a/REPORT.md))에 대한 사용자 결정을 반영한 계약이다.

> 보정(2026-10-08, Gate B 검토 반영): ① 삭제·재생성 후 옛 창이 새 세션을 덮던 문제를 세션 인스턴스 ID로 막았다. ② 쓰기 후 확인 실패를 `unverified`로 분리했다. ③ 잠금 요청 실패를 예외 대신 `lock_failed` 결과로 돌려준다. 아래 2·4·5·6·8절에 반영했다.

**범위:** 이번 Gate B에서는 순수 저장 모듈 `frontend/components/readingSessionStorage.ts`, 그 테스트, `npm test` 연결만 구현했다. `page.tsx`·복구 UI·인증 흐름 연결은 Gate C에 남긴다. 그래서 **현재 앱은 아직 옛 공통 키를 그대로 쓴다.**

## 1. 승인된 결정

| 항목 | 결정 |
| --- | --- |
| 저장 범위 | 백엔드 환경과 계정별 v3 키. 방문자 영역은 별도로 둔다 |
| 옛 공통 키 | 자동 복원·수정·삭제하지 않는다. 읽기와 원자료 다운로드만 허용한다 |
| 복구 | **원문만 복사가 기본**이고 전체 로컬 사본은 보조다. 전체 사본에서는 옛 서버 ID, 저장 완료 정보, 서버에 연결된 뜻/예문 필드를 제거한다. 원본은 보존한다 |
| Web Locks 미지원 | **A안.** 읽기·메모리 편집·다운로드만 허용하고, 자동 저장·복사(·삭제)는 중지한다 |
| 미저장 편집 + 수동 계정 전환 | 머무르기 / 다운로드 / 계속으로 확인한다. 다운로드는 전환 승인이 아니다(Gate C) |
| 실패 안내 | 이전 저장본이 있는지와 실패 원인을 구분한다(Gate C 문구, 이번 모듈은 구분값 제공) |

## 2. 키와 payload

- 키:
  - 계정: `jp-vocab-reader:reading-session-v3:<api-scope>:user:<userId>`
  - 방문자: `jp-vocab-reader:reading-session-v3:<api-scope>:guest`
  - `api-scope`는 `learningPlanStorageScope(apiBaseUrl)`의 결과를 호출자가 넘긴다. 값 import 제약 때문에 모듈 안에서 다시 계산하지 않는다. `:`가 들어간 scope와 1 미만·정수 아닌 userId는 거부한다.
- payload:
  - 형식: `{ version: 3, scope, owner: {kind:"user", userId} | {kind:"guest"}, instanceId, revision(1부터 1씩), updatedAt, session }`
  - `instanceId`: 키가 새로 만들어질 때(키가 없는 상태에서의 첫 저장, 복사)마다 새로 정하는 무작위 ID다(`crypto.randomUUID`, 없으면 시간+난수). 같은 세션 안에서는 바뀌지 않고 `revision`만 오른다. **세션 버전은 `{instanceId, revision}` 쌍**이다. 그래서 삭제 후 다시 만든 세션은 revision이 1로 같아도 옛 세션과 구별된다. instanceId가 없거나 비었거나 100자를 넘는 v3 payload는 `corrupt/invalid_fields`다.
  - `session`: 옛 v1/v2 payload와 같은 데이터다(원문, 분석 원문, 덱 ID, 토큰, 선택, 안내, 접힘, 최근 저장 IDs, 두 스크롤 분율).
  - 이메일·토큰·비밀번호는 넣지 않는다.
- 키의 scope·owner와 payload 안의 값이 다르면 `corrupt/owner_mismatch`다. 복원하지 않고, 덮어쓰지도 않는다.
- 옛 공통 키 `jp-vocab-reader:reading-session-v1`: 모듈은 읽기(`readLegacyReadingSession`, `readLegacyReadingSessionRaw`)만 한다. 이 키에 대한 `setItem`과 `removeItem`은 코드에 없고, 테스트도 이를 확인한다.

## 3. 읽기 결과

`empty | ok | corrupt(reason) | unavailable`. reason은 `invalid_json | unsupported_version | invalid_fields | owner_mismatch`다. 읽기는 잠금 없이 가능하다(미지원 환경 포함). 읽기는 아무것도 쓰지 않는다. 저장소 접근 거부는 `unavailable`이며, 빈 자료로 취급하지 않는다.

## 4. 쓰기 규칙 (`saveReadingSession`)

1. 미지원(`navigator.locks` 없음)이면 `unsupported`. 저장소를 건드리지 않는다.
2. 시작 전에 `signal`이 이미 취소됐거나 `isCurrent()`가 거짓이면 `cancelled`.
3. 키별 배타 잠금 `jp-vocab-reader:lock:<key>`를 얻는다. 대기 중 `signal`로 취소하면 `cancelled`.
4. 잠금을 얻은 직후 `isCurrent()`를 다시 검사한다. owner·계정 세대·읽기 세대가 바뀌었으면 `cancelled`.
5. 현재 값을 읽는다.
   - 읽기 실패 → `error/unavailable`
   - 깨진 값 → `corrupt` (덮어쓰지 않음)
   - 저장된 버전 `{instanceId, revision}`(키가 없으면 `null`)이 호출자의 `base`와 정확히 같지 않으면 → `conflict`(`stored`에 현재 버전). 다른 창의 저장·삭제·재생성이 있었다는 뜻이고, 덮어쓰지 않는다. `base: null`은 "키가 없다고 확인했다"는 뜻이라, 그사이 다른 창이 세션을 만들었으면 conflict다.
6. 원문 또는 분석 원문이 200,000자를 넘으면 `tooLarge`. 기존 값은 그대로 둔다.
7. 쓰기 직전에 `isCurrent()`를 한 번 더 확인한다.
8. 같은 instanceId로 revision+1(키가 없었으면 새 instanceId와 revision 1)을 쓰고, 다시 읽어 확인한다. 결과는 둘로 나뉜다.
   - **쓰기 자체 실패**(저장소 값은 바뀌지 않음): `setItem` 예외 → `error`, reason은 `quota | denied | unknown`. `setItem`은 끝났지만 다시 읽은 값이 이전 값 그대로 → `error/not_persisted`. 둘 다 `previous`가 붙는다.
   - **쓰기 후 확인 실패**(상태 불명): 다시 읽기가 실패하거나(`read_back_failed`), 쓴 값도 이전 값도 아닌 값이 읽히면(`read_back_mismatch`) → `unverified`. 이 결과에는 `previous`도 새 버전도 없다. 저장 성공도 이전 값 보존도 단정하지 않고, **이전 값으로 되돌리지 않는다.** 호출자는 `readReadingSession`으로 다시 읽어 새 `base`를 얻기 전에는 저장할 수 없다. 옛 `base`로 저장하면 값이 바뀐 경우 conflict가 된다.
9. 빈 세션도 지우지 않고 저장한다(revision 증가).
10. 잠금 요청 자체가 실패하면(`SecurityError` 등, 동기·비동기 예외 모두) `error/lock_failed`(`previous: unknown`)다. 잠금 없이 쓰는 우회 경로는 없다. 잠금 요청의 `AbortError`는 `cancelled`다.

실패 결과(`conflict | corrupt | tooLarge | error`)의 `previous`는 이 호출이 키를 바꾸지 않았다는 전제에서 이전 저장본이 그대로 있음(`kept`), 원래 없었음(`none`), 알 수 없음(`unknown`)을 뜻한다. 안내 문구는 실패 원인과 함께 이 값을 구분해 쓴다. `unverified`는 따로 안내한다("저장됐는지 확인하지 못했어요").

## 5. 복사 (`copyToEmptyReadingSession`)

- 사용자가 본인 자료임을 확인한 뒤에만 호출한다. 확인 UI는 Gate C다.
- 원본은 호출자가 읽은 세션 객체다(옛 공통 키 또는 방문자 영역). 모듈은 원본 객체와 원본 키를 바꾸지 않는다.
- `textOnly`(기본): 원문 하나만 남긴다. 원문이 비어 있으면 분석 원문을 쓴다. 나머지는 모두 빈 값이다.
- `full`(보조, `detachServerLinks`):
  - 제거: `deckId`, `message`, `recentlySavedVocabItemIds`, 각 토큰의 `savedVocabItemId`·`savedExampleSentence`·`savedMeaningKo`
  - 유지: 로컬 분류 상태, 사전 뜻, 분석 예문, 선택, 두 스크롤 분율, 접힘
- 잠금 안에서 목적지 키가 **없을 때만** 새 instanceId와 revision 1로 쓴다. 키가 있으면 내용이 빈 세션이거나 깨진 자료여도 `destinationExists`이고, 그대로 둔다.
- 잠금 전·후·쓰기 직전의 문맥 확인, 초과 길이, 쓰기 실패(`error`)와 확인 실패(`unverified`)의 구분, `lock_failed`, 미지원 시 `unsupported`는 저장과 같다.

## 6. 삭제 (`removeReadingSession`)

사용자가 확인한 "현재 읽기 초기화"에만 쓴다. 현재 owner의 키 하나만, 저장된 버전 `{instanceId, revision}`이 `expected`와 정확히 같을 때만 지운다. 그래서 옛 창의 삭제는 삭제 후 다시 만든 세션에 적용되지 않는다(`conflict`). 깨진 자료는 `expected: "corrupt"`를 명시해야만 지우고, 정상 세션은 `"corrupt"`로 지울 수 없다. `removeItem` 예외는 `error`다. 지운 뒤 다시 읽기에 실패하거나 값이 남아 있으면 `unverified`다. 잠금 실패는 `lock_failed`, 미지원 환경은 `unsupported`다. 다른 키와 옛 공통 키는 건드리지 않는다.

## 7. 다운로드

`rawBackupDownload(raw)`는 원자료 문자열을 그대로 내보낸다. `originalTextDownload(session)`는 메모리 편집의 원문을 내보낸다. 둘 다 파일 이름·형식·내용만 만드는 순수 함수다. Blob 생성과 클릭은 Gate C에서 사용자 동작 때만 한다. 파일 이름에는 원문을 넣지 않는다.

## 8. 검증 (Gate B)

`npm test`: 전체 61/61 통과. 그중 `readingSessionStorage.test.mts`가 27건이다(최초 19건에 보정 회귀 8건을 더함; 기존 테스트는 새 API로 갱신). 무작위 instanceId가 들어가므로 이 파일을 8번 반복 실행해 모두 통과함을 확인했다. `npm run typecheck`도 통과했다. 모든 테스트는 합성 원문, 메모리 저장소, 이름별 배타 순서를 지키는 가짜 잠금만 쓴다.

| 영역 | 확인 내용 |
| --- | --- |
| 계정·환경 격리 | 키 6종이 서로 다름, A 저장이 B·방문자·다른 환경에서 empty, 이메일·토큰 없음, owner 불일치 시 복원·덮어쓰기 거부 |
| 원본 보존 | v1/v2 읽기 호환, 깨진/미지원 구분, 저장·복사·삭제 후 옛 키 원값 동일, 옛 키 쓰기 0회 |
| 서버 연결 제거 | 원문만 복사, 전체 사본의 ID·저장 완료·서버 뜻/예문 제거와 로컬 분류·선택·위치 유지, 원본 객체 불변 |
| 목적지 | 빈 세션·깨진 자료가 있는 목적지에는 복사하지 않음 |
| 동시 쓰기 | 같은 버전 두 저장 중 하나만 ok, 나머지는 conflict. 같은 빈 목적지 두 복사 중 하나만 ok |
| [보정1] 삭제·재생성 | 저장→삭제→새 사본(rev 1) 뒤 옛 창의 rev 1 저장은 conflict, 새 사본 보존. 삭제 후 첫 저장으로 다시 만든 세션도 새 instanceId라 옛 창의 저장·삭제 모두 conflict. `base: null`로 잠금을 기다리던 저장·복사는 그사이 다른 창이 만든 세션에 conflict/destinationExists |
| [보정2] 쓰기 후 확인 실패 | 다시 읽기 실패는 `unverified`(previous·version 없음), 실제 값은 새 내용 그대로(롤백 없음), 옛 base 재저장은 conflict, 재조회한 base로는 저장. 불일치 값은 `read_back_mismatch`, 반영 안 됨은 `not_persisted`. 복사·삭제도 같은 구분 |
| [보정3] 잠금 요청 실패 | 비동기·동기 `SecurityError`, 기타 예외에서 저장·복사·삭제 모두 `error/lock_failed`, 저장소 쓰기 0회. `AbortError`는 `cancelled` |
| 대기 중 취소·계정 변경 | 잠금 대기 중 계정 변경 시 저장·복사·삭제 모두 cancelled, 대기 중 abort, 잠금 획득 후 쓰기 직전 무효화 |
| 미지원(A안) | 읽기·다운로드만 가능, 저장·복사·삭제 unsupported, 저장소 쓰기 0회 |
| 저장 실패 | 초과 길이·용량·거부·확인 실패를 원인과 이전 저장본 유무로 구분, 기존 값 동일, 실패 뒤 재시도 가능, 읽기 거부는 unavailable |
| 삭제 | 버전(instanceId+revision) 일치·현재 owner 키만, 깨진 자료는 `"corrupt"` 명시로만, 정상 세션은 `"corrupt"`로 못 지움 |

**미검증:** 실제 브라우저의 Web Locks·localStorage는 이 모듈과 아직 연결하지 않았다(Gate C·D). 가짜 잠금은 큐 순서와 abort만 흉내 낸다. 실제 창 간 배타성은 Gate A에서 내장 Chromium·localhost로만 확인했다.

## 9. Gate C로 넘기는 연결 지점

- owner 상태(pending/guest/user)를 확정한 뒤 `readReadingSession`으로 hydration한다. pending 중에는 읽지도 쓰지도 않는다.
- 자동 저장 debounce는 `saveReadingSession`을 호출한다. `isCurrent`는 `{ownerKey, accountEpoch, readingGeneration}` 비교다. 창은 마지막으로 확인한 버전 `{instanceId, revision}`(또는 키 없음 `null`)을 `base`로 들고 있다가 ok 결과의 `version`으로 갱신한다. conflict·corrupt·실패 결과는 메모리 편집을 지우지 않고 안내에 쓴다. `unverified`면 자동 저장을 멈추고, 다시 읽어 확인한 뒤에만 재개한다. `lock_failed`는 실패 안내 대상이다.
- 미지원 환경에서는 자동 저장 대신 "이 브라우저에서는 자동 저장되지 않음 + 다운로드"를 안내한다.
- 옛 키나 방문자 자료가 있고 현재 owner 키가 비어 있을 때만 복구 안내를 보여 주고 `copyToEmptyReadingSession`을 쓴다(기본은 원문만).
- 수동 계정 전환 확인(머무르기 / 다운로드 / 계속), 경계에서 읽기 상태 초기화, 분석·저장 응답 가드, `storage` 이벤트 처리.

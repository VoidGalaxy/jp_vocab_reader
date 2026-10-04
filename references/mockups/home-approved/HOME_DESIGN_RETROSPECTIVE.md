# Home Design Retrospective

> Historical record through Home V10.12. The current Home is the B2 binding
> scene in `frontend/components/HomeDashboard.tsx` and
> `frontend/public/brand/decor/home-b2-binding/`. Asset paths and "final"
> judgments below describe the V10.12 phase, not current production.

이 문서는 Home 디자인을 V10.12까지 완성하며 확인한 실패 원인, 성공한 방법,
의사결정 순서, 에셋 제작 규칙, 검증 기준을 한곳에 정리한 기준 문서다.
단순한 버전 기록이 아니라 다음 장면형 UI 작업에서 같은 시행착오를 반복하지
않기 위한 실행 매뉴얼로 사용한다.

## 1. 당시 최종 기준 상태

- Desktop production asset:
  `frontend/public/brand/decor/home-v10.12/home-v10.12-scene-desktop.png`
- Desktop source geometry: `1888 x 833`, RGB PNG
- Desktop SHA-256:
  `48B97975DB620EF819852DCFACBB232C15089B0C7359F195C035AFF4E6592726`
- Mobile production asset:
  `frontend/public/brand/decor/home-v10.5/home-v10.5-scene-mobile.png`
- Live text, icons, hit zones, callbacks, routing, auth, SRS, storage, API behavior는
  이미지에 굽지 않고 DOM과 기존 애플리케이션 로직으로 유지한다.
- Desktop scene geometry는 `1888 / 833`, mobile scene geometry는 별도 세로형
  source와 좌표를 사용한다.
- 당시 Home의 구도, 장면, 책 크기, 메모, CTA, 탭, 소품은 완료 상태였다.
  후속 작업은 명확한 사용자 문제나 기능 요구가 없으면 추가 미세조정을 하지 않는다.

## 2. 핵심 결론

Home에서 가장 오래 반복된 실패는 CSS 수치가 부족해서가 아니었다. 하나의 물리적
장면이어야 할 책, 탭, 메모, 소품, 그림자를 여러 레이어와 서로 다른 기준면으로
조립한 것이 근본 원인이었다.

최종적으로 성공한 방식은 다음과 같다.

1. 코드보다 먼저 텍스트 없는 완성 목업을 확정한다.
2. 같은 광원과 접촉 관계를 가진 정적 요소는 하나의 full-scene 이미지로 묶는다.
3. Desktop과 mobile은 같은 이미지를 축소하지 않고 별도 silhouette로 설계한다.
4. 텍스트와 동작만 DOM overlay로 남기고 source 기준 좌표를 퍼센트로 측정한다.
5. 에셋 제작과 production 연결을 Gate A/Gate B로 분리한다.
6. 부분 수정은 색상 임계값이 아니라 실제 물리 레이어를 기준으로 제한한다.
7. 빌드 성공이 아니라 실제 화면의 첫인상과 실측 결과로 승인한다.

## 3. 시행착오 흐름

### 3.1 분리 에셋 조립 단계

초기 구조는 책, 탭, Shiori, 메모, CTA, 접지 그림자를 별도 이미지와 CSS로
조립했다. 개별 파일은 괜찮아 보여도 브라우저에서는 다음 문제가 반복됐다.

- 책과 그림자의 원근, 광원, 크기가 서로 달라 책이 공중에 떠 보였다.
- 탭 그림자가 책 그림자와 연결되지 않아 책 아래에 붙은 물체가 아니라 별도 스티커로
  보였다.
- `::before`, `::after`, radial/linear gradient, broad blur는 실제 책상 질감 위에서
  사각 판, 검은 띠, 잘린 blur 경계로 드러났다.
- 큰 원본에서 은은했던 그림자가 실제 렌더 크기에서는 사라졌다.
- 위치를 CSS로 반복 보정해도 장면의 첫인상은 거의 변하지 않았다.

이 단계의 교훈은 명확하다. 같은 물체군을 CSS 레이어로 다시 조립하지 않는다.

### 3.2 V7-V9 plate 실험

책과 탭을 plate로 묶는 방향은 맞았지만, 불투명 matte, 경계 잔여물, 잘못된 그림자
여백과 crop이 남았다. 특히 V9 계열에서는 책 주변에 직사각형 색면과 검은 영역이
생겨 합성 흔적이 장면보다 먼저 보였다.

실패 원인:

- 투명 알파와 그림자 padding을 production 크기에서 검증하지 않았다.
- 원본의 배경색이나 matte가 남은 plate를 투명 전경처럼 사용했다.
- 책, 탭, 그림자가 묶였어도 책상과 소품은 다른 광원 시스템에 남아 있었다.
- 코드 연결 전에 완성 장면 전체를 실제 viewport crop으로 보지 않았다.

결론:

- 부분 plate가 아니라 desk까지 포함한 opaque full scene으로 전환한다.
- 투명 foreground가 꼭 필요하다면 검정, 흰색, checkerboard, 실제 배경 네 곳에서
  알파와 halo를 확인한다.

### 3.3 V10 full-scene 전환

V10.1에서 책, 메모, CTA, 탭, Shiori, 책상과 그림자를 한 장면으로 묶고 DOM에는
텍스트와 hit zone만 남기면서 가장 큰 전환이 일어났다. 이때부터 화면이 "PNG를 붙인
웹페이지"가 아니라 한 장의 실제 책상 장면으로 읽히기 시작했다.

다만 full scene만으로 자동 해결되지는 않았다.

- V10.1/V10.2는 `cover` crop과 source 비율 때문에 좌우가 잘리거나 책이 오른쪽으로
  밀렸다.
- 와시테이프, 펜, 클립을 기존 장면 위에 다시 붙이면 광원과 접촉 그림자가 달라
  소품이 떠 보였다.
- 가정한 viewport 높이와 실제 `svh`가 달라 특정 해상도에서 소품이 예상과 다르게
  잘렸다.
- Desktop 장면을 mobile에 재사용하면 제목과 책 모서리가 crop됐다.

통과한 해결:

- V10.3에서 중심 구도와 source ratio를 다시 잡았다.
- V10.4는 `1888 x 833` desktop source로 상하 crop 없이 가로 방향만 안전하게
  crop되도록 정리했다.
- V10.5는 mobile용 세로 장면을 별도로 만들고 위아래 desk 여백을 확장했다.
- 소품은 full scene에 다시 합성해 같은 광원과 그림자 체계에 넣었다.

### 3.4 하단 책 모서리와 page block 수정

V10.6 이후에는 전체 구도보다 책 하단의 물리 구조가 문제였다. 이 구간에서 가장
중요한 교훈은 "색을 바꾸는 것"과 "구조를 고치는 것"은 다르다는 점이다.

#### V10.7 실패

증상:

- 검은 하단 외곽선을 밝히자 두꺼운 연속 녹색 띠로 바뀌었다.
- 좌우 corner, front-cover lip, page block, rear-cover return이 하나의 경계처럼
  보였다.

원인:

- `G >= R - 6` 같은 색상 임계값으로 leather를 선택했다.
- 서로 다른 물리 레이어가 비슷한 색을 갖는다는 사실을 무시했다.
- 기존의 잘못된 band geometry를 유지한 채 RGB만 바꿨다.

재발 방지:

- 물체 경계 수정에 단순 hue/luminance threshold를 최종 mask로 사용하지 않는다.
- cover, bevel, page, rear cover, desk shadow를 위치와 연결 관계로 분리한다.

#### V10.8-V10.9 개선

- source를 이전 실패본이 아니라 구조가 비교적 온전한 V10.4로 되돌렸다.
- column별 physical stack을 탐지하고 좌우 corner를 서로 다른 폭과 taper로 처리했다.
- front-cover lip, page block, rear return, corner fold를 독립 mask로 만들었다.
- 좌우 recessed side와 grounding을 따로 보정해 mirror clone 느낌을 피했다.

#### V10.10 실패와 회복

첫 procedural candidate는 page line이 규칙적이고, scan-range 오류로 세로 picket-fence,
검은 wedge, comb 형태가 생겼다. 확대 crop에서는 개선처럼 보여도 전체 장면에서는
새로운 합성 흔적이 더 강했다.

통과한 방식:

- Image generation은 물리 구조의 reference를 만드는 용도로만 사용했다.
- 실제 production 결과는 bounded deterministic compositor로 만들었다.
- editable envelope 밖 픽셀은 완전히 동일하게 유지했다.
- visible tab body와 보호 surface는 byte-identical 검사를 적용했다.
- 검은 cavity는 임의의 검정 fill이 아니라 주변 page와 desk-contact texture를 이용해
  연결했다.

#### V10.11-V10.12 마감

- page block의 반복적인 수평선 대비를 낮췄다.
- tab root의 작은 near-black gap을 짧은 warm contact shadow로 바꿨다.
- 세 tape의 밝기와 질감에 작은 차이를 줬다.
- yellow/coral/blue tab의 과도한 saturation을 낮췄다.
- cover lip, corner, 전체 그림자, 레이아웃과 mobile 장면은 변경하지 않았다.

이 단계에서 수정 범위는 장면 전체가 아니라 명시된 envelope 안으로 제한했고,
V10.12를 Home desktop의 최종 production 기준으로 확정했다.

### 3.5 상단 navigation과 장면 이음매

Home 장면과 별도로 상단 탭도 물리적 종이 띠로 재설계했다. 여기서 확인된 실패는
다음과 같다.

- paper strip이 두꺼워 콘텐츠를 누르고 탭이 과도하게 무거워졌다.
- active 상태만 크기가 달라져 탭 이동 때 인접 항목이 흔들렸다.
- strip 하단과 장면 사이에 빈 줄이 보였다.
- Reading, Deck, Stats, Classify, Vocab의 legacy title tag가 nav 뒤로 튀어나왔다.
- 종이의 마지막 불투명 행을 직접 어둡게 하자 모든 배경에서 회색/검은 stroke가
  보였다.

통과한 해결:

- 모든 desktop slot을 `106 x 36`, active linen을 `98 x 36`으로 고정했다.
- legacy protrusion은 desktop render에서 역할을 제거하고 mobile은 보존했다.
- scene의 상단 corner를 square로 맞춰 strip과 하나의 이음매로 연결했다.
- 종이 내부 edge를 어둡게 하지 않고, alpha 바깥에 짧고 부드러운 warm shadow를
  별도 bake했다.
- paper strip은 배경이 아니라 장면 위에 놓인 실제 한 장의 종이로 보이도록 끝냈다.

## 4. 실패 패턴과 대응표

| 보이는 증상 | 실제 원인 | 실패한 대응 | 통과한 대응 |
| --- | --- | --- | --- |
| 책이 떠 보임 | 물체와 그림자가 서로 다른 기준면/광원 | CSS blur 확대 | 같은 scene에 contact+ambient shadow bake |
| 그림자가 안 보임 | 원본에서만 보이고 렌더 크기에서 소실 | opacity만 증가 | 실제 표시 크기로 먼저 검사 |
| 검은 띠/사각형 | blur canvas, matte, clipped shadow | 추가 pseudo-element | alpha/envelope 재제작 또는 opaque full scene |
| 탭이 스티커처럼 보임 | page/tape/tab/shadow 접촉 구조 분리 | 탭별 box-shadow | root와 page block을 한 구조로 재합성 |
| 책이 한쪽으로 밀림 | source 중심과 `cover` crop 불일치 | DOM 전체 translate | source composition/ratio 재설계 |
| 모바일 제목/모서리 crop | desktop silhouette 축소 사용 | breakpoint 위치 미세조정 | mobile 전용 세로 scene과 좌표 |
| 소품이 떠 보임 | 별도 prop 합성, 다른 그림자 | CSS shadow 추가 | full scene에 동일 광원으로 bake |
| 검은 외곽선이 녹색 띠가 됨 | 잘못된 geometry에 색만 변경 | color threshold recolor | physical-layer semantic masks |
| page block이 플라스틱처럼 보임 | flat fill/blur/규칙적 line | 선을 더 추가 | 실제 texture 재등록 + 낮은 대비 variation |
| nav 하단이 딱딱함 | opaque edge row 자체를 어둡게 함 | 더 약한 내부 stroke | alpha 밖 warm shadow + clean fiber edge |
| 탭 이동 시 크기 변화 | active style이 layout size 변경 | margin 보정 | 고정 slot, 내부 asset만 상태 변경 |
| QA는 통과했지만 디자인이 그대로 | 기계 검증만 보고 first impression 미검토 | build 반복 | before/after screenshot 판정 우선 |

## 5. 성공한 계획 수립 과정

### Step 1. 현재 실패를 세 줄로 고정한다

감상 대신 화면에서 바로 확인 가능한 문장으로 적는다.

예시:

1. page block 뒤에 긴 near-black cavity가 있어 tab이 떠 보인다.
2. 좌우 corner가 같은 폭의 어두운 tube처럼 이어진다.
3. tape shadow와 book shadow의 방향이 달라 하나의 물체로 읽히지 않는다.

이 단계에서 해결책을 섞지 않는다. 먼저 실패가 무엇인지 고정한다.

### Step 2. 변경 단위를 결정한다

- 구도, silhouette, crop이 문제면 full-scene replacement다.
- 광원과 접촉 관계가 문제면 관련 정적 물체를 하나의 plate/scene으로 묶는다.
- 한정된 물리 경계만 문제면 bounded asset reconstruction이다.
- 텍스트 위치나 hit zone만 문제면 source를 유지하고 좌표만 다시 측정한다.
- 색상만 문제처럼 보여도 geometry가 잘못됐다면 recolor를 금지한다.

### Step 3. 잠글 것과 바꿀 것을 선언한다

항상 다음을 구분한다.

- Editable: 정확한 source, 좌표 envelope, 허용되는 물리 레이어
- Protected: scene 밖 픽셀, text safe zone, visible tab body, desk, props 등
- Behavior locked: callback, routing, API, auth, SRS, storage, accessibility
- Forbidden: CSS shadow/filter/gradient, overlay patch, whole-scene repaint, production
  연결 전 임의 코드 수정

### Step 4. Gate A에서 에셋만 만든다

- production code를 수정하지 않는다.
- 후보는 같은 source size와 color mode를 유지한다.
- full scene, native crop, 4x detail, diff heatmap을 한 contact sheet에 넣는다.
- A/B/C가 필요하면 차이를 한 축으로 제한한다. 예: shadow 강도 또는 lip 두께.
- 후보를 추천하되 승인 전 production 폴더의 최종 이름으로 확정하지 않는다.

### Step 5. 사람의 첫인상으로 승인한다

다음을 순서대로 본다.

1. 전체 장면에서 문제가 사라졌는가?
2. 새 합성 흔적이 더 먼저 보이지 않는가?
3. 실제 100% 렌더 크기에서도 개선이 보이는가?
4. 4x crop에서 matte, hard mask, clone 반복이 없는가?
5. 보호 영역이 정말 그대로인가?

확대 crop만 좋아지고 전체 장면이 나빠졌다면 실패다.

### Step 6. Gate B에서 승인본만 연결한다

- 승인 후보를 re-encode 없이 versioned production 폴더로 옮긴다.
- hash와 dimensions를 다시 확인한다.
- production 연결은 image URL과 필요한 좌표만 최소 변경한다.
- CSS geometry와 application behavior는 brief가 허용하지 않으면 건드리지 않는다.
- rejected candidate와 debug 파일은 production 폴더에서 제거한다.

### Step 7. 브라우저 QA와 종료

첫 판정은 `1280` desktop과 `390` mobile에서 한다. 최종 후보는 다음을 확인한다.

- Desktop: `1280`, `1024`
- Mobile: `390`, `375`, `320`
- `scrollWidth === clientWidth`
- `currentSrc`가 breakpoint별 승인 asset인지 확인
- image request 404와 구버전 asset 요청이 없는지 확인
- 새 console error/warning이 없는지 확인
- sample, CTA, vocab, review/account branch, deck의 실제 클릭 확인
- `npm run build`는 dev server와 동시에 돌리지 않고 마지막에 한 번 실행
- `git diff --check`
- QA 종료 후 port `3000`, `8000`, `9222`와 scratch profile/database 정리

Backend가 필요한 QA는 session-only SQLite override를 사용한다. Neon/prod에는 접근하지
않는다.

## 6. 에셋 제작 규칙

### Full scene을 써야 하는 경우

- 물체가 같은 광원 아래 있고 서로 겹치거나 접촉한다.
- 그림자와 crop이 장면의 사실감을 좌우한다.
- 여러 transparent PNG의 경계가 눈에 띈다.
- responsive crop을 source 구도 단계에서 해결해야 한다.

### 분리 DOM/asset으로 남겨야 하는 경우

- 사용자별로 바뀌는 텍스트와 숫자
- 버튼 label, hint, icon, accessibility text
- 클릭/키보드 focus/hit zone
- 로딩, auth, review 분기와 같은 application state

### 부분 재구성 규칙

- 이전 실패본이 아니라 가장 구조가 온전한 source를 선택한다.
- editable envelope를 숫자로 고정한다.
- 보호 sample과 protected regions를 먼저 정의한다.
- 색상보다는 physical stack과 connectivity로 mask를 만든다.
- 좌우 corner는 독립적으로 측정하며 자동 mirror하지 않는다.
- 실루엣 밖 shadow나 matte가 필요하면 충분한 alpha padding을 준다.
- 생성 모델은 reference 또는 새 배경 영역에 사용하고 pixel lock이 필요한 결과는
  deterministic composite로 마감한다.

## 7. Claude/작업 에이전트 프롬프트 공식

첫 구현 프롬프트는 짧고 닫힌 범위로 작성한다. 긴 역사와 최종 QA 전체를 한 번에
넣지 않는다.

### Gate A 프롬프트 골격

```text
# [Phase name: Full Scene Replacement / Structural Rebuild]

현재 실패:
1. [스크린샷에서 확인되는 실패]
2. [물리 구조 또는 crop 실패]
3. [왜 CSS/기존 구조 보정으로 해결되지 않는지]

목표:
[한 문장으로 새 silhouette 또는 물리 stack 정의]

Source of truth:
- source: [정확한 파일]
- target/reference: [정확한 파일]
- source size/hash: [값]
- editable envelope: [x/y 범위]

삭제/역할 재정의:
- [폐기할 legacy layer/wrapper/asset]

보호 범위:
- [pixel-identical 영역]
- callbacks/API/auth/SRS/storage/routing unchanged

금지:
- CSS shadow/filter/gradient/pseudo-element patch
- whole-scene repaint
- 승인 전 production 연결
- 색상 threshold만으로 구조 mask 생성

Gate A 산출물:
- 동일 크기 candidate
- full/native/4x/diff contact sheet
- changed-pixel bounds와 보호 영역 검증
- 추천안 1개와 잔여 위험
- commit/push 금지
```

### Gate B 프롬프트 골격

```text
# Approved Candidate Integration

승인 후보: [파일/해시]

1. 후보를 re-encode 없이 최종 production 이름으로 확정한다.
2. production 폴더에는 최종 asset과 manifest만 남긴다.
3. [desktop 또는 mobile] source URL만 연결한다.
4. CSS geometry, coordinates, JSX structure, callbacks, API, auth, SRS,
   storage, routing은 변경하지 않는다.
5. 1280/1024/390/375/320에서 currentSrc, overflow, 404, console,
   핵심 클릭을 검증한다.
6. build는 마지막에 한 번 실행한다.
7. 서버와 scratch 파일을 정리한다.
8. commit/push는 하지 않는다.
```

좋은 표현:

- `replace`, `remove`, `source of truth`, `pixel-identical`, `bounded envelope`
- `unchanged screenshot is failure`
- `same light source`, `one physical stack`, `separate mobile silhouette`

피해야 할 표현:

- `polish`, `minor`, `slight`, `tweak`
- `CSS-only if possible`
- `알아서 자연스럽게`
- 검증할 수 없는 `더 고급스럽게`, `더 예쁘게`

## 8. 정량 검증 항목

에셋 단계에서는 필요한 항목만 선택해 기록한다.

- source/output SHA-256와 dimensions
- changed pixel count와 bounding box
- editable envelope 밖 changed pixels = 0
- protected region max-channel diff = 0
- alpha corner 값과 matte/halo 검사
- near-black connected run의 최대 길이
- crop formula와 실제 art rectangle
- text/hit-zone source percentage와 실제 DOM rectangle
- production network에서 current asset만 200/304, 구 asset request 0

숫자는 디자인 판단을 대신하지 않는다. 숫자는 승인된 시각 결과가 우연히 깨지지
않았음을 증명하는 용도다.

## 9. 중단 및 완료 기준

### 즉시 중단하고 계획으로 돌아갈 조건

- 두 번의 CSS 수정 후 before/after 첫인상이 거의 같다.
- 문제 영역을 고쳤지만 새로운 matte, line, wedge, blur patch가 생겼다.
- desktop을 고치며 mobile source나 좌표가 바뀌었다.
- protected pixel 또는 application behavior가 불필요하게 변경됐다.
- 확대 crop만 개선되고 실제 viewport에서는 개선이 보이지 않는다.

### 완료 조건

- 승인 target과 화면의 hierarchy와 silhouette가 일치한다.
- 물체의 접촉, 광원, 그림자가 하나의 장면으로 읽힌다.
- live text가 safe zone 안에 있고 기능과 접근성이 보존된다.
- desktop/mobile이 각각 의도한 source와 crop을 사용한다.
- overflow, 404, 신규 console 오류, matte, clipped shadow가 없다.
- 최종 asset, manifest, 최소 production 연결만 남고 후보/debug 파일이 정리됐다.
- 사용자가 실제 전체 화면을 보고 완료를 선언했다.

## 10. 다음 디자인 작업의 기본 순서

1. 사용자 표시 스크린샷과 현재 production 화면을 확보한다.
2. 실패를 세 줄로 작성한다.
3. 문제가 구도, 물리 구조, 좌표, 색 중 어디에 속하는지 분류한다.
4. 가장 온전한 source와 editable/protected 범위를 고른다.
5. 텍스트 없는 target 또는 candidate를 먼저 만든다.
6. Gate A contact sheet로 실제 크기와 확대를 함께 승인한다.
7. 승인본만 Gate B로 연결한다.
8. 1280/390 첫 판정 후 1024/375/320 최종 QA를 한다.
9. build, diff, process cleanup을 끝낸다.
10. commit, push, merge, branch cleanup은 사용자 승인 순서에 따라 별도 진행한다.

이 순서를 지키면 Home에서 반복됐던 CSS 루프, 떠 있는 에셋, 잘못된 crop, 검은
경계, 과도한 재생성, 불필요한 기능 회귀를 대부분 사전에 차단할 수 있다.

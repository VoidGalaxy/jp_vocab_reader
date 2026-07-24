# 시오리(Shiori) 캐릭터 디자인 스펙

> 이 문서는 시오리의 **캐릭터 조형/브랜드 규칙**과 **현재 구현(PNG 에셋 + `Shiori.tsx` variant 시스템)** 사용 규칙을 함께 정리한 스펙입니다.
> 최초 조형 기준은 `docs/design/reference/시오리 캐릭터 디자인 시안.png`이며, 아래 1~2장의 조형 설명은 그 이미지를 참고해 PNG 원화를 제작할 때 지킨 기준입니다.
> **현재 구현은 SVG/CSS로 직접 그리는 방식이 아니라, 완성된 PNG 이미지(`frontend/public/brand/shiori/shiori-<variant>.png`)를 `frontend/components/Shiori.tsx`가 variant/size에 맞게 골라 보여주는 방식입니다.** 캐릭터 조형을 바꾸려면 PNG 파일을 새로 제작해야 하며, 이 문서의 조형 설명만으로 코드가 그림을 그리지 않습니다.

---

## 1) 브랜드 역할

시오리는 앱의 **보조 안내자**입니다 — 책 속에 살며 조용히 곁을 지키는 코지한 북마크 정령으로, 화면의 핵심 정보(원문, 단어, 카드, 통계)보다 앞에 나서지 않습니다.

- 화면의 주인공은 항상 원문·단어·카드이고, 시오리는 그 옆에서 상황(읽는 중/분류 중/복습 대기/완료 등)을 조용히 알려주는 역할만 합니다.
- 브랜드 캐릭터이자 동시에 UI 상태 일러스트 역할을 겸합니다 — variant는 감정 표현이 아니라 "지금 이 화면이 어떤 상태인지"를 나타내는 신호입니다.
- 존재감보다 "있는 듯 없는 듯"한 절제가 원칙입니다. 자세한 배치 규칙은 `docs/design/ui-guidelines.md` 6장을 참고하세요 — 이 문서는 캐릭터 조형과 에셋 운영 규칙만 다룹니다.

## 2) 캐릭터 컨셉 / 조형 원칙

시오리는 "귀여운 코지 마스코트에 책갈피 장식을 붙인 것"이 아니라, **몸 자체가 책갈피인 존재**입니다. 세로로 긴 실루엣, 뚜렷한 V컷, 옆으로 드리운 고리·태슬·잎사귀 참이 장식이 아니라 캐릭터 정체성의 본체입니다. 표정은 항상 평온·졸림 쪽에 머물고, 사람형·여성형으로 치우치지 않습니다.

| 항목 | 내용 |
|---|---|
| 캐릭터 컨셉 한 줄 | 책 속에 살며 조용히 곁을 지키는 코지한 북마크 정령 |
| 외형 핵심 | 세로로 긴 북마크 실루엣(폭:높이 ≈ 1:2 이상), 둥근 상단 + 아래쪽 뚜렷한 V컷(리본 컷, 실루엣의 25~30%), 짧고 말랑한 팔다리 |
| 몸체 색감 | 크림/아이보리 몸체 고정 |
| 얼굴/표정 규칙 | 기본은 평온·졸림. 표정 종류는 평온/졸림/미소(+아주 미세한 놀람, 필요시)를 넘지 않음. 볼터치는 모든 표정 공통. 과장된 만화 표정 금지 |
| 책갈피 요소 규칙 | ① 상단 고리(ring/loop, 중앙 아닌 옆 위치) ② 옆으로 흐르는 태슬/끈(수직이면 안테나처럼 보여 금지) ③ 태슬 끝 잎사귀 참(몸통과 겹침) ④ 아래쪽 V컷(뚜렷하고 깊게). 4가지 모두 모든 variant·모든 크기에서 생략 불가 |
| 컬러 포인트 | 고리(amber/gold) · 참(sage green) · 볼터치(peach) 3개로 제한. variant별 몸 색 변경 금지 |
| 지향점 | 보조 안내자 — 화면의 주인공이 아님. 너무 여성형/사람형으로 치우치지 않은 정령/마스코트에 가까운 형태 |
| 금지사항 | 마시멜로/떡/유령형 원통 실루엣 · 태슬이 수직 안테나처럼 보이는 것 · 팔다리가 얇은 실선(철사) · 과장된 표정·다색 장식 · variant별 몸통 색/실루엣 변경 · 작은 크기에서 뭉개지는 디테일 |

> 이 조형 설명은 PNG 원화를 새로 제작하거나 교체할 때 지켜야 할 기준입니다. 코드는 이 규칙대로 그림을 그리지 않으며, 새 PNG를 발주/제작할 때 참고 자료로만 사용합니다.

---

## 3) PNG 에셋 기반 운영 방식

- 실제 파일: `frontend/public/brand/shiori/shiori-<variant>.png` (9개, 아래 4장 참고)
- 코드: `frontend/components/Shiori.tsx`의 `SHIORI_ASSET_MAP`이 variant → PNG 경로를 매핑하고, `ShioriImage`가 그 이미지를 `<img>`로 렌더링합니다. 캐릭터 형태를 SVG/CSS로 직접 그리는 코드는 없습니다.
- **Fallback 규칙**: 특정 variant의 PNG가 로드 실패(404 등)하면 `default` variant PNG로 자동 대체됩니다. `default`마저 실패하면 아무것도 렌더링하지 않아(깨진 이미지 아이콘 대신) 레이아웃이 깨지지 않습니다.
- **재해석 없음**: 참고 이미지를 픽셀 단위로 베끼지 않는다는 원칙은 PNG 원화 제작 단계에만 적용되며, 완성된 PNG는 그대로 사용합니다 — 외부 이미지 URL 사용은 여전히 금지입니다(로컬 에셋만 사용).
- **디자인 랩(참고용)**: `frontend/app/design-lab/shiori/page.tsx`는 실제 사용자 화면이 아니라 모든 variant/size 조합을 한눈에 확인하는 내부 점검용 페이지입니다. 새 PNG를 넣거나 교체했을 때 여기서 먼저 확인합니다.

## 4) 현재 Variant 목록 (9종)

| Variant | 상황 | 표정/포즈 요약 |
|---|---|---|
| `default` | 기본 마크/스탬프, 폴백 | 정면, 소품 없음, 평온 |
| `hero` | 홈 대표 일러스트용으로 준비된 에셋 | 책 위에 기대어 휴식, 졸림 |
| `reading` | 읽기 안내 | 작은 책을 들고 보는 자세, 평온 |
| `classify` | 빠른 분류 | 단어 카드 한 장을 들어 보임, 평온~미소 |
| `save` | 저장/담기 완료 확인 | 카드함(노트)에 단어를 넣음, 평온·만족 |
| `review` | 복습 대기 | 작은 책을 품에 안음, 졸림 |
| `success` | 완료 스탬프 | 양팔 살짝 들고 반짝임, 가장 밝은 미소 |
| `empty` | 빈 상태(카드함/덱/노트) | 빈 상자 옆에 서거나 기댐, 평온~살짝 처짐 |
| `loading` | 로딩/분석 중 | 책더미에 기대 꾸벅꾸벅, 완전히 감은 눈 |

> **참고**: `hero` variant PNG는 존재하지만, 현재 실제 화면 코드에서는 호출되지 않습니다. 책상 탭의 홈 히어로는 `variant="default" size="hero"`(= default 그림을 hero 크기로)를 사용합니다. `hero` variant는 디자인 랩 페이지에서만 미리보기로 쓰입니다. 아래 5장의 "화면별 실제 사용처" 표는 이 차이를 반영한 것입니다.

## 5) 화면별 실제 사용처 (코드 기준)

아래 표는 실제 컴포넌트 코드를 확인해 정리한 **현재 사용 현황**입니다.

| 화면/컴포넌트 | 사용 | variant | 비고 |
|---|---|---|---|
| 책상 (`HomeDashboard.tsx`) | `ShioriCharacter` | `default` (size `hero`) | 홈 히어로 비주얼. `hero` variant 자체는 미사용 |
| 분류 (`AnalyzeSection.tsx`) | `ShioriCharacter` | `classify` (size `lg`) | 분류 인트로 히어로 |
| 분류 완료 | `ShioriStamp` | `success` | 결과 요약 카드 상단 |
| 읽기 idle 안내 (`ReaderMode.tsx`) | `ShioriGuideCard` | `reading` | "원문에서 모르는 단어를 눌러보세요" 힌트 카드 |
| 단어 인스펙터 타이틀 (`TokenDetailSheet.tsx`) | `ShioriMark` | `reading` | 제목 옆 인라인 마크 |
| 단어 인스펙터 담기 확인 (`TokenDetailSheet.tsx`) | `ShioriStamp` | `save` | 바구니에 담았을 때 "노트에 담았어요" 라벨과 함께 표시 |
| 읽기 저장 완료 메시지 (`ReadingTab.tsx`) | `ShioriStamp` | `success` | 저장 성공 메시지 옆 |
| 복습 준비/empty (`StudySection.tsx`, `AppEmptyState`) | `ShioriCharacter` | `review` / `empty` | 학습 대상 있음=`review`, 학습 대상 없음=`empty` |
| 복습 완료 (`StudySection.tsx`) | `ShioriStamp` | `success` | 세션 완료 카드 |
| 노트 empty (`VocabSection.tsx`, `AppEmptyState`) | `ShioriCharacter` | `empty` | 목록/검색 결과 없음 |
| 덱 책장 타이틀 (`SharedDeckSection.tsx`) | `ShioriMark` | `default` | 제목 옆 인라인 마크 |
| 덱 책장 초기 로딩 (`SharedDeckSection.tsx`, `AppEmptyState`) | `ShioriCharacter` | `loading` | 목록 첫 로딩 중 |
| 덱 책장 empty (`SharedDeckSection.tsx`, `AppEmptyState`) | `ShioriCharacter` | `empty` | 덱 없음/실패 아님 |
| 덱 가져오기 성공 (`SharedDeckSection.tsx`) | `ShioriStamp` | `success` | 가져오기 완료 메시지 옆 |
| 통계/학습 일지 empty (`InfoSection.tsx`, `AppEmptyState`) | `ShioriCharacter` | `empty` | 기록 없음 |
| 베타 피드백 모달 (`GlobalFeedbackModal.tsx`) | `ShioriCharacter` | `default` | 모달 동반자, 모든 모달에 필수는 아님(`MeaningFeedbackModal`은 없음 — 정상) |

이 표가 실제 코드와 달라지면(새 화면 추가/변경 시) 이 표를 먼저 갱신합니다.

## 6) Size 사용 기준

Size는 `frontend/components/Shiori.tsx`의 `ShioriSize`(`sm`/`md`/`lg`/`xl`/`hero`)이며, 실제 px/clamp 값은 `globals.css`의 `.shiori-asset--*` 클래스가 정의합니다.

| size | 용도 | 실사용 예 |
|---|---|---|
| `sm` | 인라인 마크, 스탬프 — 항상 이 크기 | `ShioriMark`, `ShioriStamp`는 컴포넌트 자체가 항상 `sm`으로 고정 |
| `md` | 힌트 카드, 보통 크기 empty 삽화 | `ShioriGuideCard` 기본값, 읽기 empty 안내 |
| `lg` | 화면급 인트로 일러스트 | 분류 탭 인트로(`classify`) |
| `xl` | 화면의 "주인공 카드"에 얹는 큰 삽화 | 복습 준비/empty 카드, 노트 empty 카드 |
| `hero` | 화면 대표 히어로 비주얼(가장 큼) | 책상 탭 홈 히어로 |

**규칙**: `lg` 이상(= "큰 시오리")은 화면당 최대 1개만 동시에 보여야 합니다(`docs/design/ui-guidelines.md` 6장 참고). `ShioriMark`/`ShioriStamp`는 컴포넌트 정의상 항상 `sm`이라 이 규칙과 자연히 충돌하지 않습니다.

## 7) Shiori 컴포넌트 사용 규칙

`frontend/components/Shiori.tsx`가 내보내는 4개 컴포넌트만 사용합니다 — 화면에서 `<img>`나 PNG 경로를 직접 다루지 않습니다.

- **`ShioriCharacter`**: 화면급 일러스트(히어로, empty-state 삽화). `variant`/`size`를 직접 지정. `AppEmptyState`의 `mood` prop이 내부적으로 이 컴포넌트를 사용합니다.
- **`ShioriMark`**: 제목 옆 작은 인라인 브랜드 마크. 항상 `sm` 고정(컴포넌트가 강제).
- **`ShioriStamp`**: "방금 완료됨" 도장. 항상 `sm` 고정. `label`을 주면 점선 필 형태의 "포스트마크" 스타일이 되고, 없으면 캐릭터만 표시됩니다.
- **`ShioriGuideCard`**: 이미지(좌) + 한 줄 메시지(우)로 된 가로형 힌트 카드. `AppEmptyState`처럼 액션 버튼까지 포함하는 완전한 empty-state 대신, 가벼운 한 줄 힌트가 필요할 때만 사용합니다.

새 화면에서 시오리가 필요하면 이 4개 중 상황에 맞는 것을 고르고, 새 마크업/새 `<img>` 사용을 만들지 않습니다.

## 8) ShioriStamp 사용 규칙

- 완료/성공 순간에 붙는 "포스트마크"이지, 두 번째 큰 캐릭터가 아닙니다 — 항상 `sm`.
- 기본 `variant`는 `success`이지만, 문맥에 따라 다른 variant(예: `save`)를 쓸 수 있습니다 — 단, 어떤 variant를 쓰든 크기는 항상 `sm`입니다.
- `label`은 짧은 한 줄(예: "완료", "노트에 담았어요")만 사용하고, 여러 줄 설명을 넣지 않습니다.
- 한 메시지/카드에 스탬프는 1개만 — 같은 완료 상태에 스탬프를 여러 번 반복하지 않습니다.

## 9) 접근성 / alt text 기준

- 시오리는 현재 앱 전체에서 **항상 장식(decorative) 요소**로만 쓰입니다 — 실제 코드에서 `ShioriCharacter`/`ShioriMark`/`ShioriStamp`/`ShioriGuideCard`에 의미 있는 `alt` 텍스트를 넘기는 곳은 없습니다.
- `ShioriImage`는 `alt`가 비어 있으면 감싸는 `<span>`에 `aria-hidden="true"`를 자동으로 붙입니다 — 별도 처리 없이도 스크린 리더가 캐릭터를 건너뜁니다.
- **규칙**: 시오리 단독으로 화면의 유일한 정보 전달 수단이 되면 안 됩니다. 상태 정보(로딩/완료/비어있음 등)는 항상 같은 자리의 텍스트(제목/설명/메시지)로도 전달되어야 하며, 시오리 이미지는 그 텍스트를 시각적으로 보조할 뿐입니다.
- 만약 시오리 자체가 유의미한 정보를 전달해야 하는 예외적 상황이 생기면(현재는 없음) `alt`를 채우고 `aria-hidden`을 빼야 하며, 이 경우 이 문서의 "9) 접근성" 절을 먼저 갱신합니다.

## 10) 금지 사용

- **버튼 안에 시오리를 넣지 않습니다.** 버튼 옆 별개 요소(예: 스탬프)로는 배치 가능.
- **리스트 row마다 반복하지 않습니다.** 단어 목록/카드 그리드의 각 행에 시오리를 넣지 않습니다.
- **한 화면에 큰 시오리(`lg` 이상)는 2개 이상 두지 않습니다.**
- **사람형/여성형 과잉을 피합니다.** 조형은 2장의 원칙을 벗어나지 않습니다.
- **장식 목적 남발을 금지합니다.** 상태(로딩/완료/비어있음/안내)를 나타내지 않는 순수 장식으로는 사용하지 않습니다.
- **새 포즈/이미지를 함부로 추가하지 않습니다.** 아래 11장 체크리스트를 먼저 거칩니다.

## 11) 향후 새 Variant 추가 시 체크리스트

1. 기존 9종(4장)으로 정말 해결이 안 되는 새로운 "상태"인가? (색상/문구만 다른 경우는 기존 variant 재사용으로 해결)
2. 2장의 조형 원칙(실루엣/고리/태슬/참/V컷/색 제한)을 지키는 새 PNG를 제작했는가?
3. `frontend/public/brand/shiori/shiori-<variant>.png` 경로로 파일을 추가했는가?
4. `Shiori.tsx`의 `ShioriVariant` 타입과 `SHIORI_ASSET_MAP`에 새 variant를 추가했는가?
5. 이 문서의 4장(variant 목록)과 5장(화면별 실제 사용처)을 갱신했는가?
6. `docs/design/ui-guidelines.md` 6장의 배치 규칙(화면당 큰 시오리 1개, 버튼 안 금지, row 반복 금지)을 새 variant에도 그대로 적용했는가?
7. 디자인 랩(`frontend/app/design-lab/shiori/page.tsx`)에서 모든 size 조합을 미리 확인했는가?

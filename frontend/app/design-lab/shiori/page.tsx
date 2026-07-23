"use client";

// ============================================================================
// Shiori Design Lab preview -- NOT linked from the app's nav/rail/bottom-tab
// anywhere (reached only by typing the URL directly), and does not affect
// any real functional screen. Unlike the sibling /design-lab comparison
// page (static fixture sketches only), this preview imports the REAL
// production character components (components/Shiori.tsx) so what's shown
// here is exactly what real screens render -- a true swatch sheet, not a
// mockup that could drift from production. Shiori is illustrated PNG
// assets now (frontend/public/brand/shiori/shiori-<variant>.png), not
// hand-drawn SVG -- this page just confirms every variant/size loads (and
// falls back to shiori-default.png) the same way production does.
// ============================================================================

import "./shiori-preview.css";
import {
  ShioriCharacter,
  ShioriGuideCard,
  ShioriMark,
  ShioriStamp,
  type ShioriSize,
  type ShioriVariant,
} from "../../../components/Shiori";

const allVariants: Array<{ variant: ShioriVariant; label: string }> = [
  { variant: "default", label: "default" },
  { variant: "hero", label: "hero" },
  { variant: "reading", label: "reading" },
  { variant: "classify", label: "classify" },
  { variant: "save", label: "save" },
  { variant: "review", label: "review" },
  { variant: "success", label: "success" },
  { variant: "empty", label: "empty" },
  { variant: "loading", label: "loading" },
];

const allSizes: Array<{ size: ShioriSize; label: string }> = [
  { size: "sm", label: "sm" },
  { size: "md", label: "md" },
  { size: "lg", label: "lg" },
  { size: "xl", label: "xl" },
  { size: "hero", label: "hero" },
];

export default function ShioriDesignLabPage() {
  return (
    <div className="dl-shiori-preview-page">
      <header className="dl-shiori-preview-header">
        <h1>Shiori 캐릭터 시스템 미리보기 -- 이미지 에셋 기반</h1>
        <p>
          components/Shiori.tsx는 이제 SVG를 그리지 않고
          public/brand/shiori/shiori-&lt;variant&gt;.png를 그대로 불러와
          보여줍니다. 이 페이지는 그 로딩/폴백 동작이 실제 화면과 동일하게
          작동하는지 확인하는 내부 전용 페이지입니다. 운영 메뉴에는
          노출되지 않습니다.
        </p>
      </header>

      <section className="dl-shiori-preview-section">
        <h2>Hero 사이즈</h2>
        <p className="dl-shiori-preview-section-hint">
          홈 hero 장면에 실제로 쓰이는 크기 (variant=&quot;hero&quot; --
          shiori-hero.png, 책 위에서 쉬는 모습이 그림 자체에 포함됨)
        </p>
        <div className="dl-shiori-preview-hero-row">
          <ShioriCharacter variant="hero" size="hero" />
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>크기 비교 (sm / md / lg / hero)</h2>
        <div className="dl-shiori-preview-row">
          {allSizes.map(({ size, label }) => (
            <div className="dl-shiori-preview-cell" key={size}>
              <ShioriCharacter variant="default" size={size} />
              <span className="dl-shiori-preview-cell-label">{label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>Variant 9종</h2>
        <p className="dl-shiori-preview-section-hint">
          default / hero / reading / classify / save / review / success / empty / loading
          -- 각 shiori-&lt;variant&gt;.png를 그대로 로딩. 특정 variant 파일이
          없거나 로드에 실패하면 shiori-default.png로 자동 대체되고, 그마저
          없으면 깨진 이미지 아이콘 대신 아무것도 렌더링하지 않습니다
          (components/Shiori.tsx의 onError 처리).
        </p>
        <div className="dl-shiori-preview-row">
          {allVariants.map(({ variant, label }) => (
            <div className="dl-shiori-preview-cell" key={variant}>
              <ShioriCharacter variant={variant} size="md" />
              <span className="dl-shiori-preview-cell-label">{label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>ShioriMark (인라인 브랜드 마크)</h2>
        <p className="dl-shiori-preview-section-hint">
          선택 단어 패널 제목 옆, 통계 &quot;오늘 학습&quot; 소제목 옆 등에 쓰이는 축소형
        </p>
        <div className="dl-shiori-preview-row">
          <div className="dl-shiori-preview-cell">
            <ShioriMark />
            <span className="dl-shiori-preview-cell-label">mark</span>
          </div>
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>ShioriStamp (완료 표시)</h2>
        <div className="dl-shiori-preview-row">
          <div className="dl-shiori-preview-cell">
            <ShioriStamp variant="save" />
            <span className="dl-shiori-preview-cell-label">save (bare)</span>
          </div>
          <div className="dl-shiori-preview-cell">
            <ShioriStamp variant="success" label="완료" />
            <span className="dl-shiori-preview-cell-label">success + label</span>
          </div>
          <div className="dl-shiori-preview-cell">
            <ShioriStamp variant="review" label="완료" />
            <span className="dl-shiori-preview-cell-label">review + label</span>
          </div>
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>ShioriGuideCard (읽기 단어 미선택 힌트)</h2>
        <ShioriGuideCard
          variant="reading"
          message="원문에서 모르는 단어를 눌러보세요."
        />
      </section>

      <section className="dl-shiori-preview-section">
        <h2>홈 hero 적용 예시</h2>
        <p className="dl-shiori-preview-section-hint">
          실제 HomeDashboard의 .shiori-book-scene과 동일한 구성 -- 별도
          일러스트 레이어 없이 shiori-hero.png 하나만 사용
        </p>
        <div className="dl-shiori-preview-home-mock shiori-book-scene">
          <ShioriCharacter variant="hero" size="hero" />
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>빠른 분류 card stage 적용 예시</h2>
        <div className="dl-shiori-preview-classify-mock">
          <span className="shiori-glow">
            <ShioriCharacter variant="classify" size="lg" />
          </span>
          <div>
            <h3>단어를 빠르게 나눠볼까요?</h3>
            <p>원문에서 뽑은 단어를 카드처럼 넘기며 정리해요.</p>
          </div>
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>복습 완료 stamp 적용 예시</h2>
        <div className="dl-shiori-preview-review-mock">
          <ShioriStamp variant="success" label="완료" />
          <p>오늘 복습을 마쳤어요.</p>
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>복습 ready/empty 상태 적용 예시</h2>
        <p className="dl-shiori-preview-section-hint">
          StudySection의 AppEmptyState mood=&quot;review&quot;/&quot;empty&quot;와 동일한 구성
        </p>
        <div className="dl-shiori-preview-review-empty-mock">
          <ShioriCharacter variant="review" size="sm" />
          <div>
            <p>학습할 단어를 불러오세요</p>
            <p className="dl-shiori-preview-section-hint">
              덱과 학습 모드를 선택한 뒤 복습을 시작할 수 있어요.
            </p>
          </div>
        </div>
        <div className="dl-shiori-preview-review-empty-mock">
          <ShioriCharacter variant="empty" size="sm" />
          <div>
            <p>오늘은 복습할 단어가 없어요.</p>
            <p className="dl-shiori-preview-section-hint">
              새 원문을 읽고 모르는 단어를 노트에 담아보세요.
            </p>
          </div>
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>분류 카드 진행 표시 (ClassifyCardStage)</h2>
        <p className="dl-shiori-preview-section-hint">
          카드 상단 진행 배지 옆에 붙는 축소형 classify mark
        </p>
        <div className="dl-shiori-preview-classify-progress-mock">
          <ShioriMark variant="classify" />
          <span>3 / 10</span>
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>저장 바구니 담김 stamp (읽기 단어 카드)</h2>
        <p className="dl-shiori-preview-section-hint">
          Word Inspector의 &quot;저장 바구니에서 빼기&quot; 버튼 옆에 붙는 save stamp
        </p>
        <div className="dl-shiori-preview-classify-progress-mock">
          <span>저장 바구니에서 빼기</span>
          <ShioriStamp variant="save" label="노트에 담았어요" />
        </div>
      </section>
    </div>
  );
}

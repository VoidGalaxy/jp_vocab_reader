"use client";

// ============================================================================
// Shiori Design Lab preview -- NOT linked from the app's nav/rail/bottom-tab
// anywhere (reached only by typing the URL directly), and does not affect
// any real functional screen. Unlike the sibling /design-lab comparison
// page (static fixture sketches only), this preview imports the REAL
// production character components (components/Shiori.tsx) so what's shown
// here is exactly what real screens render -- a true swatch sheet, not a
// mockup that could drift from production.
// ============================================================================

import "./shiori-preview.css";
import { LibraryHeroIllustration } from "../../../components/BrandElements";
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
  { variant: "reading", label: "reading" },
  { variant: "save", label: "save" },
  { variant: "classify", label: "classify" },
  { variant: "review", label: "review" },
  { variant: "success", label: "success" },
  { variant: "empty", label: "empty" },
  { variant: "loading", label: "loading" },
];

const allSizes: Array<{ size: ShioriSize; label: string }> = [
  { size: "sm", label: "sm" },
  { size: "md", label: "md" },
  { size: "lg", label: "lg" },
  { size: "hero", label: "hero" },
];

export default function ShioriDesignLabPage() {
  return (
    <div className="dl-shiori-preview-page">
      <header className="dl-shiori-preview-header">
        <h1>Shiori 캐릭터 시스템 미리보기</h1>
        <p>
          components/Shiori.tsx를 그대로 렌더링하는 내부 전용 페이지입니다.
          운영 메뉴에는 노출되지 않습니다.
        </p>
      </header>

      <section className="dl-shiori-preview-section">
        <h2>Hero 사이즈</h2>
        <p className="dl-shiori-preview-section-hint">
          홈 hero 장면에 실제로 쓰이는 크기 (variant=&quot;reading&quot;)
        </p>
        <div className="dl-shiori-preview-hero-row">
          <ShioriCharacter variant="reading" size="hero" />
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
        <h2>Variant 8종</h2>
        <p className="dl-shiori-preview-section-hint">
          default / reading / save / classify / review / success / empty / loading
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
          실제 HomeDashboard의 .shiori-hero-scene과 동일한 구성
        </p>
        <div className="dl-shiori-preview-home-mock shiori-hero-scene">
          <LibraryHeroIllustration />
          <ShioriCharacter
            variant="reading"
            size="hero"
            className="shiori-hero-scene-character"
          />
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>빠른 분류 card stage 적용 예시</h2>
        <div className="dl-shiori-preview-classify-mock">
          <ShioriCharacter variant="classify" size="md" className="shiori-glow" />
          <div>
            <h3>단어를 빠르게 나눠볼까요?</h3>
            <p>원문에서 뽑은 단어를 카드처럼 넘기며 정리해요.</p>
          </div>
        </div>
      </section>

      <section className="dl-shiori-preview-section">
        <h2>복습 완료 stamp 적용 예시</h2>
        <div className="dl-shiori-preview-review-mock">
          <ShioriStamp variant="review" label="완료" />
          <p>오늘 복습을 마쳤어요.</p>
        </div>
      </section>
    </div>
  );
}

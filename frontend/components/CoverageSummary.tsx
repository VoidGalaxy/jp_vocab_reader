"use client";

import type { CoverageStats } from "./types";

type CoverageSummaryProps = {
  stats: CoverageStats;
};

export function CoverageSummary({ stats }: CoverageSummaryProps) {
  if (stats.uniqueTotal === 0) {
    return null;
  }

  return (
    <div className="coverage-summary">
      <div className="coverage-headline">
        <span className="coverage-percent">텍스트 커버리지 {stats.coveragePercent}%</span>
        <span className="coverage-percent-sub">
          등장 횟수 기준 {stats.occurrenceCoveragePercent}%
        </span>
      </div>
      <div className="coverage-stats-grid">
        <span className="coverage-stat coverage-stat-known">
          아는 단어 {stats.uniqueKnown}개
        </span>
        <span className="coverage-stat coverage-stat-uncertain">
          헷갈리는 단어 {stats.uniqueUncertain}개
        </span>
        <span className="coverage-stat coverage-stat-unknown">
          모르는 단어 {stats.uniqueUnknown}개
        </span>
        <span className="coverage-stat coverage-stat-unclassified">
          미분류 {stats.uniqueUnclassified}개
        </span>
        <span className="coverage-stat coverage-stat-ignored">
          조사/기호 제외 {stats.ignoredCount}개
        </span>
      </div>
      <p className="coverage-footnote">
        의미 있는 어휘 {stats.uniqueTotal}종 (등장 {stats.occurrenceTotal}회) 기준
      </p>
    </div>
  );
}

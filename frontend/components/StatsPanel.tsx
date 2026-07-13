"use client";

import { classifyMessageTone } from "./coverageUtils";
import type { DeckStats, StudyStats } from "./types";

type StatsPanelProps = {
  title: string;
  stats: StudyStats | null;
  isLoading: boolean;
  message: string;
  showDeckStats?: boolean;
};

export function StatsPanel({
  title,
  stats,
  isLoading,
  message,
  showDeckStats = false,
}: StatsPanelProps) {
  return (
    <section className="stats-panel">
      <div className="result-heading">
        <div>
          <h2>{title}</h2>
          <span>
            {stats?.scope === "deck" && stats.deck_name
              ? stats.deck_name
              : "전체 단어장"}
          </span>
        </div>
      </div>

      {isLoading ? <p className="muted-text">학습 통계를 불러오는 중입니다.</p> : null}
      {message ? (
        <p className={`message message--${classifyMessageTone(message)}`}>
          {message}
        </p>
      ) : null}

      {stats ? (
        <>
          <div className="stats-grid">
            <StatCard label="전체 단어" value={stats.total_count} />
            <StatCard label="완벽히 아는 단어" value={stats.known_count} />
            <StatCard label="헷갈리는 단어" value={stats.uncertain_count} />
            <StatCard label="모르는 단어" value={stats.unknown_count} />
            <StatCard label="오늘 복습" value={stats.due_today_count} />
            <StatCard label="총 맞음" value={stats.total_correct_count} />
            <StatCard label="총 틀림" value={stats.total_wrong_count} />
          </div>
          <div className="progress-summary">
            <div>
              <strong>진행률 {formatPercent(stats.learned_rate)}</strong>
              <span>평균 복습 레벨 {stats.average_review_level.toFixed(1)}</span>
            </div>
            <ProgressBar value={stats.learned_rate} />
          </div>

          {showDeckStats && stats.deck_stats.length > 0 ? (
            <div className="deck-stats-list">
              <h3>덱별 통계</h3>
              {stats.deck_stats.map((deck) => (
                <DeckStatsRow key={deck.deck_id} deck={deck} />
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat-card">
      <span>{label}</span>
      <strong>{value.toLocaleString("ko-KR")}</strong>
    </div>
  );
}

function DeckStatsRow({ deck }: { deck: DeckStats }) {
  return (
    <div className="deck-stat-row">
      <div>
        <strong>{deck.deck_name}</strong>
        <span>
          전체 {deck.total_count} · 아는 단어 {deck.known_count} · 헷갈림{" "}
          {deck.uncertain_count} · 모름 {deck.unknown_count} · 오늘 복습{" "}
          {deck.due_today_count}
        </span>
      </div>
      <div className="deck-progress">
        <span>{formatPercent(deck.learned_rate)}</span>
        <ProgressBar value={deck.learned_rate} />
      </div>
    </div>
  );
}

function ProgressBar({ value }: { value: number }) {
  const percent = Math.max(0, Math.min(value, 1)) * 100;
  return (
    <div className="progress-bar" aria-hidden="true">
      <div style={{ width: `${percent}%` }} />
    </div>
  );
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

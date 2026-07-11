"use client";

import { useMemo, useState } from "react";
import type { TokenWithStatus, VocabItem } from "./types";
import {
  computeReadingVocabEntries,
  filterReadingVocabEntries,
  getTokenGroupKey,
  searchReadingVocabEntries,
} from "./coverageUtils";
import type { ReadingVocabFilter } from "./coverageUtils";
import { statusLabels } from "./shared";

type ReadingVocabPanelProps = {
  tokens: TokenWithStatus[];
  vocabItems: VocabItem[];
  selectedDeckId: string;
  selectedTokenKey: string | null;
  onSelectToken: (tokenIndex: number) => void;
};

const filterOptions: Array<{ value: ReadingVocabFilter; label: string }> = [
  { value: "all", label: "전체" },
  { value: "unknown", label: "모르는 단어" },
  { value: "uncertain", label: "헷갈리는 단어" },
  { value: "unclassified", label: "미분류" },
  { value: "known", label: "아는 단어" },
  { value: "saveable", label: "저장 가능" },
];

export function ReadingVocabPanel({
  tokens,
  vocabItems,
  selectedDeckId,
  selectedTokenKey,
  onSelectToken,
}: ReadingVocabPanelProps) {
  const [filter, setFilter] = useState<ReadingVocabFilter>("all");
  const [search, setSearch] = useState("");

  // Each memo only recomputes on the input that actually changed it --
  // typing in the search box never re-derives entries from tokens/vocabItems,
  // which matters once a chunk-analyzed text has hundreds of unique words.
  const entries = useMemo(
    () => computeReadingVocabEntries(tokens, vocabItems, selectedDeckId),
    [tokens, vocabItems, selectedDeckId],
  );

  const filteredEntries = useMemo(
    () => filterReadingVocabEntries(entries, filter),
    [entries, filter],
  );

  const visibleEntries = useMemo(
    () => searchReadingVocabEntries(filteredEntries, search),
    [filteredEntries, search],
  );

  return (
    <section className="panel-card reading-vocab-panel">
      <div className="panel-card-header">
        <h3 className="panel-card-title">이 텍스트 단어 목록</h3>
        <p className="panel-card-description">
          이 텍스트에서 나온 학습 가능 단어를 모아봤어요. 단어를 누르면 원문
          위치로 이동합니다.
        </p>
      </div>
      <div className="reading-vocab-controls">
        <input
          type="search"
          className="reading-vocab-search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="단어, 읽기, 뜻으로 검색"
          aria-label="단어 목록 검색"
        />
        <div
          className="reading-vocab-filters"
          role="group"
          aria-label="상태 필터"
        >
          {filterOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`reading-vocab-filter-button${
                filter === option.value ? " reading-vocab-filter-active" : ""
              }`}
              aria-pressed={filter === option.value}
              onClick={() => setFilter(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      {visibleEntries.length === 0 ? (
        <p className="muted-text reading-vocab-empty">
          표시할 학습 단어가 없습니다.
        </p>
      ) : (
        <ul className="reading-vocab-list">
          {visibleEntries.map((entry) => {
            const key = getTokenGroupKey(entry.token);
            const isActive =
              selectedTokenKey !== null && key === selectedTokenKey;
            const label = entry.token.surface || entry.token.base_form;
            const meaning = entry.token.savedMeaningKo || entry.token.meaning_ko;
            return (
              <li key={`${key}-${entry.tokenIndex}`}>
                <button
                  type="button"
                  className={`reading-vocab-item${
                    isActive ? " reading-vocab-item-active" : ""
                  }`}
                  onClick={() => onSelectToken(entry.tokenIndex)}
                >
                  <span className="reading-vocab-item-main">
                    <span className="reading-vocab-item-word">{label}</span>
                    {entry.token.reading && entry.token.reading !== label ? (
                      <span className="reading-vocab-item-reading">
                        {entry.token.reading}
                      </span>
                    ) : null}
                  </span>
                  <span className="reading-vocab-item-meaning">
                    {meaning || "뜻 후보 없음"}
                  </span>
                  <span className="reading-vocab-item-meta">
                    <span
                      className={`reading-vocab-status-badge token-chip-${entry.status}`}
                    >
                      {statusLabels[entry.status]}
                    </span>
                    <span className="reading-vocab-occurrence">
                      {entry.token.occurrence_count || 1}회
                    </span>
                    {entry.isSaved ? (
                      <span className="reading-vocab-saved-badge">저장됨</span>
                    ) : null}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

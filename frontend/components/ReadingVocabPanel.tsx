"use client";

import { useMemo, useState } from "react";
import {
  filterReadingVocabEntries,
  getTokenGroupKey,
  searchReadingVocabEntries,
  selectReadingVocabEntriesByMode,
} from "./coverageUtils";
import type {
  ReadingSaveMode,
  ReadingVocabEntry,
  ReadingVocabFilter,
} from "./coverageUtils";
import { ChevronDownIcon, ChevronRightIcon, SearchIcon } from "./icons";
import { getDisplayMeaning, statusLabels } from "./shared";

type ReadingVocabPanelProps = {
  // Computed once in ReadingTab (shared with the Save Tray/Word Inspector)
  // instead of recomputed here, so every part of the reading workspace
  // agrees on exactly the same grouped/deduped word list.
  entries: ReadingVocabEntry[];
  selectedTokenKey: string | null;
  onSelectToken: (tokenIndex: number) => void;
  // Word Basket (Save Tray) selection -- lifted up to ReadingTab so the
  // Word Inspector's "저장 바구니에 담기" toggle and this panel's checkboxes
  // both read/write the same Set. This panel no longer owns saving itself;
  // the Save Tray's "담은 단어 저장" button is the one save action.
  selectedWordKeys: Set<string>;
  onToggleSelect: (key: string) => void;
  onReplaceSelection: (entries: ReadingVocabEntry[]) => void;
  onClearSelection: () => void;
};

const filterOptions: Array<{ value: ReadingVocabFilter; label: string }> = [
  { value: "all", label: "전체" },
  { value: "unknown", label: "모르는 단어" },
  { value: "uncertain", label: "헷갈리는 단어" },
  { value: "unclassified", label: "미분류" },
  { value: "known", label: "아는 단어" },
  { value: "saveable", label: "저장 가능" },
];

// Ties each status-specific filter chip to the same warm color language as
// the reader highlights/status badges elsewhere -- "전체"/"저장 가능" stay
// neutral since they aren't a single status. Only applied on the *active*
// chip so the idle filter row stays calm rather than rainbow-striped.
const filterColorClass: Partial<Record<ReadingVocabFilter, string>> = {
  known: "reading-vocab-filter-known",
  uncertain: "reading-vocab-filter-uncertain",
  unknown: "reading-vocab-filter-unknown",
  unclassified: "reading-vocab-filter-unclassified",
};

const quickSelectModes: Array<{ mode: ReadingSaveMode; label: string; hint: string }> = [
  {
    mode: "unknown_only",
    label: "모르는 단어 담기",
    hint: "unknown 상태 단어를 바구니에 담습니다",
  },
  {
    mode: "unknown_uncertain",
    label: "모르는+헷갈리는 단어 담기",
    hint: "unknown + uncertain 상태 단어를 바구니에 담습니다",
  },
  {
    mode: "all_unclassified",
    label: "미분류까지 담기",
    hint: "unknown + uncertain + 미분류 단어를 바구니에 담습니다",
  },
];

export function ReadingVocabPanel({
  entries,
  selectedTokenKey,
  onSelectToken,
  selectedWordKeys,
  onToggleSelect,
  onReplaceSelection,
  onClearSelection,
}: ReadingVocabPanelProps) {
  const [filter, setFilter] = useState<ReadingVocabFilter>("all");
  const [search, setSearch] = useState("");
  // Collapsed by default -- the word list is a secondary/reference panel in
  // the reader workspace, not the main event, so it starts out of the way
  // and only expands on request ("어휘 후보 보기").
  const [isCollapsed, setIsCollapsed] = useState(true);

  const filteredEntries = useMemo(
    () => filterReadingVocabEntries(entries, filter),
    [entries, filter],
  );

  const visibleEntries = useMemo(
    () => searchReadingVocabEntries(filteredEntries, search),
    [filteredEntries, search],
  );

  const selectedCount = useMemo(
    () =>
      entries.filter(
        (entry) =>
          entry.isSaveable && selectedWordKeys.has(getTokenGroupKey(entry.token)),
      ).length,
    [entries, selectedWordKeys],
  );
  // Total saveable words in this text (not just the current selection) --
  // the header-level "저장 가능" stat design improvement 1 asks for.
  const saveableCount = useMemo(
    () => entries.filter((entry) => entry.isSaveable).length,
    [entries],
  );

  return (
    <section
      className={`candidate-drawer reading-vocab-drawer${isCollapsed ? "" : " reading-vocab-drawer-open"}`}
    >
      <button
        type="button"
        className="reading-vocab-drawer-pull"
        onClick={() => setIsCollapsed((value) => !value)}
        aria-expanded={!isCollapsed}
      >
        <SearchIcon className="reading-vocab-drawer-pull-icon" />
        <span className="reading-vocab-drawer-pull-label">
          어휘 후보 {entries.length}개
          {saveableCount > 0 ? ` · 담을 수 있는 단어 ${saveableCount}개` : ""}
        </span>
        <ChevronDownIcon
          className={`reading-vocab-collapse-icon${
            isCollapsed ? " reading-vocab-collapse-icon-collapsed" : ""
          }`}
        />
      </button>
      {isCollapsed ? null : (
        <div className="reading-vocab-drawer-body">
      <p className="reading-vocab-drawer-hint">
        단어를 누르면 원문 위치로 이동하고, 체크박스로 바구니에 담을 수 있어요.
      </p>
      <div className="reading-vocab-controls">
        <div className="reading-vocab-search-wrap">
          <SearchIcon className="reading-vocab-search-icon" />
          <input
            type="search"
            className="reading-vocab-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="단어, 읽기, 뜻으로 검색"
            aria-label="단어 목록 검색"
          />
        </div>
        <div
          className="reading-vocab-filters"
          role="group"
          aria-label="상태 필터"
        >
          {filterOptions.map((option) => {
            const isActive = filter === option.value;
            const colorClass = filterColorClass[option.value];
            return (
              <button
                key={option.value}
                type="button"
                className={`reading-vocab-filter-button${
                  isActive ? " reading-vocab-filter-active" : ""
                }${isActive && colorClass ? ` ${colorClass}` : ""}`}
                aria-pressed={isActive}
                onClick={() => setFilter(option.value)}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </div>

      <div
        className="reading-vocab-quick-select"
        role="group"
        aria-label="빠른 선택"
      >
        <button
          type="button"
          className="ghost-button compact-button"
          title="전체 텍스트에서 저장 가능한 단어를 모두 바구니에 담습니다"
          onClick={() => onReplaceSelection(entries.filter((e) => e.isSaveable))}
        >
          전체 담기
        </button>
        <button
          type="button"
          className="ghost-button compact-button"
          onClick={onClearSelection}
        >
          바구니 비우기
        </button>
        {quickSelectModes.map(({ mode, label, hint }) => (
          <button
            key={mode}
            type="button"
            className="ghost-button compact-button"
            title={hint}
            onClick={() =>
              onReplaceSelection(selectReadingVocabEntriesByMode(entries, mode))
            }
          >
            {label}
          </button>
        ))}
      </div>

      <p className="reading-vocab-selection-summary">
        바구니에 담음 {selectedCount}개 · 현재 목록 {visibleEntries.length}개
      </p>

      {visibleEntries.length === 0 ? (
        <p className="muted-text reading-vocab-empty">
          <SearchIcon className="reading-vocab-empty-icon" />
          {search.trim()
            ? "찾는 단어가 없어요. 다른 단어나 읽기로 검색해보세요."
            : filter === "saveable"
              ? "담을 수 있는 새 단어가 없어요. 이미 저장한 단어는 복습 탭에서 볼 수 있어요."
              : "표시할 단어가 없어요."}
        </p>
      ) : (
        <ul className="reading-vocab-list">
          {visibleEntries.map((entry) => {
            const key = getTokenGroupKey(entry.token);
            const isActive =
              selectedTokenKey !== null && key === selectedTokenKey;
            const isChecked = selectedWordKeys.has(key);
            const label = entry.token.surface || entry.token.base_form;
            const meaning = getDisplayMeaning(
              entry.token.savedMeaningKo || entry.token.meaning_ko,
            );
            return (
              <li
                key={`${key}-${entry.tokenIndex}`}
                className={`reading-vocab-item-row${
                  isChecked ? " reading-vocab-item-row-checked" : ""
                }`}
              >
                {entry.isSaveable ? (
                  <input
                    type="checkbox"
                    className="reading-vocab-item-checkbox"
                    checked={isChecked}
                    onChange={() => onToggleSelect(key)}
                    aria-label={`${label} 저장 대상으로 선택`}
                  />
                ) : (
                  <span
                    className="reading-vocab-item-checkbox-placeholder"
                    aria-hidden="true"
                  />
                )}
                <button
                  type="button"
                  className={`reading-vocab-item${
                    isActive ? " reading-vocab-item-active" : ""
                  }`}
                  onClick={() => onSelectToken(entry.tokenIndex)}
                  title={`${label} 원문 위치로 이동`}
                >
                  <span className="reading-vocab-item-main">
                    <span className="reading-vocab-item-word">{label}</span>
                    {entry.token.reading && entry.token.reading !== label ? (
                      <span className="reading-vocab-item-reading">
                        {entry.token.reading}
                      </span>
                    ) : null}
                  </span>
                  <span className="reading-vocab-item-meaning" title={meaning}>
                    {meaning}
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
                    <ChevronRightIcon
                      className="reading-vocab-item-goto-icon"
                      aria-hidden="true"
                    />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
        </div>
      )}
    </section>
  );
}

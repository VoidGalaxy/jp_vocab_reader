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
import {
  CardFileIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  CloseIcon,
  SearchIcon,
} from "./icons";
import { getDisplayMeaning, statusLabels } from "./shared";

type ReadingVocabPanelProps = {
  // Computed once in ReadingTab (shared with the Save Tray/Word Inspector)
  // instead of recomputed here, so every part of the reading workspace
  // agrees on exactly the same grouped/deduped word list.
  entries: ReadingVocabEntry[];
  selectedTokenKey: string | null;
  onSelectToken: (tokenIndex: number) => void;
  // Word Basket (Save Tray) selection -- lifted up to ReadingTab so the
  // Word Inspector's "저장 대상으로 선택" toggle and this panel's checkboxes
  // both read/write the same Set. This panel no longer owns saving itself;
  // the Save Tray's "선택한 단어 저장" button is the one save action. Phase
  // 99 -- classifying a word as unknown/uncertain already auto-saves it, so
  // this whole panel is now framed as an auxiliary "select several words to
  // save together" tool rather than a primary save flow: labels below say
  // "선택" (select), never "담기"/"저장", to avoid reading as a second save.
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
    label: "모르는 단어 선택",
    hint: "모르는 단어를 모두 선택해요",
  },
  {
    mode: "unknown_uncertain",
    label: "모르는+헷갈리는 단어 선택",
    hint: "모르는 단어와 헷갈리는 단어를 모두 선택해요",
  },
  {
    mode: "all_unclassified",
    label: "미분류까지 선택",
    hint: "모르는 단어, 헷갈리는 단어, 미분류 단어를 모두 선택해요",
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

  return (
    <>
      {/* Phase 169 -- a physical pull-tab clipped to the book's outer edge
          (echoing the mobile V2 photo's own sticky bookmark tab, see
          globals.css), not an admin-drawer handle row spanning the page
          width. Opening it slides a panel out from the same edge
          (.reading-candidate-panel) -- still an overlay attached to the
          scene, never a separate section below the fold. */}
      <button
        type="button"
        className={`reading-candidate-tab${isCollapsed ? "" : " reading-candidate-tab-open"}`}
        onClick={() => setIsCollapsed((value) => !value)}
        aria-expanded={!isCollapsed}
      >
        <CardFileIcon className="reading-candidate-tab-icon" />
        {entries.length}
      </button>
      {isCollapsed ? null : (
        <div className="reading-candidate-panel">
      <div className="reading-candidate-panel-header">
        <span className="reading-candidate-panel-title">
          단어 스티커 트레이 · {entries.length}개
        </span>
        <button
          type="button"
          className="reading-candidate-panel-close"
          onClick={() => setIsCollapsed(true)}
          aria-label="단어 목록 닫기"
        >
          <CloseIcon className="reading-candidate-panel-close-icon" />
        </button>
      </div>
      <p className="reading-vocab-drawer-hint">
        단어를 누르면 원문 위치로 이동해요. 여러 단어를 한번에 저장하려면
        체크박스로 선택하세요.
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
          className="ghost-button compact-button reading-vocab-quick-select-button"
          title="전체 텍스트에서 저장 가능한 단어를 모두 선택해요"
          onClick={() => onReplaceSelection(entries.filter((e) => e.isSaveable))}
        >
          전체 선택
        </button>
        <button
          type="button"
          className="ghost-button compact-button reading-vocab-quick-select-button"
          onClick={onClearSelection}
        >
          선택 해제
        </button>
        {quickSelectModes.map(({ mode, label, hint }) => (
          <button
            key={mode}
            type="button"
            className="ghost-button compact-button reading-vocab-quick-select-button"
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
        현재 목록 {visibleEntries.length}개
      </p>

      {visibleEntries.length === 0 ? (
        <p className="muted-text reading-vocab-empty">
          <SearchIcon className="reading-vocab-empty-icon" />
          {search.trim()
            ? "찾는 단어가 없어요. 다른 단어나 읽기로 검색해보세요."
            : filter === "saveable"
              ? "선택할 수 있는 새 단어가 없어요. 저장한 단어는 위 저장 바구니의 '바로 복습'으로 이어서 볼 수 있어요."
              : "표시할 단어가 없어요."}
        </p>
      ) : (
        // Sticker tray -- a flex-wrap cluster of small word stickers, not a
        // stacked list of full-width admin rows. Same data/handlers as
        // before, just laid out and skinned differently (see
        // .reading-vocab-tray / .reading-vocab-sticker* in globals.css).
        <ul className="reading-vocab-tray">
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
                className={`reading-vocab-sticker-row${
                  isChecked ? " reading-vocab-sticker-row-checked" : ""
                }`}
              >
                {entry.isSaveable ? (
                  <input
                    type="checkbox"
                    className="reading-vocab-sticker-toggle"
                    checked={isChecked}
                    onChange={() => onToggleSelect(key)}
                    aria-label={`${label} 저장 대상으로 선택`}
                  />
                ) : (
                  // Already-known words can't be added -- a muted check
                  // mark (not a blank spacer) so the reason is visible at a
                  // glance without relying on the status badge text alone.
                  <span
                    className="reading-vocab-sticker-toggle-placeholder"
                    aria-hidden="true"
                    title="이미 아는 단어라 선택할 수 없어요"
                  >
                    <CheckCircleIcon />
                  </span>
                )}
                <button
                  type="button"
                  className={`reading-vocab-sticker${
                    isActive ? " reading-vocab-sticker-active" : ""
                  }`}
                  onClick={() => onSelectToken(entry.tokenIndex)}
                  title={`${label} 원문 위치로 이동`}
                >
                  <ChevronRightIcon
                    className="reading-vocab-sticker-goto-icon"
                    aria-hidden="true"
                  />
                  <span className="reading-vocab-sticker-word-row">
                    <span className="reading-vocab-sticker-word">{label}</span>
                    {entry.token.reading && entry.token.reading !== label ? (
                      <span className="reading-vocab-sticker-reading">
                        {entry.token.reading}
                      </span>
                    ) : null}
                  </span>
                  <span className="reading-vocab-sticker-meaning" title={meaning}>
                    {meaning}
                  </span>
                  <span className="reading-vocab-sticker-meta">
                    <span
                      className={`reading-vocab-status-badge token-chip-${entry.status}`}
                    >
                      {statusLabels[entry.status]}
                    </span>
                    <span className="reading-vocab-occurrence">
                      {entry.token.occurrence_count || 1}회
                    </span>
                    {entry.isSaved ? (
                      <span className="reading-vocab-saved-badge">
                        <CheckCircleIcon className="reading-vocab-saved-badge-icon" />
                        저장됨
                      </span>
                    ) : null}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
        </div>
      )}
    </>
  );
}

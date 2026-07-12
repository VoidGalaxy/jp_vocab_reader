"use client";

import { useMemo, useState } from "react";
import type { TokenWithStatus, VocabItem } from "./types";
import {
  computeReadingVocabEntries,
  filterReadingVocabEntries,
  getTokenGroupKey,
  searchReadingVocabEntries,
  selectReadingVocabEntriesByMode,
} from "./coverageUtils";
import type { ReadingSaveMode, ReadingVocabEntry, ReadingVocabFilter } from "./coverageUtils";
import { ChevronDownIcon, FolderIcon, SearchIcon } from "./icons";
import { statusLabels } from "./shared";

type ReadingVocabPanelProps = {
  tokens: TokenWithStatus[];
  vocabItems: VocabItem[];
  selectedDeckId: string;
  selectedTokenKey: string | null;
  onSelectToken: (tokenIndex: number) => void;
  isSaving: boolean;
  // Resolves once persistence finishes; returns the tokenIndexes that were
  // actually saved (fulfilled or already-saved) so the panel can drop just
  // those from the selection instead of clearing everything indiscriminately.
  onSaveSelected: (tokenIndexes: number[]) => Promise<number[]>;
};

const filterOptions: Array<{ value: ReadingVocabFilter; label: string }> = [
  { value: "all", label: "전체" },
  { value: "unknown", label: "모르는 단어" },
  { value: "uncertain", label: "헷갈리는 단어" },
  { value: "unclassified", label: "미분류" },
  { value: "known", label: "아는 단어" },
  { value: "saveable", label: "저장 가능" },
];

const quickSelectModes: Array<{ mode: ReadingSaveMode; label: string; hint: string }> = [
  {
    mode: "unknown_only",
    label: "모르는 단어 선택",
    hint: "unknown 상태 단어를 선택합니다",
  },
  {
    mode: "unknown_uncertain",
    label: "모르는+헷갈리는 단어 선택",
    hint: "unknown + uncertain 상태 단어를 선택합니다",
  },
  {
    mode: "all_unclassified",
    label: "미분류까지 선택",
    hint: "unknown + uncertain + 미분류 단어를 선택합니다",
  },
];

export function ReadingVocabPanel({
  tokens,
  vocabItems,
  selectedDeckId,
  selectedTokenKey,
  onSelectToken,
  isSaving,
  onSaveSelected,
}: ReadingVocabPanelProps) {
  const [filter, setFilter] = useState<ReadingVocabFilter>("all");
  const [search, setSearch] = useState("");
  const [selectedWordKeys, setSelectedWordKeys] = useState<Set<string>>(
    () => new Set(),
  );
  // Collapsed by default only matters visually on narrow screens (the
  // toggle button itself is desktop-visible too, but the panel simply
  // never gets tall enough there to need collapsing) -- keeps the "이 텍스트
  // 단어 목록" section from pushing the save CTA far down the page on long,
  // chunk-analyzed texts. Starts expanded so existing behavior is unchanged
  // until a user actually taps the toggle.
  const [isCollapsed, setIsCollapsed] = useState(false);

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

  // selectedWordKeys can outlive the entries it was built from (a
  // re-analysis swaps tokens out from under an already-mounted panel) --
  // this is the single place that reconciles the raw key Set against what's
  // actually selectable right now, so every count/action below only ever
  // sees valid, currently-saveable selections.
  const selectedEntries = useMemo(() => {
    if (selectedWordKeys.size === 0) {
      return [];
    }
    return entries.filter(
      (entry) =>
        entry.isSaveable && selectedWordKeys.has(getTokenGroupKey(entry.token)),
    );
  }, [entries, selectedWordKeys]);

  const selectedCount = selectedEntries.length;
  const selectedAlreadySavedCount = selectedEntries.filter(
    (entry) => entry.isSaved,
  ).length;

  function toggleSelect(key: string) {
    setSelectedWordKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function replaceSelection(nextEntries: ReadingVocabEntry[]) {
    setSelectedWordKeys(
      new Set(nextEntries.map((entry) => getTokenGroupKey(entry.token))),
    );
  }

  async function handleSaveSelected() {
    if (selectedCount === 0 || isSaving) {
      return;
    }
    const tokenIndexes = selectedEntries.map((entry) => entry.tokenIndex);
    const savedTokenIndexes = await onSaveSelected(tokenIndexes);
    if (savedTokenIndexes.length === 0) {
      return;
    }
    const savedKeys = new Set(
      savedTokenIndexes
        .map((index) => tokens[index])
        .filter((token): token is TokenWithStatus => Boolean(token))
        .map((token) => getTokenGroupKey(token)),
    );
    setSelectedWordKeys((current) => {
      const next = new Set(current);
      savedKeys.forEach((key) => next.delete(key));
      return next;
    });
  }

  return (
    <section className="panel-card reading-vocab-panel">
      <div className="panel-card-header reading-vocab-panel-header">
        <div>
          <h3 className="panel-card-title">이 텍스트 단어 목록</h3>
          <p className="panel-card-description">
            이 텍스트에서 나온 학습 가능 단어를 모아봤어요. 단어를 누르면 원문
            위치로 이동하고, 체크박스로 저장할 단어를 직접 골라 담을 수
            있습니다.
          </p>
        </div>
        <button
          type="button"
          className="ghost-button compact-button reading-vocab-collapse-toggle"
          onClick={() => setIsCollapsed((value) => !value)}
          aria-expanded={!isCollapsed}
        >
          <ChevronDownIcon
            className={`reading-vocab-collapse-icon${
              isCollapsed ? " reading-vocab-collapse-icon-collapsed" : ""
            }`}
          />
          {isCollapsed ? "펼치기" : "접기"}
        </button>
      </div>
      {isCollapsed ? (
        <p className="muted-text reading-vocab-collapsed-summary">
          {entries.length}개 단어
          {selectedCount > 0 ? ` · 선택한 단어 ${selectedCount}개` : ""}
        </p>
      ) : (
        <>
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

      <div className="reading-vocab-select-controls">
        <div
          className="reading-vocab-quick-select"
          role="group"
          aria-label="빠른 선택"
        >
          <button
            type="button"
            className="ghost-button compact-button"
            title="전체 텍스트에서 저장 가능한 단어를 모두 선택합니다"
            onClick={() => replaceSelection(entries.filter((e) => e.isSaveable))}
          >
            전체 선택
          </button>
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={() => setSelectedWordKeys(new Set())}
          >
            선택 해제
          </button>
          {quickSelectModes.map(({ mode, label, hint }) => (
            <button
              key={mode}
              type="button"
              className="ghost-button compact-button"
              title={hint}
              onClick={() =>
                replaceSelection(selectReadingVocabEntriesByMode(entries, mode))
              }
            >
              {label}
            </button>
          ))}
        </div>
        <p className="reading-vocab-selection-summary">
          선택한 단어 {selectedCount}개 · 저장 가능 {selectedCount}개
          {selectedAlreadySavedCount > 0
            ? ` · 이미 저장됨 ${selectedAlreadySavedCount}개`
            : ""}
          {" · "}현재 목록 {visibleEntries.length}개
        </p>
        <div className="reading-vocab-save-selected-row">
          <button
            type="button"
            className="reading-vocab-save-selected-button"
            onClick={() => void handleSaveSelected()}
            disabled={selectedCount === 0 || isSaving}
            title={
              selectedCount === 0
                ? "먼저 저장할 단어를 선택해 주세요."
                : undefined
            }
          >
            {isSaving ? (
              "저장 중..."
            ) : (
              <>
                <FolderIcon className="button-icon" />
                {`선택한 단어 저장 (${selectedCount})`}
              </>
            )}
          </button>
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
            const isChecked = selectedWordKeys.has(key);
            const label = entry.token.surface || entry.token.base_form;
            const meaning = entry.token.savedMeaningKo || entry.token.meaning_ko;
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
                    onChange={() => toggleSelect(key)}
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
        </>
      )}
    </section>
  );
}

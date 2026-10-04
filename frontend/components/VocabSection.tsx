"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { classifyMessageTone } from "./coverageUtils";
import { HighlightedExample } from "./HighlightedExample";
import { SearchIcon } from "./icons";
import { MeaningQuickEdit } from "./MeaningQuickEdit";
import {
  formatDateTime,
  formatNextReview,
  getDisplayMeaning,
  StatusSelect,
} from "./shared";
import type {
  Deck,
  CustomTerm,
  CustomTermFormData,
  QualityTag,
  StudyStats,
  TokenStatus,
  VocabFormData,
  VocabItem,
  VocabSort,
} from "./types";

// scrollIntoView's explicit `behavior: "smooth"` option bypasses the CSS
// `scroll-behavior: auto !important` the app's global prefers-reduced-motion
// rule sets (that CSS property only governs "auto" JS calls, not an
// explicitly-requested smooth one) -- so a reduced-motion user still gets an
// animated scroll unless this downgrades it first.
function resolveScrollBehavior(preferred: ScrollBehavior): ScrollBehavior {
  if (
    preferred === "smooth" &&
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ) {
    return "auto";
  }
  return preferred;
}

// Short paper labels for the status index/filter line and each row's
// status note. The full statusLabels wording stays in the row's
// StatusSelect, which is where the status is actually changed.
const statusShortLabels: Record<TokenStatus, string> = {
  known: "아는",
  uncertain: "헷갈림",
  unknown: "모름",
  unclassified: "미분류",
};

const statusFilterOptions: Array<{ value: "all" | TokenStatus; label: string }> = [
  { value: "all", label: "전체" },
  { value: "known", label: statusShortLabels.known },
  { value: "uncertain", label: statusShortLabels.uncertain },
  { value: "unknown", label: statusShortLabels.unknown },
  { value: "unclassified", label: statusShortLabels.unclassified },
];

const sortOptions: Array<{ value: VocabSort; label: string }> = [
  { value: "created_desc", label: "최근 저장순" },
  { value: "created_asc", label: "오래된 저장순" },
  { value: "wrong_desc", label: "많이 틀린순" },
  { value: "correct_desc", label: "많이 맞힌순" },
  { value: "review_level_asc", label: "복습 단계 낮은순" },
  { value: "next_review_asc", label: "다음 복습 가까운순" },
];

type VocabSectionProps = {
  items: VocabItem[];
  stats: StudyStats | null;
  isLoading: boolean;
  isExportingCsv: boolean;
  isExportingDeckPackage: boolean;
  isImportingDeckPackage: boolean;
  isPublishingDeck: boolean;
  message: string;
  decks: Deck[];
  selectedDeckId: string;
  defaultDeckId: string;
  searchText: string;
  statusFilter: "all" | TokenStatus;
  dueOnly: boolean;
  sortValue: VocabSort;
  newDeckName: string;
  newDeckDescription: string;
  isCreatingDeck: boolean;
  isAddingVocab: boolean;
  isUpdatingVocab: boolean;
  isNewVocabFormOpen: boolean;
  deckMessage: string;
  newVocabForm: VocabFormData;
  editingItemId: number | null;
  editVocabForm: VocabFormData;
  customTerms: CustomTerm[];
  newCustomTermForm: CustomTermFormData;
  editCustomTermForm: CustomTermFormData;
  isCustomTermFormOpen: boolean;
  editingCustomTermId: number | null;
  isSavingCustomTerm: boolean;
  deckPackageFileName: string;
  publishTitle: string;
  publishDescription: string;
  onSelectedDeckChange: (deckId: string) => void;
  onSearchTextChange: (text: string) => void;
  onStatusFilterChange: (status: "all" | TokenStatus) => void;
  onDueOnlyChange: (checked: boolean) => void;
  onSortChange: (sort: VocabSort) => void;
  onNewDeckNameChange: (name: string) => void;
  onNewDeckDescriptionChange: (description: string) => void;
  onCreateDeck: () => void;
  onDeleteDeck: (deckId: number) => void;
  onNewVocabFormOpenChange: (open: boolean) => void;
  onNewVocabFormChange: (field: keyof VocabFormData, value: string) => void;
  onAddVocabItem: () => void;
  onCustomTermFormOpenChange: (open: boolean) => void;
  onNewCustomTermFormChange: (
    field: keyof CustomTermFormData,
    value: string,
  ) => void;
  onAddCustomTerm: () => void;
  onEditCustomTermFormChange: (
    field: keyof CustomTermFormData,
    value: string,
  ) => void;
  onStartCustomTermEdit: (term: CustomTerm) => void;
  onSaveCustomTermEdit: () => void;
  onCancelCustomTermEdit: () => void;
  onDeleteCustomTerm: (termId: number) => void;
  onEditVocabFormChange: (field: keyof VocabFormData, value: string) => void;
  onStartEdit: (item: VocabItem) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  meaningEditItemId: number | null;
  meaningEditDraft: string;
  isSavingMeaningEdit: boolean;
  meaningEditMessage: string;
  onStartMeaningEdit: (itemId: number, currentMeaning: string) => void;
  onMeaningEditDraftChange: (value: string) => void;
  onSaveMeaningEdit: () => void;
  onCancelMeaningEdit: () => void;
  onReportMeaning: (item: VocabItem) => void;
  onRefresh: () => void;
  onDownloadCsv: () => void;
  onExportDeckPackage: () => void;
  onDeckPackageFileChange: (file: File | null) => void;
  onImportDeckPackage: () => void;
  onPublishTitleChange: (title: string) => void;
  onPublishDescriptionChange: (description: string) => void;
  onPublishDeck: () => void;
  onStudySelectedDeck: () => void;
  onStatusChange: (itemId: number, status: TokenStatus) => void;
  onDelete: (itemId: number) => void;
  onGoToReading: () => void;
  onGoToStudyToday: () => void;
  onGoToShared: () => void;
};

/* Vocab A, the file drawer (references/mockups/vocab-b-hybrid-three/
   handoff). Desktop is one shallow drawer: a narrow index on its left side
   and one wide ivory sheet holding the header, search/deck/sort, status
   line and the paired-language list. Phones get one full-height sheet with
   a binding strip instead of a shrunk drawer. Every word, count and control
   is DOM; the drawer and paper are CSS only. Selecting a word opens its
   detail inside the same row, and management opens on the same sheet in
   place of the list, so nothing renders below the scene. */
export function VocabSection({
  items,
  stats,
  isLoading,
  isExportingCsv,
  isExportingDeckPackage,
  isImportingDeckPackage,
  isPublishingDeck,
  message,
  decks,
  selectedDeckId,
  defaultDeckId,
  searchText,
  statusFilter,
  dueOnly,
  sortValue,
  newDeckName,
  newDeckDescription,
  isCreatingDeck,
  isAddingVocab,
  isUpdatingVocab,
  isNewVocabFormOpen,
  deckMessage,
  newVocabForm,
  editingItemId,
  editVocabForm,
  customTerms,
  newCustomTermForm,
  editCustomTermForm,
  isCustomTermFormOpen,
  editingCustomTermId,
  isSavingCustomTerm,
  deckPackageFileName,
  publishTitle,
  publishDescription,
  onSelectedDeckChange,
  onSearchTextChange,
  onStatusFilterChange,
  onDueOnlyChange,
  onSortChange,
  onNewDeckNameChange,
  onNewDeckDescriptionChange,
  onCreateDeck,
  onDeleteDeck,
  onNewVocabFormOpenChange,
  onNewVocabFormChange,
  onAddVocabItem,
  onCustomTermFormOpenChange,
  onNewCustomTermFormChange,
  onAddCustomTerm,
  onEditCustomTermFormChange,
  onStartCustomTermEdit,
  onSaveCustomTermEdit,
  onCancelCustomTermEdit,
  onDeleteCustomTerm,
  onEditVocabFormChange,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  meaningEditItemId,
  meaningEditDraft,
  isSavingMeaningEdit,
  meaningEditMessage,
  onStartMeaningEdit,
  onMeaningEditDraftChange,
  onSaveMeaningEdit,
  onCancelMeaningEdit,
  onReportMeaning,
  onRefresh,
  onDownloadCsv,
  onExportDeckPackage,
  onDeckPackageFileChange,
  onImportDeckPackage,
  onPublishTitleChange,
  onPublishDescriptionChange,
  onPublishDeck,
  onStudySelectedDeck,
  onStatusChange,
  onDelete,
  onGoToReading,
  onGoToStudyToday,
  onGoToShared,
}: VocabSectionProps) {
  // Management (deck, share, backup, custom terms) takes the sheet's list
  // area instead of stacking panels under the drawer.
  const [isManagementOpen, setIsManagementOpen] = useState(false);
  const [isCustomTermManagerOpen, setIsCustomTermManagerOpen] = useState(false);
  const [isBackupToolsOpen, setIsBackupToolsOpen] = useState(false);
  // One open row at a time; an item being edited always stays open.
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const customTermSectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isManagementOpen && isCustomTermManagerOpen) {
      customTermSectionRef.current?.scrollIntoView({
        behavior: resolveScrollBehavior("smooth"),
        block: "start",
      });
    }
  }, [isManagementOpen, isCustomTermManagerOpen]);

  // Opening management or the add form starts the sheet from the top.
  useEffect(() => {
    if (isManagementOpen || isNewVocabFormOpen) {
      scrollRef.current?.scrollTo({ top: 0 });
    }
  }, [isManagementOpen, isNewVocabFormOpen]);

  // A row opened near the end of the list is brought fully into view
  // inside the sheet's own scroller.
  useEffect(() => {
    if (selectedItemId === null) {
      return;
    }
    document
      .getElementById(`vocab-file-row-${selectedItemId}`)
      ?.scrollIntoView({ behavior: resolveScrollBehavior("smooth"), block: "nearest" });
  }, [selectedItemId]);

  const hasActiveFilter =
    searchText.trim() !== "" || statusFilter !== "all" || dueOnly;
  const hasDeckSelected = selectedDeckId !== "";
  const isSpecificDeck = selectedDeckId !== "all" && selectedDeckId !== "";
  const selectedDeckName = isSpecificDeck
    ? decks.find((deck) => String(deck.id) === selectedDeckId)?.name ?? "덱"
    : selectedDeckId === "all"
      ? "전체"
      : "덱 선택 전";

  // Stats are loaded for whichever deck Review last used, so per-status
  // counts are only shown when they describe the deck on this sheet.
  const statsMatchDeck =
    !!stats &&
    (selectedDeckId === "all"
      ? stats.scope === "all"
      : isSpecificDeck && stats.scope === "deck" && String(stats.deck_id) === selectedDeckId);
  function countFor(value: "all" | TokenStatus | "due"): number | null {
    if (!statsMatchDeck || !stats) {
      return null;
    }
    switch (value) {
      case "all":
        return stats.total_vocab_count;
      case "known":
        return stats.known_count;
      case "uncertain":
        return stats.uncertain_count;
      case "unknown":
        return stats.unknown_count;
      case "unclassified":
        return stats.unclassified_count;
      case "due":
        return stats.due_today_count;
    }
  }
  const sortLabel =
    sortOptions.find((option) => option.value === sortValue)?.label ?? "정렬";

  function toggleItem(itemId: number) {
    setSelectedItemId((current) => (current === itemId ? null : itemId));
  }

  function resetVocabFilters() {
    onSearchTextChange("");
    onStatusFilterChange("all");
    onDueOnlyChange(false);
  }

  function openCustomTerms() {
    setIsManagementOpen(true);
    setIsCustomTermManagerOpen(true);
  }

  const studyDisabledTitle = isSpecificDeck
    ? undefined
    : "학습할 특정 덱을 먼저 선택해 주세요.";

  const filterButtons = (
    <>
      {statusFilterOptions.map((option) => {
        const isActive = statusFilter === option.value;
        const count = countFor(option.value);
        return (
          <button
            key={option.value}
            type="button"
            className={`vocab-file-filter${isActive ? " is-active" : ""}`}
            aria-pressed={isActive}
            onClick={() => onStatusFilterChange(option.value)}
          >
            {option.label}
            {count !== null ? <b>{count}</b> : null}
          </button>
        );
      })}
      <button
        type="button"
        className={`vocab-file-filter vocab-file-filter-due${dueOnly ? " is-active" : ""}`}
        aria-pressed={dueOnly}
        onClick={() => onDueOnlyChange(!dueOnly)}
      >
        복습 예정
        {countFor("due") !== null ? <b>{countFor("due")}</b> : null}
      </button>
    </>
  );

  const sortSelect = (extraClass: string) => (
    <label className={`vocab-file-select vocab-file-sort ${extraClass}`}>
      <span className="vocab-file-sr">정렬</span>
      <select
        value={sortValue}
        onChange={(event) => onSortChange(event.target.value as VocabSort)}
      >
        {sortOptions.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );

  function renderList() {
    if (!hasDeckSelected) {
      return (
        <div className="vocab-file-note">
          {decks.length === 0 ? (
            <>
              <p className="vocab-file-note-title">아직 만든 단어장이 없어요.</p>
              <p>읽기 탭에서 원문을 읽고 단어를 담으면 단어장이 자동으로 만들어져요.</p>
              <button type="button" className="vocab-file-link" onClick={onGoToReading}>
                원문 읽기 시작
              </button>
            </>
          ) : (
            <>
              <p className="vocab-file-note-title">볼 단어장을 골라볼까요?</p>
              <p>위에서 덱을 고르면 담아둔 단어가 이 장에 적혀요.</p>
            </>
          )}
        </div>
      );
    }

    if (items.length === 0) {
      if (isLoading) {
        return <p className="vocab-file-note vocab-file-note-quiet">단어를 불러오는 중이에요.</p>;
      }
      if (dueOnly && !searchText.trim() && statusFilter === "all") {
        return (
          <div className="vocab-file-note">
            <p className="vocab-file-note-title">지금 복습할 단어가 없어요.</p>
            <p>새 원문을 읽고 단어를 더 담아보세요.</p>
            <button type="button" className="vocab-file-link" onClick={onGoToReading}>
              원문 읽기
            </button>
          </div>
        );
      }
      if (hasActiveFilter) {
        return (
          <div className="vocab-file-note">
            <p className="vocab-file-note-title">찾는 단어가 없어요.</p>
            <p>검색어를 바꾸거나 필터를 풀어보세요.</p>
            <button type="button" className="vocab-file-link" onClick={resetVocabFilters}>
              필터 초기화
            </button>
          </div>
        );
      }
      return (
        <div className="vocab-file-note">
          <p className="vocab-file-note-title">아직 담은 단어가 없어요.</p>
          <p>원문에서 모르는 단어를 눌러 이 장에 쌓아보세요.</p>
          <span className="vocab-file-note-actions">
            <button type="button" className="vocab-file-link" onClick={onGoToReading}>
              원문 읽기 시작
            </button>
            <button type="button" className="vocab-file-link" onClick={onGoToShared}>
              덱 책장 둘러보기
            </button>
          </span>
        </div>
      );
    }

    return (
      <ol className="vocab-file-list" aria-label="저장한 단어">
        {items.map((item, index) => {
          const isExpanded =
            selectedItemId === item.id || editingItemId === item.id;
          const isDue =
            !!item.next_review_at &&
            new Date(item.next_review_at).getTime() <= Date.now();
          const detailId = `vocab-file-detail-${item.id}`;
          const hasReading = !!item.reading && item.reading !== item.surface;

          return (
            <li
              key={item.id}
              id={`vocab-file-row-${item.id}`}
              className={`vocab-file-pair${isExpanded ? " is-open" : ""}`}
              data-status={item.status}
            >
              <button
                type="button"
                className="vocab-file-pair-hit"
                aria-expanded={isExpanded}
                aria-controls={isExpanded ? detailId : undefined}
                onClick={() => toggleItem(item.id)}
              >
                <span className="vocab-file-no" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="vocab-file-ja">
                  <strong lang="ja">{item.surface || item.base_form}</strong>
                  {hasReading ? <span lang="ja">{item.reading}</span> : null}
                  <QualityBadge qualityTag={item.quality_tag} />
                </span>
                <span className="vocab-file-ko">
                  <strong>{getDisplayMeaning(item.meaning_ko)}</strong>
                  <span className="vocab-file-status">
                    {statusShortLabels[item.status]}
                    {isDue ? <em> · 복습 예정</em> : null}
                  </span>
                </span>
              </button>

              {isExpanded ? (
                <VocabItemDetail
                  id={detailId}
                  item={item}
                  decks={decks}
                  editingItemId={editingItemId}
                  editVocabForm={editVocabForm}
                  isUpdatingVocab={isUpdatingVocab}
                  meaningEditItemId={meaningEditItemId}
                  meaningEditDraft={meaningEditDraft}
                  isSavingMeaningEdit={isSavingMeaningEdit}
                  meaningEditMessage={meaningEditMessage}
                  onStatusChange={onStatusChange}
                  onStartMeaningEdit={onStartMeaningEdit}
                  onMeaningEditDraftChange={onMeaningEditDraftChange}
                  onSaveMeaningEdit={onSaveMeaningEdit}
                  onCancelMeaningEdit={onCancelMeaningEdit}
                  onReportMeaning={onReportMeaning}
                  onEditVocabFormChange={onEditVocabFormChange}
                  onStartEdit={onStartEdit}
                  onSaveEdit={onSaveEdit}
                  onCancelEdit={onCancelEdit}
                  onDelete={onDelete}
                />
              ) : null}
            </li>
          );
        })}
      </ol>
    );
  }

  function renderManagement() {
    return (
      <div className="vocab-file-manage">
        <div className="vocab-file-manage-head">
          <h3>단어장 관리</h3>
          <button
            type="button"
            className="vocab-file-link"
            onClick={() => setIsManagementOpen(false)}
          >
            단어 목록으로
          </button>
        </div>

        <section className="vocab-file-manage-section" aria-label="바로 가기">
          <div className="vocab-file-manage-links">
            <button
              type="button"
              className="vocab-file-link"
              onClick={onStudySelectedDeck}
              disabled={!isSpecificDeck}
              title={studyDisabledTitle}
            >
              이 덱 학습하기
            </button>
            <button type="button" className="vocab-file-link" onClick={onGoToStudyToday}>
              오늘 복습하기
            </button>
            <button type="button" className="vocab-file-link" onClick={onGoToReading}>
              원문 읽기
            </button>
            <button type="button" className="vocab-file-link" onClick={onGoToShared}>
              덱 책장
            </button>
            <button
              type="button"
              className="vocab-file-link"
              onClick={() => onNewVocabFormOpenChange(!isNewVocabFormOpen)}
              aria-expanded={isNewVocabFormOpen}
            >
              {isNewVocabFormOpen ? "단어 추가 닫기" : "단어 직접 추가"}
            </button>
            <button
              type="button"
              className="vocab-file-link"
              onClick={onRefresh}
              disabled={isLoading || !hasDeckSelected}
            >
              {isLoading ? "불러오는 중..." : "새로고침"}
            </button>
          </div>
          <p className="vocab-file-manage-note">
            전체 {stats ? stats.total_vocab_count : items.length}개 · 복습 예정{" "}
            {stats ? stats.due_today_count : "-"}개 · 어려운 단어{" "}
            {stats ? stats.hard_count : "-"}개
          </p>
        </section>

        <section className="vocab-file-manage-section">
          <h4>덱 관리</h4>
          <p className="vocab-file-manage-note">새 덱을 만들거나 현재 선택한 덱을 삭제해요.</p>
          <div className="deck-create">
            <input
              value={newDeckName}
              onChange={(event) => onNewDeckNameChange(event.target.value)}
              placeholder="덱 이름"
              aria-label="새 덱 이름"
            />
            <input
              value={newDeckDescription}
              onChange={(event) => onNewDeckDescriptionChange(event.target.value)}
              placeholder="설명"
              aria-label="새 덱 설명"
            />
            <button
              type="button"
              className="vocab-file-ink-button"
              onClick={onCreateDeck}
              disabled={isCreatingDeck}
            >
              {isCreatingDeck ? "만드는 중..." : "덱 만들기"}
            </button>
          </div>
          {deckMessage ? (
            <p className={`vocab-file-message is-${classifyMessageTone(deckMessage)}`} role="status">
              {deckMessage}
            </p>
          ) : null}
          <div className="vocab-file-danger">
            <span className="vocab-file-danger-label">위험 구역</span>
            {isSpecificDeck ? (
              <button
                type="button"
                className="vocab-file-link vocab-file-link-danger"
                onClick={() => onDeleteDeck(Number(selectedDeckId))}
                disabled={selectedDeckId === defaultDeckId}
                title={
                  selectedDeckId === defaultDeckId
                    ? "기본 단어장은 삭제할 수 없어요."
                    : undefined
                }
              >
                현재 덱 삭제
              </button>
            ) : (
              <span className="vocab-file-manage-note">삭제하려면 특정 덱을 선택하세요.</span>
            )}
          </div>
        </section>

        <section className="vocab-file-manage-section">
          <h4>덱 공유</h4>
          <p className="vocab-file-manage-note">
            등록하면 다른 사용자가 공유 탭에서 이 덱을 보고 자기 단어장으로 가져올 수 있어요. 학습 기록은 공유되지 않아요.
          </p>
          <div className="publish-deck-form">
            <label className="inline-field">
              공유 제목
              <input
                value={publishTitle}
                onChange={(event) => onPublishTitleChange(event.target.value)}
                placeholder="비워두면 현재 덱 이름 사용"
              />
            </label>
            <label className="inline-field wide-field">
              공유 설명
              <textarea
                className="compact-textarea"
                value={publishDescription}
                onChange={(event) => onPublishDescriptionChange(event.target.value)}
                placeholder="덱에 포함된 작품 범위나 학습 목적"
              />
            </label>
            <button
              type="button"
              className="vocab-file-ink-button"
              onClick={onPublishDeck}
              disabled={!isSpecificDeck || isPublishingDeck}
              title={isSpecificDeck ? undefined : "공유할 특정 덱을 먼저 선택해 주세요."}
            >
              {isPublishingDeck ? "등록 중..." : "현재 덱을 공유 덱으로 등록"}
            </button>
          </div>
          <button
            type="button"
            className="vocab-file-link"
            onClick={() => setIsBackupToolsOpen((open) => !open)}
            aria-expanded={isBackupToolsOpen}
          >
            고급 백업/파일 내보내기
          </button>
          {isBackupToolsOpen ? (
            <div className="vocab-file-backup">
              <p className="vocab-file-manage-note">
                CSV는 엑셀 확인용이에요. 일반적인 덱 공유는 공유 탭을 사용하고, CSV/JSON 파일은 백업이나 수동 이동이 필요할 때만 사용하세요.
              </p>
              <div className="vocab-file-backup-actions">
                <button
                  type="button"
                  className="vocab-file-link"
                  onClick={onExportDeckPackage}
                  disabled={!isSpecificDeck || isExportingDeckPackage}
                  title={isSpecificDeck ? undefined : "내보낼 특정 덱을 먼저 선택해 주세요."}
                >
                  {isExportingDeckPackage ? "내보내는 중..." : "현재 덱 공유 파일로 내보내기"}
                </button>
                <button
                  type="button"
                  className="vocab-file-link"
                  onClick={onDownloadCsv}
                  disabled={isExportingCsv}
                >
                  {isExportingCsv ? "다운로드 중..." : "CSV 다운로드"}
                </button>
              </div>
              <label className="inline-field">
                덱 공유 JSON
                <input
                  type="file"
                  accept="application/json,.json"
                  onChange={(event) =>
                    onDeckPackageFileChange(event.target.files?.[0] ?? null)
                  }
                />
              </label>
              {deckPackageFileName ? (
                <span className="vocab-file-manage-note">{deckPackageFileName}</span>
              ) : null}
              <button
                type="button"
                className="vocab-file-ink-button"
                onClick={onImportDeckPackage}
                disabled={!deckPackageFileName || isImportingDeckPackage}
                title={
                  deckPackageFileName
                    ? undefined
                    : "가져올 덱 공유 JSON 파일을 먼저 선택해 주세요."
                }
              >
                {isImportingDeckPackage ? "가져오는 중..." : "덱 가져오기"}
              </button>
            </div>
          ) : null}
        </section>

        <section className="vocab-file-manage-section" ref={customTermSectionRef}>
          <h4>사용자 정의 용어</h4>
          <p className="vocab-file-manage-note">
            작품 고유명사나 자주 나오는 용어를 등록하면 분석 결과에 먼저 반영돼요.
          </p>
          <button
            type="button"
            className="vocab-file-link"
            onClick={() => setIsCustomTermManagerOpen((open) => !open)}
            aria-expanded={isCustomTermManagerOpen}
          >
            {isCustomTermManagerOpen
              ? "사용자 정의 용어 접기"
              : `사용자 정의 용어 관리 (${customTerms.length}개)`}
          </button>
          {isCustomTermManagerOpen ? renderCustomTerms() : null}
        </section>
      </div>
    );
  }

  function renderCustomTerms() {
    return (
      <div className="vocab-file-terms">
        {!isCustomTermFormOpen ? (
          <button
            type="button"
            className="vocab-file-link"
            onClick={() => onCustomTermFormOpenChange(true)}
          >
            + 사용자 정의 용어 추가
          </button>
        ) : (
          <div className="vocab-file-form">
            <CustomTermForm
              form={newCustomTermForm}
              decks={decks}
              onChange={onNewCustomTermFormChange}
            />
            <div className="form-actions">
              <button
                type="button"
                className="vocab-file-ink-button"
                onClick={onAddCustomTerm}
                disabled={isSavingCustomTerm}
              >
                {isSavingCustomTerm ? "추가 중..." : "추가"}
              </button>
              <button
                type="button"
                className="vocab-file-link"
                onClick={() => onCustomTermFormOpenChange(false)}
                disabled={isSavingCustomTerm}
              >
                취소
              </button>
            </div>
          </div>
        )}

        {customTerms.length > 0 ? (
          <ul className="vocab-file-term-list">
            {customTerms.map((term) => (
              <Fragment key={term.id}>
                <li className="vocab-file-term">
                  <span className="vocab-file-term-word">
                    <strong lang="ja">{term.term}</strong>
                    {term.reading ? <span lang="ja">{term.reading}</span> : null}
                  </span>
                  <span className="vocab-file-term-meaning">
                    {getDisplayMeaning(term.meaning_ko)}
                    <small>
                      {[term.part_of_speech, term.deck_name || "공통"]
                        .filter(Boolean)
                        .join(" · ")}
                    </small>
                    {term.description ? <small>{term.description}</small> : null}
                  </span>
                  <span className="vocab-file-term-actions">
                    <button
                      type="button"
                      className="vocab-file-link"
                      onClick={() => onStartCustomTermEdit(term)}
                    >
                      수정
                    </button>
                    <button
                      type="button"
                      className="vocab-file-link vocab-file-link-danger"
                      onClick={() => {
                        if (window.confirm(`"${term.term}" 용어를 삭제할까요?`)) {
                          onDeleteCustomTerm(term.id);
                        }
                      }}
                    >
                      삭제
                    </button>
                  </span>
                </li>
                {editingCustomTermId === term.id ? (
                  <li className="vocab-file-form">
                    <CustomTermForm
                      form={editCustomTermForm}
                      decks={decks}
                      onChange={onEditCustomTermFormChange}
                    />
                    <div className="form-actions">
                      <button
                        type="button"
                        className="vocab-file-ink-button"
                        onClick={onSaveCustomTermEdit}
                        disabled={isSavingCustomTerm}
                      >
                        {isSavingCustomTerm ? "저장 중..." : "저장"}
                      </button>
                      <button
                        type="button"
                        className="vocab-file-link"
                        onClick={onCancelCustomTermEdit}
                        disabled={isSavingCustomTerm}
                      >
                        취소
                      </button>
                    </div>
                  </li>
                ) : null}
              </Fragment>
            ))}
          </ul>
        ) : (
          <p className="vocab-file-manage-note">
            {selectedDeckId === ""
              ? "덱을 선택하면 그 덱에 등록한 사용자 정의 용어를 볼 수 있어요."
              : "등록된 사용자 정의 용어가 없어요."}
          </p>
        )}
      </div>
    );
  }

  const indexTotal = countFor("all");

  return (
    <section className="tab-panel vocab-file">
      <div className="vocab-file-stage">
        <div className="vocab-file-tray">
          <aside className="vocab-file-index" aria-label="단어장 색인">
            <span className="vocab-file-mark" lang="ja">
              ことば
            </span>
            <div className="vocab-file-index-list" role="group" aria-label="상태 색인">
              {statusFilterOptions.map((option) => {
                const isActive = statusFilter === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    className={`vocab-file-index-tab${isActive ? " is-active" : ""}`}
                    aria-pressed={isActive}
                    onClick={() => onStatusFilterChange(option.value)}
                  >
                    {option.label}
                  </button>
                );
              })}
              <button
                type="button"
                className={`vocab-file-index-tab${dueOnly ? " is-active" : ""}`}
                aria-pressed={dueOnly}
                onClick={() => onDueOnlyChange(!dueOnly)}
              >
                복습 예정
              </button>
            </div>
            <span className="vocab-file-index-foot">
              {indexTotal !== null ? `단어 ${indexTotal} · ` : ""}덱 {decks.length}
            </span>
          </aside>

          <div className="vocab-file-back" aria-hidden="true" />

          <div className="vocab-file-sheet">
            <span className="vocab-file-tab" aria-hidden="true">
              내 단어장 · {selectedDeckName}
            </span>

            <header className="vocab-file-head">
              <div>
                <span className="vocab-file-smallcap">
                  MY VOCABULARY<span className="vocab-file-desk-only"> / 日本語</span>
                </span>
                <h2>
                  <span className="vocab-file-desk-only">일본어와 한국어</span>
                  <span className="vocab-file-phone-only">내 단어장</span>
                </h2>
              </div>
              <span className="vocab-file-count" aria-live="polite">
                {hasDeckSelected && !(isLoading && items.length === 0) ? items.length : "–"}
                <small>단어</small>
              </span>
            </header>

            <div className="vocab-file-tools">
              <label className="vocab-file-search">
                <SearchIcon className="vocab-file-search-icon" />
                <input
                  value={searchText}
                  onChange={(event) => onSearchTextChange(event.target.value)}
                  placeholder="단어, 읽기, 뜻 검색"
                  aria-label="단어장 검색"
                />
              </label>
              <label className="vocab-file-select vocab-file-deck">
                <span className="vocab-file-sr">덱</span>
                <select
                  value={selectedDeckId}
                  onChange={(event) => onSelectedDeckChange(event.target.value)}
                >
                  <option value="" disabled hidden>
                    덱 선택
                  </option>
                  <option value="all">전체 단어장</option>
                  {decks.map((deck) => (
                    <option key={deck.id} value={String(deck.id)}>
                      {deck.name}
                    </option>
                  ))}
                </select>
              </label>
              {sortSelect("vocab-file-desk-only")}
              <button
                type="button"
                className="vocab-file-link vocab-file-desk-only"
                onClick={() => onNewVocabFormOpenChange(!isNewVocabFormOpen)}
                aria-expanded={isNewVocabFormOpen}
              >
                {isNewVocabFormOpen ? "추가 닫기" : "단어 추가"}
              </button>
            </div>

            <div className="vocab-file-filters" role="group" aria-label="단어 상태">
              {filterButtons}
            </div>

            {message ? (
              <p
                className={`vocab-file-message is-${classifyMessageTone(message)}`}
                role="status"
              >
                {message}
              </p>
            ) : null}

            {!isManagementOpen ? (
              <div className="vocab-file-columns">
                <span>
                  <span className="vocab-file-desk-only">일본어 · 읽기</span>
                  <span className="vocab-file-phone-only">일본어</span>
                </span>
                <span>
                  <span className="vocab-file-desk-only">뜻 · 기억</span>
                  <span className="vocab-file-phone-only">한국어</span>
                </span>
                {sortSelect("vocab-file-phone-only")}
              </div>
            ) : null}

            <div className="vocab-file-scroll" ref={scrollRef}>
              {isNewVocabFormOpen ? (
                <div className="vocab-file-form vocab-file-add">
                  <h3>단어 직접 추가</h3>
                  <VocabItemForm
                    form={newVocabForm}
                    decks={decks}
                    onChange={onNewVocabFormChange}
                  />
                  <div className="form-actions">
                    <button
                      type="button"
                      className="vocab-file-ink-button"
                      onClick={onAddVocabItem}
                      disabled={isAddingVocab}
                    >
                      {isAddingVocab ? "추가 중..." : "추가"}
                    </button>
                    <button
                      type="button"
                      className="vocab-file-link"
                      onClick={() => onNewVocabFormOpenChange(false)}
                      disabled={isAddingVocab}
                    >
                      취소
                    </button>
                  </div>
                </div>
              ) : null}
              {isManagementOpen ? renderManagement() : renderList()}
            </div>

            <footer className="vocab-file-foot">
              <span className="vocab-file-foot-note">
                {hasDeckSelected ? (
                  <>
                    <span className="vocab-file-desk-only">{sortLabel} · </span>
                    {items.length}개
                  </>
                ) : (
                  "덱을 골라 주세요"
                )}
              </span>
              <span className="vocab-file-foot-actions">
                <button
                  type="button"
                  className="vocab-file-link"
                  onClick={onStudySelectedDeck}
                  disabled={!isSpecificDeck}
                  title={studyDisabledTitle}
                >
                  이 덱 학습하기
                </button>
                <button
                  type="button"
                  className="vocab-file-link vocab-file-desk-only"
                  onClick={onGoToReading}
                >
                  원문 읽기
                </button>
                <button
                  type="button"
                  className="vocab-file-link"
                  onClick={() => setIsManagementOpen((open) => !open)}
                  aria-expanded={isManagementOpen}
                >
                  {isManagementOpen ? "단어 목록" : "단어장 관리"}
                </button>
              </span>
            </footer>
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// VocabItemDetail -- the open row's body: saved example first, then status,
// review record, and the meaning-edit/report/edit/delete actions with the
// inline edit form. Rendered once, inside the selected row.
// ---------------------------------------------------------------------------
type VocabItemDetailProps = {
  id: string;
  item: VocabItem;
  decks: Deck[];
  editingItemId: number | null;
  editVocabForm: VocabFormData;
  isUpdatingVocab: boolean;
  meaningEditItemId: number | null;
  meaningEditDraft: string;
  isSavingMeaningEdit: boolean;
  meaningEditMessage: string;
  onStatusChange: (itemId: number, status: TokenStatus) => void;
  onStartMeaningEdit: (itemId: number, currentMeaning: string) => void;
  onMeaningEditDraftChange: (value: string) => void;
  onSaveMeaningEdit: () => void;
  onCancelMeaningEdit: () => void;
  onReportMeaning: (item: VocabItem) => void;
  onEditVocabFormChange: (field: keyof VocabFormData, value: string) => void;
  onStartEdit: (item: VocabItem) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onDelete: (itemId: number) => void;
};

function VocabItemDetail({
  id,
  item,
  decks,
  editingItemId,
  editVocabForm,
  isUpdatingVocab,
  meaningEditItemId,
  meaningEditDraft,
  isSavingMeaningEdit,
  meaningEditMessage,
  onStatusChange,
  onStartMeaningEdit,
  onMeaningEditDraftChange,
  onSaveMeaningEdit,
  onCancelMeaningEdit,
  onReportMeaning,
  onEditVocabFormChange,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onDelete,
}: VocabItemDetailProps) {
  const metaParts = [
    item.base_form && item.base_form !== item.surface ? `기본형 ${item.base_form}` : "",
    item.part_of_speech,
    item.deck_name,
    `복습 레벨 ${item.review_level}`,
    `맞음 ${item.correct_count} · 다시 ${item.wrong_count}`,
    formatNextReview(item.next_review_at),
    item.last_reviewed_at ? `마지막 복습 ${formatDateTime(item.last_reviewed_at)}` : "",
  ].filter(Boolean);

  return (
    <div className="vocab-file-detail" id={id}>
      {item.example_sentence ? (
        <p className="vocab-file-example" lang="ja">
          <HighlightedExample
            sentence={item.example_sentence}
            surface={item.surface}
            baseForm={item.base_form}
            normalizedForm={item.normalized_form}
          />
        </p>
      ) : (
        <p className="vocab-file-example-empty">저장된 예문이 없어요.</p>
      )}

      <p className="vocab-file-meta">{metaParts.join(" · ")}</p>

      <div className="vocab-file-actions">
        <label className="vocab-file-select vocab-file-status-select">
          <span className="vocab-file-sr">기억 상태</span>
          <StatusSelect
            value={item.status}
            label={`${item.surface} 저장 상태`}
            onChange={(status) => onStatusChange(item.id, status)}
          />
        </label>
        <MeaningQuickEdit
          isEditing={meaningEditItemId === item.id}
          draftValue={meaningEditDraft}
          isSaving={isSavingMeaningEdit}
          message={meaningEditItemId === item.id ? meaningEditMessage : ""}
          onStartEdit={() => onStartMeaningEdit(item.id, item.meaning_ko)}
          onDraftChange={onMeaningEditDraftChange}
          onSave={onSaveMeaningEdit}
          onCancel={onCancelMeaningEdit}
          triggerLabel="뜻 고치기"
          triggerClassName="vocab-file-link"
        />
        <button
          type="button"
          className="vocab-file-link"
          onClick={() => onReportMeaning(item)}
        >
          뜻 오류 신고
        </button>
        <button
          type="button"
          className="vocab-file-link"
          onClick={() => onStartEdit(item)}
        >
          수정
        </button>
        <button
          type="button"
          className="vocab-file-link vocab-file-link-danger"
          onClick={() => {
            const label = item.surface || item.base_form;
            if (
              window.confirm(
                `"${label}" 단어를 삭제할까요? 저장된 학습 기록도 함께 삭제돼요.`,
              )
            ) {
              onDelete(item.id);
            }
          }}
        >
          삭제
        </button>
      </div>

      {editingItemId === item.id ? (
        <div className="vocab-file-form">
          <h3>단어 수정</h3>
          <VocabItemForm
            form={editVocabForm}
            decks={decks}
            onChange={onEditVocabFormChange}
          />
          <div className="form-actions">
            <button
              type="button"
              className="vocab-file-ink-button"
              onClick={onSaveEdit}
              disabled={isUpdatingVocab}
            >
              {isUpdatingVocab ? "저장 중..." : "저장"}
            </button>
            <button
              type="button"
              className="vocab-file-link"
              onClick={onCancelEdit}
              disabled={isUpdatingVocab}
            >
              취소
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

const qualityTagLabels: Record<Exclude<QualityTag, "normal">, string> = {
  custom_term: "사용자 용어",
  compound_verb: "복합동사",
  noun_phrase_candidate: "명사구 후보",
  known_phrase: "관용구",
};

function QualityBadge({ qualityTag }: { qualityTag: QualityTag }) {
  if (qualityTag === "normal") {
    return null;
  }

  return <span className="term-badge">{qualityTagLabels[qualityTag]}</span>;
}

type VocabItemFormProps = {
  form: VocabFormData;
  decks: Deck[];
  onChange: (field: keyof VocabFormData, value: string) => void;
};

function VocabItemForm({
  form,
  decks,
  onChange,
}: VocabItemFormProps) {
  return (
    <div className="vocab-item-form">
      <label className="inline-field">
        단어
        <input
          value={form.surface}
          onChange={(event) => onChange("surface", event.target.value)}
        />
      </label>
      <label className="inline-field">
        기본형
        <input
          value={form.base_form}
          onChange={(event) => onChange("base_form", event.target.value)}
        />
      </label>
      <label className="inline-field">
        읽기
        <input
          value={form.reading}
          onChange={(event) => onChange("reading", event.target.value)}
        />
      </label>
      <label className="inline-field">
        품사
        <input
          value={form.part_of_speech}
          onChange={(event) => onChange("part_of_speech", event.target.value)}
        />
      </label>
      <label className="inline-field">
        한국어 뜻
        <input
          value={form.meaning_ko}
          onChange={(event) => onChange("meaning_ko", event.target.value)}
        />
      </label>
      <label className="inline-field wide-field">
        영어 gloss 참고
        <input
          value={form.dictionary_gloss}
          placeholder="선택 입력"
          onChange={(event) => onChange("dictionary_gloss", event.target.value)}
        />
      </label>
      <label className="inline-field">
        상태
        <select
          value={form.status}
          onChange={(event) => onChange("status", event.target.value)}
        >
          <option value="unknown">모르는 단어</option>
          <option value="uncertain">헷갈리는 단어</option>
          <option value="known">완벽히 아는 단어</option>
          <option value="unclassified">분류되지 않음</option>
        </select>
      </label>
      <label className="inline-field">
        덱
        <select
          value={form.deck_id}
          onChange={(event) => onChange("deck_id", event.target.value)}
        >
          {decks.map((deck) => (
            <option key={deck.id} value={String(deck.id)}>
              {deck.name}
            </option>
          ))}
        </select>
      </label>
      <label className="inline-field wide-field">
        예문
        <textarea
          className="compact-textarea"
          value={form.example_sentence}
          onChange={(event) => onChange("example_sentence", event.target.value)}
        />
      </label>
    </div>
  );
}

type CustomTermFormProps = {
  form: CustomTermFormData;
  decks: Deck[];
  onChange: (field: keyof CustomTermFormData, value: string) => void;
};

function CustomTermForm({ form, decks, onChange }: CustomTermFormProps) {
  return (
    <div className="vocab-item-form">
      <label className="inline-field">
        용어
        <input
          value={form.term}
          onChange={(event) => onChange("term", event.target.value)}
        />
      </label>
      <label className="inline-field">
        읽기
        <input
          value={form.reading}
          onChange={(event) => onChange("reading", event.target.value)}
        />
      </label>
      <label className="inline-field">
        품사
        <input
          value={form.part_of_speech}
          onChange={(event) => onChange("part_of_speech", event.target.value)}
        />
      </label>
      <label className="inline-field">
        한국어 뜻
        <input
          value={form.meaning_ko}
          onChange={(event) => onChange("meaning_ko", event.target.value)}
        />
      </label>
      <label className="inline-field">
        덱
        <select
          value={form.deck_id}
          onChange={(event) => onChange("deck_id", event.target.value)}
        >
          <option value="">공통</option>
          {decks.map((deck) => (
            <option key={deck.id} value={String(deck.id)}>
              {deck.name}
            </option>
          ))}
        </select>
      </label>
      <label className="inline-field wide-field">
        설명
        <textarea
          className="compact-textarea"
          value={form.description}
          onChange={(event) => onChange("description", event.target.value)}
        />
      </label>
    </div>
  );
}

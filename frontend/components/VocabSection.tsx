"use client";

import { Fragment, useState } from "react";
import { AppEmptyState, BrandSectionBadge } from "./BrandElements";
import { classifyMessageTone } from "./coverageUtils";
import { HighlightedExample } from "./HighlightedExample";
import {
  BookIcon,
  BookshelfIcon,
  CardFileIcon,
  CardsIcon,
  ChevronDownIcon,
  ClockIcon,
  SearchIcon,
} from "./icons";
import { MeaningQuickEdit } from "./MeaningQuickEdit";
import {
  formatDateTime,
  formatNextReview,
  getDisplayMeaning,
  statusLabels,
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

const statusFilterOptions: Array<{ value: "all" | TokenStatus; label: string }> = [
  { value: "all", label: "전체" },
  { value: "unknown", label: statusLabels.unknown },
  { value: "uncertain", label: statusLabels.uncertain },
  { value: "known", label: statusLabels.known },
  { value: "unclassified", label: statusLabels.unclassified },
];

// Ties each status filter chip to the same warm color language as the
// reading tab / study cards once active -- "전체" stays neutral since it
// isn't a single status.
const statusFilterColorClass: Partial<Record<"all" | TokenStatus, string>> = {
  known: "vocab-filter-known",
  uncertain: "vocab-filter-uncertain",
  unknown: "vocab-filter-unknown",
  unclassified: "vocab-filter-unclassified",
};

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
  const [isManagementOpen, setIsManagementOpen] = useState(false);
  const [isCustomTermManagerOpen, setIsCustomTermManagerOpen] = useState(false);
  const hasActiveFilter =
    searchText.trim() !== "" || statusFilter !== "all" || dueOnly;
  const [isBackupToolsOpen, setIsBackupToolsOpen] = useState(false);
  // Compact list rows stay collapsed by default (구현3/4) -- example_sentence,
  // 품사/base_form, 복습 상세, 수정/삭제 all move behind a per-row toggle
  // instead of always showing on every card.
  const [expandedItemIds, setExpandedItemIds] = useState<Set<number>>(
    () => new Set(),
  );

  function toggleItemExpanded(itemId: number) {
    setExpandedItemIds((current) => {
      const next = new Set(current);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  }

  function resetVocabFilters() {
    onSearchTextChange("");
    onStatusFilterChange("all");
    onDueOnlyChange(false);
  }

  const selectedDeckLabel =
    selectedDeckId === "all"
      ? "전체 단어장"
      : decks.find((deck) => String(deck.id) === selectedDeckId)?.name ?? "전체 단어장";

  return (
    <section className="tab-panel vocab-panel" aria-live="polite">
      <section className="panel-card hero-card vocab-hero-card vocab-hero-compact">
        <div className="panel-card-header">
          <h2 className="panel-card-title">내 단어 노트</h2>
          <p className="panel-card-description">
            읽으며 담은 단어를 모아두고 다시 복습해요.
          </p>
        </div>
        <div className="vocab-hero-chip-row">
          <span className="memo-label vocab-hero-deck-label">{selectedDeckLabel}</span>
          <span className="vocab-hero-chip">
            전체 {stats ? stats.total_vocab_count : items.length}개
          </span>
          <span className="vocab-hero-chip vocab-hero-chip-accent">
            복습 예정 {stats ? stats.due_today_count : "-"}개
          </span>
          <span className="vocab-hero-chip">
            어려운 단어 {stats ? stats.hard_count : "-"}개
          </span>
        </div>
        <div className="landing-hero-actions vocab-hero-actions-compact">
          <button
            type="button"
            onClick={onStudySelectedDeck}
            disabled={selectedDeckId === "all"}
            title={
              selectedDeckId === "all"
                ? "학습할 특정 덱을 먼저 선택해 주세요."
                : undefined
            }
          >
            <CardsIcon className="button-icon" />이 덱 학습하기
          </button>
          <button type="button" className="secondary-button" onClick={onGoToReading}>
            <BookIcon className="button-icon" />
            원문 읽기
          </button>
        </div>
        <div className="vocab-hero-links">
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={onGoToStudyToday}
          >
            <CardsIcon className="button-icon" />
            오늘 복습하기
          </button>
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={onGoToShared}
          >
            <BookshelfIcon className="button-icon" />
            덱 책장
          </button>
        </div>
      </section>

      <div className="index-card-filter">
        <span className="memo-label vocab-toolbar-label">
          <SearchIcon className="vocab-toolbar-label-icon" />
          카드함 필터
        </span>
        <div className="vocab-filter-group">
          <label className="inline-field">
            덱
            <select value={selectedDeckId} onChange={(event) => onSelectedDeckChange(event.target.value)}>
              <option value="all">전체 단어장</option>
              {decks.map((deck) => (
                <option key={deck.id} value={String(deck.id)}>
                  {deck.name}
                </option>
              ))}
            </select>
          </label>
          <div className="vocab-search-wrap">
            <SearchIcon className="vocab-search-icon" />
            <input
              className="vocab-search-input"
              value={searchText}
              onChange={(event) => onSearchTextChange(event.target.value)}
              placeholder="단어, 읽기, 뜻으로 검색"
              aria-label="단어장 검색"
            />
          </div>
          <label className="inline-field">
            정렬
            <select
              value={sortValue}
              onChange={(event) => onSortChange(event.target.value as VocabSort)}
            >
              <option value="created_desc">최근 저장순</option>
              <option value="created_asc">오래된 저장순</option>
              <option value="wrong_desc">많이 틀린순</option>
              <option value="correct_desc">많이 맞힌순</option>
              <option value="review_level_asc">복습 단계 낮은순</option>
              <option value="next_review_asc">다음 복습 가까운순</option>
            </select>
          </label>
        </div>

        <div className="vocab-status-filters" role="group" aria-label="상태 필터">
          {statusFilterOptions.map((option) => {
            const isActive = statusFilter === option.value;
            const colorClass = statusFilterColorClass[option.value];
            return (
              <button
                key={option.value}
                type="button"
                className={`vocab-filter-chip${isActive ? " vocab-filter-chip-active" : ""}${
                  isActive && colorClass ? ` ${colorClass}` : ""
                }`}
                aria-pressed={isActive}
                onClick={() => onStatusFilterChange(option.value)}
              >
                {option.label}
              </button>
            );
          })}
          <button
            type="button"
            className={`vocab-filter-chip${dueOnly ? " vocab-filter-chip-active" : ""}`}
            aria-pressed={dueOnly}
            onClick={() => onDueOnlyChange(!dueOnly)}
          >
            복습 예정만
          </button>
        </div>

        <div className="vocab-action-group">
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={() => onNewVocabFormOpenChange(!isNewVocabFormOpen)}
          >
            {isNewVocabFormOpen ? "단어 추가 닫기" : "+ 단어 직접 추가"}
          </button>
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={() => setIsManagementOpen((open) => !open)}
            aria-expanded={isManagementOpen}
          >
            덱/공유 관리
          </button>
        </div>
      </div>

      {isManagementOpen ? (
        <div className="vocab-management-panel">
          <section className="management-card">
            <div className="management-card-header">
              <h2>덱 관리</h2>
              <p className="muted-text">새 덱을 만들거나 현재 선택한 덱을 삭제합니다.</p>
            </div>

      <div className="management-actions">
        {selectedDeckId !== "all" ? (
          <button
            type="button"
            className="danger-button"
            onClick={() => onDeleteDeck(Number(selectedDeckId))}
            disabled={selectedDeckId === defaultDeckId}
            title={
              selectedDeckId === defaultDeckId
                ? "기본 단어장은 삭제할 수 없습니다."
                : undefined
            }
          >
            현재 덱 삭제
          </button>
        ) : (
          <span className="muted-text">삭제하려면 특정 덱을 선택하세요.</span>
        )}
      </div>

      <div className="deck-create">
        <input
          value={newDeckName}
          onChange={(event) => onNewDeckNameChange(event.target.value)}
          placeholder="덱 이름"
        />
        <input
          value={newDeckDescription}
          onChange={(event) => onNewDeckDescriptionChange(event.target.value)}
          placeholder="설명"
        />
        <button type="button" onClick={onCreateDeck} disabled={isCreatingDeck}>
          {isCreatingDeck ? "만드는 중..." : "덱 만들기"}
        </button>
      </div>

      {deckMessage ? (
        <p className={`message message--${classifyMessageTone(deckMessage)}`}>
          {deckMessage}
        </p>
      ) : null}

          </section>
          <section className="management-card">
            <div className="management-card-header">
              <h2>덱 공유</h2>
              <p className="muted-text">
                CSV는 엑셀 확인용입니다. 앱 간 공유는 덱 공유 파일을 사용하세요.
              </p>
            </div>

      <div className="deck-share-panel">
        <p className="muted-text">
          등록하면 다른 사용자가 공유 탭에서 이 덱을 보고 자기 단어장으로 가져올 수 있습니다. 학습 기록은 공유되지 않습니다.
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
              onChange={(event) =>
                onPublishDescriptionChange(event.target.value)
              }
              placeholder="덱에 포함된 작품 범위나 학습 목적"
            />
          </label>
          <button
            type="button"
            onClick={onPublishDeck}
            disabled={selectedDeckId === "all" || isPublishingDeck}
            title={
              selectedDeckId === "all"
                ? "공유할 특정 덱을 먼저 선택해 주세요."
                : undefined
            }
          >
            {isPublishingDeck ? "등록 중..." : "현재 덱을 공유 덱으로 등록"}
          </button>
        </div>
        <div className="advanced-backup-panel">
          <button
            type="button"
            className="secondary-button"
            onClick={() => setIsBackupToolsOpen((open) => !open)}
            aria-expanded={isBackupToolsOpen}
          >
            고급 백업/파일 내보내기
          </button>
          {isBackupToolsOpen ? (
            <div className="backup-tools">
              <p className="muted-text">
                일반적인 덱 공유는 공유 탭을 사용하세요. CSV/JSON 파일은 백업이나 수동 이동이 필요할 때만 사용하는 고급 기능입니다.
              </p>
        <div className="deck-share-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={onExportDeckPackage}
            disabled={selectedDeckId === "all" || isExportingDeckPackage}
            title={
              selectedDeckId === "all"
                ? "내보낼 특정 덱을 먼저 선택해 주세요."
                : undefined
            }
          >
            {isExportingDeckPackage
              ? "내보내는 중..."
              : "현재 덱 공유 파일로 내보내기"}
          </button>
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
            <span className="muted-text">{deckPackageFileName}</span>
          ) : null}
          <button
            type="button"
            onClick={onImportDeckPackage}
            disabled={!deckPackageFileName || isImportingDeckPackage}
            title={
              !deckPackageFileName
                ? "가져올 덱 공유 JSON 파일을 먼저 선택해 주세요."
                : undefined
            }
          >
            {isImportingDeckPackage ? "가져오는 중..." : "덱 가져오기"}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={onDownloadCsv}
            disabled={isExportingCsv}
          >
            {isExportingCsv ? "다운로드 중..." : "CSV 다운로드"}
          </button>
        </div>
            </div>
          ) : null}
        </div>
      </div>

          </section>
          <section className="management-card">
            <div className="management-card-header">
              <h2>고급</h2>
              <p className="muted-text">작품별 사용자 용어와 보조 관리 기능입니다.</p>
            </div>
            <div className="management-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setIsCustomTermManagerOpen((open) => !open)}
                aria-expanded={isCustomTermManagerOpen}
              >
                사용자 정의 용어 관리
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {!isNewVocabFormOpen ? (
        null
      ) : (
        <div className="vocab-form-panel">
          <div className="form-heading">
            <h2>단어 직접 추가</h2>
          </div>
          <VocabItemForm
            form={newVocabForm}
            decks={decks}
            onChange={onNewVocabFormChange}
          />
          <div className="form-actions">
            <button type="button" onClick={onAddVocabItem} disabled={isAddingVocab}>
              {isAddingVocab ? "추가 중..." : "추가"}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => onNewVocabFormOpenChange(false)}
              disabled={isAddingVocab}
            >
              취소
            </button>
          </div>
        </div>
      )}

      {isManagementOpen && isCustomTermManagerOpen ? (
      <div className="custom-term-section">
        <div className="result-heading compact-heading">
          <div>
            <h2>사용자 정의 용어</h2>
            <span>{customTerms.length}개</span>
          </div>
          {!isCustomTermFormOpen ? (
            <button
              type="button"
              className="secondary-button"
              onClick={() => onCustomTermFormOpenChange(true)}
            >
              + 사용자 정의 용어 추가
            </button>
          ) : null}
        </div>

        {isCustomTermFormOpen ? (
          <div className="vocab-form-panel">
            <CustomTermForm
              form={newCustomTermForm}
              decks={decks}
              onChange={onNewCustomTermFormChange}
            />
            <div className="form-actions">
              <button
                type="button"
                onClick={onAddCustomTerm}
                disabled={isSavingCustomTerm}
              >
                {isSavingCustomTerm ? "추가 중..." : "추가"}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => onCustomTermFormOpenChange(false)}
                disabled={isSavingCustomTerm}
              >
                취소
              </button>
            </div>
          </div>
        ) : null}

        {customTerms.length > 0 ? (
          <div className="table-wrap custom-term-table">
            <table>
              <thead>
                <tr>
                  <th>용어</th>
                  <th>읽기</th>
                  <th>품사</th>
                  <th>뜻</th>
                  <th>덱</th>
                  <th>설명</th>
                  <th>관리</th>
                </tr>
              </thead>
              <tbody>
                {customTerms.map((term) => (
                  <Fragment key={term.id}>
                    <tr>
                      <td>{term.term}</td>
                      <td>{term.reading || "-"}</td>
                      <td>{term.part_of_speech || "-"}</td>
                      <td>{getDisplayMeaning(term.meaning_ko)}</td>
                      <td>{term.deck_name || "공통"}</td>
                      <td>
                        <span className="example-text">
                          {term.description || "-"}
                        </span>
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="secondary-button compact-button"
                            onClick={() => onStartCustomTermEdit(term)}
                          >
                            수정
                          </button>
                          <button
                            type="button"
                            className="danger-button compact-button"
                            onClick={() => onDeleteCustomTerm(term.id)}
                          >
                            삭제
                          </button>
                        </div>
                      </td>
                    </tr>
                    {editingCustomTermId === term.id ? (
                      <tr className="edit-row">
                        <td colSpan={7}>
                          <div className="vocab-form-panel inline-edit-form">
                            <CustomTermForm
                              form={editCustomTermForm}
                              decks={decks}
                              onChange={onEditCustomTermFormChange}
                            />
                            <div className="form-actions">
                              <button
                                type="button"
                                onClick={onSaveCustomTermEdit}
                                disabled={isSavingCustomTerm}
                              >
                                {isSavingCustomTerm ? "저장 중..." : "저장"}
                              </button>
                              <button
                                type="button"
                                className="secondary-button"
                                onClick={onCancelCustomTermEdit}
                                disabled={isSavingCustomTerm}
                              >
                                취소
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty">
            등록된 사용자 정의 용어가 없습니다. 작품 고유명사나 자주 나오는
            용어를 추가하면 분석 결과에 우선 반영됩니다.
          </p>
        )}
      </div>

      ) : null}

      <div className="result-heading">
        <div>
          <h2 className="section-title-with-icon">
            <BrandSectionBadge icon={CardFileIcon} />
            저장된 단어장
          </h2>
          <span>{items.length}개</span>
        </div>
        <div className="heading-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={onRefresh}
            disabled={isLoading}
          >
            {isLoading ? "불러오는 중..." : "새로고침"}
          </button>
        </div>
      </div>

      {message ? (
        <p className={`message message--${classifyMessageTone(message)}`}>
          {message}
        </p>
      ) : null}

      {items.length > 0 ? (
        <div className="vocab-list index-card-drawer">
          {items.map((item) => {
            const isExpanded =
              expandedItemIds.has(item.id) || editingItemId === item.id;
            const isDue =
              !!item.next_review_at &&
              new Date(item.next_review_at).getTime() <= Date.now();

            return (
              <div
                className={`vocabulary-index-row paper-corner vocab-row-status-${item.status}${isExpanded ? " vocab-row-expanded" : ""}`}
                key={item.id}
              >
                <div className="vocab-row-main">
                  <div className="vocab-row-headword">
                    <span className="vocab-item-surface">{item.surface}</span>
                    {item.reading && item.reading !== item.surface ? (
                      <span className="vocab-item-reading">{item.reading}</span>
                    ) : null}
                    <QualityBadge qualityTag={item.quality_tag} />
                  </div>
                  <p className="vocab-row-meaning">
                    {getDisplayMeaning(item.meaning_ko)}
                  </p>
                  <div className="vocab-row-badges">
                    <div
                      className={`vocab-item-status-wrap token-chip-${item.status}`}
                    >
                      <StatusSelect
                        value={item.status}
                        label={`${item.surface} 저장 상태`}
                        onChange={(status) => onStatusChange(item.id, status)}
                      />
                    </div>
                    {isDue ? (
                      <span className="vocab-row-due-chip">복습 예정</span>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    className="ghost-button compact-button vocab-row-toggle"
                    onClick={() => toggleItemExpanded(item.id)}
                    aria-expanded={isExpanded}
                    aria-label={`${item.surface} 상세 정보 ${isExpanded ? "접기" : "펼치기"}`}
                  >
                    <ChevronDownIcon
                      className={`reading-vocab-collapse-icon${
                        isExpanded ? "" : " reading-vocab-collapse-icon-collapsed"
                      }`}
                    />
                    {isExpanded ? "접기" : "펼치기"}
                  </button>
                </div>

                {isExpanded ? (
                  <div className="vocab-row-detail">
                    <div className="vocab-item-secondary">
                      {item.base_form && item.base_form !== item.surface ? (
                        <span className="vocab-item-secondary-tag">
                          기본형 {item.base_form}
                        </span>
                      ) : null}
                      {item.part_of_speech ? (
                        <span className="vocab-item-secondary-tag">
                          {item.part_of_speech}
                        </span>
                      ) : null}
                      <span className="vocab-item-secondary-tag">
                        {item.deck_name}
                      </span>
                    </div>

                    <div className="vocab-item-review-meta">
                      <span className="vocab-item-review-badge">
                        복습 레벨 {item.review_level}
                      </span>
                      <span className="vocab-item-review-badge">
                        맞음 {item.correct_count} · 다시 {item.wrong_count}
                      </span>
                      <span className="vocab-item-review-badge vocab-item-review-badge-accent">
                        <ClockIcon className="vocab-item-review-badge-icon" />
                        {formatNextReview(item.next_review_at)}
                      </span>
                      {item.last_reviewed_at ? (
                        <span className="vocab-item-review-badge vocab-item-review-badge-muted">
                          마지막 복습 {formatDateTime(item.last_reviewed_at)}
                        </span>
                      ) : null}
                    </div>

                    {item.example_sentence ? (
                      <div className="vocab-item-example">
                        <span className="vocab-item-example-label">문맥 예문</span>
                        <p className="vocab-item-example-text">
                          <HighlightedExample
                            sentence={item.example_sentence}
                            surface={item.surface}
                            baseForm={item.base_form}
                            normalizedForm={item.normalized_form}
                          />
                        </p>
                      </div>
                    ) : (
                      <p className="vocab-item-example-empty">저장된 예문이 없어요.</p>
                    )}

                    <div className="vocab-item-actions">
                      <MeaningQuickEdit
                        isEditing={meaningEditItemId === item.id}
                        draftValue={meaningEditDraft}
                        isSaving={isSavingMeaningEdit}
                        message={
                          meaningEditItemId === item.id ? meaningEditMessage : ""
                        }
                        onStartEdit={() =>
                          onStartMeaningEdit(item.id, item.meaning_ko)
                        }
                        onDraftChange={onMeaningEditDraftChange}
                        onSave={onSaveMeaningEdit}
                        onCancel={onCancelMeaningEdit}
                      />
                      <button
                        type="button"
                        className="ghost-button compact-button"
                        onClick={() => onReportMeaning(item)}
                      >
                        뜻 오류 신고
                      </button>
                      <button
                        type="button"
                        className="secondary-button compact-button"
                        onClick={() => onStartEdit(item)}
                      >
                        수정
                      </button>
                      <button
                        type="button"
                        className="danger-button danger-button-subtle compact-button"
                        onClick={() => {
                          const label = item.surface || item.base_form;
                          if (
                            window.confirm(
                              `"${label}" 단어를 삭제할까요? 저장된 학습 기록도 함께 삭제됩니다.`,
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
                      <div className="vocab-form-panel inline-edit-form">
                        <div className="form-heading">
                          <h2>단어 수정</h2>
                        </div>
                        <VocabItemForm
                          form={editVocabForm}
                          decks={decks}
                          onChange={onEditVocabFormChange}
                        />
                        <div className="form-actions">
                          <button
                            type="button"
                            onClick={onSaveEdit}
                            disabled={isUpdatingVocab}
                          >
                            {isUpdatingVocab ? "저장 중..." : "저장"}
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={onCancelEdit}
                            disabled={isUpdatingVocab}
                          >
                            취소
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : dueOnly && !searchText.trim() && statusFilter === "all" ? (
        <AppEmptyState
          mood="empty"
          title="지금 복습할 단어가 없어요."
          description="새 원문을 읽고 단어를 더 담아보세요."
        >
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={onGoToReading}
          >
            <BookIcon className="button-icon" />
            원문 읽기
          </button>
        </AppEmptyState>
      ) : hasActiveFilter ? (
        <AppEmptyState
          mood="empty"
          title="찾는 단어가 없어요."
          description="검색어를 바꾸거나 필터를 풀어보세요."
        >
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={resetVocabFilters}
          >
            필터 초기화
          </button>
        </AppEmptyState>
      ) : (
        <AppEmptyState
          mood="empty"
          title="아직 담은 단어가 없어요."
          description="원문을 읽으며 모르는 단어를 어휘 노트에 쌓아보세요."
        >
          <div className="study-actions">
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={onGoToReading}
            >
              <BookIcon className="button-icon" />
              원문 읽기 시작
            </button>
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={onGoToShared}
            >
              <BookshelfIcon className="button-icon" />
              덱 책장 둘러보기
            </button>
          </div>
        </AppEmptyState>
      )}
    </section>
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

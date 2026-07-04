"use client";

import { Fragment, useState } from "react";
import { formatDateTime, formatNextReview, StatusSelect } from "./shared";
import type {
  Deck,
  CustomTerm,
  CustomTermFormData,
  QualityTag,
  TokenStatus,
  VocabFormData,
  VocabItem,
  VocabSort,
} from "./types";

type VocabSectionProps = {
  items: VocabItem[];
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
};

export function VocabSection({
  items,
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
}: VocabSectionProps) {
  const [isManagementOpen, setIsManagementOpen] = useState(false);
  const [isCustomTermManagerOpen, setIsCustomTermManagerOpen] = useState(false);
  const [isBackupToolsOpen, setIsBackupToolsOpen] = useState(false);

  return (
    <section className="tab-panel" aria-live="polite">
      <div className="vocab-compact-toolbar">
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
        <input
          value={searchText}
          onChange={(event) => onSearchTextChange(event.target.value)}
          placeholder="단어, 뜻, 읽기, 예문 검색"
        />
        <label className="inline-field">
          상태
          <select
            value={statusFilter}
            onChange={(event) =>
              onStatusFilterChange(event.target.value as "all" | TokenStatus)
            }
          >
            <option value="all">전체</option>
            <option value="known">완벽히 아는 단어</option>
            <option value="uncertain">헷갈리는 단어</option>
            <option value="unknown">모르는 단어</option>
            <option value="unclassified">분류되지 않음</option>
          </select>
        </label>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={dueOnly}
            onChange={(event) => onDueOnlyChange(event.target.checked)}
          />
          복습 대상만 보기
        </label>
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
        <button
          type="button"
          className="secondary-button"
          onClick={onStudySelectedDeck}
          disabled={selectedDeckId === "all"}
          title={
            selectedDeckId === "all"
              ? "학습할 특정 덱을 먼저 선택해 주세요."
              : undefined
          }
        >
          이 덱 학습하기
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={() => onNewVocabFormOpenChange(!isNewVocabFormOpen)}
        >
          {isNewVocabFormOpen ? "단어 추가 닫기" : "+ 단어 직접 추가"}
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={() => setIsManagementOpen((open) => !open)}
          aria-expanded={isManagementOpen}
        >
          덱/공유 관리
        </button>
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

      {deckMessage ? <p className="message">{deckMessage}</p> : null}

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
                      <td>{term.meaning_ko || "-"}</td>
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
          <h2>저장된 단어장</h2>
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

      {message ? <p className="message">{message}</p> : null}

      {items.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>단어</th>
                <th>덱</th>
                <th>기본형</th>
                <th>읽기</th>
                <th>품사</th>
                <th>뜻</th>
                <th>예문</th>
                <th>상태</th>
                <th>맞음</th>
                <th>틀림</th>
                <th>레벨</th>
                <th>마지막 복습</th>
                <th>다음 복습</th>
                <th>관리</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <Fragment key={item.id}>
                  <tr>
                    <td>
                      <div>{item.surface}</div>
                      <QualityBadge qualityTag={item.quality_tag} />
                    </td>
                    <td>{item.deck_name}</td>
                    <td>{item.base_form}</td>
                    <td>{item.reading}</td>
                    <td>{item.part_of_speech}</td>
                    <td>
                      <div>{item.meaning_ko || "-"}</div>
                      {item.dictionary_gloss ? (
                        <div className="gloss-text">
                          영어 gloss: {item.dictionary_gloss}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <span className="example-text">
                        {item.example_sentence || "-"}
                      </span>
                    </td>
                    <td>
                      <StatusSelect
                        value={item.status}
                        label={`${item.surface} 저장 상태`}
                        onChange={(status) => onStatusChange(item.id, status)}
                      />
                    </td>
                    <td>{item.correct_count}</td>
                    <td>{item.wrong_count}</td>
                    <td>{item.review_level}</td>
                    <td>{formatDateTime(item.last_reviewed_at)}</td>
                    <td>{formatNextReview(item.next_review_at)}</td>
                    <td>
                      <div className="row-actions">
                        <button
                          type="button"
                          className="secondary-button compact-button"
                          onClick={() => onStartEdit(item)}
                        >
                          수정
                        </button>
                        <button
                          type="button"
                          className="danger-button compact-button"
                          onClick={() => onDelete(item.id)}
                        >
                          삭제
                        </button>
                      </div>
                    </td>
                  </tr>
                  {editingItemId === item.id ? (
                    <tr className="edit-row">
                      <td colSpan={14}>
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
          표시할 단어가 없습니다. 검색어와 필터를 바꾸거나 단어를 직접
          추가해 보세요.
        </p>
      )}
    </section>
  );
}

const qualityTagLabels: Record<Exclude<QualityTag, "normal">, string> = {
  custom_term: "사용자 용어",
  compound_verb: "복합동사",
  noun_phrase_candidate: "명사구 후보",
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

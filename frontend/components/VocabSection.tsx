"use client";

import { Fragment } from "react";
import { formatDateTime, formatNextReview, StatusSelect } from "./shared";
import type {
  Deck,
  CustomTerm,
  CustomTermFormData,
  TokenStatus,
  VocabFormData,
  VocabItem,
  VocabSort,
} from "./types";

type VocabSectionProps = {
  items: VocabItem[];
  isLoading: boolean;
  isExportingCsv: boolean;
  explainingItemId: number | null;
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
  onExplain: (itemId: number) => void;
  onStatusChange: (itemId: number, status: TokenStatus) => void;
  onDelete: (itemId: number) => void;
};

export function VocabSection({
  items,
  isLoading,
  isExportingCsv,
  explainingItemId,
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
  onExplain,
  onStatusChange,
  onDelete,
}: VocabSectionProps) {
  return (
    <section className="tab-panel" aria-live="polite">
      <div className="vocab-filters">
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
      </div>

      <div className="deck-toolbar">
        <label className="inline-field">
          보기
          <select value={selectedDeckId} onChange={(event) => onSelectedDeckChange(event.target.value)}>
            <option value="all">전체 단어장</option>
            {decks.map((deck) => (
              <option key={deck.id} value={String(deck.id)}>
                {deck.name}
              </option>
            ))}
          </select>
        </label>
        {selectedDeckId !== "all" ? (
          <button
            type="button"
            className="secondary-button"
            onClick={() => onDeleteDeck(Number(selectedDeckId))}
            disabled={selectedDeckId === defaultDeckId}
            title={
              selectedDeckId === defaultDeckId
                ? "기본 단어장은 삭제할 수 없습니다."
                : undefined
            }
          >
            덱 삭제
          </button>
        ) : null}
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

      {!isNewVocabFormOpen ? (
        <div className="collapsible-action">
          <button
            type="button"
            className="secondary-button"
            onClick={() => onNewVocabFormOpenChange(true)}
          >
            + 단어 직접 추가
          </button>
        </div>
      ) : (
        <div className="vocab-form-panel">
          <div className="form-heading">
            <h2>단어 직접 추가</h2>
          </div>
          <VocabItemForm
            form={newVocabForm}
            decks={decks}
            includeContextExplanation={false}
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

      <div className="result-heading">
        <div>
          <h2>저장된 단어장</h2>
          <span>{items.length}개</span>
        </div>
        <div className="heading-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={onDownloadCsv}
            disabled={isExportingCsv}
          >
            {isExportingCsv ? "다운로드 중..." : "CSV 다운로드"}
          </button>
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
                <th>AI 설명</th>
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
                    <td>{item.surface}</td>
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
                      <div className="ai-explanation-cell">
                        {item.context_explanation_ko ? (
                          <span className="example-text">
                            {item.context_explanation_ko}
                          </span>
                        ) : (
                          <span className="muted-text">-</span>
                        )}
                        <button
                          type="button"
                          className="secondary-button compact-button"
                          onClick={() => onExplain(item.id)}
                          disabled={explainingItemId === item.id}
                        >
                          {explainingItemId === item.id
                            ? "생성 중..."
                            : item.context_explanation_ko
                              ? "AI 설명 다시 생성"
                              : "AI 설명 생성"}
                        </button>
                      </div>
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
                      <td colSpan={15}>
                        <div className="vocab-form-panel inline-edit-form">
                          <div className="form-heading">
                            <h2>단어 수정</h2>
                          </div>
                          <VocabItemForm
                            form={editVocabForm}
                            decks={decks}
                            includeContextExplanation
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

type VocabItemFormProps = {
  form: VocabFormData;
  decks: Deck[];
  includeContextExplanation: boolean;
  onChange: (field: keyof VocabFormData, value: string) => void;
};

function VocabItemForm({
  form,
  decks,
  includeContextExplanation,
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
      {includeContextExplanation ? (
        <label className="inline-field wide-field">
          AI 문맥 설명
          <textarea
            className="compact-textarea"
            value={form.context_explanation_ko}
            onChange={(event) =>
              onChange("context_explanation_ko", event.target.value)
            }
          />
        </label>
      ) : null}
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

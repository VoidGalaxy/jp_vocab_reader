"use client";

import { formatDateTime, formatNextReview, StatusSelect } from "./shared";
import type { Deck, TokenStatus, VocabItem, VocabSort } from "./types";

type VocabSectionProps = {
  items: VocabItem[];
  isLoading: boolean;
  isExportingCsv: boolean;
  explainingItemId: number | null;
  message: string;
  decks: Deck[];
  selectedDeckId: string;
  searchText: string;
  statusFilter: "all" | TokenStatus;
  dueOnly: boolean;
  sortValue: VocabSort;
  newDeckName: string;
  newDeckDescription: string;
  isCreatingDeck: boolean;
  deckMessage: string;
  onSelectedDeckChange: (deckId: string) => void;
  onSearchTextChange: (text: string) => void;
  onStatusFilterChange: (status: "all" | TokenStatus) => void;
  onDueOnlyChange: (checked: boolean) => void;
  onSortChange: (sort: VocabSort) => void;
  onNewDeckNameChange: (name: string) => void;
  onNewDeckDescriptionChange: (description: string) => void;
  onCreateDeck: () => void;
  onDeleteDeck: (deckId: number) => void;
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
  searchText,
  statusFilter,
  dueOnly,
  sortValue,
  newDeckName,
  newDeckDescription,
  isCreatingDeck,
  deckMessage,
  onSelectedDeckChange,
  onSearchTextChange,
  onStatusFilterChange,
  onDueOnlyChange,
  onSortChange,
  onNewDeckNameChange,
  onNewDeckDescriptionChange,
  onCreateDeck,
  onDeleteDeck,
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
            <option value="unknown">모르는 단어</option>
            <option value="known">아는 단어</option>
            <option value="unclassified">미분류</option>
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
                <th>삭제</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.surface}</td>
                  <td>{item.deck_name}</td>
                  <td>{item.base_form}</td>
                  <td>{item.reading}</td>
                  <td>{item.part_of_speech}</td>
                  <td>{item.meaning_ko || "-"}</td>
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
                    <button
                      type="button"
                      className="danger-button"
                      onClick={() => onDelete(item.id)}
                    >
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="empty">조건에 맞는 단어가 없습니다.</p>
      )}
    </section>
  );
}

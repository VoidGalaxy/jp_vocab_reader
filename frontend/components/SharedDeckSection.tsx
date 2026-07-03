import { formatDateTime } from "./shared";
import type { SharedDeckDetail, SharedDeckSummary } from "./types";

type SharedDeckSectionProps = {
  decks: SharedDeckSummary[];
  selectedDeck: SharedDeckDetail | null;
  selectedDeckId: number | null;
  isLoading: boolean;
  isLoadingDetail: boolean;
  importingDeckId: number | null;
  message: string;
  onRefresh: () => void;
  onSelectDeck: (deckId: number) => void;
  onImportDeck: (deckId: number) => void;
};

export function SharedDeckSection({
  decks,
  selectedDeck,
  selectedDeckId,
  isLoading,
  isLoadingDetail,
  importingDeckId,
  message,
  onRefresh,
  onSelectDeck,
  onImportDeck,
}: SharedDeckSectionProps) {
  return (
    <section className="tab-panel shared-deck-section" aria-live="polite">
      <div className="result-heading">
        <div>
          <h2>공유 덱</h2>
          <span>{decks.length}개</span>
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

      {decks.length > 0 ? (
        <div className="shared-deck-grid">
          {decks.map((deck) => (
            <article
              key={deck.id}
              className={
                selectedDeckId === deck.id
                  ? "shared-deck-card selected-shared-deck-card"
                  : "shared-deck-card"
              }
            >
              <div>
                <h3>{deck.title}</h3>
                <p className="muted-text">
                  {deck.description || "설명이 없습니다."}
                </p>
              </div>
              <dl className="shared-deck-meta">
                <div>
                  <dt>작성자</dt>
                  <dd>{deck.owner_display_name || "-"}</dd>
                </div>
                <div>
                  <dt>단어</dt>
                  <dd>{deck.vocab_count}</dd>
                </div>
                <div>
                  <dt>용어</dt>
                  <dd>{deck.custom_term_count}</dd>
                </div>
                <div>
                  <dt>가져오기</dt>
                  <dd>{deck.import_count}</dd>
                </div>
                <div>
                  <dt>등록일</dt>
                  <dd>{formatDateTime(deck.created_at)}</dd>
                </div>
              </dl>
              <div className="row-actions">
                <button
                  type="button"
                  className="secondary-button compact-button"
                  onClick={() => onSelectDeck(deck.id)}
                  disabled={isLoadingDetail && selectedDeckId === deck.id}
                >
                  {isLoadingDetail && selectedDeckId === deck.id
                    ? "불러오는 중..."
                    : "상세 보기"}
                </button>
                <button
                  type="button"
                  className="compact-button"
                  onClick={() => onImportDeck(deck.id)}
                  disabled={importingDeckId === deck.id}
                >
                  {importingDeckId === deck.id
                    ? "가져오는 중..."
                    : "내 덱으로 가져오기"}
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="empty">
          공개 공유 덱이 없습니다. 단어장 탭에서 현재 덱을 공유 덱으로 등록할 수
          있습니다.
        </p>
      )}

      {selectedDeck ? (
        <section className="shared-deck-detail">
          <div className="result-heading compact-heading">
            <div>
              <h2>{selectedDeck.title}</h2>
              <span>
                단어 {selectedDeck.vocab_count}개 · 용어{" "}
                {selectedDeck.custom_term_count}개
              </span>
            </div>
            <button
              type="button"
              onClick={() => onImportDeck(selectedDeck.id)}
              disabled={importingDeckId === selectedDeck.id}
            >
              {importingDeckId === selectedDeck.id
                ? "가져오는 중..."
                : "내 덱으로 가져오기"}
            </button>
          </div>
          <p className="muted-text">
            {selectedDeck.description || "설명이 없습니다."}
          </p>

          <div className="shared-detail-columns">
            <div>
              <h3>단어 미리보기</h3>
              {selectedDeck.items.length > 0 ? (
                <div className="shared-preview-list">
                  {selectedDeck.items.slice(0, 30).map((item) => (
                    <div key={item.id} className="shared-preview-row">
                      <strong>{item.surface || item.base_form || "-"}</strong>
                      <span>{item.reading || "-"}</span>
                      <span>{item.meaning_ko || item.dictionary_gloss || "-"}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="empty">공유된 단어가 없습니다.</p>
              )}
            </div>

            <div>
              <h3>사용자 정의 용어</h3>
              {selectedDeck.custom_terms.length > 0 ? (
                <div className="shared-preview-list">
                  {selectedDeck.custom_terms.slice(0, 30).map((term) => (
                    <div key={term.id} className="shared-preview-row">
                      <strong>{term.term}</strong>
                      <span>{term.reading || "-"}</span>
                      <span>{term.meaning_ko || term.description || "-"}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="empty">공유된 사용자 정의 용어가 없습니다.</p>
              )}
            </div>
          </div>
        </section>
      ) : null}
    </section>
  );
}

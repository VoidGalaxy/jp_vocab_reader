import {
  formatDateTime,
  getJlptLevel,
  sortSharedDecksByJlptLevel,
} from "./shared";
import type { SharedDeckDetail, SharedDeckSummary } from "./types";

function JlptLevelTag({ level }: { level: string }) {
  return (
    <span className={`jlpt-level-tag jlpt-level-${level.toLowerCase()}`}>
      {level}
    </span>
  );
}

type SharedDeckSectionProps = {
  decks: SharedDeckSummary[];
  selectedDeck: SharedDeckDetail | null;
  selectedDeckId: number | null;
  isLoading: boolean;
  isLoadingDetail: boolean;
  importingDeckId: number | null;
  importedDeckId: number | null;
  unpublishingDeckId: number | null;
  message: string;
  onRefresh: () => void;
  onSelectDeck: (deckId: number) => void;
  onCloseDetail: () => void;
  onImportDeck: (deckId: number) => void;
  onUnpublishDeck: (deckId: number) => void;
  onGoToVocab: () => void;
};

export function SharedDeckSection({
  decks,
  selectedDeck,
  selectedDeckId,
  isLoading,
  isLoadingDetail,
  importingDeckId,
  importedDeckId,
  unpublishingDeckId,
  message,
  onRefresh,
  onSelectDeck,
  onCloseDetail,
  onImportDeck,
  onUnpublishDeck,
  onGoToVocab,
}: SharedDeckSectionProps) {
  const sortedDecks = sortSharedDecksByJlptLevel(decks);
  const hasJlptDeck = sortedDecks.some((deck) => getJlptLevel(deck.title));

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

      {hasJlptDeck ? (
        <p className="shared-deck-disclaimer">
          JLPT 추천 어휘 덱은 공식 JLPT 어휘 목록이 아니라, 공개 학습 자료와
          내부 사전 데이터를 바탕으로 구성한 학습용 추천 덱입니다.
        </p>
      ) : null}

      {message ? (
        <div className="shared-deck-message">
          <p className="message">{message}</p>
          <button
            type="button"
            className="secondary-button compact-button"
            onClick={onGoToVocab}
          >
            단어장 탭으로 이동
          </button>
        </div>
      ) : null}

      {sortedDecks.length > 0 ? (
        <div className="shared-deck-grid">
          {sortedDecks.map((deck) => {
            const isSelected = selectedDeckId === deck.id;
            const isImporting = importingDeckId === deck.id;
            const isImported = importedDeckId === deck.id;
            const isUnpublishing = unpublishingDeckId === deck.id;
            const level = getJlptLevel(deck.title);
            const totalWordCount = deck.vocab_count + deck.custom_term_count;
            return (
              <article
                key={deck.id}
                className={
                  isSelected
                    ? "shared-deck-card selected-shared-deck-card"
                    : "shared-deck-card"
                }
              >
                <div>
                  <div className="shared-deck-title-row">
                    <h3>{deck.title}</h3>
                    {level ? <JlptLevelTag level={level} /> : null}
                    <span className="shared-deck-word-count-badge">
                      단어 {totalWordCount}개
                    </span>
                  </div>
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
                    <dt>단어 수</dt>
                    <dd>{deck.vocab_count}</dd>
                  </div>
                  <div>
                    <dt>용어 수</dt>
                    <dd>{deck.custom_term_count}</dd>
                  </div>
                  <div>
                    <dt>공유된 횟수</dt>
                    <dd>{deck.import_count}</dd>
                  </div>
                  <div>
                    <dt>등록일</dt>
                    <dd>{formatDateTime(deck.created_at)}</dd>
                  </div>
                  <div>
                    <dt>상태</dt>
                    <dd>
                      {isImported
                        ? "가져오기 완료"
                        : isSelected
                          ? "상세 표시 중"
                          : "공개"}
                    </dd>
                  </div>
                </dl>
                <div className="row-actions">
                  <button
                    type="button"
                    className="secondary-button compact-button"
                    onClick={() => onSelectDeck(deck.id)}
                    disabled={isLoadingDetail && isSelected}
                  >
                    {isLoadingDetail && isSelected
                      ? "불러오는 중..."
                      : isSelected
                        ? "상세 닫기"
                        : "상세 보기"}
                  </button>
                  <button
                    type="button"
                    className="compact-button"
                    onClick={() => onImportDeck(deck.id)}
                    disabled={isImporting}
                  >
                    {isImporting
                      ? "가져오는 중..."
                      : isImported
                        ? "가져오기 완료"
                        : "내 덱으로 가져오기"}
                  </button>
                  {deck.is_owner ? (
                    <button
                      type="button"
                      className="secondary-button compact-button danger-button"
                      onClick={() => onUnpublishDeck(deck.id)}
                      disabled={isUnpublishing}
                    >
                      {isUnpublishing ? "공유 취소 중..." : "공유 취소"}
                    </button>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="empty">
          공개 공유 덱이 없습니다. 단어장 탭에서 현재 덱을 공유 덱으로
          등록할 수 있습니다.
        </p>
      )}

      {selectedDeck ? (
        <section className="shared-deck-detail">
          <div className="result-heading compact-heading">
            <div>
              <div className="shared-deck-title-row">
                <h2>{selectedDeck.title}</h2>
                {getJlptLevel(selectedDeck.title) ? (
                  <JlptLevelTag level={getJlptLevel(selectedDeck.title)!} />
                ) : null}
              </div>
              <span>
                단어 수 {selectedDeck.vocab_count}개 · 용어 수{" "}
                {selectedDeck.custom_term_count}개 · 공유된 횟수{" "}
                {selectedDeck.import_count}회
              </span>
            </div>
            <div className="heading-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={onCloseDetail}
              >
                닫기
              </button>
              <button
                type="button"
                onClick={() => onImportDeck(selectedDeck.id)}
                disabled={importingDeckId === selectedDeck.id}
              >
                {importingDeckId === selectedDeck.id
                  ? "가져오는 중..."
                  : importedDeckId === selectedDeck.id
                    ? "가져오기 완료"
                    : "내 덱으로 가져오기"}
              </button>
              {selectedDeck.is_owner ? (
                <button
                  type="button"
                  className="secondary-button danger-button"
                  onClick={() => onUnpublishDeck(selectedDeck.id)}
                  disabled={unpublishingDeckId === selectedDeck.id}
                >
                  {unpublishingDeckId === selectedDeck.id
                    ? "공유 취소 중..."
                    : "공유 취소"}
                </button>
              ) : null}
            </div>
          </div>
          <p className="muted-text">
            {selectedDeck.description || "설명이 없습니다."}
          </p>
          {getJlptLevel(selectedDeck.title) ? (
            <p className="shared-deck-disclaimer">
              JLPT 추천 어휘 덱은 공식 JLPT 어휘 목록이 아니라, 공개 학습
              자료와 내부 사전 데이터를 바탕으로 구성한 학습용 추천 덱입니다.
            </p>
          ) : null}
          {selectedDeck.is_owner ? (
            <p className="muted-text shared-deck-owner-hint">
              공유 취소하면 공유 목록에서만 내려가며, 이미 가져간 개인 덱은
              삭제되지 않습니다.
            </p>
          ) : null}

          <div className="shared-detail-columns">
            <div>
              <h3>단어 미리보기 (최대 20개)</h3>
              {selectedDeck.items.length > 0 ? (
                <div className="shared-preview-list">
                  {selectedDeck.items.slice(0, 20).map((item) => (
                    <div key={item.id} className="shared-preview-row">
                      <strong>{item.surface || item.base_form || "-"}</strong>
                      <span>{item.reading || "-"}</span>
                      <span>{item.meaning_ko || "-"}</span>
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

          <div className="form-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={onCloseDetail}
            >
              닫기
            </button>
          </div>
        </section>
      ) : null}
    </section>
  );
}

import { classifyMessageTone } from "./coverageUtils";
import { FolderIcon, ShareIcon, ShieldIcon } from "./icons";
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
  const selectedAlreadyImported = selectedDeck
    ? Boolean(selectedDeck.imported_at) || importedDeckId === selectedDeck.id
    : false;

  function handleImportClick(deck: SharedDeckSummary) {
    if (deck.imported_at) {
      const confirmed = window.confirm(
        `이미 가져온 공유덱입니다 (${formatDateTime(deck.imported_at)}). 다시 가져올까요?`,
      );
      if (!confirmed) {
        return;
      }
    }
    onImportDeck(deck.id);
  }

  const messageTone = classifyMessageTone(message);
  const isInitialLoading = isLoading && decks.length === 0;

  return (
    <section className="tab-panel shared-deck-section" aria-live="polite">
      <section className="panel-card hero-card shared-hero-card">
        <div className="panel-card-header">
          <h2 className="panel-card-title">공유덱</h2>
          <p className="panel-card-description">
            다른 사용자가 공유한 어휘 덱과 JLPT 추천 어휘를 가져와 문맥
            예문과 함께 학습하세요.
          </p>
        </div>
        <div className="landing-hero-actions">
          <button type="button" onClick={onGoToVocab}>
            <FolderIcon className="button-icon" />내 단어장 보기
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
        <p className="landing-trust-note">
          <ShieldIcon className="landing-trust-note-icon" />
          <span className="home-trust-list-wrap">
            <span>가져온 덱은 내 단어장에 그대로 추가됩니다.</span>
            <span>공유덱에는 사용자 원문 전체가 포함되지 않습니다.</span>
          </span>
        </p>
      </section>

      {hasJlptDeck ? (
        <p className="shared-deck-disclaimer">
          JLPT 추천 어휘 덱은 공식 JLPT 어휘 목록이 아니라, 공개 학습 자료와
          내부 사전 데이터를 바탕으로 구성한 학습용 추천 덱입니다.
        </p>
      ) : null}

      {message ? (
        <div className="shared-deck-message">
          <p className={`message message--${messageTone}`}>{message}</p>
          <button
            type="button"
            className="secondary-button compact-button"
            onClick={onGoToVocab}
          >
            단어장 탭으로 이동
          </button>
        </div>
      ) : null}

      {isInitialLoading ? (
        <div className="empty-guide">
          <ShareIcon className="empty-state-icon" />
          <p>공유덱을 불러오는 중입니다...</p>
        </div>
      ) : sortedDecks.length > 0 ? (
        <div className="shared-deck-grid">
          {sortedDecks.map((deck) => {
            const isSelected = selectedDeckId === deck.id;
            const isImporting = importingDeckId === deck.id;
            const isImported = importedDeckId === deck.id;
            const isUnpublishing = unpublishingDeckId === deck.id;
            const level = getJlptLevel(deck.title);
            const totalWordCount = deck.vocab_count + deck.custom_term_count;
            const alreadyImported = Boolean(deck.imported_at) || isImported;
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
                    {alreadyImported ? (
                      <span
                        className="shared-deck-imported-badge"
                        title={
                          deck.imported_at
                            ? `가져온 날짜: ${formatDateTime(deck.imported_at)}`
                            : undefined
                        }
                      >
                        가져옴
                        {deck.imported_at
                          ? ` · ${formatDateTime(deck.imported_at)}`
                          : ""}
                      </span>
                    ) : null}
                  </div>
                  <p className="shared-deck-description">
                    {deck.description || "설명이 없습니다."}
                  </p>
                </div>
                <p className="shared-deck-byline">
                  {deck.owner_display_name ? `${deck.owner_display_name} · ` : ""}
                  등록일 {formatDateTime(deck.created_at)} · 가져간 횟수{" "}
                  {deck.import_count}회
                </p>
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
                    className={
                      alreadyImported
                        ? "secondary-button compact-button"
                        : "compact-button"
                    }
                    onClick={() => handleImportClick(deck)}
                    disabled={isImporting}
                  >
                    {isImporting
                      ? "가져오는 중..."
                      : alreadyImported
                        ? "다시 가져오기"
                        : "내 덱으로 가져오기"}
                  </button>
                  {deck.is_owner ? (
                    <button
                      type="button"
                      className="danger-secondary-button compact-button"
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
        <div className="empty-guide">
          <ShareIcon className="empty-state-icon" />
          <p>아직 공유된 덱이 없습니다.</p>
          <p className="muted-text">
            내 단어장을 공유하거나, 단어장 탭에서 JLPT 추천 어휘 덱을 가져와
            보세요.
          </p>
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={onGoToVocab}
          >
            <FolderIcon className="button-icon" />
            단어장 탭으로 이동
          </button>
        </div>
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
                {selectedAlreadyImported ? (
                  <span
                    className="shared-deck-imported-badge"
                    title={
                      selectedDeck.imported_at
                        ? `가져온 날짜: ${formatDateTime(selectedDeck.imported_at)}`
                        : undefined
                    }
                  >
                    가져옴
                    {selectedDeck.imported_at
                      ? ` · ${formatDateTime(selectedDeck.imported_at)}`
                      : ""}
                  </span>
                ) : null}
              </div>
              <span className="shared-deck-byline">
                {selectedDeck.owner_display_name
                  ? `${selectedDeck.owner_display_name} · `
                  : ""}
                단어 수 {selectedDeck.vocab_count}개 · 용어 수{" "}
                {selectedDeck.custom_term_count}개 · 가져간 횟수{" "}
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
                className={selectedAlreadyImported ? "secondary-button" : undefined}
                onClick={() => handleImportClick(selectedDeck)}
                disabled={importingDeckId === selectedDeck.id}
              >
                {importingDeckId === selectedDeck.id
                  ? "가져오는 중..."
                  : selectedAlreadyImported
                    ? "다시 가져오기"
                    : "내 덱으로 가져오기"}
              </button>
              {selectedDeck.is_owner ? (
                <button
                  type="button"
                  className="danger-secondary-button"
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
          <p className="shared-deck-description">
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

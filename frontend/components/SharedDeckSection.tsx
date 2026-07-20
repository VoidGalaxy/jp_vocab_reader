import {
  BrandDeckCover,
  BrandEmptyIllustration,
  BrandSectionBadge,
  StudyCompanion,
} from "./BrandElements";
import { classifyMessageTone } from "./coverageUtils";
import { BookIcon, FolderIcon, RotateIcon, ShareIcon, ShieldIcon } from "./icons";
import {
  formatDateTime,
  getDisplayMeaning,
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

// UI-only display label -- the underlying deck.title in the DB may still be
// the older "N5어휘모음" form (see getJlptLevel's pattern below); this only
// normalizes what's rendered, never the stored data.
function getDisplayTitle(deck: SharedDeckSummary, level: string | null) {
  if (level) {
    return `JLPT 추천 어휘 ${level}`;
  }
  return deck.title;
}

const jlptLevelDescriptions: Record<string, string> = {
  N5: "기초 문장 읽기에 자주 쓰이는 추천 어휘입니다.",
  N4: "초급 원문 읽기에 도움이 되는 추천 어휘입니다.",
  N3: "중급 독해로 넘어가기 위한 추천 어휘입니다.",
  N2: "긴 문장과 기사 독해에 도움이 되는 추천 어휘입니다.",
  N1: "고급 독해와 원서 읽기에 도움이 되는 추천 어휘입니다.",
};

const DEFAULT_SHARED_DECK_DESCRIPTION =
  "일본어 원문 읽기에 활용할 수 있는 공유 어휘 덱입니다. 가져와서 내 단어장에 추가하고 복습할 수 있어요.";

// Display-only fallback -- never written back, so a deck with no
// description in the DB still reads as a finished library card instead of
// showing "설명이 없습니다."
function getDeckDescription(
  description: string | null | undefined,
  level: string | null,
) {
  const trimmed = description?.trim();
  if (trimmed) {
    return trimmed;
  }
  if (level && jlptLevelDescriptions[level]) {
    return jlptLevelDescriptions[level];
  }
  return DEFAULT_SHARED_DECK_DESCRIPTION;
}

// Resolves which BrandDeckCover tone/level a deck gets -- level wins
// (recommended-vocab ramp), otherwise ownership decides 내가 공유함 vs 공유 덱.
function getDeckCoverProps(deck: SharedDeckSummary, level: string | null) {
  if (level) {
    return { tone: "recommended" as const, level };
  }
  return { tone: deck.is_owner ? ("mine" as const) : ("shared" as const) };
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
  const selectedLevel = selectedDeck ? getJlptLevel(selectedDeck.title) : null;

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

  function renderDeckCard(deck: SharedDeckSummary) {
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
        <BrandDeckCover {...getDeckCoverProps(deck, level)} />
        <div>
          <div className="shared-deck-title-row">
            <h3>{getDisplayTitle(deck, level)}</h3>
            {level ? <JlptLevelTag level={level} /> : null}
          </div>
          <div className="shared-deck-meta-row">
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
                {deck.imported_at ? ` · ${formatDateTime(deck.imported_at)}` : ""}
              </span>
            ) : null}
          </div>
          <p className="shared-deck-description">
            {getDeckDescription(deck.description, level)}
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
            title={
              alreadyImported
                ? "이미 가져온 덱입니다. 다시 가져오면 확인 후 새로 추가됩니다."
                : undefined
            }
          >
            {isImporting
              ? "가져오는 중..."
              : alreadyImported
                ? "다시 가져오기"
                : "내 노트에 가져오기"}
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
  }

  const recommendedDecks = sortedDecks.filter((deck) => getJlptLevel(deck.title));
  const myDecks = sortedDecks.filter(
    (deck) => !getJlptLevel(deck.title) && deck.is_owner,
  );
  const otherDecks = sortedDecks.filter(
    (deck) => !getJlptLevel(deck.title) && !deck.is_owner,
  );
  // Grouping is a display-only partition of the already-fetched `decks`
  // array (by fields the API already returns) -- no extra fetch/filter
  // logic, so an ambiguous shape just falls back to one plain grid below.
  const hasGroups = recommendedDecks.length > 0 && (myDecks.length > 0 || otherDecks.length > 0);

  const messageTone = classifyMessageTone(message);
  const isInitialLoading = isLoading && decks.length === 0;

  return (
    <section className="tab-panel shared-deck-section" aria-live="polite">
      <section className="panel-card hero-card shared-hero-card">
        <div className="panel-card-header">
          <h2 className="panel-card-title">
            <BrandSectionBadge icon={BookIcon} />
            덱 책장
          </h2>
          <p className="panel-card-description">
            추천 어휘 덱을 둘러보고 내 노트에 가져오세요.
          </p>
        </div>
        <div className="landing-hero-actions">
          <button type="button" onClick={onGoToVocab}>
            <ShareIcon className="button-icon" />어휘 노트 공유하기
          </button>
          <button type="button" className="secondary-button" onClick={onGoToVocab}>
            <FolderIcon className="button-icon" />어휘 노트 보기
          </button>
          <button
            type="button"
            className="ghost-button"
            onClick={onRefresh}
            disabled={isLoading}
          >
            <RotateIcon className="button-icon" />
            {isLoading ? "불러오는 중..." : "새로고침"}
          </button>
        </div>
        <p className="info-strip">
          <ShieldIcon className="info-strip-icon" />
          가져온 덱은 내 노트에 바로 추가돼요. 원문 전체는 들어가지 않습니다.
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
            어휘 노트로 이동
          </button>
        </div>
      ) : null}

      {isInitialLoading ? (
        <div className="empty-guide">
          <BrandEmptyIllustration icon={ShareIcon} />
          <p>공유덱을 불러오는 중입니다...</p>
        </div>
      ) : sortedDecks.length > 0 ? (
        hasGroups ? (
          <>
            {recommendedDecks.length > 0 ? (
              <div className="shared-deck-shelf">
                <h3 className="shared-deck-shelf-title">JLPT 추천 어휘 서가</h3>
                <div className="shared-deck-grid">
                  {recommendedDecks.map(renderDeckCard)}
                </div>
              </div>
            ) : null}
            {myDecks.length > 0 ? (
              <div className="shared-deck-shelf">
                <h3 className="shared-deck-shelf-title">내가 공유한 덱</h3>
                <div className="shared-deck-grid">{myDecks.map(renderDeckCard)}</div>
              </div>
            ) : null}
            {otherDecks.length > 0 ? (
              <div className="shared-deck-shelf">
                <h3 className="shared-deck-shelf-title">다른 학습자의 덱</h3>
                <div className="shared-deck-grid">{otherDecks.map(renderDeckCard)}</div>
              </div>
            ) : null}
          </>
        ) : (
          <div className="shared-deck-grid">{sortedDecks.map(renderDeckCard)}</div>
        )
      ) : (
        <div className="empty-guide">
          <StudyCompanion mood="reading" />
          <p>가져올 수 있는 추천 덱을 살펴보세요.</p>
          <p className="muted-text">내 어휘 노트를 공유하거나 추천 덱을 가져올 수 있어요.</p>
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={onGoToVocab}
          >
            <FolderIcon className="button-icon" />
            어휘 노트로 이동
          </button>
        </div>
      )}

      {selectedDeck ? (
        <section className="shared-deck-detail">
          <div className="result-heading compact-heading">
            <div>
              <div className="shared-deck-title-row">
                <h2>{getDisplayTitle(selectedDeck, selectedLevel)}</h2>
                {selectedLevel ? <JlptLevelTag level={selectedLevel} /> : null}
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
                    : "내 노트에 가져오기"}
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
          <p className="shared-deck-description shared-deck-description-full">
            {getDeckDescription(selectedDeck.description, selectedLevel)}
          </p>
          {selectedLevel ? (
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
                      <span>{getDisplayMeaning(item.meaning_ko)}</span>
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
                  {selectedDeck.custom_terms.slice(0, 30).map((term) => {
                    const goodMeaning = getDisplayMeaning(term.meaning_ko, "");
                    return (
                      <div key={term.id} className="shared-preview-row">
                        <strong>{term.term}</strong>
                        <span>{term.reading || "-"}</span>
                        <span>
                          {goodMeaning || term.description || getDisplayMeaning(null)}
                        </span>
                      </div>
                    );
                  })}
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

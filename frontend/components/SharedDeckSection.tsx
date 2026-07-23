import { useEffect, useMemo, useState } from "react";
import {
  AppEmptyState,
  BrandDeckCover,
  BrandSectionBadge,
} from "./BrandElements";
import { ShioriMark, ShioriStamp } from "./Shiori";
import { classifyMessageTone } from "./coverageUtils";
import {
  BookIcon,
  BookshelfIcon,
  CardFileIcon,
  RotateIcon,
  SearchIcon,
  ShieldIcon,
} from "./icons";
import {
  formatDateTime,
  getDisplayMeaning,
  getJlptLevel,
  sortSharedDecksByJlptLevel,
  statusLabels,
  StatusSelect,
} from "./shared";
import type {
  SharedDeckDetail,
  SharedDeckItem,
  SharedDeckSummary,
  SharedDeckWordProgress,
  TokenStatus,
} from "./types";

// 학습 목록 카드함 필터 -- 색인 카드 카드함을 뒤지듯 검색/상태로 좁혀볼 수 있게
// (see VocabSection.tsx's identical statusFilterOptions pattern for the 노트
// tab). "전체"는 특정 상태가 아니라 필터 해제이므로 TokenStatus에 없음.
const SHARED_WORD_STATUS_FILTERS: Array<{ value: "all" | TokenStatus; label: string }> = [
  { value: "all", label: "전체" },
  { value: "unknown", label: statusLabels.unknown },
  { value: "uncertain", label: statusLabels.uncertain },
  { value: "known", label: statusLabels.known },
  { value: "unclassified", label: statusLabels.unclassified },
];

// 한 번에 렌더링하는 단어 카드 수 -- 수백~수천 단어짜리 추천 덱을 열어도
// 목록이 스프레드시트처럼 한 번에 쏟아지지 않도록 페이지 단위로 늘려간다.
const SHARED_WORD_PAGE_SIZE = 80;

// Maps one overlay-carrying SharedDeckItem (see the additive fields on that
// type) into the shape the interactive word list actually works with --
// deliberately named/typed so `lexemeId` is never confused with a personal
// VocabularyItem's `id`. Only meaningful for a "subscribed"-mode deck's
// items, which always carry these fields (see
// docs/architecture/shared-lexeme-progress-storage.md).
function toSharedDeckWordProgress(item: SharedDeckItem): SharedDeckWordProgress {
  return {
    lexemeId: item.lexeme_id ?? item.id,
    surface: item.surface || item.base_form || "",
    baseForm: item.base_form || item.surface || "",
    reading: item.reading || "",
    partOfSpeech: item.part_of_speech || "",
    meaningKo: item.meaning_ko || "",
    jlptLevel: item.jlpt_level ?? null,
    status: (item.status as TokenStatus | null) ?? "unclassified",
    reviewLevel: item.review_level ?? 0,
    nextReviewAt: item.next_review_at ?? null,
    correctCount: item.correct_count ?? 0,
    wrongCount: item.wrong_count ?? 0,
  };
}

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
  // Subscribed-deck word status (see
  // docs/architecture/shared-lexeme-progress-storage.md) -- lexeme_id of
  // whichever word is currently being updated, so its own dropdown can show
  // a saving state without disabling the whole list.
  updatingWordLexemeId: number | null;
  onRefresh: () => void;
  onSelectDeck: (deckId: number) => void;
  onCloseDetail: () => void;
  onImportDeck: (deckId: number) => void;
  onUnpublishDeck: (deckId: number) => void;
  onUpdateWordStatus: (sharedDeckId: number, lexemeId: number, status: TokenStatus) => void;
  onGoToVocab: () => void;
  onGoToStudyToday: () => void;
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
  updatingWordLexemeId,
  onRefresh,
  onSelectDeck,
  onCloseDetail,
  onImportDeck,
  onUnpublishDeck,
  onUpdateWordStatus,
  onGoToVocab,
  onGoToStudyToday,
}: SharedDeckSectionProps) {
  const sortedDecks = sortSharedDecksByJlptLevel(decks);
  const hasJlptDeck = sortedDecks.some((deck) => getJlptLevel(deck.title));
  const selectedAlreadyImported = selectedDeck
    ? Boolean(selectedDeck.imported_at) || importedDeckId === selectedDeck.id
    : false;
  const selectedLevel = selectedDeck ? getJlptLevel(selectedDeck.title) : null;

  // 학습 목록 카드함 검색/필터 -- 구독 덱 단어가 수백~수천 개여도 스크롤로만
  // 뒤지지 않도록. 다른 덱을 열거나 검색어/필터를 바꾸면 표시 개수를 다시
  // 첫 페이지로 되돌린다.
  const [wordSearchText, setWordSearchText] = useState("");
  const [wordStatusFilter, setWordStatusFilter] = useState<"all" | TokenStatus>("all");
  const [visibleWordCount, setVisibleWordCount] = useState(SHARED_WORD_PAGE_SIZE);

  useEffect(() => {
    setWordSearchText("");
    setWordStatusFilter("all");
    setVisibleWordCount(SHARED_WORD_PAGE_SIZE);
  }, [selectedDeck?.id]);

  function handleWordSearchChange(value: string) {
    setWordSearchText(value);
    setVisibleWordCount(SHARED_WORD_PAGE_SIZE);
  }

  function handleWordStatusFilterChange(value: "all" | TokenStatus) {
    setWordStatusFilter(value);
    setVisibleWordCount(SHARED_WORD_PAGE_SIZE);
  }

  const subscribedWords = useMemo(
    () =>
      selectedDeck && selectedDeck.mode === "subscribed"
        ? selectedDeck.items.map(toSharedDeckWordProgress)
        : [],
    [selectedDeck],
  );
  const filteredSubscribedWords = useMemo(() => {
    const query = wordSearchText.trim().toLowerCase();
    return subscribedWords.filter((word) => {
      if (wordStatusFilter !== "all" && word.status !== wordStatusFilter) {
        return false;
      }
      if (!query) {
        return true;
      }
      return (
        word.surface.toLowerCase().includes(query) ||
        word.baseForm.toLowerCase().includes(query) ||
        word.reading.toLowerCase().includes(query) ||
        word.meaningKo.toLowerCase().includes(query)
      );
    });
  }, [subscribedWords, wordSearchText, wordStatusFilter]);
  const visibleSubscribedWords = filteredSubscribedWords.slice(0, visibleWordCount);
  const hasMoreSubscribedWords = filteredSubscribedWords.length > visibleSubscribedWords.length;

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
    // Subscribed-mode decks (see docs/architecture/shared-lexeme-progress-storage.md)
    // never need a "다시 가져오기" re-copy confirm -- once subscribed,
    // the same button just opens the deck's word list instead.
    const isSubscribedMode = deck.mode === "subscribed";
    return (
      <article
        key={deck.id}
        className={
          isSelected
            ? "shared-deck-card selected-shared-deck-card card-stack-surface"
            : "shared-deck-card card-stack-surface"
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
                {isSubscribedMode ? "학습 목록에 있음" : "가져옴"}
                {deck.imported_at ? ` · ${formatDateTime(deck.imported_at)}` : ""}
              </span>
            ) : null}
          </div>
          <p className="shared-deck-description">
            {getDeckDescription(deck.description, level)}
          </p>
        </div>
        {/* 등록일/작성자/가져간 횟수는 카드마다 항상 보이던 메타데이터였는데,
            덱 이름/단어 수/설명/가져오기 버튼이 이 카드의 실제 주인공이라
            "상세 보기"를 열었을 때만 보이도록 옮겼다 (아래 selectedDeck
            상세 영역의 shared-deck-byline). */}
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
            onClick={() => {
              if (isSubscribedMode && alreadyImported) {
                onSelectDeck(deck.id);
                return;
              }
              handleImportClick(deck);
            }}
            disabled={isImporting}
            title={
              !isSubscribedMode && alreadyImported
                ? "이미 가져온 덱입니다. 다시 가져오면 확인 후 새로 추가됩니다."
                : undefined
            }
          >
            {isImporting ? (
              "가져오는 중..."
            ) : isSubscribedMode && alreadyImported ? (
              <>
                <BookIcon className="button-icon" />열기
              </>
            ) : alreadyImported ? (
              <>
                <RotateIcon className="button-icon" />
                다시 가져오기
              </>
            ) : isSubscribedMode ? (
              <>
                <CardFileIcon className="button-icon" />학습 목록에 추가
              </>
            ) : (
              <>
                <CardFileIcon className="button-icon" />내 노트에 가져오기
              </>
            )}
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
            <ShioriMark className="shared-deck-title-mark" />
            <BrandSectionBadge icon={BookshelfIcon} />
            덱 책장
          </h2>
          <p className="panel-card-description">
            추천 어휘 덱을 내 노트에 가져와 읽기와 복습에 사용하세요.
          </p>
        </div>
        <div className="landing-hero-actions">
          <button type="button" className="secondary-button" onClick={onGoToVocab}>
            <CardFileIcon className="button-icon" />어휘 노트 보기
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
          가져온 덱은 학습 목록에 바로 추가돼요. 원문 전체는 들어가지 않아요.
        </p>
      </section>

      {hasJlptDeck ? (
        <p className="info-strip shared-deck-disclaimer">
          <ShieldIcon className="info-strip-icon" />
          JLPT 추천 어휘 덱은 학습 참고용 비공식 목록이며, 공개 학습 자료와
          내부 사전 데이터를 바탕으로 구성했습니다.
        </p>
      ) : null}

      {message ? (
        <div className="shared-deck-message">
          <p
            className={`message message--${messageTone}${
              messageTone === "success" ? " message-stamped" : ""
            }`}
          >
            {messageTone === "success" ? (
              <ShioriStamp variant="success" className="shared-deck-message-stamp" />
            ) : null}
            <span>{message}</span>
          </p>
          <div className="shared-deck-message-actions">
            <button
              type="button"
              className="secondary-button compact-button"
              onClick={onGoToVocab}
            >
              어휘 노트 보기
            </button>
            {messageTone === "success" ? (
              <button
                type="button"
                className="ghost-button compact-button"
                onClick={onGoToStudyToday}
              >
                복습 시작
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {isInitialLoading ? (
        <AppEmptyState
          mood="loading"
          moodSize="xl"
          className="shared-deck-loading"
          title="덱 책장을 불러오는 중이에요..."
        />
      ) : sortedDecks.length > 0 ? (
        hasGroups ? (
          <>
            {recommendedDecks.length > 0 ? (
              <div className="shelf-section">
                <h3 className="shelf-section-title">
                  <BookshelfIcon className="shelf-section-icon" />
                  JLPT 추천 어휘 서가
                </h3>
                <div className="shared-deck-grid">
                  {recommendedDecks.map(renderDeckCard)}
                </div>
              </div>
            ) : null}
            {myDecks.length > 0 ? (
              <div className="shelf-section">
                <h3 className="shelf-section-title">
                  <BookshelfIcon className="shelf-section-icon" />
                  내가 공유한 덱
                </h3>
                <div className="shared-deck-grid">{myDecks.map(renderDeckCard)}</div>
              </div>
            ) : null}
            {otherDecks.length > 0 ? (
              <div className="shelf-section">
                <h3 className="shelf-section-title">
                  <BookshelfIcon className="shelf-section-icon" />
                  다른 학습자의 덱
                </h3>
                <div className="shared-deck-grid">{otherDecks.map(renderDeckCard)}</div>
              </div>
            ) : null}
          </>
        ) : (
          <div className="shared-deck-grid">{sortedDecks.map(renderDeckCard)}</div>
        )
      ) : messageTone === "error" ? (
        // Fetch genuinely failed -- shows a retry CTA instead of the
        // cheerful "둘러보세요" copy below, which would otherwise read as
        // if the deck shelf is just empty rather than unreachable.
        <AppEmptyState
          icon={BookshelfIcon}
          title="덱을 불러오지 못했어요."
          description="잠시 후 다시 시도해주세요."
        >
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={onRefresh}
            disabled={isLoading}
          >
            <RotateIcon className="button-icon" />
            {isLoading ? "다시 불러오는 중..." : "다시 불러오기"}
          </button>
        </AppEmptyState>
      ) : (
        <AppEmptyState
          mood="empty"
          moodSize="xl"
          title="가져올 수 있는 추천 덱을 살펴보세요."
          description="내 어휘 노트를 공유하거나 추천 덱을 가져올 수 있어요."
        >
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={onGoToVocab}
          >
            <CardFileIcon className="button-icon" />
            어휘 노트로 이동
          </button>
        </AppEmptyState>
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
                    {selectedDeck.mode === "subscribed" ? "학습 목록에 있음" : "가져옴"}
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
                {selectedDeck.custom_term_count}개 · 등록일{" "}
                {formatDateTime(selectedDeck.created_at)} · 가져간 횟수{" "}
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
              {selectedDeck.mode === "subscribed" && selectedAlreadyImported ? null : (
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
                      : selectedDeck.mode === "subscribed"
                        ? "학습 목록에 추가"
                        : "내 노트에 가져오기"}
                </button>
              )}
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
            <p className="info-strip shared-deck-disclaimer">
              <ShieldIcon className="info-strip-icon" />
              JLPT 추천 어휘 덱은 학습 참고용 비공식 목록이며, 공개 학습
              자료와 내부 사전 데이터를 바탕으로 구성했습니다.
            </p>
          ) : null}
          {selectedDeck.is_owner ? (
            <p className="muted-text shared-deck-owner-hint">
              공유 취소하면 공유 목록에서만 내려가며, 이미 가져간 개인 덱은
              삭제되지 않습니다.
            </p>
          ) : null}

          {selectedDeck.mode === "subscribed" ? (
            // Subscribed-mode deck: this is the real "학습 목록" (see
            // docs/architecture/shared-lexeme-progress-storage.md), not a
            // preview -- show every word, and once the user has actually
            // added the deck, let them classify each one right here. No
            // custom_terms column: lexeme-mode decks never have any (the
            // backend always returns an empty array for them).
            <div className="shared-detail-columns shared-detail-columns-single">
              <div>
                <h3>
                  학습 목록 ({selectedDeck.items.length}개)
                </h3>
                {subscribedWords.length > 0 ? (
                  <>
                    <div className="index-card-filter shared-lexeme-word-filter">
                      <span className="memo-label vocab-toolbar-label">
                        <SearchIcon className="vocab-toolbar-label-icon" />
                        카드함 필터
                      </span>
                      <div className="vocab-search-wrap">
                        <SearchIcon className="vocab-search-icon" />
                        <input
                          className="vocab-search-input"
                          value={wordSearchText}
                          onChange={(event) => handleWordSearchChange(event.target.value)}
                          placeholder="단어, 읽기, 뜻으로 검색"
                          aria-label="학습 목록 검색"
                        />
                      </div>
                      <div className="vocab-status-filters" role="group" aria-label="학습 상태 필터">
                        {SHARED_WORD_STATUS_FILTERS.map((option) => (
                          <button
                            key={option.value}
                            type="button"
                            className={`vocab-filter-chip${
                              wordStatusFilter === option.value ? " vocab-filter-chip-active" : ""
                            }`}
                            aria-pressed={wordStatusFilter === option.value}
                            onClick={() => handleWordStatusFilterChange(option.value)}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {filteredSubscribedWords.length > 0 ? (
                      <>
                        <div className="shared-preview-list shared-lexeme-word-list">
                          {visibleSubscribedWords.map((word) => (
                            <div
                              key={word.lexemeId}
                              className="shared-preview-row shared-lexeme-row"
                            >
                              <div className="shared-lexeme-row-main">
                                <strong>{word.surface || word.baseForm || "-"}</strong>
                                <span>{word.reading || "-"}</span>
                                <span>{getDisplayMeaning(word.meaningKo)}</span>
                              </div>
                              {selectedAlreadyImported ? (
                                <div className="shared-lexeme-row-status">
                                  <StatusSelect
                                    value={word.status}
                                    label={`${word.surface || word.baseForm} 학습 상태`}
                                    onChange={(status) =>
                                      onUpdateWordStatus(selectedDeck.id, word.lexemeId, status)
                                    }
                                  />
                                  {updatingWordLexemeId === word.lexemeId ? (
                                    <span className="shared-lexeme-row-saving">저장 중...</span>
                                  ) : null}
                                </div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                        <p className="muted-text shared-lexeme-word-count-caption">
                          전체 {filteredSubscribedWords.length}개 중{" "}
                          {visibleSubscribedWords.length}개 표시
                        </p>
                        {hasMoreSubscribedWords ? (
                          <button
                            type="button"
                            className="secondary-button compact-button shared-lexeme-load-more"
                            onClick={() =>
                              setVisibleWordCount((count) => count + SHARED_WORD_PAGE_SIZE)
                            }
                          >
                            더 보기 (
                            {Math.min(
                              SHARED_WORD_PAGE_SIZE,
                              filteredSubscribedWords.length - visibleSubscribedWords.length,
                            )}
                            개)
                          </button>
                        ) : null}
                      </>
                    ) : (
                      <p className="empty">검색 결과가 없어요.</p>
                    )}
                  </>
                ) : (
                  <p className="empty">공유된 단어가 없어요.</p>
                )}
              </div>
            </div>
          ) : (
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
                  <p className="empty">공유된 단어가 없어요.</p>
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
                  <p className="empty">공유된 사용자 정의 용어가 없어요.</p>
                )}
              </div>
            </div>
          )}

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

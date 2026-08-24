import { useEffect, useMemo, useState } from "react";
import { AppEmptyState } from "./BrandElements";
import { ShioriMark, ShioriStamp } from "./Shiori";
import { classifyMessageTone } from "./coverageUtils";
import {
  BookmarkIcon,
  BookshelfIcon,
  CardFileIcon,
  ChevronRightIcon,
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

// Phase 7 Round 1 added `is_published` to the API response (see
// docs/architecture/shared-lexeme-progress-storage.md -- "Owner unpublish
// policy"). Treat a missing/undefined value as published for backward
// compatibility with any response shape that predates the field.
function isDeckPublished(deck: { is_published?: boolean }): boolean {
  return deck.is_published !== false;
}

// Calm, non-alarming status pill -- an owner unpublishing their own deck (or
// a subscriber whose deck got unpublished) is a normal state change, not an
// error, so this deliberately avoids the danger-button's red tone.
function UnpublishedBadge() {
  return (
    <span className="shared-deck-status-badge shared-deck-status-badge-unpublished">
      공유 중단됨
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
  N5: "기초 문장 읽기에 자주 쓰이는 추천 어휘예요.",
  N4: "초급 원문 읽기에 도움이 되는 추천 어휘예요.",
  N3: "중급 독해로 넘어가기 위한 추천 어휘예요.",
  N2: "긴 문장과 기사 독해에 도움이 되는 추천 어휘예요.",
  N1: "고급 독해와 원서 읽기에 도움이 되는 추천 어휘예요.",
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
  // Phase 7 Round 8 (see docs/architecture/shared-lexeme-progress-storage.md
  // -- "Owner unpublish policy" republish decision): mirrors
  // unpublishingDeckId above, just for the reverse action.
  republishingDeckId: number | null;
  canManageSharedDecks: boolean;
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
  onRepublishSharedDeck?: (sharedDeckId: number) => void | Promise<void>;
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
  republishingDeckId,
  canManageSharedDecks,
  message,
  updatingWordLexemeId,
  onRefresh,
  onSelectDeck,
  onCloseDetail,
  onImportDeck,
  onUnpublishDeck,
  onRepublishSharedDeck,
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
  const selectedDeckPublished = selectedDeck ? isDeckPublished(selectedDeck) : true;

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
        `이미 가져온 공유덱이에요 (${formatDateTime(deck.imported_at)}). 다시 가져올까요?`,
      );
      if (!confirmed) {
        return;
      }
    }
    onImportDeck(deck.id);
  }

  // ---------------------------------------------------------------------
  // renderBookSpine -- Phase 158. Was renderDeckCard: an <article> laid out
  // as cover-band-then-title-then-meta-then-a-footer-of-buttons -- a real
  // card model, just with a book-flavored top strip. Discarded entirely,
  // not reskinned. A deck is now a standing .book-spine: the whole tone
  // color (JLPT ramp / 내가 공유함 / 공유 덱, the exact palette
  // getDeckCoverProps already resolved) fills the spine itself rather than
  // a thin cap band, title is the spine's own printed label (clamped, not
  // pushed below a cover image), level/unpublished/owned are small
  // stickers on the spine face, and there is at most one action -- a
  // pull-tab fixed to the spine's base -- instead of a card footer that
  // could hold up to 3 buttons. Owner-only manage actions (공유 취소/다시
  // 공유하기) are dropped from the spine entirely and now live only in the
  // opened detail panel (unchanged there) -- a real shelf book isn't
  // managed while it's still standing closed on the shelf, you pull it out
  // first, which is exactly what clicking the spine's face already does.
  // ---------------------------------------------------------------------
  function renderBookSpine(deck: SharedDeckSummary) {
    const isSelected = selectedDeckId === deck.id;
    const isImporting = importingDeckId === deck.id;
    const isImported = importedDeckId === deck.id;
    const level = getJlptLevel(deck.title);
    const totalWordCount = deck.vocab_count + deck.custom_term_count;
    const alreadyImported = Boolean(deck.imported_at) || isImported;
    // Subscribed-mode decks (see docs/architecture/shared-lexeme-progress-storage.md)
    // never need a "다시 가져오기" re-copy confirm -- once subscribed,
    // the same button just opens the deck's word list instead.
    const isSubscribedMode = deck.mode === "subscribed";
    const published = isDeckPublished(deck);
    // Once unpublished, the only reason this button should still appear is
    // to let an already-subscribed user open their own word list -- never
    // as a new-import CTA (see docs/architecture/shared-lexeme-progress-storage.md
    // "Owner unpublish policy" Round 2 update).
    const showActionButton =
      !deck.is_owner && (published || (isSubscribedMode && alreadyImported));
    // Phase 107 -- once a subscribed-mode deck is already in the user's
    // 학습 목록, the spine's face and the pull-tab below would both end up
    // calling the exact same onSelectDeck(deck.id) (see the 열기 branch
    // below), which itself already toggles open/closed via
    // loadSharedDeckDetail's "select the same id again -> close" logic (see
    // docs/design/DESIGN.md Phase 107). Two controls doing the identical
    // thing read as a real duplicate, not just visual clutter, so the
    // pull-tab is suppressed in this one state -- the spine face alone
    // still opens/closes the same detail panel. Every other state (owner,
    // newcomer, non-subscribed-mode) keeps both.
    const hasDuplicateOpenAction =
      !deck.is_owner && isSubscribedMode && alreadyImported;
    const { tone } = getDeckCoverProps(deck, level);
    const toneClass = level
      ? `jlpt-level-${level.toLowerCase()}`
      : `book-spine-tone-${tone}`;

    return (
      <div
        key={deck.id}
        className={`book-spine ${toneClass}${isSelected ? " book-spine-selected" : ""}`}
      >
        <button
          type="button"
          className="book-spine-face"
          onClick={() => onSelectDeck(deck.id)}
          disabled={isLoadingDetail && isSelected}
          aria-expanded={isSelected}
          title={getDisplayTitle(deck, level)}
        >
          <span className="book-spine-stickers">
            {level ? <span className="book-spine-sticker">{level}</span> : null}
            {!published ? (
              <span className="book-spine-sticker book-spine-sticker-muted">중단</span>
            ) : null}
          </span>
          <span className="book-spine-label">{getDisplayTitle(deck, level)}</span>
          <span className="book-spine-face-footer">
            <span className="book-spine-count">{totalWordCount}개</span>
            {alreadyImported ? (
              <span
                className="book-spine-owned-mark"
                aria-hidden="true"
                title={
                  deck.imported_at
                    ? `가져온 날짜: ${formatDateTime(deck.imported_at)}`
                    : "학습 목록에 있음"
                }
              />
            ) : null}
            <ChevronRightIcon
              className={`book-spine-face-chevron${isSelected ? " book-spine-face-chevron-open" : ""}`}
            />
          </span>
        </button>
        {showActionButton && !hasDuplicateOpenAction ? (
          <button
            type="button"
            className="book-spine-pulltab"
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
                ? "이미 가져온 덱이에요. 다시 가져오면 확인 후 새로 추가돼요."
                : undefined
            }
          >
            {isImporting ? (
              <span>가져오는 중</span>
            ) : isSubscribedMode && alreadyImported ? (
              <>
                <BookmarkIcon className="book-spine-pulltab-icon" />
                <span>열기</span>
              </>
            ) : alreadyImported ? (
              <>
                <RotateIcon className="book-spine-pulltab-icon" />
                <span>다시 가져오기</span>
              </>
            ) : isSubscribedMode ? (
              <>
                <CardFileIcon className="book-spine-pulltab-icon" />
                <span>학습 목록 추가</span>
              </>
            ) : (
              <>
                <CardFileIcon className="book-spine-pulltab-icon" />
                <span>내 노트에 담기</span>
              </>
            )}
          </button>
        ) : null}
      </div>
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

  const hasDecks = sortedDecks.length > 0;

  return (
    <section className="tab-panel shared-deck-section" aria-live="polite">
      <span className="shared-scene-v2-eyebrow">
        <ShioriMark variant="default" />
        덱 책장
      </span>

      {/* Phase 170 -- one full-bleed V2 bookshelf photo is the scene anchor
          (a different shot per breakpoint, not one crop of the other). The
          photo's own painted spines are never mapped 1:1 to real decks --
          real decks render as live .book-spine elements (Phase 158's
          object, unchanged) in a horizontally-scrolling row pinned over the
          photo's own shelf board; whatever width real decks don't fill just
          shows the photo's own densely-stocked shelf underneath, which is
          exactly why a handful of decks still reads as "a real shelf with
          room on it" instead of bare web space (this phase's own
          requirement) without any conditional filler markup. */}
      <div className="shared-scene-v2">
        <div className="shared-scene-v2-frame">
          <picture className="shared-scene-v2-media">
            <source
              media="(min-width: 1024px)"
              srcSet="/brand/decor/v2/v2-shared-bookshelf-desktop-16x9.webp"
            />
            <img
              className="shared-scene-v2-media-img"
              src="/brand/decor/v2/v2-shared-bookshelf-mobile-9x16.webp"
              alt=""
              draggable={false}
            />
          </picture>

          {/* Small index tabs clipped to the shelf frame's own top-right
              corner -- Phase 152's existing notch-tag shape
              (.shared-deck-tab-action), just moved off a dedicated header
              row and onto the scene itself so it reads as part of the
              shelf furniture, not a toolbar sitting above it. */}
          <div className="shared-scene-v2-actions">
            <button type="button" className="shared-deck-tab-action" onClick={onGoToVocab}>
              <CardFileIcon className="button-icon" />
              어휘 노트
            </button>
            <button
              type="button"
              className="shared-deck-tab-action shared-deck-tab-action-ghost"
              onClick={onRefresh}
              disabled={isLoading}
            >
              <RotateIcon className="button-icon" />
              {isLoading ? "..." : "새로고침"}
            </button>
          </div>

          {hasDecks ? (
            <div className="shared-shelf-band">
              <div className="book-shelf-row">
                {hasGroups ? (
                  <>
                    {recommendedDecks.map(renderBookSpine)}
                    {myDecks.length > 0 ? (
                      <span className="shared-shelf-divider" aria-hidden="true">
                        내가 공유함
                      </span>
                    ) : null}
                    {myDecks.map(renderBookSpine)}
                    {otherDecks.length > 0 ? (
                      <span className="shared-shelf-divider" aria-hidden="true">
                        다른 학습자
                      </span>
                    ) : null}
                    {otherDecks.map(renderBookSpine)}
                  </>
                ) : (
                  sortedDecks.map(renderBookSpine)
                )}
              </div>
            </div>
          ) : null}

          <p className="shared-scene-v2-privacy">
            <ShieldIcon className="shared-scene-v2-privacy-icon" />
            가져온 덱은 학습 목록에 바로 추가돼요. 원문 전체는 들어가지 않아요.
          </p>
        </div>
      </div>

      {isInitialLoading ? (
        <AppEmptyState
          mood="loading"
          moodSize="md"
          className="shared-deck-loading"
          title="덱 책장을 불러오는 중이에요..."
        />
      ) : !hasDecks ? (
        messageTone === "error" ? (
          // Fetch genuinely failed -- shows a retry CTA instead of the
          // cheerful "둘러보세요" copy below, which would otherwise read as
          // if the deck shelf is just empty rather than unreachable.
          <AppEmptyState
            mood="empty"
            moodSize="md"
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
            moodSize="md"
            title="가져올 수 있는 추천 덱을 살펴보세요."
            description="내 어휘 노트를 공유하거나 추천 덱을 가져올 수 있어요."
          >
            <button type="button" className="ghost-button compact-button" onClick={onGoToVocab}>
              <CardFileIcon className="button-icon" />
              어휘 노트로 이동
            </button>
          </AppEmptyState>
        )
      ) : null}

      {hasJlptDeck ? (
        <p className="info-strip info-strip-quiet shared-deck-disclaimer">
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
          {messageTone === "success" ? (
            <div className="shared-deck-message-actions">
              {importedDeckId ? (
                <button
                  type="button"
                  className="secondary-button compact-button"
                  onClick={() => onSelectDeck(importedDeckId)}
                >
                  학습 목록 보기
                </button>
              ) : null}
              <button
                type="button"
                className="ghost-button compact-button"
                onClick={onGoToStudyToday}
              >
                복습 시작
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {selectedDeck ? (
        <section className="shared-deck-detail app-slide-up" key={selectedDeck.id}>
          <span className="shared-deck-detail-tape" aria-hidden="true" />
          <div className="result-heading compact-heading">
            <div>
              <div className="shared-deck-title-row">
                <h2>{getDisplayTitle(selectedDeck, selectedLevel)}</h2>
                {selectedLevel ? <JlptLevelTag level={selectedLevel} /> : null}
                {!selectedDeckPublished ? <UnpublishedBadge /> : null}
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
                className="shared-deck-detail-dismiss"
                onClick={onCloseDetail}
              >
                닫기
              </button>
              {selectedDeck.is_owner ||
              (selectedDeck.mode === "subscribed" && selectedAlreadyImported) ||
              !selectedDeckPublished ? null : (
                <button
                  type="button"
                  className={
                    selectedAlreadyImported
                      ? "secondary-button shared-deck-checkout-tag"
                      : "shared-deck-checkout-tag"
                  }
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
              {canManageSharedDecks && selectedDeck.is_owner && selectedDeckPublished ? (
                <button
                  type="button"
                  className="danger-secondary-button shared-deck-manage-tag"
                  onClick={() => onUnpublishDeck(selectedDeck.id)}
                  disabled={unpublishingDeckId === selectedDeck.id}
                >
                  {unpublishingDeckId === selectedDeck.id
                    ? "공유 취소 중..."
                    : "공유 취소"}
                </button>
              ) : null}
              {canManageSharedDecks && selectedDeck.is_owner && !selectedDeckPublished ? (
                <button
                  type="button"
                  className="secondary-button shared-deck-manage-tag"
                  onClick={() => onRepublishSharedDeck?.(selectedDeck.id)}
                  disabled={republishingDeckId === selectedDeck.id}
                >
                  {republishingDeckId === selectedDeck.id
                    ? "다시 공유하는 중..."
                    : "다시 공유하기"}
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
          {canManageSharedDecks && selectedDeck.is_owner ? (
            <p className="muted-text shared-deck-owner-hint">
              {selectedDeckPublished
                ? "공유를 중단하면 새 사용자는 더 이상 이 덱을 가져올 수 없어요. 이미 학습 중인 사용자는 복습을 계속 이어갈 수 있고, 이 덱은 내 책장에서도 계속 볼 수 있어요."
                : "이 덱은 더 이상 공유 목록에 보이지 않지만, 이미 학습 중인 사용자는 복습을 이어갈 수 있어요."}
            </p>
          ) : !selectedDeckPublished ? (
            <p className="muted-text shared-deck-subscriber-hint">
              새 사용자는 더 이상 가져올 수 없지만, 내 복습은 계속 이어져요.
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

          {/* Phase 158 -- Phase 157's audit flagged this as a literal
              duplicate of the top-right "닫기" link (same handler, same
              label, same action). Rather than drop it outright -- a long
              subscribed word list can run to hundreds of rows, and losing
              the only reachable-without-scrolling-up close control would
              be a real usability regression, not a cleanup -- it's
              recopied as "책장으로 돌아가기" (same onCloseDetail handler,
              unchanged), so it reads as this book's own closing action
              (put it back on the shelf) rather than an identical second
              copy of the header's quick dismiss. */}
          <div className="form-actions">
            <button
              type="button"
              className="secondary-button book-return-to-shelf-button"
              onClick={onCloseDetail}
            >
              <BookshelfIcon className="button-icon" />
              책장으로 돌아가기
            </button>
          </div>
        </section>
      ) : null}
    </section>
  );
}

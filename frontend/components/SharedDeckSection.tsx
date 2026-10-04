import {
  useDeferredValue,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ShioriStamp } from "./Shiori";
import { classifyMessageTone } from "./coverageUtils";
import { ChevronRightIcon, RotateIcon, SearchIcon } from "./icons";
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

// 학습 목록 카드함 필터 -- 구독 덱 단어를 검색/상태로 좁혀볼 수 있게
// (see VocabSection.tsx's statusFilterOptions pattern). "전체"는 특정 상태가
// 아니라 필터 해제이므로 TokenStatus에 없음.
const SHARED_WORD_STATUS_FILTERS: Array<{ value: "all" | TokenStatus; label: string }> = [
  { value: "all", label: "전체" },
  { value: "unknown", label: statusLabels.unknown },
  { value: "uncertain", label: statusLabels.uncertain },
  { value: "known", label: statusLabels.known },
  { value: "unclassified", label: statusLabels.unclassified },
];

// 한 번에 렌더링하는 단어 수 -- 수백~수천 단어짜리 추천 덱을 열어도
// 목록이 한 번에 쏟아지지 않도록 페이지 단위로 늘려간다.
const SHARED_WORD_PAGE_SIZE = 80;

const JLPT_DISCLAIMER =
  "JLPT 추천 어휘 덱은 학습 참고용 비공식 목록이며, 공개 학습 자료와 내부 사전 데이터를 바탕으로 구성했습니다.";

// Deck C register (references/mockups/deck-scale-catalog/handoff). The
// source filter is a display-only partition of the already-fetched list by
// fields the API already returns -- the same three groups the old shelf
// used -- so every deck lands in exactly one source.
type DeckSource = "recommended" | "mine" | "community";
type DeckSourceFilter = "all" | DeckSource;
type DeckSort = "default" | "words" | "imports" | "recent";

const DECK_SOURCE_LABELS: Record<DeckSource, string> = {
  recommended: "추천",
  mine: "내가 공유함",
  community: "다른 학습자",
};

const DECK_SORT_OPTIONS: Array<{ value: DeckSort; label: string }> = [
  { value: "default", label: "기본 순" },
  { value: "words", label: "많이 담은 순" },
  { value: "imports", label: "많이 가져간 순" },
  { value: "recent", label: "최근 공유 순" },
];

// GET /shared-decks returns the whole visible list (no paging yet). Rows
// are one line and the same height, so only the rows in view plus this many
// on each side are in the DOM; spacing above/below stands in for the rest.
const DECK_ROW_OVERSCAN = 8;
const DECK_ROW_FALLBACK_HEIGHT = 58;

const IMPORT_SUCCESS_PATTERN = /(학습 목록에 추가했어요|어휘 노트에 가져왔어요)/;

// Below this width the register shows one page at a time (list -> detail
// -> back). Kept in sync with the deck-ledger media queries in globals.css.
const SINGLE_PAGE_QUERY = "(max-width: 1023px)";

function getDeckSource(deck: SharedDeckSummary): DeckSource {
  if (getJlptLevel(deck.title)) {
    return "recommended";
  }
  return deck.is_owner ? "mine" : "community";
}

function getTotalWordCount(deck: SharedDeckSummary) {
  return deck.vocab_count + deck.custom_term_count;
}

function formatIndex(index: number) {
  return String(index + 1).padStart(2, "0");
}

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

// Phase 7 Round 1 added `is_published` to the API response (see
// docs/architecture/shared-lexeme-progress-storage.md -- "Owner unpublish
// policy"). Treat a missing/undefined value as published for backward
// compatibility with any response shape that predates the field.
function isDeckPublished(deck: { is_published?: boolean }): boolean {
  return deck.is_published !== false;
}

// UI-only display label -- the underlying deck.title in the DB may still be
// the older "N5어휘모음" form (see getJlptLevel's pattern); this only
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
// description in the DB still reads as a finished page instead of showing
// "설명이 없습니다."
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
  // ---------------------------------------------------------------------
  // Register list: search, source filter and sort over the list the API
  // already returned (GET /shared-decks has no query/sort/page params).
  // These live in this component, so opening a deck and coming back on a
  // phone keeps them; the list's own scrollTop is saved on open and put
  // back on Back (see the layout effect below).
  // ---------------------------------------------------------------------
  const [deckQuery, setDeckQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<DeckSourceFilter>("all");
  const [deckSort, setDeckSort] = useState<DeckSort>("default");
  const listRef = useRef<HTMLDivElement | null>(null);
  const backButtonRef = useRef<HTMLButtonElement | null>(null);
  const savedListScrollRef = useRef(0);
  const lastOpenedDeckIdRef = useRef<number | null>(null);
  const previousSelectedIdRef = useRef<number | null>(selectedDeckId);
  const scrollFrameRef = useRef(0);
  const pendingRowFocusRef = useRef<{ index: number; scrollTop: number } | null>(null);
  const [rowHeight, setRowHeight] = useState(DECK_ROW_FALLBACK_HEIGHT);
  const [listViewport, setListViewport] = useState({ top: 0, height: 0 });
  // Typing stays responsive on long lists; filtering follows a beat later.
  const deferredQuery = useDeferredValue(deckQuery);

  const baseSortedDecks = useMemo(() => sortSharedDecksByJlptLevel(decks), [decks]);
  // Lowercased search text and parsed dates, computed once per fetch rather
  // than on every keystroke/comparison.
  const deckIndex = useMemo(() => {
    const index = new Map<number, { text: string; createdAt: number }>();
    for (const deck of decks) {
      const level = getJlptLevel(deck.title);
      index.set(deck.id, {
        text: [getDisplayTitle(deck, level), deck.title, deck.owner_display_name, deck.description]
          .filter(Boolean)
          .join(" | ")
          .toLowerCase(),
        createdAt: Date.parse(deck.created_at) || 0,
      });
    }
    return index;
  }, [decks]);
  const hasJlptDeck = baseSortedDecks.some((deck) => getJlptLevel(deck.title));

  const sourceCounts = useMemo(() => {
    const counts: Record<DeckSource, number> = { recommended: 0, mine: 0, community: 0 };
    for (const deck of decks) {
      counts[getDeckSource(deck)] += 1;
    }
    return counts;
  }, [decks]);

  const visibleDecks = useMemo(() => {
    const query = deferredQuery.trim().toLowerCase();
    const matched = baseSortedDecks.filter((deck) => {
      if (sourceFilter !== "all" && getDeckSource(deck) !== sourceFilter) {
        return false;
      }
      return !query || Boolean(deckIndex.get(deck.id)?.text.includes(query));
    });
    if (deckSort === "default") {
      return matched;
    }
    return [...matched].sort((a, b) => {
      if (deckSort === "words") {
        return getTotalWordCount(b) - getTotalWordCount(a);
      }
      if (deckSort === "imports") {
        return b.import_count - a.import_count;
      }
      return (deckIndex.get(b.id)?.createdAt ?? 0) - (deckIndex.get(a.id)?.createdAt ?? 0);
    });
  }, [baseSortedDecks, deckIndex, deferredQuery, sourceFilter, deckSort]);

  // The list window follows the list's own scroll position and height. A
  // hidden list (phone detail page) reports 0 and keeps its last window, so
  // Back finds the opened row already rendered.
  function syncListViewport() {
    const list = listRef.current;
    if (!list || list.clientHeight === 0) {
      return;
    }
    const top = list.scrollTop;
    const height = list.clientHeight;
    setListViewport((current) =>
      current.top === top && current.height === height ? current : { top, height },
    );
  }

  function handleListScroll() {
    if (scrollFrameRef.current) {
      return;
    }
    scrollFrameRef.current = window.requestAnimationFrame(() => {
      scrollFrameRef.current = 0;
      syncListViewport();
    });
  }

  useEffect(() => {
    const list = listRef.current;
    if (!list) {
      return;
    }
    syncListViewport();
    const observer = new ResizeObserver(() => syncListViewport());
    observer.observe(list);
    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(scrollFrameRef.current);
      scrollFrameRef.current = 0;
    };
  }, []);

  // Row height differs by breakpoint; read it from a rendered row.
  useLayoutEffect(() => {
    const row = listRef.current?.querySelector<HTMLElement>(".deck-ledger-row-item");
    if (row && row.offsetHeight > 0 && row.offsetHeight !== rowHeight) {
      setRowHeight(row.offsetHeight);
    }
    // Keyboard row moves: scroll only once the target's window is in the
    // DOM, then focus it. Scrolling first (while the old window was still
    // rendered) let the browser re-adjust scrollTop as rows were swapped.
    const pending = pendingRowFocusRef.current;
    const list = listRef.current;
    if (pending !== null && list) {
      const target = list.querySelector<HTMLButtonElement>(
        `[data-row-index="${pending.index}"]`,
      );
      if (target) {
        pendingRowFocusRef.current = null;
        list.scrollTop = pending.scrollTop;
        target.focus({ preventScroll: true });
      }
    }
  });

  // A new query/filter/sort starts the list from its first row again.
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = 0;
    }
    syncListViewport();
  }, [deferredQuery, sourceFilter, deckSort]);

  const viewportHeight = listViewport.height || rowHeight * 12;
  const firstRowIndex = Math.max(
    0,
    Math.floor(listViewport.top / rowHeight) - DECK_ROW_OVERSCAN,
  );
  const endRowIndex = Math.min(
    visibleDecks.length,
    Math.ceil((listViewport.top + viewportHeight) / rowHeight) + DECK_ROW_OVERSCAN,
  );
  const windowedDecks = visibleDecks.slice(firstRowIndex, endRowIndex);

  // Arrow/Page/Home/End move between rows even when the next row is not
  // rendered yet: scroll it into the window, then focus it after render.
  function handleRowKeyDown(event: React.KeyboardEvent<HTMLOListElement>) {
    const current = (event.target as HTMLElement).closest<HTMLElement>("[data-row-index]");
    const list = listRef.current;
    if (!current || !list || visibleDecks.length === 0) {
      return;
    }
    const index = Number(current.dataset.rowIndex);
    const pageRows = Math.max(1, Math.floor(list.clientHeight / rowHeight) - 1);
    const targets: Record<string, number> = {
      ArrowDown: index + 1,
      ArrowUp: index - 1,
      PageDown: index + pageRows,
      PageUp: index - pageRows,
      Home: 0,
      End: visibleDecks.length - 1,
    };
    if (!(event.key in targets)) {
      return;
    }
    event.preventDefault();
    const target = Math.min(visibleDecks.length - 1, Math.max(0, targets[event.key]));
    const rowTop = target * rowHeight;
    let nextTop = list.scrollTop;
    if (rowTop < nextTop) {
      nextTop = rowTop;
    } else if (rowTop + rowHeight > nextTop + list.clientHeight) {
      nextTop = rowTop + rowHeight - list.clientHeight;
    }
    const rendered = list.querySelector<HTMLButtonElement>(`[data-row-index="${target}"]`);
    if (rendered && nextTop === list.scrollTop) {
      rendered.focus({ preventScroll: true });
      return;
    }
    pendingRowFocusRef.current = { index: target, scrollTop: nextTop };
    const height = list.clientHeight;
    setListViewport({ top: nextTop, height });
  }

  const hasFilters = deckQuery.trim() !== "" || sourceFilter !== "all";
  const selectedIndex =
    selectedDeckId === null ? -1 : visibleDecks.findIndex((deck) => deck.id === selectedDeckId);

  // Back on a phone/tablet: restore the list's exact scroll position and
  // return focus to the row that was opened. Desktop never hides the list,
  // so there is nothing to restore there.
  useLayoutEffect(() => {
    const previous = previousSelectedIdRef.current;
    previousSelectedIdRef.current = selectedDeckId;
    const isSinglePage =
      typeof window !== "undefined" && window.matchMedia(SINGLE_PAGE_QUERY).matches;
    if (!isSinglePage) {
      return;
    }
    if (previous !== null && selectedDeckId === null && listRef.current) {
      listRef.current.scrollTop = savedListScrollRef.current;
      const openedId = lastOpenedDeckIdRef.current;
      if (openedId !== null) {
        listRef.current
          .querySelector<HTMLButtonElement>(`[data-deck-id="${openedId}"]`)
          ?.focus({ preventScroll: true });
      }
    } else if (previous === null && selectedDeckId !== null) {
      backButtonRef.current?.focus({ preventScroll: true });
    }
  }, [selectedDeckId]);

  function handleOpenDeck(deckId: number) {
    // The page-level handler toggles closed when the open deck is chosen
    // again; in a register where the detail page is always beside the list
    // that would read as the page going blank, so an already-open row is
    // left as is.
    if (deckId === selectedDeckId && (selectedDeck || isLoadingDetail)) {
      return;
    }
    savedListScrollRef.current = listRef.current?.scrollTop ?? 0;
    lastOpenedDeckIdRef.current = deckId;
    onSelectDeck(deckId);
  }

  function clearDeckFilters() {
    setDeckQuery("");
    setSourceFilter("all");
  }

  // ---------------------------------------------------------------------
  // Selected deck page
  // ---------------------------------------------------------------------
  const selectedAlreadyImported = selectedDeck
    ? Boolean(selectedDeck.imported_at) || importedDeckId === selectedDeck.id
    : false;
  const selectedLevel = selectedDeck ? getJlptLevel(selectedDeck.title) : null;
  const selectedDeckPublished = selectedDeck ? isDeckPublished(selectedDeck) : true;

  // 학습 목록 검색/필터 -- 다른 덱을 열거나 검색어/필터를 바꾸면 표시
  // 개수를 다시 첫 페이지로 되돌린다.
  const [wordSearchText, setWordSearchText] = useState("");
  const [wordStatusFilter, setWordStatusFilter] = useState<"all" | TokenStatus>("all");
  const [visibleWordCount, setVisibleWordCount] = useState(SHARED_WORD_PAGE_SIZE);
  // Imported word list: one Tab stop (roving tabindex) -- the active row is
  // the only tabbable item, rows move with arrows, and each row's status
  // select is entered with Enter/Space instead of being its own Tab stop.
  const [activeWordIndex, setActiveWordIndex] = useState(0);
  const wordListRef = useRef<HTMLUListElement | null>(null);
  // Row index whose select just changed. Under a status filter the word can
  // leave the list with its focused select; focus then lands on the row now
  // at that position instead of falling back to the page.
  const pendingWordFocusRef = useRef<number | null>(null);
  const detailBodyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setWordSearchText("");
    setWordStatusFilter("all");
    setVisibleWordCount(SHARED_WORD_PAGE_SIZE);
    setActiveWordIndex(0);
    if (detailBodyRef.current) {
      detailBodyRef.current.scrollTop = 0;
    }
  }, [selectedDeck?.id]);

  function handleWordSearchChange(value: string) {
    setWordSearchText(value);
    setVisibleWordCount(SHARED_WORD_PAGE_SIZE);
    setActiveWordIndex(0);
  }

  function handleWordStatusFilterChange(value: "all" | TokenStatus) {
    setWordStatusFilter(value);
    setVisibleWordCount(SHARED_WORD_PAGE_SIZE);
    setActiveWordIndex(0);
  }

  useLayoutEffect(() => {
    const pending = pendingWordFocusRef.current;
    if (pending === null) {
      return;
    }
    // One shot: whatever happens below, this change is settled.
    pendingWordFocusRef.current = null;
    const active = document.activeElement;
    // Focus is still somewhere real (the select that kept its word, or a
    // control the user already moved to): leave it there.
    if (active && active !== document.body) {
      return;
    }
    const count = visibleSubscribedWords.length;
    if (count > 0) {
      focusWordRow(Math.min(pending, count - 1));
      return;
    }
    // The filter now matches nothing: return to the status filter that is
    // in effect, the control the user would act on next.
    document
      .querySelector<HTMLButtonElement>('.deck-ledger-word-filters button[aria-pressed="true"]')
      ?.focus();
  });

  function focusWordRow(index: number) {
    const row = wordListRef.current?.querySelector<HTMLLIElement>(`[data-word-index="${index}"]`);
    if (row) {
      setActiveWordIndex(index);
      row.focus();
      row.scrollIntoView({ block: "nearest" });
    }
  }

  // Rows: ↑↓/Home/End move, Enter/Space enter the row's status select.
  // Select: its own arrow keys/changes are untouched; Escape returns to the
  // row. Tab is never handled, so it leaves the list (other rows and every
  // select are tabIndex -1).
  function handleWordListKeyDown(event: React.KeyboardEvent<HTMLUListElement>) {
    const target = event.target as HTMLElement;
    const row = target.closest<HTMLLIElement>("[data-word-index]");
    if (!row) {
      return;
    }
    const index = Number(row.dataset.wordIndex);
    if (target.tagName === "SELECT") {
      if (event.key === "Escape") {
        event.preventDefault();
        focusWordRow(index);
      }
      return;
    }
    if (target !== row) {
      return;
    }
    const lastIndex = visibleSubscribedWords.length - 1;
    const moves: Record<string, number> = {
      ArrowDown: Math.min(lastIndex, index + 1),
      ArrowUp: Math.max(0, index - 1),
      Home: 0,
      End: lastIndex,
    };
    if (event.key in moves) {
      event.preventDefault();
      focusWordRow(moves[event.key]);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      row.querySelector<HTMLSelectElement>("select")?.focus();
    }
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

  // page.tsx writes the import results in the polite "-어요" form, which the
  // shared classifier (tuned for "-습니다") reads as plain info -- so the
  // stamp and the 학습 목록 보기/복습 시작 links never appeared.
  const isImportSuccess = IMPORT_SUCCESS_PATTERN.test(message);
  const messageTone = isImportSuccess ? "success" : classifyMessageTone(message);
  const isInitialLoading = isLoading && decks.length === 0;
  const hasDecks = decks.length > 0;
  const isDetailOpen = selectedDeckId !== null;

  function renderDeckRow(deck: SharedDeckSummary, index: number) {
    const isSelected = selectedDeckId === deck.id;
    const level = getJlptLevel(deck.title);
    const title = getDisplayTitle(deck, level);
    const alreadyImported = Boolean(deck.imported_at) || importedDeckId === deck.id;
    const published = isDeckPublished(deck);
    const source = getDeckSource(deck);

    return (
      <li
        key={deck.id}
        className="deck-ledger-row-item"
        aria-posinset={index + 1}
        aria-setsize={visibleDecks.length}
      >
        <button
          type="button"
          className={`deck-ledger-row${isSelected ? " is-selected" : ""}`}
          data-deck-id={deck.id}
          data-row-index={index}
          aria-current={isSelected ? "true" : undefined}
          onClick={() => handleOpenDeck(deck.id)}
          title={title}
        >
          <span className="deck-ledger-row-no">{formatIndex(index)}</span>
          <span className="deck-ledger-row-main">
            <strong>{title}</strong>
            <small>
              {deck.owner_display_name || "공유자 미표시"}
              {level ? ` · ${level}` : ""}
              {!published ? (
                <em className="deck-ledger-row-paused">공유 중단</em>
              ) : null}
            </small>
          </span>
          <span className="deck-ledger-row-source">{DECK_SOURCE_LABELS[source]}</span>
          <span className="deck-ledger-row-count">{getTotalWordCount(deck)}개</span>
          <span
            className="deck-ledger-row-mark"
            title={
              alreadyImported && deck.imported_at
                ? `가져온 날짜: ${formatDateTime(deck.imported_at)}`
                : undefined
            }
          >
            {alreadyImported ? "담음" : ""}
          </span>
          <ChevronRightIcon className="deck-ledger-row-chevron" />
        </button>
      </li>
    );
  }

  function renderListBody() {
    if (isInitialLoading) {
      return <p className="deck-ledger-empty">덱 책장을 불러오는 중이에요...</p>;
    }
    if (!hasDecks) {
      if (messageTone === "error") {
        // Fetch genuinely failed -- a retry instead of the "둘러보세요"
        // copy, which would read as an empty shelf rather than an
        // unreachable one.
        return (
          <div className="deck-ledger-empty">
            <strong>덱을 불러오지 못했어요.</strong>
            <span>잠시 후 다시 시도해주세요.</span>
            <button
              type="button"
              className="deck-ledger-link"
              onClick={onRefresh}
              disabled={isLoading}
            >
              {isLoading ? "다시 불러오는 중..." : "다시 불러오기"}
            </button>
          </div>
        );
      }
      return (
        <div className="deck-ledger-empty">
          <strong>아직 펼쳐 볼 공유 덱이 없어요.</strong>
          <span>내 어휘 노트를 공유하거나 추천 덱을 가져올 수 있어요.</span>
          <button type="button" className="deck-ledger-link" onClick={onGoToVocab}>
            어휘 노트로 이동
          </button>
        </div>
      );
    }
    if (visibleDecks.length === 0) {
      return (
        <div className="deck-ledger-empty">
          <strong>조건에 맞는 덱이 없어요.</strong>
          <span>검색어나 분류를 바꿔 보세요.</span>
          <button type="button" className="deck-ledger-link" onClick={clearDeckFilters}>
            조건 지우기
          </button>
        </div>
      );
    }
    return (
      <>
        <ol
          className="deck-ledger-rows"
          style={{
            paddingTop: firstRowIndex * rowHeight,
            paddingBottom: (visibleDecks.length - endRowIndex) * rowHeight,
          }}
          onKeyDown={handleRowKeyDown}
        >
          {windowedDecks.map((deck, offset) => renderDeckRow(deck, firstRowIndex + offset))}
        </ol>
        {hasJlptDeck ? <p className="deck-ledger-list-note">{JLPT_DISCLAIMER}</p> : null}
      </>
    );
  }

  function renderPrimaryAction(deck: SharedDeckDetail) {
    const isImporting = importingDeckId === deck.id;
    if (deck.is_owner) {
      if (!canManageSharedDecks) {
        return null;
      }
      return isDeckPublished(deck) ? (
        <button
          type="button"
          className="deck-ledger-action deck-ledger-action-quiet"
          onClick={() => onUnpublishDeck(deck.id)}
          disabled={unpublishingDeckId === deck.id}
        >
          {unpublishingDeckId === deck.id ? "공유 취소 중..." : "공유 취소"}
        </button>
      ) : (
        <button
          type="button"
          className="deck-ledger-action deck-ledger-action-secondary"
          onClick={() => onRepublishSharedDeck?.(deck.id)}
          disabled={republishingDeckId === deck.id}
        >
          {republishingDeckId === deck.id ? "다시 공유하는 중..." : "다시 공유하기"}
        </button>
      );
    }
    if ((deck.mode === "subscribed" && selectedAlreadyImported) || !isDeckPublished(deck)) {
      return null;
    }
    return (
      <button
        type="button"
        className={`deck-ledger-action${selectedAlreadyImported ? " deck-ledger-action-secondary" : ""}`}
        onClick={() => handleImportClick(deck)}
        disabled={isImporting}
        title={
          deck.mode !== "subscribed" && selectedAlreadyImported
            ? "이미 가져온 덱이에요. 다시 가져오면 확인 후 새로 추가돼요."
            : undefined
        }
      >
        {isImporting
          ? "가져오는 중..."
          : selectedAlreadyImported
            ? "다시 가져오기"
            : deck.mode === "subscribed"
              ? "학습 목록에 추가"
              : "내 노트에 가져오기"}
      </button>
    );
  }

  function renderWordSection(deck: SharedDeckDetail) {
    if (deck.mode === "subscribed") {
      // Subscribed-mode deck: this is the real "학습 목록" (see
      // docs/architecture/shared-lexeme-progress-storage.md), not a
      // preview -- show every word, and once the user has actually added
      // the deck, let them classify each one right here.
      return (
        <section className="deck-ledger-words" aria-label="학습 목록">
          <div className="deck-ledger-words-head">
            <span>학습 목록</span>
            <span>{deck.items.length}개</span>
          </div>
          {subscribedWords.length > 0 ? (
            <>
              <div className="deck-ledger-word-tools">
                <label className="deck-ledger-word-search">
                  <SearchIcon className="deck-ledger-search-icon" />
                  <input
                    value={wordSearchText}
                    onChange={(event) => handleWordSearchChange(event.target.value)}
                    placeholder="단어, 읽기, 뜻으로 검색"
                    aria-label="학습 목록 검색"
                  />
                </label>
                <div className="deck-ledger-word-filters" role="group" aria-label="학습 상태 필터">
                  {SHARED_WORD_STATUS_FILTERS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={wordStatusFilter === option.value ? "is-active" : undefined}
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
                  {selectedAlreadyImported ? (
                    <p id="deck-ledger-word-keys" className="deck-ledger-sr">
                      위아래 화살표로 단어를 옮기고, Enter나 Space로 상태를 바꿔요. Escape는
                      단어로 돌아오고, Tab은 목록을 나가요.
                    </p>
                  ) : null}
                  <ul
                    className="deck-ledger-word-list"
                    ref={wordListRef}
                    aria-label={`학습 목록 단어 ${filteredSubscribedWords.length}개`}
                    onKeyDown={selectedAlreadyImported ? handleWordListKeyDown : undefined}
                  >
                    {visibleSubscribedWords.map((word, index) => (
                      <li
                        key={word.lexemeId}
                        className="deck-ledger-word"
                        {...(selectedAlreadyImported
                          ? {
                              "data-word-index": index,
                              tabIndex:
                                index === Math.min(activeWordIndex, visibleSubscribedWords.length - 1)
                                  ? 0
                                  : -1,
                              "aria-posinset": index + 1,
                              "aria-setsize": filteredSubscribedWords.length,
                              "aria-label": `${word.surface || word.baseForm || "-"}${
                                word.reading ? `, ${word.reading}` : ""
                              }, ${getDisplayMeaning(word.meaningKo)}, 현재 상태 ${
                                statusLabels[word.status]
                              }${updatingWordLexemeId === word.lexemeId ? ", 저장 중" : ""}`,
                              "aria-describedby": "deck-ledger-word-keys",
                              // Focus anywhere in the row (row or its
                              // select, keyboard or mouse) makes it the
                              // list's Tab stop.
                              onFocus: () => setActiveWordIndex(index),
                            }
                          : {})}
                      >
                        <strong lang="ja">{word.surface || word.baseForm || "-"}</strong>
                        <span lang="ja">{word.reading || ""}</span>
                        <b>{getDisplayMeaning(word.meaningKo)}</b>
                        {selectedAlreadyImported ? (
                          <span className="deck-ledger-word-status">
                            <StatusSelect
                              value={word.status}
                              label={`${word.surface || word.baseForm} 학습 상태`}
                              tabIndex={-1}
                              onChange={(status) => {
                                pendingWordFocusRef.current = index;
                                onUpdateWordStatus(deck.id, word.lexemeId, status);
                              }}
                            />
                            {updatingWordLexemeId === word.lexemeId ? (
                              <small>저장 중...</small>
                            ) : null}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                  <p className="deck-ledger-word-caption">
                    전체 {filteredSubscribedWords.length}개 중 {visibleSubscribedWords.length}개
                    표시
                  </p>
                  {hasMoreSubscribedWords ? (
                    <button
                      type="button"
                      className="deck-ledger-link deck-ledger-more"
                      onClick={() => setVisibleWordCount((count) => count + SHARED_WORD_PAGE_SIZE)}
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
                <p className="deck-ledger-word-empty">검색 결과가 없어요.</p>
              )}
            </>
          ) : (
            <p className="deck-ledger-word-empty">공유된 단어가 없어요.</p>
          )}
        </section>
      );
    }

    const previewItems = deck.items.slice(0, 20);
    const previewTerms = deck.custom_terms.slice(0, 30);
    return (
      <>
        <section className="deck-ledger-words" aria-label="미리 보는 단어">
          <div className="deck-ledger-words-head">
            <span>미리 보는 단어</span>
            <span>
              {previewItems.length} / {deck.vocab_count}
            </span>
          </div>
          {previewItems.length > 0 ? (
            <ul className="deck-ledger-word-list">
              {previewItems.map((item) => (
                <li key={item.id} className="deck-ledger-word">
                  <strong lang="ja">{item.surface || item.base_form || "-"}</strong>
                  <span lang="ja">{item.reading || ""}</span>
                  <b>{getDisplayMeaning(item.meaning_ko)}</b>
                </li>
              ))}
            </ul>
          ) : (
            <p className="deck-ledger-word-empty">공유된 단어가 없어요.</p>
          )}
        </section>
        <section className="deck-ledger-words" aria-label="사용자 정의 용어">
          <div className="deck-ledger-words-head">
            <span>사용자 정의 용어</span>
            <span>
              {previewTerms.length} / {deck.custom_term_count}
            </span>
          </div>
          {previewTerms.length > 0 ? (
            <ul className="deck-ledger-word-list">
              {previewTerms.map((term) => {
                const goodMeaning = getDisplayMeaning(term.meaning_ko, "");
                return (
                  <li key={term.id} className="deck-ledger-word">
                    <strong lang="ja">{term.term}</strong>
                    <span lang="ja">{term.reading || ""}</span>
                    <b>{goodMeaning || term.description || getDisplayMeaning(null)}</b>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="deck-ledger-word-empty">공유된 사용자 정의 용어가 없어요.</p>
          )}
        </section>
      </>
    );
  }

  function renderDetailPage() {
    if (!isDetailOpen) {
      return (
        <div className="deck-ledger-detail-blank">
          <span className="deck-ledger-smallcap">선택한 덱</span>
          <p className="deck-ledger-blank-title">덱을 고르면 이 지면에 펼쳐져요.</p>
          <p>
            단어를 미리 살펴보고 마음에 드는 덱은 내 학습 목록에 담아 읽기와 복습에 함께
            쓸 수 있어요.
          </p>
          {hasJlptDeck ? <p className="deck-ledger-note">{JLPT_DISCLAIMER}</p> : null}
          <p className="deck-ledger-privacy">원문 전체는 포함되지 않아요.</p>
        </div>
      );
    }

    const positionLabel =
      selectedIndex >= 0
        ? `${formatIndex(selectedIndex)} / ${visibleDecks.length}`
        : hasFilters
          ? "현재 조건 밖"
          : "";

    return (
      <>
        <div className="deck-ledger-detail-top">
          <button
            type="button"
            ref={backButtonRef}
            className="deck-ledger-back"
            onClick={onCloseDetail}
          >
            ‹ 덱 목록
          </button>
          <span className="deck-ledger-position">{positionLabel}</span>
        </div>

        {!selectedDeck ? (
          <div className="deck-ledger-detail-blank">
            <p className="deck-ledger-blank-title">
              {isLoadingDetail ? "덱을 펼치는 중이에요..." : "이 덱을 펼치지 못했어요."}
            </p>
            {!isLoadingDetail ? <p>목록에서 다시 골라 주세요.</p> : null}
          </div>
        ) : (
          <>
            <div className="deck-ledger-detail-body" ref={detailBodyRef} key={selectedDeck.id}>
              <span className="deck-ledger-smallcap">
                {DECK_SOURCE_LABELS[getDeckSource(selectedDeck)]}
                {selectedLevel ? ` · JLPT ${selectedLevel}` : ""}
                {selectedDeck.mode === "subscribed" ? " · 학습 목록형" : ""}
              </span>
              <h3 className="deck-ledger-detail-title">
                {getDisplayTitle(selectedDeck, selectedLevel)}
              </h3>
              <p className="deck-ledger-detail-meta">
                {selectedDeck.owner_display_name ? (
                  <span>{selectedDeck.owner_display_name}</span>
                ) : null}
                <span>단어 {selectedDeck.vocab_count}개</span>
                {selectedDeck.custom_term_count > 0 ? (
                  <span>용어 {selectedDeck.custom_term_count}개</span>
                ) : null}
                <span>가져간 횟수 {selectedDeck.import_count}회</span>
              </p>
              <p className="deck-ledger-detail-date">
                등록 {formatDateTime(selectedDeck.created_at)}
              </p>
              {!selectedDeckPublished || selectedAlreadyImported ? (
                <p className="deck-ledger-detail-states">
                  {!selectedDeckPublished ? (
                    <span className="deck-ledger-state deck-ledger-state-paused">공유 중단됨</span>
                  ) : null}
                  {selectedAlreadyImported ? (
                    <span className="deck-ledger-state">
                      {selectedDeck.mode === "subscribed" ? "학습 목록에 있음" : "가져옴"}
                      {selectedDeck.imported_at
                        ? ` · ${formatDateTime(selectedDeck.imported_at)}`
                        : ""}
                    </span>
                  ) : null}
                </p>
              ) : null}
              <p className="deck-ledger-detail-desc">
                {getDeckDescription(selectedDeck.description, selectedLevel)}
              </p>
              {selectedLevel ? <p className="deck-ledger-note">{JLPT_DISCLAIMER}</p> : null}
              {canManageSharedDecks && selectedDeck.is_owner ? (
                <p className="deck-ledger-note">
                  {selectedDeckPublished
                    ? "공유를 중단하면 새 사용자는 더 이상 이 덱을 가져올 수 없어요. 이미 학습 중인 사용자는 복습을 계속 이어갈 수 있고, 이 덱은 내 책장에서도 계속 볼 수 있어요."
                    : "이 덱은 더 이상 공유 목록에 보이지 않지만, 이미 학습 중인 사용자는 복습을 이어갈 수 있어요."}
                </p>
              ) : !selectedDeckPublished ? (
                <p className="deck-ledger-note">
                  새 사용자는 더 이상 가져올 수 없지만, 내 복습은 계속 이어져요.
                </p>
              ) : null}

              {renderWordSection(selectedDeck)}
            </div>

            <div className="deck-ledger-detail-foot">
              {renderPrimaryAction(selectedDeck)}
              <p className="deck-ledger-privacy">원문 전체는 포함되지 않아요.</p>
            </div>
          </>
        )}
      </>
    );
  }

  const importedDeckIsOpen =
    importedDeckId !== null && importedDeckId === selectedDeckId && selectedDeck !== null;

  return (
    <section
      className={`tab-panel deck-ledger${isDetailOpen ? " is-detail-open" : ""}`}
      aria-label="덱 책장"
    >
      <div className="deck-ledger-stage">
        <header className="deck-ledger-head">
          <div>
            <span className="deck-ledger-kicker">SHARED DECKS / 共有ノート</span>
            <h2>덱 책장</h2>
          </div>
          <button type="button" className="deck-ledger-head-link" onClick={onGoToVocab}>
            내 단어장 만들기 ↗
          </button>
        </header>

        <div className="deck-ledger-register">
          <div className="deck-ledger-strip">
            <span>공유 단어장 목록</span>
            <span className="deck-ledger-strip-motto">고르고 · 열고 · 함께 공부하기</span>
          </div>

          {/* A failed list load with nothing to show already says so (with a
              retry) in the list itself; the strip would repeat it. */}
          {message && !(messageTone === "error" && !hasDecks) ? (
            <div className={`deck-ledger-message deck-ledger-message-${messageTone}`} role="status">
              {messageTone === "success" ? (
                <ShioriStamp variant="success" className="deck-ledger-message-stamp" />
              ) : null}
              <span className="deck-ledger-message-text">{message}</span>
              {isImportSuccess ? (
                <span className="deck-ledger-message-actions">
                  {importedDeckId && !importedDeckIsOpen ? (
                    <button
                      type="button"
                      className="deck-ledger-link"
                      onClick={() => handleOpenDeck(importedDeckId)}
                    >
                      학습 목록 보기
                    </button>
                  ) : null}
                  <button type="button" className="deck-ledger-link" onClick={onGoToStudyToday}>
                    복습 시작
                  </button>
                </span>
              ) : null}
            </div>
          ) : null}

          <div className="deck-ledger-pages">
            <div className="deck-ledger-list-page">
              <div className="deck-ledger-tools">
                <label className="deck-ledger-search">
                  <SearchIcon className="deck-ledger-search-icon" />
                  <input
                    type="search"
                    value={deckQuery}
                    onChange={(event) => setDeckQuery(event.target.value)}
                    placeholder="제목, 공유자, 설명으로 검색"
                    aria-label="공유 덱 검색"
                  />
                </label>
                <label className="deck-ledger-sort">
                  <span className="deck-ledger-sort-label">정렬</span>
                  <select
                    value={deckSort}
                    onChange={(event) => setDeckSort(event.target.value as DeckSort)}
                    aria-label="공유 덱 정렬"
                  >
                    {DECK_SORT_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="deck-ledger-filters" role="group" aria-label="덱 분류">
                <button
                  type="button"
                  className={sourceFilter === "all" ? "is-active" : undefined}
                  aria-pressed={sourceFilter === "all"}
                  onClick={() => setSourceFilter("all")}
                >
                  전체 <b>{decks.length}</b>
                </button>
                {(Object.keys(DECK_SOURCE_LABELS) as DeckSource[]).map((source) => (
                  <button
                    key={source}
                    type="button"
                    className={sourceFilter === source ? "is-active" : undefined}
                    aria-pressed={sourceFilter === source}
                    onClick={() => setSourceFilter(source)}
                  >
                    {DECK_SOURCE_LABELS[source]} <b>{sourceCounts[source]}</b>
                  </button>
                ))}
              </div>

              <div className="deck-ledger-count">
                <span aria-live="polite">{visibleDecks.length}개 덱</span>
                <span className="deck-ledger-count-cols">제목 · 공유자 · 단어 수</span>
              </div>

              <div className="deck-ledger-list" ref={listRef} onScroll={handleListScroll}>
                {renderListBody()}
              </div>

              <div className="deck-ledger-list-foot">
                <span>
                  전체 {decks.length}개 중 {visibleDecks.length}개 표시
                </span>
                <button
                  type="button"
                  className="deck-ledger-link"
                  onClick={onRefresh}
                  disabled={isLoading}
                >
                  {isLoading ? "불러오는 중..." : "목록 새로고침"}
                  <RotateIcon className="deck-ledger-link-icon" />
                </button>
              </div>
            </div>

            <article className="deck-ledger-detail" aria-label="선택한 덱">
              {renderDetailPage()}
            </article>
          </div>

          <footer className="deck-ledger-foot">
            <span>내가 공유함 {sourceCounts.mine}</span>
            <span>추천 {sourceCounts.recommended}</span>
            <span>다른 학습자 {sourceCounts.community}</span>
          </footer>
        </div>
      </div>
    </section>
  );
}

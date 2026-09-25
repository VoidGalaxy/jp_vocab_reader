"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { TokenStatus, TokenWithStatus } from "./types";
import { TokenChip } from "./TokenChip";
import { TokenDetailSheet, TokenDetailLedger } from "./TokenDetailSheet";
import { MeaningQuickEdit } from "./MeaningQuickEdit";
import { ShioriGuideCard, ShioriMark } from "./Shiori";
import { ReadingSourceSlip } from "./ReadingSourceSlip";
import type { ReadingSourceSlipProps } from "./ReadingSourceSlip";
import { buildReaderLayout, getNavigableTokenIndexes } from "./readerLayout";
import { getTokenGroupKey } from "./coverageUtils";
import type { MessageTone } from "./coverageUtils";
import { BookmarkIcon, CardFileIcon, ChevronDownIcon, FolderIcon, InfoIcon, PencilIcon } from "./icons";

// Reading-progress percentage is derived from how far the reader has
// scrolled through the .reader-text container relative to the viewport,
// not from selected-token position -- most reading happens without
// clicking every word, so scroll position is the more meaningful signal.
// 0 = container top just entered the viewport top, 1 = container bottom
// has reached the viewport bottom. Deliberately approximate (see task
// notes): the goal is a sense of "how far in", not a precise metric.
function computeScrollProgress(container: HTMLElement | null): number {
  if (!container || typeof window === "undefined") {
    return 0;
  }
  const rect = container.getBoundingClientRect();
  const viewportHeight = window.innerHeight || 1;
  const total = Math.max(rect.height - viewportHeight, 1);
  const scrolled = Math.min(Math.max(-rect.top, 0), total);
  return scrolled / total;
}

// Reading V3 Gate C correction -- desktop's actual scrolling element is
// .reader-scroll-region itself (overflow-y:auto, see globals.css), not the
// window (window never scrolls at this breakpoint -- confirmed via
// body.scrollHeight === window.innerHeight in Gate B/C QA). The
// window-scroll-based computeScrollProgress above is correct for mobile
// (where the page itself scrolls) but silently never advances past its
// initial value on desktop, which is why the progress ribbon stayed stuck.
// scrollTop / max(scrollHeight - clientHeight, 1), clamped to 0..1.
function computeReaderRegionProgress(region: HTMLElement | null): number {
  if (!region) {
    return 0;
  }
  const total = Math.max(region.scrollHeight - region.clientHeight, 1);
  const scrolled = Math.min(Math.max(region.scrollTop, 0), total);
  return scrolled / total;
}

// scrollIntoView/scrollTo's explicit `behavior: "smooth"` option bypasses
// the CSS `scroll-behavior: auto !important` the app's global
// prefers-reduced-motion rule sets (that CSS property only governs "auto"
// JS calls, not an explicitly-requested smooth one) -- so a reduced-motion
// user still gets an animated scroll unless call sites downgrade it here.
function resolveScrollBehavior(preferred: ScrollBehavior): ScrollBehavior {
  if (
    preferred === "smooth" &&
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ) {
    return "auto";
  }
  return preferred;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

type ReaderModeProps = {
  originalText: string;
  tokens: TokenWithStatus[];
  onStatusChange: (index: number, status: TokenStatus) => void;
  initialSelectedTokenKey?: string | null;
  onSelectedTokenKeyChange?: (key: string | null) => void;
  // Scroll-through-container fraction (0..1) restored from the last saved
  // reading session, if any. Read once at mount (see bookmarkScrollFractionRef
  // below) -- later prop updates (this same value gets echoed back up via
  // onScrollProgressChange as the user scrolls) are intentionally ignored so
  // the "마지막 위치로 이동" bookmark keeps pointing at where the user left
  // off last time, not at wherever they've scrolled to just now.
  initialScrollFraction?: number | null;
  onScrollProgressChange?: (fraction: number) => void;
  // Imperative "select this token" channel for triggers outside the reader
  // itself (currently: the word-list panel). requestId must increment on
  // every request, including repeat clicks on the same tokenIndex, so the
  // effect below can tell "new click" apart from "unrelated re-render with
  // the same prop value" -- a plain tokenIndex-only prop couldn't do that.
  externalSelectRequest?: { tokenIndex: number; requestId: number } | null;
  meaningEditItemId: number | null;
  meaningEditDraft: string;
  isSavingMeaningEdit: boolean;
  meaningEditMessage: string;
  onStartMeaningEdit: (itemId: number, currentMeaning: string) => void;
  onMeaningEditDraftChange: (value: string) => void;
  onSaveMeaningEdit: () => void;
  onCancelMeaningEdit: () => void;
  onReportMeaning: (token: TokenWithStatus) => void;
  // Word Basket (Save Tray) wiring -- the selection Set itself lives in
  // ReadingTab (shared with the word-list panel), so the inspector only
  // needs yes/no + a toggle for whichever token is currently active.
  isTokenInBasket: (token: TokenWithStatus) => boolean;
  canAddToBasket: (token: TokenWithStatus) => boolean;
  onToggleBasket: (token: TokenWithStatus) => void;
  // Reading V3 Gate 3 -- the Save Tray (selection count + "선택한 단어
  // 저장") used to be its own floating card (.reading-save-memo) pinned
  // over the scene regardless of what the right page was showing. The
  // approved analyzed-state reference folds it into the right page's own
  // footer instead, alongside the per-word basket/meaning-edit/report
  // actions -- so it needs the same summary data ReadingTab already
  // computes for that card. No behavior change: same selection Set, same
  // save handler, same message/tone, just rendered in a different place.
  selectedCount: number;
  saveableCount: number;
  isSavingBatch: boolean;
  onSaveSelected: () => void;
  saveMessage: string;
  saveMessageTone: MessageTone;
  recentlySavedCount: number;
  onStartStudyFromSaved: () => void;
  onGoToVocab: () => void;
  wordListOpen: boolean;
  onToggleWordList: () => void;
  wordListCount: number;
  wordListContent: ReactNode;
  // Session management -- previously ReadingTab's own top-of-screen
  // "원문 관리" toolbar (a separate row above this card). Folded in here
  // instead: the restore notice as a small chip in the header, the
  // collapse/reset actions inside the existing "옵션" panel, so the reading
  // tab has one management surface instead of a toolbar plus a card.
  isSessionRestored: boolean;
  onDismissRestoredNotice: () => void;
  isTextCollapsed: boolean;
  onToggleTextCollapsed: () => void;
  onResetSession: () => void;
  // Phase 169 -- the re-edit source slip (same component/markup Reading's
  // no-result state renders directly, see ReadingSourceSlip.tsx) now lives
  // inside this component's own left page pane, above the reader text,
  // instead of a separate .reading-input-open card ReadingTab used to
  // render below the whole reader workspace. showSlip mirrors ReadingTab's
  // existing `!isTextCollapsed` visibility rule; slipProps is the exact
  // prop bag ReadingTab already builds for its own no-result render of the
  // same component, just threaded one level deeper.
  showSlip: boolean;
  slipProps: ReadingSourceSlipProps;
};

export function ReaderMode({
  originalText,
  tokens,
  onStatusChange,
  initialSelectedTokenKey = null,
  onSelectedTokenKeyChange,
  initialScrollFraction = null,
  onScrollProgressChange,
  externalSelectRequest = null,
  meaningEditItemId,
  meaningEditDraft,
  isSavingMeaningEdit,
  meaningEditMessage,
  onStartMeaningEdit,
  onMeaningEditDraftChange,
  onSaveMeaningEdit,
  onCancelMeaningEdit,
  onReportMeaning,
  isTokenInBasket,
  canAddToBasket,
  onToggleBasket,
  selectedCount,
  saveableCount,
  isSavingBatch,
  onSaveSelected,
  saveMessage,
  saveMessageTone,
  recentlySavedCount,
  onStartStudyFromSaved,
  onGoToVocab,
  wordListOpen,
  onToggleWordList,
  wordListCount,
  wordListContent,
  isSessionRestored,
  onDismissRestoredNotice,
  isTextCollapsed,
  onToggleTextCollapsed,
  onResetSession,
  showSlip,
  slipProps,
}: ReaderModeProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  // Which literal rendered occurrence was clicked, when known -- a repeated
  // word (e.g. 闇 appearing 40 times in a long text) collapses to one
  // tokenIndex after dedup, so tokenIndex alone can't tell "the 3rd 闇" apart
  // from "the 1st 闇". null means "no specific occurrence" (prev/next nav,
  // the word-list panel, or a restored selection), which intentionally
  // falls back to the word's first occurrence.
  const [activeSegmentKey, setActiveSegmentKey] = useState<string | null>(
    null,
  );
  const [focusMode, setFocusMode] = useState(false);
  const [showJlptTags, setShowJlptTags] = useState(true);
  // Reader-first layout: display toggles used to sit inline in the header
  // row, always visible -- collapsed behind a small "옵션" button instead,
  // so the reader paper's own header doesn't compete with the paper below
  // it for attention. Local-only UI state, no effect on the toggles'
  // values or behavior once opened.
  const [isOptionsOpen, setIsOptionsOpen] = useState(false);
  // Casual Sticker Reader (Phase 65) -- true 2-column "desk scene" (reader
  // page + pinned word inspector) only kicks in at the same breakpoint as
  // .reading-page--right's own display:none override in globals.css
  // (1024px); keep both in sync if this value ever changes. Starts false
  // (matches SSR/first paint) and is
  // only actually read once a token is selected, which never happens before
  // this effect has had a chance to run once mounted -- so there is no
  // hydration mismatch to worry about here.
  const [isDesktopPinned, setIsDesktopPinned] = useState(false);
  // Guards against re-applying a restored selection every time tokens
  // change (e.g. after a status save) -- only ever resolved once, right
  // after a restore, then the user's own clicks take over.
  const [hasAppliedInitialSelection, setHasAppliedInitialSelection] =
    useState(false);
  // Guards the one-time scroll-to-last-position restore the same way
  // hasAppliedInitialSelection guards the token restore above.
  const [hasAppliedInitialScroll, setHasAppliedInitialScroll] =
    useState(false);
  // Live 0..1 scroll-through-container fraction, recomputed as the user
  // scrolls -- drives the progress bar/percent display.
  const [scrollProgress, setScrollProgress] = useState(0);
  const readerTextRef = useRef<HTMLDivElement | null>(null);
  // Reading V3 Gate 3B -- the actual scrolling element for reading mode
  // (.reader-scroll-region, overflow-y:auto at desktop; readerTextRef above
  // points at .reader-text, a non-scrolling child of it). Desktop's
  // options/re-edit modes now unmount this region entirely (mutually
  // exclusive render regions, not an overlay on top of it), so its own
  // scrollTop resets to 0 on remount unless explicitly saved/restored --
  // these two refs are that save/restore channel, plus a deferred-action
  // slot for the options panel's "맨 위로"/"선택 단어로 이동" buttons, which
  // can't act on a currently-unmounted reader directly. Desktop-only
  // (gated on isDesktopPinned in every handler/effect that touches them):
  // mobile never unmounts the reader for options/re-edit (same simultaneous
  // overlay it always had), so it needs none of this.
  const readerScrollRegionRef = useRef<HTMLDivElement | null>(null);
  const savedReaderScrollTopRef = useRef(0);
  const pendingReaderNavActionRef = useRef<null | "top" | "bookmark">(null);
  const scrollProgressThrottleRef = useRef<number | null>(null);
  // Frozen at mount: the "last read position" bookmark from the restored
  // session, kept separate from the live scrollProgress state above (which
  // this same value seeds in the parent and would otherwise immediately
  // drift to "wherever the user is right now" the moment they scroll).
  const bookmarkScrollFractionRef = useRef<number | null>(
    initialScrollFraction,
  );
  // Same reasoning, same bug class: initialSelectedTokenKey and
  // onSelectedTokenKeyChange are two ends of one live-updating piece of
  // parent state (the parent just echoes back whatever the user last
  // clicked), not a one-shot "restore this" value. Freezing it at mount
  // keeps the restore effect below from misfiring on the user's very first
  // in-session click (which otherwise looks identical to "a session was
  // restored with this key" the moment that click's key change round-trips
  // back down as a new initialSelectedTokenKey) and stomping the segment
  // key that click just set.
  const initialSelectedTokenKeyRef = useRef(initialSelectedTokenKey);
  // Tracks the last externalSelectRequest.requestId actually applied, so a
  // repeat click on the same word (same tokenIndex, new requestId) still
  // re-triggers the select+scroll, while an unrelated re-render that just
  // echoes the same request object back doesn't reapply it forever.
  const lastHandledExternalRequestIdRef = useRef<number | null>(null);

  const scrollToFraction = useCallback(
    (fraction: number, behavior: ScrollBehavior) => {
      const container = readerTextRef.current;
      if (!container || typeof window === "undefined") {
        return;
      }
      const rect = container.getBoundingClientRect();
      const viewportHeight = window.innerHeight || 1;
      const total = Math.max(rect.height - viewportHeight, 1);
      const containerTopAbsolute = window.scrollY + rect.top;
      const targetScrollY = Math.max(
        containerTopAbsolute + fraction * total,
        0,
      );
      window.scrollTo({ top: targetScrollY, behavior: resolveScrollBehavior(behavior) });
    },
    [],
  );

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const query = window.matchMedia("(min-width: 1024px)");
    const update = () => setIsDesktopPinned(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  // Reading V3 Gate 3B -- the left page's desktop render region is exactly
  // one of these three at a time (reedit takes priority over options: if
  // re-edit is opened while options happens to still be flagged open
  // underneath, the mode must land on "reedit", not draw both). Mobile
  // ignores this value entirely (its CSS never reads data-left-mode), so
  // isTextCollapsed/isOptionsOpen keep their pre-Gate-3B simultaneous
  // mobile behavior untouched.
  const leftMode: "reading" | "options" | "reedit" = showSlip
    ? "reedit"
    : isOptionsOpen
      ? "options"
      : "reading";

  // Restores the reading-region scroll position saved just before switching
  // away from it (see handleOpenOptions/handleToggleTextCollapsed below) --
  // fires whenever the mode returns to "reading", which covers both
  // "options closed" and "re-edit closed/submitted" the same way, since
  // both land back on leftMode "reading".
  useEffect(() => {
    if (!isDesktopPinned || leftMode !== "reading") {
      return;
    }
    const container = readerScrollRegionRef.current;
    if (container) {
      container.scrollTop = savedReaderScrollTopRef.current;
      // Reading V3 Gate C correction -- recompute immediately rather than
      // waiting for the native "scroll" event this assignment triggers, so
      // the progress ribbon's number is never stale even for one frame
      // right after returning from options/re-edit.
      setScrollProgress(computeReaderRegionProgress(container));
    }
  }, [isDesktopPinned, leftMode]);

  // A "맨 위로"/"선택 단어로 이동" click inside the desktop options panel
  // can't act on the reader directly (it's unmounted while options is the
  // active mode) -- it queues the action here and closes options instead;
  // once leftMode flips back to "reading" and the reader remounts, this
  // effect runs it (small timeout so layout/refs are settled first, same
  // reasoning as the existing initial-scroll-restore effect above).
  useEffect(() => {
    if (!isDesktopPinned || leftMode !== "reading" || !pendingReaderNavActionRef.current) {
      return;
    }
    const action = pendingReaderNavActionRef.current;
    pendingReaderNavActionRef.current = null;
    const timeoutId = window.setTimeout(() => {
      if (action === "top") {
        scrollToTop();
      } else {
        scrollToBookmark();
      }
    }, 50);
    return () => window.clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDesktopPinned, leftMode]);

  const layout = useMemo(
    () => buildReaderLayout(originalText, tokens),
    [originalText, tokens],
  );

  // Previous/next order follows tokens[] directly (already first-occurrence
  // text order -- see getNavigableTokenIndexes), not the rendered layout.
  const navigableIndexes = useMemo(
    () => getNavigableTokenIndexes(tokens),
    [tokens],
  );

  useEffect(() => {
    if (
      hasAppliedInitialSelection ||
      !initialSelectedTokenKeyRef.current ||
      tokens.length === 0
    ) {
      return;
    }
    const matchIndex = tokens.findIndex(
      (token) => getTokenGroupKey(token) === initialSelectedTokenKeyRef.current,
    );
    if (matchIndex !== -1) {
      setActiveIndex(matchIndex);
      setActiveSegmentKey(null);
    }
    setHasAppliedInitialSelection(true);
  }, [hasAppliedInitialSelection, tokens]);

  // Handles an external "jump to this word" request (the word-list panel).
  // Inlines the same select+notify steps selectToken does below rather than
  // calling it directly, since that function is declared after the early
  // tokens.length===0 return and hooks can't depend on post-return bindings.
  useEffect(() => {
    if (
      !externalSelectRequest ||
      lastHandledExternalRequestIdRef.current === externalSelectRequest.requestId
    ) {
      return;
    }
    lastHandledExternalRequestIdRef.current = externalSelectRequest.requestId;
    const { tokenIndex } = externalSelectRequest;
    if (tokenIndex < 0 || tokenIndex >= tokens.length) {
      return;
    }
    setActiveIndex(tokenIndex);
    setActiveSegmentKey(null);
    onSelectedTokenKeyChange?.(getTokenGroupKey(tokens[tokenIndex]));
  }, [externalSelectRequest, tokens, onSelectedTokenKeyChange]);

  // Restores scroll position on mount when there's no token bookmark to
  // restore to instead (the token-restore effect above already scrolls the
  // selected word into view via the activeIndex effect below, which is more
  // precise -- this is only the fallback for "was scroll-reading without
  // selecting a word"). Runs after render so the container has real layout
  // to measure -- a short setTimeout rather than requestAnimationFrame,
  // since rAF isn't guaranteed to be serviced promptly in every context
  // (see the scroll-tracking effect below for the same reasoning).
  useEffect(() => {
    if (
      hasAppliedInitialScroll ||
      initialScrollFraction === null ||
      initialScrollFraction === undefined ||
      tokens.length === 0
    ) {
      return;
    }
    if (initialSelectedTokenKey) {
      const matchExists = tokens.some(
        (token) => getTokenGroupKey(token) === initialSelectedTokenKey,
      );
      if (matchExists) {
        setHasAppliedInitialScroll(true);
        return;
      }
    }
    const timeoutId = window.setTimeout(() => {
      scrollToFraction(initialScrollFraction, "auto");
    }, 50);
    setHasAppliedInitialScroll(true);
    return () => window.clearTimeout(timeoutId);
  }, [
    hasAppliedInitialScroll,
    initialScrollFraction,
    initialSelectedTokenKey,
    tokens,
    scrollToFraction,
  ]);

  // Tracks reading progress as the user scrolls. Throttled with a plain
  // setTimeout rather than requestAnimationFrame -- rAF callbacks are tied
  // to the compositor's paint loop and can silently stall (backgrounded/
  // inactive tabs, some headless/low-power contexts), which would leave the
  // progress bar stuck. A ~50ms timer is imperceptible for a position
  // indicator and fires reliably regardless of paint state.
  //
  // Reading V3 Gate C correction -- desktop (isDesktopPinned) subscribes to
  // .reader-scroll-region's own "scroll" event and computes from its
  // scrollTop/scrollHeight/clientHeight (see computeReaderRegionProgress);
  // that element, not the window, is what actually scrolls at this
  // breakpoint. Mobile keeps subscribing to window "scroll" exactly as
  // before -- untouched behavior, untouched formula.
  useEffect(() => {
    function recompute() {
      if (scrollProgressThrottleRef.current !== null) {
        return;
      }
      scrollProgressThrottleRef.current = window.setTimeout(() => {
        scrollProgressThrottleRef.current = null;
        setScrollProgress(
          isDesktopPinned
            ? computeReaderRegionProgress(readerScrollRegionRef.current)
            : computeScrollProgress(readerTextRef.current),
        );
      }, 50) as unknown as number;
    }
    recompute();
    const scrollTarget: EventTarget = isDesktopPinned
      ? readerScrollRegionRef.current ?? window
      : window;
    scrollTarget.addEventListener("scroll", recompute, { passive: true });
    window.addEventListener("resize", recompute);
    return () => {
      scrollTarget.removeEventListener("scroll", recompute);
      window.removeEventListener("resize", recompute);
      // isDesktopPinned flips shortly after mount (the separate matchMedia
      // effect below), which tears this effect down and rebuilds it once
      // more almost immediately -- if a throttle timeout was still pending
      // at that moment, clearing it without also resetting the ref left
      // recompute()'s own guard permanently non-null (the timeout callback
      // that would have reset it to null never got to run), silently
      // disabling every future recompute call, forever, on this and every
      // later effect instance. Reset it here too, not just inside the
      // timeout body.
      if (scrollProgressThrottleRef.current !== null) {
        window.clearTimeout(scrollProgressThrottleRef.current);
        scrollProgressThrottleRef.current = null;
      }
    };
  }, [layout, isDesktopPinned]);

  // Bubbles the live scroll fraction up to the parent (for localStorage
  // persistence) on a trailing debounce, decoupled from the throttled local
  // updates above so scrolling never writes to localStorage dozens of times
  // per second.
  useEffect(() => {
    if (!onScrollProgressChange) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      onScrollProgressChange(scrollProgress);
    }, 400);
    return () => window.clearTimeout(timeoutId);
  }, [scrollProgress, onScrollProgressChange]);

  // Keeps the selected word visible in the source text as prev/next moves
  // it around -- best-effort only, so a missing DOM match (e.g. the active
  // token fell into the "unmatched" fallback row) is silently skipped.
  // Prefers the exact clicked occurrence (activeSegmentKey) when known;
  // otherwise falls back to the word's first occurrence by tokenIndex --
  // without this split, clicking e.g. the 40th occurrence of a repeated
  // word would scroll back up to the 1st one instead of staying put, since
  // querying by tokenIndex alone always finds the first DOM match.
  useEffect(() => {
    if (activeIndex === null || !readerTextRef.current) {
      return;
    }
    const selector = activeSegmentKey
      ? `[data-segment-key="${activeSegmentKey}"]`
      : `[data-token-index="${activeIndex}"]`;
    const target = readerTextRef.current.querySelector(selector);
    target?.scrollIntoView({ behavior: resolveScrollBehavior("smooth"), block: "center" });
  }, [activeIndex, activeSegmentKey]);

  useEffect(() => {
    if (activeIndex === null) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target)) {
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        goToNext();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        goToPrev();
      } else if (event.key === "Escape") {
        closeDetail();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeIndex, navigableIndexes]);

  if (tokens.length === 0) {
    return null;
  }

  // segmentKey is the specific rendered occurrence that was clicked, if
  // any -- omitted (null) for prev/next nav, which has no single "clicked
  // element" and intentionally lands on the word's first occurrence.
  function selectToken(index: number, segmentKey: string | null = null) {
    setActiveIndex(index);
    setActiveSegmentKey(segmentKey);
    onSelectedTokenKeyChange?.(getTokenGroupKey(tokens[index]));
  }

  function closeDetail() {
    setActiveIndex(null);
    setActiveSegmentKey(null);
    onSelectedTokenKeyChange?.(null);
  }

  const navPosition = activeIndex !== null ? navigableIndexes.indexOf(activeIndex) : -1;
  const canGoPrev = navPosition > 0;
  const canGoNext = navPosition !== -1 && navPosition < navigableIndexes.length - 1;

  function goToPrev() {
    if (navPosition > 0) {
      selectToken(navigableIndexes[navPosition - 1]);
    }
  }

  function goToNext() {
    if (navPosition !== -1 && navPosition < navigableIndexes.length - 1) {
      selectToken(navigableIndexes[navPosition + 1]);
    }
  }

  // "다음 모르는 단어" -- same forward-only walk as goToNext, but skips
  // ahead to the next `unknown`-status word instead of the immediate
  // neighbor. Search starts right after the current position (or from the
  // very start when nothing is selected yet), never wraps.
  function findNextUnknownPosition(): number {
    const startPos = activeIndex !== null ? navPosition : -1;
    for (let i = startPos + 1; i < navigableIndexes.length; i += 1) {
      if (tokens[navigableIndexes[i]].status === "unknown") {
        return i;
      }
    }
    return -1;
  }

  function goToNextUnknown() {
    const nextPos = findNextUnknownPosition();
    if (nextPos !== -1) {
      selectToken(navigableIndexes[nextPos]);
    }
  }

  // Re-selects the same word with no specific occurrence -- selectToken's
  // segmentKey=null default already falls back to the word's first
  // occurrence (see the scroll-into-view effect above), so this is enough
  // to jump back to it from any later occurrence.
  function goToFirstOccurrence() {
    if (activeIndex !== null) {
      selectToken(activeIndex);
    }
  }

  function scrollToTop() {
    readerTextRef.current?.scrollIntoView({ behavior: resolveScrollBehavior("smooth"), block: "start" });
  }

  const hasBookmarkScrollFraction =
    bookmarkScrollFractionRef.current !== null &&
    bookmarkScrollFractionRef.current !== undefined;
  // Label (and target) depend on what's actually available to jump back
  // to: a currently-selected word wins over the frozen scroll bookmark
  // (it's the more precise target), and the button disappears entirely
  // when neither exists.
  const bookmarkButtonLabel =
    activeIndex !== null
      ? "선택 단어로 이동"
      : hasBookmarkScrollFraction
        ? "마지막 위치로 이동"
        : null;

  function scrollToBookmark() {
    if (activeIndex !== null) {
      const selector = activeSegmentKey
        ? `[data-segment-key="${activeSegmentKey}"]`
        : `[data-token-index="${activeIndex}"]`;
      const target = readerTextRef.current?.querySelector(selector);
      target?.scrollIntoView({ behavior: resolveScrollBehavior("smooth"), block: "center" });
      return;
    }
    if (hasBookmarkScrollFraction) {
      scrollToFraction(bookmarkScrollFractionRef.current as number, "smooth");
    }
  }

  // Reading V3 Gate 3B -- desktop's three left-page modes are mutually
  // exclusive, so opening options or re-edit needs to remember where
  // reading mode's scroll was (see the restore effect above) before the
  // reader unmounts; mobile's reader never unmounts for either, so these
  // wrappers only do the extra bookkeeping when isDesktopPinned.
  function handleOpenOptions() {
    if (isDesktopPinned && readerScrollRegionRef.current) {
      savedReaderScrollTopRef.current = readerScrollRegionRef.current.scrollTop;
    }
    setIsOptionsOpen(true);
  }

  function handleToggleOptions() {
    if (isOptionsOpen) {
      setIsOptionsOpen(false);
    } else {
      handleOpenOptions();
    }
  }

  function handleToggleTextCollapsed() {
    if (isDesktopPinned) {
      if (!showSlip && readerScrollRegionRef.current) {
        // About to open re-edit (currently in reading mode) -- remember
        // the scroll position the same way handleOpenOptions does.
        savedReaderScrollTopRef.current = readerScrollRegionRef.current.scrollTop;
      }
      // re-edit and options are mutually exclusive on desktop -- without
      // this, closing re-edit again could land on leftMode "options"
      // instead of back on "reading" (isOptionsOpen would still be true
      // from before re-edit opened, even though its panel was hidden
      // the whole time re-edit was showing).
      setIsOptionsOpen(false);
    }
    onToggleTextCollapsed();
  }

  // "맨 위로"/"선택 단어로 이동" inside the options panel: on desktop the
  // reader is unmounted while options is the active mode, so these defer
  // to the pending-action effect above instead of calling scrollToTop/
  // scrollToBookmark directly. Mobile's reader is never unmounted, so it
  // keeps calling them immediately, exactly as before.
  function handleScrollToTopFromOptions() {
    if (isDesktopPinned) {
      pendingReaderNavActionRef.current = "top";
      setIsOptionsOpen(false);
    } else {
      scrollToTop();
    }
  }

  function handleScrollToBookmarkFromOptions() {
    if (isDesktopPinned) {
      pendingReaderNavActionRef.current = "bookmark";
      setIsOptionsOpen(false);
    } else {
      scrollToBookmark();
    }
  }

  const progressPercent = Math.round(scrollProgress * 100);
  const activeToken = activeIndex !== null ? tokens[activeIndex] : null;
  const hasNextUnknown = findNextUnknownPosition() !== -1;
  const isAtFirstOccurrence = activeSegmentKey === null;
  // Narrowed once here (not re-read off activeToken.savedVocabItemId inside
  // the footer's closures below) so TypeScript can actually track that it's
  // non-null wherever onStartEdit captures it.
  const activeVocabItemId = activeToken?.savedVocabItemId ?? null;

  // Built once and reused by both the pinned (desktop) and modal (mobile)
  // TokenDetailSheet renders below, so the two presentations can never
  // drift out of sync with each other's prop list.
  const tokenDetailProps = activeToken
    ? {
        token: activeToken,
        onClose: closeDetail,
        onStatusChange: (status: TokenStatus) => {
          if (activeIndex !== null) {
            onStatusChange(activeIndex, status);
          }
        },
        onPrevious: goToPrev,
        onNext: goToNext,
        canGoPrevious: canGoPrev,
        canGoNext: canGoNext,
        onNextUnknown: goToNextUnknown,
        canGoNextUnknown: hasNextUnknown,
        onFirstOccurrence: goToFirstOccurrence,
        canGoFirstOccurrence: !isAtFirstOccurrence,
        positionLabel:
          navPosition !== -1
            ? `${navPosition + 1} / ${navigableIndexes.length}`
            : null,
        isInBasket: isTokenInBasket(activeToken),
        canAddToBasket: canAddToBasket(activeToken),
        onToggleBasket: () => onToggleBasket(activeToken),
        meaningEditItemId,
        meaningEditDraft,
        isSavingMeaningEdit,
        meaningEditMessage,
        onStartMeaningEdit,
        onMeaningEditDraftChange,
        onSaveMeaningEdit,
        onCancelMeaningEdit,
        onReportMeaning,
      }
    : null;

  // Reading V3 Gate 3B -- shared between the mobile popover (unchanged
  // shell/behavior, .reader-mode-toggles) and desktop's own inline options
  // mode (new shell, .reading-options-inline, see the return JSX below) so
  // there is exactly one copy of this content/handlers, not two drifting
  // copies. The nav buttons call the desktop-aware wrappers above, which
  // fall back to the exact previous direct scrollToTop/scrollToBookmark
  // calls on mobile (isDesktopPinned false there).
  const optionsSections = (
    <>
      {/* 3 clearly separated groups (dashed divider + small label, same
          recipe the manage row already used) instead of one long
          undifferentiated stack -- easier to scan than a single flat list. */}
      <div className="reader-mode-toggles-section">
        <span className="reader-mode-toggles-section-label">표시</span>
        <label className="checkbox-field reading-focus-toggle">
          <input
            type="checkbox"
            checked={focusMode}
            onChange={(event) => setFocusMode(event.target.checked)}
          />
          <span className="reading-focus-label-full">모르는/헷갈리는 단어만 강조</span>
          <span className="reading-focus-label-compact">모름·헷갈림 강조</span>
        </label>
        <label className="checkbox-field reading-jlpt-toggle">
          <input
            type="checkbox"
            checked={showJlptTags}
            onChange={(event) => setShowJlptTags(event.target.checked)}
          />
          JLPT 태그 표시
        </label>
        <div className="reader-legend-strip">
          <span className="reader-legend-strip-label">색상</span>
          <span className="reader-legend-strip-item">
            <span className="legend-swatch token-chip-known" />
            아는
          </span>
          <span className="reader-legend-strip-item">
            <span className="legend-swatch token-chip-uncertain" />
            헷갈림
          </span>
          <span className="reader-legend-strip-item">
            <span className="legend-swatch token-chip-unknown" />
            모름
          </span>
          <span className="reader-legend-strip-item">
            <span className="legend-swatch token-chip-unclassified" />
            미분류
          </span>
        </div>
      </div>
      <div className="reader-mode-toggles-section">
        <span className="reader-mode-toggles-section-label">이동</span>
        {navPosition !== -1 ? (
          <p className="reader-progress-token-count">
            {navPosition + 1} / {navigableIndexes.length} 단어 확인 중
          </p>
        ) : null}
        <div className="reader-progress-actions">
          {bookmarkButtonLabel ? (
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={handleScrollToBookmarkFromOptions}
            >
              {bookmarkButtonLabel}
            </button>
          ) : null}
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={handleScrollToTopFromOptions}
          >
            맨 위로
          </button>
        </div>
      </div>
      <div className="reader-mode-toggles-section">
        <span className="reader-mode-toggles-section-label">원문 관리</span>
        {/* Reading V3 Gate 3 -- desktop now has its own dedicated "원문
            편집" footer button calling this exact same handler (see
            .reading-left-footer below), so this row would be a second,
            redundant way to do the same thing there. Mobile has no such
            footer, so it keeps this as its only entry point (hidden at
            desktop only, see globals.css). */}
        <button
          type="button"
          className="ghost-button compact-button reader-mode-toggle-textcollapse"
          onClick={handleToggleTextCollapsed}
        >
          {isTextCollapsed ? "원문 입력 펼치기" : "원문 입력 접기"}
        </button>
        <button type="button" className="ghost-button compact-button" onClick={onResetSession}>
          새 원문
        </button>
      </div>
    </>
  );

  // Mobile-only shell (unchanged from before Gate 3B): an absolute-
  // positioned popover under the top progress pill, reader still visible
  // and interactive behind/around it -- see .reader-mode-toggles in
  // globals.css (base rules, no @media(min-width:1024px) gate on the
  // popover itself; the pill it hangs off of is desktop-hidden instead).
  const optionsPopover = isOptionsOpen ? (
    <div className="reader-mode-toggles">
      <p className="reader-mode-hint">모르는 단어를 눌러보세요.</p>
      {optionsSections}
    </div>
  ) : null;

  return (
    <>
      {/* Phase 169 -- reading-page--left is the book's left page on desktop
          (grid, ≥1024px -- see globals.css) and the single visible page on
          mobile (the mobile V2 photo shows one page plus a sliver of the
          other, already baked into the shot). Everything that used to live
          in .reader-desk-scene/.reader-paper/.reader-toolbar now lives here
          as ordinary scrollable page content instead of a bordered card
          layered on a wallpaper photo. */}
      <div
        className="reading-page reading-page--left reading-page--reader"
        data-left-mode={leftMode}
      >
        {isSessionRestored ? (
          <span className="reading-restored-chip">
            이전 작업 복원됨
            <button
              type="button"
              className="reading-restored-chip-dismiss"
              onClick={onDismissRestoredNotice}
            >
              확인
            </button>
          </span>
        ) : null}

        {showSlip ? (
          <div className="reading-page-reedit-slip">
            <ReadingSourceSlip {...slipProps} />
          </div>
        ) : null}

        {/* Phase 169 -- was a full-width toolbar row (title/progress bar/
            percent/"옵션 열기") sitting between the page edge and the first
            line of text. Shrunk to the small page-marker/bookmark-tag the
            brief asks for: one pill showing the read percentage, which is
            also the trigger for the exact same options popover (display
            toggles, legend, nav, session management) this always had.
            Reading V3 Gate 3 -- desktop replaces this top pill with a
            small printed tool row at the page's own bottom edge (see
            .reading-left-footer below) instead, matching
            reading-v3-analyzed-reference.png; this trigger/popover pair
            stays exactly as-is for mobile, which keeps its pre-Gate-3
            look untouched (hidden at >=1024px purely via CSS, see
            globals.css -- same isOptionsOpen state either way, so opening
            it from either trigger can never desync). */}
        <div className="reading-progress-tag-wrap">
          <button
            type="button"
            className="reading-progress-tag"
            onClick={handleToggleOptions}
            aria-expanded={isOptionsOpen}
            aria-label={`읽기 진행률 ${progressPercent}%, 옵션 ${isOptionsOpen ? "닫기" : "열기"}`}
          >
            <ShioriMark variant="reading" />
            <span className="sr-only-label">읽기 모드</span>
            {progressPercent}%
            <ChevronDownIcon
              className={`reading-progress-tag-icon${isOptionsOpen ? " reading-progress-tag-icon-open" : ""}`}
            />
          </button>
        </div>

        {/* Mobile's popover anchor: kept right after the trigger pill above
            (normal flow) so it floats directly below it -- see
            .reading-options-popover-anchor in globals.css. Desktop
            overrides this element's position entirely via
            grid-area:footer (CSS Grid placement ignores DOM source order),
            so moving this here doesn't affect the desktop footer's own
            layout at all. */}
        <div className="reading-options-popover-anchor">{optionsPopover}</div>

        {/* Reading V3 Gate 3 -- only the reading region itself scrolls for
            long text (DESIGN_SPEC.md State Continuity); the footer below
            stays fixed at the page's bottom edge (desktop only -- see the
            .reading-page--reader grid rules in globals.css, same recipe
            Gate 2B already used for the input slip's own fixed controls).
            Reading V3 Gate 3B -- reading/options/re-edit are mutually
            exclusive left-page *modes* on desktop now (data-left-mode
            above), not a stack of overlays: this region stays mounted
            (mobile always shows it regardless of mode, exactly as before
            Gate 3B -- it never had this conflict) but is display:none'd at
            desktop whenever data-left-mode isn't "reading" -- see
            globals.css. Kept mounted rather than conditionally rendered
            specifically so mobile's simultaneous reader+popover overlay
            (its own, separate, intentional pattern) never has to change. */}
        <div className="reader-scroll-region" ref={readerScrollRegionRef}>
          <div className="reader-text" ref={readerTextRef}>
            {layout.lines.map((line, lineIndex) => (
              <p className="reader-line" key={`line-${lineIndex}`}>
                {line.length > 0
                  ? line.map((segment) =>
                      segment.type === "token" ? (
                        <TokenChip
                          key={segment.key}
                          token={tokens[segment.tokenIndex]}
                          tokenIndex={segment.tokenIndex}
                          segmentKey={segment.key}
                          isActive={activeIndex === segment.tokenIndex}
                          focusMode={focusMode}
                          showJlptTags={showJlptTags}
                          onSelect={() => selectToken(segment.tokenIndex, segment.key)}
                        />
                      ) : (
                        <span key={segment.key}>{segment.content}</span>
                      ),
                    )
                  : " "}
              </p>
            ))}
          </div>
          {layout.unmatchedTokenIndexes.length > 0 ? (
            <div className="reader-unmatched-row">
              <span className="reader-unmatched-label">
                원문 위치를 찾지 못한 단어
              </span>
              <div className="reader-unmatched-chips">
                {layout.unmatchedTokenIndexes.map((tokenIndex) => (
                  <TokenChip
                    key={`unmatched-${tokenIndex}`}
                    token={tokens[tokenIndex]}
                    tokenIndex={tokenIndex}
                    isActive={activeIndex === tokenIndex}
                    focusMode={focusMode}
                    showJlptTags={showJlptTags}
                    onSelect={() => selectToken(tokenIndex)}
                  />
                ))}
              </div>
            </div>
          ) : null}
        </div>

        {/* Reading V3 Gate 3B -- desktop's options *mode*: printed directly
            in the same reading region the reader itself occupies (same
            grid-area, see globals.css), not a popover floating over it.
            JSX-conditional (not just CSS-hidden) since -- unlike
            reader-scroll-region above -- mobile has no use for this
            element at all; it keeps using the separate, unchanged
            optionsPopover/.reading-progress-tag-wrap pairing instead. */}
        {isOptionsOpen ? (
          <div className="reading-options-inline">
            <p className="reader-mode-hint">모르는 단어를 눌러보세요.</p>
            {optionsSections}
          </div>
        ) : null}

        {/* Desktop-only small printed tool row (reading-v3-analyzed-reference.png's
            bottom-left "원문 편집 / 표시 옵션 / 문자 수" row). Stays fixed and
            visible in every left-page mode (Gate 3B: closing options or
            re-edit needs this same row still there to land back on). */}
        {/* Reading V3 Gate C correction -- at 1024-1199px the full labels
            ("원문 편집 / 표시 옵션 / 문자 수 N") wrapped the char-count number
            one digit per line, reading as broken text rather than a one-line
            tool strip. Each label now carries both a full and a compact span
            (CSS below shows exactly one per breakpoint, see .reading-left-
            footer-label-full/-compact); aria-label pins the button's
            accessible name to the full phrase regardless of which span is
            visually showing, so assistive tech never sees "편집"/"옵션". */}
        <div className="reading-left-footer">
          <button
            type="button"
            className="reading-left-footer-btn"
            onClick={handleToggleTextCollapsed}
            aria-label="원문 편집"
          >
            <PencilIcon className="button-icon" />
            <span className="reading-left-footer-label-full">원문 편집</span>
            <span className="reading-left-footer-label-compact">편집</span>
          </button>
          <button
            type="button"
            className="reading-left-footer-btn"
            onClick={handleToggleOptions}
            aria-expanded={isOptionsOpen}
            aria-label="표시 옵션"
          >
            <ChevronDownIcon
              className={`reading-left-footer-btn-icon${isOptionsOpen ? " reading-left-footer-btn-icon-open" : ""}`}
            />
            <span className="reading-left-footer-label-full">표시 옵션</span>
            <span className="reading-left-footer-label-compact">옵션</span>
          </button>
          <span className="reading-left-footer-charcount">
            <span className="reading-left-footer-label-full">
              문자 수 {originalText.length}
            </span>
            <span className="reading-left-footer-label-compact">
              {originalText.length}자
            </span>
          </span>
        </div>

        {/* Small physical page-corner marker (reading-v3-analyzed-reference.png's
            forest-green folded corner), desktop only -- a passive readout,
            not an interactive trigger (그 역할은 이제 "표시 옵션" 버튼). */}
        <span className="reading-progress-flag" aria-hidden="true">
          <span className="reading-progress-flag-label">읽기 진행률</span>
          <strong>{progressPercent}%</strong>
        </span>
      </div>

      {/* Desktop-only opposite page: always mounted (an idle Shiori guide
          when nothing is selected, or the pinned dictionary ledger) so the
          book never shows a lopsided single page with empty space beside
          it. Hidden below 1024px via .reading-page--right's own
          display:none (see globals.css); mobile instead gets the floating
          card TokenDetailSheet renders itself in its "modal" presentation,
          further down. Reading V3 Gate 3 -- the footer row (basket/meaning
          edit/report + the Save Tray's selection count and save button,
          previously the separate floating .reading-save-memo card) is now
          part of this same page, always present once a result exists, so
          the right page always ends in one small tidy footer row instead
          of a floating card layered on top of the scene. */}
      <div className="reading-page reading-page--right reading-page--reader" data-right-mode={wordListOpen ? "list" : "ledger"}>
        <div className="reader-scroll-region" id="reading-right-content" key={wordListOpen ? "list" : "ledger"}>
          {wordListOpen ? (
            wordListContent
          ) : tokenDetailProps && isDesktopPinned ? (
            <TokenDetailLedger {...tokenDetailProps} />
          ) : (
            <div className="reading-page-idle">
              <ShioriGuideCard
                variant="reading"
                size="md"
                message="단어를 누르면 이 자리에서 뜻과 예문을 볼 수 있어요."
              />
            </div>
          )}
        </div>

        <div className="reading-right-footer-wrap">
        <div className="reading-right-footer">
          {activeToken ? (
            <>
              {canAddToBasket(activeToken) ? (
                <button
                  type="button"
                  className={`reading-right-footer-btn${
                    isTokenInBasket(activeToken) ? " reading-right-footer-btn-active" : ""
                  }`}
                  onClick={() => onToggleBasket(activeToken)}
                  aria-pressed={isTokenInBasket(activeToken)}
                >
                  <BookmarkIcon className="button-icon" />
                  {isTokenInBasket(activeToken) ? "어휘 노트 담기 해제" : "어휘 노트 담기"}
                </button>
              ) : null}
              {activeVocabItemId !== null ? (
                <MeaningQuickEdit
                  isEditing={meaningEditItemId === activeVocabItemId}
                  draftValue={meaningEditDraft}
                  isSaving={isSavingMeaningEdit}
                  message={
                    meaningEditItemId === activeVocabItemId ? meaningEditMessage : ""
                  }
                  onStartEdit={() =>
                    onStartMeaningEdit(
                      activeVocabItemId,
                      activeToken.savedMeaningKo || activeToken.meaning_ko,
                    )
                  }
                  onDraftChange={onMeaningEditDraftChange}
                  onSave={onSaveMeaningEdit}
                  onCancel={onCancelMeaningEdit}
                  triggerLabel="뜻 수정"
                  triggerClassName="reading-right-footer-btn"
                />
              ) : null}
              <button
                type="button"
                className="reading-right-footer-btn"
                onClick={() => onReportMeaning(activeToken)}
              >
                <InfoIcon className="button-icon" />
                신고
              </button>
              {hasNextUnknown ? (
                <button
                  type="button"
                  className="reading-right-footer-link"
                  onClick={goToNextUnknown}
                >
                  다음 모르는 단어
                </button>
              ) : null}
              {activeToken.occurrence_count > 1 && !isAtFirstOccurrence ? (
                <button
                  type="button"
                  className="reading-right-footer-link"
                  onClick={goToFirstOccurrence}
                >
                  첫 등장으로
                </button>
              ) : null}
            </>
          ) : null}
        </div>
        {/* Reading V3 Gate C -- the accounting sentence + save command used
            to sit as trailing flex items in the same wrapping row as the
            per-word tools above, pushed right by a flex:1 spacer. That
            meant how many lines the row took (and therefore the whole
            footer's height) depended on which per-word tools happened to
            be present (뜻 수정 only shows once a word is already saved) AND
            on selectedCount (the save button only exists once
            selectedCount > 0) at the same time -- exactly the combination
            that could push the save button alone onto a second line the
            moment selectedCount went 0 -> 1, moving the footer's height.
            A dedicated second row removes that coupling: its own presence
            and height never depend on selectedCount, only whether the save
            button paints *inside* it. */}
        <div className="reading-right-footer-tail">
          <span className="reading-right-footer-count">
            선택 <strong>{selectedCount}</strong>개
            <span className="reading-right-footer-saveable">
              저장 가능 {saveableCount}개
            </span>
          </span>
          {selectedCount > 0 ? (
            <button
              type="button"
              className="reader-bookmark-button reading-right-footer-save"
              onClick={onSaveSelected}
              disabled={isSavingBatch}
            >
              <FolderIcon className="button-icon" />
              {isSavingBatch ? "저장 중..." : `선택한 단어 저장 (${selectedCount})`}
            </button>
          ) : null}
        </div>
        {saveMessage ? (
          <p className={`reading-right-footer-message reading-right-footer-message--${saveMessageTone}`}>
            {saveMessage}
          </p>
        ) : null}
        <div className="reading-right-footer-links">
          <button
            type="button"
            className="reading-right-footer-link reading-right-footer-list-toggle"
            onClick={onToggleWordList}
            aria-controls="reading-right-content"
            aria-pressed={wordListOpen}
          >
            <CardFileIcon className="button-icon" />
            {wordListOpen ? "단어 정보로" : `이 글의 단어 ${wordListCount}개`}
          </button>
          {recentlySavedCount > 0 ? (
            <button
              type="button"
              className="reading-right-footer-link"
              onClick={onStartStudyFromSaved}
            >
              저장한 단어 {recentlySavedCount}개 복습
            </button>
          ) : null}
          <button type="button" className="reading-right-footer-link" onClick={onGoToVocab}>
            어휘 노트 보기
          </button>
        </div>
        </div>
      </div>

      {tokenDetailProps && !isDesktopPinned ? (
        <TokenDetailSheet presentation="modal" {...tokenDetailProps} />
      ) : null}
    </>
  );
}

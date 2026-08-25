"use client";

import { useMemo, useRef, useState, type FormEvent } from "react";
import { ShioriGuideCard, ShioriMark } from "./Shiori";
import { ReaderMode } from "./ReaderMode";
import { ReadingVocabPanel } from "./ReadingVocabPanel";
import { DeckLoadRecovery, ReadingSourceSlip } from "./ReadingSourceSlip";
import type { ReadingSourceSlipProps } from "./ReadingSourceSlip";
import {
  classifyMessageTone,
  computeReadingSaveSummary,
  computeReadingVocabEntries,
  getTokenGroupKey,
} from "./coverageUtils";
import type { ReadingVocabEntry } from "./coverageUtils";
import { FolderIcon } from "./icons";
import type { ChunkAnalyzeProgress } from "./readingChunkAnalyze";
import type { Deck, TokenStatus, TokenWithStatus, VocabItem } from "./types";

// Copyright-safe, hand-written sample so first-time users can try the flow
// without pasting their own text first. Exported so page.tsx's home-tab
// "샘플로 체험하기" CTA can load the exact same text/deck-analyze pipeline
// from outside this tab without a second source of truth.
export const SAMPLE_TEXT =
  "彼は闇の中で声を聞いた。少女は約束を思い出した。騎士は剣を握り、敵から王を守った。";

const DESKTOP_ASSET = "/brand/decor/v2/v2-reading-open-book-desktop-16x9.webp";
const MOBILE_ASSET = "/brand/decor/v2/v2-reading-page-mobile-9x16.webp";

type ReadingTabProps = {
  text: string;
  analyzedText: string;
  tokens: TokenWithStatus[];
  vocabItems: VocabItem[];
  decks: Deck[];
  isLoadingDecks: boolean;
  deckLoadError: string;
  onRetryLoadDecks: () => void;
  selectedDeckId: string;
  isAnalyzing: boolean;
  analyzeProgress: ChunkAnalyzeProgress | null;
  onCancelAnalyze: () => void;
  message: string;
  storageWarning: string;
  isTextCollapsed: boolean;
  isSavingBatch: boolean;
  recentlySavedCount: number;
  isSessionRestored: boolean;
  selectedTokenKey: string | null;
  scrollFraction: number | null;
  onScrollProgressChange: (fraction: number) => void;
  onTextChange: (text: string) => void;
  onLoadSampleText: () => void;
  onSelectedDeckChange: (deckId: string) => void;
  onAnalyze: (event: FormEvent<HTMLFormElement>) => void;
  onStatusChange: (index: number, status: TokenStatus) => void;
  onToggleTextCollapsed: () => void;
  onSaveSelected: (tokenIndexes: number[]) => Promise<number[]>;
  onStartStudyFromSaved: () => void;
  onGoToVocab: () => void;
  onSelectedTokenKeyChange: (key: string | null) => void;
  onDismissRestoredNotice: () => void;
  onResetSession: () => void;
  meaningEditItemId: number | null;
  meaningEditDraft: string;
  isSavingMeaningEdit: boolean;
  meaningEditMessage: string;
  onStartMeaningEdit: (itemId: number, currentMeaning: string) => void;
  onMeaningEditDraftChange: (value: string) => void;
  onSaveMeaningEdit: () => void;
  onCancelMeaningEdit: () => void;
  onReportMeaning: (token: TokenWithStatus) => void;
};

export function ReadingTab({
  text,
  analyzedText,
  tokens,
  vocabItems,
  decks,
  isLoadingDecks,
  deckLoadError,
  onRetryLoadDecks,
  selectedDeckId,
  isAnalyzing,
  analyzeProgress,
  onCancelAnalyze,
  message,
  storageWarning,
  isTextCollapsed,
  isSavingBatch,
  recentlySavedCount,
  isSessionRestored,
  selectedTokenKey,
  scrollFraction,
  onScrollProgressChange,
  onTextChange,
  onLoadSampleText,
  onSelectedDeckChange,
  onAnalyze,
  onStatusChange,
  onToggleTextCollapsed,
  onSaveSelected,
  onStartStudyFromSaved,
  onGoToVocab,
  onSelectedTokenKeyChange,
  onDismissRestoredNotice,
  onResetSession,
  meaningEditItemId,
  meaningEditDraft,
  isSavingMeaningEdit,
  meaningEditMessage,
  onStartMeaningEdit,
  onMeaningEditDraftChange,
  onSaveMeaningEdit,
  onCancelMeaningEdit,
  onReportMeaning,
}: ReadingTabProps) {
  const hasResult = tokens.length > 0;
  const showForm = !hasResult || !isTextCollapsed;
  // Imperative "jump to this word" channel from the word-list panel to
  // ReaderMode -- purely a UI wiring concern local to this tab, so it
  // doesn't need to live in page.tsx or localStorage (the resulting
  // selection/scroll gets persisted through the existing
  // onSelectedTokenKeyChange/onScrollProgressChange pipes once applied).
  const [externalSelectRequest, setExternalSelectRequest] = useState<{
    tokenIndex: number;
    requestId: number;
  } | null>(null);
  const externalSelectRequestIdRef = useRef(0);

  function handleVocabPanelSelect(tokenIndex: number) {
    externalSelectRequestIdRef.current += 1;
    setExternalSelectRequest({
      tokenIndex,
      requestId: externalSelectRequestIdRef.current,
    });
  }
  const summary = hasResult
    ? computeReadingSaveSummary(tokens, vocabItems, selectedDeckId)
    : null;

  // Save Tray / Word Basket -- lifted up from ReadingVocabPanel so both the
  // word-list panel's checkboxes and the Word Inspector's "저장 대상으로
  // 선택" toggle read/write the exact same selection instead of each owning
  // a separate one. Keyed by getTokenGroupKey (same grouping every other
  // save path already uses), not tokenIndex, so a repeated word selected via
  // one occurrence is recognized when clicked via another.
  const entries = useMemo(
    () => computeReadingVocabEntries(tokens, vocabItems, selectedDeckId),
    [tokens, vocabItems, selectedDeckId],
  );
  const entriesByKey = useMemo(() => {
    const map = new Map<string, ReadingVocabEntry>();
    entries.forEach((entry) => map.set(getTokenGroupKey(entry.token), entry));
    return map;
  }, [entries]);
  const [selectedWordKeys, setSelectedWordKeys] = useState<Set<string>>(
    () => new Set(),
  );
  const selectedEntries = useMemo(() => {
    if (selectedWordKeys.size === 0) {
      return [];
    }
    return entries.filter(
      (entry) =>
        entry.isSaveable && selectedWordKeys.has(getTokenGroupKey(entry.token)),
    );
  }, [entries, selectedWordKeys]);
  const selectedCount = selectedEntries.length;

  function toggleSelect(key: string) {
    setSelectedWordKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function replaceSelection(nextEntries: ReadingVocabEntry[]) {
    setSelectedWordKeys(
      new Set(nextEntries.map((entry) => getTokenGroupKey(entry.token))),
    );
  }

  function clearSelection() {
    setSelectedWordKeys(new Set());
  }

  async function handleSaveSelected() {
    if (selectedCount === 0 || isSavingBatch) {
      return;
    }
    const tokenIndexes = selectedEntries.map((entry) => entry.tokenIndex);
    const savedTokenIndexes = await onSaveSelected(tokenIndexes);
    if (savedTokenIndexes.length === 0) {
      return;
    }
    const savedKeys = new Set(
      savedTokenIndexes
        .map((index) => tokens[index])
        .filter((token): token is TokenWithStatus => Boolean(token))
        .map((token) => getTokenGroupKey(token)),
    );
    setSelectedWordKeys((current) => {
      const next = new Set(current);
      savedKeys.forEach((key) => next.delete(key));
      return next;
    });
  }

  function isTokenInBasket(token: TokenWithStatus) {
    return selectedWordKeys.has(getTokenGroupKey(token));
  }

  function canAddToBasket(token: TokenWithStatus) {
    return entriesByKey.get(getTokenGroupKey(token))?.isSaveable ?? false;
  }

  function onToggleBasket(token: TokenWithStatus) {
    toggleSelect(getTokenGroupKey(token));
  }
  const hasNoDecks = decks.length === 0;
  const needsDeckRecovery = hasNoDecks && !isLoadingDecks && deckLoadError !== "";
  const analyzeHint = needsDeckRecovery
    ? null
    : !text.trim()
      ? "원문을 입력하면 분석할 수 있어요."
      : !selectedDeckId
        ? "읽기 덱을 선택하면 분석할 수 있어요."
        : isAnalyzing
          ? "분석 중이에요. 잠시만 기다려주세요..."
          : null;
  const messageTone = classifyMessageTone(message);
  const hasRecentlySaved = recentlySavedCount > 0;

  const slipProps: ReadingSourceSlipProps = {
    text,
    onTextChange,
    onLoadSampleText,
    decks,
    isLoadingDecks,
    hasNoDecks,
    needsDeckRecovery,
    deckLoadError,
    onRetryLoadDecks,
    selectedDeckId,
    onSelectedDeckChange,
    isAnalyzing,
    analyzeProgress,
    onCancelAnalyze,
    analyzeHint,
    onAnalyze,
    storageWarning,
  };

  return (
    <section
      className={`tab-panel reading-panel${
        hasResult ? " reading-panel--has-result" : " reading-panel--start"
      }`}
      aria-live="polite"
    >
      {/* Phase 169 -- one full-bleed V2 open-book photo is the scene anchor
          (a different shot per breakpoint, not one crop of the other): the
          desktop photo is a two-page ruled spread, so .reading-page--left/
          --right are that book's two real pages; the mobile photo shows one
          page (plus a sliver of the other, already baked into the shot), so
          --right stays unmounted there and --left becomes that single
          page's full extent. Every live piece below (slip, reader text,
          word inspector, save memo, candidate tab) is positioned as a % of
          this same frame -- see globals.css for the exact zones, tuned per
          breakpoint against where each photo actually has ruled-page room.
          Phase 173 -- the "원문 읽기" eyebrow used to be a plain text row
          sitting above this scene, its own separate header section reading
          as a leftover app title bar. Moved inside .reading-scene-v2-frame
          as a small paper tag hanging off the book's top edge instead --
          see .reading-scene-v2-eyebrow, now absolutely positioned against
          the frame rather than sitting in normal flow above it. */}
      <div className="reading-scene-v2">
        <div className="reading-scene-v2-frame">
          <picture className="reading-scene-v2-media">
            <source media="(min-width: 1024px)" srcSet={DESKTOP_ASSET} />
            <img
              className="reading-scene-v2-media-img"
              src={MOBILE_ASSET}
              alt=""
              draggable={false}
            />
          </picture>

          <span className="reading-scene-v2-eyebrow">
            <ShioriMark variant="reading" />
            원문 읽기
          </span>

          {hasResult ? (
            <ReaderMode
              originalText={analyzedText}
              tokens={tokens}
              onStatusChange={onStatusChange}
              initialSelectedTokenKey={selectedTokenKey}
              onSelectedTokenKeyChange={onSelectedTokenKeyChange}
              initialScrollFraction={scrollFraction}
              onScrollProgressChange={onScrollProgressChange}
              externalSelectRequest={externalSelectRequest}
              isTokenInBasket={isTokenInBasket}
              canAddToBasket={canAddToBasket}
              onToggleBasket={onToggleBasket}
              meaningEditItemId={meaningEditItemId}
              meaningEditDraft={meaningEditDraft}
              isSavingMeaningEdit={isSavingMeaningEdit}
              meaningEditMessage={meaningEditMessage}
              onStartMeaningEdit={onStartMeaningEdit}
              onMeaningEditDraftChange={onMeaningEditDraftChange}
              onSaveMeaningEdit={onSaveMeaningEdit}
              onCancelMeaningEdit={onCancelMeaningEdit}
              onReportMeaning={onReportMeaning}
              isSessionRestored={isSessionRestored}
              onDismissRestoredNotice={onDismissRestoredNotice}
              isTextCollapsed={isTextCollapsed}
              onToggleTextCollapsed={onToggleTextCollapsed}
              onResetSession={onResetSession}
              showSlip={showForm}
              slipProps={slipProps}
            />
          ) : (
            <>
              <div className="reading-page reading-page--left reading-page--start">
                <ReadingSourceSlip {...slipProps} />
              </div>
              <div className="reading-page reading-page--right">
                <div className="reading-page-idle">
                  <ShioriGuideCard
                    variant="reading"
                    size="md"
                    message="원문을 붙여넣으면 여기서 함께 읽고, 모르는 단어는 단어 노트에 담아요."
                  />
                </div>
              </div>
            </>
          )}

          {summary ? (
            <div className="reading-save-memo" aria-label="저장 바구니">
              <div className="reading-save-memo-count">
                <FolderIcon className="reading-save-memo-icon" />
                <span>
                  선택 <strong>{selectedCount}</strong>개
                </span>
                <span className="reading-save-memo-saveable">
                  저장 가능 {summary.saveableCount}개
                </span>
              </div>
              {selectedCount > 0 ? (
                <button
                  type="button"
                  className="reader-bookmark-button reading-save-memo-button"
                  onClick={() => void handleSaveSelected()}
                  disabled={isSavingBatch}
                >
                  <FolderIcon className="button-icon" />
                  {isSavingBatch ? "저장 중..." : `선택 저장 (${selectedCount})`}
                </button>
              ) : summary.saveableCount > 0 ? (
                <p className="reading-save-memo-hint">
                  목록에서 단어를 선택하면 한번에 저장해요.
                </p>
              ) : null}
              {message ? (
                <p
                  className={`reading-save-memo-message reading-save-memo-message--${messageTone}`}
                >
                  {message}
                </p>
              ) : null}
              {hasRecentlySaved ? (
                <button
                  type="button"
                  className="reader-bookmark-button reading-save-memo-button reading-save-memo-study"
                  onClick={onStartStudyFromSaved}
                >
                  저장한 단어 {recentlySavedCount}개 복습
                </button>
              ) : null}
              <button
                type="button"
                className="reading-save-memo-link"
                onClick={onGoToVocab}
              >
                어휘 노트 보기
              </button>
            </div>
          ) : null}

          {hasResult ? (
            <ReadingVocabPanel
              entries={entries}
              selectedTokenKey={selectedTokenKey}
              onSelectToken={handleVocabPanelSelect}
              selectedWordKeys={selectedWordKeys}
              onToggleSelect={toggleSelect}
              onReplaceSelection={replaceSelection}
              onClearSelection={clearSelection}
            />
          ) : null}
        </div>
      </div>

      {!summary && message ? (
        !hasResult && !isAnalyzing && messageTone === "info" ? (
          <p className="action-hint reading-status-hint">{message}</p>
        ) : (
          <p className={`message message--${messageTone}`}>{message}</p>
        )
      ) : null}

      {needsDeckRecovery && !showForm ? (
        <DeckLoadRecovery
          message={deckLoadError}
          isRetrying={isLoadingDecks}
          onRetry={onRetryLoadDecks}
        />
      ) : null}
    </section>
  );
}

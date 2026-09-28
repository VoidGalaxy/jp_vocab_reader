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
import type { ChunkAnalyzeProgress } from "./readingChunkAnalyze";
import type { Deck, TokenStatus, TokenWithStatus, VocabItem } from "./types";

// Copyright-safe, hand-written sample so first-time users can try the flow
// without pasting their own text first. Exported so page.tsx's home-tab
// "샘플로 체험하기" CTA can load the exact same text/deck-analyze pipeline
// from outside this tab without a second source of truth.
export const SAMPLE_TEXT =
  "彼は闇の中で声を聞いた。少女は約束を思い出した。騎士は剣を握り、敵から王を守った。";

const DESKTOP_ASSET = "/brand/decor/v4/v4-reading-c-folio-desktop-wide.webp";
const TALL_DESKTOP_ASSET = "/brand/decor/v4/v4-reading-c-folio-desktop-tall.webp";
const MOBILE_ASSET = "/brand/decor/v2/v2-reading-page-mobile-9x16.webp";
const PHONE_PAPER_ASSET = "/brand/decor/v4/v4-reading-washi-mobile-c-quiet.webp";

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
  tabletDocumentScrollFraction: number | null;
  onTabletDocumentScrollChange: (fraction: number) => void;
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
  tabletDocumentScrollFraction,
  onTabletDocumentScrollChange,
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
  const [isWordListOpen, setIsWordListOpen] = useState(false);
  const externalSelectRequestIdRef = useRef(0);

  function handleVocabPanelSelect(tokenIndex: number) {
    externalSelectRequestIdRef.current += 1;
    setExternalSelectRequest({
      tokenIndex,
      requestId: externalSelectRequestIdRef.current,
    });
  }
  function handleDesktopVocabSelect(tokenIndex: number) {
    handleVocabPanelSelect(tokenIndex);
    setIsWordListOpen(false);
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
      {/* Desktop uses one C folio book scene per aspect-ratio bucket. Live
          content stays inside the measured paper zones; phones and tablets
          retain their existing separate scenes. */}
      <div className="reading-scene-v2">
        <div className="reading-scene-v2-frame" data-mobile-word-list-open={isWordListOpen}>
          <picture className="reading-scene-v2-media">
            {/* Source conditions must match the desktop safe-zone variables
                in globals.css. Each scene's book core is contained; only its
                surrounding cloth bleed may be clipped at the frame edge. */}
            <source
              media="(min-width: 1500px) and (min-aspect-ratio: 2/1)"
              srcSet={DESKTOP_ASSET}
            />
            <source media="(min-width: 1024px)" srcSet={TALL_DESKTOP_ASSET} />
            <source media="(max-width: 640px)" srcSet={PHONE_PAPER_ASSET} />
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
              initialTabletDocumentScrollFraction={tabletDocumentScrollFraction}
              onTabletDocumentScrollChange={onTabletDocumentScrollChange}
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
              selectedCount={selectedCount}
              saveableCount={summary?.saveableCount ?? 0}
              isSavingBatch={isSavingBatch}
              onSaveSelected={() => void handleSaveSelected()}
              saveMessage={message}
              saveMessageTone={messageTone}
              recentlySavedCount={recentlySavedCount}
              onStartStudyFromSaved={onStartStudyFromSaved}
              onGoToVocab={onGoToVocab}
              wordListOpen={isWordListOpen}
              onToggleWordList={() => setIsWordListOpen((value) => !value)}
              wordListCount={entries.length}
              wordListContent={
                <ReadingVocabPanel
                  variant="page"
                  onClose={() => setIsWordListOpen(false)}
                  entries={entries}
                  selectedTokenKey={selectedTokenKey}
                  onSelectToken={handleDesktopVocabSelect}
                  selectedWordKeys={selectedWordKeys}
                  onToggleSelect={toggleSelect}
                  onReplaceSelection={replaceSelection}
                  onClearSelection={clearSelection}
                />
              }
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

          {hasResult ? (
            <div className="reading-vocab-mobile-only">
              <ReadingVocabPanel
                isOpen={isWordListOpen}
                onOpenChange={setIsWordListOpen}
                entries={entries}
                selectedTokenKey={selectedTokenKey}
                onSelectToken={handleDesktopVocabSelect}
                selectedWordKeys={selectedWordKeys}
                onToggleSelect={toggleSelect}
                onReplaceSelection={replaceSelection}
                onClearSelection={clearSelection}
              />
            </div>
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

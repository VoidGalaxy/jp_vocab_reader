"use client";

import { useMemo, useRef, useState, type FormEvent } from "react";
import { ShioriGuideCard, ShioriMark, ShioriStamp } from "./Shiori";
import { ReaderMode } from "./ReaderMode";
import { ReadingVocabPanel } from "./ReadingVocabPanel";
import {
  classifyMessageTone,
  computeReadingSaveSummary,
  computeReadingVocabEntries,
  getTokenGroupKey,
} from "./coverageUtils";
import type { ReadingSaveSummary, ReadingVocabEntry } from "./coverageUtils";
import {
  CardFileIcon,
  CardsIcon,
  FolderIcon,
  ShieldIcon,
  SparkleIcon,
} from "./icons";
import type { ChunkAnalyzeProgress } from "./readingChunkAnalyze";
import type { Deck, TokenStatus, TokenWithStatus, VocabItem } from "./types";

// Copyright-safe, hand-written sample so first-time users can try the flow
// without pasting their own text first. Exported so page.tsx's home-tab
// "샘플로 체험하기" CTA can load the exact same text/deck-analyze pipeline
// from outside this tab without a second source of truth.
export const SAMPLE_TEXT =
  "彼は闇の中で声を聞いた。少女は約束を思い出した。騎士は剣を握り、敵から王を守った。";

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

// ---------------------------------------------------------------------------
// ReaderSaveDock -- deliberately not a titled panel-card, a slim shelf-like
// strip sitting right under ReaderPaper.
//
// Phase 97 -- previously also owned a "빠르게 전체 저장" disclosure (a
// toggle + 5 status-count pills + 3 immediate-save-by-status buttons) that
// duplicated ReadingVocabPanel's quick-select row one screen section down:
// both dealt in the same status buckets (모르는/모르는+헷갈리는/미분류까지),
// but this one saved immediately while the tray's only changed the
// selection, waiting for the button below to actually save it. Two visibly
// different flows for the same underlying action. Removed here -- the tray's
// quick-select is now the only place to act on a whole status bucket at
// once; this dock only ever saves whatever is currently selected (via
// onSaveSelected, unchanged), same as its plain per-word "저장 대상으로
// 선택" path always did. See DESIGN.md Phase 97 note for the fuller
// rationale.
//
// Phase 99 -- unknown/uncertain classification now auto-saves a word the
// moment it's chosen in the Word Inspector (see handleReadingStatusChange
// in page.tsx), so this dock is no longer "the" save action -- it's an
// auxiliary tool for saving several words at once. Copy below says
// "선택한 단어" (selected words) rather than "담은 단어" (words placed in
// the basket) so it doesn't read as a separate, competing save flow.
// ---------------------------------------------------------------------------
type ReaderSaveDockProps = {
  summary: ReadingSaveSummary;
  selectedCount: number;
  isSavingBatch: boolean;
  onSaveSelected: () => void;
  recentlySavedCount: number;
  onStartStudyFromSaved: () => void;
  onGoToVocab: () => void;
  message: string;
  messageTone: ReturnType<typeof classifyMessageTone>;
};

function ReaderSaveDock({
  summary,
  selectedCount,
  isSavingBatch,
  onSaveSelected,
  recentlySavedCount,
  onStartStudyFromSaved,
  onGoToVocab,
  message,
  messageTone,
}: ReaderSaveDockProps) {
  const hasRecentlySaved = recentlySavedCount > 0;

  return (
    <section className="reading-action-dock" aria-label="저장 바구니">
      {/* Phase 150 -- the count row used to share a plain flex line with the
          primary button (Phase 65's .save-tray-shelf-row), sitting directly
          on the same page background as everything else in Reading, with
          nothing marking it as its own object. It now sits on
          reading-selected-memo-strip.webp -- a loose torn-paper strip with
          taped corners and ring holes (frontend/public/brand/decor/
          phase145/), reserved since Phase 145's own rebuild plan named this
          exact spot ("선택한 단어는 loose memo strip 위에"). The image
          determines this element's shape/identity (a strip, not a bar); the
          real count/badges are still live DOM text laid over its blank
          center -- percentage padding (see .save-dock-memo-strip) keeps
          them clear of the tape/holes at any width, unlike a fixed-pixel
          crop. */}
      <div className="save-dock-memo-strip">
        <div className="save-dock-count">
          <FolderIcon className="save-dock-icon" />
          <span>
            선택한 단어 <strong className="save-dock-count-badge">{selectedCount}</strong>개
          </span>
          <span className="save-dock-saveable-chip">저장 가능 {summary.saveableCount}개</span>
        </div>
      </div>

      {/* Casual Sticker Reader (Phase 65) -- the primary action's own row,
          separated from the memo strip above. Phase 150 -- the button is
          now a small notched bookmark tag (.reader-bookmark-button, same
          screen-accent-colored family as .reader-start-cta) instead of a
          full gradient CTA, so save/idle states both read as a stationery
          action, not an admin control-panel button. */}
      <div className="save-tray-shelf-row">
        {selectedCount > 0 ? (
          <button
            type="button"
            className="save-dock-primary-button reader-bookmark-button"
            onClick={onSaveSelected}
            disabled={isSavingBatch}
          >
            <FolderIcon className="button-icon" />
            {isSavingBatch ? "저장 중..." : `선택한 단어 저장 (${selectedCount})`}
          </button>
        ) : (
          <ShioriGuideCard
            variant="reading"
            message="여러 단어를 한번에 저장하려면 아래 목록에서 선택하세요."
            className="save-dock-idle-hint"
          />
        )}
      </div>

      {summary.saveableCount === 0 ? (
        <p className="muted-text reading-summary-hint">
          저장 가능한 단어가 없어요. 이미 학습 중인 단어일 수 있습니다.
        </p>
      ) : null}
      {message ? (
        <p
          className={`message message--${messageTone} reading-summary-message${
            messageTone === "success" ? " message-stamped" : ""
          }`}
        >
          {messageTone === "success" ? (
            <ShioriStamp variant="success" className="reading-summary-message-stamp" />
          ) : null}
          <span>{message}</span>
        </p>
      ) : null}

      {/* Before anything is saved there is no study CTA at all -- same idea as
          .save-dock-idle-hint above: a permanently-disabled primary button was
          taking hero weight while being the one thing the user can't do yet.
          Once a save lands it becomes the emphasized next step. */}
      <div className="reading-summary-next-actions">
        {hasRecentlySaved ? (
          <button
            type="button"
            className="reading-summary-cta-button reading-summary-cta-ready reader-bookmark-button"
            onClick={onStartStudyFromSaved}
          >
            <CardsIcon className="button-icon" />
            저장한 단어 {recentlySavedCount}개 바로 복습
          </button>
        ) : null}
        <button type="button" className="reading-summary-link-button" onClick={onGoToVocab}>
          <CardFileIcon className="button-icon" />
          어휘 노트 보기
        </button>
      </div>
    </section>
  );
}

// Shown wherever the deck select would otherwise be an empty dropdown the
// user can do nothing with. Rendered either inside the input form or, when
// the form is collapsed away (restored session with the text folded), on its
// own in the panel body -- never both at once.
function DeckLoadRecovery({
  message,
  isRetrying,
  onRetry,
}: {
  message: string;
  isRetrying: boolean;
  onRetry: () => void;
}) {
  return (
    <div className="reading-deck-recovery" role="alert">
      <p className="reading-deck-recovery-text">
        {message} 읽기 덱이 없어 분석을 시작할 수 없어요.
      </p>
      <button
        type="button"
        className="secondary-button compact-button"
        onClick={onRetry}
        disabled={isRetrying}
      >
        {isRetrying ? "불러오는 중..." : "덱 다시 불러오기"}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ReaderStartScene -- Phase 121. Previously the pre-analyze view was
// .reader-start-card: a bordered/shadowed form card (header, a whole
// AppEmptyState illustration+guide block, a taped textarea, a footer row)
// -- structurally still "form card", just skinned warmer. This replaces it
// with the same open-book language Phase 119 built for the analyzed
// result (.reader-desk-scene's border/shadow/paper background, ruled-line
// texture) so arriving at Reading and finishing an analysis feel like the
// same notebook, not two different card systems. The sample-CTA guide
// shrinks from a whole illustrated card to one quiet link (matching
// Home's .home-cover-sample), and the idle "덱을 선택하고 원문을 입력한
//뒤..." fallback paragraph that used to live below this in
// .reader-workspace is dropped entirely -- the scene's own title/
// placeholder/button already say the same thing. Behavior (onAnalyze
// submit, onLoadSampleText, deck select, cancel) is unchanged from before;
// only composition and copy length changed.
// ---------------------------------------------------------------------------
type ReaderStartSceneProps = {
  text: string;
  onTextChange: (text: string) => void;
  onLoadSampleText: () => void;
  decks: Deck[];
  isLoadingDecks: boolean;
  hasNoDecks: boolean;
  needsDeckRecovery: boolean;
  deckLoadError: string;
  onRetryLoadDecks: () => void;
  selectedDeckId: string;
  onSelectedDeckChange: (deckId: string) => void;
  isAnalyzing: boolean;
  analyzeProgress: ChunkAnalyzeProgress | null;
  onCancelAnalyze: () => void;
  analyzeHint: string | null;
  onAnalyze: (event: FormEvent<HTMLFormElement>) => void;
  storageWarning: string;
};

function ReaderStartScene({
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
}: ReaderStartSceneProps) {
  const hasChunkProgress = isAnalyzing && !!analyzeProgress && analyzeProgress.total > 1;

  return (
    <section className="reader-start-scene">
      <div className="reader-start-heading">
        <span className="reading-input-eyebrow">
          <ShioriMark variant="reading" />
          원문 읽기
        </span>
        <h2 className="reader-start-title">원문으로 읽고 바로 노트에 담기</h2>
        <p className="reader-start-subtitle">
          원문을 붙여넣고 모르는 단어를 바로 담아보세요.
        </p>
      </div>

      <form className="reader-start-form" onSubmit={onAnalyze}>
        <label htmlFor="reading-source-text" className="sr-only-label">
          원문
        </label>
        <div className="reader-start-page">
          <textarea
            id="reading-source-text"
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
            placeholder="彼は闇の中で声を聞いた。少女は約束を思い出した。"
            rows={6}
          />
          {!text.trim() ? (
            <button
              type="button"
              className="reader-start-sample-link"
              onClick={onLoadSampleText}
            >
              <SparkleIcon className="button-icon" />
              샘플 문장으로 체험
            </button>
          ) : null}
        </div>

        {/* Loading feedback lives on the scene itself now, not as a
            separate line below the whole card. Chunked analysis keeps its
            real progress bar + cancel escape hatch; a quick single-chunk
            analyze (the common case) already says "펼치는 중..." right on
            the submit button below, so it only needs an aria-live
            announcement, not a second visible line saying the same thing. */}
        {hasChunkProgress ? (
          <div className="reading-analyze-progress" role="status" aria-live="polite">
            <p className="reading-analyze-progress-label">
              긴 원문을 문단·문장 단위로 나눠 분석하고 있습니다.
            </p>
            <p className="reading-analyze-progress-count">
              {analyzeProgress!.current} / {analyzeProgress!.total} 조각 분석 중
            </p>
            <div
              className="reading-analyze-progress-bar"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={analyzeProgress!.total}
              aria-valuenow={analyzeProgress!.current}
            >
              <div
                className="reading-analyze-progress-bar-fill"
                style={{
                  width: `${Math.round(
                    (analyzeProgress!.current / analyzeProgress!.total) * 100,
                  )}%`,
                }}
              />
            </div>
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={onCancelAnalyze}
            >
              분석 취소
            </button>
          </div>
        ) : isAnalyzing ? (
          <p className="sr-only-label" role="status">
            원문을 읽는 중이에요. 잠시만 기다려주세요...
          </p>
        ) : null}

        <div className="reader-start-footer">
          {needsDeckRecovery ? (
            <DeckLoadRecovery
              message={deckLoadError}
              isRetrying={isLoadingDecks}
              onRetry={onRetryLoadDecks}
            />
          ) : (
            <label className="reading-deck-picker">
              <FolderIcon className="reading-deck-picker-icon" />
              <select
                value={selectedDeckId}
                onChange={(event) => onSelectedDeckChange(event.target.value)}
                aria-label="읽기 덱"
                disabled={hasNoDecks}
              >
                {hasNoDecks ? (
                  <option value="">
                    {isLoadingDecks
                      ? "덱을 불러오는 중..."
                      : "사용할 수 있는 덱이 없어요"}
                  </option>
                ) : (
                  decks.map((deck) => (
                    <option key={deck.id} value={String(deck.id)}>
                      {deck.name}
                    </option>
                  ))
                )}
              </select>
            </label>
          )}
          <button
            type="submit"
            className="reader-start-cta reader-bookmark-button"
            disabled={isAnalyzing || !selectedDeckId || !text.trim()}
          >
            {isAnalyzing ? (
              "펼치는 중..."
            ) : (
              <>
                <SparkleIcon className="button-icon" />
                원문 펼치기
              </>
            )}
          </button>
        </div>
        {analyzeHint ? <p className="action-hint">{analyzeHint}</p> : null}
      </form>

      <p className="muted-text copyright-note reader-start-copyright">
        <ShieldIcon className="copyright-note-icon" />
        <span>원문 전체는 서버에 저장하지 않아요.</span>
      </p>
      {storageWarning ? (
        <p className="muted-text reading-storage-warning">{storageWarning}</p>
      ) : null}
    </section>
  );
}

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

  return (
    <section
      className={`tab-panel reading-panel${
        hasResult ? " reading-panel--has-result" : " reading-panel--start"
      }`}
      aria-live="polite"
    >
      {hasResult ? (
        // Post-analysis "manuscript tray" -- a quiet, un-boxed re-edit form
        // collapsed by default (see ReaderMode's "원문 입력 펼치기"
        // toggle). Unchanged from before Phase 121: this phase's target is
        // the pre-analyze scene below, not this recovery/re-edit path.
        <section className="reading-input-open">
          <form className="analyze-form" onSubmit={onAnalyze}>
            <label htmlFor="reading-source-text" className="sr-only-label">
              원문
            </label>
            {showForm ? (
              <>
                <div className="reading-note-sheet">
                  <textarea
                    id="reading-source-text"
                    value={text}
                    onChange={(event) => onTextChange(event.target.value)}
                    placeholder="彼は闇の中で声を聞いた。少女は約束を思い出した。"
                    rows={4}
                  />
                </div>
                <div className="reading-input-footer">
                  {needsDeckRecovery ? (
                    <DeckLoadRecovery
                      message={deckLoadError}
                      isRetrying={isLoadingDecks}
                      onRetry={onRetryLoadDecks}
                    />
                  ) : (
                    <label className="reading-deck-picker">
                      <FolderIcon className="reading-deck-picker-icon" />
                      <select
                        value={selectedDeckId}
                        onChange={(event) => onSelectedDeckChange(event.target.value)}
                        aria-label="읽기 덱"
                        disabled={hasNoDecks}
                      >
                        {hasNoDecks ? (
                          <option value="">
                            {isLoadingDecks
                              ? "덱을 불러오는 중..."
                              : "사용할 수 있는 덱이 없어요"}
                          </option>
                        ) : (
                          decks.map((deck) => (
                            <option key={deck.id} value={String(deck.id)}>
                              {deck.name}
                            </option>
                          ))
                        )}
                      </select>
                    </label>
                  )}
                  <button
                    type="submit"
                    className="reading-open-button reader-bookmark-button"
                    disabled={isAnalyzing || !selectedDeckId || !text.trim()}
                  >
                    {isAnalyzing ? (
                      "펼치는 중..."
                    ) : (
                      <>
                        <SparkleIcon className="button-icon" />
                        원문 펼치기
                      </>
                    )}
                  </button>
                </div>
                {analyzeHint ? <p className="action-hint">{analyzeHint}</p> : null}
              </>
            ) : null}
          </form>

          {isAnalyzing && analyzeProgress && analyzeProgress.total > 1 ? (
            <div className="reading-analyze-progress" role="status" aria-live="polite">
              <p className="reading-analyze-progress-label">
                긴 원문을 문단·문장 단위로 나눠 분석하고 있습니다.
              </p>
              <p className="reading-analyze-progress-count">
                {analyzeProgress.current} / {analyzeProgress.total} 조각 분석 중
              </p>
              <div
                className="reading-analyze-progress-bar"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={analyzeProgress.total}
                aria-valuenow={analyzeProgress.current}
              >
                <div
                  className="reading-analyze-progress-bar-fill"
                  style={{
                    width: `${Math.round(
                      (analyzeProgress.current / analyzeProgress.total) * 100,
                    )}%`,
                  }}
                />
              </div>
              <button
                type="button"
                className="ghost-button compact-button"
                onClick={onCancelAnalyze}
              >
                분석 취소
              </button>
            </div>
          ) : null}

          <p className="muted-text copyright-note">
            <ShieldIcon className="copyright-note-icon" />
            <span>원문 전체는 서버에 저장하지 않아요.</span>
          </p>
          {storageWarning ? (
            <p className="muted-text reading-storage-warning">{storageWarning}</p>
          ) : null}
        </section>
      ) : (
        <ReaderStartScene
          text={text}
          onTextChange={onTextChange}
          onLoadSampleText={onLoadSampleText}
          decks={decks}
          isLoadingDecks={isLoadingDecks}
          hasNoDecks={hasNoDecks}
          needsDeckRecovery={needsDeckRecovery}
          deckLoadError={deckLoadError}
          onRetryLoadDecks={onRetryLoadDecks}
          selectedDeckId={selectedDeckId}
          onSelectedDeckChange={onSelectedDeckChange}
          isAnalyzing={isAnalyzing}
          analyzeProgress={analyzeProgress}
          onCancelAnalyze={onCancelAnalyze}
          analyzeHint={analyzeHint}
          onAnalyze={onAnalyze}
          storageWarning={storageWarning}
        />
      )}

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

      {/* Phase 114 -- ReaderWorkspace used to be its own bordered/shadowed
          "stage" box (.library-card-stage) wrapping ReaderPaper + a dashed
          ring-spine down the left edge, so the open reading page sat inside
          a second card rather than being the scene's own artifact -- against
          the mockup, where the book/page IS the desk scene, not a panel on
          top of it. Now a plain layout container: ReaderPaper (the one real
          "page" surface, with its own tape-corner/ruled-paper treatment),
          ReaderSaveDock (slim dashed shelf strip), and CandidateDrawer
          (ReadingVocabPanel's sticker tray) sit directly on the board
          background as three distinct desk objects, spaced by gap alone. */}
      <div className="reader-workspace">
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
          />
        ) : null}

        {summary ? (
          <ReaderSaveDock
            summary={summary}
            selectedCount={selectedCount}
            isSavingBatch={isSavingBatch}
            onSaveSelected={() => void handleSaveSelected()}
            recentlySavedCount={recentlySavedCount}
            onStartStudyFromSaved={onStartStudyFromSaved}
            onGoToVocab={onGoToVocab}
            message={message}
            messageTone={messageTone}
          />
        ) : null}

        {/* CandidateDrawer (ReadingVocabPanel) follows the reader card and
            save tray, not before them -- for long chunk-analyzed texts a
            dense candidate list would otherwise push the actual reading
            experience (the core screen) far down the page. Collapsed by
            default: search/filter/bulk actions only show once opened. */}
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
    </section>
  );
}

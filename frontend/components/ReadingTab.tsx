"use client";

import { useMemo, useRef, useState, type FormEvent } from "react";
import { BrandEmptyIllustration, BrandSectionBadge, StudyCompanion } from "./BrandElements";
import { ReaderMode } from "./ReaderMode";
import { ReadingVocabPanel } from "./ReadingVocabPanel";
import {
  classifyMessageTone,
  computeReadingSaveSummary,
  computeReadingVocabEntries,
  getTokenGroupKey,
} from "./coverageUtils";
import type { ReadingSaveMode, ReadingVocabEntry } from "./coverageUtils";
import { CardsIcon, FolderIcon, ShieldIcon, SparkleIcon } from "./icons";
import type { ChunkAnalyzeProgress } from "./readingChunkAnalyze";
import type { Deck, TokenStatus, TokenWithStatus, VocabItem } from "./types";

// Copyright-safe, hand-written sample so first-time users can try the flow
// without pasting their own text first. Exported so page.tsx's home-tab
// "샘플로 체험하기" CTA can load the exact same text/deck-analyze pipeline
// from outside this tab, and so this component can tell "the user is
// looking at the sample" apart from their own text (see isSampleText
// below) without a second source of truth.
export const SAMPLE_TEXT =
  "彼は闇の中で声を聞いた。少女は約束を思い出した。騎士は剣を握り、敵から王を守った。";

type ReadingTabProps = {
  text: string;
  analyzedText: string;
  tokens: TokenWithStatus[];
  vocabItems: VocabItem[];
  decks: Deck[];
  selectedDeckId: string;
  isAnalyzing: boolean;
  analyzeProgress: ChunkAnalyzeProgress | null;
  onCancelAnalyze: () => void;
  message: string;
  storageWarning: string;
  isTextCollapsed: boolean;
  isSavingBatch: boolean;
  canStartFromSaved: boolean;
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
  onSaveBatch: (mode: ReadingSaveMode) => void;
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

const saveButtons: Array<{
  mode: ReadingSaveMode;
  label: string;
  hint: string;
  variant: "secondary" | "ghost";
}> = [
  {
    mode: "unknown_only",
    label: "모르는 단어 저장",
    hint: "unknown 상태 후보만 저장",
    variant: "secondary",
  },
  {
    mode: "unknown_uncertain",
    label: "모르는+헷갈리는 단어 저장",
    hint: "unknown + uncertain 저장",
    variant: "secondary",
  },
  {
    mode: "all_unclassified",
    label: "미분류까지 저장",
    hint: "unknown + uncertain + unclassified 저장",
    variant: "ghost",
  },
];

export function ReadingTab({
  text,
  analyzedText,
  tokens,
  vocabItems,
  decks,
  selectedDeckId,
  isAnalyzing,
  analyzeProgress,
  onCancelAnalyze,
  message,
  storageWarning,
  isTextCollapsed,
  isSavingBatch,
  canStartFromSaved,
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
  onSaveBatch,
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
  // word-list panel's checkboxes and the Word Inspector's "저장 바구니에
  // 담기" toggle read/write the exact same selection instead of each owning
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
  // Reconciles the raw key Set against what's actually selectable right now
  // (a re-analysis can swap tokens out from under an already-built
  // selection) -- every count/action below only ever sees valid, currently
  // saveable entries.
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
  // Onboarding-only guide note (design improvement 5) -- derived from
  // existing props (no new dismissed-state storage key needed) so it only
  // shows while the user is actually looking at the sample text, and
  // disappears on its own once they analyze their own real text.
  const isSampleText = analyzedText === SAMPLE_TEXT;
  const analyzeHint = !text.trim()
    ? "원문을 입력하면 분석할 수 있습니다."
    : !selectedDeckId
      ? "읽기 덱을 선택하면 분석할 수 있습니다."
      : isAnalyzing
        ? "분석 중입니다. 잠시만 기다려주세요..."
        : null;
  const messageTone = classifyMessageTone(message);

  return (
    <section className="tab-panel reading-panel" aria-live="polite">
      <div className="reading-hero">
        <h2 className="reading-hero-title">원문으로 읽고 바로 노트에 담기</h2>
        <p className="reading-hero-subtitle">
          원문을 붙여넣고 모르는 단어를 바로 담아보세요.
        </p>
      </div>

      {isSessionRestored && hasResult ? (
        <div className="reading-restored-banner">
          <span>
            이전 작업이 복원되었습니다. 원문·분석 결과·선택한 단어와 마지막
            읽던 위치를 이어서 볼 수 있습니다.
          </span>
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={onDismissRestoredNotice}
          >
            확인
          </button>
        </div>
      ) : null}

      <section className="panel-card reading-input-card">
        <div className="panel-card-header">
          <h3 className="panel-card-title">원문 입력</h3>
          <p className="panel-card-description">
            읽고 싶은 일본어 문장을 붙여넣으세요.
          </p>
        </div>
        <form className="analyze-form" onSubmit={onAnalyze}>
          <div className="reading-input-header">
            <label htmlFor="reading-source-text">원문</label>
            <div className="reading-input-header-actions">
              {hasResult ? (
                <button
                  type="button"
                  className="ghost-button compact-button"
                  onClick={onToggleTextCollapsed}
                >
                  {isTextCollapsed ? "원문 입력 펼치기" : "원문 입력 접기"}
                </button>
              ) : null}
              {hasResult || text ? (
                <button
                  type="button"
                  className="ghost-button compact-button"
                  onClick={onResetSession}
                >
                  현재 읽기 작업 초기화
                </button>
              ) : null}
            </div>
          </div>

          {showForm ? (
            <>
              {!hasResult && !text.trim() ? (
                <div className="reading-empty-guide">
                  <StudyCompanion mood="reading" />
                  <p>읽고 싶은 일본어 문장을 붙여넣고 분석해보세요.</p>
                  <p className="muted-text">
                    모르는 단어를 클릭해 뜻과 읽기를 확인할 수 있습니다.
                  </p>
                  <button
                    type="button"
                    className="ghost-button compact-button"
                    onClick={onLoadSampleText}
                  >
                    <SparkleIcon className="button-icon" />
                    샘플 문장으로 체험
                  </button>
                </div>
              ) : null}
              <textarea
                id="reading-source-text"
                value={text}
                onChange={(event) => onTextChange(event.target.value)}
                placeholder="彼は闇の中で声を聞いた。少女は約束を思い出した。"
                rows={6}
              />
              <div className="analyze-options">
                <label className="inline-field">
                  읽기 덱
                  <select
                    value={selectedDeckId}
                    onChange={(event) => onSelectedDeckChange(event.target.value)}
                  >
                    {decks.map((deck) => (
                      <option key={deck.id} value={String(deck.id)}>
                        {deck.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="actions actions-with-hint">
                <button
                  type="submit"
                  disabled={isAnalyzing || !selectedDeckId || !text.trim()}
                >
                  {isAnalyzing ? (
                    "분석 중..."
                  ) : (
                    <>
                      <SparkleIcon className="button-icon" />
                      읽기 분석
                    </>
                  )}
                </button>
                {analyzeHint ? <p className="action-hint">{analyzeHint}</p> : null}
              </div>
            </>
          ) : null}
        </form>

        {isAnalyzing && analyzeProgress && analyzeProgress.total > 1 ? (
          <div
            className="reading-analyze-progress"
            role="status"
            aria-live="polite"
          >
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
          <span>
            원문 전체는 저장되지 않고 이 브라우저에만 임시 보관돼요. 저장한
            단어에는 짧은 예문만 남습니다.
          </span>
        </p>
        {storageWarning ? (
          <p className="muted-text reading-storage-warning">{storageWarning}</p>
        ) : null}
      </section>

      {!summary && message ? (
        !hasResult && !isAnalyzing && messageTone === "info" ? (
          // Analysis genuinely ran and found nothing learnable (as opposed
          // to a network/analysis error, which keeps the plain inline
          // message below) -- give it the same icon+text empty-state
          // treatment as every other "nothing here" moment in the app
          // instead of a bare one-line message.
          <div className="reading-empty-guide">
            <BrandEmptyIllustration icon={SparkleIcon} />
            <p>{message}</p>
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={onLoadSampleText}
            >
              <SparkleIcon className="button-icon" />
              샘플 문장으로 체험
            </button>
          </div>
        ) : (
          <p className={`message message--${messageTone}`}>{message}</p>
        )
      ) : null}

      {summary && isSampleText ? (
        <div className="panel-card note-card reading-onboarding-note">
          <span className="memo-label">가이드</span>
          <p className="reading-onboarding-note-title">
            샘플로 핵심 흐름을 체험해보세요
          </p>
          <p className="muted-text">
            1 단어 클릭해 뜻 확인 → 2 모르는 단어 저장 → 3 저장한 단어로
            바로 학습
          </p>
        </div>
      ) : null}

      {summary ? (
        <div className="reader-toolbar" role="group" aria-label="읽기 작업 상태">
          <span className="reader-toolbar-chip">
            저장 가능 {summary.saveableCount}개
          </span>
          <span className="reader-toolbar-chip reader-toolbar-chip-accent">
            바구니에 담음 {selectedCount}개
          </span>
        </div>
      ) : null}

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
        />
      ) : isAnalyzing ? (
        (!analyzeProgress || analyzeProgress.total <= 1) ? (
          <p className="empty reading-loading-hint" role="status">
            분석 중입니다. 잠시만 기다려주세요...
          </p>
        ) : null
      ) : message ? null : (
        // Whenever there's a message (analysis failed, found zero words,
        // sample just loaded, session reset, ...), it already explains
        // what happened -- this generic "please analyze" prompt would
        // otherwise sit right below it and contradict it.
        <p className="empty">
          덱을 선택하고 원문을 입력한 뒤 읽기 분석을 눌러주세요.
        </p>
      )}

      {summary ? (
        <section className="panel-card save-tray">
          <div className="panel-card-header save-tray-header">
            <div>
              <h3 className="panel-card-title">
                <BrandSectionBadge icon={FolderIcon} />
                저장 바구니
              </h3>
              <p className="panel-card-description">
                담은 단어를 확인하고 저장하세요.
              </p>
            </div>
            <span className="save-tray-count-badge">
              {selectedCount}개 담음
            </span>
          </div>

          <div className="save-tray-stats" role="group" aria-label="상태별 단어 수">
            <span className="save-tray-stat-pill save-tray-stat-new">
              새 단어 {summary.newCount}개
            </span>
            <span className="save-tray-stat-pill save-tray-stat-unknown">
              모르는 단어 {summary.unknownCount}개
            </span>
            <span className="save-tray-stat-pill save-tray-stat-uncertain">
              헷갈리는 단어 {summary.uncertainCount}개
            </span>
            <span className="save-tray-stat-pill save-tray-stat-unclassified">
              미분류 {summary.unclassifiedCount}개
            </span>
            <span className="save-tray-stat-pill save-tray-stat-known">
              아는 단어 {summary.knownCount}개
            </span>
          </div>

          <button
            type="button"
            className="save-tray-primary-button"
            onClick={() => void handleSaveSelected()}
            disabled={selectedCount === 0 || isSavingBatch}
            title={
              selectedCount === 0
                ? "원문에서 단어를 눌러 바구니에 담아주세요."
                : undefined
            }
          >
            <FolderIcon className="button-icon" />
            {isSavingBatch ? "저장 중..." : `담은 단어 저장 (${selectedCount})`}
          </button>

          <div className="save-tray-quick-save">
            <span className="save-tray-quick-save-label">빠르게 전체 저장</span>
            <div className="reading-summary-actions">
              {saveButtons.map(({ mode, label, hint, variant }) => (
                <button
                  key={mode}
                  type="button"
                  className={`${variant === "ghost" ? "ghost-button" : "secondary-button"} reading-summary-save-button`}
                  onClick={() => onSaveBatch(mode)}
                  disabled={isSavingBatch || summary.saveableCount === 0}
                  title={hint}
                >
                  {isSavingBatch ? "저장 중..." : label}
                </button>
              ))}
            </div>
          </div>

          {summary.saveableCount === 0 ? (
            <p className="muted-text reading-summary-hint">
              저장 가능한 단어가 없어요. 이미 학습 중인 단어일 수 있습니다.
            </p>
          ) : null}
          {message ? (
            <p className={`message message--${messageTone} reading-summary-message`}>
              {message}
            </p>
          ) : null}

          <div className="reading-summary-next-actions">
            <button
              type="button"
              className="reading-summary-cta-button"
              onClick={onStartStudyFromSaved}
              disabled={!canStartFromSaved}
              title={
                canStartFromSaved
                  ? undefined
                  : "먼저 단어를 저장하면 바로 학습으로 이동할 수 있습니다."
              }
            >
              <CardsIcon className="button-icon" />
              저장한 단어로 바로 학습
            </button>
            <button
              type="button"
              className="secondary-button reading-summary-cta-button"
              onClick={onGoToVocab}
            >
              어휘 노트 보기
            </button>
          </div>
        </section>
      ) : null}

      {/* Word list follows the reading card and save tray, not before them
          -- for long chunk-analyzed texts a dense candidate list would
          otherwise push the actual reading experience (the core screen)
          far down the page. Collapsed by default (design: word list is a
          secondary/reference panel, not the main event). */}
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
    </section>
  );
}

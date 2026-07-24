"use client";

import { useMemo, useRef, useState, type FormEvent } from "react";
import { AppEmptyState } from "./BrandElements";
import { ShioriStamp } from "./Shiori";
import { ReaderMode } from "./ReaderMode";
import { ReadingVocabPanel } from "./ReadingVocabPanel";
import {
  classifyMessageTone,
  computeReadingSaveSummary,
  computeReadingVocabEntries,
  getTokenGroupKey,
} from "./coverageUtils";
import type { ReadingSaveMode, ReadingSaveSummary, ReadingVocabEntry } from "./coverageUtils";
import {
  CardFileIcon,
  CardsIcon,
  ChevronDownIcon,
  FolderIcon,
  ShieldIcon,
  SparkleIcon,
} from "./icons";
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
    hint: "모르는 단어로 표시한 후보만 저장해요",
    variant: "secondary",
  },
  {
    mode: "unknown_uncertain",
    label: "모르는+헷갈리는 단어 저장",
    hint: "모르는 단어와 헷갈리는 단어를 함께 저장해요",
    variant: "secondary",
  },
  {
    mode: "all_unclassified",
    label: "미분류까지 저장",
    hint: "모르는 단어, 헷갈리는 단어, 아직 분류하지 않은 단어까지 모두 저장해요",
    variant: "ghost",
  },
];

// ---------------------------------------------------------------------------
// ReaderRestoreBanner -- was a full-width banner, now a small dismissible
// pill that lives inside ReaderCompactToolbar instead of its own stacked
// row above everything else.
// ---------------------------------------------------------------------------
function ReaderRestoreBanner({ onDismiss }: { onDismiss: () => void }) {
  return (
    <span className="reading-restored-chip">
      이전 작업 복원됨
      <button
        type="button"
        className="reading-restored-chip-dismiss"
        onClick={onDismiss}
      >
        확인
      </button>
    </span>
  );
}

// ---------------------------------------------------------------------------
// ReaderCompactToolbar -- everything that used to compete with the reader
// for first-glance attention (복원 안내, 원문 입력 토글, 새 원문, 저장 가능/
// 바구니 chip) lives in this one compact row instead of a stacked hero
// title + banner + header-actions row + chip row, so ReaderPaper sits much
// closer to the top of the screen once a result exists.
// ---------------------------------------------------------------------------
type ReaderCompactToolbarProps = {
  isSessionRestored: boolean;
  onDismissRestoredNotice: () => void;
  isTextCollapsed: boolean;
  onToggleTextCollapsed: () => void;
  onResetSession: () => void;
  summary: ReadingSaveSummary | null;
  selectedCount: number;
};

function ReaderCompactToolbar({
  isSessionRestored,
  onDismissRestoredNotice,
  isTextCollapsed,
  onToggleTextCollapsed,
  onResetSession,
  summary,
  selectedCount,
}: ReaderCompactToolbarProps) {
  // "원문 입력 펼치기/접기"와 "새 원문"은 둘 다 자주 쓰는 액션이 아니라
  // "원문을 어떻게 할지" 계열이라 하나의 토글 뒤로 접어 둔다 -- 기본 노출은
  // 토글 버튼 하나뿐, 눌렀을 때만 두 액션이 같은 줄에 나타난다.
  const [isManageOpen, setIsManageOpen] = useState(false);
  return (
    <div className="reader-compact-toolbar" role="group" aria-label="읽기 도구">
      {isSessionRestored ? <ReaderRestoreBanner onDismiss={onDismissRestoredNotice} /> : null}
      <button
        type="button"
        className="ghost-button compact-button"
        onClick={() => setIsManageOpen((value) => !value)}
        aria-expanded={isManageOpen}
      >
        <ChevronDownIcon
          className={`reading-vocab-collapse-icon${
            isManageOpen ? "" : " reading-vocab-collapse-icon-collapsed"
          }`}
        />
        원문 관리
      </button>
      {isManageOpen ? (
        <>
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={onToggleTextCollapsed}
          >
            {isTextCollapsed ? "원문 입력 펼치기" : "원문 입력 접기"}
          </button>
          <button type="button" className="ghost-button compact-button" onClick={onResetSession}>
            새 원문
          </button>
        </>
      ) : null}
      {summary ? (
        <>
          <span className="reader-toolbar-chip">저장 가능 {summary.saveableCount}개</span>
          <span className="reader-toolbar-chip reader-toolbar-chip-accent">
            바구니에 담음 {selectedCount}개
          </span>
        </>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ReaderSaveDock -- deliberately not a titled panel-card, a slim shelf-like
// strip sitting right under ReaderPaper. Owns its own "빠르게 전체 저장"
// disclosure state -- nothing outside this component needs it.
// ---------------------------------------------------------------------------
type ReaderSaveDockProps = {
  summary: ReadingSaveSummary;
  selectedCount: number;
  isSavingBatch: boolean;
  onSaveSelected: () => void;
  onSaveBatch: (mode: ReadingSaveMode) => void;
  canStartFromSaved: boolean;
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
  onSaveBatch,
  canStartFromSaved,
  onStartStudyFromSaved,
  onGoToVocab,
  message,
  messageTone,
}: ReaderSaveDockProps) {
  const [isQuickSaveOpen, setIsQuickSaveOpen] = useState(false);

  return (
    <section className="reader-save-dock" aria-label="저장 바구니">
      <div className="save-dock-count">
        <FolderIcon className="save-dock-icon" />
        <span>
          담은 단어 <strong>{selectedCount}</strong>개
        </span>
      </div>

      {selectedCount > 0 ? (
        <button
          type="button"
          className="save-dock-primary-button"
          onClick={onSaveSelected}
          disabled={isSavingBatch}
        >
          <FolderIcon className="button-icon" />
          {isSavingBatch ? "저장 중..." : `담은 단어 저장 (${selectedCount})`}
        </button>
      ) : (
        <p className="save-dock-idle-hint muted-text">
          원문에서 단어를 눌러 바구니에 담아보세요.
        </p>
      )}

      <div className="save-tray-quick-save">
        <button
          type="button"
          className="ghost-button compact-button save-tray-quick-save-toggle"
          onClick={() => setIsQuickSaveOpen((value) => !value)}
          aria-expanded={isQuickSaveOpen}
        >
          <ChevronDownIcon
            className={`reading-vocab-collapse-icon${
              isQuickSaveOpen ? "" : " reading-vocab-collapse-icon-collapsed"
            }`}
          />
          빠르게 전체 저장
        </button>
        {isQuickSaveOpen ? (
          <>
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
          </>
        ) : null}
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

      <div className="reading-summary-next-actions">
        <button
          type="button"
          className="reading-summary-cta-button"
          onClick={onStartStudyFromSaved}
          disabled={!canStartFromSaved}
          title={
            canStartFromSaved
              ? undefined
              : "먼저 단어를 저장하면 바로 학습으로 이동할 수 있어요."
          }
        >
          <CardsIcon className="button-icon" />
          저장한 단어로 바로 학습
        </button>
        <button type="button" className="secondary-button reading-summary-cta-button" onClick={onGoToVocab}>
          <CardFileIcon className="button-icon" />
          어휘 노트 보기
        </button>
      </div>
    </section>
  );
}

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
    ? "원문을 입력하면 분석할 수 있어요."
    : !selectedDeckId
      ? "읽기 덱을 선택하면 분석할 수 있어요."
      : isAnalyzing
        ? "분석 중이에요. 잠시만 기다려주세요..."
        : null;
  const messageTone = classifyMessageTone(message);

  return (
    <section className="tab-panel reading-panel" aria-live="polite">
      {!hasResult ? (
        <div className="reading-hero">
          <h2 className="reading-hero-title">원문으로 읽고 바로 노트에 담기</h2>
          <p className="reading-hero-subtitle">
            원문을 붙여넣고 모르는 단어를 바로 담아보세요.
          </p>
        </div>
      ) : null}

      {hasResult ? (
        <ReaderCompactToolbar
          isSessionRestored={isSessionRestored}
          onDismissRestoredNotice={onDismissRestoredNotice}
          isTextCollapsed={isTextCollapsed}
          onToggleTextCollapsed={onToggleTextCollapsed}
          onResetSession={onResetSession}
          summary={summary}
          selectedCount={selectedCount}
        />
      ) : null}

      <section className="reading-input-open">
        {!hasResult ? (
          <div className="reading-input-open-header">
            <span className="reading-input-eyebrow">원문 읽기</span>
            {!text.trim() ? null : (
              <h3 className="reading-input-open-title">읽을 원문을 붙여넣어 주세요</h3>
            )}
          </div>
        ) : null}
        <form className="analyze-form" onSubmit={onAnalyze}>
          <label htmlFor="reading-source-text" className="sr-only-label">
            원문
          </label>

          {showForm ? (
            <>
              {!hasResult && !text.trim() ? (
                <AppEmptyState
                  mood="reading"
                  moodSize="md"
                  className="reading-empty-guide"
                  title="원문을 펼쳐볼까요?"
                  description="일본어 원문을 붙여넣고 모르는 단어를 눌러보세요."
                >
                  <button
                    type="button"
                    className="ghost-button compact-button"
                    onClick={onLoadSampleText}
                  >
                    <SparkleIcon className="button-icon" />
                    샘플 문장으로 체험
                  </button>
                </AppEmptyState>
              ) : null}
              <textarea
                id="reading-source-text"
                value={text}
                onChange={(event) => onTextChange(event.target.value)}
                placeholder="彼は闇の中で声を聞いた。少女は約束を思い出した。"
                rows={6}
              />
              <div className="reading-input-footer">
                <label className="reading-deck-picker">
                  <FolderIcon className="reading-deck-picker-icon" />
                  <select
                    value={selectedDeckId}
                    onChange={(event) => onSelectedDeckChange(event.target.value)}
                    aria-label="읽기 덱"
                  >
                    {decks.map((deck) => (
                      <option key={deck.id} value={String(deck.id)}>
                        {deck.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="submit"
                  className="reading-open-button"
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

      {!summary && message ? (
        !hasResult && !isAnalyzing && messageTone === "info" ? (
          <AppEmptyState icon={SparkleIcon} className="reading-empty-guide" title={message}>
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={onLoadSampleText}
            >
              <SparkleIcon className="button-icon" />
              샘플 문장으로 체험
            </button>
          </AppEmptyState>
        ) : (
          <p className={`message message--${messageTone}`}>{message}</p>
        )
      ) : null}

      {summary && isSampleText ? (
        <details className="panel-card note-card reading-onboarding-note">
          <summary className="reading-onboarding-note-title">
            <span className="memo-label">가이드</span>
            샘플로 핵심 흐름을 체험해보세요
          </summary>
          <p className="muted-text reading-onboarding-note-steps">
            1 단어 클릭해 뜻 확인 → 2 모르는 단어 저장 → 3 저장한 단어로 바로 학습
          </p>
        </details>
      ) : null}

      {/* ReaderWorkspace -- ReaderPaper (reader-paper, hero tier) +
          ReaderSaveDock (slim strip) + CandidateDrawer (ReadingVocabPanel,
          collapsed by default) share one "bound notebook" frame (a dashed
          spine down the left edge) instead of reading as three unrelated
          floating boxes. */}
      <div className="reader-workspace library-card-stage">
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
          !analyzeProgress || analyzeProgress.total <= 1 ? (
            <p className="empty reading-loading-hint" role="status">
              원문을 읽는 중이에요. 잠시만 기다려주세요...
            </p>
          ) : null
        ) : message ? null : (
          <p className="empty">덱을 선택하고 원문을 입력한 뒤 읽기 분석을 눌러주세요.</p>
        )}

        {summary ? (
          <ReaderSaveDock
            summary={summary}
            selectedCount={selectedCount}
            isSavingBatch={isSavingBatch}
            onSaveSelected={() => void handleSaveSelected()}
            onSaveBatch={onSaveBatch}
            canStartFromSaved={canStartFromSaved}
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

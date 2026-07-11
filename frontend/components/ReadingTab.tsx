"use client";

import { useRef, useState, type FormEvent } from "react";
import { ReaderMode } from "./ReaderMode";
import { ReadingVocabPanel } from "./ReadingVocabPanel";
import { classifyMessageTone, computeReadingSaveSummary } from "./coverageUtils";
import type { ReadingSaveMode } from "./coverageUtils";
import type { ChunkAnalyzeProgress } from "./readingChunkAnalyze";
import type { Deck, TokenStatus, TokenWithStatus, VocabItem } from "./types";

// Copyright-safe, hand-written sample so first-time users can try the flow
// without pasting their own text first.
const SAMPLE_TEXT =
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
  onSelectedDeckChange: (deckId: string) => void;
  onAnalyze: (event: FormEvent<HTMLFormElement>) => void;
  onStatusChange: (index: number, status: TokenStatus) => void;
  onToggleTextCollapsed: () => void;
  onSaveBatch: (mode: ReadingSaveMode) => void;
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
  onSelectedDeckChange,
  onAnalyze,
  onStatusChange,
  onToggleTextCollapsed,
  onSaveBatch,
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
  const analyzeHint = !text.trim()
    ? "원문을 입력하면 분석할 수 있습니다."
    : !selectedDeckId
      ? "읽기 덱을 선택하면 분석할 수 있습니다."
      : isAnalyzing
        ? "분석 중입니다. 잠시만 기다려주세요..."
        : null;
  const messageTone = classifyMessageTone(message);

  return (
    <section className="tab-panel" aria-live="polite">
      <div className="reading-hero">
        <h2 className="reading-hero-title">원문으로 읽고 바로 단어장에 담기</h2>
        <p className="reading-hero-subtitle">
          일본어 원문을 붙여넣고 분석하면 모르는 단어만 골라 문맥 예문과
          함께 저장하고, 바로 복습으로 이어갈 수 있습니다.
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
                  <p>읽고 싶은 일본어 문장을 붙여넣고 분석해보세요.</p>
                  <p className="muted-text">
                    모르는 단어를 클릭해 뜻과 읽기를 확인할 수 있습니다.
                  </p>
                  <button
                    type="button"
                    className="ghost-button compact-button"
                    onClick={() => onTextChange(SAMPLE_TEXT)}
                  >
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
                  {isAnalyzing ? "분석 중..." : "읽기 분석"}
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
          입력한 원문은 분석에만 사용되며, 원문 전체는 서버에 저장되지 않고
          공유 덱에도 포함되지 않습니다. 이어서 읽을 수 있도록 이 브라우저에만
          임시로 저장되며, 언제든 "현재 읽기 작업 초기화"로 직접 지울 수
          있습니다. 단어 저장 시 해당 단어가 포함된 짧은 문장만 예문으로
          저장됩니다.
        </p>
        {storageWarning ? (
          <p className="muted-text reading-storage-warning">{storageWarning}</p>
        ) : null}
      </section>

      {!summary && message ? (
        <p className={`message message--${messageTone}`}>{message}</p>
      ) : null}

      {summary ? (
        <section className="panel-card reading-summary-panel">
          <div className="panel-card-header">
            <h3 className="panel-card-title">이 텍스트 학습 요약</h3>
            <p className="panel-card-description">
              상태별 단어 수를 확인하고, 원하는 범위만 골라 단어장에
              저장하세요.
            </p>
            <span className="reading-summary-highlight">
              저장 가능 단어 {summary.saveableCount}개
            </span>
          </div>
          <div className="reading-summary-grid" role="group" aria-label="이 텍스트 학습 요약">
            <div className="reading-summary-card reading-summary-card-new">
              <span>새 단어</span>
              <strong>{summary.newCount}개</strong>
            </div>
            <div className="reading-summary-card reading-summary-card-unknown">
              <span>모르는 단어</span>
              <strong>{summary.unknownCount}개</strong>
            </div>
            <div className="reading-summary-card reading-summary-card-uncertain">
              <span>헷갈리는 단어</span>
              <strong>{summary.uncertainCount}개</strong>
            </div>
            <div className="reading-summary-card reading-summary-card-known">
              <span>이미 아는 단어</span>
              <strong>{summary.knownCount}개</strong>
            </div>
            <div className="reading-summary-card reading-summary-card-unclassified">
              <span>미분류 단어</span>
              <strong>{summary.unclassifiedCount}개</strong>
            </div>
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
          {summary.saveableCount === 0 ? (
            <p className="muted-text reading-summary-hint">
              저장 가능한 단어가 없어요. 이미 학습 중인 단어일 수 있습니다.
            </p>
          ) : isSavingBatch ? (
            <p className="muted-text reading-summary-hint">저장 중입니다...</p>
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
              저장한 단어로 바로 학습
            </button>
            <button
              type="button"
              className="secondary-button reading-summary-cta-button"
              onClick={onGoToVocab}
            >
              단어장 보기
            </button>
          </div>
        </section>
      ) : null}

      {hasResult ? (
        <ReadingVocabPanel
          tokens={tokens}
          vocabItems={vocabItems}
          selectedDeckId={selectedDeckId}
          selectedTokenKey={selectedTokenKey}
          onSelectToken={handleVocabPanelSelect}
        />
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
      ) : (
        <p className="empty">
          덱을 선택하고 원문을 입력한 뒤 읽기 분석을 눌러주세요.
        </p>
      )}
    </section>
  );
}

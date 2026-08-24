"use client";

import type { FormEvent } from "react";
import { FolderIcon, ShieldIcon, SparkleIcon } from "./icons";
import type { ChunkAnalyzeProgress } from "./readingChunkAnalyze";
import type { Deck } from "./types";

// Shown wherever the deck select would otherwise be an empty dropdown the
// user can do nothing with. Rendered either inside the source slip or, when
// the slip is collapsed away (restored session with the text folded), on
// its own -- never both at once.
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
// ReadingSourceSlip -- Phase 169 (Reading V2). One physical object: a paper
// slip resting on the book's page, not a bordered "form card" sitting on a
// wallpaper photo behind it. The exact same component renders both the
// first-visit blank-page state (ReadingTab renders it directly into
// .reading-page--left when there's no result yet) and the collapsed re-edit
// tray once a result exists (ReaderMode renders it above the reader text,
// inside the same scrollable page pane, when the user opens "원문 입력
// 펼치기") -- previously those were two unrelated systems
// (.reader-start-scene vs .reading-input-open/.reading-note-sheet) that
// happened to look similar; now there's exactly one slip component and one
// CSS family for it, in its own module so both ReadingTab.tsx (the no-
// result state) and ReaderMode.tsx (the re-edit state) can import it
// without a circular ReadingTab<->ReaderMode dependency. Deck select stays
// a small paper tag (.reading-deck-picker, shared with Analyze), submit is
// the same notched bookmark-tag CTA every other reading action uses
// (.reader-bookmark-button). Behavior (onAnalyze submit, onLoadSampleText,
// deck select, cancel) is unchanged from before Phase 169; only where/how
// often this markup is mounted changed.
// ---------------------------------------------------------------------------
export type ReadingSourceSlipProps = {
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

export function ReadingSourceSlip({
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
}: ReadingSourceSlipProps) {
  const hasChunkProgress = isAnalyzing && !!analyzeProgress && analyzeProgress.total > 1;

  return (
    <form className="reading-slip-form" onSubmit={onAnalyze}>
      <label htmlFor="reading-source-text" className="sr-only-label">
        원문
      </label>
      <div className="reading-slip">
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
            className="reading-slip-sample"
            onClick={onLoadSampleText}
          >
            <SparkleIcon className="button-icon" />
            샘플 문장으로 체험
          </button>
        ) : null}
      </div>

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
          <button type="button" className="ghost-button compact-button" onClick={onCancelAnalyze}>
            분석 취소
          </button>
        </div>
      ) : isAnalyzing ? (
        <p className="sr-only-label" role="status">
          원문을 읽는 중이에요. 잠시만 기다려주세요...
        </p>
      ) : null}

      <div className="reading-slip-controls">
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
                  {isLoadingDecks ? "덱을 불러오는 중..." : "사용할 수 있는 덱이 없어요"}
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
          className="reader-bookmark-button reading-slip-cta"
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

      <p className="muted-text copyright-note reading-slip-copyright">
        <ShieldIcon className="copyright-note-icon" />
        <span>원문 전체는 서버에 저장하지 않아요.</span>
      </p>
      {storageWarning ? (
        <p className="muted-text reading-storage-warning">{storageWarning}</p>
      ) : null}
    </form>
  );
}

export { DeckLoadRecovery };

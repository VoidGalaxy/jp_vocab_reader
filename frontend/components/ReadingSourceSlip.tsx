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

  // Reading V3 Gate 2 -- the deck-load failure used to swap the deck
  // selector's own slot for <DeckLoadRecovery>, a boxed red-bordered panel
  // (exactly the "form card on the photo" look the whole redesign exists to
  // remove) and left the message sitting *below* the privacy/count row
  // instead of the one line directly above it DESIGN_SPEC.md calls for.
  // Folding it into the same one-line error slot analyzeHint already uses
  // fixes both at once: the deck <select> now always renders in its own
  // slot (it already has its own "사용할 수 있는 덱이 없어요" empty state),
  // and there is exactly one error line, in exactly one fixed-height slot,
  // above metadata, whichever message is active.
  const errorLine = needsDeckRecovery
    ? `${deckLoadError} 읽기 덱이 없어 분석을 시작할 수 없어요.`
    : analyzeHint;

  return (
    <form className="reading-slip-form" onSubmit={onAnalyze}>
      {/* Reading V3 Gate B -- desktop-only header (hidden on mobile, see
          .reading-slip-head in globals.css): title/supporting copy written
          directly on the page, matching reading-v3-input-approved.png. Kept
          the same fixed block height as ReaderMode's .reading-progress-tag-wrap
          so the editor/reader text below both start at the same y origin
          regardless of which header is showing (see DESIGN_SPEC.md's State
          Continuity section). */}
      <div className="reading-slip-head">
        <h2 className="reading-slip-title">원문 입력</h2>
        <p className="reading-slip-subtitle">
          일본어 원문을 붙여넣고 함께 읽어보세요.
        </p>
      </div>

      <label htmlFor="reading-source-text" className="sr-only-label">
        원문
      </label>
      <div className="reading-slip">
        <textarea
          id="reading-source-text"
          value={text}
          onChange={(event) => onTextChange(event.target.value)}
          placeholder="여기에 일본어 원문을 붙여넣으세요."
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

      {/* Reading V3 Gate 2B -- status lives in .reading-slip-status, an
          always-reserved grid row (see globals.css), not a block that
          appears/pushes siblings. The long descriptive label is kept for
          screen readers only (sr-only-label) so the visible row fits count
          + cancel side by side within that reserved height -- Gate 2's
          position:absolute version put this whole block below the visible
          fold, which is the exact regression this restructure fixes. */}
      {hasChunkProgress ? (
        <div className="reading-analyze-progress" role="status" aria-live="polite">
          <p className="reading-analyze-progress-label sr-only-label">
            긴 원문을 문단·문장 단위로 나눠 분석하고 있습니다.
          </p>
          <div className="reading-analyze-progress-row">
            <p className="reading-analyze-progress-count">
              {analyzeProgress!.current} / {analyzeProgress!.total} 조각 분석 중
            </p>
            <button
              type="button"
              className="ghost-button compact-button reading-analyze-progress-cancel"
              onClick={onCancelAnalyze}
            >
              분석 취소
            </button>
          </div>
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
        </div>
      ) : isAnalyzing ? (
        <p className="sr-only-label" role="status">
          원문을 읽는 중이에요. 잠시만 기다려주세요...
        </p>
      ) : null}

      <div className="reading-slip-controls">
        {/* Reading V3 Gate 2 -- mobile keeps its exact pre-Gate-2 look: the
            recovery box replaces the picker in this slot (hidden at
            desktop, see .reading-slip-controls .reading-deck-recovery
            below -- scoped to *this* slot only, so the unrelated standalone
            <DeckLoadRecovery> ReadingTab.tsx renders elsewhere, for the
            collapsed-session case, is untouched). Desktop instead always
            shows the compact selector (hidden on mobile while recovery is
            active, same as before) -- its own disabled/empty option already
            reads "사용할 수 있는 덱이 없어요", so the slot never needs a
            second, boxed explanation next to it; the actual error message
            now lives once, in .reading-slip-error-row below. */}
        {needsDeckRecovery ? (
          <DeckLoadRecovery
            message={deckLoadError}
            isRetrying={isLoadingDecks}
            onRetry={onRetryLoadDecks}
          />
        ) : null}
        <label
          className={
            needsDeckRecovery
              ? "reading-deck-picker reading-deck-picker--desktop-fallback"
              : "reading-deck-picker"
          }
        >
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

      {/* Reading V3 Gate 2 -- one fixed-height slot, always rendered (even
          with nothing to say), so the metadata row below never shifts when
          an error/hint appears or disappears. One line only: long deck
          errors ellipsize (see .reading-slip-error-text) instead of
          wrapping into a second line or a bordered panel.
          The recovery variant is desktop-only (see globals.css): on mobile
          that same message already shows inside <DeckLoadRecovery> above,
          so showing it again here would duplicate it -- a plain hint
          (analyzeHint, not deck recovery) has no other home and keeps
          showing on every width, matching its pre-Gate-2 behavior. */}
      <div
        className={
          needsDeckRecovery
            ? "reading-slip-error-row reading-slip-error-row--recovery"
            : "reading-slip-error-row"
        }
      >
        {errorLine ? (
          <>
            <p className="reading-slip-error-text" title={errorLine}>
              {errorLine}
            </p>
            {needsDeckRecovery ? (
              <button
                type="button"
                className="reading-slip-error-action"
                onClick={onRetryLoadDecks}
                disabled={isLoadingDecks}
              >
                {isLoadingDecks ? "불러오는 중..." : "다시 불러오기"}
              </button>
            ) : null}
          </>
        ) : null}
      </div>

      <div className="reading-slip-meta">
        <p className="muted-text copyright-note reading-slip-copyright">
          <ShieldIcon className="copyright-note-icon" />
          <span className="reading-slip-copyright-text">
            원문 전체는 서버에 저장하지 않아요.
          </span>
        </p>
        {/* Desktop-only (see .reading-slip-charcount in globals.css) --
            purely presentational, derived from the same `text` prop
            everything else here already reads; no new state or behavior. */}
        <span className="reading-slip-charcount">문자 수 {text.length}</span>
      </div>
      {storageWarning ? (
        <p className="muted-text reading-storage-warning">{storageWarning}</p>
      ) : null}
    </form>
  );
}

export { DeckLoadRecovery };

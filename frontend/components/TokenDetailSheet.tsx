"use client";

import type { TokenStatus, TokenWithStatus } from "./types";
import { getDisplayMeaning } from "./shared";
import { HighlightedExample } from "./HighlightedExample";
import { MeaningQuickEdit } from "./MeaningQuickEdit";
import { BookmarkIcon, CloseIcon } from "./icons";
import { ShioriMark, ShioriStamp } from "./Shiori";

type TokenDetailSheetProps = {
  token: TokenWithStatus;
  onClose: () => void;
  onStatusChange: (status: TokenStatus) => void;
  onPrevious: () => void;
  onNext: () => void;
  canGoPrevious: boolean;
  canGoNext: boolean;
  onNextUnknown: () => void;
  canGoNextUnknown: boolean;
  onFirstOccurrence: () => void;
  canGoFirstOccurrence: boolean;
  positionLabel: string | null;
  isInBasket: boolean;
  canAddToBasket: boolean;
  onToggleBasket: () => void;
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

// Casual Sticker Reader (Phase 65) -- "presentation" decides only the outer
// shell: "modal" is the original full-screen/bottom-sheet overlay (mobile,
// and any narrower desktop-ish width below the true 2-column desk scene --
// see .reader-desk-scene's 1024px breakpoint in globals.css), "pinned" is
// the always-present word-inspector column next to the reader page on wide
// desktop viewports (no overlay, no dialog semantics -- it's a persistent
// panel, not something that interrupts the page). Both shells render the
// exact same TokenDetailContent, so there is exactly one place that knows
// what a word card actually contains.
type TokenDetailPresentation = "modal" | "pinned";

// Short local labels for the classify stamp row only -- statusLabels
// (shared.tsx) stays the long/formal form used elsewhere (Analyze tab
// summary, Vocab list badges, Study). Reuses the exact short forms
// ReaderMode's own color legend already settled on (아는/헷갈림/모름/
// 미분류), so the same word doesn't have two different short spellings
// inside one screen.
const stampLabels: Record<TokenStatus, string> = {
  known: "아는",
  uncertain: "헷갈림",
  unknown: "모름",
  unclassified: "미분류",
};

// Phase 120 -- Reading Inspector Interior Reconstruction. Previously this
// card was built like an information-management panel: a titled/tinted
// "한국어 뜻" block, a "현재 상태: X" sentence duplicating the classify
// grid's own active state, a bordered 2x2 button grid, a bordered pill row
// of meta tags, a bordered/accented example callout, and a bordered footer
// of same-weight action buttons (basket toggle, 4 nav buttons, meaning
// edit, report) -- eight-ish same-looking chrome blocks stacked with no
// clear "what matters first" read. Rebuilt around one hierarchy instead:
// word/reading/meaning dominate with no card-in-card chrome at all: a
// compact single-row classify "stamp" strip (short labels, soft per-status
// tint, no bordered grid) comes right after; meta/example/basket/nav/edit/
// report all drop into one quiet, small-text secondary area below a thin
// divider (further folded behind "자세히" on the mobile peek card, same as
// before). No functional change -- every handler/prop below is called
// exactly as it was.
function TokenDetailContent({
  token,
  onClose,
  onStatusChange,
  onPrevious,
  onNext,
  canGoPrevious,
  canGoNext,
  onNextUnknown,
  canGoNextUnknown,
  onFirstOccurrence,
  canGoFirstOccurrence,
  positionLabel,
  isInBasket,
  canAddToBasket,
  onToggleBasket,
  meaningEditItemId,
  meaningEditDraft,
  isSavingMeaningEdit,
  meaningEditMessage,
  onStartMeaningEdit,
  onMeaningEditDraftChange,
  onSaveMeaningEdit,
  onCancelMeaningEdit,
  onReportMeaning,
}: TokenDetailSheetProps) {
  const label = token.surface || token.base_form;
  // Prefer the user's own saved (and possibly edited) meaning over the
  // fresh dictionary lookup from /analyze, same priority savedExampleSentence
  // already uses -- this is what makes editing a word's meaning here
  // actually visible the next time the word is encountered while reading.
  const displayedMeaning = token.savedMeaningKo || token.meaning_ko;
  const vocabItemId = token.savedVocabItemId ?? null;
  const isEditingMeaning =
    vocabItemId !== null && meaningEditItemId === vocabItemId;

  const metaParts: string[] = [];
  if (token.base_form && token.base_form !== label) {
    metaParts.push(`기본형 ${token.base_form}`);
  }
  if (token.part_of_speech) {
    metaParts.push(token.part_of_speech);
  }
  metaParts.push(`${token.occurrence_count || 1}회 등장`);
  if (token.jlpt_level) {
    metaParts.push(`JLPT 추천 ${token.jlpt_level}`);
  }

  const exampleSentence = token.savedExampleSentence || token.example_sentence;

  return (
    <>
      <div className="token-note-header">
        <ShioriMark variant="reading" className="token-note-mark" />
        <div className="token-note-heading">
          <div className="token-note-word-row">
            <span className="token-note-word">{label}</span>
            {token.reading && token.reading !== label ? (
              <span className="token-note-reading">{token.reading}</span>
            ) : null}
          </div>
          {positionLabel ? (
            <span className="token-note-position">{positionLabel}</span>
          ) : null}
        </div>
        <button
          type="button"
          className="token-sheet-close"
          onClick={onClose}
          aria-label="단어 카드 닫기"
        >
          <CloseIcon className="token-sheet-close-icon" />
        </button>
      </div>

      <p className="token-note-meaning-label">한국어 뜻</p>
      <p className="token-note-meaning">{getDisplayMeaning(displayedMeaning)}</p>

      {/* Phase 99 -- classification is the primary action now that
          unknown/uncertain auto-save on click (see handleReadingStatusChange
          in page.tsx). Phase 120 -- recast from a bordered 2x2 button grid
          into a single-row strip of small stamp chips (soft per-status
          tint, filled only when active via the existing shared
          [data-active="true"] convention) so it reads as a quick mark, not
          an admin form section -- but every button still calls the exact
          same onStatusChange(status) it always did. */}
      <div
        className="token-note-stamps"
        role="group"
        aria-label="단어 상태 변경"
      >
        <button
          type="button"
          className="token-note-stamp success-button"
          aria-pressed={token.status === "known"}
          data-active={token.status === "known"}
          onClick={() => onStatusChange("known")}
        >
          {stampLabels.known}
        </button>
        <button
          type="button"
          className="token-note-stamp warning-button"
          aria-pressed={token.status === "uncertain"}
          data-active={token.status === "uncertain"}
          onClick={() => onStatusChange("uncertain")}
        >
          {stampLabels.uncertain}
        </button>
        <button
          type="button"
          className="token-note-stamp danger-button"
          aria-pressed={token.status === "unknown"}
          data-active={token.status === "unknown"}
          onClick={() => onStatusChange("unknown")}
        >
          {stampLabels.unknown}
        </button>
        <button
          type="button"
          className="token-note-stamp secondary-button"
          aria-pressed={token.status === "unclassified"}
          data-active={token.status === "unclassified"}
          onClick={() => onStatusChange("unclassified")}
        >
          {stampLabels.unclassified}
        </button>
      </div>
      {/* No visible "현재 상태: X" line -- each stamp's own aria-pressed
          already announces the active state accessibly (this is a
          role="group" of toggle buttons, not a plain button row), so a
          second sentence saying the same thing would be redundant both
          visually and for screen readers. */}
      {token.status === "unclassified" ? (
        <p className="token-note-stamp-hint">
          모르는·헷갈리는 단어는 자동 저장돼요
        </p>
      ) : null}

      {/* Phase 94 -- hidden by default (pinned desktop / docked tablet aren't
          height-constrained); shown only on the compact mobile sheet, right
          where its max-height actually cuts the card off. Phase 120 -- moved
          up to sit right after the stamp row (word/meaning/status is now the
          card's entire "first look"; meta/example/basket/nav/edit/report are
          all secondary and fold below this same marker). */}
      <div className="token-sheet-fold-divider" aria-hidden="true">
        <span>자세히</span>
      </div>

      <p className="token-note-meta">{metaParts.join(" · ")}</p>
      {token.jlpt_level ? (
        <p className="jlpt-detail-hint">
          JLPT 추천 어휘 기준이며, 비공식 참고용 표시입니다.
        </p>
      ) : null}

      <div className="token-note-example">
        <span className="token-note-example-label">예문</span>
        {exampleSentence ? (
          <p className="token-note-example-text">
            <HighlightedExample
              sentence={exampleSentence}
              surface={token.surface}
              baseForm={token.base_form}
              normalizedForm={token.normalized_form}
            />
          </p>
        ) : (
          <p className="token-note-example-hint">
            이 단어가 포함된 문장을 찾지 못했어요.
          </p>
        )}
      </div>

      <div className="token-note-actions">
        {canAddToBasket ? (
          <span className="token-note-basket-row">
            <button
              type="button"
              className={`token-note-action-chip${isInBasket ? " token-note-action-chip-active" : ""}`}
              onClick={onToggleBasket}
              aria-pressed={isInBasket}
            >
              <BookmarkIcon className="button-icon" />
              {isInBasket ? "저장 대상에서 제외" : "저장 대상으로 선택"}
            </button>
            {isInBasket ? (
              <ShioriStamp
                variant="save"
                label="선택했어요"
                className="token-note-basket-stamp"
              />
            ) : null}
          </span>
        ) : null}
        <span className="token-note-nav" role="group" aria-label="단어 이동">
          <button
            type="button"
            className="token-note-action-link"
            onClick={onPrevious}
            disabled={!canGoPrevious}
          >
            ← 이전
          </button>
          <button
            type="button"
            className="token-note-action-link"
            onClick={onNext}
            disabled={!canGoNext}
          >
            다음 →
          </button>
          <button
            type="button"
            className="token-note-action-link"
            onClick={onNextUnknown}
            disabled={!canGoNextUnknown}
          >
            모르는 단어로
          </button>
          {token.occurrence_count > 1 ? (
            <button
              type="button"
              className="token-note-action-link"
              onClick={onFirstOccurrence}
              disabled={!canGoFirstOccurrence}
            >
              첫 등장으로
            </button>
          ) : null}
        </span>
        <span className="token-note-meaning-actions">
          {vocabItemId !== null ? (
            <MeaningQuickEdit
              isEditing={isEditingMeaning}
              draftValue={meaningEditDraft}
              isSaving={isSavingMeaningEdit}
              message={isEditingMeaning ? meaningEditMessage : ""}
              onStartEdit={() =>
                onStartMeaningEdit(vocabItemId, displayedMeaning)
              }
              onDraftChange={onMeaningEditDraftChange}
              onSave={onSaveMeaningEdit}
              onCancel={onCancelMeaningEdit}
            />
          ) : null}
          {!isEditingMeaning ? (
            <button
              type="button"
              className="token-note-action-link"
              onClick={() => onReportMeaning(token)}
            >
              뜻 오류 신고
            </button>
          ) : null}
        </span>
      </div>
    </>
  );
}

export function TokenDetailSheet({
  presentation,
  ...contentProps
}: TokenDetailSheetProps & { presentation: TokenDetailPresentation }) {
  const { token, onClose } = contentProps;
  const label = token.surface || token.base_form;

  if (presentation === "pinned") {
    // Phase 169 -- Desktop open-book scene: the word note pinned directly
    // onto the book's right page (see .reading-page--right in
    // ReaderMode.tsx), not a bordered panel-card floating beside it. No
    // card chrome of its own (.reading-pinned-note is close to unstyled --
    // the page pane's own padding/scroll already does the work); not a
    // dialog, nothing to trap focus in or dismiss via Escape-as-close.
    // aria-live announces the swapped-in word to screen reader users who
    // never move focus off the reader text itself.
    return (
      <div
        className="reading-pinned-note"
        aria-label={`${label} 단어 정보`}
        aria-live="polite"
      >
        <TokenDetailContent {...contentProps} />
      </div>
    );
  }

  // Phase 169 -- mobile/tablet: a small floating note anchored to the
  // bottom of the book scene (.reading-inspector-float), not a full-screen
  // or near-full-height bottom sheet -- capped well under half the frame's
  // height (see globals.css) so the original text stays visible above and
  // around it instead of being pushed out or covered. The catcher behind it
  // stays transparent (no dark scrim), same reasoning Phase 94 already
  // established: dimming the reader text behind a "glance at the meaning"
  // card fights the whole point of keeping it visible.
  return (
    <div
      className="reading-inspector-float-overlay"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="reading-inspector-float"
        role="dialog"
        aria-modal="true"
        aria-label={`${label} 단어 정보`}
        onClick={(event) => event.stopPropagation()}
      >
        <TokenDetailContent {...contentProps} />
      </div>
    </div>
  );
}

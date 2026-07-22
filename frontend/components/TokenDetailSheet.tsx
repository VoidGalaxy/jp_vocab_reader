"use client";

import type { TokenStatus, TokenWithStatus } from "./types";
import { getDisplayMeaning, statusLabels } from "./shared";
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

export function TokenDetailSheet({
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

  return (
    <div className="token-sheet-overlay" role="presentation" onClick={onClose}>
      <div
        className="bookmark-inspector word-index-inspector paper-corner card-stack-surface"
        role="dialog"
        aria-modal="true"
        aria-label={`${label} 단어 정보`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="token-sheet-header">
          <div className="token-sheet-title-group">
            <ShioriMark variant="reading" className="token-sheet-bookmark-icon" />
            <span className="token-sheet-word">{label}</span>
            {token.reading && token.reading !== label ? (
              <span className="token-sheet-reading">{token.reading}</span>
            ) : null}
            {positionLabel ? (
              <span className="token-sheet-position-badge">
                {positionLabel}
              </span>
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
        <div className="token-sheet-meaning-block">
          <span className="token-sheet-meaning-label">한국어 뜻</span>
          <p className="token-sheet-meaning-value">
            {getDisplayMeaning(displayedMeaning)}
          </p>
        </div>
        <p className="token-sheet-status">
          현재 상태: <strong>{statusLabels[token.status]}</strong>
        </p>
        <div className="classify-actions" role="group" aria-label="단어 상태 변경">
          <button
            type="button"
            className="success-button"
            aria-pressed={token.status === "known"}
            data-active={token.status === "known"}
            onClick={() => onStatusChange("known")}
          >
            {statusLabels.known}
          </button>
          <button
            type="button"
            className="warning-button"
            aria-pressed={token.status === "uncertain"}
            data-active={token.status === "uncertain"}
            onClick={() => onStatusChange("uncertain")}
          >
            {statusLabels.uncertain}
          </button>
          <button
            type="button"
            className="danger-button"
            aria-pressed={token.status === "unknown"}
            data-active={token.status === "unknown"}
            onClick={() => onStatusChange("unknown")}
          >
            {statusLabels.unknown}
          </button>
          <button
            type="button"
            className="secondary-button"
            aria-pressed={token.status === "unclassified"}
            data-active={token.status === "unclassified"}
            onClick={() => onStatusChange("unclassified")}
          >
            미분류 / 건너뛰기
          </button>
        </div>
        {canAddToBasket ? (
          <div className="token-sheet-basket-row">
            <button
              type="button"
              className={`token-sheet-basket-button${isInBasket ? " token-sheet-basket-button-active" : ""}`}
              onClick={onToggleBasket}
              aria-pressed={isInBasket}
            >
              <BookmarkIcon className="button-icon" />
              {isInBasket ? "저장 바구니에서 빼기" : "저장 바구니에 담기"}
            </button>
            {isInBasket ? (
              <ShioriStamp
                variant="save"
                label="노트에 담았어요"
                className="token-sheet-basket-stamp"
              />
            ) : null}
          </div>
        ) : null}
        <div className="token-sheet-meta-row">
          {token.base_form && token.base_form !== label ? (
            <span className="token-sheet-meta-tag">기본형 {token.base_form}</span>
          ) : null}
          {token.part_of_speech ? (
            <span className="token-sheet-meta-tag">{token.part_of_speech}</span>
          ) : null}
          <span className="token-sheet-meta-tag">
            {token.occurrence_count || 1}회 등장
          </span>
          {token.jlpt_level ? (
            <span className="token-sheet-meta-tag">
              JLPT 추천 {token.jlpt_level}
            </span>
          ) : null}
        </div>
        {token.jlpt_level ? (
          <p className="jlpt-detail-hint">
            JLPT 추천 어휘 기준이며, 공식 JLPT 어휘 목록은 아닙니다.
          </p>
        ) : null}
        <div className="context-example-block">
          <p className="context-example-label">문맥 예문</p>
          {token.savedExampleSentence ? (
            <p className="context-example-text">
              <HighlightedExample
                sentence={token.savedExampleSentence}
                surface={token.surface}
                baseForm={token.base_form}
                normalizedForm={token.normalized_form}
              />
            </p>
          ) : token.example_sentence ? (
            <>
              <p className="context-example-text">
                <HighlightedExample
                  sentence={token.example_sentence}
                  surface={token.surface}
                  baseForm={token.base_form}
                  normalizedForm={token.normalized_form}
                />
              </p>
              <p className="context-example-hint">
                이 단어가 나온 문장을 복습 카드에 함께 저장합니다.
              </p>
            </>
          ) : (
            <p className="context-example-hint">
              이 단어가 포함된 문장을 찾지 못했습니다.
            </p>
          )}
        </div>
        <div className="token-sheet-secondary-actions">
          <div className="token-sheet-nav" role="group" aria-label="단어 이동">
            <button
              type="button"
              className="ghost-button compact-button token-sheet-nav-button"
              onClick={onPrevious}
              disabled={!canGoPrevious}
            >
              ← 이전
            </button>
            <button
              type="button"
              className="ghost-button compact-button token-sheet-nav-button"
              onClick={onNext}
              disabled={!canGoNext}
            >
              다음 →
            </button>
            <button
              type="button"
              className="ghost-button compact-button token-sheet-nav-button"
              onClick={onNextUnknown}
              disabled={!canGoNextUnknown}
            >
              모르는 단어로
            </button>
            {token.occurrence_count > 1 ? (
              <button
                type="button"
                className="ghost-button compact-button token-sheet-nav-button"
                onClick={onFirstOccurrence}
                disabled={!canGoFirstOccurrence}
              >
                첫 등장으로
              </button>
            ) : null}
          </div>
          <div className="meaning-actions-row">
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
                className="ghost-button compact-button"
                onClick={() => onReportMeaning(token)}
              >
                뜻 오류 신고
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

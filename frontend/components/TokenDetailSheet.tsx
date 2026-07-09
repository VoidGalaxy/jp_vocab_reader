"use client";

import type { TokenStatus, TokenWithStatus } from "./types";
import { statusLabels } from "./shared";
import { HighlightedExample } from "./HighlightedExample";
import { MeaningQuickEdit } from "./MeaningQuickEdit";

type TokenDetailSheetProps = {
  token: TokenWithStatus;
  onClose: () => void;
  onStatusChange: (status: TokenStatus) => void;
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
        className="token-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={`${label} 단어 정보`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="token-sheet-header">
          <span className="token-sheet-word">{label}</span>
          <button
            type="button"
            className="secondary-button token-sheet-close"
            onClick={onClose}
          >
            닫기
          </button>
        </div>
        <dl className="classify-details">
          <div>
            <dt>기본형</dt>
            <dd>{token.base_form || "-"}</dd>
          </div>
          <div>
            <dt>읽기</dt>
            <dd>{token.reading || "-"}</dd>
          </div>
          <div>
            <dt>품사</dt>
            <dd>{token.part_of_speech || "-"}</dd>
          </div>
          <div>
            <dt>한국어 뜻</dt>
            <dd>{displayedMeaning || "뜻 후보 없음"}</dd>
          </div>
          <div>
            <dt>JLPT 추천 레벨</dt>
            <dd>
              {token.jlpt_level ? (
                <>
                  {token.jlpt_level}
                  <span className="jlpt-detail-hint">
                    {" "}
                    · JLPT 추천 어휘 기준이며, 공식 JLPT 어휘 목록은
                    아닙니다.
                  </span>
                </>
              ) : (
                "-"
              )}
            </dd>
          </div>
        </dl>
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
        <p className="token-sheet-status">
          현재 상태: <strong>{statusLabels[token.status]}</strong>
        </p>
        <div className="classify-actions">
          <button
            type="button"
            className="success-button"
            onClick={() => onStatusChange("known")}
          >
            {statusLabels.known}
          </button>
          <button
            type="button"
            className="warning-button"
            onClick={() => onStatusChange("uncertain")}
          >
            {statusLabels.uncertain}
          </button>
          <button
            type="button"
            className="danger-button"
            onClick={() => onStatusChange("unknown")}
          >
            {statusLabels.unknown}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() => onStatusChange("unclassified")}
          >
            미분류 / 건너뛰기
          </button>
        </div>
      </div>
    </div>
  );
}

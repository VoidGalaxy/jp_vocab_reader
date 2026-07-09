"use client";

import type { MeaningFeedbackTarget } from "./types";

const MAX_FEEDBACK_FIELD_LENGTH = 500;

type MeaningFeedbackModalProps = {
  target: MeaningFeedbackTarget;
  suggestedMeaning: string;
  reason: string;
  isSubmitting: boolean;
  message: string;
  onSuggestedMeaningChange: (value: string) => void;
  onReasonChange: (value: string) => void;
  onSubmit: () => void;
  onClose: () => void;
};

// One shared "뜻 오류 신고" dialog, rendered once at the top of page.tsx and
// opened from wherever a word is shown (reading tab, vocab list, study
// card) -- reuses the same overlay/sheet look as TokenDetailSheet.
export function MeaningFeedbackModal({
  target,
  suggestedMeaning,
  reason,
  isSubmitting,
  message,
  onSuggestedMeaningChange,
  onReasonChange,
  onSubmit,
  onClose,
}: MeaningFeedbackModalProps) {
  const label = target.surface || target.baseForm || "단어";

  return (
    <div className="token-sheet-overlay" role="presentation" onClick={onClose}>
      <div
        className="token-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={`${label} 뜻 오류 신고`}
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
            <dt>읽기</dt>
            <dd>{target.reading || "-"}</dd>
          </div>
          <div>
            <dt>현재 뜻</dt>
            <dd>{target.currentMeaningKo || "뜻 후보 없음"}</dd>
          </div>
        </dl>

        <label className="inline-field wide-field">
          제안하는 뜻 (선택)
          <textarea
            className="compact-textarea"
            value={suggestedMeaning}
            onChange={(event) => onSuggestedMeaningChange(event.target.value)}
            rows={2}
            maxLength={MAX_FEEDBACK_FIELD_LENGTH}
          />
        </label>
        <label className="inline-field wide-field">
          신고 이유 (선택)
          <textarea
            className="compact-textarea"
            value={reason}
            onChange={(event) => onReasonChange(event.target.value)}
            rows={2}
            maxLength={MAX_FEEDBACK_FIELD_LENGTH}
          />
        </label>

        <p className="meaning-feedback-hint">
          신고 내용은 사전 품질 개선에 참고됩니다.
        </p>

        {message ? <p className="message">{message}</p> : null}

        <div className="classify-actions">
          <button type="button" onClick={onSubmit} disabled={isSubmitting}>
            {isSubmitting ? "제출 중..." : "신고 제출"}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={onClose}
            disabled={isSubmitting}
          >
            취소
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { classifyMessageTone } from "./coverageUtils";
import type { AppFeedbackCategory } from "./types";

const APP_FEEDBACK_MESSAGE_MIN_LENGTH = 10;
const APP_FEEDBACK_MESSAGE_MAX_LENGTH = 1000;

const categoryOptions: Array<{ value: AppFeedbackCategory; label: string }> = [
  { value: "bug", label: "오류" },
  { value: "ux", label: "불편함" },
  { value: "feature", label: "기능 제안" },
  { value: "meaning", label: "뜻 문제" },
  { value: "other", label: "기타" },
];

type GlobalFeedbackModalProps = {
  screenLabel: string;
  category: AppFeedbackCategory;
  message: string;
  isSubmitting: boolean;
  resultMessage: string;
  onCategoryChange: (category: AppFeedbackCategory) => void;
  onMessageChange: (value: string) => void;
  onSubmit: () => void;
  onClose: () => void;
};

// App-wide "불편한 점 보내기" dialog -- separate from MeaningFeedbackModal
// (a specific word's meaning report). This one is for anything else: bugs,
// UX friction, feature requests, or a quick "뜻 문제" pointer when the
// reading card's own "뜻 오류 신고" isn't the right fit.
export function GlobalFeedbackModal({
  screenLabel,
  category,
  message,
  isSubmitting,
  resultMessage,
  onCategoryChange,
  onMessageChange,
  onSubmit,
  onClose,
}: GlobalFeedbackModalProps) {
  const trimmedLength = message.trim().length;
  const isTooShort = trimmedLength > 0 && trimmedLength < APP_FEEDBACK_MESSAGE_MIN_LENGTH;
  const canSubmit = trimmedLength >= APP_FEEDBACK_MESSAGE_MIN_LENGTH && !isSubmitting;

  return (
    <div className="feedback-modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="feedback-modal"
        role="dialog"
        aria-modal="true"
        aria-label="피드백 보내기"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="feedback-modal-header">
          <h2 className="feedback-modal-title">피드백</h2>
          <button
            type="button"
            className="feedback-modal-close"
            onClick={onClose}
            aria-label="피드백 창 닫기"
          >
            ×
          </button>
        </div>

        <p className="muted-text feedback-screen-label">현재 화면: {screenLabel}</p>

        <label className="inline-field wide-field">
          카테고리
          <select
            value={category}
            onChange={(event) =>
              onCategoryChange(event.target.value as AppFeedbackCategory)
            }
          >
            {categoryOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="inline-field wide-field">
          내용
          <textarea
            className="compact-textarea"
            value={message}
            onChange={(event) => onMessageChange(event.target.value)}
            rows={4}
            maxLength={APP_FEEDBACK_MESSAGE_MAX_LENGTH}
            placeholder="불편한 점, 오류, 기능 제안 등을 간단히 적어주세요."
          />
        </label>
        <p className="meaning-feedback-hint">
          {message.length} / {APP_FEEDBACK_MESSAGE_MAX_LENGTH}자
          {isTooShort ? ` · 최소 ${APP_FEEDBACK_MESSAGE_MIN_LENGTH}자 이상 입력해 주세요.` : ""}
        </p>
        <p className="meaning-feedback-hint">
          원문 전체나 개인정보는 보내지 말아주세요. 불편한 점만 간단히
          적어주세요.
        </p>

        {resultMessage ? (
          <p className={`message message--${classifyMessageTone(resultMessage)}`}>
            {resultMessage}
          </p>
        ) : null}

        <div className="feedback-modal-footer">
          <button
            type="button"
            className="ghost-button"
            onClick={onClose}
            disabled={isSubmitting}
          >
            취소
          </button>
          <button type="button" onClick={onSubmit} disabled={!canSubmit}>
            {isSubmitting ? "제출 중..." : "제출"}
          </button>
        </div>
      </div>
    </div>
  );
}

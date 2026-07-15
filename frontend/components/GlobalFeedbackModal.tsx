"use client";

import { useState } from "react";
import { classifyMessageTone } from "./coverageUtils";
import type { AppFeedbackCategory } from "./types";

const APP_FEEDBACK_MESSAGE_MIN_LENGTH = 10;
const APP_FEEDBACK_MESSAGE_MAX_LENGTH = 1000;

// The UI intentionally offers 6 specific categories even though the
// backend only accepts 5 fixed values (AppFeedbackCategory) -- two labels
// below share one backend value ("사용성/흐름" + "디자인/모바일" -> "ux",
// "저장/복습 문제" + "버그/오류" -> "bug") so a beta tester can pick the
// option that actually matches what happened, without the API payload or
// backend enum changing. "기능 제안" folds into "기타" for the same reason.
// A plain <select> can't reliably stay in sync when two <option>s share a
// value, so this component tracks its own `key` locally and only ever
// reports the mapped backend `value` upward via onCategoryChange.
const categoryOptions: Array<{
  key: string;
  value: AppFeedbackCategory;
  label: string;
  placeholder: string;
}> = [
  {
    key: "flow",
    value: "ux",
    label: "사용성/흐름",
    placeholder:
      "어느 화면, 어느 단계에서 헷갈렸는지 적어주세요.\n예: 읽기 탭에서 단어 저장 버튼을 찾기 어려웠어요.",
  },
  {
    key: "meaning",
    value: "meaning",
    label: "단어 뜻 오류",
    placeholder: "단어, 화면에 보인 뜻, 기대한 뜻을 적어주세요.",
  },
  {
    key: "save_review",
    value: "bug",
    label: "저장/복습 문제",
    placeholder: "저장, 단어장, 복습 중 어떤 상황에서 문제가 생겼는지 적어주세요.",
  },
  {
    key: "design_mobile",
    value: "ux",
    label: "디자인/모바일",
    placeholder: "어떤 화면이 보기 불편했는지 적어주세요. 사용 기기/브라우저도 함께 적어주면 좋아요.",
  },
  {
    key: "bug",
    value: "bug",
    label: "버그/오류",
    placeholder: "오류가 난 화면과 눌렀던 버튼을 적어주세요.",
  },
  {
    key: "other",
    value: "other",
    label: "기타",
    placeholder: "그 외 의견이나 제안을 자유롭게 적어주세요.",
  },
];

function keyForCategory(category: AppFeedbackCategory): string {
  return categoryOptions.find((option) => option.value === category)?.key ?? "flow";
}

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

// App-wide "베타 피드백" dialog -- separate from MeaningFeedbackModal (a
// specific word's meaning report). This one is for anything else during the
// beta: confusing flows, save/review hiccups, design/mobile issues, bugs,
// or a quick "뜻 문제" pointer when the reading card's own "뜻 오류 신고"
// isn't the right fit.
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
  const [categoryKey, setCategoryKey] = useState(() => keyForCategory(category));
  const activeOption =
    categoryOptions.find((option) => option.key === categoryKey) ?? categoryOptions[0];

  function handleCategoryKeyChange(key: string) {
    setCategoryKey(key);
    const option = categoryOptions.find((item) => item.key === key);
    if (option) {
      onCategoryChange(option.value);
    }
  }

  const trimmedLength = message.trim().length;
  const isTooShort = trimmedLength > 0 && trimmedLength < APP_FEEDBACK_MESSAGE_MIN_LENGTH;
  const canSubmit = trimmedLength >= APP_FEEDBACK_MESSAGE_MIN_LENGTH && !isSubmitting;

  return (
    <div className="feedback-modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="feedback-modal"
        role="dialog"
        aria-modal="true"
        aria-label="베타 피드백 보내기"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="feedback-modal-header">
          <div>
            <h2 className="feedback-modal-title">베타 피드백</h2>
            <p className="muted-text feedback-modal-subtitle">
              막혔던 부분이나 어색했던 점을 알려주세요.
            </p>
          </div>
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
          어떤 종류인가요?
          <select
            value={categoryKey}
            onChange={(event) => handleCategoryKeyChange(event.target.value)}
          >
            {categoryOptions.map((option) => (
              <option key={option.key} value={option.key}>
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
            placeholder={activeOption.placeholder}
          />
        </label>
        <p className="meaning-feedback-hint">
          {message.length} / {APP_FEEDBACK_MESSAGE_MAX_LENGTH}자
          {isTooShort ? ` · 최소 ${APP_FEEDBACK_MESSAGE_MIN_LENGTH}자 이상 입력해 주세요.` : ""}
        </p>
        <p className="meaning-feedback-hint">
          원문 전체는 자동으로 첨부되지 않아요. 문제가 생긴 단어나 상황만 직접 적어주세요.
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

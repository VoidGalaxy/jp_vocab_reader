"use client";

import { classifyMessageTone } from "./coverageUtils";

const MAX_MEANING_KO_LENGTH = 200;

type MeaningQuickEditProps = {
  isEditing: boolean;
  draftValue: string;
  isSaving: boolean;
  message: string;
  onStartEdit: () => void;
  onDraftChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
};

// Shared by the vocab list, reading-tab word detail, and study card --
// a small "내 단어장 뜻 수정" affordance that PATCHes only meaning_ko on the
// user's own vocab item. All the actual state (which item is being edited,
// the draft text, save-in-flight) lives centrally in page.tsx so only one
// edit can be open across the whole app at a time.
export function MeaningQuickEdit({
  isEditing,
  draftValue,
  isSaving,
  message,
  onStartEdit,
  onDraftChange,
  onSave,
  onCancel,
}: MeaningQuickEditProps) {
  if (!isEditing) {
    return (
      <button
        type="button"
        className="ghost-button compact-button meaning-quick-edit-trigger"
        onClick={onStartEdit}
      >
        내 단어장 뜻 수정
      </button>
    );
  }

  return (
    <div className="meaning-quick-edit">
      <textarea
        className="compact-textarea"
        value={draftValue}
        onChange={(event) => onDraftChange(event.target.value)}
        rows={2}
        maxLength={MAX_MEANING_KO_LENGTH}
        aria-label="내 단어장 뜻 수정"
        autoFocus
      />
      <p className="meaning-quick-edit-hint">
        수정한 뜻은 내 단어장에만 적용돼요.
      </p>
      {message ? (
        <p className={`message message--${classifyMessageTone(message)} compact-message`}>
          {message}
        </p>
      ) : null}
      <div className="meaning-quick-edit-actions">
        <button type="button" onClick={onSave} disabled={isSaving}>
          {isSaving ? "저장 중..." : "저장"}
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={onCancel}
          disabled={isSaving}
        >
          취소
        </button>
      </div>
    </div>
  );
}

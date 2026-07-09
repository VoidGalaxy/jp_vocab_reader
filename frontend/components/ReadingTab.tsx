"use client";

import type { FormEvent } from "react";
import { ReaderMode } from "./ReaderMode";
import { computeReadingSaveSummary } from "./coverageUtils";
import type { ReadingSaveMode } from "./coverageUtils";
import type { Deck, TokenStatus, TokenWithStatus, VocabItem } from "./types";

type ReadingTabProps = {
  text: string;
  tokens: TokenWithStatus[];
  vocabItems: VocabItem[];
  decks: Deck[];
  selectedDeckId: string;
  isAnalyzing: boolean;
  message: string;
  isTextCollapsed: boolean;
  isSavingBatch: boolean;
  canStartFromSaved: boolean;
  onTextChange: (text: string) => void;
  onSelectedDeckChange: (deckId: string) => void;
  onAnalyze: (event: FormEvent<HTMLFormElement>) => void;
  onStatusChange: (index: number, status: TokenStatus) => void;
  onToggleTextCollapsed: () => void;
  onSaveBatch: (mode: ReadingSaveMode) => void;
  onStartStudyFromSaved: () => void;
};

const saveButtons: Array<{
  mode: ReadingSaveMode;
  label: string;
  hint: string;
}> = [
  { mode: "unknown_only", label: "모르는 단어 저장", hint: "unknown 상태 후보만 저장" },
  {
    mode: "unknown_uncertain",
    label: "모르는+헷갈리는 단어 저장",
    hint: "unknown + uncertain 저장",
  },
  {
    mode: "all_unclassified",
    label: "미분류까지 저장",
    hint: "unknown + uncertain + unclassified 저장",
  },
];

export function ReadingTab({
  text,
  tokens,
  vocabItems,
  decks,
  selectedDeckId,
  isAnalyzing,
  message,
  isTextCollapsed,
  isSavingBatch,
  canStartFromSaved,
  onTextChange,
  onSelectedDeckChange,
  onAnalyze,
  onStatusChange,
  onToggleTextCollapsed,
  onSaveBatch,
  onStartStudyFromSaved,
}: ReadingTabProps) {
  const hasResult = tokens.length > 0;
  const showForm = !hasResult || !isTextCollapsed;
  const summary = hasResult
    ? computeReadingSaveSummary(tokens, vocabItems, selectedDeckId)
    : null;

  return (
    <section className="tab-panel" aria-live="polite">
      <form className="analyze-form" onSubmit={onAnalyze}>
        <div className="reading-input-header">
          <label htmlFor="reading-source-text">원문</label>
          {hasResult ? (
            <button
              type="button"
              className="secondary-button compact-button"
              onClick={onToggleTextCollapsed}
            >
              {isTextCollapsed ? "원문 입력 펼치기" : "원문 입력 접기"}
            </button>
          ) : null}
        </div>

        {showForm ? (
          <>
            <textarea
              id="reading-source-text"
              value={text}
              onChange={(event) => onTextChange(event.target.value)}
              placeholder="彼は怠惰であることを自覚していた。"
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
            <div className="actions">
              <button type="submit" disabled={isAnalyzing || !selectedDeckId}>
                {isAnalyzing ? "분석 중..." : "읽기 분석"}
              </button>
            </div>
          </>
        ) : null}
      </form>

      <p className="muted-text copyright-note">
        입력한 원문은 본인 학습용으로 사용하세요. 원문 전체는 서버에 자동
        저장되지 않으며 공유 덱에 포함되지 않습니다. 단어 저장 시 해당
        단어가 포함된 짧은 문장만 예문으로 저장됩니다.
      </p>

      {message ? <p className="message">{message}</p> : null}

      {summary ? (
        <section className="reading-summary-panel">
          <div className="result-heading compact-heading">
            <div>
              <h2>이 텍스트 학습 요약</h2>
              <span>저장 가능 단어 {summary.saveableCount}개</span>
            </div>
          </div>
          <div className="reading-summary-grid" role="group" aria-label="이 텍스트 학습 요약">
            <div className="reading-summary-card">
              <span>새 단어</span>
              <strong>{summary.newCount}개</strong>
            </div>
            <div className="reading-summary-card">
              <span>모르는 단어</span>
              <strong>{summary.unknownCount}개</strong>
            </div>
            <div className="reading-summary-card">
              <span>헷갈리는 단어</span>
              <strong>{summary.uncertainCount}개</strong>
            </div>
            <div className="reading-summary-card">
              <span>이미 아는 단어</span>
              <strong>{summary.knownCount}개</strong>
            </div>
            <div className="reading-summary-card">
              <span>미분류 단어</span>
              <strong>{summary.unclassifiedCount}개</strong>
            </div>
          </div>
          <div className="reading-summary-actions">
            {saveButtons.map(({ mode, label, hint }) => (
              <button
                key={mode}
                type="button"
                className="secondary-button reading-summary-save-button"
                onClick={() => onSaveBatch(mode)}
                disabled={isSavingBatch || summary.saveableCount === 0}
                title={hint}
              >
                {isSavingBatch ? "저장 중..." : label}
              </button>
            ))}
            <button
              type="button"
              onClick={onStartStudyFromSaved}
              disabled={!canStartFromSaved}
            >
              저장한 단어로 바로 학습
            </button>
          </div>
        </section>
      ) : null}

      {hasResult ? (
        <ReaderMode tokens={tokens} onStatusChange={onStatusChange} />
      ) : !isAnalyzing ? (
        <p className="empty">
          덱을 선택하고 원문을 입력한 뒤 읽기 분석을 눌러주세요.
        </p>
      ) : null}
    </section>
  );
}

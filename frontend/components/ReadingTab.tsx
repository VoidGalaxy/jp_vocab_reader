"use client";

import type { FormEvent } from "react";
import { ReaderMode } from "./ReaderMode";
import type { Deck, TokenStatus, TokenWithStatus } from "./types";

type ReadingTabProps = {
  text: string;
  tokens: TokenWithStatus[];
  decks: Deck[];
  selectedDeckId: string;
  isAnalyzing: boolean;
  message: string;
  isTextCollapsed: boolean;
  onTextChange: (text: string) => void;
  onSelectedDeckChange: (deckId: string) => void;
  onAnalyze: (event: FormEvent<HTMLFormElement>) => void;
  onStatusChange: (index: number, status: TokenStatus) => void;
  onToggleTextCollapsed: () => void;
};

export function ReadingTab({
  text,
  tokens,
  decks,
  selectedDeckId,
  isAnalyzing,
  message,
  isTextCollapsed,
  onTextChange,
  onSelectedDeckChange,
  onAnalyze,
  onStatusChange,
  onToggleTextCollapsed,
}: ReadingTabProps) {
  const hasResult = tokens.length > 0;
  const showForm = !hasResult || !isTextCollapsed;

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
        저장되지 않으며 공유 덱에 포함되지 않습니다.
      </p>

      {message ? <p className="message">{message}</p> : null}

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

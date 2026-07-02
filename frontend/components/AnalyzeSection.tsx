"use client";

import type { FormEvent } from "react";
import { StatusSelect } from "./shared";
import type { Deck, TokenStatus, TokenWithStatus } from "./types";

type AnalyzeSectionProps = {
  text: string;
  tokens: TokenWithStatus[];
  isAnalyzing: boolean;
  isSaving: boolean;
  message: string;
  decks: Deck[];
  selectedDeckId: string;
  onTextChange: (text: string) => void;
  onSelectedDeckChange: (deckId: string) => void;
  onAnalyze: (event: FormEvent<HTMLFormElement>) => void;
  onSaveUnknown: () => void;
  onStatusChange: (index: number, status: TokenStatus) => void;
};

export function AnalyzeSection({
  text,
  tokens,
  isAnalyzing,
  isSaving,
  message,
  decks,
  selectedDeckId,
  onTextChange,
  onSelectedDeckChange,
  onAnalyze,
  onSaveUnknown,
  onStatusChange,
}: AnalyzeSectionProps) {
  return (
    <section className="tab-panel" aria-live="polite">
      <form className="analyze-form" onSubmit={onAnalyze}>
        <label htmlFor="source-text">원문</label>
        <textarea
          id="source-text"
          value={text}
          onChange={(event) => onTextChange(event.target.value)}
          placeholder="彼は怠惰であることを自覚していた。"
          rows={8}
        />
        <div className="actions">
          <button type="submit" disabled={isAnalyzing}>
            {isAnalyzing ? "분석 중..." : "분석하기"}
          </button>
        </div>
      </form>

      {message ? <p className="message">{message}</p> : null}

      <section className="result-section">
        <div className="result-heading">
          <div>
            <h2>분석 결과</h2>
            <span>{tokens.length}개</span>
          </div>
          <div className="heading-actions">
            <label className="inline-field">
              저장 덱
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
            <button
              type="button"
              onClick={onSaveUnknown}
              disabled={isSaving || tokens.length === 0 || !selectedDeckId}
            >
              {isSaving ? "저장 중..." : "모르는 단어 저장"}
            </button>
          </div>
        </div>

        {tokens.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>단어</th>
                  <th>기본형</th>
                  <th>읽기</th>
                  <th>품사</th>
                  <th>뜻</th>
                  <th>예문</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                {tokens.map((token, index) => (
                  <tr key={`${token.base_form}-${token.reading}-${index}`}>
                    <td>{token.surface}</td>
                    <td>{token.base_form}</td>
                    <td>{token.reading}</td>
                    <td>{token.part_of_speech}</td>
                    <td>{token.meaning_ko || "-"}</td>
                    <td>
                      <span className="example-text">
                        {token.example_sentence || "-"}
                      </span>
                    </td>
                    <td>
                      <StatusSelect
                        value={token.status}
                        label={`${token.surface} 상태`}
                        onChange={(status) => onStatusChange(index, status)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty">분석 결과가 아직 없습니다.</p>
        )}
      </section>
    </section>
  );
}

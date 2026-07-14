"use client";

import type { FormEvent } from "react";
import { CoverageSummary } from "./CoverageSummary";
import { classifyMessageTone, computeCoverageStats } from "./coverageUtils";
import { HighlightedExample } from "./HighlightedExample";
import { ShieldIcon } from "./icons";
import { StatusSelect, statusLabels } from "./shared";
import type {
  Deck,
  QualityTag,
  TokenStatus,
  TokenWithStatus,
  VocabItem,
} from "./types";

type ClassificationDraftSummary = {
  saved_at: string;
};

type AnalyzeSectionProps = {
  text: string;
  tokens: TokenWithStatus[];
  ignoredTokenCount: number;
  deckVocabItems: VocabItem[];
  isAnalyzing: boolean;
  isSaving: boolean;
  message: string;
  decks: Deck[];
  selectedDeckId: string;
  includeKnown: boolean;
  currentCardIndex: number;
  showAllResults: boolean;
  pendingDraft: ClassificationDraftSummary | null;
  draftSavedAt: string;
  onTextChange: (text: string) => void;
  onSelectedDeckChange: (deckId: string) => void;
  onIncludeKnownChange: (checked: boolean) => void;
  onAnalyze: (event: FormEvent<HTMLFormElement>) => void;
  onSaveSelected: () => void;
  onStatusChange: (index: number, status: TokenStatus) => void;
  onClassifyCurrent: (status: TokenStatus) => void;
  onPreviousCard: () => void;
  onShowAllResultsChange: (checked: boolean) => void;
  onRestoreDraft: () => void;
  onDiscardDraft: () => void;
  onViewInReadingTab: () => void;
};

export function AnalyzeSection({
  text,
  tokens,
  ignoredTokenCount,
  deckVocabItems,
  isAnalyzing,
  isSaving,
  message,
  decks,
  selectedDeckId,
  includeKnown,
  currentCardIndex,
  showAllResults,
  pendingDraft,
  draftSavedAt,
  onTextChange,
  onSelectedDeckChange,
  onIncludeKnownChange,
  onAnalyze,
  onSaveSelected,
  onStatusChange,
  onClassifyCurrent,
  onPreviousCard,
  onShowAllResultsChange,
  onRestoreDraft,
  onDiscardDraft,
  onViewInReadingTab,
}: AnalyzeSectionProps) {
  const currentToken = tokens[currentCardIndex];
  const classifiedCount = tokens.filter((token) => token.isClassified).length;
  const remainingCount = Math.max(tokens.length - classifiedCount, 0);
  const knownCount = tokens.filter((token) => token.status === "known").length;
  const uncertainCount = tokens.filter(
    (token) => token.status === "uncertain",
  ).length;
  const unknownCount = tokens.filter((token) => token.status === "unknown").length;
  const skippedCount = tokens.filter(
    (token) => token.isClassified && token.status === "unclassified",
  ).length;
  const isClassificationComplete =
    tokens.length > 0 && currentCardIndex >= tokens.length;
  const coverageStats = computeCoverageStats(
    tokens,
    deckVocabItems,
    selectedDeckId,
    ignoredTokenCount,
  );
  const savedAtText = draftSavedAt
    ? new Date(draftSavedAt).toLocaleString("ko-KR", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";

  return (
    <section className="tab-panel" aria-live="polite">
      <div className="reading-hero">
        <h2 className="reading-hero-title">단어 카드로 빠르게 분류하기</h2>
        <p className="reading-hero-subtitle">
          원문을 붙여넣고 단어를 한 장씩 카드로 넘기며 완벽히 아는 단어,
          헷갈리는 단어, 모르는 단어로 분류하세요.
        </p>
      </div>

      <section className="panel-card reading-input-card">
        <div className="panel-card-header">
          <h3 className="panel-card-title">원문 입력</h3>
          <p className="panel-card-description">
            읽고 싶은 일본어 문장을 붙여넣으세요.
          </p>
        </div>
        <form className="analyze-form" onSubmit={onAnalyze}>
          <label htmlFor="source-text">원문</label>
          <textarea
            id="source-text"
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
            placeholder="彼は怠惰であることを自覚していた。"
            rows={8}
          />
          <div className="analyze-options">
            <label className="inline-field">
              분석/저장 덱
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
            <label className="checkbox-field analyze-checkbox">
              <input
                type="checkbox"
                checked={includeKnown}
                onChange={(event) => onIncludeKnownChange(event.target.checked)}
              />
              완벽히 아는 단어도 표시
            </label>
          </div>
          <div className="actions">
            <button type="submit" disabled={isAnalyzing}>
              {isAnalyzing ? "분석 중..." : "분석하기"}
            </button>
          </div>
        </form>

        <p className="muted-text copyright-note">
          <ShieldIcon className="copyright-note-icon" />
          <span>
            입력한 원문은 본인 학습용으로 사용하세요. 원문 전체는 서버에
            저장되지 않으며, 공유 덱에도 원문 전체가 포함되지 않습니다.
          </span>
        </p>
      </section>

      {message ? (
        <p className={`message message--${classifyMessageTone(message)}`}>
          {message}
        </p>
      ) : null}

      {pendingDraft ? (
        <div className="draft-panel">
          <div>
            <strong>이전에 분류하던 분석 결과가 있습니다.</strong>
            <span>
              마지막 저장:{" "}
              {new Date(pendingDraft.saved_at).toLocaleString("ko-KR", {
                month: "2-digit",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
          <div className="draft-actions">
            <button type="button" onClick={onRestoreDraft}>
              이어하기
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={onDiscardDraft}
            >
              삭제하고 새로 시작
            </button>
          </div>
        </div>
      ) : null}

      <section className="result-section">
        <div className="result-heading">
          <div>
            <h2>분석 결과</h2>
            <span>
              {tokens.length > 0
                ? `${Math.min(currentCardIndex + 1, tokens.length)} / ${tokens.length}`
                : "0개"}
            </span>
          </div>
          <div className="heading-actions">
            {tokens.length > 0 ? (
              <button
                type="button"
                className="secondary-button compact-button"
                onClick={onViewInReadingTab}
              >
                이 원문을 읽기 탭에서 보기
              </button>
            ) : null}
            <button
              type="button"
              onClick={onSaveSelected}
              disabled={isSaving || tokens.length === 0 || !selectedDeckId}
              title={
                !selectedDeckId
                  ? "저장할 덱을 선택해 주세요."
                  : tokens.length === 0
                    ? "먼저 원문을 분석해 주세요."
                    : undefined
              }
            >
              {isSaving ? "저장 중..." : "분류한 단어 저장"}
            </button>
          </div>
        </div>

        {tokens.length > 0 ? (
          <>
            <CoverageSummary stats={coverageStats} />

            <div className="classification-summary">
              <span>분류 완료 {classifiedCount}개</span>
              <span>남은 단어 {remainingCount}개</span>
              <span>{statusLabels.known} {knownCount}개</span>
              <span>{statusLabels.uncertain} {uncertainCount}개</span>
              <span>{statusLabels.unknown} {unknownCount}개</span>
            </div>
            {savedAtText ? (
              <p className="draft-status">
                분류 진행상태 자동 저장 중 · 마지막 저장: {savedAtText}
              </p>
            ) : null}

            {!isClassificationComplete && currentToken ? (
              <div className="classify-card">
                <div className="classify-progress">
                  {currentCardIndex + 1} / {tokens.length}
                </div>
                <div className="classify-word">
                  {currentToken.surface || currentToken.base_form}
                </div>
                {currentToken.quality_tag !== "normal" ? (
                  <div className="term-badge-wrap">
                    <QualityBadge qualityTag={currentToken.quality_tag} />
                  </div>
                ) : null}
                <dl className="classify-details">
                  <div>
                    <dt>기본형</dt>
                    <dd>{currentToken.base_form || "-"}</dd>
                  </div>
                  <div>
                    <dt>읽기</dt>
                    <dd>{currentToken.reading || "-"}</dd>
                  </div>
                  <div>
                    <dt>품사</dt>
                    <dd>{currentToken.part_of_speech || "-"}</dd>
                  </div>
                  <div>
                    <dt>한국어 뜻</dt>
                    <dd>{currentToken.meaning_ko || "-"}</dd>
                  </div>
                  <div className="classify-example">
                    <dt>예문</dt>
                    <dd>{currentToken.example_sentence || "-"}</dd>
                  </div>
                </dl>
                <div className="classify-actions">
                  <button
                    type="button"
                    className="success-button"
                    onClick={() => onClassifyCurrent("known")}
                  >
                    완벽히 아는 단어
                  </button>
                  <button
                    type="button"
                    className="warning-button"
                    onClick={() => onClassifyCurrent("uncertain")}
                  >
                    헷갈리는 단어
                  </button>
                  <button
                    type="button"
                    className="danger-button"
                    onClick={() => onClassifyCurrent("unknown")}
                  >
                    모르는 단어
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => onClassifyCurrent("unclassified")}
                  >
                    건너뛰기
                  </button>
                </div>
                <div className="card-navigation">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={onPreviousCard}
                    disabled={currentCardIndex === 0}
                  >
                    이전
                  </button>
                </div>
              </div>
            ) : (
              <div className="classification-complete">
                <h3>분류 완료</h3>
                <div className="classification-summary final-summary">
                  <span>{statusLabels.known} {knownCount}개</span>
                  <span>{statusLabels.uncertain} {uncertainCount}개</span>
                  <span>{statusLabels.unknown} {unknownCount}개</span>
                  <span>건너뛴 단어 {skippedCount}개</span>
                </div>
                <button
                  type="button"
                  onClick={onSaveSelected}
                  disabled={isSaving || !selectedDeckId}
                  title={
                    !selectedDeckId ? "저장할 덱을 선택해 주세요." : undefined
                  }
                >
                  {isSaving ? "저장 중..." : "분류한 단어 저장"}
                </button>
                <p className="muted-text">
                  분류한 단어 저장 시 임시 저장이 삭제됩니다.
                </p>
              </div>
            )}

            <label className="checkbox-field show-results-toggle">
              <input
                type="checkbox"
                checked={showAllResults}
                onChange={(event) => onShowAllResultsChange(event.target.checked)}
              />
              전체 결과 보기
            </label>

            {showAllResults ? (
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
                        <td>
                          <div>{token.surface}</div>
                          <QualityBadge qualityTag={token.quality_tag} />
                        </td>
                        <td>{token.base_form}</td>
                        <td>{token.reading}</td>
                        <td>{token.part_of_speech}</td>
                        <td>
                          <div>{token.meaning_ko || "-"}</div>
                        </td>
                        <td>
                          <span className="example-text">
                            <HighlightedExample
                              sentence={token.example_sentence}
                              surface={token.surface}
                              baseForm={token.base_form}
                              normalizedForm={token.normalized_form}
                            />
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
            ) : null}
          </>
        ) : (
          <p className="empty">분석 결과가 아직 없습니다.</p>
        )}
      </section>
    </section>
  );
}

const qualityTagLabels: Record<Exclude<QualityTag, "normal">, string> = {
  custom_term: "사용자 용어",
  compound_verb: "복합동사",
  noun_phrase_candidate: "명사구 후보",
  known_phrase: "관용구",
};

function QualityBadge({ qualityTag }: { qualityTag: QualityTag }) {
  if (qualityTag === "normal") {
    return null;
  }

  return <span className="term-badge">{qualityTagLabels[qualityTag]}</span>;
}

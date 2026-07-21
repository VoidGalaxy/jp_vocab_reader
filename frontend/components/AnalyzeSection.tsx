"use client";

import { useState, type FormEvent } from "react";
import { AppEmptyState, StudyCompanion } from "./BrandElements";
import { CoverageSummary } from "./CoverageSummary";
import { classifyMessageTone, computeCoverageStats } from "./coverageUtils";
import { HighlightedExample } from "./HighlightedExample";
import {
  BookmarkIcon,
  BookIcon,
  CardFileIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  ClockIcon,
  ShieldIcon,
  SparkleIcon,
} from "./icons";
import { getDisplayMeaning, StatusSelect, statusLabels } from "./shared";
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
  onGoToVocab: () => void;
};

// Each classify action gets its own icon+hint, not just its own color --
// 아는 (차분한 확인) / 헷갈리는 (곧 다시) / 모르는 (책갈피처럼 담기) / 건너뛰기
// (그냥 지나가기) -- so the 4-way decision reads as four different actions,
// reusing the same rating-button visual recipe review cards already use.
const classifyRatingButtons: Array<{
  status: TokenStatus;
  label: string;
  hint: string;
  className: string;
  icon: (props: { className?: string }) => JSX.Element;
}> = [
  {
    status: "known",
    label: "아는 단어",
    hint: "이미 알아요",
    className: "rating-classify-known",
    icon: CheckCircleIcon,
  },
  {
    status: "uncertain",
    label: "헷갈리는 단어",
    hint: "다시 볼래요",
    className: "rating-classify-uncertain",
    icon: ClockIcon,
  },
  {
    status: "unknown",
    label: "모르는 단어",
    hint: "노트에 담을래요",
    className: "rating-classify-unknown",
    icon: BookmarkIcon,
  },
  {
    status: "unclassified",
    label: "건너뛰기",
    hint: "나중에 볼게요",
    className: "rating-classify-skip",
    icon: ChevronRightIcon,
  },
];

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
  onGoToVocab,
}: AnalyzeSectionProps) {
  const [isInputExpanded, setIsInputExpanded] = useState(false);
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

  const hasResult = tokens.length > 0;
  const showInputForm = !hasResult || isInputExpanded;

  return (
    <section className="tab-panel analyze-panel" aria-live="polite">
      <section className="reading-input-open">
        <div className="reading-input-open-header">
          <span className="reading-input-eyebrow">빠른 분류</span>
          <h2 className="reading-input-open-title">
            {hasResult ? "원문" : "단어를 빠르게 나눠볼까요?"}
          </h2>
          {!hasResult ? (
            <p className="reading-input-open-hint">
              원문에서 뽑은 단어를 카드처럼 넘기며 정리해요.
            </p>
          ) : null}
        </div>

        {hasResult ? (
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={() => setIsInputExpanded((value) => !value)}
          >
            {isInputExpanded ? "원문 접기" : "원문 수정"}
          </button>
        ) : null}

        {showInputForm ? (
          <form className="analyze-form" onSubmit={onAnalyze}>
            {!hasResult && !text.trim() ? (
              <AppEmptyState
                mood="reading"
                className="reading-empty-guide"
                title="분류할 원문을 붙여넣어 주세요"
                description="추출된 단어를 아는/헷갈리는/모르는 단어로 빠르게 나눠요."
              />
            ) : null}
            <label htmlFor="source-text" className="sr-only-label">
              원문
            </label>
            <textarea
              id="source-text"
              value={text}
              onChange={(event) => onTextChange(event.target.value)}
              placeholder="彼は怠惰であることを自覚していた。"
              rows={6}
            />
            <div className="reading-input-footer">
              <label className="reading-deck-picker">
                <CardFileIcon className="reading-deck-picker-icon" />
                <select
                  value={selectedDeckId}
                  onChange={(event) => onSelectedDeckChange(event.target.value)}
                  aria-label="분석/저장 덱"
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
              <div className="analyze-cta-row">
                <button
                  type="submit"
                  className="reading-open-button"
                  disabled={isAnalyzing}
                >
                  {isAnalyzing ? (
                    "나누는 중..."
                  ) : (
                    <>
                      <SparkleIcon className="button-icon" />
                      {hasResult ? "다시 분류하기" : "분류 카드 만들기"}
                    </>
                  )}
                </button>
                {!hasResult && pendingDraft ? (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={onRestoreDraft}
                  >
                    이전 분류 이어하기
                  </button>
                ) : null}
              </div>
            </div>
          </form>
        ) : null}

        {!hasResult && pendingDraft ? (
          <p className="draft-status">
            이전 분류 저장:{" "}
            {new Date(pendingDraft.saved_at).toLocaleString("ko-KR", {
              month: "2-digit",
              day: "2-digit",
              hour: "2-digit",
              minute: "2-digit",
            })}{" "}
            ·{" "}
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={onDiscardDraft}
            >
              삭제하고 새로 시작
            </button>
          </p>
        ) : null}

        <p className="muted-text copyright-note">
          <ShieldIcon className="copyright-note-icon" />
          <span>원문 전체는 저장하지 않고, 분석에만 사용됩니다.</span>
        </p>
      </section>

      {message ? (
        <p className={`message message--${classifyMessageTone(message)}`}>
          {message}
        </p>
      ) : null}

      {tokens.length > 0 ? (
        <section className="result-section">
          {!isClassificationComplete ? (
            <>
              <div className="classify-stage-toolbar">
                <button
                  type="button"
                  className="ghost-button compact-button"
                  onClick={onViewInReadingTab}
                >
                  읽기 탭에서 보기
                </button>
                <button
                  type="button"
                  className="ghost-button compact-button"
                  onClick={onSaveSelected}
                  disabled={isSaving || !selectedDeckId}
                  title={
                    !selectedDeckId ? "저장할 덱을 선택해 주세요." : undefined
                  }
                >
                  {isSaving ? "저장 중..." : "지금까지 저장"}
                </button>
              </div>
              {savedAtText ? (
                <p className="draft-status">
                  분류 진행상태 자동 저장 중 · 마지막 저장: {savedAtText}
                </p>
              ) : null}
            </>
          ) : null}

          <>
            {!isClassificationComplete && currentToken ? (
              <div className="classify-card">
                <div className="classify-progress">
                  {currentCardIndex + 1} / {tokens.length}
                </div>
                <div className="classify-word">
                  {currentToken.surface || currentToken.base_form}
                </div>
                {currentToken.reading &&
                currentToken.reading !==
                  (currentToken.surface || currentToken.base_form) ? (
                  <div className="token-sheet-reading classify-reading">
                    {currentToken.reading}
                  </div>
                ) : null}
                {currentToken.quality_tag !== "normal" ? (
                  <div className="term-badge-wrap">
                    <QualityBadge qualityTag={currentToken.quality_tag} />
                  </div>
                ) : null}

                <div className="token-sheet-meaning-block">
                  <span className="token-sheet-meaning-label">한국어 뜻</span>
                  <p className="token-sheet-meaning-value">
                    {getDisplayMeaning(currentToken.meaning_ko)}
                  </p>
                </div>

                <div className="token-sheet-meta-row">
                  {currentToken.base_form &&
                  currentToken.base_form !== currentToken.surface ? (
                    <span className="token-sheet-meta-tag">
                      기본형 {currentToken.base_form}
                    </span>
                  ) : null}
                  {currentToken.part_of_speech ? (
                    <span className="token-sheet-meta-tag">
                      {currentToken.part_of_speech}
                    </span>
                  ) : null}
                </div>

                <div className="context-example-block">
                  <p className="context-example-label">문맥 예문</p>
                  {currentToken.example_sentence ? (
                    <p className="context-example-text">
                      <HighlightedExample
                        sentence={currentToken.example_sentence}
                        surface={currentToken.surface}
                        baseForm={currentToken.base_form}
                        normalizedForm={currentToken.normalized_form}
                      />
                    </p>
                  ) : (
                    <p className="context-example-hint">예문을 찾지 못했습니다.</p>
                  )}
                </div>

                <div className="classify-actions" role="group" aria-label="단어 분류">
                  {classifyRatingButtons.map(({ status, label, hint, className, icon: Icon }) => (
                    <button
                      key={status}
                      type="button"
                      className={`rating-button ${className}`}
                      onClick={() => onClassifyCurrent(status)}
                    >
                      <Icon className="rating-icon" />
                      <span className="rating-label">{label}</span>
                      <span className="rating-hint">{hint}</span>
                    </button>
                  ))}
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
                <StudyCompanion mood="done" />
                <span className="brand-stamp">완료</span>
                <h3>단어 나누기를 마쳤어요.</h3>
                <CoverageSummary stats={coverageStats} />
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
                  {isSaving ? "저장 중..." : "모르는 단어 노트에 담기"}
                </button>
                <p className="muted-text">
                  저장 시 임시 저장이 삭제됩니다.
                </p>
                <div className="study-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={onViewInReadingTab}
                  >
                    <BookIcon className="button-icon" />
                    원문 읽기로 이동
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={onGoToVocab}
                  >
                    <CardFileIcon className="button-icon" />
                    어휘 노트 보기
                  </button>
                </div>
              </div>
            )}
          </>

          <label className="checkbox-field show-results-toggle">
            <input
              type="checkbox"
              checked={showAllResults}
              onChange={(event) => onShowAllResultsChange(event.target.checked)}
            />
            전체 결과를 목록으로 보기
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
                        <div>{getDisplayMeaning(token.meaning_ko)}</div>
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
        </section>
      ) : null}
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

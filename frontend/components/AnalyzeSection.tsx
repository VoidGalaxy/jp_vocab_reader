"use client";

import { useState, type FormEvent } from "react";
import { ShioriCharacter, ShioriMark, ShioriStamp } from "./Shiori";
import { CoverageSummary } from "./CoverageSummary";
import { classifyMessageTone, computeCoverageStats } from "./coverageUtils";
import type { CoverageStats } from "./types";
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

// ---------------------------------------------------------------------------
// ClassifyPaperInput -- the one text-entry form, reused by both the intro
// stage (large, hero-styled, paper-note textarea) and the post-result
// compact "원문 수정" editor (small, plain open-notebook form). A bare
// textarea+deck-picker+checkbox reads as an analysis tool no matter the
// copy around it, so the two variants exist so the *intro* screen never
// looks like that -- variant="stage" is the only one a first-time visit
// ever sees.
// ---------------------------------------------------------------------------
type ClassifyPaperInputProps = {
  variant: "stage" | "compact";
  text: string;
  decks: Deck[];
  selectedDeckId: string;
  includeKnown: boolean;
  isAnalyzing: boolean;
  submitLabel: string;
  onTextChange: (text: string) => void;
  onSelectedDeckChange: (deckId: string) => void;
  onIncludeKnownChange: (checked: boolean) => void;
  onAnalyze: (event: FormEvent<HTMLFormElement>) => void;
  secondaryAction?: { label: string; onClick: () => void };
};

function ClassifyPaperInput({
  variant,
  text,
  decks,
  selectedDeckId,
  includeKnown,
  isAnalyzing,
  submitLabel,
  onTextChange,
  onSelectedDeckChange,
  onIncludeKnownChange,
  onAnalyze,
  secondaryAction,
}: ClassifyPaperInputProps) {
  const isStage = variant === "stage";
  const submitButton = (
    <button type="submit" className="reading-open-button" disabled={isAnalyzing}>
      {isAnalyzing ? (
        "나누는 중..."
      ) : (
        <>
          <SparkleIcon className="button-icon" />
          {submitLabel}
        </>
      )}
    </button>
  );

  return (
    <form
      className={isStage ? "classify-paper-input" : "analyze-form"}
      onSubmit={onAnalyze}
    >
      <label htmlFor="source-text" className="sr-only-label">
        원문
      </label>
      <textarea
        id="source-text"
        className={isStage ? "classify-hero-textarea" : undefined}
        value={text}
        onChange={(event) => onTextChange(event.target.value)}
        placeholder="彼は怠惰であることを自覚していた。"
        rows={isStage ? 4 : 6}
      />
      <div className={isStage ? "classify-hero-footer" : "reading-input-footer"}>
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
        {!isStage ? <div className="analyze-cta-row">{submitButton}</div> : null}
      </div>
      {isStage ? (
        <div className="analyze-cta-row classify-hero-cta-row">
          {submitButton}
          {secondaryAction ? (
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={secondaryAction.onClick}
            >
              {secondaryAction.label}
            </button>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}

// ---------------------------------------------------------------------------
// ClassifyStageIntro -- the pre-analysis "stage/hero", not a bare form: a
// small Shiori guide + title + description stay visible the whole time
// (even while typing), the textarea reads as a paper note, and any
// resumeable draft shows as a small secondary CTA + one status line, never
// its own boxed panel competing with the main "분류 카드 만들기" CTA.
// ---------------------------------------------------------------------------
type ClassifyStageIntroProps = {
  text: string;
  decks: Deck[];
  selectedDeckId: string;
  includeKnown: boolean;
  isAnalyzing: boolean;
  pendingDraft: ClassificationDraftSummary | null;
  onTextChange: (text: string) => void;
  onSelectedDeckChange: (deckId: string) => void;
  onIncludeKnownChange: (checked: boolean) => void;
  onAnalyze: (event: FormEvent<HTMLFormElement>) => void;
  onRestoreDraft: () => void;
  onDiscardDraft: () => void;
};

function ClassifyStageIntro({
  text,
  decks,
  selectedDeckId,
  includeKnown,
  isAnalyzing,
  pendingDraft,
  onTextChange,
  onSelectedDeckChange,
  onIncludeKnownChange,
  onAnalyze,
  onRestoreDraft,
  onDiscardDraft,
}: ClassifyStageIntroProps) {
  return (
    <section className="classify-stage hero-card library-card-stage">
      <div className="classify-hero-header">
        <ShioriCharacter
          variant="classify"
          size="lg"
          className="shiori-glow classify-hero-companion"
        />
        <div>
          <span className="reading-input-eyebrow">빠른 분류</span>
          <h2>단어를 빠르게 나눠볼까요?</h2>
          <p>원문에서 뽑은 단어를 카드처럼 넘기며 정리해요.</p>
        </div>
      </div>

      <ClassifyPaperInput
        variant="stage"
        text={text}
        decks={decks}
        selectedDeckId={selectedDeckId}
        includeKnown={includeKnown}
        isAnalyzing={isAnalyzing}
        submitLabel="분류 카드 만들기"
        onTextChange={onTextChange}
        onSelectedDeckChange={onSelectedDeckChange}
        onIncludeKnownChange={onIncludeKnownChange}
        onAnalyze={onAnalyze}
        secondaryAction={
          pendingDraft
            ? { label: "이전 분류 이어하기", onClick: onRestoreDraft }
            : undefined
        }
      />

      {pendingDraft ? (
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
        <span>원문 전체는 서버에 저장하지 않습니다.</span>
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------
// ClassifyWordCard -- one word, shown large: surface first, reading/pos/
// base_form as small supporting chips, meaning_ko as the one emphasized
// block, context example as a small memo card. No status controls here --
// ClassifyActionGrid owns those, so this component is purely "what word is
// this".
// ---------------------------------------------------------------------------
function ClassifyWordCard({ token }: { token: TokenWithStatus }) {
  return (
    <>
      <div className="classify-word">{token.surface || token.base_form}</div>
      {token.reading && token.reading !== (token.surface || token.base_form) ? (
        <div className="token-sheet-reading classify-reading">{token.reading}</div>
      ) : null}
      {token.quality_tag !== "normal" ? (
        <div className="term-badge-wrap">
          <QualityBadge qualityTag={token.quality_tag} />
        </div>
      ) : null}

      <div className="token-sheet-meaning-block">
        <span className="token-sheet-meaning-label">한국어 뜻</span>
        <p className="token-sheet-meaning-value">
          {getDisplayMeaning(token.meaning_ko)}
        </p>
      </div>

      <div className="token-sheet-meta-row">
        {token.base_form && token.base_form !== token.surface ? (
          <span className="token-sheet-meta-tag">기본형 {token.base_form}</span>
        ) : null}
        {token.part_of_speech ? (
          <span className="token-sheet-meta-tag">{token.part_of_speech}</span>
        ) : null}
      </div>

      <div className="context-example-block">
        <p className="context-example-label">문맥 예문</p>
        {token.example_sentence ? (
          <p className="context-example-text">
            <HighlightedExample
              sentence={token.example_sentence}
              surface={token.surface}
              baseForm={token.base_form}
              normalizedForm={token.normalized_form}
            />
          </p>
        ) : (
          <p className="context-example-hint">예문을 찾지 못했습니다.</p>
        )}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// ClassifyActionGrid -- the 4-way decision (아는/헷갈리는/모르는/건너뛰기).
// Desktop: 4-across or 2x2 (CSS-driven); mobile: always 2x2 (see
// .analyze-panel .classify-action-grid mobile override).
// ---------------------------------------------------------------------------
function ClassifyActionGrid({
  onClassify,
}: {
  onClassify: (status: TokenStatus) => void;
}) {
  return (
    <div className="classify-action-grid classify-actions" role="group" aria-label="단어 분류">
      {classifyRatingButtons.map(({ status, label, hint, className, icon: Icon }) => (
        <button
          key={status}
          type="button"
          className={`rating-button ${className}`}
          onClick={() => onClassify(status)}
        >
          <Icon className="rating-icon" />
          <span className="rating-label">{label}</span>
          <span className="rating-hint">{hint}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ClassifyCardStage -- the in-progress screen: one word card, front and
// center, plus the small toolbar (읽기 탭에서 보기/지금까지 저장) that used
// to be a "분석 결과" dashboard heading. No result list/table lives here --
// that stays opt-in, rendered by the parent only after this stage (and
// ClassifyResultSummary) are done.
// ---------------------------------------------------------------------------
type ClassifyCardStageProps = {
  currentToken: TokenWithStatus;
  currentCardIndex: number;
  totalCount: number;
  savedAtText: string;
  isSaving: boolean;
  selectedDeckId: string;
  onClassifyCurrent: (status: TokenStatus) => void;
  onPreviousCard: () => void;
  onViewInReadingTab: () => void;
  onSaveSelected: () => void;
};

function ClassifyCardStage({
  currentToken,
  currentCardIndex,
  totalCount,
  savedAtText,
  isSaving,
  selectedDeckId,
  onClassifyCurrent,
  onPreviousCard,
  onViewInReadingTab,
  onSaveSelected,
}: ClassifyCardStageProps) {
  return (
    <div className="classify-card-stage">
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
          title={!selectedDeckId ? "저장할 덱을 선택해 주세요." : undefined}
        >
          {isSaving ? "저장 중..." : "지금까지 저장"}
        </button>
      </div>
      {savedAtText ? (
        <p className="draft-status">
          분류 진행상태 자동 저장 중 · 마지막 저장: {savedAtText}
        </p>
      ) : null}

      <div className="classify-word-card card-stack-surface">
        <div className="classify-progress">
          <ShioriMark variant="classify" />
          <span>
            {currentCardIndex + 1} / {totalCount}
          </span>
        </div>
        <ClassifyWordCard token={currentToken} />
        <ClassifyActionGrid onClassify={onClassifyCurrent} />
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
    </div>
  );
}

// ---------------------------------------------------------------------------
// ClassifyResultSummary -- shown only once every card has a status. Counts
// + the 3 next-step CTAs the core loop actually needs; no list/table here
// either.
// ---------------------------------------------------------------------------
type ClassifyResultSummaryProps = {
  coverageStats: CoverageStats;
  knownCount: number;
  uncertainCount: number;
  unknownCount: number;
  skippedCount: number;
  isSaving: boolean;
  selectedDeckId: string;
  onSaveSelected: () => void;
  onViewInReadingTab: () => void;
  onGoToVocab: () => void;
};

function ClassifyResultSummary({
  coverageStats,
  knownCount,
  uncertainCount,
  unknownCount,
  skippedCount,
  isSaving,
  selectedDeckId,
  onSaveSelected,
  onViewInReadingTab,
  onGoToVocab,
}: ClassifyResultSummaryProps) {
  return (
    <div className="classify-result-summary index-card-shell">
      <ShioriStamp variant="success" label="완료" />
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
        title={!selectedDeckId ? "저장할 덱을 선택해 주세요." : undefined}
      >
        {isSaving ? "저장 중..." : "모르는 단어 노트에 담기"}
      </button>
      <p className="muted-text">저장 시 임시 저장이 삭제됩니다.</p>
      <div className="study-actions">
        <button type="button" className="secondary-button" onClick={onViewInReadingTab}>
          <BookIcon className="button-icon" />
          원문 읽기로 이동
        </button>
        <button type="button" className="ghost-button" onClick={onGoToVocab}>
          <CardFileIcon className="button-icon" />
          어휘 노트 보기
        </button>
      </div>
    </div>
  );
}

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

  return (
    <section className="tab-panel analyze-panel" aria-live="polite">
      {!hasResult ? (
        <ClassifyStageIntro
          text={text}
          decks={decks}
          selectedDeckId={selectedDeckId}
          includeKnown={includeKnown}
          isAnalyzing={isAnalyzing}
          pendingDraft={pendingDraft}
          onTextChange={onTextChange}
          onSelectedDeckChange={onSelectedDeckChange}
          onIncludeKnownChange={onIncludeKnownChange}
          onAnalyze={onAnalyze}
          onRestoreDraft={onRestoreDraft}
          onDiscardDraft={onDiscardDraft}
        />
      ) : (
        // Once a result exists, the intro stage steps aside for a small
        // "원문 수정" affordance -- editing text is now a secondary/
        // maintenance action, not the screen's main event.
        <section className="reading-input-open">
          <div className="reading-input-open-header">
            <span className="reading-input-eyebrow">빠른 분류</span>
            <h2 className="reading-input-open-title">원문</h2>
          </div>

          <button
            type="button"
            className="ghost-button compact-button"
            onClick={() => setIsInputExpanded((value) => !value)}
          >
            {isInputExpanded ? "원문 접기" : "원문 수정"}
          </button>

          {isInputExpanded ? (
            <ClassifyPaperInput
              variant="compact"
              text={text}
              decks={decks}
              selectedDeckId={selectedDeckId}
              includeKnown={includeKnown}
              isAnalyzing={isAnalyzing}
              submitLabel="다시 분류하기"
              onTextChange={onTextChange}
              onSelectedDeckChange={onSelectedDeckChange}
              onIncludeKnownChange={onIncludeKnownChange}
              onAnalyze={onAnalyze}
            />
          ) : null}

          <p className="muted-text copyright-note">
            <ShieldIcon className="copyright-note-icon" />
            <span>원문 전체는 서버에 저장하지 않습니다.</span>
          </p>
        </section>
      )}

      {message ? (
        <p className={`message message--${classifyMessageTone(message)}`}>
          {message}
        </p>
      ) : null}

      {hasResult ? (
        <section className="classify-stage-outer">
          {!isClassificationComplete && currentToken ? (
            <ClassifyCardStage
              currentToken={currentToken}
              currentCardIndex={currentCardIndex}
              totalCount={tokens.length}
              savedAtText={savedAtText}
              isSaving={isSaving}
              selectedDeckId={selectedDeckId}
              onClassifyCurrent={onClassifyCurrent}
              onPreviousCard={onPreviousCard}
              onViewInReadingTab={onViewInReadingTab}
              onSaveSelected={onSaveSelected}
            />
          ) : (
            <ClassifyResultSummary
              coverageStats={coverageStats}
              knownCount={knownCount}
              uncertainCount={uncertainCount}
              unknownCount={unknownCount}
              skippedCount={skippedCount}
              isSaving={isSaving}
              selectedDeckId={selectedDeckId}
              onSaveSelected={onSaveSelected}
              onViewInReadingTab={onViewInReadingTab}
              onGoToVocab={onGoToVocab}
            />
          )}

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

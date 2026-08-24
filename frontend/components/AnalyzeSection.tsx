"use client";

import { useState, type FormEvent } from "react";
import { ShioriCharacter, ShioriStamp } from "./Shiori";
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
// ClassifyCompactEditor -- the post-result "원문 수정" editor only. Phase 156
// split this off of the old dual-variant ClassifyPaperInput: the intro
// stage no longer shares this component at all (see ClassifyDeskIntro
// below), so there is nothing left to branch on here -- a single plain
// open-notebook form, same as the "maintenance action" it has always been
// once a result exists.
// ---------------------------------------------------------------------------
type ClassifyCompactEditorProps = {
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
};

function ClassifyCompactEditor({
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
}: ClassifyCompactEditorProps) {
  return (
    <form className="analyze-form" onSubmit={onAnalyze}>
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
        </div>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// ClassifyDeskV2 -- Phase 165 (V2 scene reconstruction pilot). Replaces the
// Phase 156 ClassifyDeskIntro, which was still a CSS-drawn approximation of
// a desk (a plain textarea box + chip row + button, arranged in a grid).
// This version puts the real `v2-classify-card-desk-*` photo underneath as
// a layout anchor -- source slip, stamp CTA, and card tray are positioned
// against the actual paper/stamp/tray objects in the photo, not decoration
// behind an unchanged form. Every live element below (ClassifySourceSlipV2,
// ClassifyDeskChipRowV2, the stamp <button>, ClassifyCardTrayV2) is an
// absolutely-positioned sibling inside .classify-v2-scene, positioned
// independently per breakpoint (mobile 9:16 photo vs desktop 16:9 photo are
// two different compositions, not a crop of one image) rather than nested
// in a shared DOM order that would force the same relative placement on
// both.
// ---------------------------------------------------------------------------
function ClassifySourceSlipV2({
  text,
  onTextChange,
}: {
  text: string;
  onTextChange: (text: string) => void;
}) {
  return (
    <div className="classify-v2-slip-zone">
      <label htmlFor="source-text" className="classify-v2-slip-label">
        원문 slip
      </label>
      <textarea
        id="source-text"
        className="classify-v2-slip-textarea"
        value={text}
        onChange={(event) => onTextChange(event.target.value)}
        placeholder="彼は怠惰であることを自覚していた。"
        rows={3}
      />
    </div>
  );
}

// Deck select + "완벽히 아는 단어도 표시" toggle as two small paper chips.
// Positioned as its own absolutely-placed sibling (not nested inside the
// slip zone) so CSS can move the whole row to a different part of the
// photo on mobile vs desktop without touching the DOM.
function ClassifyDeskChipRowV2({
  decks,
  selectedDeckId,
  includeKnown,
  onSelectedDeckChange,
  onIncludeKnownChange,
}: {
  decks: Deck[];
  selectedDeckId: string;
  includeKnown: boolean;
  onSelectedDeckChange: (deckId: string) => void;
  onIncludeKnownChange: (checked: boolean) => void;
}) {
  return (
    <div className="classify-v2-chip-row">
      <label className="classify-v2-chip">
        <CardFileIcon className="classify-v2-chip-icon" />
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
      <label className="checkbox-field classify-v2-chip classify-v2-chip-checkbox">
        <input
          type="checkbox"
          checked={includeKnown}
          onChange={(event) => onIncludeKnownChange(event.target.checked)}
        />
        완벽히 아는 단어도 표시
      </label>
    </div>
  );
}

// The card tray zone now sits on top of the photographed card stack itself
// -- no more decorative CSS card fan (the photo already shows real cards).
// It only carries the resumeable-draft receipt, since that's the one real
// piece of state this zone needs to show before analysis has run.
function ClassifyCardTrayV2({
  pendingDraft,
  onRestoreDraft,
  onDiscardDraft,
}: {
  pendingDraft: ClassificationDraftSummary | null;
  onRestoreDraft: () => void;
  onDiscardDraft: () => void;
}) {
  return (
    <div className="classify-v2-tray-zone">
      <p className="classify-v2-tray-hint">
        원문을 나누면 이 카드함에 단어 카드가 한 장씩 쌓여요.
      </p>
      {pendingDraft ? (
        <div className="classify-draft-chip classify-v2-draft-chip">
          <ClockIcon className="classify-draft-chip-icon" />
          <span>
            이전 분류 저장:{" "}
            {new Date(pendingDraft.saved_at).toLocaleString("ko-KR", {
              month: "2-digit",
              day: "2-digit",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          <div className="classify-draft-chip-actions">
            <button type="button" className="classify-quiet-link" onClick={onRestoreDraft}>
              이어하기
            </button>
            <button type="button" className="classify-quiet-link" onClick={onDiscardDraft}>
              삭제하고 새로 시작
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

type ClassifyDeskV2Props = {
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

function ClassifyDeskV2({
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
}: ClassifyDeskV2Props) {
  return (
    <section className="classify-v2-root">
      <div className="classify-v2-heading">
        <span className="shiori-glow shiori-companion--section classify-v2-heading-companion">
          <ShioriCharacter variant="classify" size="sm" />
        </span>
        <div>
          <span className="reading-input-eyebrow">읽은 원문에서 카드 만들기</span>
          <h2>단어 카드를 만들어볼까요?</h2>
        </div>
      </div>

      <form className="classify-v2-scene" onSubmit={onAnalyze}>
        <ClassifySourceSlipV2 text={text} onTextChange={onTextChange} />
        <ClassifyDeskChipRowV2
          decks={decks}
          selectedDeckId={selectedDeckId}
          includeKnown={includeKnown}
          onSelectedDeckChange={onSelectedDeckChange}
          onIncludeKnownChange={onIncludeKnownChange}
        />
        <button type="submit" className="classify-v2-stamp-button" disabled={isAnalyzing}>
          {isAnalyzing ? (
            "나누는 중..."
          ) : (
            <>
              <SparkleIcon className="button-icon" />
              분류 카드 만들기
            </>
          )}
        </button>
        <ClassifyCardTrayV2
          pendingDraft={pendingDraft}
          onRestoreDraft={onRestoreDraft}
          onDiscardDraft={onDiscardDraft}
        />
      </form>

      <p className="muted-text copyright-note classify-v2-copyright">
        <ShieldIcon className="copyright-note-icon" />
        <span>원문 전체는 서버에 저장하지 않아요.</span>
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------
// ClassifyWordPrimary -- surface first, reading/quality-badge as small
// supporting chips, meaning_ko as the one emphasized block. This is the
// minimum a learner needs before making the 아는/헷갈리는/모르는/건너뛰기
// call, so it's the half of the old single ClassifyWordCard that stays
// directly above ClassifyActionGrid at every width (see
// ClassifyWordSecondary below for why the rest moved out). No status
// controls here -- ClassifyActionGrid owns those.
// ---------------------------------------------------------------------------
function ClassifyWordPrimary({ token }: { token: TokenWithStatus }) {
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
    </>
  );
}

// ---------------------------------------------------------------------------
// ClassifyWordSecondary -- base_form/POS tags + context example: useful
// reference, not required to make the classify decision (the meaning above
// already covers that). Phase 111 found this content, when bundled with
// ClassifyWordPrimary inside one shared wrapper, pushed
// ClassifyActionGrid's 4-way grid partially behind the fixed bottom nav on
// 320-390px phones on every single card. Phase 112 splits it into its own
// sibling of ClassifyActionGrid (still rendered right after it in source/
// desktop order, so the desktop card's visual rhythm is unchanged) purely
// so a mobile-only `order` rule (see .classify-word-card-secondary in
// globals.css) can move ClassifyActionGrid ahead of it -- the same
// order-only technique Phase 110 used for Study's .study-answer-reveal.
// Content, copy, and the example-sentence fallback are unchanged.
// ---------------------------------------------------------------------------
function ClassifyWordSecondary({ token }: { token: TokenWithStatus }) {
  return (
    <>
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
          <p className="context-example-hint">예문을 찾지 못했어요.</p>
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
// ClassifyProgressTally -- desktop-only side-rail readout of how the tokens
// classified so far break down (아는/헷갈리는/모르는/건너뜀). Reuses the same
// counts ClassifyResultSummary already receives, just live-updated mid-stage
// instead of only at completion, so the >=1024px work-aside always has real
// content instead of empty space next to the card stack (same "sticky rail
// beside the main surface" idea as Reading's .reader-inspector-rail).
// ---------------------------------------------------------------------------
function ClassifyProgressTally({
  knownCount,
  uncertainCount,
  unknownCount,
  skippedCount,
}: {
  knownCount: number;
  uncertainCount: number;
  unknownCount: number;
  skippedCount: number;
}) {
  return (
    <div className="analyze-tally" role="status" aria-live="polite">
      <span className="analyze-tally-stat analyze-tally-stat-known">
        <span>{statusLabels.known}</span>
        <strong>{knownCount}</strong>
      </span>
      <span className="analyze-tally-stat analyze-tally-stat-uncertain">
        <span>{statusLabels.uncertain}</span>
        <strong>{uncertainCount}</strong>
      </span>
      <span className="analyze-tally-stat analyze-tally-stat-unknown">
        <span>{statusLabels.unknown}</span>
        <strong>{unknownCount}</strong>
      </span>
      <span className="analyze-tally-stat analyze-tally-stat-skip">
        <span>건너뜀</span>
        <strong>{skippedCount}</strong>
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ClassifyCardStage -- the in-progress screen: one word card, front and
// center, plus the small toolbar (읽기 탭에서 보기/지금까지 저장) that used
// to be a "분석 결과" dashboard heading. No result list/table lives here --
// that stays opt-in, rendered by the parent only after this stage (and
// ClassifyResultSummary) are done. At >=1024px the toolbar/tally move into a
// sticky work-aside beside the card (.analyze-work-scene), so the screen
// reads as a small work desk with the card in the middle instead of a
// toolbar stacked above a form; below that it stays the same single column
// as before this pass.
// ---------------------------------------------------------------------------
type ClassifyCardStageProps = {
  currentToken: TokenWithStatus;
  currentCardIndex: number;
  totalCount: number;
  savedAtText: string;
  isSaving: boolean;
  selectedDeckId: string;
  knownCount: number;
  uncertainCount: number;
  unknownCount: number;
  skippedCount: number;
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
  knownCount,
  uncertainCount,
  unknownCount,
  skippedCount,
  onClassifyCurrent,
  onPreviousCard,
  onViewInReadingTab,
  onSaveSelected,
}: ClassifyCardStageProps) {
  return (
    <div className="classify-card-stage analyze-work-scene">
      <div className="analyze-work-main">
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
            <span className="classify-progress-marker">
              <CardFileIcon className="classify-progress-marker-icon" />
              {currentCardIndex + 1} / {totalCount}
            </span>
          </div>
          <div className="classify-word-card-content app-slide-up" key={`primary-${currentCardIndex}`}>
            <ClassifyWordPrimary token={currentToken} />
          </div>
          <div className="classify-word-card-secondary app-slide-up" key={`secondary-${currentCardIndex}`}>
            <ClassifyWordSecondary token={currentToken} />
          </div>
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

      <aside className="analyze-work-aside">
        <p className="analyze-work-aside-label">지금까지 나눈 단어</p>
        <ClassifyProgressTally
          knownCount={knownCount}
          uncertainCount={uncertainCount}
          unknownCount={unknownCount}
          skippedCount={skippedCount}
        />
      </aside>
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
    // Phase 156 -- was a plain pill row (.classification-summary) reading
    // as a dashboard stat strip right under a "완료" heading. Now a small
    // fanned stack of result cards (.classify-result-cards), the same
    // "paper card" shape ClassifyCardTray previews before analysis --
    // this is the real, filled-in version of that earlier blank preview,
    // so the desk scene reads as slip -> blank card tray -> finished card
    // bundle, not form -> dashboard summary. Copy now frames the save
    // action as putting a finished card bundle into the notebook, not a
    // generic "저장" submit.
    <div className="classify-result-summary">
      <ShioriStamp variant="success" label="완료" />
      <h3>단어 카드 묶음을 다 만들었어요.</h3>
      <CoverageSummary stats={coverageStats} />
      <div className="classify-result-cards">
        <span className="classify-result-card">
          <span>{statusLabels.known}</span>
          <strong>{knownCount}개</strong>
        </span>
        <span className="classify-result-card">
          <span>{statusLabels.uncertain}</span>
          <strong>{uncertainCount}개</strong>
        </span>
        <span className="classify-result-card">
          <span>{statusLabels.unknown}</span>
          <strong>{unknownCount}개</strong>
        </span>
        <span className="classify-result-card">
          <span>건너뛴 단어</span>
          <strong>{skippedCount}개</strong>
        </span>
      </div>
      <button
        type="button"
        className="classify-save-button"
        onClick={onSaveSelected}
        disabled={isSaving || !selectedDeckId}
        title={!selectedDeckId ? "저장할 덱을 선택해 주세요." : undefined}
      >
        {isSaving ? "저장 중..." : "카드 묶음 노트에 붙이기"}
      </button>
      <p className="muted-text">저장하면 임시 저장은 삭제돼요.</p>
      <div className="study-actions">
        <button
          type="button"
          className="study-actions-link-button"
          onClick={onViewInReadingTab}
        >
          <BookIcon className="button-icon" />
          원문 읽기로 이동
        </button>
        <button
          type="button"
          className="study-actions-link-button"
          onClick={onGoToVocab}
        >
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
        <ClassifyDeskV2
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
            className="ghost-button compact-button classify-source-toggle"
            onClick={() => setIsInputExpanded((value) => !value)}
          >
            {isInputExpanded ? "원문 접기" : "원문 수정"}
          </button>

          {isInputExpanded ? (
            <ClassifyCompactEditor
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
            <span>원문 전체는 서버에 저장하지 않아요.</span>
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
              knownCount={knownCount}
              uncertainCount={uncertainCount}
              unknownCount={unknownCount}
              skippedCount={skippedCount}
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
            <div className="classify-ledger-wrap">
              <table className="classify-ledger">
                <colgroup>
                  <col className="classify-ledger-col-surface" />
                  <col className="classify-ledger-col-baseform" />
                  <col className="classify-ledger-col-reading" />
                  <col className="classify-ledger-col-pos" />
                  <col className="classify-ledger-col-meaning" />
                  <col className="classify-ledger-col-example" />
                  <col className="classify-ledger-col-status" />
                </colgroup>
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
                      <td data-label="단어">
                        <div>{token.surface}</div>
                        <QualityBadge qualityTag={token.quality_tag} />
                      </td>
                      <td data-label="기본형">{token.base_form}</td>
                      <td data-label="읽기">{token.reading}</td>
                      <td data-label="품사">{token.part_of_speech}</td>
                      <td data-label="뜻">
                        <div>{getDisplayMeaning(token.meaning_ko)}</div>
                      </td>
                      <td data-label="예문">
                        <span className="example-text">
                          <HighlightedExample
                            sentence={token.example_sentence}
                            surface={token.surface}
                            baseForm={token.base_form}
                            normalizedForm={token.normalized_form}
                          />
                        </span>
                      </td>
                      <td data-label="상태">
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

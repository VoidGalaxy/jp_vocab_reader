"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { TokenStatus, TokenWithStatus } from "./types";
import { TokenChip } from "./TokenChip";
import { TokenDetailSheet } from "./TokenDetailSheet";
import { buildReaderLayout, getNavigableTokenIndexes } from "./readerLayout";
import { getTokenGroupKey } from "./coverageUtils";

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

type ReaderModeProps = {
  originalText: string;
  tokens: TokenWithStatus[];
  onStatusChange: (index: number, status: TokenStatus) => void;
  initialSelectedTokenKey?: string | null;
  onSelectedTokenKeyChange?: (key: string | null) => void;
  meaningEditItemId: number | null;
  meaningEditDraft: string;
  isSavingMeaningEdit: boolean;
  meaningEditMessage: string;
  onStartMeaningEdit: (itemId: number, currentMeaning: string) => void;
  onMeaningEditDraftChange: (value: string) => void;
  onSaveMeaningEdit: () => void;
  onCancelMeaningEdit: () => void;
  onReportMeaning: (token: TokenWithStatus) => void;
};

export function ReaderMode({
  originalText,
  tokens,
  onStatusChange,
  initialSelectedTokenKey = null,
  onSelectedTokenKeyChange,
  meaningEditItemId,
  meaningEditDraft,
  isSavingMeaningEdit,
  meaningEditMessage,
  onStartMeaningEdit,
  onMeaningEditDraftChange,
  onSaveMeaningEdit,
  onCancelMeaningEdit,
  onReportMeaning,
}: ReaderModeProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [focusMode, setFocusMode] = useState(false);
  const [showJlptTags, setShowJlptTags] = useState(true);
  // Guards against re-applying a restored selection every time tokens
  // change (e.g. after a status save) -- only ever resolved once, right
  // after a restore, then the user's own clicks take over.
  const [hasAppliedInitialSelection, setHasAppliedInitialSelection] =
    useState(false);
  const readerTextRef = useRef<HTMLDivElement | null>(null);

  const layout = useMemo(
    () => buildReaderLayout(originalText, tokens),
    [originalText, tokens],
  );

  // Previous/next order follows tokens[] directly (already first-occurrence
  // text order -- see getNavigableTokenIndexes), not the rendered layout.
  const navigableIndexes = useMemo(
    () => getNavigableTokenIndexes(tokens),
    [tokens],
  );

  useEffect(() => {
    if (
      hasAppliedInitialSelection ||
      !initialSelectedTokenKey ||
      tokens.length === 0
    ) {
      return;
    }
    const matchIndex = tokens.findIndex(
      (token) => getTokenGroupKey(token) === initialSelectedTokenKey,
    );
    if (matchIndex !== -1) {
      setActiveIndex(matchIndex);
    }
    setHasAppliedInitialSelection(true);
  }, [hasAppliedInitialSelection, initialSelectedTokenKey, tokens]);

  // Keeps the selected word visible in the source text as prev/next moves
  // it around -- best-effort only, so a missing DOM match (e.g. the active
  // token fell into the "unmatched" fallback row) is silently skipped.
  useEffect(() => {
    if (activeIndex === null || !readerTextRef.current) {
      return;
    }
    const target = readerTextRef.current.querySelector(
      `[data-token-index="${activeIndex}"]`,
    );
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [activeIndex]);

  useEffect(() => {
    if (activeIndex === null) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target)) {
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        goToNext();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        goToPrev();
      } else if (event.key === "Escape") {
        closeDetail();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeIndex, navigableIndexes]);

  if (tokens.length === 0) {
    return null;
  }

  function selectToken(index: number) {
    setActiveIndex(index);
    onSelectedTokenKeyChange?.(getTokenGroupKey(tokens[index]));
  }

  function closeDetail() {
    setActiveIndex(null);
    onSelectedTokenKeyChange?.(null);
  }

  const navPosition = activeIndex !== null ? navigableIndexes.indexOf(activeIndex) : -1;
  const canGoPrev = navPosition > 0;
  const canGoNext = navPosition !== -1 && navPosition < navigableIndexes.length - 1;

  function goToPrev() {
    if (navPosition > 0) {
      selectToken(navigableIndexes[navPosition - 1]);
    }
  }

  function goToNext() {
    if (navPosition !== -1 && navPosition < navigableIndexes.length - 1) {
      selectToken(navigableIndexes[navPosition + 1]);
    }
  }

  const activeToken = activeIndex !== null ? tokens[activeIndex] : null;

  return (
    <div className="reader-mode">
      <div className="reader-mode-header-row">
        <div>
          <h3 className="reader-mode-title">읽기 모드</h3>
          <p className="reader-mode-hint">
            원문을 읽으면서 단어를 누르면 뜻과 상태를 확인하고 바로 분류할 수
            있습니다.
          </p>
        </div>
        <div className="reader-mode-toggles">
          <label className="checkbox-field reading-focus-toggle">
            <input
              type="checkbox"
              checked={focusMode}
              onChange={(event) => setFocusMode(event.target.checked)}
            />
            모르는/헷갈리는 단어만 강조
          </label>
          <label className="checkbox-field reading-jlpt-toggle">
            <input
              type="checkbox"
              checked={showJlptTags}
              onChange={(event) => setShowJlptTags(event.target.checked)}
            />
            JLPT 태그 표시
          </label>
        </div>
      </div>
      <div className="reader-legend">
        <span className="legend-title">단어 상태 색상</span>
        <span className="legend-item">
          <span className="legend-swatch token-chip-known" /> 아는 단어
        </span>
        <span className="legend-item">
          <span className="legend-swatch token-chip-uncertain" /> 헷갈리는 단어
        </span>
        <span className="legend-item">
          <span className="legend-swatch token-chip-unknown" /> 모르는 단어
        </span>
        <span className="legend-item">
          <span className="legend-swatch token-chip-unclassified" /> 미분류
        </span>
      </div>
      <div className="reader-text" ref={readerTextRef}>
        {layout.lines.map((line, lineIndex) => (
          <p className="reader-line" key={`line-${lineIndex}`}>
            {line.length > 0
              ? line.map((segment) =>
                  segment.type === "token" ? (
                    <TokenChip
                      key={segment.key}
                      token={tokens[segment.tokenIndex]}
                      tokenIndex={segment.tokenIndex}
                      isActive={activeIndex === segment.tokenIndex}
                      focusMode={focusMode}
                      showJlptTags={showJlptTags}
                      onSelect={() => selectToken(segment.tokenIndex)}
                    />
                  ) : (
                    <span key={segment.key}>{segment.content}</span>
                  ),
                )
              : " "}
          </p>
        ))}
      </div>
      {layout.unmatchedTokenIndexes.length > 0 ? (
        <div className="reader-unmatched-row">
          <span className="reader-unmatched-label">
            원문 위치를 찾지 못한 단어
          </span>
          <div className="reader-unmatched-chips">
            {layout.unmatchedTokenIndexes.map((tokenIndex) => (
              <TokenChip
                key={`unmatched-${tokenIndex}`}
                token={tokens[tokenIndex]}
                tokenIndex={tokenIndex}
                isActive={activeIndex === tokenIndex}
                focusMode={focusMode}
                showJlptTags={showJlptTags}
                onSelect={() => selectToken(tokenIndex)}
              />
            ))}
          </div>
        </div>
      ) : null}
      {activeToken ? (
        <TokenDetailSheet
          token={activeToken}
          onClose={closeDetail}
          onStatusChange={(status) => {
            if (activeIndex !== null) {
              onStatusChange(activeIndex, status);
            }
          }}
          onPrevious={goToPrev}
          onNext={goToNext}
          canGoPrevious={canGoPrev}
          canGoNext={canGoNext}
          positionLabel={
            navPosition !== -1
              ? `${navPosition + 1} / ${navigableIndexes.length}`
              : null
          }
          meaningEditItemId={meaningEditItemId}
          meaningEditDraft={meaningEditDraft}
          isSavingMeaningEdit={isSavingMeaningEdit}
          meaningEditMessage={meaningEditMessage}
          onStartMeaningEdit={onStartMeaningEdit}
          onMeaningEditDraftChange={onMeaningEditDraftChange}
          onSaveMeaningEdit={onSaveMeaningEdit}
          onCancelMeaningEdit={onCancelMeaningEdit}
          onReportMeaning={onReportMeaning}
        />
      ) : null}
    </div>
  );
}

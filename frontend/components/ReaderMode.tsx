"use client";

import { useState } from "react";
import type { TokenStatus, TokenWithStatus } from "./types";
import { TokenChip } from "./TokenChip";
import { TokenDetailSheet } from "./TokenDetailSheet";

type ReaderModeProps = {
  tokens: TokenWithStatus[];
  onStatusChange: (index: number, status: TokenStatus) => void;
};

type SentenceGroup = {
  sentence: string;
  items: { token: TokenWithStatus; index: number }[];
};

// Tokens don't carry original character offsets (analyze_with_raw already
// dedupes by base_form and drops particles/punctuation before the frontend
// ever sees them), so exact original-text reconstruction isn't possible
// without a backend change. Instead, consecutive tokens that share the same
// example_sentence (already computed per-token on the backend) are grouped
// into one line -- a reasonably natural sentence-by-sentence read without
// needing new backend fields.
function groupTokensBySentence(tokens: TokenWithStatus[]): SentenceGroup[] {
  const groups: SentenceGroup[] = [];
  tokens.forEach((token, index) => {
    const sentence = token.example_sentence || "";
    const last = groups[groups.length - 1];
    if (last && last.sentence === sentence) {
      last.items.push({ token, index });
    } else {
      groups.push({ sentence, items: [{ token, index }] });
    }
  });
  return groups;
}

export function ReaderMode({ tokens, onStatusChange }: ReaderModeProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [focusMode, setFocusMode] = useState(false);
  const [showJlptTags, setShowJlptTags] = useState(true);

  if (tokens.length === 0) {
    return null;
  }

  const groups = groupTokensBySentence(tokens);
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
      <div className="reader-text">
        {groups.map((group, groupIndex) => (
          <p
            className="reader-sentence"
            key={`sentence-${groupIndex}-${group.items[0]?.index ?? groupIndex}`}
          >
            {group.items.map(({ token, index }) => (
              <TokenChip
                key={`${token.base_form}-${token.reading}-${index}`}
                token={token}
                isActive={activeIndex === index}
                focusMode={focusMode}
                showJlptTags={showJlptTags}
                onSelect={() => setActiveIndex(index)}
              />
            ))}
          </p>
        ))}
      </div>
      <div className="reader-legend">
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
      {activeToken ? (
        <TokenDetailSheet
          token={activeToken}
          onClose={() => setActiveIndex(null)}
          onStatusChange={(status) => {
            if (activeIndex !== null) {
              onStatusChange(activeIndex, status);
            }
          }}
        />
      ) : null}
    </div>
  );
}

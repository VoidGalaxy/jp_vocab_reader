"use client";

import type { TokenStatus } from "./types";

export const statusLabels: Record<TokenStatus, string> = {
  known: "완벽히 아는 단어",
  uncertain: "헷갈리는 단어",
  unknown: "모르는 단어",
  unclassified: "분류되지 않음",
};

export function StatusSelect({
  value,
  label,
  onChange,
}: {
  value: TokenStatus;
  label: string;
  onChange: (status: TokenStatus) => void;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value as TokenStatus)}
      aria-label={label}
    >
      {Object.entries(statusLabels).map(([status, labelText]) => (
        <option key={status} value={status}>
          {labelText}
        </option>
      ))}
    </select>
  );
}

export function formatDateTime(value: string | null) {
  if (!value) {
    return "-";
  }

  return new Date(value).toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatNextReview(value: string | null) {
  if (!value) {
    return "다음 복습: 미정";
  }

  return `다음 복습: ${new Date(value).toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })}`;
}

const JLPT_LEVEL_PATTERN = /^JLPT\s*(N[1-5])\s*추천\s*어휘/;
const JLPT_LEVEL_ORDER: Record<string, number> = {
  N5: 0,
  N4: 1,
  N3: 2,
  N2: 3,
  N1: 4,
};

export function getJlptLevel(title: string): string | null {
  const match = title.match(JLPT_LEVEL_PATTERN);
  return match ? match[1] : null;
}

export function sortSharedDecksByJlptLevel<T extends { title: string }>(
  decks: T[],
): T[] {
  return [...decks].sort((a, b) => {
    const levelA = getJlptLevel(a.title);
    const levelB = getJlptLevel(b.title);
    if (levelA && levelB) {
      return JLPT_LEVEL_ORDER[levelA] - JLPT_LEVEL_ORDER[levelB];
    }
    if (levelA && !levelB) {
      return -1;
    }
    if (!levelA && levelB) {
      return 1;
    }
    return 0;
  });
}

const KOREAN_SYLLABLE_START = 0xac00;
const KOREAN_SYLLABLE_END = 0xd7a3;

export function withObjectParticle(word: string) {
  const lastChar = word.charCodeAt(word.length - 1);
  const hasBatchim =
    lastChar >= KOREAN_SYLLABLE_START &&
    lastChar <= KOREAN_SYLLABLE_END &&
    (lastChar - KOREAN_SYLLABLE_START) % 28 !== 0;
  return `${word}${hasBatchim ? "을" : "를"}`;
}

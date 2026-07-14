"use client";

import type { TokenStatus } from "./types";

// A meaning_ko value is only worth showing as "the Korean meaning" if it
// actually contains Korean text. The backend's custom-term bypass and any
// already-saved data from before that guard existed can still carry a raw
// English gloss, a bare Japanese reading, or a leftover placeholder string
// ("TODO", "확인 필요", ...) -- any of those showing up as-is would read as
// a broken/untrustworthy product to a learner expecting a Korean
// definition. This is a display-time-only guard (never touches what's
// stored): every screen that shows a saved meaning_ko should route through
// this one function so the fallback wording and rule stay identical
// everywhere, instead of each screen inventing its own "-" / "뜻 후보 없음"
// fallback. Never apply this to a value about to be pre-filled into an
// *edit* field -- editing needs the real raw stored value, not the
// fallback text, or saving would overwrite it with the fallback itself.
const MEANING_PLACEHOLDER_VALUES = new Set([
  "todo",
  "tbd",
  "n/a",
  "na",
  "none",
  "null",
  "undefined",
  "meaning_needs_review",
  "source english",
  "english gloss",
  "확인 필요",
  "확인필요",
  "미정",
]);

const HANGUL_PATTERN = /[가-힣]/;

export const DEFAULT_MEANING_FALLBACK = "한국어 뜻을 찾지 못했습니다.";

export function getDisplayMeaning(
  meaningKo: string | null | undefined,
  fallback: string = DEFAULT_MEANING_FALLBACK,
): string {
  const trimmed = (meaningKo || "").trim();
  if (!trimmed) {
    return fallback;
  }
  if (MEANING_PLACEHOLDER_VALUES.has(trimmed.toLowerCase())) {
    return fallback;
  }
  if (!HANGUL_PATTERN.test(trimmed)) {
    return fallback;
  }
  return trimmed;
}

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

// Matches both the documented "JLPT {level} 추천 어휘" naming and the
// "{level}어휘모음" naming currently used by the live registered decks.
const JLPT_LEVEL_PATTERN =
  /^(?:JLPT\s*(N[1-5])\s*추천\s*어휘|(N[1-5])어휘모음)/;
const JLPT_LEVEL_ORDER: Record<string, number> = {
  N5: 0,
  N4: 1,
  N3: 2,
  N2: 3,
  N1: 4,
};

export function getJlptLevel(title: string): string | null {
  const match = title.match(JLPT_LEVEL_PATTERN);
  if (!match) {
    return null;
  }
  return match[1] || match[2] || null;
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

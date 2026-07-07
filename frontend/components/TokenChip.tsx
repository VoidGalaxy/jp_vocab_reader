"use client";

import type { TokenWithStatus } from "./types";
import { statusLabels } from "./shared";

// Part-of-speech tags that reach the frontend but read as function
// words/fillers (particles/aux verbs/symbols are already filtered out on the
// backend). Rendered muted/pale so they don't compete visually with content
// words in reader mode.
const FUNCTION_LIKE_POS = new Set([
  "감탄사",
  "접속사",
  "연체사",
  "접두사",
  "접미사",
  "기호",
]);

export function isMutedToken(token: Pick<TokenWithStatus, "part_of_speech">): boolean {
  return FUNCTION_LIKE_POS.has(token.part_of_speech);
}

type TokenChipProps = {
  token: TokenWithStatus;
  onSelect: () => void;
};

export function TokenChip({ token, onSelect }: TokenChipProps) {
  const label = token.surface || token.base_form;
  const muted = isMutedToken(token);
  const statusClass = muted ? "token-chip-muted" : `token-chip-${token.status}`;
  const title = [
    token.base_form && token.base_form !== token.surface
      ? `기본형: ${token.base_form}`
      : null,
    token.reading ? `읽기: ${token.reading}` : null,
    token.meaning_ko ? `뜻: ${token.meaning_ko}` : "뜻 후보 없음",
    `상태: ${statusLabels[token.status]}`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      type="button"
      className={`token-chip ${statusClass}`}
      onClick={onSelect}
      title={title}
      aria-label={`${label}, ${statusLabels[token.status]}`}
    >
      {label}
    </button>
  );
}

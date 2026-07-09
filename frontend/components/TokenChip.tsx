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
  isActive: boolean;
  focusMode: boolean;
  showJlptTags: boolean;
  onSelect: () => void;
};

export function TokenChip({
  token,
  isActive,
  focusMode,
  showJlptTags,
  onSelect,
}: TokenChipProps) {
  const label = token.surface || token.base_form;
  const muted = isMutedToken(token);
  // focusMode ("모르는/헷갈리는 단어만 강조") mutes known/unclassified words down to
  // plain text so only unknown/uncertain words stand out while reading.
  const isEmphasizedStatus =
    token.status === "unknown" || token.status === "uncertain";
  const showStatusColor = !muted && (!focusMode || isEmphasizedStatus);
  const statusClass = muted
    ? "token-chip-muted"
    : showStatusColor
      ? `token-chip-${token.status}`
      : "token-chip-plain";
  const classNames = ["token-chip", statusClass];
  if (isActive) {
    classNames.push("token-chip-active");
  }
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
  const jlptLevel = showJlptTags ? token.jlpt_level : null;

  return (
    <button
      type="button"
      className={classNames.join(" ")}
      onClick={onSelect}
      title={
        jlptLevel ? `${title} · JLPT 추천 레벨: ${jlptLevel}` : title
      }
      aria-label={
        jlptLevel
          ? `${label}, ${statusLabels[token.status]}, JLPT 추천 레벨 ${jlptLevel}`
          : `${label}, ${statusLabels[token.status]}`
      }
    >
      {label}
      {jlptLevel ? (
        <span className="jlpt-chip-badge">{jlptLevel}</span>
      ) : null}
    </button>
  );
}

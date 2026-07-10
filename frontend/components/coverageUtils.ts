import type {
  CoverageStats,
  PriorityVocabEntry,
  TokenStatus,
  TokenWithStatus,
  VocabItem,
} from "./types";

// base_form 우선, 없으면 normalized_form, 그다음 surface로 묶는다.
export function getTokenGroupKey(token: {
  base_form: string;
  normalized_form: string;
  surface: string;
}): string {
  return token.base_form || token.normalized_form || token.surface || "";
}

export type MessageTone = "info" | "success" | "error";

// Reading-tab status/result messages are all authored in page.tsx as plain
// strings (no separate tone field) -- this keeps a single visual language
// (success/error/info) without threading a second piece of state through
// every setReadingMessage call site.
const ERROR_MESSAGE_PATTERN = /(실패|오류|찾지 못)/;
const SUCCESS_MESSAGE_PATTERN = /(저장했습니다|건너뛰었습니다|복원했습니다|초기화했습니다)/;

export function classifyMessageTone(message: string): MessageTone {
  if (!message) {
    return "info";
  }
  if (ERROR_MESSAGE_PATTERN.test(message)) {
    return "error";
  }
  if (SUCCESS_MESSAGE_PATTERN.test(message)) {
    return "success";
  }
  return "info";
}

function findMatchingVocabItem(
  token: { base_form: string; normalized_form: string; surface: string },
  vocabItems: VocabItem[],
  deckId: string,
): VocabItem | undefined {
  const key = getTokenGroupKey(token);
  if (!key) {
    return undefined;
  }
  const deckIdNumber = deckId ? Number(deckId) : null;
  return vocabItems.find((item) => {
    if (deckIdNumber !== null && item.deck_id !== deckIdNumber) {
      return false;
    }
    return getTokenGroupKey(item) === key;
  });
}

// 현재 세션에서 직접 분류한 상태가 최우선이고, 없으면 현재 선택된 덱에
// 저장된 단어 상태를 사용한다. 둘 다 없으면 미분류.
export function getTokenStatus(
  token: TokenWithStatus,
  vocabItems: VocabItem[],
  deckId: string,
): TokenStatus {
  if (token.status !== "unclassified") {
    return token.status;
  }
  const match = findMatchingVocabItem(token, vocabItems, deckId);
  return match ? match.status : "unclassified";
}

// getTokenStatus alone can't tell a never-saved word apart from one that's
// saved with status "unclassified" (both read as "unclassified") -- this
// checks deck membership directly so callers can tell "new" from "saved".
export function isTokenSavedInDeck(
  token: { base_form: string; normalized_form: string; surface: string },
  vocabItems: VocabItem[],
  deckId: string,
): boolean {
  return Boolean(findMatchingVocabItem(token, vocabItems, deckId));
}

export type ReadingSaveSummary = {
  newCount: number;
  unknownCount: number;
  uncertainCount: number;
  knownCount: number;
  unclassifiedCount: number;
  saveableCount: number;
};

// "이 텍스트 학습 요약" panel counts: known words are set aside, everything
// else (never-saved "new" words plus already-saved unknown/uncertain/
// unclassified ones) is a save/study candidate.
export function computeReadingSaveSummary(
  tokens: TokenWithStatus[],
  vocabItems: VocabItem[],
  deckId: string,
): ReadingSaveSummary {
  let newCount = 0;
  let unknownCount = 0;
  let uncertainCount = 0;
  let knownCount = 0;
  let unclassifiedCount = 0;

  for (const token of tokens) {
    const status = getTokenStatus(token, vocabItems, deckId);
    if (status === "unclassified" && !isTokenSavedInDeck(token, vocabItems, deckId)) {
      newCount += 1;
      continue;
    }
    if (status === "known") {
      knownCount += 1;
    } else if (status === "uncertain") {
      uncertainCount += 1;
    } else if (status === "unknown") {
      unknownCount += 1;
    } else {
      unclassifiedCount += 1;
    }
  }

  return {
    newCount,
    unknownCount,
    uncertainCount,
    knownCount,
    unclassifiedCount,
    saveableCount: newCount + unknownCount + uncertainCount + unclassifiedCount,
  };
}

export type ReadingSaveMode = "unknown_only" | "unknown_uncertain" | "all_unclassified";

export type ReadingSaveTarget = {
  index: number;
  token: TokenWithStatus;
  targetStatus: TokenStatus;
  // True when the word is already saved with this exact status AND already
  // has a context sentence -- nothing would actually change, so callers can
  // skip the API call entirely and report it as "already saved" instead of
  // "saved" or "failed".
  alreadySaved: boolean;
  existingItemId: number | null;
};

// Resolves which tokens each bulk-save button should act on, and what
// status to save them as. A never-saved ("new") word defaults to "unknown"
// since there's no earlier classification to preserve; an already-saved
// word keeps whatever status it already has. "known" words are never
// touched by these buttons.
export function resolveReadingSaveTargets(
  tokens: TokenWithStatus[],
  vocabItems: VocabItem[],
  deckId: string,
  mode: ReadingSaveMode,
): ReadingSaveTarget[] {
  const targets: ReadingSaveTarget[] = [];

  tokens.forEach((token, index) => {
    const existingItem = findMatchingVocabItem(token, vocabItems, deckId);
    const status = getTokenStatus(token, vocabItems, deckId);
    const bucket: TokenStatus | "new" =
      status === "unclassified" && !existingItem ? "new" : status;

    if (bucket === "known") {
      return;
    }

    const included =
      mode === "unknown_only"
        ? bucket === "new" || bucket === "unknown"
        : mode === "unknown_uncertain"
          ? bucket === "new" || bucket === "unknown" || bucket === "uncertain"
          : true;

    if (!included) {
      return;
    }

    const targetStatus = bucket === "new" ? "unknown" : bucket;
    const alreadySaved = Boolean(
      existingItem &&
        existingItem.status === targetStatus &&
        existingItem.example_sentence,
    );

    targets.push({
      index,
      token,
      targetStatus,
      alreadySaved,
      existingItemId: existingItem ? existingItem.id : null,
    });
  });

  return targets;
}

export function computeCoverageStats(
  tokens: TokenWithStatus[],
  vocabItems: VocabItem[],
  deckId: string,
  ignoredCount: number,
): CoverageStats {
  let uniqueKnown = 0;
  let uniqueUncertain = 0;
  let uniqueUnknown = 0;
  let uniqueUnclassified = 0;
  let occurrenceKnown = 0;
  let occurrenceUncertain = 0;
  let occurrenceUnknown = 0;
  let occurrenceUnclassified = 0;
  let occurrenceTotal = 0;

  for (const token of tokens) {
    const status = getTokenStatus(token, vocabItems, deckId);
    const occurrenceCount = token.occurrence_count || 1;
    occurrenceTotal += occurrenceCount;

    if (status === "known") {
      uniqueKnown += 1;
      occurrenceKnown += occurrenceCount;
    } else if (status === "uncertain") {
      uniqueUncertain += 1;
      occurrenceUncertain += occurrenceCount;
    } else if (status === "unknown") {
      uniqueUnknown += 1;
      occurrenceUnknown += occurrenceCount;
    } else {
      uniqueUnclassified += 1;
      occurrenceUnclassified += occurrenceCount;
    }
  }

  const uniqueTotal = tokens.length;

  return {
    uniqueTotal,
    uniqueKnown,
    uniqueUncertain,
    uniqueUnknown,
    uniqueUnclassified,
    occurrenceTotal,
    occurrenceKnown,
    occurrenceUncertain,
    occurrenceUnknown,
    occurrenceUnclassified,
    ignoredCount,
    coveragePercent:
      uniqueTotal > 0 ? Math.round((uniqueKnown / uniqueTotal) * 100) : 0,
    occurrenceCoveragePercent:
      occurrenceTotal > 0
        ? Math.round((occurrenceKnown / occurrenceTotal) * 100)
        : 0,
  };
}

const STATUS_PRIORITY: Record<TokenStatus, number> = {
  unknown: 0,
  uncertain: 1,
  unclassified: 2,
  known: 3,
};

const CONTENT_POS_KEYWORDS = ["명사", "동사", "형용사", "형용동사"];

function isContentWord(partOfSpeech: string): boolean {
  return CONTENT_POS_KEYWORDS.some((keyword) => partOfSpeech.includes(keyword));
}

// unknown > uncertain > unclassified 순으로 우선하고, 같은 상태 안에서는
// 등장 횟수가 많고, 뜻이 있고, 명사/동사/형용사인 단어를 우선한다.
// known 단어는 이미 아는 단어이므로 추천 목록에서 제외한다.
export function buildPriorityStudyList(
  tokens: TokenWithStatus[],
  vocabItems: VocabItem[],
  deckId: string,
  limit = 10,
): PriorityVocabEntry[] {
  const candidates = tokens
    .map((token, tokenIndex) => ({
      token,
      tokenIndex,
      status: getTokenStatus(token, vocabItems, deckId),
    }))
    .filter((entry) => entry.status !== "known");

  candidates.sort((a, b) => {
    const statusDiff = STATUS_PRIORITY[a.status] - STATUS_PRIORITY[b.status];
    if (statusDiff !== 0) {
      return statusDiff;
    }
    const occurrenceDiff =
      (b.token.occurrence_count || 1) - (a.token.occurrence_count || 1);
    if (occurrenceDiff !== 0) {
      return occurrenceDiff;
    }
    const meaningDiff =
      (b.token.meaning_ko ? 1 : 0) - (a.token.meaning_ko ? 1 : 0);
    if (meaningDiff !== 0) {
      return meaningDiff;
    }
    const posDiff =
      (isContentWord(b.token.part_of_speech) ? 1 : 0) -
      (isContentWord(a.token.part_of_speech) ? 1 : 0);
    if (posDiff !== 0) {
      return posDiff;
    }
    return 0;
  });

  return candidates.slice(0, limit).map(({ token, tokenIndex, status }) => ({
    ...token,
    status,
    tokenIndex,
  }));
}

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

function findMatchingVocabItem(
  token: TokenWithStatus,
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

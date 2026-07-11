import type { Token } from "./types";
import { getTokenGroupKey } from "./coverageUtils";

export type ChunkAnalyzeProgress = {
  current: number;
  total: number;
};

// Shape returned by one /analyze call -- matches the AnalyzeResponse JSON
// body without importing page.tsx's local type (keeps this module
// independent/testable).
export type ChunkAnalyzeCallResult = {
  tokens: Token[];
  ignored_token_count: number;
};

// Merges a newly-analyzed chunk's tokens into the running result, applying
// the same base_form/normalized_form/surface dedup the backend already
// performs within a single /analyze call. Without this, a word repeated
// across a chunk boundary (very common in any text long enough to be
// chunked) would show up as two separate entries instead of one, breaking
// occurrence counts, save-summary counts, and previous/next navigation.
// First-occurrence fields win (surface, meaning, example_sentence, ...);
// only occurrence_count accumulates, and an empty example_sentence from the
// first occurrence is backfilled from a later one.
export function mergeAnalyzedTokens(
  accumulated: Token[],
  chunkTokens: Token[],
): Token[] {
  const merged = [...accumulated];
  const indexByKey = new Map<string, number>();
  merged.forEach((token, index) => {
    const key = getTokenGroupKey(token);
    if (key) {
      indexByKey.set(key, index);
    }
  });

  for (const token of chunkTokens) {
    const key = getTokenGroupKey(token);
    const existingIndex = key ? indexByKey.get(key) : undefined;
    if (existingIndex === undefined) {
      if (key) {
        indexByKey.set(key, merged.length);
      }
      merged.push(token);
      continue;
    }
    const existing = merged[existingIndex];
    merged[existingIndex] = {
      ...existing,
      occurrence_count:
        (existing.occurrence_count || 1) + (token.occurrence_count || 1),
      example_sentence: existing.example_sentence || token.example_sentence,
    };
  }

  return merged;
}

export type ChunkAnalyzeOutcome = {
  tokens: Token[];
  ignoredTokenCount: number;
  failedChunkCount: number;
  totalChunkCount: number;
  cancelled: boolean;
};

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

// Sequentially analyzes each chunk -- never Promise.all -- so a long read
// doesn't slam the backend with dozens of concurrent requests at once.
// Results are merged in original-text order as they arrive. A single
// chunk's failure doesn't abort the rest: the loop keeps going so the other
// chunks' words still show up, and the caller is told how many chunks
// failed so it can surface that without discarding everything.
export async function analyzeLongTextInChunks(
  chunks: string[],
  analyzeChunk: (
    chunkText: string,
    signal: AbortSignal,
  ) => Promise<ChunkAnalyzeCallResult>,
  options: {
    signal: AbortSignal;
    onProgress?: (progress: ChunkAnalyzeProgress) => void;
  },
): Promise<ChunkAnalyzeOutcome> {
  let tokens: Token[] = [];
  let ignoredTokenCount = 0;
  let failedChunkCount = 0;

  for (let index = 0; index < chunks.length; index += 1) {
    if (options.signal.aborted) {
      return {
        tokens,
        ignoredTokenCount,
        failedChunkCount,
        totalChunkCount: chunks.length,
        cancelled: true,
      };
    }

    options.onProgress?.({ current: index + 1, total: chunks.length });

    try {
      const result = await analyzeChunk(chunks[index], options.signal);
      tokens = mergeAnalyzedTokens(tokens, result.tokens);
      ignoredTokenCount += result.ignored_token_count || 0;
    } catch (error) {
      if (options.signal.aborted || isAbortError(error)) {
        return {
          tokens,
          ignoredTokenCount,
          failedChunkCount,
          totalChunkCount: chunks.length,
          cancelled: true,
        };
      }
      failedChunkCount += 1;
    }
  }

  return {
    tokens,
    ignoredTokenCount,
    failedChunkCount,
    totalChunkCount: chunks.length,
    cancelled: false,
  };
}

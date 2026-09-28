import type { TokenWithStatus } from "./types";

const SENTENCE_ENDING_CHARS = new Set(["。", "！", "？", "!", "?"]);

// Every token that reaches the frontend is already clickable in reader mode
// (particles/aux-verbs/punctuation/whitespace are filtered out server-side,
// see backend EXCLUDED_POS) -- but symbol-class tokens ("기호") still slip
// through as low-value nav targets (TokenChip renders them muted for the
// same reason). Previous/next word navigation reuses that existing
// clickable set, only narrowing it to skip symbols, so it stays in sync
// with whatever is actually clickable instead of inventing a new filter.
const NON_NAVIGABLE_POS = new Set(["기호"]);

export function isNavigableToken(
  token: Pick<TokenWithStatus, "surface" | "base_form" | "part_of_speech">,
): boolean {
  const label = (token.surface || token.base_form || "").trim();
  if (!label) {
    return false;
  }
  return !NON_NAVIGABLE_POS.has(token.part_of_speech);
}

// tokens[] is already ordered by first-occurrence position in the original
// text (the backend dedupes by base_form at tokenize time, appending each
// token the first time its base_form is seen), so previous/next navigation
// can walk this array directly without re-deriving order from the rendered
// layout.
export function getNavigableTokenIndexes(tokens: TokenWithStatus[]): number[] {
  const indexes: number[] = [];
  tokens.forEach((token, index) => {
    if (isNavigableToken(token)) {
      indexes.push(index);
    }
  });
  return indexes;
}

export type ReaderInlineSegment =
  | { type: "text"; key: string; content: string }
  | { type: "token"; key: string; tokenIndex: number };

export type ReaderLayout = {
  lines: ReaderInlineSegment[][];
  // Parallel to lines: true when that line opens a new paragraph in the
  // source (a blank line, or a line break right after a sentence end).
  // Only set in sentence-row mode, where those breaks used to render as
  // one or two empty full-height rows; the reader draws a short spacer
  // instead. Phone paper keeps its literal empty lines and never sets it.
  lineStartsParagraph: boolean[];
  // Tokens whose surface never matched anywhere in originalText (should be
  // rare -- e.g. a compound/noun-phrase candidate whose span got consumed
  // by an overlapping match first). Kept so the UI can still surface them
  // instead of silently dropping a study candidate.
  unmatchedTokenIndexes: number[];
};

// Reconstructs the pasted text close to verbatim: known token surfaces
// become clickable spans in place, everything else (particles, punctuation,
// spaces, line breaks) stays as plain text in its original order and
// position. This is a left-to-right greedy scan, not a global replace --
// replacing by string search+replace would let a repeated word incorrectly
// re-match earlier positions; scanning forward from a moving cursor instead
// guarantees each occurrence in the source text binds once, in order.
export function buildReaderLayout(
  originalText: string,
  tokens: TokenWithStatus[],
  splitSentences = true,
): ReaderLayout {
  const lines: ReaderInlineSegment[][] = [[]];
  const lineStartsParagraph: boolean[] = [false];
  const usedTokenIndexes = new Set<number>();
  let keyCounter = 0;
  // Sentence-row mode only: line breaks seen while the current row is
  // still empty. The row itself already provides one break, so any extra
  // one means the source started a new paragraph here.
  let pendingBreaks = 0;

  const currentLine = () => lines[lines.length - 1];

  function startLine() {
    lines.push([]);
    lineStartsParagraph.push(false);
    pendingBreaks = 0;
  }

  // Called before anything is placed on the current row.
  function beginContent() {
    if (splitSentences && currentLine().length === 0) {
      if (pendingBreaks > 0 && lines.length > 1) {
        lineStartsParagraph[lines.length - 1] = true;
      }
      pendingBreaks = 0;
    }
  }

  function pushChar(char: string) {
    if (char === "\n") {
      if (splitSentences && currentLine().length === 0) {
        pendingBreaks += 1;
      } else {
        startLine();
      }
      return;
    }
    beginContent();
    const line = currentLine();
    const last = line[line.length - 1];
    if (last && last.type === "text") {
      last.content += char;
    } else {
      line.push({ type: "text", key: `t-${keyCounter++}`, content: char });
    }
    // Desktop/tablet keep the legacy sentence rows; phone paper uses only
    // the line breaks the user actually entered.
    if (splitSentences && SENTENCE_ENDING_CHARS.has(char)) {
      startLine();
    }
  }

  let cursor = 0;
  while (cursor < originalText.length) {
    let matchedTokenIndex = -1;
    let matchedLength = 0;

    for (let index = 0; index < tokens.length; index += 1) {
      const surface = tokens[index].surface;
      if (!surface || surface.length <= matchedLength) {
        continue;
      }
      if (originalText.startsWith(surface, cursor)) {
        matchedTokenIndex = index;
        matchedLength = surface.length;
      }
    }

    if (matchedTokenIndex !== -1) {
      beginContent();
      currentLine().push({
        type: "token",
        key: `k-${keyCounter++}`,
        tokenIndex: matchedTokenIndex,
      });
      usedTokenIndexes.add(matchedTokenIndex);
      cursor += matchedLength;
    } else {
      pushChar(originalText[cursor]);
      cursor += 1;
    }
  }

  while (lines.length > 1 && lines[lines.length - 1].length === 0) {
    lines.pop();
    lineStartsParagraph.pop();
  }

  const unmatchedTokenIndexes: number[] = [];
  tokens.forEach((_, index) => {
    if (!usedTokenIndexes.has(index)) {
      unmatchedTokenIndexes.push(index);
    }
  });

  return { lines, lineStartsParagraph, unmatchedTokenIndexes };
}

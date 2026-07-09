import type { TokenWithStatus } from "./types";

const SENTENCE_ENDING_CHARS = new Set(["。", "！", "？", "!", "?"]);

export type ReaderInlineSegment =
  | { type: "text"; key: string; content: string }
  | { type: "token"; key: string; tokenIndex: number };

export type ReaderLayout = {
  lines: ReaderInlineSegment[][];
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
): ReaderLayout {
  const lines: ReaderInlineSegment[][] = [[]];
  const usedTokenIndexes = new Set<number>();
  let keyCounter = 0;

  const currentLine = () => lines[lines.length - 1];

  function pushChar(char: string) {
    if (char === "\n") {
      lines.push([]);
      return;
    }
    const line = currentLine();
    const last = line[line.length - 1];
    if (last && last.type === "text") {
      last.content += char;
    } else {
      line.push({ type: "text", key: `t-${keyCounter++}`, content: char });
    }
    // Break onto a new line right after sentence-ending punctuation so a
    // wall of pasted text reads one sentence per line, the way the input
    // would if the user had typed line breaks themselves.
    if (SENTENCE_ENDING_CHARS.has(char)) {
      lines.push([]);
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
  }

  const unmatchedTokenIndexes: number[] = [];
  tokens.forEach((_, index) => {
    if (!usedTokenIndexes.has(index)) {
      unmatchedTokenIndexes.push(index);
    }
  });

  return { lines, unmatchedTokenIndexes };
}

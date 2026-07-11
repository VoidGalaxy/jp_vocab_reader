// Long original texts are analyzed by the backend in bounded chunks so a
// single /analyze request never grows unbounded, while the reading tab still
// shows one continuous document. Chunk boundaries are chosen so text is
// never silently dropped or altered -- chunks are a pure left-to-right
// partition of the original string, so concatenating them back together
// always reproduces the exact original text (whitespace, particles, and
// punctuation included).
export const ANALYZE_CHUNK_SIZE = 4000;

const PARAGRAPH_BREAK = "\n";
const SENTENCE_ENDING_CHARS = new Set(["。", "！", "？", "!", "?"]);

// Searches backward from hardEnd (exclusive) for the best place to end a
// chunk: a paragraph break first, then a sentence ending, so chunks rarely
// cut mid-sentence. Only considers breakpoints in the back portion of the
// window (index >= minBreak) so a stray early line break doesn't produce a
// tiny chunk. Falls back to hardEnd (a hard cut) when nothing suitable is
// found nearby -- e.g. one very long sentence with no punctuation.
function findBreakPoint(text: string, start: number, hardEnd: number): number {
  const minBreak = start + Math.floor((hardEnd - start) * 0.4);

  for (let index = hardEnd - 1; index >= minBreak; index -= 1) {
    if (text[index] === PARAGRAPH_BREAK) {
      return index + 1;
    }
  }
  for (let index = hardEnd - 1; index >= minBreak; index -= 1) {
    if (SENTENCE_ENDING_CHARS.has(text[index])) {
      return index + 1;
    }
  }
  return hardEnd;
}

// Splits `text` into ordered chunks no longer than `maxChunkSize`,
// preferring paragraph boundaries, then sentence endings, and only falling
// back to a hard cut when neither exists nearby. `chunks.join("")` always
// equals `text` -- this only decides where to cut, never what survives.
export function splitTextIntoChunks(
  text: string,
  maxChunkSize: number = ANALYZE_CHUNK_SIZE,
): string[] {
  if (text.length === 0) {
    return [];
  }
  if (text.length <= maxChunkSize) {
    return [text];
  }

  const chunks: string[] = [];
  let start = 0;
  while (start < text.length) {
    const hardEnd = Math.min(start + maxChunkSize, text.length);
    const end = hardEnd < text.length ? findBreakPoint(text, start, hardEnd) : hardEnd;
    chunks.push(text.slice(start, end));
    start = end;
  }
  return chunks;
}

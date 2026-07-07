"use client";

type HighlightedExampleProps = {
  sentence: string;
  surface?: string;
  baseForm?: string;
  normalizedForm?: string;
};

// Pure string-slice + React node composition -- no HTML parsing, so this is
// safe against injection without needing dangerouslySetInnerHTML.
export function HighlightedExample({
  sentence,
  surface,
  baseForm,
  normalizedForm,
}: HighlightedExampleProps) {
  if (!sentence) {
    return <>-</>;
  }

  const candidates = [surface, baseForm, normalizedForm].filter(
    (candidate): candidate is string => Boolean(candidate && candidate.trim()),
  );

  for (const candidate of candidates) {
    const matchIndex = sentence.indexOf(candidate);
    if (matchIndex !== -1) {
      const before = sentence.slice(0, matchIndex);
      const match = sentence.slice(matchIndex, matchIndex + candidate.length);
      const after = sentence.slice(matchIndex + candidate.length);
      return (
        <>
          {before}
          <mark className="example-highlight">{match}</mark>
          {after}
        </>
      );
    }
  }

  return <>{sentence}</>;
}

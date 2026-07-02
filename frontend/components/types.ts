export type TokenStatus = "unclassified" | "known" | "unknown";

export type Token = {
  surface: string;
  base_form: string;
  reading: string;
  part_of_speech: string;
  normalized_form: string;
  meaning_ko: string;
  example_sentence: string;
};

export type TokenWithStatus = Token & {
  status: TokenStatus;
};

export type VocabItem = TokenWithStatus & {
  id: number;
  correct_count: number;
  wrong_count: number;
  last_reviewed_at: string | null;
  review_level: number;
  next_review_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ReviewResult = "correct" | "wrong";

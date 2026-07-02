export type TokenStatus = "unclassified" | "known" | "uncertain" | "unknown";
export type QualityTag =
  | "normal"
  | "custom_term"
  | "compound_verb"
  | "noun_phrase_candidate";

export type Token = {
  surface: string;
  base_form: string;
  reading: string;
  part_of_speech: string;
  normalized_form: string;
  meaning_ko: string;
  dictionary_gloss: string;
  quality_tag: QualityTag;
  example_sentence: string;
  is_custom_term: boolean;
};

export type TokenWithStatus = Token & {
  status: TokenStatus;
  isClassified?: boolean;
};

export type VocabItem = TokenWithStatus & {
  id: number;
  deck_id: number;
  deck_name: string;
  context_explanation_ko: string;
  correct_count: number;
  wrong_count: number;
  last_reviewed_at: string | null;
  review_level: number;
  next_review_at: string | null;
  created_at: string;
  updated_at: string;
};

export type VocabFormData = {
  surface: string;
  base_form: string;
  reading: string;
  part_of_speech: string;
  meaning_ko: string;
  dictionary_gloss: string;
  quality_tag: QualityTag;
  example_sentence: string;
  context_explanation_ko: string;
  status: TokenStatus;
  deck_id: string;
};

export type ReviewResult = "correct" | "wrong";

export type DeckStats = {
  deck_id: number;
  deck_name: string;
  total_count: number;
  known_count: number;
  uncertain_count: number;
  unknown_count: number;
  unclassified_count: number;
  due_today_count: number;
  learned_rate: number;
};

export type ReviewLevelCount = {
  review_level: number;
  count: number;
};

export type StudyStats = {
  scope: "all" | "deck";
  deck_id: number | null;
  deck_name: string | null;
  total_count: number;
  known_count: number;
  uncertain_count: number;
  unknown_count: number;
  unclassified_count: number;
  due_today_count: number;
  total_correct_count: number;
  total_wrong_count: number;
  average_review_level: number;
  learned_rate: number;
  deck_stats: DeckStats[];
  review_level_counts: ReviewLevelCount[];
};

export type VocabSort =
  | "created_desc"
  | "created_asc"
  | "wrong_desc"
  | "correct_desc"
  | "review_level_asc"
  | "next_review_asc";

export type Deck = {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
};

export type CustomTerm = {
  id: number;
  term: string;
  reading: string;
  part_of_speech: string;
  meaning_ko: string;
  description: string;
  deck_id: number | null;
  deck_name: string | null;
  created_at: string;
  updated_at: string;
};

export type CustomTermFormData = {
  term: string;
  reading: string;
  part_of_speech: string;
  meaning_ko: string;
  description: string;
  deck_id: string;
};

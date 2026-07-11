export type TokenStatus = "unclassified" | "known" | "uncertain" | "unknown";
export type QualityTag =
  | "normal"
  | "custom_term"
  | "compound_verb"
  | "noun_phrase_candidate"
  | "known_phrase";

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
  occurrence_count: number;
  jlpt_level?: string | null;
};

export type TokenWithStatus = Token & {
  status: TokenStatus;
  isClassified?: boolean;
  savedExampleSentence?: string | null;
  // Present when this token matches a word already saved in the current
  // deck -- lets the Reading tab show/edit the user's own saved meaning
  // instead of (or alongside) the fresh dictionary lookup from /analyze.
  savedMeaningKo?: string | null;
  savedVocabItemId?: number | null;
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

export type MeaningFeedbackSource = "reading" | "vocab" | "review";

export type MeaningFeedbackTarget = {
  vocabularyId: number | null;
  surface: string;
  baseForm: string;
  reading: string;
  currentMeaningKo: string;
  source: MeaningFeedbackSource;
};

// General in-app feedback (bugs/UX/feature requests/etc) -- kept separate
// from MeaningFeedbackTarget above, which is only for a specific word's
// meaning and posts to a different endpoint/table.
export type AppFeedbackCategory = "bug" | "ux" | "feature" | "meaning" | "other";

export type ReviewResult = "again" | "hard" | "good" | "easy";
export type StudyMode =
  | "today"
  | "uncertain"
  | "unknown"
  | "all"
  | "new"
  | "recent";

export type SessionReviewCounts = Record<ReviewResult, number>;

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
  total_vocab_count: number;
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
  new_count: number;
  hard_count: number;
  reviewed_today_count: number;
  today_again_count: number;
  today_hard_count: number;
  today_good_count: number;
  today_easy_count: number;
  streak_days: number;
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

export type SharedDeckSummary = {
  id: number;
  title: string;
  description: string | null;
  owner_display_name: string | null;
  vocab_count: number;
  custom_term_count: number;
  import_count: number;
  created_at: string;
  is_owner: boolean;
  imported_at: string | null;
};

export type SharedDeckItem = {
  id: number;
  surface: string | null;
  base_form: string | null;
  reading: string | null;
  part_of_speech: string | null;
  normalized_form: string | null;
  meaning_ko: string | null;
  dictionary_gloss: string | null;
  context_explanation_ko: string | null;
  example_sentence: string | null;
  quality_tag: string | null;
  created_at: string;
};

export type SharedDeckTerm = {
  id: number;
  term: string;
  reading: string | null;
  part_of_speech: string | null;
  meaning_ko: string | null;
  description: string | null;
  created_at: string;
};

export type SharedDeckDetail = SharedDeckSummary & {
  updated_at: string;
  items: SharedDeckItem[];
  custom_terms: SharedDeckTerm[];
};

export type CoverageStats = {
  uniqueTotal: number;
  uniqueKnown: number;
  uniqueUncertain: number;
  uniqueUnknown: number;
  uniqueUnclassified: number;
  occurrenceTotal: number;
  occurrenceKnown: number;
  occurrenceUncertain: number;
  occurrenceUnknown: number;
  occurrenceUnclassified: number;
  ignoredCount: number;
  coveragePercent: number;
  occurrenceCoveragePercent: number;
};

export type PriorityVocabEntry = TokenWithStatus & {
  tokenIndex: number;
};

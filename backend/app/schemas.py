from pydantic import BaseModel, Field


VALID_STATUSES = {"unknown", "uncertain", "known", "unclassified"}
VALID_REVIEW_RESULTS = {"correct", "wrong"}
VALID_REVIEW_RATINGS = {"again", "hard", "good", "easy"}
# Legacy correct/wrong clients keep working by mapping onto the new 4-way
# rating scale: a plain "got it right" becomes "good", a miss becomes "again".
RESULT_TO_RATING = {"correct": "good", "wrong": "again"}


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str
    auth_provider: str


class AuthRegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# Per-request safety ceiling for /analyze. The frontend reading tab never
# hits this in normal use -- it splits long original text into chunks well
# under this size before sending each request (see
# frontend/components/textChunking.ts). This exists to bound abnormal/direct
# API calls, not to cap how long a user's original text can be.
ANALYZE_TEXT_MAX_LENGTH = 8000


class AnalyzeRequest(BaseModel):
    text: str = Field(...)
    deck_id: int | None = None
    include_known: bool = False


class TokenResponse(BaseModel):
    surface: str
    base_form: str
    reading: str
    part_of_speech: str
    normalized_form: str
    meaning_ko: str
    dictionary_gloss: str = ""
    quality_tag: str = "normal"
    example_sentence: str
    is_custom_term: bool = False
    occurrence_count: int = 1
    jlpt_level: str | None = None


class AnalyzeResponse(BaseModel):
    tokens: list[TokenResponse]
    ignored_token_count: int = 0


class VocabItemCreate(BaseModel):
    surface: str = ""
    base_form: str = ""
    reading: str = ""
    part_of_speech: str = ""
    normalized_form: str = ""
    meaning_ko: str = ""
    dictionary_gloss: str = ""
    quality_tag: str = "normal"
    context_explanation_ko: str = ""
    example_sentence: str = ""
    status: str = "unknown"
    deck_id: int | None = None


class VocabItemUpdate(BaseModel):
    surface: str | None = None
    base_form: str | None = None
    reading: str | None = None
    part_of_speech: str | None = None
    normalized_form: str | None = None
    meaning_ko: str | None = None
    dictionary_gloss: str | None = None
    quality_tag: str | None = None
    context_explanation_ko: str | None = None
    example_sentence: str | None = None
    status: str | None = None
    deck_id: int | None = None


class VocabItemResponse(BaseModel):
    id: int
    deck_id: int
    deck_name: str
    surface: str
    base_form: str
    reading: str
    part_of_speech: str
    normalized_form: str
    meaning_ko: str
    dictionary_gloss: str
    quality_tag: str
    example_sentence: str
    context_explanation_ko: str
    status: str
    correct_count: int
    wrong_count: int
    last_reviewed_at: str | None
    review_level: int
    next_review_at: str | None
    created_at: str
    updated_at: str


class VocabItemsResponse(BaseModel):
    items: list[VocabItemResponse]


class StudyItemsResponse(BaseModel):
    items: list[VocabItemResponse]


class StudyReviewRequest(BaseModel):
    result: str | None = None
    rating: str | None = None
    response_time_ms: int | None = None


class DeckStatsResponse(BaseModel):
    deck_id: int
    deck_name: str
    total_count: int
    known_count: int
    uncertain_count: int
    unknown_count: int
    unclassified_count: int
    due_today_count: int
    learned_rate: float


class ReviewLevelCountResponse(BaseModel):
    review_level: int
    count: int


class StatsResponse(BaseModel):
    scope: str
    deck_id: int | None
    deck_name: str | None
    total_count: int
    total_vocab_count: int = 0
    known_count: int
    uncertain_count: int
    unknown_count: int
    unclassified_count: int
    due_today_count: int
    total_correct_count: int
    total_wrong_count: int
    average_review_level: float
    learned_rate: float
    deck_stats: list[DeckStatsResponse] = []
    review_level_counts: list[ReviewLevelCountResponse] = []
    new_count: int = 0
    hard_count: int = 0
    reviewed_today_count: int = 0
    today_again_count: int = 0
    today_hard_count: int = 0
    today_good_count: int = 0
    today_easy_count: int = 0
    streak_days: int = 0


class DeckCreate(BaseModel):
    name: str
    description: str = ""


class DeckUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class DeckResponse(BaseModel):
    id: int
    name: str
    description: str
    created_at: str
    updated_at: str


class DecksResponse(BaseModel):
    items: list[DeckResponse]


class DeckDeleteResponse(BaseModel):
    deleted_deck_id: int
    deleted_vocab_count: int
    message: str


class DeckPublishRequest(BaseModel):
    title: str = ""
    description: str = ""


class DeckPublishResponse(BaseModel):
    shared_deck_id: int
    title: str
    vocab_count: int
    custom_term_count: int
    message: str


class SharedDeckSummaryResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    owner_display_name: str | None = None
    vocab_count: int
    custom_term_count: int
    import_count: int
    created_at: str
    is_owner: bool = False
    imported_at: str | None = None


class SharedDeckItemResponse(BaseModel):
    id: int
    surface: str | None = None
    base_form: str | None = None
    reading: str | None = None
    part_of_speech: str | None = None
    normalized_form: str | None = None
    meaning_ko: str | None = None
    dictionary_gloss: str | None = None
    context_explanation_ko: str | None = None
    example_sentence: str | None = None
    quality_tag: str | None = None
    created_at: str
    # Additive: only populated for lexeme-mode shared decks (see
    # docs/architecture/shared-lexeme-progress-storage.md). None/default for
    # legacy shared_deck_items-based decks, which never set these.
    lexeme_id: int | None = None
    jlpt_level: str | None = None
    status: str | None = None
    review_level: int | None = None
    next_review_at: str | None = None
    correct_count: int | None = None
    wrong_count: int | None = None


class SharedDeckTermResponse(BaseModel):
    id: int
    term: str
    reading: str | None = None
    part_of_speech: str | None = None
    meaning_ko: str | None = None
    description: str | None = None
    created_at: str


class SharedDeckDetailResponse(SharedDeckSummaryResponse):
    updated_at: str
    items: list[SharedDeckItemResponse] = []
    custom_terms: list[SharedDeckTermResponse] = []


class SharedDeckDeleteResponse(BaseModel):
    ok: bool = True
    shared_deck_id: int
    title: str
    message: str


class SharedDeckImportResponse(BaseModel):
    deck_id: int
    deck_name: str
    imported_vocab_count: int
    imported_custom_term_count: int
    message: str
    # Additive (see docs/architecture/shared-lexeme-progress-storage.md).
    # "copied" = legacy path (unchanged behavior, personal deck + vocab_items
    # copy). "subscribed" = new lexeme-mode path: no personal deck, no
    # vocab_items copy -- deck_id/deck_name/imported_vocab_count above are
    # still populated with sensible stand-in values so older client code
    # that only reads those fields doesn't break.
    success: bool = True
    mode: str = "copied"
    subscribed: bool = False
    shared_deck_id: int | None = None
    word_count: int | None = None


# --- Lexeme-mode shared deck word progress (additive; see
# docs/architecture/shared-lexeme-progress-storage.md) -----------------------


class LexemeProgressUpdateRequest(BaseModel):
    status: str


class LexemeReviewRequest(BaseModel):
    rating: str


class LexemeWordProgressResponse(BaseModel):
    lexeme_id: int
    status: str
    review_level: int
    next_review_at: str | None = None
    correct_count: int
    wrong_count: int
    last_reviewed_at: str | None = None


class DeckPackageApp(BaseModel):
    name: str = "JP Vocab Reader"
    format: str = "deck_package"


class DeckPackageDeck(BaseModel):
    name: str
    description: str = ""


class DeckPackageVocabItem(BaseModel):
    surface: str = ""
    base_form: str = ""
    reading: str = ""
    part_of_speech: str = ""
    normalized_form: str = ""
    meaning_ko: str = ""
    dictionary_gloss: str = ""
    context_explanation_ko: str = ""
    example_sentence: str = ""
    quality_tag: str = "normal"


class DeckPackageCustomTerm(BaseModel):
    term: str
    reading: str = ""
    part_of_speech: str = "명사"
    meaning_ko: str = ""
    description: str = ""


class DeckPackage(BaseModel):
    package_type: str
    package_version: int
    exported_at: str | None = None
    app: DeckPackageApp = Field(default_factory=DeckPackageApp)
    deck: DeckPackageDeck
    vocab_items: list[DeckPackageVocabItem] = Field(default_factory=list)
    custom_terms: list[DeckPackageCustomTerm] = Field(default_factory=list)


class DeckPackageImportResponse(BaseModel):
    deck_id: int
    deck_name: str
    imported_vocab_count: int
    skipped_vocab_count: int
    imported_custom_term_count: int
    skipped_custom_term_count: int
    message: str


class CustomTermCreate(BaseModel):
    term: str
    reading: str = ""
    part_of_speech: str = "명사"
    meaning_ko: str = ""
    description: str = ""
    deck_id: int | None = None


class CustomTermUpdate(BaseModel):
    term: str | None = None
    reading: str | None = None
    part_of_speech: str | None = None
    meaning_ko: str | None = None
    description: str | None = None
    deck_id: int | None = None


class CustomTermResponse(BaseModel):
    id: int
    term: str
    reading: str
    part_of_speech: str
    meaning_ko: str
    description: str
    deck_id: int | None
    deck_name: str | None
    created_at: str
    updated_at: str


class CustomTermsResponse(BaseModel):
    items: list[CustomTermResponse]


MAX_FEEDBACK_FIELD_LENGTH = 500
VALID_FEEDBACK_SOURCES = {"reading", "vocab", "review", "shared_deck"}


class MeaningFeedbackRequest(BaseModel):
    # vocabulary_id is only a hint -- the endpoint re-checks it belongs to
    # the requesting user before storing it, same as user_id is always taken
    # from the auth token rather than trusted from the client body.
    vocabulary_id: int | None = None
    surface: str = ""
    base_form: str = ""
    reading: str = ""
    current_meaning_ko: str = ""
    suggested_meaning_ko: str = ""
    reason: str = ""
    source: str = ""


class MeaningFeedbackResponse(BaseModel):
    ok: bool = True
    message: str


# General in-app feedback (bug reports, UX complaints, feature requests --
# anything that isn't a specific word's meaning, which stays on the
# meaning_feedback table/endpoint above). Deliberately small: no free-form
# long text, no original-text/context fields, so beta feedback can never
# become a backdoor for storing the full reading-tab source text.
APP_FEEDBACK_MESSAGE_MIN_LENGTH = 10
APP_FEEDBACK_MESSAGE_MAX_LENGTH = 1000
APP_FEEDBACK_META_MAX_LENGTH = 100
VALID_APP_FEEDBACK_CATEGORIES = {"bug", "ux", "feature", "meaning", "other"}


class AppFeedbackRequest(BaseModel):
    category: str
    message: str
    screen: str = ""
    path: str = ""


class AppFeedbackResponse(BaseModel):
    ok: bool = True
    message: str

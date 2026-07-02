from pydantic import BaseModel, Field


VALID_STATUSES = {"unknown", "uncertain", "known", "unclassified"}
VALID_REVIEW_RESULTS = {"correct", "wrong"}


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


class AnalyzeResponse(BaseModel):
    tokens: list[TokenResponse]


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
    result: str


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

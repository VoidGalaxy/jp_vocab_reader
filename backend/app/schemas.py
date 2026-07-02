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
    example_sentence: str


class AnalyzeResponse(BaseModel):
    tokens: list[TokenResponse]


class VocabItemCreate(BaseModel):
    surface: str = ""
    base_form: str = ""
    reading: str = ""
    part_of_speech: str = ""
    normalized_form: str = ""
    meaning_ko: str = ""
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

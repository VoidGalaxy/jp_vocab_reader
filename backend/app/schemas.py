from pydantic import BaseModel, Field


VALID_STATUSES = {"unknown", "known", "unclassified"}
VALID_REVIEW_RESULTS = {"correct", "wrong"}


class AnalyzeRequest(BaseModel):
    text: str = Field(...)


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
    surface: str
    base_form: str
    reading: str
    part_of_speech: str
    normalized_form: str
    meaning_ko: str = ""
    example_sentence: str = ""
    status: str = "unknown"


class VocabItemUpdate(BaseModel):
    status: str


class VocabItemResponse(BaseModel):
    id: int
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

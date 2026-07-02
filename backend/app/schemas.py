from pydantic import BaseModel, Field


VALID_STATUSES = {"unknown", "known", "unclassified"}


class AnalyzeRequest(BaseModel):
    text: str = Field(...)


class TokenResponse(BaseModel):
    surface: str
    base_form: str
    reading: str
    part_of_speech: str
    normalized_form: str
    meaning_ko: str


class AnalyzeResponse(BaseModel):
    tokens: list[TokenResponse]


class VocabItemCreate(BaseModel):
    surface: str
    base_form: str
    reading: str
    part_of_speech: str
    normalized_form: str
    meaning_ko: str = ""
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
    status: str
    created_at: str
    updated_at: str


class VocabItemsResponse(BaseModel):
    items: list[VocabItemResponse]

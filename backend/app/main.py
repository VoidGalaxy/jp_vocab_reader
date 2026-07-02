import csv
from io import StringIO

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.ai_explainer import (
    AIExplanationError,
    MissingOpenAIKeyError,
    generate_context_explanation,
)
from app.analyzer import analyzer
from app.database import (
    create_deck,
    create_vocab_item,
    delete_deck,
    delete_vocab_item,
    get_deck,
    get_vocab_item,
    init_db,
    list_decks,
    list_study_items,
    list_vocab_items,
    record_study_review,
    update_deck,
    update_context_explanation,
    update_vocab_item_status,
)
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DeckCreate,
    DeckResponse,
    DecksResponse,
    DeckUpdate,
    StudyItemsResponse,
    StudyReviewRequest,
    VALID_REVIEW_RESULTS,
    VALID_STATUSES,
    VocabItemCreate,
    VocabItemResponse,
    VocabItemsResponse,
    VocabItemUpdate,
)


app = FastAPI(title="JP Vocab Reader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text must not be blank")

    return AnalyzeResponse(tokens=analyzer.analyze(request.text))


@app.get("/decks", response_model=DecksResponse)
def get_decks() -> DecksResponse:
    return DecksResponse(items=list_decks())


@app.post("/decks", response_model=DeckResponse)
def post_deck(deck: DeckCreate, response: Response) -> DeckResponse:
    if not deck.name.strip():
        raise HTTPException(status_code=400, detail="deck name must not be blank")

    saved_deck, created = create_deck(deck)
    if not created:
        response.status_code = status.HTTP_200_OK
    return DeckResponse(**saved_deck)


@app.patch("/decks/{deck_id}", response_model=DeckResponse)
def patch_deck(deck_id: int, deck: DeckUpdate) -> DeckResponse:
    if deck.name is not None and not deck.name.strip():
        raise HTTPException(status_code=400, detail="deck name must not be blank")

    try:
        updated_deck = update_deck(deck_id, deck)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="deck update failed") from exc
    if not updated_deck:
        raise HTTPException(status_code=404, detail="deck not found")
    return DeckResponse(**updated_deck)


@app.delete("/decks/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_deck(deck_id: int) -> Response:
    deleted = delete_deck(deck_id)
    if deleted is None:
        raise HTTPException(status_code=400, detail="default deck cannot be deleted")
    if deleted is False:
        raise HTTPException(status_code=404, detail="deck not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/vocab-items", response_model=VocabItemsResponse)
def get_vocab_items(deck_id: int | None = Query(default=None)) -> VocabItemsResponse:
    if deck_id is not None and not get_deck(deck_id):
        raise HTTPException(status_code=404, detail="deck not found")
    return VocabItemsResponse(items=list_vocab_items(deck_id=deck_id))


@app.get("/study-items", response_model=StudyItemsResponse)
def get_study_items(deck_id: int | None = Query(default=None)) -> StudyItemsResponse:
    if deck_id is not None and not get_deck(deck_id):
        raise HTTPException(status_code=404, detail="deck not found")
    return StudyItemsResponse(items=list_study_items(deck_id=deck_id))


@app.post("/study-items/{item_id}/review", response_model=VocabItemResponse)
def post_study_review(
    item_id: int, review: StudyReviewRequest
) -> VocabItemResponse:
    if review.result not in VALID_REVIEW_RESULTS:
        raise HTTPException(status_code=400, detail="invalid review result")

    updated_item = record_study_review(item_id, review.result)
    if not updated_item:
        raise HTTPException(status_code=404, detail="vocab item not found")
    return VocabItemResponse(**updated_item)


@app.get("/vocab-items/export.csv")
def export_vocab_items_csv(deck_id: int | None = Query(default=None)) -> Response:
    if deck_id is not None and not get_deck(deck_id):
        raise HTTPException(status_code=404, detail="deck not found")

    output = StringIO()
    fieldnames = [
        "surface",
        "base_form",
        "reading",
        "part_of_speech",
        "meaning_ko",
        "context_explanation_ko",
        "example_sentence",
        "status",
        "review_level",
        "correct_count",
        "wrong_count",
        "next_review_at",
        "created_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(list_vocab_items(deck_id=deck_id))

    content = "\ufeff" + output.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="jp-vocab-items.csv"',
        },
    )


@app.post("/vocab-items", response_model=VocabItemResponse)
def post_vocab_item(
    item: VocabItemCreate, response: Response
) -> VocabItemResponse:
    if item.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    saved_item, created = create_vocab_item(item)
    if not created:
        response.status_code = status.HTTP_200_OK
    return VocabItemResponse(**saved_item)


@app.patch("/vocab-items/{item_id}", response_model=VocabItemResponse)
def patch_vocab_item(item_id: int, item: VocabItemUpdate) -> VocabItemResponse:
    if item.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    updated_item = update_vocab_item_status(item_id, item.status)
    if not updated_item:
        raise HTTPException(status_code=404, detail="vocab item not found")
    return VocabItemResponse(**updated_item)


@app.post("/vocab-items/{item_id}/explain", response_model=VocabItemResponse)
def explain_vocab_item(item_id: int) -> VocabItemResponse:
    item = get_vocab_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="vocab item not found")

    try:
        explanation = generate_context_explanation(item)
    except MissingOpenAIKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIExplanationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    updated_item = update_context_explanation(item_id, explanation)
    if not updated_item:
        raise HTTPException(status_code=404, detail="vocab item not found")
    return VocabItemResponse(**updated_item)


@app.delete("/vocab-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_vocab_item(item_id: int) -> Response:
    if not delete_vocab_item(item_id):
        raise HTTPException(status_code=404, detail="vocab item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

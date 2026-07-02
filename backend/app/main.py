import csv
from io import StringIO

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.analyzer import analyzer
from app.database import (
    create_vocab_item,
    delete_vocab_item,
    init_db,
    list_study_items,
    list_vocab_items,
    record_study_review,
    update_vocab_item_status,
)
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
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


@app.get("/vocab-items", response_model=VocabItemsResponse)
def get_vocab_items() -> VocabItemsResponse:
    return VocabItemsResponse(items=list_vocab_items())


@app.get("/study-items", response_model=StudyItemsResponse)
def get_study_items() -> StudyItemsResponse:
    return StudyItemsResponse(items=list_study_items())


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
def export_vocab_items_csv() -> Response:
    output = StringIO()
    fieldnames = [
        "surface",
        "base_form",
        "reading",
        "part_of_speech",
        "meaning_ko",
        "status",
        "created_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(list_vocab_items())

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


@app.delete("/vocab-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_vocab_item(item_id: int) -> Response:
    if not delete_vocab_item(item_id):
        raise HTTPException(status_code=404, detail="vocab item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

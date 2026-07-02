import csv
from io import StringIO

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.ai_explainer import (
    AIExplanationError,
    MissingOpenAIKeyError,
    generate_context_explanation,
)
from app.analyze_postprocess import improve_analysis_tokens
from app.analyzer import analyzer
from app.analyzer import find_example_sentence, split_sentences
from app.database import (
    build_deck_package,
    create_custom_term,
    create_deck,
    create_vocab_item,
    delete_custom_term,
    delete_deck,
    delete_vocab_item,
    get_custom_term,
    get_deck,
    get_stats,
    get_vocab_item,
    import_deck_package,
    init_db,
    list_custom_terms,
    list_decks,
    list_known_vocab_keys,
    list_study_items,
    list_vocab_items,
    record_study_review,
    update_custom_term,
    update_deck,
    update_context_explanation,
    update_vocab_item,
)
from app.dictionary_service import lookup_meaning
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CustomTermCreate,
    CustomTermResponse,
    CustomTermsResponse,
    CustomTermUpdate,
    DeckCreate,
    DeckDeleteResponse,
    DeckPackage,
    DeckPackageImportResponse,
    DeckResponse,
    DecksResponse,
    DeckUpdate,
    StatsResponse,
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


def ranges_overlap(
    first_start: int, first_end: int, second_start: int, second_end: int
) -> bool:
    return first_start < second_end and second_start < first_end


def find_custom_term_tokens(
    text: str, custom_terms: list[dict], deck_id: int | None
) -> list[dict]:
    sentences = split_sentences(text)
    matches: list[dict] = []
    occupied_ranges: list[tuple[int, int]] = []

    for term in sorted(custom_terms, key=lambda item: len(item["term"]), reverse=True):
        term_text = term["term"]
        if not term_text:
            continue
        search_start = 0
        while True:
            start = text.find(term_text, search_start)
            if start == -1:
                break
            end = start + len(term_text)
            search_start = start + 1
            if any(
                ranges_overlap(start, end, occupied_start, occupied_end)
                for occupied_start, occupied_end in occupied_ranges
            ):
                continue
            occupied_ranges.append((start, end))
            matches.append(
                {
                    "surface": term_text,
                    "base_form": term_text,
                    "reading": term["reading"],
                    "part_of_speech": term["part_of_speech"],
                    "normalized_form": term_text,
                    "meaning_ko": lookup_meaning(
                        surface=term_text,
                        base_form=term_text,
                        normalized_form=term_text,
                        reading=term["reading"],
                        deck_id=deck_id,
                        custom_meaning_ko=term["meaning_ko"],
                    ),
                    "dictionary_gloss": "",
                    "example_sentence": find_example_sentence(sentences, start),
                    "is_custom_term": True,
                    "quality_tag": "custom_term",
                    "_start": start,
                    "_end": end,
                }
            )

    return sorted(matches, key=lambda item: item["_start"])


def merge_custom_terms(text: str, tokens: list[dict], deck_id: int | None) -> list[dict]:
    custom_tokens = find_custom_term_tokens(
        text, list_custom_terms(deck_id=deck_id), deck_id
    )
    custom_ranges = [(token["_start"], token["_end"]) for token in custom_tokens]
    seen_base_forms = {token["base_form"] for token in custom_tokens}
    merged_tokens = custom_tokens.copy()

    for token in tokens:
        token_start = token.get("_start", -1)
        token_end = token.get("_end", -1)
        if token["base_form"] in seen_base_forms:
            continue
        if token_start != -1 and any(
            ranges_overlap(token_start, token_end, start, end)
            for start, end in custom_ranges
        ):
            continue
        seen_base_forms.add(token["base_form"])
        token["is_custom_term"] = False
        token["quality_tag"] = token.get("quality_tag") or "normal"
        merged_tokens.append(token)

    return sorted(merged_tokens, key=lambda item: item.get("_start", 0))


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

    if request.deck_id is not None and not get_deck(request.deck_id):
        raise HTTPException(status_code=404, detail="deck not found")

    analysis_tokens, raw_tokens = analyzer.analyze_with_raw(
        request.text, deck_id=request.deck_id
    )
    tokens = merge_custom_terms(
        request.text,
        analysis_tokens,
        request.deck_id,
    )
    tokens = improve_analysis_tokens(
        text=request.text,
        raw_tokens=raw_tokens,
        tokens=tokens,
        deck_id=request.deck_id,
    )
    if not request.include_known:
        known_keys = list_known_vocab_keys(deck_id=request.deck_id)
        tokens = [
            token
            for token in tokens
            if (token["base_form"], token["reading"]) not in known_keys
        ]

    return AnalyzeResponse(tokens=tokens)


@app.get("/custom-terms", response_model=CustomTermsResponse)
def get_custom_terms(
    deck_id: int | None = Query(default=None),
) -> CustomTermsResponse:
    if deck_id is not None and not get_deck(deck_id):
        raise HTTPException(status_code=404, detail="deck not found")
    return CustomTermsResponse(items=list_custom_terms(deck_id=deck_id))


@app.post("/custom-terms", response_model=CustomTermResponse)
def post_custom_term(
    term: CustomTermCreate, response: Response
) -> CustomTermResponse:
    if not term.term.strip():
        raise HTTPException(status_code=400, detail="term must not be blank")
    if term.deck_id is not None and not get_deck(term.deck_id):
        raise HTTPException(status_code=404, detail="deck not found")

    saved_term, created = create_custom_term(term)
    if not created:
        response.status_code = status.HTTP_200_OK
    return CustomTermResponse(**saved_term)


@app.patch("/custom-terms/{term_id}", response_model=CustomTermResponse)
def patch_custom_term(
    term_id: int, term: CustomTermUpdate
) -> CustomTermResponse:
    if term.term is not None and not term.term.strip():
        raise HTTPException(status_code=400, detail="term must not be blank")
    if term.deck_id is not None and not get_deck(term.deck_id):
        raise HTTPException(status_code=404, detail="deck not found")

    updated_term = update_custom_term(term_id, term)
    if not updated_term:
        raise HTTPException(status_code=404, detail="custom term not found")
    return CustomTermResponse(**updated_term)


@app.delete("/custom-terms/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_custom_term(term_id: int) -> Response:
    if not delete_custom_term(term_id):
        raise HTTPException(status_code=404, detail="custom term not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@app.delete("/decks/{deck_id}", response_model=DeckDeleteResponse)
def remove_deck(deck_id: int) -> DeckDeleteResponse:
    deleted = delete_deck(deck_id)
    if deleted is None:
        raise HTTPException(status_code=400, detail="default deck cannot be deleted")
    if deleted is False:
        raise HTTPException(status_code=404, detail="deck not found")
    return DeckDeleteResponse(
        deleted_deck_id=deleted["deleted_deck_id"],
        deleted_vocab_count=deleted["deleted_vocab_count"],
        message="덱과 덱에 포함된 단어를 삭제했습니다.",
    )


@app.get("/decks/{deck_id}/export-package", response_model=DeckPackage)
def export_deck_package(deck_id: int) -> DeckPackage:
    package = build_deck_package(deck_id=deck_id)
    if not package:
        raise HTTPException(status_code=404, detail="deck not found")
    return DeckPackage(**package)


@app.post("/decks/import-package", response_model=DeckPackageImportResponse)
def post_deck_package_import(package: DeckPackage) -> DeckPackageImportResponse:
    if package.package_type != "jp_vocab_reader_deck":
        raise HTTPException(status_code=400, detail="invalid package_type")
    if package.package_version != 1:
        raise HTTPException(status_code=400, detail="unsupported package_version")
    return DeckPackageImportResponse(**import_deck_package(package))


@app.get("/vocab-items", response_model=VocabItemsResponse)
def get_vocab_items(
    deck_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    due_only: bool = Query(default=False),
    sort: str | None = Query(default=None),
) -> VocabItemsResponse:
    if deck_id is not None and not get_deck(deck_id):
        raise HTTPException(status_code=404, detail="deck not found")
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")
    if sort is not None and sort not in {
        "created_desc",
        "created_asc",
        "wrong_desc",
        "correct_desc",
        "review_level_asc",
        "next_review_asc",
    }:
        raise HTTPException(status_code=400, detail="invalid sort")
    return VocabItemsResponse(
        items=list_vocab_items(
            deck_id=deck_id,
            status=status,
            q=q,
            due_only=due_only,
            sort=sort,
        )
    )


@app.get("/study-items", response_model=StudyItemsResponse)
def get_study_items(deck_id: int | None = Query(default=None)) -> StudyItemsResponse:
    if deck_id is not None and not get_deck(deck_id):
        raise HTTPException(status_code=404, detail="deck not found")
    return StudyItemsResponse(items=list_study_items(deck_id=deck_id))


@app.get("/stats", response_model=StatsResponse)
def get_learning_stats(deck_id: int | None = Query(default=None)) -> StatsResponse:
    if deck_id is not None and not get_deck(deck_id):
        raise HTTPException(status_code=404, detail="deck not found")
    return StatsResponse(**get_stats(deck_id=deck_id))


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
        "quality_tag",
        "meaning_ko",
        "dictionary_gloss",
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
    if not item.surface.strip() and not item.base_form.strip():
        raise HTTPException(
            status_code=400, detail="surface or base_form must not be blank"
        )
    if item.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    saved_item, created = create_vocab_item(item)
    if not created:
        response.status_code = status.HTTP_200_OK
    return VocabItemResponse(**saved_item)


@app.patch("/vocab-items/{item_id}", response_model=VocabItemResponse)
def patch_vocab_item(item_id: int, item: VocabItemUpdate) -> VocabItemResponse:
    if item.status is not None and item.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    updated_item = update_vocab_item(item_id, item)
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

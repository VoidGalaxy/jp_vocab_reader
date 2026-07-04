import csv
from io import StringIO

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.ai_explainer import (
    AIExplanationError,
    MissingOpenAIKeyError,
    generate_context_explanation,
)
from app.analyze_postprocess import improve_analysis_tokens
from app.analyzer import analyzer
from app.analyzer import find_example_sentence, split_sentences
from app.auth import (
    create_access_token,
    get_current_user_optional_or_dev,
    hash_password,
    verify_password,
)
from app.database import get_database_engine, init_db
from app.repositories.custom_term_repository import (
    create_custom_term,
    delete_custom_term,
    get_custom_term,
    list_custom_terms,
    update_custom_term,
)
from app.repositories.deck_package_repository import (
    export_deck_package as export_deck_package_data,
    import_deck_package,
)
from app.repositories.deck_repository import (
    create_deck,
    delete_deck_with_items,
    get_deck_by_id,
    list_decks,
    update_deck,
)
from app.repositories.shared_deck_repository import (
    get_shared_deck as get_shared_deck_data,
    import_shared_deck,
    list_shared_decks,
    publish_deck,
)
from app.repositories.stats_repository import build_stats
from app.repositories.user_repository import (
    create_user,
    email_exists,
    get_user_by_email,
    normalize_email,
)
from app.repositories.vocab_repository import (
    create_or_update_vocab_item,
    delete_vocab_item,
    get_vocab_item,
    list_known_vocab_keys,
    list_study_items,
    list_vocab_items,
    record_review,
    update_context_explanation,
    update_vocab_item,
)
from app.dictionary_service import lookup_meaning
from app.settings import APP_NAME, get_cors_allow_origins
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthTokenResponse,
    CustomTermCreate,
    CustomTermResponse,
    CustomTermsResponse,
    CustomTermUpdate,
    DeckCreate,
    DeckDeleteResponse,
    DeckPackage,
    DeckPackageImportResponse,
    DeckPublishRequest,
    DeckPublishResponse,
    DeckResponse,
    DecksResponse,
    DeckUpdate,
    SharedDeckDetailResponse,
    SharedDeckImportResponse,
    SharedDeckSummaryResponse,
    StatsResponse,
    StudyItemsResponse,
    StudyReviewRequest,
    VALID_REVIEW_RESULTS,
    VALID_STATUSES,
    UserResponse,
    VocabItemCreate,
    VocabItemResponse,
    VocabItemsResponse,
    VocabItemUpdate,
)


app = FastAPI(title="JP Vocab Reader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allow_origins(),
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


def merge_custom_terms(
    text: str, tokens: list[dict], user_id: int, deck_id: int | None
) -> list[dict]:
    custom_tokens = find_custom_term_tokens(
        text, list_custom_terms(user_id, deck_id=deck_id), deck_id
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
    return {
        "status": "ok",
        "app": APP_NAME,
        "database": get_database_engine(),
        "auth": "enabled",
    }


def build_auth_response(user: dict) -> AuthTokenResponse:
    return AuthTokenResponse(
        access_token=create_access_token(user),
        token_type="bearer",
        user=UserResponse(**user),
    )


def current_user_id(request: Request) -> int:
    return int(get_current_user_optional_or_dev(request)["id"])


@app.post("/auth/register", response_model=AuthTokenResponse)
def register_user(request: AuthRegisterRequest) -> AuthTokenResponse:
    email = normalize_email(request.email)
    if not email:
        raise HTTPException(status_code=400, detail="email must not be blank")
    if email_exists(email):
        raise HTTPException(status_code=400, detail="email already exists")
    if len(request.password) < 8:
        raise HTTPException(
            status_code=400, detail="password must be at least 8 characters"
        )

    display_name = request.display_name.strip() or email.split("@")[0]
    user = create_user(
        email=email,
        display_name=display_name,
        password_hash=hash_password(request.password),
    )
    return build_auth_response(user)


@app.post("/auth/login", response_model=AuthTokenResponse)
def login_user(request: AuthLoginRequest) -> AuthTokenResponse:
    user = get_user_by_email(request.email)
    if not user or user["auth_provider"] == "dev":
        raise HTTPException(status_code=401, detail="invalid email or password")
    if not verify_password(request.password, user.get("password_hash")):
        raise HTTPException(status_code=401, detail="invalid email or password")
    return build_auth_response(user)


@app.get("/me", response_model=UserResponse)
def get_me(request: Request) -> UserResponse:
    return UserResponse(**get_current_user_optional_or_dev(request))


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest, http_request: Request) -> AnalyzeResponse:
    user_id = current_user_id(http_request)
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text must not be blank")

    if request.deck_id is not None and not get_deck_by_id(user_id, request.deck_id):
        raise HTTPException(status_code=404, detail="deck not found")

    analysis_tokens, raw_tokens = analyzer.analyze_with_raw(
        request.text, deck_id=request.deck_id
    )
    tokens = merge_custom_terms(
        request.text,
        analysis_tokens,
        user_id,
        request.deck_id,
    )
    tokens = improve_analysis_tokens(
        text=request.text,
        raw_tokens=raw_tokens,
        tokens=tokens,
        deck_id=request.deck_id,
    )
    if not request.include_known:
        known_keys = list_known_vocab_keys(user_id, deck_id=request.deck_id)
        tokens = [
            token
            for token in tokens
            if (token["base_form"], token["reading"]) not in known_keys
        ]

    return AnalyzeResponse(tokens=tokens)


@app.get("/custom-terms", response_model=CustomTermsResponse)
def get_custom_terms(
    http_request: Request,
    deck_id: int | None = Query(default=None),
) -> CustomTermsResponse:
    user_id = current_user_id(http_request)
    if deck_id is not None and not get_deck_by_id(user_id, deck_id):
        raise HTTPException(status_code=404, detail="deck not found")
    return CustomTermsResponse(items=list_custom_terms(user_id, deck_id=deck_id))


@app.post("/custom-terms", response_model=CustomTermResponse)
def post_custom_term(
    term: CustomTermCreate, response: Response, http_request: Request
) -> CustomTermResponse:
    user_id = current_user_id(http_request)
    if not term.term.strip():
        raise HTTPException(status_code=400, detail="term must not be blank")
    if term.deck_id is not None and not get_deck_by_id(user_id, term.deck_id):
        raise HTTPException(status_code=404, detail="deck not found")

    saved_term, created = create_custom_term(user_id, term)
    if not created:
        response.status_code = status.HTTP_200_OK
    return CustomTermResponse(**saved_term)


@app.patch("/custom-terms/{term_id}", response_model=CustomTermResponse)
def patch_custom_term(
    term_id: int, term: CustomTermUpdate, http_request: Request
) -> CustomTermResponse:
    user_id = current_user_id(http_request)
    if term.term is not None and not term.term.strip():
        raise HTTPException(status_code=400, detail="term must not be blank")
    if term.deck_id is not None and not get_deck_by_id(user_id, term.deck_id):
        raise HTTPException(status_code=404, detail="deck not found")

    updated_term = update_custom_term(user_id, term_id, term)
    if not updated_term:
        raise HTTPException(status_code=404, detail="custom term not found")
    return CustomTermResponse(**updated_term)


@app.delete("/custom-terms/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_custom_term(term_id: int, http_request: Request) -> Response:
    user_id = current_user_id(http_request)
    if not delete_custom_term(user_id, term_id):
        raise HTTPException(status_code=404, detail="custom term not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/decks", response_model=DecksResponse)
def get_decks(http_request: Request) -> DecksResponse:
    return DecksResponse(items=list_decks(current_user_id(http_request)))


@app.post("/decks", response_model=DeckResponse)
def post_deck(
    deck: DeckCreate, response: Response, http_request: Request
) -> DeckResponse:
    user_id = current_user_id(http_request)
    if not deck.name.strip():
        raise HTTPException(status_code=400, detail="deck name must not be blank")

    saved_deck, created = create_deck(user_id, deck)
    if not created:
        response.status_code = status.HTTP_200_OK
    return DeckResponse(**saved_deck)


@app.patch("/decks/{deck_id}", response_model=DeckResponse)
def patch_deck(deck_id: int, deck: DeckUpdate, http_request: Request) -> DeckResponse:
    user_id = current_user_id(http_request)
    if deck.name is not None and not deck.name.strip():
        raise HTTPException(status_code=400, detail="deck name must not be blank")

    try:
        updated_deck = update_deck(user_id, deck_id, deck)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="deck update failed") from exc
    if not updated_deck:
        raise HTTPException(status_code=404, detail="deck not found")
    return DeckResponse(**updated_deck)


@app.delete("/decks/{deck_id}", response_model=DeckDeleteResponse)
def remove_deck(deck_id: int, http_request: Request) -> DeckDeleteResponse:
    deleted = delete_deck_with_items(current_user_id(http_request), deck_id)
    if deleted is None:
        raise HTTPException(status_code=400, detail="default deck cannot be deleted")
    if deleted is False:
        raise HTTPException(status_code=404, detail="deck not found")
    return DeckDeleteResponse(
        deleted_deck_id=deleted["deleted_deck_id"],
        deleted_vocab_count=deleted["deleted_vocab_count"],
        message="덱과 덱에 포함된 단어를 삭제했습니다.",
    )


@app.post("/decks/{deck_id}/publish", response_model=DeckPublishResponse)
def post_deck_publish(
    deck_id: int, request: DeckPublishRequest, http_request: Request
) -> DeckPublishResponse:
    published = publish_deck(
        current_user_id(http_request),
        deck_id=deck_id,
        title=request.title,
        description=request.description,
    )
    if not published:
        raise HTTPException(status_code=404, detail="deck not found")
    return DeckPublishResponse(**published)


@app.get("/decks/{deck_id}/export-package", response_model=DeckPackage)
def export_deck_package(deck_id: int, http_request: Request) -> DeckPackage:
    package = export_deck_package_data(current_user_id(http_request), deck_id=deck_id)
    if not package:
        raise HTTPException(status_code=404, detail="deck not found")
    return DeckPackage(**package)


@app.post("/decks/import-package", response_model=DeckPackageImportResponse)
def post_deck_package_import(
    package: DeckPackage, http_request: Request
) -> DeckPackageImportResponse:
    if package.package_type != "jp_vocab_reader_deck":
        raise HTTPException(status_code=400, detail="invalid package_type")
    if package.package_version != 1:
        raise HTTPException(status_code=400, detail="unsupported package_version")
    return DeckPackageImportResponse(
        **import_deck_package(current_user_id(http_request), package)
    )


@app.get("/shared-decks", response_model=list[SharedDeckSummaryResponse])
def get_shared_decks() -> list[SharedDeckSummaryResponse]:
    return [SharedDeckSummaryResponse(**deck) for deck in list_shared_decks()]


@app.get("/shared-decks/{shared_deck_id}", response_model=SharedDeckDetailResponse)
def get_shared_deck(shared_deck_id: int) -> SharedDeckDetailResponse:
    shared_deck = get_shared_deck_data(shared_deck_id)
    if not shared_deck:
        raise HTTPException(status_code=404, detail="shared deck not found")
    return SharedDeckDetailResponse(**shared_deck)


@app.post(
    "/shared-decks/{shared_deck_id}/import", response_model=SharedDeckImportResponse
)
def post_shared_deck_import(
    shared_deck_id: int, http_request: Request
) -> SharedDeckImportResponse:
    imported = import_shared_deck(current_user_id(http_request), shared_deck_id)
    if not imported:
        raise HTTPException(status_code=404, detail="shared deck not found")
    return SharedDeckImportResponse(**imported)


@app.get("/vocab-items", response_model=VocabItemsResponse)
def get_vocab_items(
    http_request: Request,
    deck_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    due_only: bool = Query(default=False),
    sort: str | None = Query(default=None),
) -> VocabItemsResponse:
    user_id = current_user_id(http_request)
    if deck_id is not None and not get_deck_by_id(user_id, deck_id):
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
            user_id,
            deck_id=deck_id,
            status=status,
            q=q,
            due_only=due_only,
            sort=sort,
        )
    )


@app.get("/study-items", response_model=StudyItemsResponse)
def get_study_items(
    http_request: Request, deck_id: int | None = Query(default=None)
) -> StudyItemsResponse:
    user_id = current_user_id(http_request)
    if deck_id is not None and not get_deck_by_id(user_id, deck_id):
        raise HTTPException(status_code=404, detail="deck not found")
    return StudyItemsResponse(items=list_study_items(user_id, deck_id=deck_id))


@app.get("/stats", response_model=StatsResponse)
def get_learning_stats(
    http_request: Request, deck_id: int | None = Query(default=None)
) -> StatsResponse:
    user_id = current_user_id(http_request)
    if deck_id is not None and not get_deck_by_id(user_id, deck_id):
        raise HTTPException(status_code=404, detail="deck not found")
    return StatsResponse(**build_stats(user_id, deck_id=deck_id))


@app.post("/study-items/{item_id}/review", response_model=VocabItemResponse)
def post_study_review(
    item_id: int, review: StudyReviewRequest, http_request: Request
) -> VocabItemResponse:
    if review.result not in VALID_REVIEW_RESULTS:
        raise HTTPException(status_code=400, detail="invalid review result")

    updated_item = record_review(current_user_id(http_request), item_id, review.result)
    if not updated_item:
        raise HTTPException(status_code=404, detail="vocab item not found")
    return VocabItemResponse(**updated_item)


@app.get("/vocab-items/export.csv")
def export_vocab_items_csv(
    http_request: Request, deck_id: int | None = Query(default=None)
) -> Response:
    user_id = current_user_id(http_request)
    if deck_id is not None and not get_deck_by_id(user_id, deck_id):
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
    writer.writerows(list_vocab_items(user_id, deck_id=deck_id))

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
    item: VocabItemCreate, response: Response, http_request: Request
) -> VocabItemResponse:
    user_id = current_user_id(http_request)
    if not item.surface.strip() and not item.base_form.strip():
        raise HTTPException(
            status_code=400, detail="surface or base_form must not be blank"
        )
    if item.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")
    if item.deck_id is not None and not get_deck_by_id(user_id, item.deck_id):
        raise HTTPException(status_code=404, detail="deck not found")

    saved_item, created = create_or_update_vocab_item(user_id, item)
    if not created:
        response.status_code = status.HTTP_200_OK
    return VocabItemResponse(**saved_item)


@app.patch("/vocab-items/{item_id}", response_model=VocabItemResponse)
def patch_vocab_item(
    item_id: int, item: VocabItemUpdate, http_request: Request
) -> VocabItemResponse:
    user_id = current_user_id(http_request)
    if item.status is not None and item.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")
    if item.deck_id is not None and not get_deck_by_id(user_id, item.deck_id):
        raise HTTPException(status_code=404, detail="deck not found")

    updated_item = update_vocab_item(user_id, item_id, item)
    if not updated_item:
        raise HTTPException(status_code=404, detail="vocab item not found")
    return VocabItemResponse(**updated_item)


@app.post("/vocab-items/{item_id}/explain", response_model=VocabItemResponse)
def explain_vocab_item(item_id: int, http_request: Request) -> VocabItemResponse:
    # Deprecated: per-word AI explanation is hidden from UI.
    user_id = current_user_id(http_request)
    item = get_vocab_item(user_id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="vocab item not found")

    try:
        explanation = generate_context_explanation(item)
    except MissingOpenAIKeyError as exc:
        raise HTTPException(
            status_code=400,
            detail="AI 설명 기능을 사용하려면 서버에 OPENAI_API_KEY를 설정해야 합니다.",
        ) from exc
    except AIExplanationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    updated_item = update_context_explanation(user_id, item_id, explanation)
    if not updated_item:
        raise HTTPException(status_code=404, detail="vocab item not found")
    return VocabItemResponse(**updated_item)


@app.delete("/vocab-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_vocab_item(item_id: int, http_request: Request) -> Response:
    if not delete_vocab_item(current_user_id(http_request), item_id):
        raise HTTPException(status_code=404, detail="vocab item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.schemas import (
    ApiResponse,
    BadCaseDraftRequest,
    BadCaseSubmitRequest,
    BadCaseUpdateRequest,
    CandidateUpdateRequest,
    CustomerOpsRetrievalRequest,
    ImportJsonRequest,
    LegacyRagImportRequest,
    ManualCleanRequest,
    RagSearchRequest,
    ReviewDecisionRequest,
)
from app.database import check_database_connection, check_pgvector_available, init_database_tables
from app.storage import (
    apply_review_decision,
    build_rag_chunks,
    create_candidate_from_bad_case,
    create_bad_case,
    create_raw_batch,
    get_bad_case,
    get_cleaning_job,
    get_customerops_retrieval_trace,
    get_extraction_job,
    get_knowledge_candidate,
    get_legacy_rag_import,
    get_rag_chunk,
    get_raw_batch_metadata,
    get_sanitized_batch,
    list_knowledge_candidates,
    list_bad_cases,
    list_legacy_rag_imports,
    list_pending_review_candidates,
    list_rag_chunks,
    list_raw_batches,
    manual_clean_sanitized_message,
    run_cleaning,
    run_customerops_retrieval,
    run_extraction,
    search_rag_chunks,
    import_legacy_rag,
    update_bad_case,
    update_knowledge_candidate,
)

app = FastAPI(title="DataHub API", version="0.1.0")

# Ensure tables exist on module load (idempotent, safe for both tests and production).
# Also runs on startup event for environments where module-level init is insufficient.
try:
    init_database_tables()
except Exception:
    pass


@app.on_event("startup")
def _startup_init_database() -> None:
    """Idempotent: ensure all tables exist on startup (P1-M17)."""
    try:
        init_database_tables()
    except Exception:
        # Startup must not fail if DB is temporarily unreachable;
        # health check will report the error status.
        pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://data-hub-flame.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BAD_CASE_ISSUE_TYPES = {
    "wrong_answer",
    "missing_knowledge",
    "unsafe_answer",
    "bad_tone",
    "retrieval_miss",
    "other",
}
BAD_CASE_SEVERITIES = {"low", "medium", "high"}
BAD_CASE_STATUSES = {"open", "triaged", "resolved", "ignored"}
BAD_CASE_RESOLUTION_TYPES = {
    "create_new_knowledge",
    "update_existing_knowledge",
    "retrieval_tuning",
    "ignore",
    "other",
}
KNOWLEDGE_TYPES = {
    "faq",
    "standard_answer",
    "business_rule",
    "human_handoff_rule",
    "forbidden_answer_rule",
}
KNOWLEDGE_INTENTS = {
    "shipping",
    "refund",
    "order_status",
    "product_info",
    "handoff",
    "prohibited_answer",
    "general",
}


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def _customerops_error(
    code: str,
    message: str,
    status_code: int,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
            "requestId": _request_id(),
        },
    )


def _authorize_customerops_client(client_header: str | None) -> JSONResponse | None:
    if client_header != "CustomerOpsAgent":
        return _customerops_error(
            code="UNAUTHORIZED_CLIENT",
            message="CustomerOpsAgent client header is required.",
            status_code=401,
        )
    return None


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "datahub-api",
        "phase": "P1-M21",
        "database_status": check_database_connection(),
        "pgvector_status": check_pgvector_available(),
    }


@app.get("/api/health")
def api_health() -> dict[str, object]:
    return health()


@app.post("/api/legacy-rag/import", response_model=ApiResponse)
def import_legacy_rag_export(payload: LegacyRagImportRequest) -> ApiResponse:
    metadata = import_legacy_rag(payload)
    return ApiResponse(
        success=True,
        data=metadata.model_dump(),
        requestId=_request_id(),
    )


@app.get("/api/legacy-rag/imports", response_model=ApiResponse)
def list_legacy_imports() -> ApiResponse:
    imports = [item.model_dump() for item in list_legacy_rag_imports()]
    return ApiResponse(
        success=True,
        data={"imports": imports},
        requestId=_request_id(),
    )


@app.get("/api/legacy-rag/imports/{import_id}", response_model=ApiResponse)
def get_legacy_import(import_id: str) -> ApiResponse:
    metadata = get_legacy_rag_import(import_id)
    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "LEGACY_RAG_IMPORT_NOT_FOUND",
                "message": "Legacy RAG import was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=metadata.model_dump(),
        requestId=_request_id(),
    )


@app.post("/api/sources/import-json", response_model=ApiResponse)
def import_json_source(payload: ImportJsonRequest) -> ApiResponse:
    metadata = create_raw_batch(payload)
    return ApiResponse(
        success=True,
        data=metadata.model_dump(),
        requestId=_request_id(),
    )


@app.get("/api/sources", response_model=ApiResponse)
def list_sources() -> ApiResponse:
    batches = [batch.model_dump() for batch in list_raw_batches()]
    return ApiResponse(
        success=True,
        data={"sources": batches},
        requestId=_request_id(),
    )


@app.get("/api/sources/{batch_id}", response_model=ApiResponse)
def get_source(batch_id: str) -> ApiResponse:
    metadata = get_raw_batch_metadata(batch_id)
    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "BATCH_NOT_FOUND",
                "message": "Raw batch was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=metadata.model_dump(),
        requestId=_request_id(),
    )


@app.post("/api/cleaning/run/{batch_id}", response_model=ApiResponse)
def run_cleaning_for_source(batch_id: str) -> ApiResponse:
    job = run_cleaning(batch_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "BATCH_NOT_FOUND",
                "message": "Raw batch was not found or could not be read.",
            },
        )
    return ApiResponse(
        success=True,
        data=job.model_dump(),
        requestId=_request_id(),
    )


@app.get("/api/cleaning/jobs/{job_id}", response_model=ApiResponse)
def get_cleaning_job_status(job_id: str) -> ApiResponse:
    job = get_cleaning_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "JOB_NOT_FOUND",
                "message": "Cleaning job was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=job.model_dump(),
        requestId=_request_id(),
    )


@app.get("/api/sanitized/{batch_id}", response_model=ApiResponse)
def get_sanitized_source(batch_id: str) -> ApiResponse:
    sanitized = get_sanitized_batch(batch_id)
    if sanitized is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SANITIZED_BATCH_NOT_FOUND",
                "message": "Sanitized batch was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=sanitized.model_dump(),
        requestId=_request_id(),
    )


@app.patch("/api/sanitized/{batch_id}/messages/{message_id}/manual-clean", response_model=ApiResponse)
def manual_clean_message(
    batch_id: str,
    message_id: str,
    payload: ManualCleanRequest,
) -> ApiResponse:
    record = manual_clean_sanitized_message(batch_id, message_id, payload)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SANITIZED_MESSAGE_NOT_FOUND",
                "message": "Sanitized batch or message was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=record.model_dump(),
        requestId=_request_id(),
    )


@app.post("/api/extraction/run/{batch_id}", response_model=ApiResponse)
def run_extraction_for_sanitized_batch(batch_id: str) -> ApiResponse:
    job = run_extraction(batch_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SANITIZED_BATCH_NOT_FOUND",
                "message": "Sanitized batch was not found. Run cleaning first.",
            },
        )
    return ApiResponse(
        success=True,
        data=job.model_dump(),
        requestId=_request_id(),
    )


@app.get("/api/extraction/jobs/{job_id}", response_model=ApiResponse)
def get_extraction_job_status(job_id: str) -> ApiResponse:
    job = get_extraction_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "EXTRACTION_JOB_NOT_FOUND",
                "message": "Extraction job was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=job.model_dump(),
        requestId=_request_id(),
    )


@app.get("/api/knowledge/candidates", response_model=ApiResponse)
def list_candidates() -> ApiResponse:
    candidates = [candidate.model_dump() for candidate in list_knowledge_candidates()]
    return ApiResponse(
        success=True,
        data={"candidates": candidates},
        requestId=_request_id(),
    )


@app.get("/api/knowledge/candidates/{candidate_id}", response_model=ApiResponse)
def get_candidate(candidate_id: str) -> ApiResponse:
    candidate = get_knowledge_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "KNOWLEDGE_CANDIDATE_NOT_FOUND",
                "message": "Knowledge candidate was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=candidate.model_dump(),
        requestId=_request_id(),
    )


@app.get("/api/review/pending", response_model=ApiResponse)
def list_pending_review() -> ApiResponse:
    candidates = [candidate.model_dump() for candidate in list_pending_review_candidates()]
    return ApiResponse(
        success=True,
        data={"candidates": candidates},
        requestId=_request_id(),
    )


@app.patch("/api/knowledge/candidates/{candidate_id}", response_model=ApiResponse)
def update_candidate(candidate_id: str, payload: CandidateUpdateRequest) -> ApiResponse:
    candidate = update_knowledge_candidate(candidate_id, payload)
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "KNOWLEDGE_CANDIDATE_NOT_FOUND",
                "message": "Knowledge candidate was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=candidate.model_dump(),
        requestId=_request_id(),
    )


def _review_response(candidate_id: str, status: str, payload: ReviewDecisionRequest) -> ApiResponse:
    candidate = apply_review_decision(candidate_id, status, payload)
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "KNOWLEDGE_CANDIDATE_NOT_FOUND",
                "message": "Knowledge candidate was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=candidate.model_dump(),
        requestId=_request_id(),
    )


@app.post("/api/review/{candidate_id}/approve", response_model=ApiResponse)
def approve_candidate(candidate_id: str, payload: ReviewDecisionRequest) -> ApiResponse:
    return _review_response(candidate_id, "approved", payload)


@app.post("/api/review/{candidate_id}/reject", response_model=ApiResponse)
def reject_candidate(candidate_id: str, payload: ReviewDecisionRequest) -> ApiResponse:
    return _review_response(candidate_id, "rejected", payload)


@app.post("/api/review/{candidate_id}/needs-revision", response_model=ApiResponse)
def request_candidate_revision(candidate_id: str, payload: ReviewDecisionRequest) -> ApiResponse:
    return _review_response(candidate_id, "needs_revision", payload)


@app.post("/api/rag/build", response_model=ApiResponse)
def build_local_rag_chunks() -> ApiResponse:
    result = build_rag_chunks()
    return ApiResponse(
        success=True,
        data=result.model_dump(),
        requestId=_request_id(),
    )


@app.get("/api/rag/chunks", response_model=ApiResponse)
def list_local_rag_chunks() -> ApiResponse:
    chunks = [chunk.model_dump() for chunk in list_rag_chunks()]
    return ApiResponse(
        success=True,
        data={"chunks": chunks},
        requestId=_request_id(),
    )


@app.get("/api/rag/chunks/{chunk_id}", response_model=ApiResponse)
def get_local_rag_chunk(chunk_id: str) -> ApiResponse:
    chunk = get_rag_chunk(chunk_id)
    if chunk is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RAG_CHUNK_NOT_FOUND",
                "message": "RAG chunk was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=chunk.model_dump(),
        requestId=_request_id(),
    )


@app.post("/api/rag/search", response_model=ApiResponse)
def search_local_rag_chunks(payload: RagSearchRequest) -> ApiResponse:
    query = payload.query.strip()
    if not query:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_QUERY",
                "message": "Query must not be empty.",
            },
        )
    if len(query) > 500:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "QUERY_TOO_LONG",
                "message": "Query must be 500 characters or fewer.",
            },
        )
    if payload.top_k < 1 or payload.top_k > 10:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_TOP_K",
                "message": "top_k must be between 1 and 10.",
            },
        )
    results = [
        result.model_dump()
        for result in search_rag_chunks(query, payload.top_k)
    ]
    return ApiResponse(
        success=True,
        data={"results": results},
        requestId=_request_id(),
    )


@app.post("/api/customer-ops-agent/retrieve", response_model=None)
def retrieve_for_customerops_agent(
    payload: CustomerOpsRetrievalRequest,
    x_datahub_client: str | None = Header(default=None, alias="X-DataHub-Client"),
) -> ApiResponse | JSONResponse:
    auth_error = _authorize_customerops_client(x_datahub_client)
    if auth_error is not None:
        return auth_error

    query = payload.query.strip()
    if not query:
        return _customerops_error(
            code="INVALID_QUERY",
            message="Query must not be empty.",
            status_code=400,
        )
    if len(query) > 500:
        return _customerops_error(
            code="QUERY_TOO_LONG",
            message="Query must be 500 characters or fewer.",
            status_code=400,
        )
    if payload.top_k < 1 or payload.top_k > 10:
        return _customerops_error(
            code="INVALID_TOP_K",
            message="top_k must be between 1 and 10.",
            status_code=400,
        )

    retrieval = run_customerops_retrieval(payload, query, payload.top_k)
    return ApiResponse(
        success=True,
        data=retrieval.model_dump(),
        requestId=_request_id(),
    )


@app.get("/api/customer-ops-agent/retrievals/{retrieval_id}", response_model=None)
def get_customerops_retrieval(
    retrieval_id: str,
    x_datahub_client: str | None = Header(default=None, alias="X-DataHub-Client"),
) -> ApiResponse | JSONResponse:
    auth_error = _authorize_customerops_client(x_datahub_client)
    if auth_error is not None:
        return auth_error

    trace = get_customerops_retrieval_trace(retrieval_id)
    if trace is None:
        return _customerops_error(
            code="RETRIEVAL_NOT_FOUND",
            message="Retrieval trace was not found.",
            status_code=404,
        )
    return ApiResponse(
        success=True,
        data=trace.model_dump(),
        requestId=_request_id(),
    )


@app.post("/api/customer-ops-agent/bad-cases", response_model=None)
def submit_customerops_bad_case(
    payload: BadCaseSubmitRequest,
    x_datahub_client: str | None = Header(default=None, alias="X-DataHub-Client"),
) -> ApiResponse | JSONResponse:
    auth_error = _authorize_customerops_client(x_datahub_client)
    if auth_error is not None:
        return auth_error

    user_query = payload.user_query.strip()
    if not user_query:
        return _customerops_error(
            code="INVALID_USER_QUERY",
            message="user_query must not be empty.",
            status_code=400,
        )
    if len(user_query) > 500:
        return _customerops_error(
            code="USER_QUERY_TOO_LONG",
            message="user_query must be 500 characters or fewer.",
            status_code=400,
        )

    agent_answer = payload.agent_answer.strip()
    if not agent_answer:
        return _customerops_error(
            code="INVALID_AGENT_ANSWER",
            message="agent_answer must not be empty.",
            status_code=400,
        )
    if len(agent_answer) > 2000:
        return _customerops_error(
            code="AGENT_ANSWER_TOO_LONG",
            message="agent_answer must be 2000 characters or fewer.",
            status_code=400,
        )

    expected_answer = None
    if payload.expected_answer is not None:
        expected_answer = payload.expected_answer.strip() or None
        if expected_answer is not None and len(expected_answer) > 2000:
            return _customerops_error(
                code="EXPECTED_ANSWER_TOO_LONG",
                message="expected_answer must be 2000 characters or fewer.",
                status_code=400,
            )

    if payload.issue_type not in BAD_CASE_ISSUE_TYPES:
        return _customerops_error(
            code="INVALID_ISSUE_TYPE",
            message="issue_type is not supported.",
            status_code=400,
            details={"allowed": sorted(BAD_CASE_ISSUE_TYPES)},
        )
    if payload.severity not in BAD_CASE_SEVERITIES:
        return _customerops_error(
            code="INVALID_SEVERITY",
            message="severity must be low, medium, or high.",
            status_code=400,
            details={"allowed": sorted(BAD_CASE_SEVERITIES)},
        )

    retrieval_trace = get_customerops_retrieval_trace(payload.retrieval_id)
    if retrieval_trace is None:
        return _customerops_error(
            code="INVALID_RETRIEVAL_REFERENCE",
            message="retrieval_id was not found.",
            status_code=404,
        )

    bad_case = create_bad_case(
        payload=payload,
        retrieval_trace=retrieval_trace,
        user_query=user_query,
        agent_answer=agent_answer,
        expected_answer=expected_answer,
    )
    return ApiResponse(
        success=True,
        data=bad_case.model_dump(),
        requestId=_request_id(),
    )


@app.get("/api/bad-cases", response_model=ApiResponse)
def list_bad_case_queue(
    status: str | None = None,
    issue_type: str | None = None,
    severity: str | None = None,
) -> ApiResponse:
    if status is not None and status not in BAD_CASE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_BAD_CASE_STATUS",
                "message": "Bad Case status filter is not supported.",
            },
        )
    if issue_type is not None and issue_type not in BAD_CASE_ISSUE_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_ISSUE_TYPE",
                "message": "Bad Case issue_type filter is not supported.",
            },
        )
    if severity is not None and severity not in BAD_CASE_SEVERITIES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_SEVERITY",
                "message": "Bad Case severity filter is not supported.",
            },
        )
    bad_cases = [
        bad_case.model_dump()
        for bad_case in list_bad_cases(status=status, issue_type=issue_type, severity=severity)
    ]
    return ApiResponse(
        success=True,
        data={"bad_cases": bad_cases},
        requestId=_request_id(),
    )


@app.get("/api/bad-cases/{bad_case_id}", response_model=ApiResponse)
def get_bad_case_detail(bad_case_id: str) -> ApiResponse:
    bad_case = get_bad_case(bad_case_id)
    if bad_case is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "BAD_CASE_NOT_FOUND",
                "message": "Bad Case was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=bad_case.model_dump(),
        requestId=_request_id(),
    )


@app.patch("/api/bad-cases/{bad_case_id}", response_model=ApiResponse)
def update_bad_case_detail(
    bad_case_id: str,
    payload: BadCaseUpdateRequest,
) -> ApiResponse:
    if payload.status is not None and payload.status not in BAD_CASE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_BAD_CASE_STATUS",
                "message": "Bad Case status is not supported.",
            },
        )
    if payload.resolution_type is not None and payload.resolution_type not in BAD_CASE_RESOLUTION_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_RESOLUTION_TYPE",
                "message": "Bad Case resolution_type is not supported.",
            },
        )
    bad_case = update_bad_case(bad_case_id, payload)
    if bad_case is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "BAD_CASE_NOT_FOUND",
                "message": "Bad Case was not found.",
            },
        )
    return ApiResponse(
        success=True,
        data=bad_case.model_dump(),
        requestId=_request_id(),
    )


@app.post("/api/bad-cases/{bad_case_id}/create-draft", response_model=ApiResponse)
def create_draft_from_bad_case(
    bad_case_id: str,
    payload: BadCaseDraftRequest,
) -> ApiResponse:
    bad_case = get_bad_case(bad_case_id)
    if bad_case is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "BAD_CASE_NOT_FOUND",
                "message": "Bad Case was not found.",
            },
        )
    if bad_case.status == "ignored":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BAD_CASE_IGNORED",
                "message": "Ignored Bad Cases cannot create knowledge drafts.",
            },
        )

    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_DRAFT_PAYLOAD",
                "message": "question must not be empty.",
            },
        )
    if len(question) > 500:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_DRAFT_PAYLOAD",
                "message": "question must be 500 characters or fewer.",
            },
        )

    answer = payload.answer.strip()
    if not answer:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_DRAFT_PAYLOAD",
                "message": "answer must not be empty.",
            },
        )
    if len(answer) > 2000:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_DRAFT_PAYLOAD",
                "message": "answer must be 2000 characters or fewer.",
            },
        )

    if payload.intent not in KNOWLEDGE_INTENTS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_DRAFT_PAYLOAD",
                "message": "intent is not supported.",
            },
        )
    if payload.risk_level not in BAD_CASE_SEVERITIES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_DRAFT_PAYLOAD",
                "message": "risk_level must be low, medium, or high.",
            },
        )
    if payload.knowledge_type not in KNOWLEDGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_DRAFT_PAYLOAD",
                "message": "knowledge_type is not supported.",
            },
        )
    if payload.quality_score < 0 or payload.quality_score > 1:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_DRAFT_PAYLOAD",
                "message": "quality_score must be between 0 and 1.",
            },
        )

    tags = [
        tag.strip()
        for tag in payload.tags
        if tag.strip()
    ]
    candidate = create_candidate_from_bad_case(
        bad_case=bad_case,
        payload=payload,
        question=question,
        answer=answer,
        tags=tags,
    )
    return ApiResponse(
        success=True,
        data=candidate.model_dump(),
        requestId=_request_id(),
    )

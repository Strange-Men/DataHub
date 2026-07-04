from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from app.schemas import (
    ApiResponse,
    BadCaseSubmitRequest,
    BadCaseUpdateRequest,
    CandidateUpdateRequest,
    CustomerOpsRetrievalRequest,
    ImportJsonRequest,
    RagSearchRequest,
    ReviewDecisionRequest,
)
from app.storage import (
    apply_review_decision,
    build_rag_chunks,
    create_bad_case,
    create_raw_batch,
    get_bad_case,
    get_cleaning_job,
    get_customerops_retrieval_trace,
    get_extraction_job,
    get_knowledge_candidate,
    get_rag_chunk,
    get_raw_batch_metadata,
    get_sanitized_batch,
    list_knowledge_candidates,
    list_bad_cases,
    list_pending_review_candidates,
    list_rag_chunks,
    list_raw_batches,
    run_cleaning,
    run_customerops_retrieval,
    run_extraction,
    search_rag_chunks,
    update_bad_case,
    update_knowledge_candidate,
)

app = FastAPI(title="DataHub API", version="0.1.0")

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
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "datahub-api",
        "phase": "M8",
    }


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

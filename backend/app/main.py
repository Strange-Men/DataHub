from uuid import uuid4

from fastapi import FastAPI, HTTPException

from app.schemas import (
    ApiResponse,
    CandidateUpdateRequest,
    ImportJsonRequest,
    RagSearchRequest,
    ReviewDecisionRequest,
)
from app.storage import (
    apply_review_decision,
    build_rag_chunks,
    create_raw_batch,
    get_cleaning_job,
    get_extraction_job,
    get_knowledge_candidate,
    get_rag_chunk,
    get_raw_batch_metadata,
    get_sanitized_batch,
    list_knowledge_candidates,
    list_pending_review_candidates,
    list_rag_chunks,
    list_raw_batches,
    run_cleaning,
    run_extraction,
    search_rag_chunks,
    update_knowledge_candidate,
)

app = FastAPI(title="DataHub API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "datahub-api",
        "phase": "M6.5",
    }


@app.post("/api/sources/import-json", response_model=ApiResponse)
def import_json_source(payload: ImportJsonRequest) -> ApiResponse:
    metadata = create_raw_batch(payload)
    return ApiResponse(
        success=True,
        data=metadata.model_dump(),
        requestId=f"req_{uuid4().hex[:12]}",
    )


@app.get("/api/sources", response_model=ApiResponse)
def list_sources() -> ApiResponse:
    batches = [batch.model_dump() for batch in list_raw_batches()]
    return ApiResponse(
        success=True,
        data={"sources": batches},
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
    )


@app.get("/api/knowledge/candidates", response_model=ApiResponse)
def list_candidates() -> ApiResponse:
    candidates = [candidate.model_dump() for candidate in list_knowledge_candidates()]
    return ApiResponse(
        success=True,
        data={"candidates": candidates},
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
    )


@app.get("/api/review/pending", response_model=ApiResponse)
def list_pending_review() -> ApiResponse:
    candidates = [candidate.model_dump() for candidate in list_pending_review_candidates()]
    return ApiResponse(
        success=True,
        data={"candidates": candidates},
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
    )


@app.get("/api/rag/chunks", response_model=ApiResponse)
def list_local_rag_chunks() -> ApiResponse:
    chunks = [chunk.model_dump() for chunk in list_rag_chunks()]
    return ApiResponse(
        success=True,
        data={"chunks": chunks},
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
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
        requestId=f"req_{uuid4().hex[:12]}",
    )

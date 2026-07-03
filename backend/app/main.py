from uuid import uuid4

from fastapi import FastAPI, HTTPException

from app.schemas import ApiResponse, ImportJsonRequest
from app.storage import create_raw_batch, get_raw_batch_metadata, list_raw_batches

app = FastAPI(title="DataHub API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "datahub-api",
        "phase": "M2",
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

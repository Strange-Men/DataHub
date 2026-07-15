"""Additive P2-M7 semantic-index management APIs; no retrieval surface."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.knowledge_embedding_repositories import list_embeddings
from app.knowledge_embedding_service import (
    P2EmbeddingDimensionError,
    P2EmbeddingFingerprintError,
    P2EmbeddingIndexNotFoundError,
    P2EmbeddingIndexNotReadyError,
    P2EmbeddingKnowledgeAssetNotActiveError,
    P2EmbeddingMissingError,
    P2EmbeddingProfileError,
    P2EmbeddingProviderError,
    P2EmbeddingSourceInvalidError,
    P2EmbeddingSyncNotReadyError,
    P2KnowledgeEmbeddingService,
)
from app.knowledge_index_repositories import KnowledgeIndexSourceTraceError
from app.schemas import ApiResponse


router = APIRouter(prefix="/api", tags=["P2 Knowledge Embeddings"])


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


@router.post("/knowledge-index/{index_entry_id}/embed", response_model=ApiResponse)
def build_knowledge_embeddings(
    index_entry_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        result = P2KnowledgeEmbeddingService(db).build(index_entry_id)
    except P2EmbeddingIndexNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "KNOWLEDGE_INDEX_NOT_FOUND", "message": "Knowledge Index entry was not found."},
        ) from exc
    except P2EmbeddingKnowledgeAssetNotActiveError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_ASSET_NOT_ACTIVE", "message": "Only active Knowledge Assets can generate embeddings."},
        ) from exc
    except P2EmbeddingIndexNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_INDEX_NOT_READY", "message": str(exc)},
        ) from exc
    except P2EmbeddingSourceInvalidError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_EMBEDDING_SOURCE_INVALID", "message": str(exc)},
        ) from exc
    except P2EmbeddingDimensionError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "KNOWLEDGE_EMBEDDING_DIMENSION_MISMATCH", "message": str(exc)},
        ) from exc
    except P2EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "KNOWLEDGE_EMBEDDING_PROVIDER_FAILED", "message": str(exc)},
        ) from exc
    return ApiResponse(success=True, data=result.model_dump(), requestId=_request_id())


@router.post("/knowledge-index/{index_entry_id}/serve", response_model=ApiResponse)
def serve_knowledge_index(
    index_entry_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        result = P2KnowledgeEmbeddingService(db).serve(index_entry_id)
    except P2EmbeddingIndexNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "KNOWLEDGE_INDEX_NOT_FOUND", "message": "Knowledge Index entry was not found."},
        ) from exc
    except P2EmbeddingKnowledgeAssetNotActiveError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_ASSET_NOT_ACTIVE", "message": "Only active Knowledge Assets can be served."},
        ) from exc
    except P2EmbeddingIndexNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_INDEX_NOT_READY_FOR_SERVING", "message": str(exc)},
        ) from exc
    except P2EmbeddingMissingError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_EMBEDDING_MISSING", "message": str(exc)},
        ) from exc
    except P2EmbeddingFingerprintError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_EMBEDDING_FINGERPRINT_MISMATCH", "message": str(exc)},
        ) from exc
    except P2EmbeddingProfileError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_EMBEDDING_PROFILE_MISMATCH", "message": str(exc)},
        ) from exc
    except P2EmbeddingDimensionError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_EMBEDDING_DIMENSION_MISMATCH", "message": str(exc)},
        ) from exc
    except P2EmbeddingSyncNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_INDEX_SYNC_NOT_READY", "message": str(exc)},
        ) from exc
    except P2EmbeddingSourceInvalidError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_EMBEDDING_SOURCE_INVALID", "message": str(exc)},
        ) from exc
    return ApiResponse(success=True, data=result.model_dump(), requestId=_request_id())

@router.get("/knowledge-embeddings", response_model=ApiResponse)
def get_knowledge_embeddings(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    index_entry_id: str | None = None,
    knowledge_asset_id: str | None = None,
    provider: str | None = None,
    embedding_profile: str | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse:
    try:
        result = list_embeddings(
            db,
            page=page,
            page_size=page_size,
            index_entry_id=index_entry_id,
            knowledge_asset_id=knowledge_asset_id,
            provider=provider,
            embedding_profile=embedding_profile,
        )
    except KnowledgeIndexSourceTraceError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "KNOWLEDGE_EMBEDDING_SOURCE_INVALID", "message": str(exc)},
        ) from exc
    return ApiResponse(success=True, data=result.model_dump(), requestId=_request_id())

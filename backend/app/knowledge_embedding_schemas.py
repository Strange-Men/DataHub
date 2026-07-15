"""P2-M7 schemas for the isolated text-bridge semantic index."""

from pydantic import BaseModel, Field

from app.knowledge_index_schemas import KnowledgeIndexSourceTrace


class P2KnowledgeEmbeddingRecord(BaseModel):
    id: str
    index_entry_id: str
    chunk_id: str
    knowledge_asset_id: str
    chunk_text: str
    provider: str
    model: str
    dimension: int
    embedding_profile: str
    fingerprint: str
    created_at: str
    source_trace: KnowledgeIndexSourceTrace


class P2KnowledgeEmbeddingPagination(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class P2KnowledgeEmbeddingList(BaseModel):
    embeddings: list[P2KnowledgeEmbeddingRecord]
    pagination: P2KnowledgeEmbeddingPagination


class BuildP2KnowledgeEmbeddingsResult(BaseModel):
    index_entry_id: str
    index_status: str
    provider: str
    model: str
    dimension: int
    embedding_profile: str
    created_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    embeddings: list[P2KnowledgeEmbeddingRecord]

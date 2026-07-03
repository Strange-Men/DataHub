from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    message_id: str = Field(min_length=1, max_length=120)
    role: Literal["customer", "agent", "system", "unknown"]
    content: str = Field(min_length=1, max_length=10000)
    timestamp: str = Field(min_length=1, max_length=80)


class Conversation(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=120)
    messages: list[ChatMessage] = Field(min_length=1)


class ImportJsonRequest(BaseModel):
    source_name: str = Field(min_length=1, max_length=160)
    conversations: list[Conversation] = Field(min_length=1)


class SourceBatchMetadata(BaseModel):
    batch_id: str
    source_name: str
    message_count: int
    conversation_count: int
    created_at: str
    status: Literal["raw_imported"]


class CleaningJobMetadata(BaseModel):
    job_id: str
    source_batch_id: str
    sanitized_batch_id: str
    raw_message_count: int
    sanitized_message_count: int
    dropped_message_count: int
    pii_detected_count: int
    status: Literal["completed"]
    created_at: str
    completed_at: str


class SanitizedMessage(BaseModel):
    source_batch_id: str
    conversation_id: str
    message_id: str
    source_message_id: str
    role: Literal["customer", "agent", "system"]
    content: str
    pii_detected: bool
    pii_types: list[str]
    cleaning_notes: list[str]


class SanitizedBatch(BaseModel):
    batch_id: str
    source_batch_id: str
    status: Literal["sanitized"]
    raw_message_count: int
    sanitized_message_count: int
    dropped_message_count: int
    pii_detected_count: int
    created_at: str
    messages: list[SanitizedMessage]


class ApiResponse(BaseModel):
    success: bool
    data: object
    requestId: str

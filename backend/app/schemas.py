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


class ApiResponse(BaseModel):
    success: bool
    data: object
    requestId: str

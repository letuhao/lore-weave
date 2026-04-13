from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ProjectType = Literal["book", "translation", "code", "general"]
ExtractionStatus = Literal["disabled", "building", "paused", "ready", "failed"]
ScopeType = Literal["global", "project", "session", "entity"]


class Project(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    user_id: UUID
    name: str
    description: str
    project_type: ProjectType
    book_id: UUID | None = None
    instructions: str
    extraction_enabled: bool
    extraction_status: ExtractionStatus
    embedding_model: str | None = None
    extraction_config: dict
    last_extracted_at: datetime | None = None
    estimated_cost_usd: Decimal
    actual_cost_usd: Decimal
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    project_type: ProjectType
    book_id: UUID | None = None
    instructions: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    instructions: str | None = None
    book_id: UUID | None = None


class Summary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary_id: UUID
    user_id: UUID
    scope_type: ScopeType
    scope_id: UUID | None = None
    content: str
    token_count: int | None = None
    version: int
    created_at: datetime
    updated_at: datetime

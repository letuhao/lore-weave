from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

ProjectType = Literal["book", "translation", "code", "general"]
ExtractionStatus = Literal["disabled", "building", "paused", "ready", "failed"]
ScopeType = Literal["global", "project", "session", "entity"]

# Names are stripped of surrounding whitespace and must contain at least
# one non-whitespace character. Max 200 chars, chat-service convention.
ProjectName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

# K7 (D-K1-01/02 cleanup): length caps mirrored in Pydantic for early
# 422s and in the DB CHECK constraints (migrate.py) for defense-in-depth.
ProjectDescription = Annotated[str, StringConstraints(max_length=2000)]
ProjectInstructions = Annotated[str, StringConstraints(max_length=20000)]
SummaryContent = Annotated[str, StringConstraints(max_length=50000)]


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
    name: ProjectName
    description: ProjectDescription = ""
    project_type: ProjectType
    book_id: UUID | None = None
    instructions: ProjectInstructions = ""


class ProjectUpdate(BaseModel):
    """Partial update. Field semantics:

    - `name`, `description`, `instructions`: omit to leave unchanged. Setting
      explicitly to None is rejected (these columns are NOT NULL). Passing
      a value replaces the current value.
    - `book_id`: omit to leave unchanged. Setting to None explicitly CLEARS
      the book link. Setting to a UUID sets a new link.
    """

    name: ProjectName | None = None
    description: ProjectDescription | None = None
    instructions: ProjectInstructions | None = None
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

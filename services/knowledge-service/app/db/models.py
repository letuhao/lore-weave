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
    # K12.3 column surfaced for K18.3 / D-K18.3-01 ingestion; the
    # passage_ingester + L3 selector need the dim at call time.
    embedding_dimension: int | None = None
    extraction_config: dict
    last_extracted_at: datetime | None = None
    estimated_cost_usd: Decimal
    actual_cost_usd: Decimal
    is_archived: bool
    version: int  # D-K8-03: bumped on every non-empty PATCH.
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
    - `is_archived`: restore-only. Set to `false` to un-archive. Setting
      to `true` is rejected at the router with 422 — archive uses the
      dedicated `POST /archive` endpoint which has the 404-oracle
      hardening (does not leak whether a project exists). K-CLEAN-3.
    - `embedding_model` (K12.4): omit to leave unchanged. Set to a
      known model name (e.g. "bge-m3", "text-embedding-3-small") to
      switch the project's vector space. Set to None to clear. The
      repo auto-derives `embedding_dimension` from the model name
      via the `EMBEDDING_MODEL_TO_DIM` map — callers never pass the
      dimension directly.
    """

    name: ProjectName | None = None
    description: ProjectDescription | None = None
    instructions: ProjectInstructions | None = None
    book_id: UUID | None = None
    is_archived: bool | None = None
    embedding_model: str | None = None


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


# D-K8-01: append-only history row captured by the repo on every
# successful summary update. `edit_source` is the rollback audit
# trail — rollback operations write 'rollback' so the UI can
# distinguish them from user-typed history entries.
EditSource = Literal["manual", "rollback", "regen"]


class SummaryVersion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: UUID
    summary_id: UUID
    user_id: UUID
    version: int
    content: str
    token_count: int | None = None
    created_at: datetime
    edit_source: EditSource

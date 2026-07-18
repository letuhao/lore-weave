"""Phase B sub-session C2 — public event-correction endpoints.

POST  /v1/knowledge/events        — author a new timeline event (D-KG-EVENT-CREATE-ROUTE)
PATCH /v1/knowledge/events/{id}   — edit title/summary/time_cue/event_date_iso
DELETE /v1/knowledge/events/{id}  — soft-archive (user "delete")

Each emits a `knowledge.event_corrected` event for the corrections log. PATCH
uses the same optimistic-concurrency If-Match/428/412 contract as entities;
archive is idempotent + If-Match-free (one-way flag flip), mirroring the entity
archive. Cross-user/missing → 404 (KSA §6.4). Create mirrors the T2.5 entity
create: user-authored (`source_type='manual'`, confidence 1.0), idempotent on
(user, project, chapter, title) via `merge_event`, and written under the JWT
`user_id` so a caller can only ever author in their own scope.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.events import (
    Event,
    archive_event,
    get_event,
    merge_event,
    update_event_fields,
)
from app.db.repositories import VersionMismatchError
from app.events.outbox_emit import (
    EVENT_CORRECTED,
    emit_correction,
    event_correction_payload,
    event_snapshot_dict,
)
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)


# Local If-Match/ETag helpers — duplicated per the codebase convention
# (entities.py / projects.py / summaries.py keep these inline to avoid a
# cross-cutting import dependency).
def _parse_if_match(header_value: str | None) -> int | None:
    if header_value is None:
        return None
    s = header_value.strip()
    if s.startswith("W/"):
        s = s[2:].strip()
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        try:
            return int(s[1:-1])
        except ValueError:
            pass
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="If-Match header must be a weak ETag with an integer version",
    )


def _etag(version: int) -> str:
    return f'W/"{version}"'


events_router = APIRouter(
    prefix="/v1/knowledge",
    tags=["events"],
    dependencies=[Depends(get_current_user)],
)


class EventCreate(BaseModel):
    """POST body — author a new timeline event (D-KG-EVENT-CREATE-ROUTE).

    ``project_id`` scopes the event to a book's knowledge graph (a tag on the
    caller's own node, never a cross-tenant handle). ``chapter_id`` optionally
    anchors it to a chapter (drives narrative event_order + the spoiler cutoff);
    ``participants`` are the display names the event involves — passing the
    focused character's name is what makes the event appear on that character's
    arc. Idempotent: the same (project, chapter, title) returns the existing
    node (``merge_event`` dedups on a canonical hash), so re-adding is a no-op
    rather than a duplicate.
    """

    project_id: UUID
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=4000)
    time_cue: str | None = Field(default=None, max_length=300)
    event_date_iso: str | None = Field(default=None, max_length=20)
    chapter_id: str | None = Field(default=None, max_length=200)
    participants: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def _validate(self) -> "EventCreate":
        if not self.title.strip():
            raise ValueError("title must not be blank")
        return self


@events_router.post(
    "/events",
    response_model=Event,
    status_code=status.HTTP_201_CREATED,
)
async def create_event_endpoint(
    body: EventCreate,
    user_id: UUID = Depends(get_current_user),
) -> Event:
    """Author a new user-created timeline event (the Character-Arc "+ Add event").

    Multi-tenant: the node is written under the JWT ``user_id`` (threaded into
    ``merge_event``'s Cypher `WHERE e.user_id = $user_id`), so a caller can only
    ever author in their own scope. ``source_type='manual'`` + confidence 1.0
    mark it user-asserted (distinct from extraction's `book_content`). Idempotent
    on (user, project, chapter, title). Emits a `knowledge.event_corrected`
    correction (op=create, before=null) for the corrections log.
    """
    participants = [p.strip() for p in body.participants if p and p.strip()]
    async with neo4j_session() as session:
        event = await merge_event(
            session,
            user_id=str(user_id),
            project_id=str(body.project_id),
            title=body.title.strip(),
            summary=body.summary,
            chapter_id=body.chapter_id,
            event_date_iso=body.event_date_iso,
            time_cue=body.time_cue,
            participants=participants,
            source_type="manual",
            confidence=1.0,
            provenance="human_authored",
        )
    await emit_correction(
        event_type=EVENT_CORRECTED,
        aggregate_id=event.id,
        payload=event_correction_payload(
            user_id=str(user_id),
            project_id=event.project_id,
            book_id=None,
            target_id=event.id,
            op="create",
            before=None,
            after=event_snapshot_dict(
                title=event.title, summary=event.summary, time_cue=event.time_cue,
                event_date_iso=event.event_date_iso, participants=event.participants,
            ),
            source_chapter=event.chapter_id,
            actor_id=str(user_id),
        ),
    )
    logger.info(
        "user created event user_id=%s project_id=%s event_id=%s",
        user_id, body.project_id, event.id,
    )
    return event


class EventUpdate(BaseModel):
    """PATCH body. At least one field required. None = leave unchanged."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=4000)
    time_cue: str | None = Field(default=None, max_length=300)
    event_date_iso: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _at_least_one(self) -> "EventUpdate":
        if (
            self.title is None
            and self.summary is None
            and self.time_cue is None
            and self.event_date_iso is None
        ):
            raise ValueError(
                "at least one of title / summary / time_cue / event_date_iso must be provided"
            )
        return self


@events_router.patch("/events/{event_id}", response_model=Event)
async def patch_event(
    body: EventUpdate,
    response: Response,
    event_id: str = Path(min_length=1, max_length=200),
    if_match: str | None = Header(default=None, alias="If-Match"),
    user_id: UUID = Depends(get_current_user),
) -> Event:
    """Edit an event's display fields with optimistic concurrency (mirrors
    entity PATCH). 428 without If-Match; 412 on version mismatch (with the
    current event body + refreshed ETag); 404 cross-user/missing."""
    expected_version = _parse_if_match(if_match)
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="If-Match header required — GET the event first to obtain an ETag",
        )
    async with neo4j_session() as session:
        try:
            updated, before = await update_event_fields(
                session,
                user_id=str(user_id),
                event_id=event_id,
                title=body.title,
                summary=body.summary,
                time_cue=body.time_cue,
                event_date_iso=body.event_date_iso,
                expected_version=expected_version,
            )
        except VersionMismatchError as exc:
            current: Event = exc.current
            return JSONResponse(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                content=current.model_dump(mode="json"),
                headers={"ETag": _etag(current.version)},
            )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")

    await emit_correction(
        event_type=EVENT_CORRECTED,
        aggregate_id=event_id,
        payload=event_correction_payload(
            user_id=str(user_id),
            project_id=updated.project_id,
            book_id=None,
            target_id=event_id,
            op="update",
            before=(
                event_snapshot_dict(
                    title=before.get("title"), summary=before.get("summary"),
                    time_cue=before.get("time_cue"), event_date_iso=before.get("event_date_iso"),
                    participants=before.get("participants"),
                )
                if before
                else None
            ),
            after=event_snapshot_dict(
                title=updated.title, summary=updated.summary, time_cue=updated.time_cue,
                event_date_iso=updated.event_date_iso, participants=updated.participants,
            ),
            source_chapter=updated.chapter_id,
            actor_id=str(user_id),
        ),
    )
    logger.info("user updated event user_id=%s event_id=%s version=%d", user_id, event_id, updated.version)
    response.headers["ETag"] = _etag(updated.version)
    return updated


@events_router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_event_endpoint(
    event_id: str = Path(min_length=1, max_length=200),
    user_id: UUID = Depends(get_current_user),
) -> None:
    """Soft-archive an event (user "delete"). Idempotent. Emits a
    `spurious-drop` correction (after=null). `before` read before archiving
    (op=delete → low-stakes)."""
    async with neo4j_session() as session:
        before_event = await get_event(session, user_id=str(user_id), event_id=event_id)
        result = await archive_event(session, user_id=str(user_id), event_id=event_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    before = (
        event_snapshot_dict(
            title=before_event.title, summary=before_event.summary,
            time_cue=before_event.time_cue, event_date_iso=before_event.event_date_iso,
            participants=before_event.participants,
        )
        if before_event is not None
        else None
    )
    await emit_correction(
        event_type=EVENT_CORRECTED,
        aggregate_id=event_id,
        payload=event_correction_payload(
            user_id=str(user_id),
            project_id=result.project_id,
            book_id=None,
            target_id=event_id,
            op="delete",
            before=before,
            after=None,
            source_chapter=result.chapter_id,
            actor_id=str(user_id),
        ),
    )
    logger.info("user archived event user_id=%s event_id=%s", user_id, event_id)

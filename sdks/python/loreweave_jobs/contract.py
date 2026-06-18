"""Canonical job contract (Unified Job Control Plane, L0).

The single shape every service emits and the P2 projection stores. Shared by every
Python service + (mirrored in) the FE. **No ``provider_job_id``** (H2): a domain job has
1:N provider LLM jobs; live-cancel is always domain-level, so the control plane never
addresses a provider job — it routes control to the owning service, which aborts its own
in-flight provider jobs. Provider-job linkage stays internal per service.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


# ── stream / outbox routing constants ────────────────────────────────────────────
# worker-infra's outbox relay routes a row to ``loreweave:events:<aggregate_type>``
# (see services/worker-infra/internal/tasks/outbox_relay.go). So a job lifecycle event
# written to the outbox with aggregate_type=JOBS_AGGREGATE_TYPE lands on JOBS_STREAM.
JOBS_AGGREGATE_TYPE = "jobs"
JOBS_STREAM = "loreweave:events:jobs"

# The existing provider-terminal stream the relay XADDs on every LLM job's terminal
# transition — the 4 terminal-event consumers (worker-ai / translation / video-gen /
# learning-judge) read THIS; the SDK base consumer defaults its ``stream`` to it.
TERMINAL_STREAM = "loreweave:events:llm_job_terminal"


class JobStatus(str, Enum):
    """The canonical lifecycle status. Service-native sub-states go in
    ``JobRecord.detail_status`` (M2), never here."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def is_terminal(cls, status: "JobStatus | str") -> bool:
        s = status.value if isinstance(status, JobStatus) else str(status)
        return s in _TERMINAL_VALUES


#: The terminal statuses — once here, no control cap applies and the projection stops
#: expecting updates. The single source of truth (no parallel set to drift).
TERMINAL: frozenset[JobStatus] = frozenset(
    {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
)
_TERMINAL_VALUES = frozenset(s.value for s in TERMINAL)


class ControlCap(str, Enum):
    """A control action valid for a job in its CURRENT status (state-aware — M5).
    Computed per-job by the owning service / projection, not a static per-kind list."""

    CANCEL = "cancel"
    PAUSE = "pause"
    RESUME = "resume"
    RETRY = "retry"  # re-submit a FAILED job as a fresh job (new job_id) — P4


@dataclass
class JobRecord:
    """The L0 canonical job shape. PK = ``(service, job_id)``.

    ``progress`` is ``{"done": int, "total": int}`` or ``None`` (single-call / streaming
    jobs — the GUI renders null-safe). ``control_caps`` is state-aware: what is valid for
    THIS job right now. ``error`` is ``{"code", "message"}`` or ``None``.
    """

    service: str
    job_id: str
    owner_user_id: str
    kind: str
    status: JobStatus
    parent_job_id: Optional[str] = None
    detail_status: Optional[str] = None
    progress: Optional[dict[str, int]] = None
    control_caps: list[ControlCap] = field(default_factory=list)
    title: Optional[str] = None
    error: Optional[dict[str, str]] = None
    # P4 usage/observability fields (all nullable — older producers + single-call jobs
    # leave them None; the GUI renders null-safe). ``model`` is the RESOLVED model NAME
    # (not the BYOK ref-UUID); ``cost_usd`` is reliable (inline on the domain row);
    # ``tokens_in``/``tokens_out`` are best-effort (scattered/per-unit upstream).
    # ``params`` is a whitelisted dynamic key-value (model now, effort later — no schema
    # change to add a key) — NEVER the raw prompt / secret blob.
    model: Optional[str] = None
    cost_usd: Optional[float] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    params: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None  # ISO-8601 UTC
    updated_at: Optional[str] = None  # ISO-8601 UTC

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict (enums → their string values)."""
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, JobStatus) else self.status
        d["control_caps"] = [
            c.value if isinstance(c, ControlCap) else c for c in self.control_caps
        ]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobRecord":
        return cls(
            service=d["service"],
            job_id=str(d["job_id"]),
            owner_user_id=str(d["owner_user_id"]),
            kind=d["kind"],
            status=JobStatus(d["status"]),
            parent_job_id=(str(d["parent_job_id"]) if d.get("parent_job_id") else None),
            detail_status=d.get("detail_status"),
            progress=d.get("progress"),
            control_caps=[ControlCap(c) for c in (d.get("control_caps") or [])],
            title=d.get("title"),
            error=d.get("error"),
            model=d.get("model"),
            cost_usd=d.get("cost_usd"),
            tokens_in=d.get("tokens_in"),
            tokens_out=d.get("tokens_out"),
            params=d.get("params"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
        )


@dataclass
class JobEvent:
    """The lifecycle event written to the outbox → ``loreweave:events:jobs`` (P2 input).

    Carries only what the projection needs to upsert a ``JobRecord``. Dedup key is
    ``(service, job_id, status)`` (the projection upserts on it; the relay also dedups
    re-emission via ``outbox_id``)."""

    service: str
    job_id: str
    owner_user_id: str
    kind: str
    status: JobStatus
    parent_job_id: Optional[str] = None
    detail_status: Optional[str] = None
    progress: Optional[dict[str, int]] = None
    title: Optional[str] = None
    error: Optional[dict[str, str]] = None
    # P4 usage/observability (all nullable — see JobRecord). A producer emits the
    # cumulative cost/tokens it has so far; the projection COALESCE-merges so a later
    # event without them never wipes the accumulated value. ``params`` = whitelisted
    # subset only, never the raw prompt/secret blob.
    model: Optional[str] = None
    cost_usd: Optional[float] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    params: Optional[dict[str, Any]] = None
    occurred_at: Optional[str] = None  # ISO-8601 UTC; set by emit if omitted

    def to_payload(self) -> dict[str, Any]:
        """The JSON payload stored in ``outbox_events.payload`` and shipped on the stream."""
        return {
            "service": self.service,
            "job_id": self.job_id,
            "owner_user_id": self.owner_user_id,
            "kind": self.kind,
            "status": self.status.value if isinstance(self.status, JobStatus) else self.status,
            "parent_job_id": self.parent_job_id,
            "detail_status": self.detail_status,
            "progress": self.progress,
            "title": self.title,
            "error": self.error,
            "model": self.model,
            "cost_usd": self.cost_usd,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "params": self.params,
            "occurred_at": self.occurred_at,
        }

    @classmethod
    def from_payload(cls, d: dict[str, Any]) -> "JobEvent":
        return cls(
            service=d["service"],
            job_id=str(d["job_id"]),
            owner_user_id=str(d["owner_user_id"]),
            kind=d["kind"],
            status=JobStatus(d["status"]),
            parent_job_id=(str(d["parent_job_id"]) if d.get("parent_job_id") else None),
            detail_status=d.get("detail_status"),
            progress=d.get("progress"),
            title=d.get("title"),
            error=d.get("error"),
            model=d.get("model"),
            cost_usd=d.get("cost_usd"),
            tokens_in=d.get("tokens_in"),
            tokens_out=d.get("tokens_out"),
            params=d.get("params"),
            occurred_at=d.get("occurred_at"),
        )

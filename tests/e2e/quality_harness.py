"""Reusable E2E harness for the composition QUALITY endpoints.

Drives the REAL `/v1/composition/*` quality surfaces through the api-gateway with the
**claude-test** account (which owns the POC book + BYOK models), discovering a real
target black-box via the API. Use this instead of hand-fed live-smoke scripts: it
exercises the full request → worker → result path (auth, outline/plan render, chapter
assembly, canon) that a crafted-input smoke skips — exactly the surface that hid the
`_render_outline_plan` ordering bug the Q3 smoke missed.

Two consumers:
- `tests/e2e/test_compose_quality_e2e.py` — asserts each endpoint's full path works.
- future evaluation scripts — import `resolve_target` + the driver fns to run a tool
  over the real book and collect its structured output as data.

Everything is env-overridable (E2E_GATEWAY_URL / E2E_TEST_EMAIL / E2E_TEST_PASSWORD)
so it runs against any stack; defaults target the local dev gateway (:3123).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import httpx

GATEWAY_URL = os.environ.get("E2E_GATEWAY_URL", "http://localhost:3123")
TEST_EMAIL = os.environ.get("E2E_TEST_EMAIL", "claude-test@loreweave.dev")
TEST_PASSWORD = os.environ.get("E2E_TEST_PASSWORD", "Claude@Test2026")

TERMINAL = {"completed", "failed", "cancelled"}


@dataclass
class QualityTarget:
    """A real, drivable target resolved from the API: a work (project) + one of its
    chapters + a chat-capable BYOK model."""

    project_id: str
    book_id: str
    chapter_id: str
    model_ref: str
    book_title: str = ""
    model_source: str = "user_model"
    source_language: str = "auto"


async def login(client: httpx.AsyncClient, *, email: str = TEST_EMAIL,
                password: str = TEST_PASSWORD) -> str:
    """POST /v1/auth/login → bearer access token."""
    r = await client.post("/v1/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def poll_job(client: httpx.AsyncClient, job_id: str, *, headers: dict[str, str],
                   max_polls: int = 240, interval: float = 2.0) -> dict:
    """Poll GET /v1/composition/jobs/{id} until a terminal status; return the job dict.
    Raises TimeoutError if it never terminates (the worker's LLM latency is absorbed by
    the poll loop, not the per-request timeout)."""
    for _ in range(max_polls):
        r = await client.get(f"/v1/composition/jobs/{job_id}", headers=headers)
        r.raise_for_status()
        job = r.json()
        if job.get("status") in TERMINAL:
            return job
        await asyncio.sleep(interval)
    raise TimeoutError(f"job {job_id} did not reach a terminal status in {max_polls} polls")


def _chapter_is_drafted(ch: dict) -> bool:
    """A chapter has prose to analyze iff a draft revision exists."""
    return (ch.get("draft_revision_count") or 0) > 0


async def resolve_target(client: httpx.AsyncClient, *, headers: dict[str, str],
                         prefer_title: str = "POC", min_chapters: int = 1) -> QualityTarget:
    """Black-box discovery of a DRIVABLE target through the gateway: books → work →
    a DRAFTED chapter → a chat model. Iterates candidate books (preferring a titled
    `prefer_title` book with the most chapters) and picks the first whose chapters
    include a drafted one — so the quality endpoints get real prose, not an empty book
    (a per-chapter endpoint on an undrafted chapter is a 400, and promise-coverage on an
    undrafted book is EMPTY_BOOK). Raises RuntimeError with a clear message if nothing
    drivable exists, so the E2E skips loudly rather than green-on-nothing."""
    r = await client.get("/v1/books?limit=100", headers=headers)
    r.raise_for_status()
    books = [b for b in r.json().get("items", []) if (b.get("chapter_count") or 0) >= min_chapters]
    if not books:
        raise RuntimeError("resolve_target: the account has no book with chapters")
    books.sort(
        key=lambda b: (prefer_title.lower() in (b.get("title") or "").lower(),
                       b.get("chapter_count") or 0),
        reverse=True,
    )

    r = await client.get("/v1/model-registry/user-models?capability=chat&limit=1", headers=headers)
    r.raise_for_status()
    models = r.json().get("items", [])
    if not models:
        raise RuntimeError("resolve_target: the account has no chat-capable model")
    model_ref = models[0]["user_model_id"]

    for book in books:
        book_id = book["book_id"]
        r = await client.get(f"/v1/composition/books/{book_id}/work", headers=headers)
        r.raise_for_status()
        wr = r.json()
        work = wr.get("work") or {}
        if wr.get("status") != "found" or not work.get("project_id"):
            continue  # no composition work for this book — not drivable
        r = await client.get(f"/v1/books/{book_id}/chapters?limit=200", headers=headers)
        r.raise_for_status()
        chapters = r.json().get("items", [])
        drafted = [c for c in chapters if _chapter_is_drafted(c)]
        if not drafted:
            continue  # book has no prose to analyze — try the next candidate
        drafted.sort(key=lambda c: c.get("sort_order") or 0)
        return QualityTarget(
            project_id=work["project_id"], book_id=book_id,
            chapter_id=drafted[0]["chapter_id"], model_ref=model_ref,
            book_title=book.get("title") or "",
            source_language=(work.get("settings") or {}).get("source_language")
            or book.get("original_language") or "auto",
        )

    raise RuntimeError(
        "resolve_target: no book with a composition work AND a drafted chapter "
        "(drive the POC pipeline first, or draft a chapter)")


async def drive(client: httpx.AsyncClient, path: str, project_id: str, body: dict, *,
                headers: dict[str, str]) -> dict:
    """POST a quality endpoint under /v1/composition/works/{project_id}{path}. On a
    202 (worker enabled) poll the job to terminal and return `job.result`; on a 200
    (inline) return the body. Raises on a failed job."""
    r = await client.post(f"/v1/composition/works/{project_id}{path}", json=body, headers=headers)
    r.raise_for_status()
    data = r.json()
    if r.status_code == 202 and data.get("job_id"):
        job = await poll_job(client, data["job_id"], headers=headers)
        if job.get("status") != "completed":
            raise RuntimeError(f"{path} job {job.get('status')}: {job.get('error')}")
        return job.get("result") or {}
    return data


async def propose_self_heal(client, target: QualityTarget, *, headers, rerank: bool = False) -> dict:
    return await drive(client, "/self-heal/propose", target.project_id, {
        "chapter_id": target.chapter_id, "model_source": target.model_source,
        "model_ref": target.model_ref, "prefilter": True, "rerank": rerank,
    }, headers=headers)


async def quality_report(client, target: QualityTarget, *, headers) -> dict:
    """Returns the inner report `{critic, promises}` (the worker wraps it in
    `{report, chapter_id, draft_version}`)."""
    res = await drive(client, "/quality-report", target.project_id, {
        "chapter_id": target.chapter_id, "model_source": target.model_source,
        "model_ref": target.model_ref,
    }, headers=headers)
    return res.get("report", res)


async def promise_coverage(client, target: QualityTarget, *, headers) -> dict:
    """Returns the inner coverage dict (the worker wraps it in `{coverage, chapters}`)."""
    res = await drive(client, "/promise-coverage", target.project_id, {
        "model_source": target.model_source, "model_ref": target.model_ref,
    }, headers=headers)
    return res.get("coverage", res)

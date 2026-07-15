"""S-TRANSL — MCP server facade for translation-service (MCP fan-out 2026-06-20).

Mounts at ``/mcp`` on the existing FastAPI app (``app/main.py``) and exposes the
translation pipeline + job control as MCP tools, via the shared Python kit
``loreweave_mcp`` (C-KIT-PY). Prefix ``translation_`` (the gateway DROPS any tool
whose name doesn't match its provider prefix). Scope = **book** — every tool
authorizes the envelope caller's ownership of the target book via the kit's
``require_book_owner`` (grant resolved through book-service, the single authority).

Tier model (C-TOOL ``_meta.tier``):
  - **R** (read) — `translation_coverage`, `translation_segment_status`,
    `translation_list_versions`, `translation_job_status`.
  - **A** (auto-apply + Undo) — `translation_set_active_version`,
    `translation_save_edited_version`, `translation_patch_block`,
    `translation_update_settings`; each returns `_meta.undo_hint`.
  - **W** (priced → confirm) — `translation_start_job`,
    `translation_retranslate_dirty`. These do NOT spend: they ESTIMATE the cost
    (HIGH#1) and MINT a confirm token; the only start path is the token-gated
    `/v1/translation/actions/confirm` route, which RE-PRICES at execution (H14).
  - **A/W** — `job_control(action)`: cancel/pause = A; resume/retry = W (re-spend
    → re-confirm). Forwards to translation-service's OWN control cores.

Identity comes ONLY from the envelope (`build_tool_context`: X-Internal-Token
constant-time check, then X-User-Id) — NEVER a tool arg. Arg models extend
`ForbidExtra`. 403/404 collapse to the uniform not-accessible error (H13).

Job *reads* (`jobs_list`/`jobs_summary`/`jobs_get`) belong to S-JOBS — NOT here.
`translation_job_status` is a translation-specific job read (its own jobs table),
distinct from the cross-service job-read SSOT.

Dual-run: the bespoke `/v1/translation` REST API is NOT removed.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal
from uuid import UUID

from mcp.server.fastmcp import Context as MCPContext
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

from loreweave_mcp import (
    ForbidExtra,
    ToolContext,
    apply_response_contract,
    build_tool_context,
    make_stateless_fastmcp,
    mint_confirm_token,
    require_book_owner,
    require_meta,
    uniform_not_accessible,
)

from ..config import settings
from ..database import get_pool
from ..grant_client import GrantLevel, get_grant_client
from ..grant_deps import clamp_effort_to_grant
from ..effective_settings import resolve_effective_settings
from ..mcp.estimate import SCOPE_CHAPTERS, SCOPE_DIRTY, estimate_job_cost
from ..routers.actions import (
    DESC_RETRANSLATE_DIRTY,
    DESC_START_EXTRACTION,
    DESC_START_JOB,
)
from ..workers.extraction_prompt import estimate_extraction_cost
from ..workers.glossary_client import fetch_extraction_profile

logger = logging.getLogger(__name__)

__all__ = ["mcp_server", "build_mcp_app"]

mcp_server = make_stateless_fastmcp("translation")


# ── W0 #4b — model-directed validation errors ─────────────────────────────────
# FastMCP surfaces a pydantic arg-validation failure as the RAW multi-line dump
# (with the errors.pydantic.dev URL) — noise a model cannot act on. Intercept at
# the per-server tool-dispatch chokepoint and rewrite to a ONE-LINE directive.
# Mirrors jobs/knowledge-service; the loreweave_mcp kit will absorb the shared
# copy later (kit is outside the W0 change surface).


def _validation_directive(tool_name: str, exc: ValidationError) -> str:
    """One line: every failing arg with pydantic's expectation + the sent shape."""
    parts = []
    errs = exc.errors(include_url=False)
    for err in errs[:3]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "arguments"
        msg = err.get("msg", "invalid value")
        sent = err.get("input")
        parts.append(f"`{loc}`: {msg} (you sent a {type(sent).__name__})")
    if len(errs) > 3:
        parts.append(f"(+{len(errs) - 3} more)")
    return (
        f"invalid arguments for {tool_name} — "
        + "; ".join(parts)
        + ". Fix the argument and call the tool again."
    )


def _install_validation_error_rewriter(server) -> None:
    """Wrap the FastMCP tool manager's dispatch so a ToolError caused by a
    pydantic ValidationError re-raises with the one-line directive instead of
    the raw dump. Non-validation errors pass through untouched."""
    manager = server._tool_manager
    original = manager.call_tool

    async def call_tool(name, arguments, *args, **kwargs):
        try:
            return await original(name, arguments, *args, **kwargs)
        except ToolError as e:
            cause = e.__cause__
            if isinstance(cause, ValidationError):
                raise ToolError(_validation_directive(name, cause)) from cause
            raise

    manager.call_tool = call_tool


_install_validation_error_rewriter(mcp_server)


def _single_value(arg_name: str, value: str | list[str] | None) -> str | None:
    """W0 #3 — models routinely send `[\"<uuid>\"]` for single-valued args.
    Accept a one-element list (unwrap it); reject a multi-element list with a
    directive naming the fix. None/str pass through."""
    if isinstance(value, list):
        if len(value) == 1:
            return value[0]
        raise ValueError(
            f"`{arg_name}` must be a single value, not a list of {len(value)} — "
            f"pick one and call the tool again"
        )
    return value


# Tier-W confirm-token TTL — the user has time to read the cost + confirm.
_CONFIRM_TTL_S = 600


# ── Ownership guard (book scope) ──────────────────────────────────────────────
# The kit's require_book_owner needs an async resolver `(book_id, user_id) -> int`
# returning the caller's grant level. Adapt the translation grant client (which
# returns a GrantLevel IntEnum); the kit compares `>= level`, so the int value of
# the enum is exactly what it wants. EDIT (2) is required to act on a book.


async def _grant_resolver(book_id: UUID, user_id: UUID) -> int:
    try:
        lvl = await get_grant_client().resolve_grant(book_id, user_id)
    except Exception:  # noqa: BLE001 — fail-closed: any resolver error → no access
        return 0
    return int(lvl)


_require_view = require_book_owner(_grant_resolver, int(GrantLevel.VIEW))
_require_edit = require_book_owner(_grant_resolver, int(GrantLevel.EDIT))


def _ctx(ctx: MCPContext) -> ToolContext:
    return build_tool_context(ctx, settings.internal_service_token)


# ── Tier R — reads ────────────────────────────────────────────────────────────


@mcp_server.tool(
    name="translation_coverage",
    description=(
        "Get a book's translation coverage matrix: per chapter × language, how many "
        "versions exist, the latest status, whether a version is active, and whether "
        "it's glossary-stale. Use this to answer 'how much of my book is translated' "
        "or 'what languages does this book have'. The `untranslated_chapter_ids` field "
        "lists chapters that have NO translation yet — these are exactly what a "
        "'translate what's new/changed' pass must cover. Book-scoped (you must have access)."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["coverage", "translation progress", "how much translated",
                  "translation matrix", "languages translated"],
        tool_name="translation_coverage",
    ),
)
async def translation_coverage(
    ctx: MCPContext,
    book_id: Annotated[str, "The book's id (UUID)."],
) -> dict:
    # @small_return: a coverage matrix of per-(chapter × language) SCALAR counts
    # (version_count, latest/active version_num, latest_status, has_active) grouped
    # into a nested {chapter -> {language -> {...}}} map. No heavy body/text field
    # exists to drop at summary — every cell is already reference-sized, and the
    # nested shape isn't the flat list the L1/L2 contract projects. Exempt.
    tc = _ctx(ctx)
    bid = _uuid(book_id)
    await _require_view(tc, bid)
    db = get_pool()
    rows = await db.fetch(_COVERAGE_SQL, bid)
    # D-S05-COVERAGE-MISMATCH — _COVERAGE_SQL derives its chapter list from chapter_translations,
    # so a NEVER-translated chapter is invisible. Fetch the book's REAL chapters (cross-service)
    # so coverage surfaces the untranslated ones — the whole point of a "translate what's new" pass.
    from ..book_client import list_chapter_ids
    all_chapter_ids = await list_chapter_ids(book_id)
    return _coverage_payload(rows, bid, all_chapter_ids)


@mcp_server.tool(
    name="translation_segment_status",
    description=(
        "Get the per-segment translation status of one chapter in a target language: "
        "which segments are translated, which are dirty (source changed), which are "
        "glossary-stale, and which need re-translation. Use this before a "
        "retranslate-dirty to see what would be re-done. Book-scoped."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["segment status", "dirty segments", "what changed",
                  "which segments are outdated", "stale segments"],
        tool_name="translation_segment_status",
    ),
)
async def translation_segment_status(
    ctx: MCPContext,
    book_id: Annotated[str, "The book's id (UUID) the chapter belongs to."],
    chapter_id: Annotated[str, "The chapter's id (UUID)."],
    target_language: Annotated[str, "The target language code (e.g. 'en')."],
) -> dict:
    # @small_return: each per-segment item is a fixed set of SCALAR status flags +
    # block indices (segment_index, start/end_block_index, token_estimate,
    # translated/dirty/stale/needs bools, translated_at) — NO source/translated text
    # body is carried. There is no heavy field to drop at summary; every field is
    # load-bearing for the "what would re-translate" answer, and dirty_count/
    # needs_count already summarize the set. Exempt.
    tc = _ctx(ctx)
    await _require_view(tc, _uuid(book_id))
    from ..workers.segment_status import compute_segment_status
    items = await compute_segment_status(get_pool(), _uuid(chapter_id), target_language)
    return {
        "chapter_id": chapter_id,
        "target_language": target_language,
        "segments": items,
        "dirty_count": sum(1 for it in items if it["dirty"]),
        "needs_count": sum(1 for it in items if it["needs"]),
    }


@mcp_server.tool(
    name="translation_list_versions",
    description=(
        "List all translation versions of a chapter, grouped by language — each with "
        "its version number, status, whether it's the active (published) version, the "
        "model used, token counts, and whether it was human-authored. Use this to "
        "inspect or pick a version to set active. Pass `detail=summary` for a "
        "lightweight list that keeps only each version's id/number/status/active flag "
        "and drops the heavy per-version metadata (model refs, job id, token counts, "
        "authored_by) — default `full`. Book-scoped."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["versions", "translation versions", "list translations",
                  "chapter versions", "which version active"],
        tool_name="translation_list_versions",
    ),
)
async def translation_list_versions(
    ctx: MCPContext,
    book_id: Annotated[str, "The book's id (UUID) the chapter belongs to."],
    chapter_id: Annotated[str, "The chapter's id (UUID)."],
    detail: Annotated[
        Literal["summary", "full"],
        "summary = id/version_num/target_language/status/is_active only (drops model "
        "refs, job id, token counts, authored_by); full = every field.",
    ] = "full",
    limit: Annotated[
        int | None,
        "Coarse cap on versions returned (a flat prefix across all languages; "
        "`truncated` reports how many were dropped). Omit for all.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    await _require_view(tc, _uuid(book_id))
    db = get_pool()
    rows = await db.fetch(_VERSIONS_SQL, _uuid(chapter_id))
    projected, meta = apply_response_contract(
        _version_rows(rows), ref_fields=_VERSION_REF_FIELDS, detail=detail, limit=limit,
    )
    return {
        "chapter_id": chapter_id,
        "languages": _group_versions(projected),
        **meta,
    }


# L1/L2 reference-first (Context Budget Law §6b): at detail=summary a per-chapter
# progress row collapses to these fields — the heavy `error_message` (a full provider
# traceback, per chapter) + token counts are dropped; the overall job-level error stays.
_JOB_STATUS_CHAPTER_REF_FIELDS = ("chapter_id", "status", "version_num")


@mcp_server.tool(
    name="translation_job_status",
    description=(
        "Get the status of a translation job by its id: overall status, per-chapter "
        "progress, and any error. This is the translation-service view of a job; for "
        "a cross-service job list use the jobs tools. Pass `detail=summary` for a "
        "lightweight per-chapter list (chapter_id/status/version_num only) that drops "
        "the heavy per-chapter error_message tracebacks + token counts — default "
        "`full`. Book-scoped (via the job's book)."
    ),
    meta=require_meta(
        "R", "book",
        synonyms=["translation job", "job status", "is my translation done",
                  "translation progress"],
        tool_name="translation_job_status",
    ),
)
async def translation_job_status(
    ctx: MCPContext,
    job_id: Annotated[str, "The translation job's id (UUID)."],
    detail: Annotated[
        Literal["summary", "full"],
        "summary = per-chapter chapter_id/status/version_num only (drops the heavy "
        "error_message + token counts); full = every field.",
    ] = "full",
    limit: Annotated[
        int | None,
        "Coarse cap on the per-chapter rows returned (`truncated` reports how many "
        "were dropped). Omit for all chapters.",
    ] = None,
) -> dict:
    tc = _ctx(ctx)
    db = get_pool()
    row = await db.fetchrow(
        "SELECT * FROM translation_jobs WHERE job_id=$1", _uuid(job_id)
    )
    if not row:
        raise uniform_not_accessible()
    # Authorize via the job's book — a non-grantee is indistinguishable from a
    # missing job (the guard raises the SAME uniform error H13).
    await _require_view(tc, row["book_id"])
    chapter_rows = await db.fetch(
        "SELECT chapter_id, status, version_num, input_tokens, output_tokens, "
        "error_message FROM chapter_translations WHERE job_id=$1 ORDER BY created_at",
        _uuid(job_id),
    )
    chapter_items = [
        {
            "chapter_id": str(r["chapter_id"]),
            "status": r["status"],
            "version_num": r["version_num"],
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
            "error_message": r["error_message"],
        }
        for r in chapter_rows
    ]
    projected, meta = apply_response_contract(
        chapter_items, ref_fields=_JOB_STATUS_CHAPTER_REF_FIELDS, detail=detail, limit=limit,
    )
    return {
        "job_id": str(row["job_id"]),
        "book_id": str(row["book_id"]),
        "status": row["status"],
        "target_language": row["target_language"],
        "total_chapters": row["total_chapters"],
        # The job-level error stays — it's the single overall failure line, not the
        # per-chapter tracebacks the summary detail drops.
        "error_message": row["error_message"],
        "chapters": projected,
        **meta,
    }


# ── Tier A — auto-apply + Undo ────────────────────────────────────────────────


@mcp_server.tool(
    name="translation_set_active_version",
    description=(
        "Set a specific translation version as the active (published) version for its "
        "chapter+language — what readers see. Auto-applies. If the version has "
        "unresolved high-severity verifier issues, pass acknowledge_issues=true to "
        "publish anyway. Book-scoped (edit)."
    ),
    meta=require_meta(
        "A", "book",
        undo_hint={"tool": "translation_set_active_version",
                   "args": {"note": "set the previously-active version id back"}},
        synonyms=["set active", "publish version", "activate translation",
                  "make this the active version"],
        tool_name="translation_set_active_version",
    ),
)
async def translation_set_active_version(
    ctx: MCPContext,
    book_id: Annotated[str, "The book's id (UUID)."],
    chapter_id: Annotated[str, "The chapter's id (UUID)."],
    version_id: Annotated[str, "The translation version id (UUID) to activate."],
    acknowledge_issues: Annotated[
        bool, "Publish even if the verifier flagged unresolved high-severity issues."
    ] = False,
) -> dict:
    tc = _ctx(ctx)
    await _require_edit(tc, _uuid(book_id))
    db = get_pool()
    row = await db.fetchrow(
        "SELECT owner_user_id, book_id, target_language, status, unresolved_high_count "
        "FROM chapter_translations WHERE id=$1 AND chapter_id=$2",
        _uuid(version_id), _uuid(chapter_id),
    )
    if not row or str(row["book_id"]) != book_id:
        raise uniform_not_accessible()
    # Replicate the route's business rules (status gate + verifier soft-gate) inline
    # to avoid re-running its JWT/grant deps (we already authorized via the kit).
    if row["status"] != "completed":
        return {"success": False, "error": "only completed versions can be set active"}
    unresolved = row["unresolved_high_count"] or 0
    if unresolved > 0 and not acknowledge_issues:
        return {
            "success": False,
            "error": "needs_review",
            "unresolved_high_count": unresolved,
            "hint": "re-call with acknowledge_issues=true to publish anyway",
        }
    prev = await db.fetchval(
        "SELECT chapter_translation_id FROM active_chapter_translation_versions "
        "WHERE chapter_id=$1 AND target_language=$2",
        _uuid(chapter_id), row["target_language"],
    )
    await db.execute(
        """
        INSERT INTO active_chapter_translation_versions
          (chapter_id, target_language, chapter_translation_id, set_by_user_id, set_at)
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (chapter_id, target_language)
          DO UPDATE SET chapter_translation_id=$3, set_by_user_id=$4, set_at=now()
        """,
        _uuid(chapter_id), row["target_language"], _uuid(version_id), tc.user_id,
    )
    return {
        "success": True,
        "chapter_id": chapter_id,
        "target_language": row["target_language"],
        "active_id": version_id,
        "_meta": {
            "undo_hint": {
                "tool": "translation_set_active_version",
                "args": {
                    "book_id": book_id,
                    "chapter_id": chapter_id,
                    "version_id": str(prev) if prev else None,
                },
            }
        } if prev else {"undo_hint": {"available": False}},
    }


@mcp_server.tool(
    name="translation_save_edited_version",
    description=(
        "Save a human-edited translation as a NEW version (authored_by='human'), "
        "linked to the LLM version it was edited from. Auto-applies; reversible by "
        "setting the prior active version back. Book-scoped (edit)."
    ),
    meta=require_meta(
        "A", "book",
        undo_hint={"tool": "translation_set_active_version",
                   "args": {"note": "re-activate the version edited from"}},
        synonyms=["save edit", "save my translation", "human edit",
                  "save edited version"],
        tool_name="translation_save_edited_version",
    ),
)
async def translation_save_edited_version(
    ctx: MCPContext,
    book_id: Annotated[str, "The book's id (UUID)."],
    chapter_id: Annotated[str, "The chapter's id (UUID)."],
    edited_from_version_id: Annotated[str, "The version id (UUID) this edit derives from."],
    target_language: Annotated[str, "The target language code; must match the source version."],
    translated_body: Annotated[str, "The edited translation text."],
) -> dict:
    tc = _ctx(ctx)
    await _require_edit(tc, _uuid(book_id))
    db = get_pool()
    src = await db.fetchrow(
        "SELECT book_id, target_language FROM chapter_translations WHERE id=$1 AND chapter_id=$2",
        _uuid(edited_from_version_id), _uuid(chapter_id),
    )
    if not src or str(src["book_id"]) != book_id:
        raise uniform_not_accessible()
    if src["target_language"] != target_language:
        return {"success": False, "error": "target_language does not match the source version"}
    async with db.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1)::bigint)",
                f"{chapter_id}|{target_language}",
            )
            new = await conn.fetchrow(
                """
                INSERT INTO chapter_translations
                  (job_id, chapter_id, book_id, owner_user_id, status, target_language,
                   translated_body, translated_body_format,
                   version_num, authored_by, edited_from_version_id, finished_at)
                SELECT job_id, chapter_id, book_id, $4::uuid, 'completed', target_language,
                       $3, 'text',
                       COALESCE((SELECT MAX(version_num) FROM chapter_translations
                                  WHERE chapter_id=$2 AND target_language=$5), 0) + 1,
                       'human', $1, now()
                FROM chapter_translations WHERE id=$1
                RETURNING id, version_num
                """,
                _uuid(edited_from_version_id), _uuid(chapter_id), translated_body,
                tc.user_id, target_language,
            )
    return {
        "success": True,
        "version_id": str(new["id"]),
        "version_num": new["version_num"],
        "_meta": {
            "undo_hint": {
                "tool": "translation_set_active_version",
                "args": {"book_id": book_id, "chapter_id": chapter_id,
                         "version_id": edited_from_version_id},
            }
        },
    }


@mcp_server.tool(
    name="translation_patch_block",
    description=(
        "Correct ONE translated block in a chapter's human version (block/JSON format "
        "only). The first patch creates the human version from the base version and "
        "makes it active; later patches edit it in place. Auto-applies. Book-scoped (edit)."
    ),
    meta=require_meta(
        "A", "book",
        undo_hint={"tool": "translation_patch_block",
                   "args": {"note": "re-patch the block with the prior text"}},
        synonyms=["fix block", "correct block", "patch translation",
                  "correct one translated paragraph"],
        tool_name="translation_patch_block",
    ),
)
async def translation_patch_block(
    ctx: MCPContext,
    book_id: Annotated[str, "The book's id (UUID)."],
    chapter_id: Annotated[str, "The chapter's id (UUID)."],
    base_version_id: Annotated[str, "The version id (UUID) to seed/patch the human version from."],
    target_language: Annotated[str, "The target language code; must match the base version."],
    block_index: Annotated[int, "The 0-based index of the block to replace."],
    block: Annotated[dict, "The replacement Tiptap block node (JSON)."],
) -> dict:
    tc = _ctx(ctx)
    await _require_edit(tc, _uuid(book_id))
    db = get_pool()
    base = await db.fetchrow(
        "SELECT book_id, target_language, translated_body_format "
        "FROM chapter_translations WHERE id=$1 AND chapter_id=$2",
        _uuid(base_version_id), _uuid(chapter_id),
    )
    if not base or str(base["book_id"]) != book_id:
        raise uniform_not_accessible()
    if base["target_language"] != target_language:
        return {"success": False, "error": "target_language does not match the base version"}
    if base["translated_body_format"] != "json":
        return {"success": False, "error": "per-block correction requires a block (json) version"}

    from ..routers.versions import _as_list, _blocks_to_text
    import json as _json
    async with db.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1)::bigint)",
                f"{chapter_id}|{target_language}",
            )
            hv = await conn.fetchrow(
                "SELECT id, translated_body_json FROM chapter_translations "
                "WHERE chapter_id=$1 AND target_language=$2 AND authored_by='human' "
                "ORDER BY version_num DESC LIMIT 1",
                _uuid(chapter_id), target_language,
            )
            if not hv:
                hv = await conn.fetchrow(
                    """
                    INSERT INTO chapter_translations
                      (job_id, chapter_id, book_id, owner_user_id, status, target_language,
                       translated_body, translated_body_json, translated_body_format,
                       version_num, authored_by, edited_from_version_id, finished_at)
                    SELECT job_id, chapter_id, book_id, $4::uuid, 'completed', target_language,
                           translated_body, translated_body_json, translated_body_format,
                           COALESCE((SELECT MAX(version_num) FROM chapter_translations
                                      WHERE chapter_id=$2 AND target_language=$3), 0) + 1,
                           'human', $1, now()
                    FROM chapter_translations WHERE id=$1
                    RETURNING id, translated_body_json
                    """,
                    _uuid(base_version_id), _uuid(chapter_id), target_language, tc.user_id,
                )
                await conn.execute(
                    """
                    INSERT INTO active_chapter_translation_versions
                      (chapter_id, target_language, chapter_translation_id, set_by_user_id, set_at)
                    VALUES ($1, $2, $3, $4, now())
                    ON CONFLICT (chapter_id, target_language)
                      DO UPDATE SET chapter_translation_id=$3, set_by_user_id=$4, set_at=now()
                    """,
                    _uuid(chapter_id), target_language, hv["id"], tc.user_id,
                )
            hv_blocks = _as_list(hv["translated_body_json"])
            if not (0 <= block_index < len(hv_blocks)):
                return {"success": False, "error": "block_index out of range"}
            prev_block = hv_blocks[block_index]
            await conn.execute(
                "UPDATE chapter_translations "
                "SET translated_body_json = jsonb_set(translated_body_json, ARRAY[$2::text], $3::jsonb, false) "
                "WHERE id=$1",
                hv["id"], str(block_index), _json.dumps(block),
            )
            new_blocks = list(hv_blocks)
            new_blocks[block_index] = block
            await conn.execute(
                "UPDATE chapter_translations SET translated_body=$2, finished_at=now() WHERE id=$1",
                hv["id"], _blocks_to_text(new_blocks),
            )
    return {
        "success": True,
        "version_id": str(hv["id"]),
        "block_index": block_index,
        "_meta": {
            "undo_hint": {
                "tool": "translation_patch_block",
                "args": {"book_id": book_id, "chapter_id": chapter_id,
                         "base_version_id": str(hv["id"]),
                         "target_language": target_language,
                         "block_index": block_index, "block": prev_block},
            }
        },
    }


@mcp_server.tool(
    name="translation_update_settings",
    description=(
        "Update a book's translation settings (target language, model, prompts, etc.). "
        "Only the fields you pass are changed; omitted fields keep their value. "
        "Auto-applies; reversible by setting the prior values back. Book-scoped (edit)."
    ),
    meta=require_meta(
        "A", "book",
        undo_hint={"tool": "translation_update_settings",
                   "args": {"note": "set the prior settings values back"}},
        synonyms=["update settings", "change model", "set target language",
                  "translation settings", "configure translation"],
        tool_name="translation_update_settings",
    ),
)
async def translation_update_settings(
    ctx: MCPContext,
    book_id: Annotated[str, "The book's id (UUID)."],
    target_language: Annotated[str | None, "New target language code, or omit to keep."] = None,
    model_source: Annotated[str | None, "New model source ('user_model'|'platform_model'), or omit."] = None,
    model_ref: Annotated[
        str | list[str] | None,
        "New model id (a single UUID string; a one-element list is tolerated), or omit to keep.",
    ] = None,
) -> dict:
    model_ref = _single_value("model_ref", model_ref)
    tc = _ctx(ctx)
    bid = _uuid(book_id)
    await _require_edit(tc, bid)
    db = get_pool()
    prior, _is_default, _u = await resolve_effective_settings(tc.user_id, bid, db)
    row = await db.fetchrow(
        """
        INSERT INTO book_translation_settings
          (book_id, owner_user_id, target_language, model_source, model_ref, updated_at)
        VALUES ($1, $2, COALESCE($3,'en'), COALESCE($4,'platform_model'), $5, now())
        ON CONFLICT (book_id) DO UPDATE SET
          target_language = COALESCE($3, book_translation_settings.target_language),
          model_source    = COALESCE($4, book_translation_settings.model_source),
          model_ref       = COALESCE($5, book_translation_settings.model_ref),
          updated_at      = now()
        RETURNING target_language, model_source, model_ref
        """,
        bid, tc.user_id, target_language, model_source,
        _uuid(model_ref) if model_ref else None,
    )
    return {
        "success": True,
        "settings": {
            "target_language": row["target_language"],
            "model_source": row["model_source"],
            "model_ref": str(row["model_ref"]) if row["model_ref"] else None,
        },
        "_meta": {
            "undo_hint": {
                "tool": "translation_update_settings",
                "args": {
                    "book_id": book_id,
                    "target_language": prior.get("target_language"),
                    "model_source": prior.get("model_source"),
                    "model_ref": str(prior["model_ref"]) if prior.get("model_ref") else None,
                },
            }
        },
    }


# ── Tier W — priced → confirm ─────────────────────────────────────────────────


@mcp_server.tool(
    name="translation_start_job",
    description=(
        "Start a translation job over one or more chapters of a book. This COSTS "
        "money, so it returns a cost ESTIMATE and a confirm token — it does NOT start "
        "until confirmed via confirm_action. Pass force_retranslate=true to re-do "
        "chapters that are already translated. Book-scoped (edit)."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["translate", "translate book", "start translation",
                  "translate chapters", "run translation"],
        async_job=True,
        tool_name="translation_start_job",
    ),
)
async def translation_start_job(
    ctx: MCPContext,
    book_id: Annotated[str, "The book's id (UUID)."],
    chapter_ids: Annotated[list[str], "The chapter ids (UUIDs) to translate."],
    target_language: Annotated[str | None, "Target language code; omit to use the book's setting."] = None,
    force_retranslate: Annotated[bool, "Re-translate chapters that are already translated."] = False,
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id)
    await _require_edit(tc, bid)
    cids = [_uuid(c) for c in chapter_ids]
    est = await estimate_job_cost(
        get_pool(), owner_user_id=str(tc.user_id), book_id=bid,
        chapter_ids=cids, scope=SCOPE_CHAPTERS, target_language=target_language,
    )
    payload = {
        "action": "start_job",
        "title": f"Translate {len(cids)} chapter(s)",
        "book_id": book_id,
        "chapter_ids": [str(c) for c in cids],
        "target_language": est.target_language,
        "force_retranslate": force_retranslate,
        "estimate": est.as_dict(),
    }
    token = mint_confirm_token(
        settings.confirm_token_signing_secret, tc.user_id, bid,
        DESC_START_JOB, payload, _CONFIRM_TTL_S,
    )
    return _confirm_envelope(token, DESC_START_JOB, payload["title"], est)


@mcp_server.tool(
    name="translation_retranslate_dirty",
    description=(
        "Re-translate ONLY the segments of a chapter whose source changed or whose "
        "glossary terms went stale (cheaper than a full re-translation). This COSTS "
        "money, so it returns a cost ESTIMATE and a confirm token — it does NOT start "
        "until confirmed via confirm_action. Book-scoped (edit)."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["retranslate dirty", "re-translate changed", "refresh translation",
                  "update stale translation", "retranslate needs"],
        async_job=True,
        tool_name="translation_retranslate_dirty",
    ),
)
async def translation_retranslate_dirty(
    ctx: MCPContext,
    book_id: Annotated[str, "The book's id (UUID) the chapter belongs to."],
    chapter_id: Annotated[str, "The chapter's id (UUID)."],
    target_language: Annotated[str, "The target language code (e.g. 'en')."],
) -> dict:
    tc = _ctx(ctx)
    bid = _uuid(book_id)
    await _require_edit(tc, bid)
    cid = _uuid(chapter_id)
    est = await estimate_job_cost(
        get_pool(), owner_user_id=str(tc.user_id), book_id=bid,
        chapter_ids=[cid], scope=SCOPE_DIRTY, chapter_id=cid,
        target_language=target_language,
    )
    payload = {
        "action": "retranslate_dirty",
        "title": f"Re-translate {est.segment_count} changed segment(s)",
        "book_id": book_id,
        "chapter_id": chapter_id,
        "target_language": target_language,
        "estimate": est.as_dict(),
    }
    token = mint_confirm_token(
        settings.confirm_token_signing_secret, tc.user_id, bid,
        DESC_RETRANSLATE_DIRTY, payload, _CONFIRM_TTL_S,
    )
    return _confirm_envelope(token, DESC_RETRANSLATE_DIRTY, payload["title"], est)


@mcp_server.tool(
    name="translation_start_extraction",
    description=(
        "Extract glossary entities (characters, places, items, ...) from one or more "
        "chapters of a book — extracted entities land as draft / ai-suggested for review. "
        "This COSTS money, so it returns a token ESTIMATE and a confirm token — it does "
        "NOT start until confirmed via confirm_action. extraction_profile maps "
        "kind_code -> {attr_code: 'fill'|'overwrite'} (fill = only empty values; "
        "overwrite = replace + audit-log); omit to extract names only. Poll progress with "
        "jobs_get (kind 'glossary_extraction'). Book-scoped (edit)."
    ),
    meta=require_meta(
        "W", "book",
        synonyms=["extract glossary", "extract entities", "scan chapters for entities",
                  "build glossary", "extract characters"],
        async_job=True,
        tool_name="translation_start_extraction",
    ),
)
async def translation_start_extraction(
    ctx: MCPContext,
    book_id: Annotated[str, "The book's id (UUID)."],
    chapter_ids: Annotated[list[str], "The chapter ids (UUIDs) to extract from."],
    extraction_profile: Annotated[
        dict[str, dict[str, str]] | None,
        "kind_code -> {attr_code: 'fill'|'overwrite'}; omit to extract names only.",
    ] = None,
    model_ref: Annotated[
        str | list[str] | None,
        "Model id (a single UUID string; a one-element list is tolerated); "
        "omit to use your translation setting.",
    ] = None,
    max_entities_per_kind: Annotated[int, "Max entities per kind per chapter."] = 30,
    reasoning_effort: Annotated[
        str,
        "Reasoning effort for the extraction LLM: none|low|medium|high (paid compute; "
        "clamped to your grant — Edit caps at medium, Manage/owner at high).",
    ] = "none",
    thinking_enabled: Annotated[bool, "Deprecated alias for reasoning_effort=medium."] = False,
) -> dict:
    model_ref = _single_value("model_ref", model_ref)
    tc = _ctx(ctx)
    bid = _uuid(book_id)
    await _require_edit(tc, bid)
    # RE-Q11 (effort-auth, the HIGH finding): clamp the requested reasoning effort to
    # the CALLER'S grant ceiling so an Edit grantee can't escalate paid compute past
    # medium on a book they don't own. `thinking_enabled` is the deprecated bool alias
    # (→ medium). Re-clamped again at confirm (actions.py) against a fresh grant read.
    requested_effort = reasoning_effort or ("medium" if thinking_enabled else "none")
    caller_level = await _grant_resolver(bid, tc.user_id)
    effort, _capped = clamp_effort_to_grant(requested_effort, caller_level)
    cids = [_uuid(c) for c in chapter_ids]
    profile = extraction_profile or {}
    # Estimate for the confirm card — a deterministic token projection over
    # (chapter count × the profile's kinds/attrs). The confirm effect re-runs the
    # core (which re-computes the SAME estimate + stores it), so no H14 re-price.
    profile_data = await fetch_extraction_profile(str(bid))
    kinds_metadata = (profile_data or {}).get("kinds") or []
    # The agent rarely authors the full kind→attr map; when omitted, extract every
    # auto-selected attribute (the same default the FE builds) so the cost estimate AND
    # the job aren't empty — without this the worker plans 0 batches → 0 entities.
    if not profile:
        # "default" → defer to each attribute's authored merge_strategy
        # (D-EXTRACT-ATTR-MERGE-DEFAULTS); "fill" used to freeze attributes on re-extraction.
        profile = {
            k["code"]: {a["code"]: "default" for a in k.get("attributes", [])}
            for k in kinds_metadata
            if k.get("auto_selected", True) and k.get("attributes")
        }
    # #36 — real per-chapter sizes (best-effort) so the windowing planner isn't blind to
    # chapter length (the flat 8000 placeholder undercounted LLM calls on large chapters).
    from ..book_client import build_chapters_meta
    chapters_meta = await build_chapters_meta(book_id, cids)
    # D-CACHE-PLANNER-WIRING: split-aware quote against the REAL model context (caller's own
    # model → user_model). Best-effort resolve → conservative fallback.
    from ..workers.extraction_model import get_model_context_window
    model_context_window = await get_model_context_window(
        "user_model", str(_uuid(model_ref)) if model_ref else None)
    # D-RE-EFFORT-COST-ESTIMATE: quote against the CLAMPED effort (resolved above) so the
    # confirm card's cost grows with high effort — the spend the user is approving.
    estimate = estimate_extraction_cost(
        chapters_meta, profile, kinds_metadata, model_context_window=model_context_window,
        reasoning_effort=effort)
    payload = {
        "action": "start_extraction",
        "title": f"Extract glossary from {len(cids)} chapter(s)",
        "book_id": book_id,
        "chapter_ids": [str(c) for c in cids],
        "extraction_profile": profile,
        # The agent picks one of the user's OWN models (settings_list_models) and the
        # worker runs on the caller's key (caller-pays) → user_model, never platform_model.
        "model_source": "user_model",
        "model_ref": str(_uuid(model_ref)) if model_ref else None,
        "max_entities_per_kind": max_entities_per_kind,
        # Clamped effort is the SSOT; the worker maps it via the SDK reasoning_fields
        # (graded low/med/high). thinking_enabled stays as the back-compat bool alias.
        "reasoning_effort": effort,
        "thinking_enabled": effort not in ("none", "off"),
        "estimate": estimate,
    }
    token = mint_confirm_token(
        settings.confirm_token_signing_secret, tc.user_id, bid,
        DESC_START_EXTRACTION, payload, _CONFIRM_TTL_S,
    )
    return {
        "needs_confirm": True,
        "confirm_token": token,
        "descriptor": DESC_START_EXTRACTION,
        "domain": "translation",
        "title": payload["title"],
        "estimate": estimate,
    }


# ── job_control — A (cancel/pause) / W (resume/retry) ─────────────────────────

_JOB_CONTROL_TIER = {"cancel": "A", "pause": "A", "resume": "W", "retry": "W"}


@mcp_server.tool(
    name="translation_job_control",
    description=(
        "Control a translation job: 'cancel' or 'pause' apply immediately; 'resume' "
        "and 'retry' RE-SPEND money so they return a cost estimate + confirm token "
        "(confirm via confirm_action — they do NOT run until confirmed). Forwards to "
        "the translation control plane. Book-scoped (edit)."
    ),
    meta=require_meta(
        "W", "book",  # declared W (the strictest path); cancel/pause execute as A inline.
        synonyms=["cancel job", "pause job", "resume job", "retry job",
                  "stop translation", "restart translation"],
        tool_name="translation_job_control",
    ),
)
async def translation_job_control(
    ctx: MCPContext,
    job_id: Annotated[str, "The translation job's id (UUID)."],
    action: Annotated[
        Literal["cancel", "pause", "resume", "retry"],
        "cancel|pause (apply now) | resume|retry (re-spend → confirm).",
    ],
) -> dict:
    tc = _ctx(ctx)
    db = get_pool()
    jid = _uuid(job_id)
    row = await db.fetchrow(
        "SELECT owner_user_id, book_id, status, chapter_ids "
        "FROM translation_jobs WHERE job_id=$1", jid
    )
    if not row:
        raise uniform_not_accessible()
    await _require_edit(tc, row["book_id"])

    tier = _JOB_CONTROL_TIER[action]
    if tier == "A":
        # cancel / pause — execute immediately via the owner-scoped control cores.
        from ..routers.jobs import _cancel_job_core, _pause_job_core
        owner = row["owner_user_id"]
        if action == "cancel":
            await _cancel_job_core(db, jid, str(owner))
            result = {"job_id": job_id, "status": "cancelled"}
        else:
            result = await _pause_job_core(db, jid, owner)
        result["_meta"] = {
            "undo_hint": (
                {"tool": "translation_job_control",
                 "args": {"job_id": job_id, "action": "resume"}}
                if action == "pause" else {"available": False}
            )
        }
        result["success"] = True
        return result

    # resume / retry — re-spend → estimate + confirm (the confirm route runs the core).
    est = await estimate_job_cost(
        db, owner_user_id=str(row["owner_user_id"]), book_id=row["book_id"],
        chapter_ids=list(row["chapter_ids"] or []),
        scope=SCOPE_CHAPTERS,
    )
    payload = {
        "action": f"job_{action}",
        "title": f"{action.capitalize()} translation job",
        "book_id": str(row["book_id"]),
        "job_id": job_id,
        "control_action": action,
        # The job's chapter scope, bound so the confirm route can re-price (H14).
        "chapter_ids": [str(c) for c in (row["chapter_ids"] or [])],
        "estimate": est.as_dict(),
    }
    token = mint_confirm_token(
        settings.confirm_token_signing_secret, tc.user_id, row["book_id"],
        f"translation.job_{action}", payload, _CONFIRM_TTL_S,
    )
    return _confirm_envelope(token, f"translation.job_{action}", payload["title"], est)


# ── helpers ───────────────────────────────────────────────────────────────────


def _uuid(s: str) -> UUID:
    try:
        return UUID(str(s))
    except (ValueError, TypeError, AttributeError):
        # A malformed id is indistinguishable from a missing resource (H13).
        raise uniform_not_accessible()


def _confirm_envelope(token: str, descriptor: str, title: str, est) -> dict:
    """The C-CONFIRM propose return shape: a confirm token + descriptor + title +
    the cost estimate the agent renders. The agent passes the token to
    confirm_action (domain='translation'), which hits /v1/translation/actions/confirm."""
    return {
        "needs_confirm": True,
        "confirm_token": token,
        "descriptor": descriptor,
        "domain": "translation",
        "title": title,
        "estimate": est.as_dict(),
    }


# SQL + payload shaping reused from the REST routers (kept here so the MCP facade
# doesn't import FastAPI route handlers, which carry JWT/grant deps).

_COVERAGE_SQL = """
SELECT
  ct.chapter_id,
  ct.target_language,
  COUNT(*) AS version_count,
  (SELECT status FROM chapter_translations ct2
    WHERE ct2.chapter_id=ct.chapter_id AND ct2.target_language=ct.target_language
    ORDER BY ct2.created_at DESC LIMIT 1) AS latest_status,
  (SELECT version_num FROM chapter_translations ct2
    WHERE ct2.chapter_id=ct.chapter_id AND ct2.target_language=ct.target_language
    ORDER BY ct2.created_at DESC LIMIT 1) AS latest_version_num,
  actv.chapter_translation_id AS active_ct_id,
  (SELECT version_num FROM chapter_translations ct3
    WHERE ct3.id=actv.chapter_translation_id) AS active_version_num
FROM chapter_translations ct
LEFT JOIN active_chapter_translation_versions actv
  ON actv.chapter_id=ct.chapter_id AND actv.target_language=ct.target_language
WHERE ct.book_id=$1
GROUP BY ct.chapter_id, ct.target_language, actv.chapter_translation_id
ORDER BY ct.chapter_id, ct.target_language
"""


def _coverage_payload(rows, book_id: UUID, all_chapter_ids: "list[str] | None" = None) -> dict:
    chapter_map: dict[str, dict] = {}
    known: set[str] = set()
    for r in rows:
        cid = str(r["chapter_id"])
        lang = r["target_language"]
        known.add(lang)
        chapter_map.setdefault(cid, {})[lang] = {
            "has_active": r["active_ct_id"] is not None,
            "active_version_num": r["active_version_num"],
            "latest_version_num": r["latest_version_num"],
            "latest_status": r["latest_status"],
            "version_count": r["version_count"],
        }
    # D-S05 — surface chapters that exist in the BOOK but have no translation row at all. Preserve
    # book order (all_chapter_ids is ordered), append any translation-only ids that book-service
    # didn't return (e.g. a deleted chapter still carrying history), and give the agent an explicit
    # `untranslated_chapter_ids` list so it doesn't have to diff two structures.
    untranslated: list[str] = []
    ordered: list[str] = []
    if all_chapter_ids:
        for cid in all_chapter_ids:
            ordered.append(cid)
            langs = chapter_map.get(cid, {})
            if not any(v.get("has_active") for v in langs.values()):
                untranslated.append(cid)
        for cid in chapter_map:  # translation-only rows book-service didn't list
            if cid not in all_chapter_ids:
                ordered.append(cid)
    else:
        ordered = list(chapter_map)  # degraded: no book chapter list available
    return {
        "book_id": str(book_id),
        "coverage": [{"chapter_id": cid, "languages": chapter_map.get(cid, {})}
                     for cid in ordered],
        "known_languages": sorted(known),
        "untranslated_chapter_ids": untranslated,
    }


# `model_source` / `model_ref` live on translation_jobs, NOT on chapter_translations — the
# model is a property of the JOB that produced a version. Selecting them off `ct` made
# Postgres reject the whole statement (`column ct.model_source does not exist`), so
# translation_list_versions failed on EVERY real chapter, always. Nothing caught it: this
# service's tests assert the tool's NAME and TIER, never run its SQL.
# LEFT JOIN, not INNER: a hand-edited version has a NULL job_id and hence no model.
_VERSIONS_SQL = """
SELECT ct.id, ct.version_num, ct.job_id, ct.status, ct.target_language,
       tj.model_source, tj.model_ref, ct.input_tokens, ct.output_tokens,
       ct.created_at, ct.authored_by,
       (actv.chapter_translation_id = ct.id) AS is_active
FROM chapter_translations ct
LEFT JOIN active_chapter_translation_versions actv
  ON actv.chapter_id=ct.chapter_id AND actv.target_language=ct.target_language
LEFT JOIN translation_jobs tj ON tj.job_id = ct.job_id
WHERE ct.chapter_id=$1
ORDER BY ct.target_language, ct.version_num DESC
"""


# L1/L2 reference-first (Context Budget Law §6b): at detail=summary a version row
# collapses to these fields — the identity (id + version_num), the language it groups
# under, and the status/active flags a "which version is live / pick one" answer needs.
# The heavier per-version metadata (model_source/model_ref UUIDs, job_id UUID, token
# counts, authored_by) is dropped; fetch a specific version's full detail via the
# version routes. target_language is a ref field so the grouped shape survives summary.
_VERSION_REF_FIELDS = (
    "id", "version_num", "target_language", "status", "is_active",
)


def _version_rows(rows) -> list[dict]:
    """Flatten the version query rows to a list of serialized dicts (each carrying
    its target_language) — the flat shape the L1/L2 contract projects over."""
    return [
        {
            "id": str(r["id"]),
            "version_num": r["version_num"],
            "target_language": r["target_language"],
            "job_id": str(r["job_id"]) if r["job_id"] else None,
            "status": r["status"],
            "is_active": bool(r["is_active"]),
            "model_source": r["model_source"],
            "model_ref": str(r["model_ref"]) if r["model_ref"] else None,
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
            "authored_by": r["authored_by"],
        }
        for r in rows
    ]


def _group_versions(items: list[dict]) -> list[dict]:
    """Re-group the (already contract-projected) flat version dicts back into the
    per-language shape `[{target_language, versions: [...]}]`. Ordering follows the
    SQL (target_language, version_num DESC) which the projection preserves."""
    lang_map: dict[str, dict] = {}
    for it in items:
        lang = it.get("target_language")
        g = lang_map.setdefault(lang, {"target_language": lang, "versions": []})
        g["versions"].append(it)
    return list(lang_map.values())


# ── ASGI factory ──────────────────────────────────────────────────────────────


def build_mcp_app():
    """Return the ASGI app to mount at ``/mcp`` in ``main.py``. The session manager
    is run by ``main.py``'s lifespan (a mounted sub-app's lifespan is not auto-run)."""
    return mcp_server.streamable_http_app()

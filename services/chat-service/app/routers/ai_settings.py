"""Chat & AI settings — the per-user prefs CRUD and the effective-settings
resolver (spec docs/specs/2026-07-05-chat-ai-settings.md §6).

Two routers, both under /v1/chat:
  * prefs_router       — GET/PATCH /v1/chat/ai-prefs (the Account tier blob)
  * effective_router   — GET /v1/chat/effective-settings (the resolved cascade
                         a chat session or any studio tool reads)

Models resolve across Session ▸ Book ▸ Account with per-tier liveness; the Book
tier is the book-owner's per-role model settings read grant-gated from
composition-service (D-CHATAI-M1B). behavior/grounding/voice/context resolve
Session ▸ Account ▸ System generically (no book scope yet).
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.client.provider_client import get_provider_client
from app.config import settings
from app.db.user_chat_ai_prefs import VersionConflict, get_prefs, patch_prefs
from app.deps import get_current_user, get_db
from app.services import settings_resolution as sr

logger = logging.getLogger(__name__)

prefs_router = APIRouter(prefix="/v1/chat/ai-prefs", tags=["ai-settings"])
effective_router = APIRouter(prefix="/v1/chat/effective-settings", tags=["ai-settings"])
capabilities_router = APIRouter(prefix="/v1/chat/capabilities", tags=["ai-settings"])

# System-tier defaults — the ONLY place a literal default lives (spec §3.3). These
# surface today's silent behaviors as explicit, visible values.
_SYSTEM_BEHAVIOR = {"reasoning_effort": "off", "permission_mode": "write"}
_SYSTEM_GROUNDING = {"grounding_enabled": True, "recent_message_count": 50}
_SYSTEM_CONTEXT = {"mode": "auto"}
_SYSTEM_VOICE: dict = {}

# Account-tier model capabilities provider-registry's default-models route supports.
_ACCOUNT_CAPS = ("chat", "planner", "embedding", "rerank")

# Closed-set values (spec §8.1) now live in the shared resolution module: the SESSION
# row is a SECOND write door onto the same settings, and an enum registry private to
# this router could not defend it. See `settings_resolution.SETTING_ENUMS`.


# ── ai-prefs CRUD ────────────────────────────────────────────────────────────
class AiPrefsResponse(BaseModel):
    behavior: dict = Field(default_factory=dict)
    grounding: dict = Field(default_factory=dict)
    voice: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    version: int = 0


class AiPrefsPatch(BaseModel):
    """Partial deep-merge patch. Each present category is field-merged into the
    stored blob; a null leaf clears that key ("inherit"). Absent = untouched."""
    behavior: dict | None = None
    grounding: dict | None = None
    voice: dict | None = None
    context: dict | None = None

    @model_validator(mode="after")
    def _check_enums(self) -> "AiPrefsPatch":
        for cat in sr.SETTING_ENUMS:
            sr.validate_setting_enums(cat, getattr(self, cat))
        # Voice source fields nest inside the voice blob (flat SETTING_ENUMS can't
        # reach them). Normalize legacy 'ai_model' → 'user_model' so the STORE
        # converges to one vocabulary, and reject a genuinely unknown source
        # (D-CHATAI-VOICE-TWO-STORES).
        self.voice = sr.normalize_voice_sources(self.voice)
        return self


@prefs_router.get("", response_model=AiPrefsResponse)
async def read_ai_prefs(
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> AiPrefsResponse:
    p = await get_prefs(pool, owner_user_id=user_id)
    return AiPrefsResponse(
        behavior=p.behavior, grounding=p.grounding, voice=p.voice,
        context=p.context, version=p.version,
    )


@prefs_router.patch("", response_model=AiPrefsResponse)
async def update_ai_prefs(
    body: AiPrefsPatch,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> AiPrefsResponse:
    patch = body.model_dump(exclude_none=True)
    if not patch:
        p = await get_prefs(pool, owner_user_id=user_id)
    else:
        try:
            p = await patch_prefs(
                pool, owner_user_id=user_id, patch=patch, expected_version=if_match
            )
        except VersionConflict as exc:
            raise HTTPException(status_code=412, detail=str(exc))
    return AiPrefsResponse(
        behavior=p.behavior, grounding=p.grounding, voice=p.voice,
        context=p.context, version=p.version,
    )


# ── effective-settings resolver ──────────────────────────────────────────────
def _loads(v) -> dict:
    if v is None:
        return {}
    if isinstance(v, str):
        return json.loads(v)
    return dict(v)


async def _fetch_session_tiers(pool, session_id, user_id) -> dict:
    """Read the session row (owner-scoped) and split it into per-category tier
    blobs. Returns {} for every category if the session is missing/foreign."""
    row = await pool.fetchrow(
        "SELECT model_source, model_ref, composer_model_source, composer_model_ref, "
        "planner_model_source, planner_model_ref, system_prompt, generation_params, "
        "grounding_enabled, project_ids, project_id, voice_overrides, context_overrides "
        "FROM chat_sessions WHERE session_id = $1 AND owner_user_id = $2",
        UUID(str(session_id)), UUID(str(user_id)),
    )
    if row is None:
        return {"models": {}, "behavior": {}, "grounding": {}, "voice": {}, "context": {}}

    def _ref(src, ref):
        return (src, str(ref)) if ref is not None else None

    models = {
        sr.ModelRole.CHAT.value: _ref(row["model_source"], row["model_ref"]),
        sr.ModelRole.COMPOSER.value: _ref(row["composer_model_source"], row["composer_model_ref"]),
        sr.ModelRole.PLANNER.value: _ref(row["planner_model_source"], row["planner_model_ref"]),
    }
    gp = _loads(row["generation_params"])
    behavior = {k: gp[k] for k in ("temperature", "top_p", "max_tokens", "reasoning_effort") if k in gp}
    if row["system_prompt"] is not None:
        behavior["system_prompt"] = row["system_prompt"]
    grounding = {}
    if row["grounding_enabled"] is not None:
        grounding["grounding_enabled"] = row["grounding_enabled"]
    pids = list(row["project_ids"] or [])
    if pids:
        grounding["project_ids"] = [str(p) for p in pids]
    return {
        "models": {k: v for k, v in models.items() if v is not None},
        "behavior": behavior,
        "grounding": grounding,
        "voice": _loads(row["voice_overrides"]),
        "context": _loads(row["context_overrides"]),
    }


async def _fetch_account_model_refs(user_id: str) -> dict[str, tuple[str, str]]:
    client = get_provider_client()
    out: dict[str, tuple[str, str]] = {}
    for cap in _ACCOUNT_CAPS:
        ref = await client.get_default_model(cap, user_id)
        if ref is not None:
            out[cap] = ref
    return out


@effective_router.get("")
async def read_effective_settings(
    book_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Resolve the full settings cascade for a context. Studio-tool callers omit
    `session_id` (Session tier skipped per §3.1). Returns per model role +
    per field: {effective_value, source_tier, tier_stack}."""
    session_tiers = (
        await _fetch_session_tiers(pool, session_id, user_id)
        if session_id else {"models": {}, "behavior": {}, "grounding": {}, "voice": {}, "context": {}}
    )
    account = await get_prefs(pool, owner_user_id=user_id)
    account_model_refs = await _fetch_account_model_refs(user_id)

    # Book tier (D-CHATAI-M1B) — the OWNER's per-role model settings for this book,
    # read grant-gated cross-tenant from composition-service (best-effort: {} on any
    # failure / no-grant → no book override, never breaks the resolve). behavior/
    # grounding/context book overrides are not book-scoped yet (empty).
    book_models: dict[str, tuple[str, str] | None] = {}
    if book_id:
        from app.client.composition_client import get_composition_client
        _roles = await get_composition_client().get_book_model_roles(str(book_id), str(user_id))
        for _role, _val in _roles.items():
            if isinstance(_val, dict) and _val.get("model_ref"):
                book_models[_role] = (_val.get("model_source") or "user_model", str(_val["model_ref"]))
    book_tiers = {"behavior": {}, "grounding": {}, "voice": {}, "context": {}}

    # ── models: batch liveness over the distinct candidate set, then resolve ──
    session_models = {
        r.value: session_tiers["models"].get(r.value) for r in sr.ModelRole
    }
    candidates = sr.collect_candidate_refs(
        session_refs=session_models, book_refs=book_models, account_refs=account_model_refs,
    )
    client = get_provider_client()
    live: dict[tuple[str, str], bool] = {}
    for cand in candidates:
        live[cand] = await client.is_live(cand[0], cand[1], user_id)

    models_out = {}
    for role in sr.ModelRole:
        models_out[role.value] = sr.resolve_model_role(
            role,
            session_ref=session_models.get(role.value),
            book_ref=book_models.get(role.value),
            account_refs=account_model_refs,
            is_live=lambda ref: live.get(ref, False),
        )

    def _cat(name, defaults):
        tiers = [(sr.TIER_SESSION, session_tiers[name]), (sr.TIER_BOOK, book_tiers[name]),
                 (sr.TIER_ACCOUNT, getattr(account, name))]
        return sr.resolve_category(tiers, defaults=defaults)

    return {
        "context_ref": {"book_id": book_id, "session_id": session_id},
        "models": models_out,
        "behavior": _cat("behavior", _SYSTEM_BEHAVIOR),
        "grounding": _cat("grounding", _SYSTEM_GROUNDING),
        "voice": _cat("voice", _SYSTEM_VOICE),
        "context": _cat("context", _SYSTEM_CONTEXT),
    }


# ── deploy capability ceilings ───────────────────────────────────────────────
# D-WS4C-EFFECTIVE-VALUE. A capability like canon auto-capture is `effective =
# AND(deploy_allows, user_enables)` (Settings & Config Boundary: env is a CEILING,
# never a per-user knob). The two halves live in different services — the ceiling
# is chat-service env (`settings.canon_capture_enabled`), the user knob is
# `knowledge_projects.canon_capture_enabled` — so the join can only be computed
# where the ceiling is visible. This route publishes the deploy-tier ceiling so a
# consumer that already holds the user knob (the knowledge project settings modal)
# can render the HONEST effective value + source, instead of the toggle silently
# doing nothing when a deployment kill-switches capture off (the "silently-off" bug
# class the boundary rule exists to prevent). `source_tier` uses the shared cascade
# vocabulary (TIER_SYSTEM) so a ceiling reads the same as any other system default.
@capabilities_router.get("")
async def read_capabilities(
    user_id: str = Depends(get_current_user),
) -> dict:
    """Deploy-tier capability ceilings. A consumer ANDs `deploy_allows` with its own
    user/project opt-in to get the effective value: `effective = AND(ceiling, knob)`."""
    return {
        "canon_capture": {
            "deploy_allows": settings.canon_capture_enabled,
            "source_tier": sr.TIER_SYSTEM,
        },
    }

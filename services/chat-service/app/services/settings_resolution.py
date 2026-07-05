"""Chat & AI settings resolution (spec docs/specs/2026-07-05-chat-ai-settings.md §3).

Pure, side-effect-free cascade logic — the single source of truth for how a
setting resolves across tiers. Kept free of I/O so it is fully unit-testable;
the router feeds it already-fetched tier data + a liveness callable.

Tier cascade, most-specific wins:

    Tool/turn  ▸  Session  ▸  Book  ▸  Account  ▸  System

- **Field-by-field deep merge**: a tier that overrides only `temperature` does
  NOT shadow a lower tier's `top_p`. Inheritance predicate = key-absence ⇒
  inherit down. (The Tool tier is FE-session-ephemeral and never reaches here.)
- **Models validate liveness at EVERY tier** from one authoritative source
  (provider-registry) so FE-preview and server-submit cannot disagree; a dead
  ref at any tier is skipped, and the skipped tiers are named. All-dead ⇒
  `no_model_configured` (never a silent mid-turn 404).
- **null at PATCH time = "clear to inherit"** (delete the key); absent = untouched.
  Resolution therefore never sees an explicit null.
"""

from __future__ import annotations

import enum
from typing import Any, Callable, Iterable


class ModelRole(str, enum.Enum):
    """The one canonical closed set of model roles (spec §3.4). Shared as the key
    vocabulary across all three model stores so no tier is read under a mis-spelled
    key. `embedding`/`rerank` are provider capabilities; `chat`/`composer`/`planner`/
    `critic` are app-roles that call the `chat` capability."""

    CHAT = "chat"
    COMPOSER = "composer"
    PLANNER = "planner"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    CRITIC = "critic"


# Roles whose Account default lives under their OWN capability key if present,
# else falls back to the `chat` capability default (spec §3.4).
_CHAT_CAPABILITY_ROLES = {ModelRole.CHAT, ModelRole.COMPOSER, ModelRole.PLANNER, ModelRole.CRITIC}

# Source-tier labels used in the effective-value contract.
TIER_TOOL = "tool"
TIER_SESSION = "session"
TIER_BOOK = "book"
TIER_ACCOUNT = "account"
TIER_SYSTEM = "system"
TIER_UNAVAILABLE = "unavailable"          # a tier's source service was unreachable
TIER_NONE = "no_model_configured"         # every tier resolved dead/unset


# ── deep field-merge (PATCH semantics) ──────────────────────────────────────
def apply_patch(current: dict, patch: dict) -> dict:
    """Return a new dict = `current` with `patch` deep-merged in.

    - a leaf value of ``None`` in `patch` DELETES that key ("clear to inherit"),
    - an absent key leaves `current` untouched,
    - nested dicts recurse (so patching `voice.chat.tts_voice_id` doesn't clobber
      `voice.chat.tts_model_ref`).
    Matches auth-service's jsonb `||` field-merge so a two-device concurrent edit
    of different leaves both survive (spec §4.5)."""
    out = dict(current)
    for key, val in patch.items():
        if val is None:
            out.pop(key, None)
        elif isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = apply_patch(out[key], val)
        elif isinstance(val, dict):
            # patching a dict onto a non-dict/absent slot: strip any null leaves
            out[key] = apply_patch({}, val)
        else:
            out[key] = val
    return out


# ── generic per-field cascade (behavior / grounding / voice / context) ───────
def resolve_category(tiers: list[tuple[str, dict]], *, defaults: dict | None = None) -> dict:
    """Resolve every leaf field across an ordered tier list.

    `tiers` is ordered MOST-SPECIFIC FIRST, e.g.
        [(TIER_SESSION, {...}), (TIER_BOOK, {...}), (TIER_ACCOUNT, {...})].
    `defaults` is the System tier (lowest precedence). Returns, per field:
        { field: {"effective_value": v, "source_tier": t, "tier_stack": {tier: v}} }
    Only scalar leaves are resolved per-field; nested dicts are treated as a leaf
    (voice's per-surface sub-objects are resolved one level down by the caller)."""
    stack: list[tuple[str, dict]] = list(tiers)
    if defaults:
        stack = stack + [(TIER_SYSTEM, defaults)]

    fields: set[str] = set()
    for _, blob in stack:
        fields.update(blob.keys())

    out: dict[str, dict] = {}
    for field in fields:
        tier_stack: dict[str, Any] = {}
        effective: Any = None
        source = None
        for tier, blob in stack:
            if field in blob and blob[field] is not None:
                tier_stack[tier] = blob[field]
                if source is None:  # first (most-specific) wins
                    effective, source = blob[field], tier
        out[field] = {
            "effective_value": effective,
            "source_tier": source,
            "tier_stack": tier_stack,
        }
    return out


# ── model-role resolution with liveness (spec §3.1) ──────────────────────────
def account_capability_for(role: ModelRole) -> list[str]:
    """The Account-tier capability keys to try for a role, in order. App-roles
    (composer/planner/critic) fall back to the `chat` capability default (§3.4)."""
    if role in _CHAT_CAPABILITY_ROLES and role is not ModelRole.CHAT:
        return [role.value, ModelRole.CHAT.value]
    return [role.value]


def resolve_model_role(
    role: ModelRole,
    *,
    session_ref: tuple[str, str] | None,          # (model_source, model_ref) or None
    book_ref: tuple[str, str] | None,
    account_refs: dict[str, tuple[str, str]],     # capability -> (source, ref)
    is_live: Callable[[tuple[str, str]], bool],   # (source, ref) -> live?
    book_unavailable: bool = False,
) -> dict:
    """Resolve one model role across tiers with per-tier liveness validation.

    Returns {"effective_value": {"model_source","model_ref"}|None, "source_tier",
             "tier_stack": {tier: {...}}, "skipped": [tiers with a dead ref]}.
    - Validates liveness at EVERY tier; a dead ref is skipped and recorded.
    - `book_unavailable` (composition-service unreachable) surfaces as
      source_tier=unavailable for the book slot rather than silently dropping to
      Account (spec §3.2) — but a live Session or a live Account still resolves.
    - all tiers dead/unset ⇒ source_tier = no_model_configured.
    """
    ordered: list[tuple[str, tuple[str, str] | None]] = [(TIER_SESSION, session_ref)]
    if book_unavailable:
        ordered.append((TIER_UNAVAILABLE, None))
    else:
        ordered.append((TIER_BOOK, book_ref))
    account_ref = None
    for cap in account_capability_for(role):
        if cap in account_refs:
            account_ref = account_refs[cap]
            break
    ordered.append((TIER_ACCOUNT, account_ref))

    tier_stack: dict[str, Any] = {}
    skipped: list[str] = []
    effective = None
    source = None
    saw_unavailable = False
    for tier, ref in ordered:
        if tier == TIER_UNAVAILABLE:
            saw_unavailable = True
            continue
        if ref is None:
            continue
        tier_stack[tier] = {"model_source": ref[0], "model_ref": ref[1]}
        if source is not None:
            continue
        if is_live(ref):
            effective = {"model_source": ref[0], "model_ref": ref[1]}
            source = tier
        else:
            skipped.append(tier)

    if source is None:
        # nothing live resolved; distinguish "a tier was unavailable" from
        # "genuinely nothing configured" so the UI messages honestly.
        source = TIER_UNAVAILABLE if saw_unavailable else TIER_NONE

    return {
        "effective_value": effective,
        "source_tier": source,
        "tier_stack": tier_stack,
        "skipped": skipped,
    }


def collect_candidate_refs(
    *,
    session_refs: dict[str, tuple[str, str] | None],
    book_refs: dict[str, tuple[str, str] | None],
    account_refs: dict[str, tuple[str, str]],
) -> set[tuple[str, str]]:
    """Every distinct (source, ref) pair across all role tiers — so the caller can
    batch a single liveness check instead of one call per tier."""
    out: set[tuple[str, str]] = set()
    for m in (session_refs, book_refs):
        for ref in m.values():
            if ref is not None:
                out.add(ref)
    for ref in account_refs.values():
        out.add(ref)
    return out


def all_roles() -> Iterable[ModelRole]:
    return list(ModelRole)

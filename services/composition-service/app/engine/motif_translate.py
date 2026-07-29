"""Motif translate — the USER-PAID runtime path (docs/plans/2026-07-29-motif-translate-runtime.md).

The platform's own 84 motifs ship pre-translated into 17 locales at dev time, free.
A motif a *user* authored is theirs: we never translate it on our own initiative and
never spend a token on it behind their back (spec §5). This module is the other half
of that policy — the one that lets them spend their own, deliberately.

``run_translate_motifs`` is the worker handler behind the Tier-W
``composition_motif_translate`` tool. The confirm effect (routers/actions.py) enqueues
a ``translate_motif`` job; the consumer dispatches here. Input envelope:

    {"worker_op": "translate_motif",
     "motif_ids": ["…"], "target_language": "ja", "book_id": null,
     "model_ref": "…", "model_source": "user_model", "force": false}

Three properties this file exists to hold:

* **Never blank.** A leaf the model drops, renames, or returns empty keeps its source
  wording. A blank motif name renders as an empty card, which reads as data loss —
  the same call `scripts/motif_translate.py` makes for the same reason.

* **Never mis-merge.** We accept only the keys we sent. A model that invents
  ``beats.typo_key.label`` has that key DROPPED (and counted), so the beat falls back
  to its source wording rather than the wording landing on the wrong beat. The
  dev-time tool raises on the same input because a human can go fix the file; at
  runtime there is nobody to fix it and a raise would burn the user's money for
  nothing.

* **Never silently English.** A leaf handed back byte-identical to its source is
  reported as `echoed`, not retried. The user paid for one pass; a silent second pass
  would double their spend. Telling them beats charging them again.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.engine.critic import parse_critique_json
from app.engine.llm_json import call_json
from app.grant_client import GrantLevel, get_grant_client
from app.grant_deps import InsufficientGrant, authorize_book
from app.packer.pack import OwnershipError
from app.motif_i18n import (
    build_translation_entry,
    extract_translatable,
    flatten_entry,
    is_untranslated_echo,
    parse_translation_entry,
    translatable_hash,
    unflatten_entry,
)

logger = logging.getLogger(__name__)

__all__ = ["run_translate_motifs", "translate_one", "LANGUAGE_NAMES", "MAX_MOTIFS_PER_JOB"]

# The languages a user may buy. Closed set = the platform's supported locales, which is
# what the FE's own language switcher offers — so the value can only ever be one the
# reader could actually be reading in. It also keeps `auto`/`und` out of the write path
# (`language='auto'` once matched zero rows and zeroed the whole library —
# D-MOTIF-AUTO-LANGUAGE-ZEROES-RETRIEVAL).
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "vi": "Tiếng Việt",
    "ja": "日本語",
    "ko": "한국어",
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
    "es": "Español",
    "pt-BR": "Português (Brasil)",
    "fr": "Français",
    "de": "Deutsch",
    "ru": "Русский",
    "id": "Bahasa Indonesia",
    "ms": "Bahasa Melayu",
    "th": "ไทย",
    "tr": "Türkçe",
    "ar": "العربية",
    "hi": "हिन्दी",
}

# One job may not translate more than this many motifs. The cap is what makes the
# confirm card's estimate meaningful — an unbounded batch is an unbounded bill.
MAX_MOTIFS_PER_JOB = 50

_SYSTEM = (
    "You are a literary translator localizing a NARRATIVE CRAFT library for a "
    "novel-writing tool. The entry below describes one reusable story pattern — its "
    "name, what it does, and the beats it runs through.\n"
    # Without this the model renders craft vocabulary as film/screenwriting jargon,
    # which reads wrong inside a prose-fiction tool. Same wording as the dev-time tool.
    "DOMAIN TERMS — these are PROSE-FICTION craft terms, not screenwriting ones: a "
    "'beat' is a unit of dramatic movement inside a scene (NOT a musical beat and NOT "
    "a screenplay beat sheet); a 'motif' is a reusable plot pattern; a 'role' is the "
    "function a character serves in the pattern; 'tension' is dramatic pressure.\n"
    "Return a JSON object with EXACTLY the same keys you were given, each value "
    "translated into {language}. Translate the VALUES only — never the keys. Keep "
    "proper nouns, keep the register (these are craft notes an author reads, so be "
    "concise and concrete, not flowery), and keep each value roughly the same length."
)

# A motif is 15-25 short, COHESIVE strings (a beat label only reads correctly against
# the motif's summary), so the whole entry goes in one call — splitting it would cost
# the model exactly the context that makes the wording good.
_MAX_TOKENS = 4096


def _context_block(payload: dict[str, Any]) -> str:
    """The motif's own name + summary, given to the model as CONTEXT, not as work.

    Translating `"the witness"` with no idea which story pattern it belongs to
    produces a literal, characterless result; naming the pattern first is what makes
    the craft vocabulary land.
    """
    name = payload.get("name") or ""
    summary = payload.get("summary") or ""
    return (f"This entry is the story pattern “{name}”"
            + (f" — {summary}" if summary else "") + ".")


def _schema_for(keys: list[str]) -> dict[str, Any]:
    """A JSON schema pinning the response to EXACTLY the keys we sent.

    Key-set identity enforced at the schema layer rather than only checked afterwards:
    a provider that honours the schema cannot drop or invent a key at all, and one
    that does not is caught by the post-hoc filter below. Belt and braces, because the
    failure mode (wording on the wrong beat) is silent.
    """
    return {
        "type": "object",
        "properties": {k: {"type": "string"} for k in keys},
        "required": list(keys),
        "additionalProperties": False,
    }


async def translate_one(
    llm: Any,
    motif: dict[str, Any],
    *,
    user_id: str,
    target_language: str,
    model_source: str,
    model_ref: str,
    trace_id: str | None = None,
    cancel_check: Any = None,
) -> dict[str, Any]:
    """Translate ONE motif. Returns an outcome dict; never raises for model reasons.

    ``{"status": "translated"|"nothing_to_translate"|"model_failed",
       "payload": {…}|None, "source_content_hash": "…",
       "translated": int, "fell_back": [key], "dropped": [key], "echoed": [key]}``
    """
    source_payload = extract_translatable(motif)
    entry = build_translation_entry(source_payload)
    flat = flatten_entry(entry)
    src_hash = translatable_hash(source_payload)

    if not flat:
        # No text at all — a structure-only motif. Refuse BEFORE spending: the user
        # would pay for a call that has nothing to say.
        return {"status": "nothing_to_translate", "payload": None,
                "source_content_hash": src_hash, "translated": 0,
                "fell_back": [], "dropped": [], "echoed": []}

    keys = sorted(flat)
    language = LANGUAGE_NAMES.get(target_language, target_language)
    messages = [
        {"role": "system", "content": _SYSTEM.format(language=language)},
        {"role": "user", "content": (
            f"{_context_block(source_payload)}\n\n"
            f"Translate every value into {language}:\n"
            + json.dumps({k: flat[k] for k in keys}, ensure_ascii=False, indent=1)
        )},
    ]

    content = await call_json(
        llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
        messages=messages, max_tokens=_MAX_TOKENS,
        job_meta={
            "extractor": "motif_translate",
            # The billing label (reference: the provider `operation` field is
            # quad-overloaded — relabel via job_meta, never by expanding the enum).
            "usage_purpose": "motif_translate",
            "motif_code": motif.get("code"),
            "target_language": target_language,
        },
        schema=_schema_for(keys), schema_name="motif_translation",
        temperature=0.2, trace_id=trace_id, cancel_check=cancel_check,
    )
    got = parse_critique_json(content or "") or {}

    # ── accept ONLY the keys we sent ────────────────────────────────────────
    # `dropped` is a key the model invented or renamed. Its source leaf simply keeps
    # its own wording (it lands in `fell_back`), so a drifted beat key can never move
    # wording onto a different beat — it can only fail to translate that one leaf.
    dropped = sorted(k for k in got if k not in flat)
    accepted: dict[str, str] = {}
    fell_back: list[str] = []
    echoed: list[str] = []
    for key in keys:
        val = got.get(key)
        if not isinstance(val, str) or not val.strip():
            fell_back.append(key)
            accepted[key] = flat[key]          # never blank
            continue
        if is_untranslated_echo(flat[key], val, target_language):
            echoed.append(key)
        accepted[key] = val

    if len(fell_back) == len(keys):
        # Nothing came back usable — do not write a "translation" that is a verbatim
        # copy of the source. A row like that reports `text_fallback: false` forever,
        # which is a lie the reader cannot see through.
        return {"status": "model_failed", "payload": None,
                "source_content_hash": src_hash, "translated": 0,
                "fell_back": fell_back, "dropped": dropped, "echoed": echoed}

    rebuilt = unflatten_entry(accepted)
    # The structural gate. Unknown keys are already filtered out above, so what this
    # catches is anything the ASSEMBLY could have broken — a mis-split dotted key, an
    # unflatten that produced a list where an object was expected. It raises, and the
    # caller turns that into a per-motif failure rather than a write.
    payload = parse_translation_entry(
        rebuilt, source_payload, where=f"{motif.get('code')}:{target_language}")

    return {
        "status": "translated", "payload": payload, "source_content_hash": src_hash,
        "translated": len(keys) - len(fell_back),
        "fell_back": fell_back, "dropped": dropped, "echoed": echoed,
    }


async def run_translate_motifs(
    pool: asyncpg.Pool,
    llm: Any,
    *,
    user_id: str,
    input: dict[str, Any],
    cancel_check: Any = None,
) -> dict[str, Any]:
    """Worker entry point — translate the named motifs into one target language.

    Partial success is the norm and is reported per motif: one motif whose model call
    failed must not discard the ones that succeeded (the user paid for all of them).
    """
    from app.db.repositories.motif_repo import MotifRepo

    target = str(input.get("target_language") or "").strip()
    if target not in LANGUAGE_NAMES:
        raise ValueError(f"translate_motif: unsupported target_language {target!r}")
    raw_ids = list(input.get("motif_ids") or [])
    if not raw_ids:
        raise ValueError("translate_motif: motif_ids is required")
    try:
        motif_ids = [UUID(str(m)) for m in raw_ids[:MAX_MOTIFS_PER_JOB]]
    except (ValueError, TypeError) as exc:
        raise ValueError("translate_motif: motif_ids must be UUIDs") from exc

    model_ref = str(input.get("model_ref") or "")
    model_source = str(input.get("model_source") or "user_model")
    if not model_ref:
        # Fail closed rather than reaching for a platform default: the whole point of
        # this path is that the USER's model spends the USER's money.
        raise ValueError("translate_motif: model_ref is required")

    book_id = input.get("book_id")
    force = bool(input.get("force"))
    repo = MotifRepo(pool)

    # THE TENANCY GATE, re-applied here rather than trusted from the proposal — a
    # `translate_motif` job is server-retryable, so the sweeper can re-drive it long
    # after the confirm that authorized it.
    #
    # Two arms, and both have to hold:
    #   · OWNERSHIP — `list_translatable` matches only `owner_user_id = caller`, plus
    #   · the BOOK GRANT for the shared-tier arm. `book_shared AND book_id = <the book
    #     named in the signed payload>` is not sufficient on its own: it proves the row
    #     belongs to that book, not that this caller may still write to it. A grant
    #     revoked between confirm and a re-drive would otherwise let a former
    #     collaborator's job keep writing.
    #
    # Fail-closed by construction: `authorize_book` resolves a book-service outage to
    # NONE → OwnershipError, so an unreachable grant service refuses the shared arm
    # rather than assuming it. The caller's OWN motifs are unaffected — they need no
    # grant — so an outage narrows the batch instead of failing it.
    book_uuid = UUID(str(book_id)) if book_id else None
    if book_uuid is not None:
        try:
            await authorize_book(
                get_grant_client(), book_uuid, UUID(user_id), GrantLevel.EDIT)
        except (OwnershipError, InsufficientGrant) as exc:
            logger.warning(
                "translate_motif: book grant re-check failed for book=%s user=%s: %s "
                "— shared-tier motifs dropped from this run", book_uuid, user_id, exc)
            book_uuid = None
    targets = await repo.list_translatable(UUID(user_id), motif_ids, book_id=book_uuid)
    by_id = {str(m["id"]): m for m in targets}

    results: list[dict[str, Any]] = []
    written = 0
    for mid in motif_ids:
        # Cancel between motifs, not only inside a call. `call_json` already threads the
        # check into the in-flight request, but a 50-motif batch is minutes of spending:
        # a user who cancels must stop being charged for the motifs not started yet, not
        # merely for the one mid-flight. Everything already written stays written.
        if cancel_check is not None and await cancel_check():
            results.append({"motif_id": str(mid), "status": "cancelled"})
            continue
        motif = by_id.get(str(mid))
        if motif is None:
            # Not owned, not shared-with-EDIT, or system tier. One uniform outcome —
            # "you may not translate this" — so the result cannot be used to probe
            # which motifs exist.
            results.append({"motif_id": str(mid), "status": "not_translatable"})
            continue
        code = motif.get("code")
        if (motif.get("original_language") or "en") == target:
            results.append({"motif_id": str(mid), "code": code,
                            "status": "already_original"})
            continue
        existing = await repo.get_translation_state(mid, target)
        # The authored guard is checked even under `force`. `force` means "re-buy the
        # machine translation", never "overwrite the human one" — and the upsert would
        # refuse the write anyway, so skipping this check would spend a real token to
        # produce something guaranteed to be discarded.
        if existing and existing["source"] == "authored":
            results.append({"motif_id": str(mid), "code": code,
                            "status": "authored_kept"})
            continue
        if not force and existing and not existing["stale"]:
            # Already fresh in this language — charging again buys nothing.
            results.append({"motif_id": str(mid), "code": code,
                            "status": "already_translated"})
            continue

        try:
            out = await translate_one(
                llm, motif, user_id=user_id, target_language=target,
                model_source=model_source, model_ref=model_ref,
                cancel_check=cancel_check,
            )
        except Exception as exc:  # noqa: BLE001 — one bad motif must not sink the batch
            logger.warning("translate_motif: %s failed: %r", code, exc)
            results.append({"motif_id": str(mid), "code": code,
                            "status": "failed", "error": str(exc)[:200]})
            continue

        if out["status"] == "translated":
            wrote = await repo.upsert_translation(
                mid, target, out["payload"],
                source_content_hash=out["source_content_hash"],
                translated_by=model_ref,
            )
            written += int(wrote)
            if not wrote:
                out["status"] = "authored_kept"
        results.append({
            "motif_id": str(mid), "code": code, "status": out["status"],
            "translated": out["translated"], "fell_back": out["fell_back"],
            "dropped": out["dropped"], "echoed": out["echoed"],
        })

    return {
        "target_language": target,
        "requested": len(motif_ids),
        "written": written,
        "results": results,
    }

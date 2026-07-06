"""Comprehension eval for the tool-catalog-simplification spec
(docs/specs/2026-07-06-tool-catalog-simplification.md).

Question: can the target local model (Gemma-4 26B-A4B QAT) correctly SELECT and
construct ARGUMENTS for the two new consolidated glossary tools
(`glossary_ontology_upsert`, `glossary_ontology_delete`) — BEFORE we invest in
the full production wiring (confirm-token flow, tenancy validation, batch
partial-results, the two find-tools visibility filters, the settings/GUI pin
feature)?

Real, not fake: calls the REAL target model through the REAL provider-registry
streaming endpoint (`loreweave_llm.Client.stream`, the same path
`stream_service.py` uses in production) with a STUB backend (no tool actually
executes — we only inspect what the model would have called). Also exercises
the REAL `search_catalog()` from `app.services.tool_discovery` (unmodified) to
check discovery ranking, offline (no model call needed — it's a deterministic
fuzzy-match, not an LLM decision).

Scope, deliberately: this tests schema comprehension + argument construction +
discovery ranking. It does NOT stand up the two-turn find_tools→activate loop,
does NOT hit a real glossary-service backend, and does NOT test the confirm-
token flow. Per the spec's rollout step 0 — this precedes, not replaces, the
full mechanism + cross-service live-smoke.

Run inside the chat-service container (has loreweave_llm + app.* on path):
    docker cp services/chat-service/eval/run_tool_catalog_eval.py infra-chat-service-1:/tmp/run_tool_catalog_eval.py
    docker exec infra-chat-service-1 python /tmp/run_tool_catalog_eval.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Any

from app.services.tool_discovery import search_catalog
from loreweave_llm.client import Client
from loreweave_llm.models import DoneEvent, ErrorEvent, StreamRequest, ToolCallEvent, TokenEvent

# ── Fixed dev-stack config (per CLAUDE.md test account) ──────────────────────
PROVIDER_REGISTRY_URL = "http://provider-registry-service:8085"
INTERNAL_TOKEN = "dev_internal_token"
TEST_USER_ID = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL_REF = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"  # Gemma-4 26B-A4B QAT (200K), tool_calling:true
BOOK_ID = "b_demo_0001"

SYSTEM_PROMPT = (
    "You are the LoreWeave writing assistant. The user is working in book_id="
    f"'{BOOK_ID}'. You manage this book's glossary ontology (genres, kinds, "
    "attributes) using the tools available to you. Call a tool when the user "
    "asks you to add, change, or remove something; otherwise respond in text."
)

# ── The two new tool schemas (exact wire shape — _meta stripped, matches
# what strip_tool_meta() sends to the model in production) ───────────────────

UPSERT_TOOL = {
    "type": "function",
    "function": {
        "name": "glossary_ontology_upsert",
        "description": (
            "Create or update book- or user-tier ontology rows (genre, kind, or attribute) — "
            "one call may mix creates and updates freely. Omit base_version on an item to create "
            "it; include the current base_version to update it with optimistic locking. Accepts "
            "1-50 items; each item succeeds or fails independently (not all-or-nothing)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["book", "user"], "description": "Which tenancy tier to write to."},
                "book_id": {"type": "string", "description": "Required when scope=book; omit when scope=user."},
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 50,
                    "items": {
                        "type": "object",
                        "properties": {
                            "level": {"type": "string", "enum": ["genre", "kind", "attribute"]},
                            "code": {"type": "string"},
                            "name": {"type": "string"},
                            "base_version": {"type": "string", "description": "Omit to create; include to update."},
                            "fields": {"type": "object", "description": "Level-specific fields (e.g. a kind's attribute list, an attribute's field_type)."},
                        },
                        "required": ["level", "code"],
                        "additionalProperties": True,
                    },
                },
            },
            "required": ["scope", "items"],
            "additionalProperties": False,
        },
    },
}

DELETE_TOOL = {
    "type": "function",
    "function": {
        "name": "glossary_ontology_delete",
        "description": (
            "Delete book- or user-tier ontology row(s). scope=book mints a confirm token — a "
            "human must approve before the delete executes; returns {confirm_token, preview}. "
            "scope=user executes immediately as a reversible soft-delete (undo via "
            "glossary_user_restore); returns {results}. Deleting an already-deleted row is a "
            "no-op, not an error."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["book", "user"]},
                "book_id": {"type": "string", "description": "Required when scope=book."},
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 50,
                    "items": {
                        "type": "object",
                        "properties": {
                            "level": {"type": "string", "enum": ["genre", "kind", "attribute"]},
                            "code": {"type": "string"},
                        },
                        "required": ["level", "code"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["scope", "items"],
            "additionalProperties": False,
        },
    },
}

ALL_TOOLS = [UPSERT_TOOL, DELETE_TOOL]


# ── Scenarios ─────────────────────────────────────────────────────────────

@dataclass
class Scenario:
    key: str
    prompt: str
    edge_case: str  # which §8 edge case (or "happy path") this targets
    expect_tool: str
    expect_scope: str | None = None
    expect_min_items: int = 1
    expect_max_items: int | None = None
    expect_base_version: str | None = None  # "absent" | "present" | "mixed" | None (don't check)
    expect_level: str | None = None
    notes: str = ""


SCENARIOS: list[Scenario] = [
    Scenario(
        key="S1_happy_create_book",
        prompt="In this book, add a new character kind called 'Antagonist'.",
        edge_case="happy path — create",
        expect_tool="glossary_ontology_upsert",
        expect_scope="book",
        expect_base_version="absent",
        expect_level="kind",
    ),
    Scenario(
        key="S2_happy_update_with_version",
        prompt="Update the 'Antagonist' kind's description to add a note about redemption arcs. Its current version is 'v3'.",
        edge_case="happy path — update via base_version presence",
        expect_tool="glossary_ontology_upsert",
        expect_scope="book",
        expect_base_version="present",
        expect_level="kind",
    ),
    Scenario(
        key="S3_batch_create",
        prompt="Add three new kinds to this book: Wizard, Rogue, and Cleric.",
        edge_case="8.7 — batch size / maxItems",
        expect_tool="glossary_ontology_upsert",
        expect_scope="book",
        expect_min_items=3,
        expect_max_items=3,
        expect_base_version="absent",
    ),
    Scenario(
        key="S4_mixed_batch",
        prompt="Create a new kind called 'Bard', and separately update the existing 'Wizard' kind (its version is 'v2') to add a spellbook field.",
        edge_case="8.1 — mixed create+update in one batch",
        expect_tool="glossary_ontology_upsert",
        expect_scope="book",
        expect_min_items=2,
        expect_max_items=2,
        expect_base_version="mixed",
    ),
    Scenario(
        key="S5_user_scope_no_book",
        prompt="Add a personal custom genre called 'Grimdark' to my account standards — it's not tied to any specific book.",
        edge_case="8.5 — scope=user, book_id should be omitted",
        expect_tool="glossary_ontology_upsert",
        expect_scope="user",
        expect_level="genre",
    ),
    Scenario(
        key="S6_delete_book_scope",
        prompt="Delete the 'Villain' kind from this book.",
        edge_case="8.8/8.9 — delete, book scope (confirm-gated server-side)",
        expect_tool="glossary_ontology_delete",
        expect_scope="book",
        expect_level="kind",
    ),
    Scenario(
        key="S7_delete_user_scope",
        prompt="Remove the 'OldGenre' entry from my personal account standards.",
        edge_case="8.8/8.9 — delete, user scope (direct, reversible)",
        expect_tool="glossary_ontology_delete",
        expect_scope="user",
    ),
    Scenario(
        key="S8_batch_delete",
        prompt="Delete the kinds 'Foo', 'Bar', and 'Baz' from this book.",
        edge_case="8.8 — one confirm token covers a batch",
        expect_tool="glossary_ontology_delete",
        expect_scope="book",
        expect_min_items=3,
        expect_max_items=3,
    ),
    Scenario(
        key="S9_legacy_phrasing_no_legacy_tool_available",
        prompt="Please create a brand-new kind called 'Sidekick' for this book.",
        edge_case="8.10/discovery — only the NEW tool is offered; must not hallucinate the old tool name",
        expect_tool="glossary_ontology_upsert",
        expect_scope="book",
        expect_base_version="absent",
        notes="Old glossary_book_create is NOT in the tools array at all — checks the model doesn't invent a call to a tool name it wasn't given.",
    ),
    Scenario(
        key="S10_attribute_fields",
        prompt="Add an attribute called 'strength_bonus' of type integer to the 'Wizard' kind.",
        edge_case="8.6 — open `fields` bag for a level-specific shape",
        expect_tool="glossary_ontology_upsert",
        expect_scope="book",
        expect_level="attribute",
        expect_base_version="absent",
    ),
    Scenario(
        key="S11_genre_level",
        prompt="Add a new genre called 'Cyberpunk-Noir' to this book.",
        edge_case="happy path — level=genre selection",
        expect_tool="glossary_ontology_upsert",
        expect_scope="book",
        expect_level="genre",
        expect_base_version="absent",
    ),
    Scenario(
        key="S12_larger_batch",
        prompt="Add 5 new kinds to this book, just by name for now: Alpha, Beta, Gamma, Delta, and Epsilon.",
        edge_case="8.7 — batch-size quality at N=5",
        expect_tool="glossary_ontology_upsert",
        expect_scope="book",
        expect_min_items=5,
        expect_max_items=5,
        expect_base_version="absent",
    ),
]


# ── Model call + tool-call reassembly ────────────────────────────────────────

async def call_model(client: Client, prompt: str) -> dict[str, Any]:
    """Runs one scenario turn. Returns {tool_calls: [{name, arguments(dict|None), raw}], text: str, error: str|None}."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    request = StreamRequest(
        model_source="user_model",
        model_ref=MODEL_REF,
        messages=messages,
        tools=ALL_TOOLS,
        tool_choice="auto",
        temperature=0.0,
        reasoning_effort="none",
    )
    frags: dict[int, dict[str, str]] = {}
    text_parts: list[str] = []
    error: str | None = None
    try:
        async for ev in client.stream(request, user_id=TEST_USER_ID):
            if isinstance(ev, ToolCallEvent):
                slot = frags.setdefault(ev.index, {"id": "", "name": "", "arguments": ""})
                if ev.id:
                    slot["id"] = ev.id
                if ev.name:
                    slot["name"] = ev.name
                slot["arguments"] += ev.arguments_delta
            elif isinstance(ev, TokenEvent):
                text_parts.append(ev.delta)
            elif isinstance(ev, ErrorEvent):
                error = f"{ev.code}: {ev.message}"
            elif isinstance(ev, DoneEvent):
                break
    except Exception as exc:  # noqa: BLE001 — surface as a scenario failure, not a crash
        error = f"transport/SDK exception: {exc!r}"

    tool_calls = []
    for idx in sorted(frags):
        f = frags[idx]
        parsed: dict | None = None
        parse_err: str | None = None
        try:
            parsed = json.loads(f["arguments"]) if f["arguments"] else {}
        except json.JSONDecodeError as exc:
            parse_err = str(exc)
        tool_calls.append({"name": f["name"], "arguments": parsed, "raw": f["arguments"], "parse_error": parse_err})

    return {"tool_calls": tool_calls, "text": "".join(text_parts), "error": error}


# ── Scoring ───────────────────────────────────────────────────────────────

@dataclass
class ScenarioResult:
    key: str
    edge_case: str
    verdict: str  # PASS | FAIL | ERROR
    reasons: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def score(scn: Scenario, outcome: dict[str, Any]) -> ScenarioResult:
    reasons: list[str] = []
    if outcome["error"]:
        return ScenarioResult(scn.key, scn.edge_case, "ERROR", [outcome["error"]], outcome)

    calls = outcome["tool_calls"]
    if not calls:
        return ScenarioResult(scn.key, scn.edge_case, "FAIL", [f"no tool call emitted; model said: {outcome['text'][:200]!r}"], outcome)
    if len(calls) > 1:
        reasons.append(f"emitted {len(calls)} tool calls, expected 1 ({[c['name'] for c in calls]})")

    call = calls[0]
    if call["name"] != scn.expect_tool:
        reasons.append(f"called {call['name']!r}, expected {scn.expect_tool!r}")
    if call["parse_error"]:
        reasons.append(f"arguments JSON did not parse: {call['parse_error']} (raw: {call['raw'][:300]!r})")
        return ScenarioResult(scn.key, scn.edge_case, "FAIL", reasons, outcome)

    args = call["arguments"] or {}
    if scn.expect_scope is not None and args.get("scope") != scn.expect_scope:
        reasons.append(f"scope={args.get('scope')!r}, expected {scn.expect_scope!r}")
    if scn.expect_scope == "user" and "book_id" in args and args.get("book_id"):
        reasons.append(f"book_id={args['book_id']!r} present but scope=user (should be omitted or empty — tolerated per IN-5, but worth noting)")
    if scn.expect_scope == "book" and not args.get("book_id"):
        reasons.append("scope=book but book_id missing")

    items = args.get("items")
    if not isinstance(items, list):
        reasons.append(f"items is not a list: {items!r}")
        items = []
    if len(items) < scn.expect_min_items:
        reasons.append(f"items has {len(items)} entries, expected >= {scn.expect_min_items}")
    if scn.expect_max_items is not None and len(items) != scn.expect_max_items:
        reasons.append(f"items has {len(items)} entries, expected exactly {scn.expect_max_items}")

    if scn.expect_base_version and items:
        presences = ["base_version" in it and it.get("base_version") for it in items]
        if scn.expect_base_version == "absent" and any(presences):
            reasons.append(f"expected base_version ABSENT on all items, got presence pattern {presences}")
        elif scn.expect_base_version == "present" and not all(presences):
            reasons.append(f"expected base_version PRESENT on all items, got presence pattern {presences}")
        elif scn.expect_base_version == "mixed" and (all(presences) or not any(presences)):
            reasons.append(f"expected a MIX of create+update in this batch, got presence pattern {presences} (all-same)")

    if scn.expect_level and items:
        levels = {it.get("level") for it in items}
        if levels != {scn.expect_level}:
            reasons.append(f"expected level={scn.expect_level!r} on all items, got {levels}")

    verdict = "PASS" if not reasons else "FAIL"
    return ScenarioResult(scn.key, scn.edge_case, verdict, reasons, outcome)


# ── Offline discovery-ranking check (no model call — real search_catalog()) ──

DISTRACTOR_CATALOG = [
    {"type": "function", "function": {
        "name": "glossary_book_create", "description": "Create a book-native genre, kind, or attribute row.",
        "_meta": {"visibility": "legacy", "synonyms": ["add a kind", "new genre", "create attribute"]},
    }},
    {"type": "function", "function": {
        "name": "glossary_user_create", "description": "Create a user-tier genre, kind, or attribute row in your personal standards library.",
        "_meta": {"visibility": "legacy", "synonyms": ["add a kind", "new genre"]},
    }},
    {"type": "function", "function": {
        "name": "glossary_search", "description": "Search this book's glossary entities by name or alias.",
        "_meta": {"visibility": "discoverable"},
    }},
    {"type": "function", "function": {
        "name": "composition_list_outline", "description": "List the outline arcs, chapters, and scenes for a work.",
        "_meta": {"visibility": "discoverable"},
    }},
    {"type": "function", "function": {
        "name": "translation_start_job", "description": "Start a translation job for a book or chapter.",
        "_meta": {"visibility": "discoverable"},
    }},
    {"type": "function", "function": {
        "name": "glossary_ontology_upsert",
        "description": UPSERT_TOOL["function"]["description"],
        "_meta": {"visibility": "discoverable", "synonyms": ["add a kind", "add a genre", "add an attribute", "edit a kind", "rename a kind", "new entity type"]},
    }},
]

DISCOVERY_QUERIES = ["add a new kind to the book", "create a genre", "make a new attribute type"]


def run_discovery_check() -> list[dict[str, Any]]:
    results = []
    for query in DISCOVERY_QUERIES:
        with_legacy, _ = search_catalog(DISTRACTOR_CATALOG, query, limit=3)
        without_legacy = [t for t in DISTRACTOR_CATALOG if t["function"].get("_meta", {}).get("visibility") != "legacy"]
        after_cat4, _ = search_catalog(without_legacy, query, limit=3)
        results.append({
            "query": query,
            "top_with_legacy_present": [m["name"] for m in with_legacy],
            "top_after_cat4_filter": [m["name"] for m in after_cat4],
        })
    return results


# ── Main ──────────────────────────────────────────────────────────────────

async def main() -> int:
    client = Client(base_url=PROVIDER_REGISTRY_URL, auth_mode="internal", internal_token=INTERNAL_TOKEN, user_id=TEST_USER_ID)
    results: list[ScenarioResult] = []
    try:
        for scn in SCENARIOS:
            outcome = await call_model(client, scn.prompt)
            res = score(scn, outcome)
            results.append(res)
            print(f"[{res.verdict}] {res.key} — {res.edge_case}")
            if res.reasons:
                for r in res.reasons:
                    print(f"    - {r}")
            if res.raw.get("tool_calls"):
                for c in res.raw["tool_calls"]:
                    print(f"    called: {c['name']}({json.dumps(c['arguments'])})")
    finally:
        await client.aclose()

    print("\n=== Discovery ranking (offline, real search_catalog) ===")
    disco = run_discovery_check()
    for d in disco:
        print(f"query={d['query']!r}")
        print(f"  with legacy tools present: {d['top_with_legacy_present']}")
        print(f"  after CAT-4 filter (simulated): {d['top_after_cat4_filter']}")

    passed = sum(1 for r in results if r.verdict == "PASS")
    failed = sum(1 for r in results if r.verdict == "FAIL")
    errored = sum(1 for r in results if r.verdict == "ERROR")
    print(f"\n=== Summary: {passed} PASS / {failed} FAIL / {errored} ERROR (of {len(results)}) ===")

    # Machine-readable dump for the report step.
    with open("/tmp/tool_catalog_eval_results.json", "w", encoding="utf-8") as fh:
        json.dump(
            {
                "scenarios": [
                    {"key": r.key, "edge_case": r.edge_case, "verdict": r.verdict, "reasons": r.reasons, "raw": r.raw}
                    for r in results
                ],
                "discovery": disco,
            },
            fh,
            indent=2,
            ensure_ascii=False,
        )
    return 0 if failed == 0 and errored == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

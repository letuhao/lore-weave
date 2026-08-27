"""Ask the PROVIDER directly what it does under this platform's real request shape.

D-TURN-STALLS-AFTER-THE-SURFACE-IS-BUILT names its own next step: "a provider-side
investigation (LM Studio under a 35-tool surface)". This is that step, kept in the repo so the
refutation is re-runnable rather than a number in a ledger row.

    python scripts/toolloop/provider_probe.py

DIAGNOSTIC ONLY. It writes to no store, creates no fixture, and touches no book. It talks to
the configured local provider directly — deliberately BESIDE the provider layer rather than
through it, because the whole question is whether the provider or the path to it is at fault,
and a probe that used the same path could not tell them apart.

WHAT IT ESTABLISHED, 2026-08-27 (all four refuted):

    tool surface     0 → 36 schemas (43.5 KB)   first byte 2.4–3.0s, every size
    prompt size      0 → 128 KB system block    2.6s → 7.6s, linear, no cliff
    reasoning        high / none / thinking     2.3–4.3s, none stalls
    endpoint         responses_api NOT declared for this model, so chat/completions is the path

Meanwhile the real turn hangs indefinitely on a request provider-registry logs at 15,591 input
tokens — SMALLER than the 18,762–20,187 of turns that complete.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: The exact surface a stalling turn advertised, read from the service's own
#: `agent-surface advertised` log line — not a set invented for the probe.
ADVERTISED = (
    "tool_list tool_load confirm_action web_search propose_edit glossary_propose_entity_edit "
    "glossary_confirm_action workflow_list workflow_load load_skill translation_update_settings "
    "kg_add_nodes book_read glossary_list_system_standards glossary_book_ontology_read "
    "kg_list_templates kg_project_list translation_start_job kg_propose_fact kg_view_read "
    "memory_remember glossary_propose_entities composition_package_tree glossary_adopt_standards "
    "translation_coverage kg_sync_available composition_error_block_edit "
    "glossary_book_sync_available kg_propose_edge glossary_entity_set_attributes "
    "composition_find_references kg_schema_read book_chapter_save_draft kg_project_create "
    "plan_compile book_list glossary_extract_entities_from_doc book_steering_list "
    "plan_propose_spec composition_diagnostics translation_retranslate_dirty book_update_details "
    "conversation_search chat_search_sessions run_subagent"
).split()

PROMPT = "Set the target language for this book's translation to Vietnamese."

#: Realistic system-prompt material — the platform's own rail language, so the token mix
#: resembles what the service sends. Filler would measure a different thing.
UNIT = (
    "ORDER IS LOAD-BEARING — categories BEFORE cast. Proposing a character before its category "
    "exists fails with 'unknown kind' and you will loop. Never skip ahead to the plan just "
    "because it looks like the flashier tool: a plan with no world behind it leaves the user "
    "with nothing they can open and read. See-standards, adopt-categories, apply-categories: "
    "look at the ready-made categories, adopt the ones that fit, then the user confirms ONCE. "
    "Capture-cast: feed the extractor the story AS THE USER TOLD IT. Save-cast: save the "
    "candidates under a category that already exists. "
)


def _catalog() -> dict:
    """The platform's own catalogue cache, loaded through the gate module that owns it."""
    spec = importlib.util.spec_from_file_location(
        "_gate", ROOT / "scripts" / "test_a_measured_turn_reaches_its_tool_gate.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return {td["function"]["name"]: td for td in mod._catalog()}


def _tool_payload(td: dict) -> dict:
    """🔴 NORMALISED, AND THE NORMALISATION IS ITSELF A FINDING. LM Studio rejects a
    `parameters` with no `properties` object outright — 400, `path: [n, function, parameters,
    properties], Required`. FOUR tools in the catalogue are shaped that way, and one of them,
    `glossary_list_system_standards`, is advertised on the stalling turn. It fails FAST, so it
    is not this stall; it would break any consumer that forwarded the schema unchanged."""
    fn = {k: v for k, v in td["function"].items()
          if k in ("name", "description", "parameters")}
    params = dict(fn.get("parameters") or {})
    params.setdefault("type", "object")
    params.setdefault("properties", {})
    fn["parameters"] = params
    return {"type": "function", "function": fn}


def probe(url: str, model: str, tools: list, system_kb: int, extra: dict,
          timeout: float) -> dict:
    system = (UNIT * ((system_kb * 1024) // len(UNIT) + 1))[:system_kb * 1024] if system_kb else ""
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": PROMPT}]
    body = {"model": model, "messages": msgs, "stream": True}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    body.update(extra)
    payload = json.dumps(body).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            first, n = None, 0
            for raw in resp:
                if not raw.strip():
                    continue
                if first is None:
                    first = time.time() - t0
                n += 1
                if n > 30:
                    break
        return {"kb": round(len(payload) / 1024, 1), "first": round(first or -1, 2),
                "total": round(time.time() - t0, 2), "outcome": "ok"}
    except Exception as exc:  # noqa: BLE001 — every failure is a result here, not an abort
        return {"kb": round(len(payload) / 1024, 1), "first": -1,
                "total": round(time.time() - t0, 2),
                "outcome": f"{type(exc).__name__}: {str(exc)[:90]}"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://localhost:1234/v1/chat/completions")
    ap.add_argument("--model", default="google/gemma-4-26b-a4b-qat")
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args()

    cat = _catalog()
    resolved = [x for x in ADVERTISED if x in cat]
    print(f"catalogue {len(cat)} tools · {len(resolved)} of the turn's {len(ADVERTISED)} "
          f"advertised names resolve · model {args.model}\n")

    print("A. TOOL SURFACE (no system prompt)")
    print(f"   {'tools':>6} {'req KB':>8} {'first':>8} {'total':>8}  outcome")
    for n in (0, 4, 10, 20, 30, len(resolved)):
        t = [_tool_payload(cat[x]) for x in resolved[:n]]
        r = probe(args.url, args.model, t, 0, {"max_tokens": 48}, args.timeout)
        print(f"   {n:>6} {r['kb']:>8} {r['first']:>8} {r['total']:>8}  {r['outcome']}")

    full = [_tool_payload(cat[x]) for x in resolved]
    print("\nB. SYSTEM PROMPT SIZE (full tool surface)")
    print(f"   {'sys KB':>6} {'req KB':>8} {'first':>8} {'total':>8}  outcome")
    for kb in (0, 4, 16, 32, 64, 128):
        r = probe(args.url, args.model, full, kb, {"max_tokens": 48}, args.timeout)
        print(f"   {kb:>6} {r['kb']:>8} {r['first']:>8} {r['total']:>8}  {r['outcome']}")

    print("\nC. REASONING (full surface + 16 KB system)")
    for label, extra in (
        ("max_tokens=48", {"max_tokens": 48}),
        ("no max_tokens", {}),
        ("reasoning_effort=high", {"reasoning_effort": "high"}),
        ("reasoning_effort=none", {"reasoning_effort": "none"}),
        ("chat_template thinking=True",
         {"chat_template_kwargs": {"thinking": True, "enable_thinking": True}}),
    ):
        r = probe(args.url, args.model, full, 16, extra, args.timeout)
        print(f"   {label:<30} first={r['first']:>6} total={r['total']:>6}  {r['outcome']}")

    print("\nA stall would show as a timeout in the `outcome` column. Every row answering in "
          "seconds is the refutation, not a pass.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""Build a batch's scenarios from each tool's OWN declared synonyms.

🔴 WHY THE PROMPT MUST NOT BE MINE. A prompt I invent proves only that I can phrase a request the
model happens to like — and when the model then reaches the tool, the run says nothing about
whether a user would have reached it. Worse, when the model DOESN'T reach it, an invented prompt
gives the finding an escape hatch: "maybe I asked badly."

`_meta.synonyms` closes that. It is the tool's own published claim about what a user says to reach
it — the same list the surfacing layer matches against. So a scenario built from it turns a miss
into a defect BY DEFINITION: the tool declared it answers "outline" questions, the turn asked an
outline question, the tool was not reached. There is no phrasing argument left to have.

Measured 2026-08-14 against the live catalogue: 228 of 315 tools declare synonyms. The other 87
are reported by name rather than skipped — a tool that quietly drops out of a batch reads as a
tool that passed, and R1's answerability pass is equally blind to them. That silence is the
subject of R2, and this script's job is to make it countable rather than invisible.

What this CANNOT do, stated plainly: it cannot invent the required arguments for a write tool
whose target does not exist yet. Write scenarios therefore get their substrate from a recipe keyed
on the tool's declared `scope`, and a tool whose recipe is missing is emitted with
`"needs_substrate": true` rather than emitted broken.

Usage:
    python scripts/toolloop/scengen.py --tools book_read,composition_list_outline --out batch.json
    python scripts/toolloop/scengen.py --next 5 --out batch.json      # next 5 in RUNBOOK order
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import catalog  # noqa: E402

LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
MODEL_REF = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"  # local gemma; resolved, see LOCAL_TEST_ENV.md

#: Plain user prose. Never the tool name, never an argument, never a JSON fragment — the LIVE bar
#: is void the moment I type either.
#:
#: 🔴 ONE TEMPLATE CANNOT TAKE EVERY SYNONYM, and the first version proved it by emitting "Show me
#: the what is in this book for this book." A declared synonym list mixes three grammatical kinds
#: freely — `composition_package_tree` alone declares a noun phrase ("book structure"), a bare
#: command ("ls", "orient me") and a question ("what is in this book"). Slotting all three into
#: one frame produces prose no user would type, and a prompt no user would type cannot support
#: the claim that a user's phrasing fails to reach the tool. So the synonym is CLASSIFIED first
#: and the frame chosen to match it.
QUESTION_STARTS = ("what", "which", "who", "where", "when", "why", "how", "is ", "are ",
                   "do ", "does ", "can ", "should ")
VERB_STARTS = (
    "list", "show", "get", "read", "open", "pull", "find", "search", "look",
    "save", "write", "create", "make", "add", "new", "start", "begin", "build", "draft",
    "edit", "change", "update", "set", "fix", "rename", "move", "reorder",
    "delete", "remove", "clear", "archive", "restore", "purge", "revert",
    "propose", "suggest", "plan", "run", "check", "adopt", "apply", "merge", "orient", "ls",
)

#: {s} is the synonym. Chosen by kind, so the result reads like something a person typed.
FRAMES = {
    ("R", "question"): "{S}?",
    ("R", "verb"): "Can you {s} for me?",
    ("R", "noun"): "Show me the {s} for this book.",
    ("W", "question"): "{S}? Sort it out for me.",
    ("W", "verb"): "Please {s}.",
    ("W", "noun"): "I want to work on the {s} — go ahead.",
}

#: 🔴 A WRITE PROMPT BUILT FROM A SYNONYM ALONE NAMES NO TARGET, AND THE MODEL IS RIGHT TO REFUSE
#: IT. Measured 2026-08-14, batch 1: "Please plan a novel.", "Please change an existing entity's
#: attribute." and "Please write a chapter." each produced ZERO tool calls on 3 of 3 runs — and
#: reading the replies, the model asked which entity, which chapter, and what the story is. That
#: is correct behaviour, so scoring it as "did not reach the tool" would have manufactured three
#: defects out of my own underspecified prompts.
#:
#: A synonym is a ROUTING hint, not a request. A real request also carries a target, and the only
#: legitimate source for one is the fixture the turn is actually looking at — so these clauses
#: name the seeded substrate in prose, the way a user would. Still no tool name and no argument
#: name: "set Aldric Vane's rank to Knight of the Ember" is a sentence, not a JSON body.
SPECIFICS: dict[str, str] = {
    "glossary_entity_set_attributes":
        " Set Aldric Vane's rank to Knight of the Ember.",
    "glossary_propose_new_attribute":
        " Add a 'rank' detail to Aldric Vane and set it to Knight of the Ember.",
    "book_chapter_create":
        " Add a new one after what I have, called The Drowned Road, about Mira leading Aldric "
        "through the marsh.",
    "plan_propose_spec":
        " The idea: a courier named Aldric carries a book that rewrites whoever reads it, and the "
        "Pale Regent wants it back. Grimdark fantasy, one continent, about thirty chapters.",
    "composition_outline_node_edit":
        " Rename The Ember Codex chapter to The Ember Codex Opens.",
    "glossary_ontology_upsert":
        " Add a category called Factions for the groups in this world.",
    "plan_compile":
        " Use the plan I already have for this book.",
}

#: Substrate recipes keyed on the tool's declared `scope`. Deliberately small: the fixture already
#: provisions a book, a chapter and a composition project, so a recipe only adds what a scope
#: needs ON TOP of that. A read scenario over an EMPTY store cannot distinguish a truthful "you
#: have none" from a fabricated one, so every recipe seeds something NAMED.
RECIPES: dict[str, list[dict]] = {
    "project": [
        {"tool": "composition_outline_node_create",
         "args": {"project_id": "{project_id}", "kind": "chapter", "title": "The Ember Codex",
                  "synopsis": "Aldric reaches Hollow Keep and is given the Codex."}},
        {"tool": "composition_canon_rule_create",
         "args": {"project_id": "{project_id}",
                  "text": "The Pale Regent is never named aloud by a living character."}},
    ],
    "book": [
        # Adopt the ontology through the REST edge first: an entity cannot be proposed into a
        # kind the book has not adopted, and the whole batch failed provisioning with "unknown
        # kind: character" until this step existed. glossary_adopt_standards (the MCP tool) is
        # deliberately NOT used — it mints a confirm_token and writes nothing at call time, so a
        # fixture built on it fails the same way while looking like a glossary defect.
        {"rest": {"domain": "glossary", "method": "POST",
                  "path": "/v1/glossary/books/{book_id}/adopt",
                  "json": {"genres": ["universal"],
                           "kinds": ["character", "location", "item"]}}},
        {"tool": "glossary_propose_entities",
         "args": {"book_id": "{book_id}",
                  "items": [{"kind": "character", "name": "Aldric Vane"},
                            {"kind": "character", "name": "Mira Solene"},
                            {"kind": "item", "name": "Ember Codex"}]}},
    ],
    "user": [],
    "none": [],
}


def phrase_kind(syn: str) -> str:
    """question | verb | noun — which grammatical slot this synonym can fill."""
    s = syn.strip().lower()
    if s.startswith(QUESTION_STARTS):
        return "question"
    first = s.split()[0] if s.split() else s
    if first in VERB_STARTS:
        return "verb"
    return "noun"


def _prompt_for(name: str, cat: dict) -> tuple[str | None, str | None]:
    """(prompt, synonym_used) — or (None, None) when the tool declares nothing to go on."""
    syns = catalog.synonyms(name, cat)
    if not syns:
        return None, None
    tier = (cat.get(name, {}).get("meta") or {}).get("tier", "R")
    slot = "R" if tier == "R" else "W"
    # Prefer the kind that reads most naturally for the intent — a question for a read, an
    # imperative for a write — and prefer the LONGEST candidate within that kind, because the
    # most specific phrasing is the one least likely to be a generic word half the catalogue also
    # claims ("list", "get", "read"). A generic synonym that fails to route is a much weaker
    # finding than a specific one that does.
    prefer = ["question", "noun", "verb"] if slot == "R" else ["verb", "question", "noun"]
    buckets: dict[str, list[str]] = {}
    for s in syns:
        buckets.setdefault(phrase_kind(s), []).append(s)
    for kind in prefer:
        if buckets.get(kind):
            syn = sorted(buckets[kind], key=len, reverse=True)[0]
            frame = FRAMES[(slot, kind)]
            return frame.format(s=syn, S=syn[:1].upper() + syn[1:]), syn
    return None, None


def _prompt_with_target(name: str, cat: dict) -> tuple[str | None, str | None, bool]:
    """(prompt, synonym, grounded) — the synonym-derived ask plus, for a write, the target."""
    prompt, syn = _prompt_for(name, cat)
    if prompt is None:
        return None, None, False
    tier = (cat.get(name, {}).get("meta") or {}).get("tier", "R")
    extra = SPECIFICS.get(name, "")
    if tier != "R" and extra:
        return prompt + extra, syn, True
    return prompt, syn, tier == "R"


def build(names: list[str], cat: dict | None = None) -> dict:
    cat = cat if cat is not None else catalog.load()
    scenarios, missing = [], []
    for name in names:
        entry = cat.get(name)
        if entry is None:
            missing.append({"tool": name, "why": "not in the federated catalogue"})
            continue
        meta = entry.get("meta") or {}
        tier = meta.get("tier", "R")
        scope = meta.get("scope", "book")
        prompt, syn, grounded = _prompt_with_target(name, cat)
        sc = {
            "id": name.replace("_", "-"),
            "tool_under_test": name,
            "expect_tool": name,
            "intent": "read" if tier == "R" else "write",
            "tier": tier,
            "scope": scope,
            "model_ref": MODEL_REF,
            "prompt": prompt,
            "prompt_source": f"_meta.synonyms[{syn!r}]" if syn else None,
            # A write whose prompt names no target measures my phrasing, not the product.
            "needs_target": (tier != "R" and name not in SPECIFICS),
            # A Tier-A/W tool SUSPENDS on an approval card, and the user clicking Approve is
            # part of the path under test — so a write scenario approves ONCE. A read scenario
            # leaves it null: approving on a turn that only asked to look would make the harness
            # itself the thing that wrote, and the store diff would then be evidence about me.
            # `approved_once`, never `approved_always` — the latter persists a standing allowlist
            # row on the real account, which is precisely the mechanism that let a 2026-07-11
            # approval silently auto-execute four chapter overwrites weeks later.
            "approve": None if tier == "R" else "approved_once",
            "seed": RECIPES.get(scope, []),
            "falsifier": None,
            "ship_audit": None,
        }
        if prompt is None:
            # NOT skipped. A tool that vanishes from the batch reads as a tool that passed.
            sc["needs_prompt"] = True
            sc["prompt"] = f"__HAND_WRITE_ME__ ({name} declares no synonyms)"
            missing.append({"tool": name, "why": "declares no _meta.synonyms — R1's "
                                                 "answerability pass is blind to it too (R2)"})
        if scope not in RECIPES:
            sc["needs_substrate"] = True
        scenarios.append(sc)
    return {"scenarios": scenarios, "_generator": "scengen.py", "_needs_attention": missing}


def next_from_ledger(n: int) -> list[str]:
    """The next n SHIPPABLE tools in RUNBOOK order: group A, then B, then C, skipping concluded.

    The ledger is the progress authority, so the batch is DERIVED rather than chosen. A batch I
    pick is a batch I can pick easy tools for.

    🔴 DEPRECATED TOOLS ARE NOT DRAWN. The ordering groups were derived from the whole federated
    catalogue, so they include tools carrying `visibility=legacy` / `_meta.superseded_by`. Batch 2
    drew two of them (`glossary_list_ai_suggestions`, `glossary_propose_new_attribute`) and I
    spent most of a session treating their silence as a defect — when a deprecated tool going
    unreached is the migration working, and its successor is what must ship.

    The denominator is the RELEASE SURFACE (owner's decision 2026-08-14: ship every non-deprecated
    tool, because the platform cannot release without them). Drawing from anything wider spends
    batches on tools nobody will run.
    """
    d = json.loads(LEDGER.read_text(encoding="utf-8"))
    tools = d.get("tools") or {}
    done = {k for k, v in tools.items() if v.get("state") in ("proven", "blocked")}
    den = d.get("denominator") or {}
    shippable = set(den.get("shippable_list") or [])
    order: list[str] = []
    order += [r["tool"] for r in (den.get("group_A") or [])]
    order += [r["tool"] for r in (den.get("group_B") or [])]
    order += list(den.get("group_C") or [])
    picked = [t for t in order if t not in done and (not shippable or t in shippable)]
    # Anything shippable that the ordering groups never listed still has to ship — append it so
    # the tail of the release surface cannot be silently unreachable by the derivation itself.
    picked += [t for t in sorted(shippable) if t not in done and t not in set(order)]
    return picked[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", default="", help="comma-separated tool names")
    ap.add_argument("--next", type=int, default=0, help="take the next N in RUNBOOK order")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    names = [t.strip() for t in a.tools.split(",") if t.strip()]
    if a.next:
        names = next_from_ledger(a.next)
    if not names:
        print("nothing to build: pass --tools or --next")
        return 2

    out = build(names)
    pathlib.Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    print(f"{len(out['scenarios'])} scenario(s) -> {a.out}")
    for sc in out["scenarios"]:
        print(f"  {sc['expect_tool']:<38} {sc['tier']}/{sc['scope']:<8} {sc['prompt']}")
    if out["_needs_attention"]:
        print("\nNEEDS ATTENTION (reported, not skipped):")
        for m in out["_needs_attention"]:
            print(f"  {m['tool']}: {m['why']}")
    print("\nEvery scenario still needs a falsifier and a ship_audit before the gate will pass "
          "it — those are judgement and are deliberately not generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

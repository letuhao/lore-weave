"""CP-5 · the tools chat-service serves ITSELF are registrable — and their names may lie.

🔴 **THE BLOCK THIS CLOSES, AND IT WAS NOT THE ONE THE BOARD WROTE DOWN.** The plan said
`compose_prose` could not be admitted because *"`derive.py` reads the federated snapshot alone —
union the local tools"*. `derive.py` reads no file (`derive_all` takes the catalogue as an
argument), and the union alone would have changed nothing: all four local tools carried **no
`_meta` at all**, so there was no `tier`, therefore no lane, and `resolve_service` is a NAME-PREFIX
table that answers `glossary-service` for `glossary_propose_entity_edit` — a tool glossary-service
does not serve.

So three things had to be true together, and each has a guard here:

1. the tools **declare** a tier and a scope, like the 315 that always did;
2. the owner comes from the **definition** where the name would lie about it;
3. the catalogue the admission path reads **contains them at all**.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.agentruntime.derive import (
    Underivable,
    coverage,
    declared_service,
    derive_one,
    resolve_service,
)
from app.services.local_tools import local_tool_defs, local_tool_names

BASELINE = (pathlib.Path(__file__).resolve().parents[3]
            / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json")


def _snapshot() -> list[dict]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["tools"]


class TestEveryLocalToolDeclaresWhatTheFederatedOnesDeclare:

    @pytest.mark.parametrize("d", local_tool_defs(),
                             ids=lambda d: d.get("function", d).get("name"))
    def test_IT_DECLARES_A_TIER_AND_A_SCOPE(self, d):
        """🔴 **These four were on the wire for weeks declaring neither**, while
        `declared_lane`'s docstring said *"measured on the live catalogue: 315/315 tools declare a
        tier, so nothing legitimate is demoted today"* — measured on the population that excluded
        the only ones that did not."""
        meta = d.get("function", d).get("_meta") or {}
        assert meta.get("tier") in ("R", "A", "W", "S"), (
            f"{d.get('function', d).get('name')} declares no tier, so it has no lane and cannot be "
            f"derived — which is what kept it out of the contract"
        )
        assert meta.get("scope") in ("book", "user", "project", "none")

    @pytest.mark.parametrize("d", local_tool_defs(),
                             ids=lambda d: d.get("function", d).get("name"))
    def test_IT_DERIVES_TO_CHAT_SERVICE(self, d):
        assert derive_one(d).declaration.source_path == "services/chat-service/"

    def test_COMPOSE_PROSE_IS_INERT_AND_IS_NOW_THE_ONLY_LOCAL_TOOL(self):
        """V7 (2026-09-03) — the three confirm tools LEFT this set, so asserting their lane here
        would `KeyError`. They are ai-gateway directive tools now and declare their own tier there
        (`confirm-tools.ts` `_meta.tier: "W"`, pinned by `test/confirm-tools.spec.ts`).

        🔴 THE COUNT IS ASSERTED, not just compose_prose's lane. This population went 4 -> 1, and
        the vacuity register flagged exactly this file: a parametrize over a shrinking set keeps
        passing while covering less and less. If it ever reaches 0 the guard must RED, not sail.
        """
        defs = local_tool_defs()
        assert len(defs) == 1, (
            f"chat-service serves {len(defs)} tools of its own: "
            f"{[d.get('function', d)['name'] for d in defs]}. Every addition needs a reason it "
            f"cannot be a domain or gateway tool — that reasoning is what architecture v1 lacked.")
        by_name = {d.get("function", d)["name"]: derive_one(d) for d in defs}
        assert by_name["compose_prose"].lane == "read", (
            "compose_prose streams a second model and returns its text; the tools that carry the "
            "write are separate")

class TestTheDefinitionOutranksTheNameWhenTheyDisagree:

    def test_THE_NAME_NO_LONGER_LIES__THE_TOOL_MOVED_TO_ITS_DECLARED_OWNER(self):
        """🔴 THIS TEST'S PREMISE WAS REMOVED BY FIXING IT, WHICH IS THE OUTCOME IT WANTED.

        It used to read: `glossary_propose_entity_edit` is named into glossary-service's namespace
        while being a chat-service frontend tool, so the prefix table answers with total
        confidence and is WRONG. That was the whole reason `served_by` exists.

        V7 moved the tool to ai-gateway, and it now declares `served_by: "ai-gateway"` on the live
        wire. The prefix table still says glossary-service — the trap is unchanged — but there is
        no longer a chat-service definition for it to mislead anyone about.

        Kept rather than deleted because the INVARIANT is what matters and it still holds: a
        declared owner outranks a name prefix. Asserted now on the tool that remains.
        """
        assert resolve_service("glossary_propose_entity_edit") == "glossary-service", (
            "the prefix table stopped guessing; the trap this guards is gone and so is the guard")
        assert not [d for d in local_tool_defs()
                    if d.get("function", d)["name"] == "glossary_propose_entity_edit"], (
            "chat-service is serving glossary_propose_entity_edit again — the exact name-lies-"
            "about-owner shape that made served_by necessary")

    def test_A_DECLARED_OWNER_THAT_NAMES_NOTHING_IS_REFUSED_NOT_IGNORED(self):
        """Falling back to the prefix on a typo is the failure the declaration exists to remove: it
        turns `chat-serivce` into a confident, wrong, WRITTEN-DOWN owner."""
        bad = {"type": "function", "function": {
            "name": "glossary_typo_tool", "description": "x", "parameters": {},
            "_meta": {"tier": "R", "served_by": "chat-serivce"}}}
        with pytest.raises(Underivable, match="not a service directory"):
            derive_one(bad)

    def test_NO_FEDERATED_TOOL_DECLARES_ITS_OWN_OWNER(self):
        """🔴 **The forgery answer, and it is a GATE rather than a rule in the function.** The
        override is reachable today only by tools this repository serves itself. The day a provider
        federates a `served_by`, this reds and a human decides whether routing or the declaration is
        the liar — which is the visible-drift treatment the prefix table already gets, not a silent
        resolution in favour of either side."""
        claimed = [t["name"] for t in _snapshot() if (t.get("_meta") or {}).get("served_by")]
        assert claimed == [], (
            f"{claimed} declare an owner from OUTSIDE this repository; `declared_service` would "
            f"honour it over gateway routing without anyone having looked"
        )


class TestTheAdmissionCatalogueContainsThem:

    def test_THE_UNION_DERIVES_COMPLETELY(self):
        """§4 scopes rung 2 to *all* the tools, and the producer's own coverage number is the
        honest place for that to be visible: the denominator is the input, never the output."""
        cov = coverage(_snapshot() + local_tool_defs())
        assert cov["unresolved"] == 0, cov["by_field"]
        assert cov["total"] == cov["derived"] == len(_snapshot()) + len(local_tool_defs())

    def test_A_LOCAL_NAME_NEVER_COLLIDES_WITH_A_FEDERATED_ONE(self):
        """A name served both locally and federated is a real ambiguity about which definition a
        turn dispatches. The admit script refuses to pick a side; this says there is no side to
        pick today."""
        assert local_tool_names() & {t["name"] for t in _snapshot()} == set()

    def test_COMPOSE_PROSE_IS_IN_THE_SET_BECAUSE_IT_IS_THE_POINT_OF_THE_JOURNEY(self):
        """The essential set's `compose` role — and the row that was blocked. A guard rather than a
        comment because this membership is what the block was about."""
        assert "compose_prose" in local_tool_names()

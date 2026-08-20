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

    def test_THE_CONFIRM_TOOLS_ARE_WRITES_AND_COMPOSE_IS_INERT(self):
        """The tiers are READ OFF the code, not chosen. `confirm_action`'s own section header says
        *"generic Tier-W/S confirm"*; the propose tool suspends for a human Apply. `compose_prose`
        streams a second model and returns its text — nothing is written, and the tools that do
        carry the write (`propose_edit`, `book_chapter_save_draft`) are separate."""
        by_name = {d.get("function", d)["name"]: derive_one(d) for d in local_tool_defs()}
        assert by_name["compose_prose"].lane == "read"
        for w in ("confirm_action", "glossary_confirm_action", "glossary_propose_entity_edit"):
            assert by_name[w].lane == "write", f"{w} must not be derivable as anything but a write"


class TestTheDefinitionOutranksTheNameWhenTheyDisagree:

    def test_THE_NAME_ACTUALLY_LIES_TODAY_SO_THIS_IS_NOT_HYPOTHETICAL(self):
        """🔴 The whole reason `served_by` exists. `glossary_propose_entity_edit` is named into
        glossary-service's namespace and is a chat-service FRONTEND tool — executed in the browser
        after a human Apply. The prefix table answers with total confidence, and it is wrong."""
        assert resolve_service("glossary_propose_entity_edit") == "glossary-service"
        decl = [d for d in local_tool_defs()
                if d["function"]["name"] == "glossary_propose_entity_edit"][0]
        assert declared_service(decl) == "chat-service"
        assert derive_one(decl).declaration.source_path == "services/chat-service/", (
            "the manifest would attribute this tool to a team that has never heard of it, and C-0 "
            "reads the owner out of exactly this path"
        )

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

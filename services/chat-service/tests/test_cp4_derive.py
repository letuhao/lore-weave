"""CP-4 — the declaration PRODUCER, checked against the frozen 315-tool baseline.

Hermetic on purpose: the baseline lives in `contracts/agent-runtime-baseline/tools-list.snapshot.json`
and is already inside the gate mirror, so these run in the census and the falsification runner. The
live gateway is measured separately; a suite that needed docker would be a suite that gets skipped.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.agentruntime.derive import (
    LANE_BY_TIER,
    PROVIDERS,
    Derived,
    Underivable,
    coverage,
    derive_all,
    derive_one,
    resolve_service,
    token_cost,
)

_REPO = pathlib.Path(__file__).resolve().parents[3]
_BASELINE = _REPO / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json"


@pytest.fixture(scope="module")
def baseline() -> list[dict]:
    doc = json.loads(_BASELINE.read_text(encoding="utf-8"))
    return doc["tools"]


class TestTheProducerReachesTheWholeCatalogue:
    """CP-4's real deliverable: a mechanism, and a coverage fraction over a denominator it did not
    choose."""

    def test_THE_DENOMINATOR_IS_THE_CATALOGUE_NOT_WHAT_THE_PRODUCER_MANAGED(self, baseline):
        cov = coverage(baseline)
        assert cov["total"] == len(baseline), (
            "the reported total is not the input size, so the fraction describes a set the caller "
            "did not hand in — every denominator this run has self-derived has read 'done'"
        )
        assert cov["derived"] + cov["unresolved"] == cov["total"]

    def test_EVERY_TOOL_IN_THE_FROZEN_BASELINE_DERIVES(self, baseline):
        cov = coverage(baseline)
        assert cov["unresolved"] == 0, (
            f"{cov['unresolved']} of {cov['total']} tools do not derive: {cov['by_field']}. Each is "
            f"a field no registered source supplies — report it and name the source that would, "
            f"never hand-author the row to make the number look complete"
        )
        assert cov["derived"] == 315, (
            f"derived {cov['derived']}, expected the frozen baseline's 315 — if the baseline moved, "
            f"that is a NEW CONTROL GROUP, not a correction (see the snapshot's own header)"
        )

    def test_EVERY_INPUT_LANDS_IN_EXACTLY_ONE_LIST(self, baseline):
        """A producer that silently dropped what it could not handle would report 100% of what it
        chose to attempt."""
        derived, unresolved = derive_all(baseline)
        ids = [d.declaration.id for d in derived] + [u.tool for u in unresolved]
        assert len(ids) == len(baseline)
        assert len(set(ids)) == len(ids), "a tool appears twice across the two lists"


class TestTheOwnerIsDerivedAndNotGuessedFromTheName:
    """C-0 requires the owner derived; C-1 forbids inferring it from a name. Both, at once."""

    def test_THE_CASE_A_PREFIX_GUESS_GETS_WRONG(self):
        """`settings_*` is served by provider-registry-service. There is no `settings-service`.

        This is the single case that justifies `PROVIDERS` existing at all: the obvious derivation
        — service = f"{prefix}-service" — is wrong here, and wrong silently, producing a
        `source_path` under a directory this repository does not contain.
        """
        assert resolve_service("settings_provider_inventory") == "provider-registry-service"
        assert not (_REPO / "services" / "settings-service").exists(), (
            "a settings-service directory now exists, so the mapping above may no longer be the "
            "interesting case — recheck which service actually serves settings_*"
        )

    def test_EVERY_DERIVED_SOURCE_PATH_IS_A_REAL_DIRECTORY(self, baseline):
        """The strongest available check on the table: C-0 reads the owner out of this path, and a
        path naming a directory that does not exist is an owner nobody can be held to."""
        derived, _ = derive_all(baseline)
        missing = sorted({d.declaration.source_path for d in derived
                          if not (_REPO / d.declaration.source_path).is_dir()})
        assert missing == [], f"{missing} — derived source paths that name no directory"

    def test_A_NAME_NO_PROVIDER_CLAIMS_IS_REPORTED_NOT_DEFAULTED(self):
        with pytest.raises(Underivable) as exc:
            derive_one({"name": "zzz_unclaimed", "description": "x",
                        "_meta": {"tier": "R"}})
        assert exc.value.field_name == "owning_service"
        assert "guessing" in str(exc.value)


class TestTheFacetsAreDerivedNotDeclared:
    def test_A_TOOL_WITH_NO_DECLARED_TIER_HAS_NO_LANE(self):
        """The fail-safe arm, matching `tool_discovery.declared_lane`. An undeclared lane must not
        become `read` by default — reads sort first into the always-advertised set."""
        with pytest.raises(Underivable) as exc:
            derive_one({"name": "book_thing", "description": "x", "_meta": {}})
        assert exc.value.field_name == "lane"

    def test_THE_TWO_LANE_MAPS_AGREE(self):
        """`derive` and the legacy surface each hold the tier→lane map; importing across that seam
        would couple the membrane to the surface it replaces, so a gate keeps them equal instead."""
        from app.services.tool_discovery import _LANE_BY_TIER

        assert dict(LANE_BY_TIER) == dict(_LANE_BY_TIER), (
            "the membrane and the legacy surface disagree about what a tier means, so a declaration "
            "would be ranked in one lane and advertised in another"
        )

    def test_COST_IS_A_FUNCTION_OF_THE_DEFINITION_AND_HAS_NO_FIELD_TO_FORGE(self, baseline):
        """🔴 The row schema refuses a hand-typed `cost` because `{"cost": 1000000000}` was measured
        steering `TakeWhileBudget`, and no value bound tells a forged integer from a real one. This
        asserts the shape that removes the question: `Derived` carries a cost recomputed from the
        bytes, and there is no input field a caller could fill instead.
        """
        derived, _ = derive_all(baseline)
        assert derived, "no rows derived; this guard would be green over nothing"
        for d in derived[:50]:
            assert d.cost > 0
        # `Declaration` — the untrusted INPUT to admission — must have no cost field at all. A
        # declaration that could state its own cost is a declaration that could state its own rank.
        from app.agentruntime.contract import Declaration

        assert "cost" not in Declaration.__dataclass_fields__, (
            "Declaration carries a `cost` field, so the value a caller supplies could reach the "
            "ranking; the whole point is that there is nothing to fill in"
        )
        # The definition is the only input. Two defs differing only in bytes differ in cost;
        # a def that STATES a cost cannot lower its own.
        cheap = {"name": "book_x", "description": "x", "_meta": {"tier": "R"}}
        forged = {"name": "book_x", "description": "x" * 4000, "_meta": {"tier": "R"},
                  "cost": 1}
        assert token_cost(forged) > token_cost(cheap), (
            "a definition claiming `cost: 1` lowered its own derived cost — the number must come "
            "from the bytes, which is what makes the forgery inexpressible rather than merely "
            "refused"
        )


class TestTheProviderTableIsAClaimAboutAnotherService:
    def test_NO_TWO_PROVIDERS_CLAIM_THE_SAME_NAMESPACE(self):
        seen: dict[str, str] = {}
        for _name, service, prefixes in PROVIDERS:
            for p in prefixes:
                assert p not in seen, (
                    f"namespace {p!r} is claimed by both {seen[p]} and {service}; the winner would "
                    f"be whichever row is listed first"
                )
                seen[p] = service

    def test_LONGEST_PREFIX_WINS_SO_THE_RULE_IS_TOTAL(self):
        """No overlapping pair exists today; the rule is total anyway so that the ambiguity is not
        discovered later by whichever entry happened to be listed first."""
        assert resolve_service("book_list") == "book-service"
        assert resolve_service("world_create") == "book-service"
        assert resolve_service("plan_validate") == "composition-service"
        assert resolve_service("lore_ask") == "knowledge-service"
        assert resolve_service("tool_load") == "ai-gateway"
        assert resolve_service("nope_") is None

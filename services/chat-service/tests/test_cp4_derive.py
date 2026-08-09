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


class TestTheRankingFacetsReachTheRow:
    """4.c — `OrderBy` and `TakeWhileBudget` rejected **every** real row because none carried
    `lane`/`tier`/`cost`. The ranking had no subject; these give it one."""

    def _admitted(self, td: dict):
        from app.agentruntime.admission import admit
        from app.agentruntime.derive import derive_one

        return admit(derive_one(td).declaration)

    def _def(self, name="book_list", tier="R", desc="x"):
        return {"name": name, "description": desc, "_meta": {"tier": tier},
                "inputSchema": {"type": "object", "properties": {}}}

    def test_A_ROW_BUILT_FROM_A_DEFINITION_CARRIES_ALL_THREE(self):
        from app.agentruntime.manifest import _row

        td = self._def()
        row = _row(self._admitted(td), tool_def=td)
        assert row["lane"] == "read" and row["tier"] == "R"
        assert row["cost"] > 0
        # And the value is the derivation's, not something a caller chose.
        from app.agentruntime.derive import facets_for

        assert {k: row[k] for k in ("lane", "tier", "cost")} == facets_for(td)

    def test_THERE_IS_NO_PARAMETER_FOR_A_CALLER_TO_STATE_A_RANK(self):
        """🔴 The construction, and the reason the first attempt was thrown away.

        A token-locked `Facets` type made a forged rank *hard to build*; the membrane gate refused
        it (a private token and `object.__setattr__` belong to `admission.py`). Removing the type
        was stronger: there is no facets argument at all, so the value cannot be **supplied**.
        """
        import inspect

        from app.agentruntime.manifest import _row

        params = set(inspect.signature(_row).parameters)
        assert "tool_def" in params
        for forbidden in ("facets", "lane", "tier", "cost"):
            assert forbidden not in params, (
                f"_row takes a `{forbidden}` argument — a caller that can pass one can state its "
                f"own rank, and a hand-typed cost of 1000000000 was measured steering "
                f"TakeWhileBudget"
            )

    def test_A_ROW_WITHOUT_A_DEFINITION_CARRIES_NONE_OF_THEM(self):
        """Optional, so every row already on disk still loads — the migration CP-1 kept
        `ROW_REQUIRED` separate from `ROW_FIELDS` to make possible."""
        from app.agentruntime.contract import FACET_FIELDS
        from app.agentruntime.manifest import _row

        row = _row(self._admitted(self._def()))
        assert not (FACET_FIELDS & row.keys())

    def test_ALL_THREE_OR_NONE_A_HALF_RANKED_ROW_IS_REFUSED(self):
        """§0.14.1a rule 2 — a missing ranking field is a REJECTION, never a fallback, because
        falling back reorders the whole surface and cuts different declarations (arm E)."""
        from app.agentruntime.contract import ContractViolation, check_row

        base = {"id": "book_list", "kind": "tool", "owning_service": "book-service",
                "lifecycle": "admitted", "contract_version": "1.0.0",
                "admitted_against": "1.0.0", "members": []}
        check_row({**base, "lane": "read", "tier": "R", "cost": 10}, "row")  # complete: fine
        for partial in ({"cost": 10}, {"lane": "read"}, {"lane": "read", "tier": "R"}):
            with pytest.raises(ContractViolation, match="or none of them"):
                check_row({**base, **partial}, "row")

    def test_THE_ENUMS_ARE_BOUNDED_AND_A_NEGATIVE_COST_IS_NOT_A_COUNT(self):
        from app.agentruntime.contract import ContractViolation, check_row

        base = {"id": "book_list", "kind": "tool", "owning_service": "book-service",
                "lifecycle": "admitted", "contract_version": "1.0.0",
                "admitted_against": "1.0.0", "members": [], "lane": "read", "tier": "R", "cost": 10}
        with pytest.raises(ContractViolation, match="unknown lane"):
            check_row({**base, "lane": "readonly"}, "row")
        with pytest.raises(ContractViolation, match="unknown tier"):
            check_row({**base, "tier": "X"}, "row")
        with pytest.raises(ContractViolation, match="non-negative"):
            check_row({**base, "cost": -1}, "row")
        # `bool` is an `int` subclass, so `True` would be a cost of 1 — the cheapest declaration on
        # the surface. The exact-type bound already excludes it; this pins that it does.
        with pytest.raises(ContractViolation, match="exactly int"):
            check_row({**base, "cost": True}, "row")

    def test_THE_RESIDUAL_THIS_ROW_OPENS_IS_STATED_NOT_HIDDEN(self):
        """🔴 **4.c GENUINELY WEAKENS THE DISK-READ PATH, AND THAT IS RECORDED RATHER THAN DENIED.**

        Before CP-4.c these three keys were undefined, so a hand-edited manifest carrying
        `cost: 1000000000` was refused by the schema itself. Now the field exists and a well-typed
        forged value **passes `check_row`** — this test asserts that it does, so nobody later reads
        the guard above and believes the file is protected.

        Why this is not a regression being waved through: §0.14.1c required the field to arrive with
        its producer, and the producer now exists. The threat model is unchanged — §6.4.2 names the
        document digest as the answer to a hand-edited manifest and records that it was
        **deliberately not taken**, adding that *"pretending a value bound closes it would be worse
        than leaving it open, because it would look closed."* What IS closed is the writer: no
        caller can supply a rank. What is open is the file, exactly as before for every other field.
        """
        from app.agentruntime.contract import check_row

        forged = {"id": "book_list", "kind": "tool", "owning_service": "book-service",
                  "lifecycle": "admitted", "contract_version": "1.0.0",
                  "admitted_against": "1.0.0", "members": [],
                  "lane": "read", "tier": "R", "cost": 1_000_000_000}
        check_row(forged, "row")  # passes — and this assertion is the honest record of that


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

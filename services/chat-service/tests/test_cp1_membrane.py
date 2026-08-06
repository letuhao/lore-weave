"""CP-1 — the membrane. Spec: docs/specs/2026-08-03-agent-runtime-unification §3, §6.1.

**A test may REJECT; it may never ADMIT.** A green suite here does not establish that the membrane
holds in production, and no bound may be claimed from it. What these do is fail when a specific
named defect appears — each one corresponds to a measured failure in this repository, not to a
hypothetical.

Every test states the defect it rejects. If you cannot say what would make it red, it is not a test.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import pickle
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.agentruntime import canon
from app.agentruntime import (
    CONTRACT_VERSION,
    Admitted,
    ContractViolation,
    Declaration,
    NarrowingLog,
    AllowList,
    DenyList,
    Filter,
    OrderBy,
    TakeWhileBudget,
    TopK,
    SurfaceAssembler,
    UnresolvedReference,
    UntrustedRow,
    admit,
    build,
    declarations,
    derive_owning_service,
    discover,
    generate,
    identity_of,
    load,
    try_admit,
    validate_document,
)

_REPO = Path(__file__).resolve().parents[3]


def _tool(id_: str = "book_list", **kw) -> Declaration:
    kw.setdefault("source_path", "services/book-service/internal/api/list.go")
    return Declaration(id=id_, kind="tool", **kw)


def _skill(id_: str = "world_setup", members=("book_list",)) -> Declaration:
    return Declaration(id=id_, kind="skill", members=tuple(members),
                       source_path="services/chat-service/app/skills/world.py")


# ── 1.1 · M1 — the registry starts empty ────────────────────────────────────────────────────────

class TestTheManifestStartsEmpty:
    """REJECTS: a manifest seeded with anything at all.

    With 315 legacy declarations one directory away, a non-empty manifest on day one is
    indistinguishable from a leak. The emptiness IS the measurement, which is why it is asserted on
    the committed artifact rather than on what the generator would produce.
    """

    def test_the_committed_manifest_is_empty(self):
        doc = json.loads((_REPO / "contracts" / "agent-runtime-manifest.json").read_text("utf-8"))
        assert doc["declarations"] == [], (
            "the membrane's only provable state is empty; a seeded row cannot be told from a leak"
        )

    def test_a_missing_manifest_reads_as_EMPTY_not_as_fall_back(self, tmp_path):
        """REJECTS the fail-open direction. A missing catalog must mean *no declarations*, never
        *use the one with 315 in it* — which is how every previous 'invisibility' leaked."""
        doc = load(path=tmp_path / "does-not-exist.json")
        assert doc["declarations"] == []

    def test_generation_round_trips_exactly_what_was_admitted(self, tmp_path):
        """M1's drift gate: manifest row count == admitted count."""
        p = tmp_path / "m.json"
        generate([admit(_tool("book_list")), admit(_tool("book_get"))], path=p, bootstrap=True)
        assert [r["id"] for r in json.loads(p.read_text("utf-8"))["declarations"]] == \
            ["book_get", "book_list"]

    def test_build_cannot_be_handed_an_unadmitted_declaration(self):
        """🔴 REWRITTEN — this test was GREEN FOR THE WRONG REASON and a verifier caught it.

        It accepted `AttributeError`, which is what duck typing raises when a bare `Declaration`
        has no `.declaration` attribute. `build()` never checked anything; the test was reading a
        coincidence of attribute names as a boundary. Now it names the exception the boundary
        actually raises, so removing the check reds it.
        """
        with pytest.raises(UntrustedRow):
            build([_tool()])                                    # a bare Declaration

    def test_an_object_that_merely_LOOKS_admitted_is_refused(self):
        """The defect the previous test was blind to, reproduced: four lines of duck type put a row
        into a generated manifest, because `build()` trusted the type instead of checking it."""
        class Fake:
            declaration = _tool("sneaky")
        with pytest.raises(UntrustedRow):
            build([Fake()])

    def test_a_row_TYPED_IN_BY_HAND_is_refused_on_load(self, tmp_path):
        """§6.1 layer 3, the read end. Admission is a property of a ROW, not of the process that
        happened to write the file — and JSON on disk has no types. Before this, a row typed
        straight into the manifest was served to the assembler having passed no clause."""
        p = tmp_path / "m.json"
        p.write_text(json.dumps({
            "manifest_version": 1, "contract_version": "1.0.0",
            "declarations": [{"id": "Not An Id", "kind": "tool", "owning_service": "book-service",
                              "lifecycle": "admitted", "contract_version": "1.0.0", "members": []}],
        }), encoding="utf-8")
        with pytest.raises(UntrustedRow):
            load(path=p)

    def test_the_EXPORTED_row_reader_refuses_a_malformed_document(self):
        """🔴 `declarations()` is the only row-reader in `__all__`, and it kept the silent
        `.get("declarations", [])` while `rows_of` — not exported — raised. So the package's public
        API answered `[]` for a broken document and its internal one answered honestly.

        Round 4 found that reverting it left 63/63 green: the fix was real and unguarded. This is
        the guard, and it names the exported surface rather than the internal helper, because that
        is where the silent answer was reachable from."""
        with pytest.raises(ValueError, match="malformed"):
            declarations({})

    def test_a_hand_broken_reference_is_refused_on_load(self, tmp_path):
        """M5 resolves at generation — and an edit afterwards can break what generation proved."""
        p = tmp_path / "m.json"
        p.write_text(json.dumps({
            "manifest_version": 1, "contract_version": "1.0.0",
            "declarations": [{"id": "world_setup", "kind": "skill", "owning_service": "chat-service",
                              "lifecycle": "admitted", "contract_version": "1.0.0",
                              "admitted_against": "1.0.0", "members": ["deleted_tool"]}],
        }), encoding="utf-8")
        with pytest.raises(UnresolvedReference):
            load(path=p)


# ── 1.2 · M2 — the import graph, the load-bearing property ──────────────────────────────────────

def _gate():
    spec = importlib.util.spec_from_file_location(
        "membrane_gate", _REPO / "scripts" / "agentruntime-membrane-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTheNewSurfaceCannotReachTheOldOne:
    """REJECTS: a code path from the legacy catalog to the new surface.

    §3 forbids the PATH, not the wrong result — a function that reads the old catalog and returns
    nothing from it still IS the path. 'Invisibility implemented as a filter' has been produced
    thirteen times here and every instance eventually leaked or deleted the wrong thing.
    """

    def test_the_package_imports_only_stdlib_and_itself(self):
        assert _gate().main([]) == 0

    @pytest.mark.parametrize("src", [
        "from app.services.tool_surface import budget_names_by_tokens\n",
        "import app.services.stream_service\n",
        "from app.services.tool_discovery import filter_intent_gated_setup_tools\n",
        "import httpx\n",
        "import importlib\n",
        "def f(n):\n    return __import__(n)\n",
    ])
    def test_the_gate_fires_on_each_bypass_shape(self, tmp_path, src):
        """NV-1 — a gate that cannot fire reports safety. Run over a temp file, so proving the gate
        red-able never mutates a tracked artifact."""
        p = tmp_path / "probe.py"
        p.write_text(src, encoding="utf-8")
        assert _gate()._violations_in(p), f"the gate did not fire on:\n{src}"

    def test_the_gate_is_silent_on_a_legal_module(self, tmp_path):
        """The other half of red-ability: a gate that fires on everything is not a gate."""
        p = tmp_path / "clean.py"
        p.write_text("import json\nfrom .contract import Declaration\n", encoding="utf-8")
        assert not _gate()._violations_in(p)

    def test_the_gate_actually_RUNS_in_ci(self):
        """REJECTS: a gate present in the tree and absent from CI. An import-graph gate is worth
        exactly what CI runs, and six legs of this very workflow once failed on main for weeks."""
        wf = (_REPO / ".github" / "workflows" / "lint-foundation.yml").read_text("utf-8")
        assert "- agentruntime-membrane-gate" in wf

    def test_the_allowlist_is_an_allowlist(self):
        """A denylist is default-permitted: a legacy module written tomorrow would be reachable
        until someone remembered to add it. The direction of the list is the gate."""
        g = _gate()
        assert g.ALLOWED_EXTERNAL == {}, (
            "every entry needs a reason in the diff that introduces it"
        )


# ── 1.3 · M3 — discovery reads the manifest only ────────────────────────────────────────────────

class TestDiscoveryReturnsNothingForLegacyDeclarations:
    """REJECTS: a legacy declaration reachable through discovery.

    Asserted for **each of the three kinds**, because the membrane is over declarations, not over
    tools — a legacy skill and a legacy workflow step must be excluded by the same construction,
    not by three separate suppressors that drift apart.
    """

    @pytest.mark.parametrize("kind", ["tool", "skill", "workflow"])
    def test_an_empty_manifest_yields_zero_rows_for_every_kind(self, kind):
        assert discover(load(path=Path("nonexistent.json")), kind=kind, log=NarrowingLog()) == []

    def test_filtering_by_kind_without_a_log_is_refused(self):
        """REJECTS the silent drop point a verifier's enumeration found. `discover(kind=…)` returns
        fewer rows than the manifest holds — that is a narrowing, and P1 does not exempt a function
        for being on the discovery side."""
        doc = build([admit(_tool("book_list"))])
        with pytest.raises(ValueError, match="narrowing"):
            discover(doc, kind="skill")

    def test_filtering_by_kind_registers_what_it_removed(self):
        log = NarrowingLog()
        doc = build([admit(_tool("book_list")), admit(_skill("world_setup", ("book_list",)))])
        assert [r["id"] for r in discover(doc, kind="skill", log=log)] == ["world_setup"]
        assert log.records() == [{
            "tool": "book_list", "stage": "discovery_kind_filter",
            "reason": "kind is 'tool', discovery asked for 'skill'", "pass": 1,
        }]

    @pytest.mark.parametrize("legacy_id", ["book_list", "glossary_search", "tool_list"])
    def test_a_real_legacy_tool_name_is_not_discoverable(self, legacy_id):
        """These three exist in the legacy catalog today. Not hidden — absent."""
        doc = json.loads((_REPO / "contracts" / "agent-runtime-manifest.json").read_text("utf-8"))
        assert legacy_id not in {r["id"] for r in discover(doc)}

    def test_REAL_legacy_declarations_of_all_three_kinds_return_zero_rows(self):
        """🔴 M3 as §3 actually words it: *"a test that SEEDS a legacy-only declaration of each of
        the three kinds and asserts discovery returns zero rows for all three."*

        The previous version asserted over an EMPTY manifest, which proves that an empty catalog is
        empty — true, and not the claim. This reads the three legacy registries and asserts every
        name in them is absent from the new surface. The names are **read from the legacy source**
        rather than typed here, so the test stays honest as those registries change; inventing the
        names would test a fiction.

        This is also the only test in the file that touches legacy modules, and that is correct:
        the membrane forbids the PACKAGE from importing them, not the test that proves the
        separation. The gate scans `app/agentruntime/**`, not `tests/`.
        """
        from app.services.intent_workflows import _COMPILED
        from app.services.skill_registry import LOADABLE_SKILL_CODES

        snapshot = json.loads(
            (_REPO / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json")
            .read_text("utf-8"))
        legacy_tools = [t["name"] for t in (snapshot.get("tools") or snapshot)]
        legacy_skills = sorted(LOADABLE_SKILL_CODES)
        legacy_workflows = [wf_id for wf_id, _ in _COMPILED]

        # NV-1: if any registry were empty the assertion below would pass vacuously.
        assert len(legacy_tools) >= 300 and legacy_skills and legacy_workflows, (
            f"a legacy registry came back empty — this test would prove nothing: "
            f"{len(legacy_tools)} tools, {len(legacy_skills)} skills, "
            f"{len(legacy_workflows)} workflows"
        )

        doc = json.loads((_REPO / "contracts" / "agent-runtime-manifest.json").read_text("utf-8"))
        surfaced = {r["id"] for r in discover(doc)}

        def leaks(names: list[str]) -> list[str]:
            return sorted(surfaced & set(names))

        for kind, names in (("tool", legacy_tools), ("skill", legacy_skills),
                            ("workflow", legacy_workflows)):
            assert not leaks(names), (
                f"legacy {kind}(s) reachable through the new discovery: {leaks(names)}"
            )

        # 🔴 POSITIVE CONTROL, and round 3's finding is why it is here. With an empty manifest
        # `surfaced` is empty, so `∅ ∩ X = ∅` for ANY X — a verifier substituted 315 fictional
        # names and got an identical pass. The assertion above therefore measures nothing TODAY;
        # it is armed for CP-4. Without this control the row would read as a live check.
        planted = {"id": legacy_tools[0], "kind": "tool", "owning_service": "book-service",
                   "lifecycle": "admitted", "contract_version": "1.0.0", "members": []}
        planted_surfaced = {r["id"] for r in discover({"declarations": [planted]})}
        assert planted_surfaced & set(legacy_tools), (
            "the leak detector cannot detect a leak: a legacy tool placed directly in the manifest "
            "was not flagged, so the assertions above would pass through a real breach"
        )


# ── 1.4 · M4 — construction IS validation ───────────────────────────────────────────────────────

class TestAdmittedCannotBeProducedWithoutTheCheck:
    """REJECTS: the 14-call-sites-against-58-constructions shape.

    The thing being replaced is not 'no validator'. It is a validator you must remember to call,
    which is therefore 76% not called. Each test below is one documented way a private constructor
    gets bypassed — most of them by accident rather than by malice.
    """

    def test_direct_construction_is_refused(self):
        with pytest.raises(TypeError, match="not constructible"):
            Admitted(_tool(), "1.0.0")

    def test_admit_produces_one(self):
        a = admit(_tool())
        assert a.id == "book_list" and a.kind == "tool"

    def test_a_failing_declaration_never_yields_an_admitted(self):
        with pytest.raises(ContractViolation):
            admit(Declaration(id="Book List", kind="tool", source_path="services/x/y.py"))

    def test_try_admit_returns_none_rather_than_a_weaker_admitted(self):
        """A 'lenient' variant is the usual way an escape hatch arrives. It must return None on the
        path where admit raises — never an Admitted that skipped a clause."""
        a, err = try_admit(Declaration(id="bad id", kind="tool", source_path="services/x/y.py"))
        assert a is None and isinstance(err, ContractViolation)

    def test_admit_has_no_escape_hatch(self):
        """REJECTS: force= / skip_checks= / strict=False. `require_meta` in this repo ships its own
        documented exemption; a validator that describes when it declines to apply is not a gate."""
        import inspect
        params = set(inspect.signature(admit).parameters)
        assert params == {"declaration"}, f"admit() grew an argument: {params}"

    def test_it_cannot_be_mutated_into_a_different_declaration(self):
        a = admit(_tool())
        with pytest.raises((AttributeError, TypeError)):
            a.declaration = _tool("something_else")

    def test_it_has_no_dict_to_reach_around_the_freeze(self):
        assert not hasattr(admit(_tool()), "__dict__")

    @pytest.mark.parametrize("forge", [copy.copy, copy.deepcopy, pickle.dumps])
    def test_round_trip_forgery_is_refused(self, forge):
        """copy and pickle reconstruct WITHOUT calling __init__, so a private constructor alone
        does not stop them. This is the bypass that happens by accident."""
        with pytest.raises(TypeError):
            forge(admit(_tool()))

    def test_a_forged_instance_is_UNUSABLE_which_is_the_honest_boundary(self):
        """object.__new__ cannot be prevented by any Python mechanism, and this does not claim it
        can. What is claimed: the forgery is loud. Every slot is unset, so the first read raises
        instead of returning a plausible value — and a plausible wrong value is what this whole
        checkpoint exists to stop."""
        forged = object.__new__(Admitted)
        with pytest.raises(AttributeError):
            _ = forged.declaration


# ── 1.5 · M5 — a reference that does not resolve stops generation ───────────────────────────────

class TestAnUnresolvedReferenceStopsGeneration:
    """REJECTS: the gate that fails OPEN. Today 12 rails point at 30 dead tools, checked at use,
    and the check's failure mode is to allow. Resolving at generation inverts both."""

    def test_a_skill_naming_an_unadmitted_member_fails(self):
        with pytest.raises(UnresolvedReference, match="book_list"):
            build([admit(_skill("world_setup", members=("book_list",)))])

    def test_it_resolves_when_the_member_is_admitted(self):
        doc = build([admit(_tool("book_list")), admit(_skill("world_setup", ("book_list",)))])
        assert len(doc["declarations"]) == 2

    def test_nothing_is_written_when_a_reference_is_unresolved(self, tmp_path):
        """The point of generation-time resolution: the failure cannot be reached at runtime,
        because the artifact does not exist."""
        p = tmp_path / "m.json"
        with pytest.raises(UnresolvedReference):
            generate([admit(_skill("world_setup", ("nope",)))], path=p, bootstrap=True)
        assert not p.exists()


# ── 1.6 · C-0 — identity, with the owner DERIVED ────────────────────────────────────────────────

class TestP4NoColumnIsBoundToAConstantAtTheWriteBoundary:
    """P4 at CP-1's own persistence boundary — the manifest.

    🔴 I had reported P4 as *"no subject at CP-1"* because the new runtime reaches no DB INSERT.
    That was reasoning from where I expected the property to live rather than from what it says. A
    verifier named this in round 2 (*"`Admitted.contract_version` remains a dead field while the row
    writes the module constant"*) and I did not act on it for three rounds.

    The consequence is §6.4's mechanism defeated in silence: a **breaking** contract amendment is
    supposed to put prior declarations into a re-admission queue, which is computed by comparing what
    a row was admitted against with what the contract now says. If the row re-states the CURRENT
    constant, every historical row claims conformance to a contract it was never checked against and
    the queue is permanently empty — a migration that can never find work.
    """

    @staticmethod
    def _amend(monkeypatch, version: str) -> None:
        """A contract amendment, as a real sequence. `CONTRACT_VERSION` is bound by name in two
        modules; rebinding one leaves the other reading the old value, which is how a previous round
        managed to measure a mechanism that could not actually run."""
        import app.agentruntime.contract as _contract
        import app.agentruntime.manifest as _manifest
        monkeypatch.setattr(_contract, "CONTRACT_VERSION", version)
        monkeypatch.setattr(_manifest, "CONTRACT_VERSION", version)

    def test_two_rows_CAN_carry_different_stamps(self, monkeypatch):
        """🔴 THE TEST THAT WOULD HAVE CAUGHT MY FIRST FIX, and did not exist.

        The first attempt moved the constant read one call earlier — `admit()` took it from
        `check_contract()`, whose only success return is `CONTRACT_VERSION`. Same value, every row.
        A verifier printed `{'1.0.0'}` across all of them. **A field that cannot differ between two
        rows records nothing about either**, and the test written then asserted a hardcoded
        `"1.0.0"`, so it was satisfied by exactly the defect it was meant to reject.

        Now driven through a real amendment rather than by hand-mutating a fixture, because a
        fixture edited in place proves only that a dict can hold two values.
        """
        first = build([admit(_tool("book_list"))], previous=None)
        assert {r["contract_version"] for r in first["declarations"]} == {CONTRACT_VERSION}

        self._amend(monkeypatch, "2.0.0")
        after = build([admit(_tool("book_list")), admit(_tool("book_get"))], previous=first)
        origins = {r["id"]: r["contract_version"] for r in after["declarations"]}
        assert origins == {"book_list": "1.0.0", "book_get": "2.0.0"}, (
            f"the ORIGIN generation was not preserved across the amendment: {origins}"
        )

    def test_THE_QUEUE_IS_EMPTY_BY_CONSTRUCTION__P4_IS_NOT_SATISFIED_HERE(self, monkeypatch):
        """🔴 **THE TEST THAT RECORDS A FAILURE INSTEAD OF HIDING IT.**

        `admitted_against` ← `Admitted.contract_version` ← `check_contract()`, whose only success
        return is `CONTRACT_VERSION` — the same literal the document header carries. A verifier
        measured **0 non-empty queues in 500 randomised builds**, and replacing the field with the
        constant read one attribute later left the suite fully green: the two expressions *cannot*
        differ in one process.

        So this asserts the defect, deliberately, because the alternative is a suite that reads as
        though §6.4 works. It turns red the day the grandfathering mechanism lands — which is
        exactly when the claim above stops being true and this test should stop being here.
        """
        doc = build([admit(_tool("book_list")), admit(_tool("book_get"))], previous=None)
        assert len(doc["declarations"]) == 2, "no rows, so every claim below is vacuous"
        queue = [r["id"] for r in doc["declarations"]
                 if r["admitted_against"] != doc["contract_version"]]
        assert queue == [], (
            "the queue is non-empty — the grandfathering mechanism has landed, so §6.4.1's FAIL "
            "record and this test are both stale and must be replaced by a drain test"
        )

        self._amend(monkeypatch, "2.0.0")
        after = build([admit(_tool("book_list")), admit(_tool("book_get"))], previous=doc)
        # 🔴 **THIS TEST WAS GREEN UNDER AN AMEND THAT DID NOTHING.** A verifier injected `_amend`
        # as a no-op and it passed in 0.11s: assertion 2 below is trivially true when nothing was
        # amended, so it degenerated into assertion 1 restated and the only half involving an
        # amendment could not tell a real one from none. **A test that asserts a FAILURE can pass
        # for the wrong reason, and this is the test CP-4 will be graded against.**
        assert after["contract_version"] == "2.0.0", (
            "the amendment did not take — `CONTRACT_VERSION` is bound by name in TWO modules and "
            "rebinding one leaves the other reading the old value, which has produced a bogus "
            "measurement in this run before. Without this line the assertion below is vacuous."
        )
        assert len(after["declarations"]) == 2
        assert {r["admitted_against"] for r in after["declarations"]} == {"2.0.0"}, (
            "admitted_against varied, which this checkpoint cannot make happen"
        )

        # 🔴 **AND THE PREVIOUS FIX STILL DID NOT MAKE THIS RED WHEN THE MECHANISM LANDS.** A
        # verifier BUILT the §6.4 carry-forward, proved it produces `queue=['book_get']` and drains
        # to `[]` — and this test **passed**, because it only ever calls `build` with EVERY
        # declaration re-admitted, so `queue == []` is true on both sides of the transition. My
        # docstring and §0.14.1c both claimed it "reds the day the mechanism lands". It did not.
        #
        # I had fixed what the verifier pointed AT (an amend that did nothing) and not what it
        # MEANT.
        #
        # 🔴 **AND THE FIX FOR THAT WAS A PROXY, WHICH THE NEXT ROUND MEASURED TOO.** It asserted
        # `build()`'s refusal — the same claim `test_A_DECLARATION_CANNOT_SILENTLY_LEAVE_THE_MANIFEST`
        # already makes — so it **red for the wrong reason** (changing the refusal's wording or its
        # exception type reds it, with the mechanism as absent as ever) and **stayed green with the
        # mechanism live** in the two most likely shapes: gated on a breaking amendment, which is
        # §6.4's literal wording, and landing in `generate()`, which is where §6.4.1's own argument
        # puts it. A verifier built both and measured 109 passed.
        #
        # So the assertion is now about the OUTCOME the mechanism exists to produce, checked through
        # every door that could produce it. **A queue with a member is the mechanism; a refusal is
        # only evidence that one thing which would break it is still absent.**
        # The scenario has to be one in which a queue member COULD exist, or the assertion is true
        # for free — which is why the previous version stayed green while a verifier ran the
        # mechanism underneath it. A queue member requires a declaration in `previous` and **absent
        # from `admitted`**, so the test performs exactly that partial re-admission.
        self._amend(monkeypatch, "3.0.0")
        try:
            partial = build([admit(_tool("book_list"))], previous=after)
        except UntrustedRow:
            return          # the mechanism is absent: `build` refuses to lose the row. Today's state.

        queue = sorted(r["id"] for r in partial["declarations"]
                       if r["admitted_against"] != partial["contract_version"])
        raise AssertionError(
            f"§6.4's re-admission queue is NON-EMPTY ({queue}) — the grandfathering mechanism has "
            f"LANDED. §6.4.1's FAIL record, §0.14.1c's row and this test are all stale now: replace "
            f"them with a drain test (fills on a breaking amendment, empties as each declaration is "
            f"re-admitted). This test asserts a defect, and the defect is gone."
        ) if queue else None

    def test_A_DECLARATION_CANNOT_SILENTLY_LEAVE_THE_MANIFEST(self, monkeypatch):
        """§1 says the plan deletes nothing; §6.4 says a declaration entering the re-admission queue
        does so *without leaving the runtime*. That mechanism is unbuilt, and a verifier measured the
        consequence: regenerate without a declaration, regenerate again with it, and its ORIGIN comes
        back as the new generation. Four routes, three ungated.

        The missing mechanism now fails loudly at the moment it is needed."""
        first = build([admit(_tool("book_list")), admit(_tool("book_get"))], previous=None)
        with pytest.raises(UntrustedRow, match="IS NOT BUILT"):
            build([admit(_tool("book_list"))], previous=first)

    def test_generate_CARRIES_THE_ORIGIN_ACROSS_A_REAL_WRITE(self, tmp_path, monkeypatch):
        """🔴 THE BRANCH THAT MATTERS, AND IT HAD NO TEST AT ALL.

        A verifier deleted `previous=` from `generate()` — **the only line that will ever write the
        real manifest** — and the suite stayed **89/89 green**, because both `generate()` call sites
        in it wrote to a fresh `tmp_path`, so that argument evaluated to `None` in every test that
        existed. Red-ability had been proven at `build()`; the production branch was dead to the
        suite. So this writes the SAME path twice, across an amendment, through the real writer.
        """
        target = tmp_path / "m.json"
        generate([admit(_tool("book_list"))], path=target, bootstrap=True)
        assert target.exists()

        self._amend(monkeypatch, "2.0.0")
        doc = generate([admit(_tool("book_list")), admit(_tool("book_get"))], path=target)

        on_disk = json.loads(target.read_text("utf-8"))
        assert on_disk == doc
        origins = {r["id"]: r["contract_version"] for r in on_disk["declarations"]}
        assert origins == {"book_list": "1.0.0", "book_get": "2.0.0"}, (
            f"generate() lost the origin across a real regeneration: {origins}"
        )
        assert {r["admitted_against"] for r in on_disk["declarations"]} == {"2.0.0"}, (
            "both rows were re-admitted under 2.0.0, so both must say so"
        )

    def test_a_MISSING_manifest_is_not_permission_to_restamp(self, tmp_path):
        """🔴 THE FAIL-OPEN ERASURE. `previous` defaulted to `None` whenever the target did not
        exist, so writing to a fresh path — or deleting the manifest, the ordinary reaction to a
        drift gate going red — restamped every origin with the current constant and emptied the
        queue. No test and no gate noticed. The caller must now say it means to bootstrap."""
        with pytest.raises(UntrustedRow, match="bootstrap"):
            generate([admit(_tool("book_list"))], path=tmp_path / "absent.json")
        assert not (tmp_path / "absent.json").exists(), "it wrote the file anyway"

    def test_the_WRITE_side_validates_previous_too(self):
        """`previous` is caller-supplied. The exported `build()` emitted an integer and `"banana"`
        as stamps and produced a document its own `load()` refuses — a writer trusting its argument,
        which is the write end of the boundary `UntrustedRow` exists to describe."""
        for bad in (7, "banana", None, "1.0"):
            with pytest.raises(UntrustedRow, match="contract_version"):
                build([admit(_tool("book_list"))],
                      previous={"declarations": [{"id": "book_list", "contract_version": bad}]})

    def test_BOTH_stamps_are_VALIDATED_not_merely_present(self):
        """A field nothing checks is a field anything can say. A verifier fed `admitted_against`
        `null`, `"banana"`, `"99.0.0"` and the OLD field name; all four were accepted.

        **Three of those four are rejected now, not four.** `"99.0.0"` is a well-formed version that
        never existed, and a shape check cannot tell it from a real one — the residual is stated
        here rather than papered over, and its direction is the safe one: a bogus stamp lands the row
        *in* the queue, not out of it.
        """
        good = build([admit(_tool("book_list"))], previous=None)
        for field in ("contract_version", "admitted_against"):
            for bad in (None, "banana", "1.0", 1.0, " 1.0.0", "1.0.0-beta"):
                doc = json.loads(json.dumps(good))
                doc["declarations"][0][field] = bad
                with pytest.raises(UntrustedRow, match=field):
                    validate_document(doc)
        # `admitted_against` is required outright.
        doc = json.loads(json.dumps(good))
        doc["declarations"][0].pop("admitted_against")
        with pytest.raises(UntrustedRow, match="admitted_against"):
            validate_document(doc)

    def test_an_OLD_SHAPE_row_is_REFUSED_rather_than_repaired_in_place(self):
        """🔴 A BACKFILL STOOD HERE AND IT WAS A LAUNDERING PATH FOR A MIGRATION WITH NO SUBJECT.

        It adopted `admitted_against` as the origin whenever `contract_version` was missing. True
        for a genuine old row — and a verifier measured the cost: a **hand-edited** row carrying
        `admitted_against: "99.0.0"` and no origin was rejected before the backfill and accepted
        after, and the carry then made `"99.0.0"` that declaration's permanent origin. A bogus
        *comparand* lands a row in the queue, which is safe; a bogus *origin* is never re-checked.

        The migration it was written for does not exist: **the committed manifest is
        `declarations: []`**, and the old shapes live only in git history. It also mutated its
        argument, so the drift gate compared a document it had silently repaired.
        """
        good = build([admit(_tool("book_list"))], previous=None)
        old = json.loads(json.dumps(good))
        old["declarations"][0].pop("contract_version")
        with pytest.raises(UntrustedRow, match="contract_version"):
            validate_document(old)

        # ...and it must not have edited the caller's document on the way to refusing it.
        assert "contract_version" not in old["declarations"][0], (
            "validate_document mutated its argument; the M1 drift gate then compares a document "
            "this function silently repaired"
        )

    def test_validate_document_does_not_MUTATE_what_it_validates(self):
        """A validator that edits its input makes every caller's later read a different question
        from the one it asked. The drift gate is the caller that matters: it compares the loaded
        document against `build([])`, so a silent repair is a comparison against a document nobody
        wrote."""
        good = build([admit(_tool("book_list"))], previous=None)
        snapshot = json.loads(json.dumps(good))
        out = validate_document(good)
        assert good == snapshot, "the document was edited in place"
        assert out == snapshot

    def test_the_DOCUMENT_stamps_are_validated_because_one_of_them_is_the_comparand(self):
        """Both were written from constants and read from nowhere: `"banana"` and a missing
        `manifest_version` both passed. The document's `contract_version` is what every row is
        compared against, so an unreadable one empties §6.4's queue in silence — the same failure
        as the row-level stamp, one level up. Caught today only by the drift gate's byte-equality
        with `build([])`, which does not survive the first non-empty manifest."""
        good = build([admit(_tool("book_list"))], previous=None)
        for key, bad in (("contract_version", "banana"), ("contract_version", None),
                         ("manifest_version", 99), ("manifest_version", None)):
            doc = json.loads(json.dumps(good))
            doc[key] = bad
            with pytest.raises(UntrustedRow, match=key):
                validate_document(doc)

    def test_a_row_with_NO_lifecycle_is_refused_rather_than_defaulted(self):
        """C-0 names lifecycle state as part of identity. `r.get("lifecycle", "draft")` admitted a
        row that omits it **and returned it still missing the key**, so the default existed only for
        the duration of the check — the P4 shape at the read half of the same boundary."""
        good = build([admit(_tool("book_list"))], previous=None)
        doc = json.loads(json.dumps(good))
        doc["declarations"][0].pop("lifecycle")
        with pytest.raises(UntrustedRow):
            validate_document(doc)

    def test_the_row_carries_BOTH_fields_because_ONE_of_them_cannot_move(self):
        """🔴 §6.4 REQUIRES TWO FIELDS AND THE FIRST FIX SHIPPED ONE — with a test that actively
        *rejected* the second, so the spec and the code contradicted each other and the suite took
        the code's side.

        They answer different questions and only one moves. Collapsing them is why nothing could
        drain: a single field cannot both record where a declaration came from and report whether it
        has been re-checked since.
        """
        row = build([admit(_tool("book_list"))], previous=None)["declarations"][0]
        assert row["contract_version"] == CONTRACT_VERSION
        assert row["admitted_against"] == CONTRACT_VERSION, (
            "on a first admission the two coincide — which is exactly why one build can never "
            "distinguish them, and why the tests above drive an amendment"
        )


class TestIdentityIsDerivedNotAuthored:
    """REJECTS: a declaration that states its own owner.

    C-0 exists because M4 was gated on C-1…C-12 and identity was in none of them, so the first
    admitted declaration would have had no id, no owner and no lifecycle. There is no CODEOWNERS
    file in this repository, so an authored `owner` could never be checked against anything.
    """

    def test_a_declaration_has_no_owner_field_to_author(self):
        assert "owning_service" not in {f for f in Declaration.__dataclass_fields__}

    @pytest.mark.parametrize("path,owner", [
        ("services/book-service/internal/api/list.go", "book-service"),
        ("services/chat-service/app/agentruntime/surface.py", "chat-service"),
        ("services\\glossary-service\\internal\\x.go", "glossary-service"),
    ])
    def test_the_owner_comes_from_where_the_code_lives(self, path, owner):
        assert derive_owning_service(path) == owner

    def test_an_underivable_owner_is_a_violation_not_a_default(self):
        """REJECTS `unknown`. A plausible-looking value for a question nobody answered is exactly
        what this run has paid for repeatedly."""
        with pytest.raises(ContractViolation, match="owning service"):
            admit(Declaration(id="x", kind="tool", source_path="tools/misc/x.py"))

    def test_identity_carries_the_fields_it_can_actually_derive(self):
        """🔴 Was `..._all_four_C0_fields`, and the fourth was `contract_version` — the running
        build's constant, asserted only for truthiness. Round 2 called it a dead field; round 6
        found the first fix had moved the deadness one type over rather than ending it. Removed
        from `Identity`, because a field kept because deleting it feels lossy is a field the next
        reader will trust. C-0's contract-version stamp lives on the manifest ROW, as
        `admitted_against`, where it can differ between rows and therefore mean something."""
        ident = identity_of(_tool())
        assert ident.id and ident.owning_service and ident.lifecycle
        assert not hasattr(ident, "contract_version")


# ── 1.7 · P1 — every narrowing registers ────────────────────────────────────────────────────────

class TestANarrowingCannotHappenSilently:
    """REJECTS the property that failed ELEVEN straight rounds as a retrofit.

    On the legacy surface P1 is one claim over seven stages, five files, thirty mint sites and six
    INSERT paths; eight fixes were attempted and two were placed where they could not run at all.
    Here there is one assembly point, and it records in the same statement that drops.
    """

    def _assembler(self, n=3):
        doc = build([admit(_tool(f"tool_{i}")) for i in range(n)])
        return SurfaceAssembler(doc)

    def test_a_dropped_declaration_produces_a_full_record(self):
        a = self._assembler()
        s = a.assemble(pass_number=1, pipeline=[
            Filter("token_budget", "over budget", field="id", op="not_in", value=("tool_1",)),
        ])
        assert "tool_1" not in s.names
        assert a.log.records() == [
            {"tool": "tool_1", "stage": "token_budget", "reason": "over budget", "pass": 1},
        ]

    def test_the_withheld_set_travels_WITH_the_surface(self):
        """A narrowing the caller must go and find in a log is a narrowing that gets dropped at the
        first persistence boundary — which is how the legacy column came to be empty for the one
        stage it was built for."""
        s = self._assembler().assemble(pass_number=1, pipeline=[
            Filter("intent_gate", "not this intent", field="id", op="eq", value="tool_0"),
        ])
        assert {w["tool"] for w in s.withheld} == {"tool_1", "tool_2"}

    def test_a_rule_without_a_stage_or_reason_cannot_be_built(self):
        """This is where 'every narrowing registers' stops being a discipline: the two fields P1
        needs are arguments of the rule, so a rule cannot be applied without them."""
        for stage, reason in (("", "r"), ("s", "")):
            with pytest.raises(ValueError, match="stage and its reason"):
                Filter(stage, reason, field="id", op="not_in", value=())

    def test_every_pass_is_recorded_separately(self):
        """REJECTS a timeless record. A verifier found 19 of 303 withheld declarations
        simultaneously advertised on every pass and could not tell a contradiction from a
        sequence — dropped at one stage then restored by a later one is coherent history."""
        a = self._assembler()
        rule = Filter("failure_breaker", "failed twice", field="id", op="not_in", value=("tool_2",))
        a.assemble(pass_number=1, pipeline=[rule])
        a.assemble(pass_number=2, pipeline=[rule])
        assert [e.pass_number for e in a.log.entries] == [1, 2]

    def test_a_pass_number_below_one_is_refused(self):
        with pytest.raises(ValueError, match="1-based"):
            self._assembler().assemble(pass_number=0)

    def test_the_POST_CONDITION_itself_fires(self):
        """🔴 A gate nobody has watched go red is the thing this checkpoint keeps shipping.

        Round 4 found that disabling the post-condition left 63/63 green — it was doing real work
        and nothing proved it. This drives a silent drop through the real `assemble()` by making
        `_narrow` remove a row without recording, which is exactly the shape three of my own gates
        failed to catch. If the law is ever deleted or weakened, this reds.
        """
        a = self._assembler(3)
        rule = Filter("token_budget", "over budget", field="id", op="not_in", value=())   # keeps everything
        original = SurfaceAssembler._narrow

        # Signature mirrors the real `_narrow`, including `ordered_by` — a stub that omits a
        # parameter the caller passes is a stub that lies about the contract.
        def silent(self, rows, stage, *, pass_number, ordered_by=None):
            return list(rows)[1:]

        SurfaceAssembler._narrow = silent
        try:
            with pytest.raises(AssertionError, match="with no .*record"):
                a.assemble(pass_number=1, pipeline=[rule])
        finally:
            SurfaceAssembler._narrow = original

    def test_a_log_SHARED_WITHIN_ONE_PASS_does_not_break_the_law(self):
        """🔴 F3 — the hole the fix itself opened, found by round 4 and fixed here.

        `withheld` counted every log entry at that pass, so a log shared inside one pass —
        discover-then-assemble, two assemblers in a turn, a retry — made `registered` too large and
        the law raised on CORRECT code, reporting a negative loss. The module's own docstring
        blesses sharing a log, and the test that covered it survived only because it happened to
        span two passes. **A conservation law over a shared counter must count its own
        contribution**, or it fails the honest caller and passes the careless one.
        """
        log = NarrowingLog()
        doc = build([admit(_tool("book_list")), admit(_tool("book_get")),
                     admit(_skill("world_setup", ("book_list",)))])
        discover(doc, kind="skill", log=log, pass_number=1)      # records 2 at pass 1
        s = SurfaceAssembler(doc, log=log).assemble(pass_number=1)
        assert s.count == 3 and s.withheld == ()
        assert len(log) == 2, "the shared log must still hold discovery's own narrowings"

        # 🔴 AND THE TWO FACTS MUST STAY TELLABLE APART. Round 5 caught the earlier version of
        # this test asserting a state where the same declaration is recorded WITHHELD at pass 1 and
        # ADVERTISED at pass 1 — the exact contradiction `pass_number` exists to make detectable,
        # recreated by me and then blessed by my own test. A query filter is not a withholding from
        # the model. `withheld` answers "what could the model not see"; the log holds the turn's
        # whole record, and `stage` is what keeps the two legible.
        assert {e.stage for e in log.for_pass(1)} == {"discovery_kind_filter"}
        assert set(s.names) & {e.declaration_id for e in log.for_pass(1)}, (
            "the declarations discovery filtered out ARE advertised by the assembler — that is "
            "coherent only while the two records are distinguishable by stage"
        )

    def test_over_registration_is_refused_too(self):
        """The law is `!=`, not `<`, and round 5 found that weakening it to one-directional was
        invisible to the whole suite. Fabricated records are the other way to break conservation:
        they balance a real drop, so a law that only watches for shortfall can be satisfied by
        inventing the evidence for the loss it is meant to catch."""
        a = self._assembler(3)
        original = SurfaceAssembler._narrow

        def double_record(self, rows, stage, *, pass_number, ordered_by=None):
            kept = original(self, rows, stage, pass_number=pass_number, ordered_by=ordered_by)
            self._log.record("__ghost__", stage="s", reason="r", pass_number=pass_number)
            return kept

        SurfaceAssembler._narrow = double_record
        try:
            with pytest.raises(AssertionError, match="lost -1"):
                a.assemble(pass_number=1, pipeline=[
                    Filter("token_budget", "over budget", field="id", op="not_in", value=()),
                ])
        finally:
            SurfaceAssembler._narrow = original

    def test_assembling_with_NO_RULES_offers_everything_admitted(self):
        """🔴 THE COVERAGE GAP THAT MADE A CORRECT POST-CONDITION SILENT.

        `assemble()` now enforces `offered + registered == admitted` on every real assembly — but
        an injected silent drop on the `rules == ()` branch still left the suite green, because
        every no-rules test here ran against a manifest of **0 or 1** declarations, where
        `kept[:1]` is indistinguishable from `kept`. The law was right and nothing drove it.

        A post-condition is only as reachable as the fixtures that reach it. This is the no-rules
        path at n=3, which is the smallest fixture that can tell a drop from a no-op.
        """
        s = self._assembler(3).assemble(pass_number=1)
        assert s.count == 3 and s.withheld == ()

    def test_CONSERVATION_nothing_leaves_the_manifest_without_a_record(self):
        """🔴 REWRITTEN TWICE, and the second rewrite is the lesson.

        v1 collected the *callers of* `log.record` and asserted the set was `{_narrow}` — the wrong
        direction entirely: it checked that everything which RECORDS is `_narrow`, and said nothing
        about anything that DROPS without recording. It was green while `discover()` filtered
        silently.

        v2 tried to enumerate drop sites from the AST and was **VACUOUS**: `".append(" in
        ast.dump(fn)` is never true, because `ast.dump` renders the call as `attr='append'`. That
        branch was dead code, so the check only ever saw filtered comprehensions — and neither real
        drop site is one. A verifier proved it by deleting `log.record` from BOTH sites and watching
        the test stay green. **My own red-ability probe missed it because the function I injected
        was a comprehension** — I had unknowingly probed the one branch that worked.

        So this stops reading the module and **runs it**. The property P1 actually asserts is a
        conservation law:

            rows returned  +  narrowings recorded  ==  rows supplied

        Nothing vanishes without a record. That cannot be defeated by how an AST renders, by a new
        function shape, or by a helper written in a style the classifier did not anticipate — a
        silent drop breaks the arithmetic whatever it looks like.
        """
        import inspect
        from app.agentruntime import surface as mod

        doc = build([
            admit(_tool("book_list")),
            admit(_tool("book_get")),
            admit(_skill("world_setup", ("book_list",))),
        ])
        supplied = len(doc["declarations"])
        checked: list[str] = []

        # Every module-level function whose first parameter is a manifest document. Enumerated by
        # SIGNATURE, so a narrowing helper added tomorrow is covered the day it is written — an
        # explicit list would be default-uncovered, the mistake this repo has a standard about.
        for name, fn in vars(mod).items():
            if not inspect.isfunction(fn) or name.startswith("_"):
                continue
            params = list(inspect.signature(fn).parameters)
            if not params or params[0] != "manifest_doc":
                continue
            for kind in ("tool", "skill", None):
                log = NarrowingLog()
                kwargs: dict = {}
                if "log" in params:
                    kwargs["log"] = log
                if "kind" in params:
                    kwargs["kind"] = kind
                elif kind is not None:
                    continue
                returned = fn(doc, **kwargs)
                assert len(returned) + len(log) == supplied, (
                    f"{name}(kind={kind!r}) lost {supplied - len(returned) - len(log)} "
                    f"declaration(s) with no {{tool, stage, reason, pass}} record"
                )
                checked.append(f"{name}({kind})")

        # The assembler is the other entry point, and it takes rules rather than a manifest.
        log = NarrowingLog()
        surface = SurfaceAssembler(doc, log=log).assemble(pass_number=1, pipeline=[
            Filter("token_budget", "over budget", field="id", op="eq", value="book_list"),
        ])
        assert surface.count + len(log) == supplied, "the assembler lost a declaration silently"
        checked.append("assemble")

        # NV-1: if nothing was enumerated, the conservation law was never applied to anything.
        assert len(checked) >= 3, f"the enumeration found almost nothing to check: {checked}"


class TestAnEmptySurfaceIsAStatementNotAGap:
    """REJECTS: 'no declarations are admitted' being indistinguishable from 'the assembler did not
    run'. Those produced the same screen in the defect that started this work."""

    def test_an_empty_manifest_yields_an_empty_surface_that_says_so(self):
        s = SurfaceAssembler(load(path=Path("nonexistent.json"))).assemble(pass_number=1)
        assert s.is_empty and s.count == 0 and s.names == ()

    def test_an_empty_surface_is_not_the_same_object_as_a_narrowed_one(self):
        """`is_empty` must mean 'nothing was admitted', which a caller can tell apart from
        'everything was withheld' by reading `withheld` — one is silence, the other is a decision."""
        doc = build([admit(_tool("book_list"))])
        s = SurfaceAssembler(doc).assemble(pass_number=1, pipeline=[
            Filter("token_budget", "over budget", field="id", op="in", value=()),
        ])
        assert s.is_empty and len(s.withheld) == 1


class TestThePackageImportsWhereItIsDEPLOYEDNotWhereItIsWritten:
    """🔴 REJECTS a defect the whole 49-test suite was structurally blind to.

    `import app.agentruntime` raised `IndexError` **in the running container**: `manifest.py` did
    `Path(__file__).resolve().parents[4]` at MODULE level, and the image flattens
    `services/chat-service/` to `/app`, so there were not four parents above it. Every submodule
    failed, in a fresh interpreter, before any code ran. A live verifier found it.

    **No test here could have.** Tests execute from the source tree, where the arithmetic is correct
    by construction — so the suite proved the layout it ran in, not the layout that ships. A path
    expression that counts directory levels encodes the *checkout*, and the deployed tree is a
    different one.

    This package imports only the standard library and itself (M2), which is what makes the
    regression testable at all: it can be copied to any depth and imported there.
    """

    def _import_at(self, tmp_path: Path, depth: int) -> subprocess.CompletedProcess:
        root = tmp_path
        for i in range(depth):
            root = root / f"d{i}"
        pkg = root / "app" / "agentruntime"
        pkg.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(_REPO / "services" / "chat-service" / "app" / "agentruntime", pkg)
        (root / "app" / "__init__.py").write_text("", encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-c",
             "import app.agentruntime as m; "
             "print(m.load()['declarations'], m.manifest_path())"],
            cwd=root, capture_output=True, text=True,
        )

    @pytest.mark.parametrize("depth", [0, 1, 4])
    def test_it_imports_at_any_depth(self, tmp_path, depth):
        """depth=0 is the container's shape: `/app/app/agentruntime`, with nothing above it."""
        r = self._import_at(tmp_path, depth)
        assert r.returncode == 0, f"import failed at depth {depth}:\n{r.stderr}"

    def test_with_no_manifest_anywhere_it_loads_EMPTY_rather_than_raising(self, tmp_path):
        """The fail-safe direction, at the one place it is easiest to get wrong. A missing manifest
        is a legitimate state — it means *no declarations* — so it must never be an import-time
        crash, and must never become *fall back to the catalog with 315 in it*."""
        r = self._import_at(tmp_path, 0)
        assert r.returncode == 0 and r.stdout.startswith("[]"), r.stderr

    def test_an_explicit_override_is_honoured(self, tmp_path):
        """Deployment resolves the path; the code does not guess it."""
        m = tmp_path / "elsewhere.json"
        m.write_text(json.dumps(build([admit(_tool("book_list"))])), encoding="utf-8")
        env = {**os.environ, "LOREWEAVE_AGENT_RUNTIME_MANIFEST": str(m)}
        r = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, sys.argv[1]); "
             "from app.agentruntime import load; print([d['id'] for d in load()['declarations']])",
             str(_REPO / "services" / "chat-service")],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 0 and "book_list" in r.stdout, r.stderr


class TestTheAssemblerRefusesAMalformedDocument:
    """A missing `declarations` key was served as an EMPTY surface — indistinguishable from
    'nothing is admitted', which is the one confusion `is_empty` exists to prevent."""

    def test_a_document_without_declarations_is_refused(self):
        with pytest.raises(ValueError, match="malformed"):
            SurfaceAssembler({"manifest_version": 1})

    def test_an_explicitly_empty_catalog_is_accepted(self):
        assert SurfaceAssembler({"declarations": []}).assemble(pass_number=1).is_empty


class TestTheLogIsIndependentOfTheAssembler:
    """A turn spans several assemblies; the record must outlive any one of them."""

    def test_a_shared_log_accumulates_across_assemblers(self):
        log = NarrowingLog()
        doc = build([admit(_tool("book_list"))])
        for p in (1, 2):
            SurfaceAssembler(doc, log=log).assemble(pass_number=p, pipeline=[
                Filter("token_budget", "over budget", field="id", op="in", value=()),
            ])
        assert len(log) == 2 and log.stages() == {"token_budget"}


# ── 1.8b · one canonical serialisation ──────────────────────────────────────────────────────────


class TestCanonicalSerialisation:
    """REJECTS the defects that make a digest lie, all of which are SILENT.

    A canonicalisation defect never raises. It produces two digests for one value, or one digest for
    two values, and the consumer reads a plausible number either way. The repository already carries
    **18 distinct canonical-JSON implementations, 5 flag variants and 0 shared helpers**, with a
    precedent of digests permanently baselined because a serializer froze — so these are the rules
    that must hold before the first digest is persisted, not after.
    """

    def test_key_order_does_not_change_the_digest(self):
        assert canon.digest({"a": 1, "b": 2}) == canon.digest({"b": 2, "a": 1})

    def test_the_same_grapheme_hashes_the_same_in_either_unicode_form(self):
        """U-1's decision applied to content-addressing. Without it the same visible text produces
        two content addresses, and a drift check reports a change nobody made."""
        import unicodedata
        s = "Tạo chương mới"
        assert unicodedata.normalize("NFD", s) != unicodedata.normalize("NFC", s)
        assert canon.digest(unicodedata.normalize("NFD", s)) == \
            canon.digest(unicodedata.normalize("NFC", s))

    def test_a_float_is_REFUSED_rather_than_formatted(self):
        """repr varies by platform and version, and the variation is invisible in the digest it
        changes. A caller that needs a number decides its own representation, where the decision is
        visible to a reader."""
        with pytest.raises(canon.NotCanonicalisable, match="float"):
            canon.digest({"score": 0.1})

    def test_a_set_is_refused_because_it_has_no_order(self):
        with pytest.raises(canon.NotCanonicalisable, match="no order"):
            canon.digest({"names": {"a", "b"}})

    def test_a_bool_is_not_swallowed_by_the_int_branch(self):
        """`bool` subclasses `int`, so an int-first check turns True into 1 — two different values,
        one digest."""
        assert canon.digest(True) != canon.digest(1)

    def test_the_version_prefix_is_INSIDE_the_hashed_bytes(self):
        """Without it, a future change to these rules collides silently with the old format and a
        serializer change is indistinguishable from a content change — which is exactly how digests
        end up permanently baselined."""
        assert canon.canonical_bytes({}).startswith(canon.CANON_VERSION.encode())
        assert canon.CANON_VERSION.encode() in canon.canonical_bytes("x")

    def test_distinct_values_do_not_collide(self):
        seen = {canon.digest(v) for v in ({"a": 1}, {"a": "1"}, {"a": [1]}, {"a": {"1": None}})}
        assert len(seen) == 4

    def test_there_is_exactly_one_CANONICAL_implementation_in_the_package(self):
        """The whole point. 18 copies exist repo-wide; this package gets one.

        🔴 **NARROWED ONCE, AND THE NARROWING IS THE INTERESTING PART.** The first version forbade
        every `json.dumps`, and it caught `manifest.py`'s file write — which is **not** a second
        canonical serialiser. That call pretty-prints the manifest for a human reader and for diffs;
        the canonical form exists to be *hashed*. Two different jobs, and the file on disk is
        deliberately not the hashed bytes — a reader reproduces a digest by calling
        `canon.digest(load())`, not by eyeballing the file.

        Narrowing a test to make it pass is the move this run has a rule against, so the replacement
        is **stricter about the thing that matters**: it forbids the *markers of canonicalisation* —
        a hash, or a sort/separator-pinned dump — anywhere but `canon.py`. A second pretty-printer is
        harmless; a second thing that decides what bytes get hashed is the defect.
        """
        import re
        offenders = []
        for f in (_REPO / "services" / "chat-service" / "app" / "agentruntime").glob("*.py"):
            if f.name == "canon.py":
                continue
            src = f.read_text("utf-8")
            for pat in (r"hashlib", r"sort_keys\s*=", r"separators\s*="):
                for m in re.finditer(pat, src):
                    offenders.append(f"{f.name}:{src[:m.start()].count(chr(10)) + 1} {pat}")
        assert not offenders, f"a second canonicalisation: {offenders}"


# ── 1.8a · narrowing stages are data, and the ordering is explicit ──────────────────────────────


class TestStageKindsAreDataNotClosures:
    """§0.14.1 — REJECTS the shape the old `keep: Callable` could not hold, and the shapes a
    careless replacement would re-admit.

    `budget_names_by_tokens` is a **running accumulator over a sort order**, not a per-row
    predicate — and **6 of the 9 rule fixtures here were already named `token_budget`**, so the
    fixtures encoded a shape the type could not express. A closure is also not content-addressable:
    two entirely different narrowings hash the same, so a pipeline of lambdas has no identity.
    """

    def _doc(self, n=4):
        return {"declarations": [
            {"id": f"t{i}", "kind": "tool", "cost": i + 1, "lane": "read"} for i in range(n)
        ]}

    def test_a_budget_walks_the_ranking_and_cuts_the_tail(self):
        s = SurfaceAssembler(self._doc()).assemble(pass_number=1, pipeline=[
            OrderBy(keys=(("lane", "asc"),)),
            TakeWhileBudget("token_budget", "over budget", budget=6),
        ])
        assert s.names == ("t0", "t1", "t2")            # 1+2+3 fits, 4 does not

    def test_a_rank_dependent_stage_without_an_order_is_REFUSED(self):
        """A budget over an unordered collection selects an arbitrary subset — the legacy defect
        where `active_tool_names` is a `set` iterated unsorted, and `tools` is the first
        prompt-cache block. Rejected at construction of the assembly, not at use."""
        for stage in (TopK("s", "r", k=1), TakeWhileBudget("s", "r", budget=1)):
            with pytest.raises(ValueError, match="no order_by precedes it"):
                SurfaceAssembler(self._doc()).assemble(pass_number=1, pipeline=[stage])

    def test_the_record_says_WHY_THIS_ONE_and_not_that_one(self):
        """§0.14.1a rule 6. `{stage: token_budget, reason: over budget}` says *that* a declaration
        was cut; it cannot answer the only question a person debugging a missing tool has."""
        a = SurfaceAssembler(self._doc())
        s = a.assemble(pass_number=1, pipeline=[
            OrderBy(keys=(("lane", "asc"),)),
            TakeWhileBudget("token_budget", "over budget", budget=6),
        ])
        cut = s.withheld[0]
        assert cut["tool"] == "t3" and cut["rank"] == 3
        assert cut["ordered_by"] == [["lane", "asc"], ["id", "asc"]]

    def test_a_per_row_stage_records_no_rank_because_the_question_does_not_arise(self):
        s = SurfaceAssembler(self._doc()).assemble(pass_number=1, pipeline=[
            Filter("intent_gate", "off-intent", field="id", op="not_in", value=("t1",)),
        ])
        assert "rank" not in s.withheld[0]

    def test_id_is_appended_as_the_final_ordering_component_always(self):
        """Equal keys are not an edge case: an embedding failure yields all-zero relevance on every
        row, and U-2 shows that failure is reachable. Without a total order the budget's victim is
        whatever the iteration happened to produce."""
        assert OrderBy(keys=(("lane", "asc"),)).effective_keys() == (("lane", "asc"), ("id", "asc"))
        # ...and it is not appended twice when the caller already named it.
        assert OrderBy(keys=(("id", "desc"),)).effective_keys() == (("id", "desc"),)

    def test_cost_may_not_be_the_primary_ordering_component(self):
        """Cheapest-first optimises COUNT, not usefulness — a cheap useless declaration outranks an
        expensive essential one, and `book_list`, arm E's victim, is what loses to volume."""
        with pytest.raises(ValueError, match="may not be the primary"):
            OrderBy(keys=(("cost", "asc"), ("lane", "asc")))
        OrderBy(keys=(("lane", "asc"), ("cost", "asc")))   # legal as a tie-break

    def test_a_missing_ordering_field_is_a_REJECTION_not_a_fallback(self):
        """Silently falling back to id-order reorders the whole surface and cuts different
        declarations — arm E, arrived at by a default."""
        with pytest.raises(ValueError, match="rejection, not a fallback"):
            SurfaceAssembler(self._doc()).assemble(pass_number=1, pipeline=[
                OrderBy(keys=(("relevance", "desc"),)),
            ])

    def test_a_missing_cost_is_a_rejection_too(self):
        doc = {"declarations": [{"id": "t0", "kind": "tool", "lane": "read"}]}
        with pytest.raises(ValueError, match="rejection, not a fallback"):
            SurfaceAssembler(doc).assemble(pass_number=1, pipeline=[
                OrderBy(keys=(("lane", "asc"),)),
                TakeWhileBudget("token_budget", "over budget", budget=10),
            ])

    def test_the_operator_set_is_closed(self):
        """An unbounded operator set is a closure with extra steps. A stage needing a fourth is a
        finding to bring back to §0.14.1, not a licence to add one."""
        assert Filter.OPS == ("eq", "in", "not_in")
        with pytest.raises(ValueError, match="unknown op"):
            Filter("s", "r", field="id", op="regex", value="^b")

    def test_no_stage_kind_DECLARES_a_callable_field(self):
        """The shape check, kept — and demoted to what it actually proves.

        🔴 A verifier measured this test seeing `['str','str','str','str','Any']` and passing, while
        **two live routes to arbitrary logic were open**. It inspects DECLARED FIELD TYPES; both
        routes live in runtime values and in the dispatch. It is red-able only for the shape already
        removed. The two tests below are the ones that gate the behaviour.
        """
        import dataclasses
        for kind in (Filter, AllowList, DenyList, OrderBy, TopK, TakeWhileBudget):
            for f in dataclasses.fields(kind):
                assert "Callable" not in str(f.type), f"{kind.__name__}.{f.name} is a closure"

    def test_AN_ARBITRARY_STAGE_OBJECT_IS_REFUSED_AT_THE_PIPELINE_BOUNDARY(self):
        """🔴 ROUTE 1, MEASURED BY A VERIFIER: `assemble` dispatched on `stage.keep(row)` by duck
        typing and nothing required a stage to be one of the six. A four-line class holding a lambda,
        never imported from the package, narrowed the surface — conservation law satisfied,
        `validate_pipeline` silent. `NarrowingRule(keep=Callable)` had not been removed; it had been
        un-named."""
        class ArbitraryStage:
            stage, reason = "custom", "because my lambda said so"

            def __init__(self, fn):
                self.fn = fn

            def keep(self, row):
                return self.fn(row)

        with pytest.raises(ValueError, match="not one of the six stage kinds"):
            SurfaceAssembler(self._doc()).assemble(
                pass_number=1, pipeline=[ArbitraryStage(lambda r: r["id"] in ("t0", "t2"))],
            )

    def test_a_SUBCLASS_of_a_kind_is_refused_too(self):
        """Membership is by exact type. A subclass overriding `keep` is the same closure arriving
        through inheritance, and `isinstance` would welcome it."""
        class SneakyFilter(Filter):
            def keep(self, row):
                return row["id"].startswith("t0")

        with pytest.raises(ValueError, match="not one of the six stage kinds"):
            SurfaceAssembler(self._doc()).assemble(
                pass_number=1,
                pipeline=[SneakyFilter("s", "r", field="id", op="eq", value="t0")],
            )

    def test_THE_OPERAND_IS_BOUNDED_NOT_ONLY_THE_OPERATOR(self):
        """🔴 ROUTE 2, MEASURED: `value: Any` re-admitted arbitrary logic through Python's own
        protocols. A custom `__contains__` gives `op="in"` the behaviour of a regex stage with **zero
        new operators**, and `__eq__` does the same for `eq`. The design reasoned about the operator
        VOCABULARY and never about the OPERAND, so its whole argument walked past this field."""
        import re

        class Regexish:
            def __contains__(self, x):
                return bool(re.match(r"^b", str(x)))

        class EqAnything:
            def __eq__(self, other):
                return str(other).endswith("_list")

        with pytest.raises(ValueError, match="custom __contains__"):
            Filter("s", "r", field="id", op="in", value=Regexish())
        with pytest.raises(ValueError, match="custom __eq__"):
            Filter("s", "r", field="id", op="eq", value=EqAnything())
        with pytest.raises(ValueError, match="custom __eq__"):
            Filter("s", "r", field="id", op="eq", value=lambda r: True)
        # ...and a str SUBCLASS overriding __eq__ passes isinstance, which is why the check is exact.
        class Sneaky(str):
            def __eq__(self, other):
                return True

        with pytest.raises(ValueError, match="custom __eq__"):
            Filter("s", "r", field="id", op="eq", value=Sneaky("t0"))

        # The legitimate operands still work.
        Filter("s", "r", field="id", op="eq", value="t0")
        Filter("s", "r", field="id", op="in", value=("t0", "t1"))
        Filter("s", "r", field="lane", op="eq", value=None)

    def test_every_kind_is_CONTENT_ADDRESSABLE__which_was_the_stated_reason(self):
        """§0.14.1's second justification: *a closure is not content-addressable, so a pipeline built
        from closures has no identity.* A verifier noted the property held only over the well-behaved
        subset — `canon.digest` raised on a pipeline carrying a `Regexish` value. With the operand
        bounded, every constructible stage is now digestible, so the justification is true of the
        whole kind set rather than of the examples."""
        import dataclasses

        from app.agentruntime import canon
        stages = [
            OrderBy(keys=(("lane", "asc"),)),
            Filter("s", "r", field="id", op="in", value=("t0",)),
            AllowList("s", "r", names=("t0",)),
            DenyList("s", "r", names=("t1",)),
            TopK("s", "r", k=2),
            TakeWhileBudget("s", "r", budget=6),
        ]
        digests = {canon.digest(dataclasses.asdict(s)) for s in stages}
        assert len(digests) == len(stages), "two different stages hashed the same"

    def test_EVERY_OPERAND_IS_BOUNDED_not_only_the_one_a_verifier_named(self):
        """🔴 THE FIRST FIX BOUNDED `Filter.value` AND LEFT SIX OTHER OPERANDS OPEN, because it
        reasoned about the field the verifier had pointed at rather than about the set.

        Each of these was **measured** reaching the narrowing decision: `TakeWhileBudget.budget` is
        compared against a running total once per row, so a custom `__lt__` decides every cut;
        `Filter.field` and `cost_field` are `row.get()` keys, so `__hash__`/`__eq__` choose which
        column is read; `TopK.k` reaches a slice through `__index__`; `OrderBy.keys` and
        `AllowList.names` are containers that can decide their own iteration and membership.
        """
        class Sneaky(int):
            def __lt__(self, other):
                return True

            def __index__(self):
                return 999

        class SneakyKey(str):
            def __hash__(self):
                return hash("id")

            def __eq__(self, other):
                return True

        for ctor, match in (
            (lambda: TakeWhileBudget("s", "r", budget=Sneaky(1)), "budget is a Sneaky"),
            (lambda: TakeWhileBudget("s", "r", budget=1, cost_field=SneakyKey("cost")),
             "cost_field is a SneakyKey"),
            (lambda: TopK("s", "r", k=Sneaky(1)), "k is a Sneaky"),
            (lambda: Filter("s", "r", field=SneakyKey("id"), op="eq", value="x"),
             "field is a SneakyKey"),
            (lambda: OrderBy(keys=[("lane", "asc")]), "keys is a list"),
            (lambda: OrderBy(keys=((SneakyKey("lane"), "asc"),)), "field is a SneakyKey"),
            (lambda: AllowList("s", "r", names=["t0"]), "names is a list"),
            (lambda: Filter(SneakyKey("s"), "r", field="id", op="eq", value="x"),
             "stage is a SneakyKey"),
        ):
            with pytest.raises(ValueError, match=match):
                ctor()

        # `bool` is an `int` subclass, and a boolean budget is a real typo shape.
        with pytest.raises(ValueError, match="budget is a bool"):
            TakeWhileBudget("s", "r", budget=True)

    def test_THE_OPERATOR_ITSELF_IS_AN_OPERAND(self):
        """🔴 `Filter.op` selects `keep()`'s branch **and** selects which validation branch runs.
        Bounding `value` while leaving `op` free bounds the argument and not the operator — the
        mirror of §0.14.1's original mistake, made inside the fix for it. Measured: a `str` subclass
        with a custom `__eq__` spells `'regex'` and satisfies `in self.OPS`."""
        class SneakyOp(str):
            def __eq__(self, other):
                return True

            def __hash__(self):
                return hash("eq")

        with pytest.raises(ValueError, match="op is a SneakyOp"):
            Filter("s", "r", field="id", op=SneakyOp("regex"), value="t0")

        class OpObj:
            def __eq__(self, other):
                return True

            def __hash__(self):
                return hash("in")

        with pytest.raises(ValueError, match="op is an? OpObj"):
            Filter("s", "r", field="id", op=OpObj(), value=("t0",))

    def test_THE_ORDERING_DIRECTION_IS_BOUNDED_TOO__it_chooses_who_survives(self):
        """`field` was bounded and `direction` was not, in the same loop. Measured: a direction
        spelled `'NONSENSE'` was accepted, the sort inverted, and end-to-end it decided which 2 of 4
        declarations reached the model — and the `ordered_by` record explaining the cut was then
        neither JSON- nor `canon`-serialisable."""
        class SneakyDir(str):
            def __eq__(self, other):
                return True

            def __hash__(self):
                return hash("asc")

        with pytest.raises(ValueError, match="direction is a SneakyDir"):
            OrderBy(keys=(("lane", SneakyDir("NONSENSE")),))
        with pytest.raises(ValueError, match="unknown direction"):
            OrderBy(keys=(("lane", "NONSENSE"),))

    def test_a_forged_ROW_VALUE_cannot_defeat_the_budget(self):
        """The stage side was exact and the ROW side was `isinstance`, so the bound stopped at the
        pipeline and the data walked in. Measured: a `SneakyCost(int)` whose `__radd__` returns the
        running total unchanged never spends budget, so nothing is ever cut."""
        class SneakyCost(int):
            def __radd__(self, other):
                return other

        doc = {"declarations": [
            {"id": f"t{i}", "kind": "tool", "cost": SneakyCost(9), "lane": "read"} for i in range(4)
        ]}
        with pytest.raises(ValueError, match="plain integer"):
            SurfaceAssembler(doc).assemble(pass_number=1, pipeline=[
                OrderBy(keys=(("lane", "asc"),)),
                TakeWhileBudget("token_budget", "over budget", budget=6),
            ])

    def test_the_identity_check_reaches_EVERY_site_not_just_the_one_reviewed(self):
        """🔴 `type(s) in _KIND_SET` was rewritten to `is` after a metaclass forgery; the two
        `type(x) not in self.SCALARS` sites were left as they were, and the same forgery passed
        both. One helper now, so a fourth site cannot disagree."""
        class Forge(type):
            def __eq__(cls, other):
                return True

            def __hash__(cls):
                return hash(str)

        class NotAStr(metaclass=Forge):
            pass

        assert type(NotAStr()) in (str,), "the forgery does not work, so this proves nothing"
        with pytest.raises(ValueError, match="filter value"):
            Filter("s", "r", field="id", op="eq", value=NotAStr())
        with pytest.raises(ValueError, match="tuple of scalars"):
            Filter("s", "r", field="id", op="in", value=(NotAStr(),))

    def test_TOP_K_ZERO_IS_REFUSED__the_default_narrows_to_nothing(self):
        """The same failure `_require_names` was written for, in the kind sitting right next to it —
        missed because the first fix looked at the two list kinds a verifier had named. `k=0` is the
        DEFAULT, so this arrives by omission rather than by decision."""
        with pytest.raises(ValueError, match="k=0 keeps nothing"):
            TopK("s", "r")
        TopK("s", "r", k=1)

    def test_a_METACLASS_cannot_forge_membership_in_the_kind_set(self):
        """🔴 `type(s) in _KIND_SET` is a `__eq__`/`__hash__` comparison, and both are overridable —
        on the METACLASS, so the class itself compares equal to a member. `is` against each member
        is the only comparison Python does not dispatch."""
        class Forge(type):
            def __eq__(cls, other):
                return True

            def __hash__(cls):
                return hash(Filter)

        class NotAFilter(metaclass=Forge):
            stage, reason = "custom", "forged"

            def keep(self, row):
                return row["id"] == "t0"

        assert type(NotAFilter()) in {Filter}, "the forgery does not work, so this proves nothing"
        with pytest.raises(ValueError, match="not one of the six stage kinds"):
            SurfaceAssembler(self._doc()).assemble(pass_number=1, pipeline=[NotAFilter()])

    def test_an_EMPTY_list_kind_is_refused_because_the_default_IS_the_failure(self):
        """"Rejected at construction, not at use" held for pipeline ORDER and not for stage
        PARAMETERS. `AllowList("s","r")` constructed happily and narrowed the surface to zero; the
        realistic way an empty list arrives is a config read that returned nothing."""
        with pytest.raises(ValueError, match="narrows the surface to NOTHING"):
            AllowList("s", "r")
        with pytest.raises(ValueError, match="removes nothing and registers nothing"):
            DenyList("s", "r", names=())
        with pytest.raises(ValueError, match="non-empty strings"):
            AllowList("s", "r", names=("t0", ""))

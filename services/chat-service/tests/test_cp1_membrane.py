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

from app.agentruntime import (
    Admitted,
    ContractViolation,
    Declaration,
    NarrowingLog,
    NarrowingRule,
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
        generate([admit(_tool("book_list")), admit(_tool("book_get"))], path=p)
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
                              "members": ["deleted_tool"]}],
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
            generate([admit(_skill("world_setup", ("nope",)))], path=p)
        assert not p.exists()


# ── 1.6 · C-0 — identity, with the owner DERIVED ────────────────────────────────────────────────

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

    def test_identity_carries_all_four_C0_fields(self):
        ident = identity_of(_tool())
        assert ident.id and ident.owning_service and ident.lifecycle and ident.contract_version


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
        s = a.assemble(pass_number=1, rules=[
            NarrowingRule("token_budget", "over budget", lambda r: r["id"] != "tool_1"),
        ])
        assert "tool_1" not in s.names
        assert a.log.records() == [
            {"tool": "tool_1", "stage": "token_budget", "reason": "over budget", "pass": 1},
        ]

    def test_the_withheld_set_travels_WITH_the_surface(self):
        """A narrowing the caller must go and find in a log is a narrowing that gets dropped at the
        first persistence boundary — which is how the legacy column came to be empty for the one
        stage it was built for."""
        s = self._assembler().assemble(pass_number=1, rules=[
            NarrowingRule("intent_gate", "not this intent", lambda r: r["id"] == "tool_0"),
        ])
        assert {w["tool"] for w in s.withheld} == {"tool_1", "tool_2"}

    def test_a_rule_without_a_stage_or_reason_cannot_be_built(self):
        """This is where 'every narrowing registers' stops being a discipline: the two fields P1
        needs are arguments of the rule, so a rule cannot be applied without them."""
        for stage, reason in (("", "r"), ("s", "")):
            with pytest.raises(ValueError, match="stage and its reason"):
                NarrowingRule(stage, reason, lambda r: True)

    def test_every_pass_is_recorded_separately(self):
        """REJECTS a timeless record. A verifier found 19 of 303 withheld declarations
        simultaneously advertised on every pass and could not tell a contradiction from a
        sequence — dropped at one stage then restored by a later one is coherent history."""
        a = self._assembler()
        rule = NarrowingRule("failure_breaker", "failed twice", lambda r: r["id"] != "tool_2")
        a.assemble(pass_number=1, rules=[rule])
        a.assemble(pass_number=2, rules=[rule])
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
        rule = NarrowingRule("token_budget", "over budget", lambda r: True)   # keeps everything
        original = SurfaceAssembler._narrow

        def silent(self, rows, rule, *, pass_number):    # drops one, records nothing
            return list(rows)[1:]

        SurfaceAssembler._narrow = silent
        try:
            with pytest.raises(AssertionError, match="with no .*record"):
                a.assemble(pass_number=1, rules=[rule])
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
        surface = SurfaceAssembler(doc, log=log).assemble(pass_number=1, rules=[
            NarrowingRule("token_budget", "over budget", lambda r: r["id"] == "book_list"),
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
        s = SurfaceAssembler(doc).assemble(pass_number=1, rules=[
            NarrowingRule("token_budget", "over budget", lambda r: False),
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
            SurfaceAssembler(doc, log=log).assemble(pass_number=p, rules=[
                NarrowingRule("token_budget", "over budget", lambda r: False),
            ])
        assert len(log) == 2 and log.stages() == {"token_budget"}

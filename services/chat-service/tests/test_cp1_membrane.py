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
    rows_of,
    try_admit,
    validate_document,
)

_REPO = Path(__file__).resolve().parents[3]

#: 🔴 **ONE FIXTURE ROW, DERIVED FROM THE CONTRACT — because hand-written partial rows were a whole
#: class of false confidence in this file.** Ranking fixtures were `{id, kind, cost, lane}`, so every
#: ordering test ran against a shape the manifest can never produce; row-bound fixtures omitted the
#: §6.4 stamps, so they exercised a door the reader half never sees. `check_row` refusing them is the
#: door working, and completing them by hand at each site is how the next omission arrives.
#:
#: It is asserted against `ROW_FIELDS` at import, so adding a contract field without adding it here
#: fails immediately rather than leaving the fixtures a generation behind the writer.
_VALID_ROW = {
    "id": "t0",
    "kind": "tool",
    "owning_service": "book-service",
    "lifecycle": "admitted",
    "contract_version": "1.0.0",
    "admitted_against": "1.0.0",
    "members": [],
}


def _rows(n: int = 4, **over) -> list[dict]:
    """`n` valid rows, `t0`..`t{n-1}`, each with a distinct `owning_service` so a ranking has
    something to rank on that a row can legitimately carry."""
    return [{**_VALID_ROW, "id": f"t{i}", "owning_service": f"svc{i}", **over} for i in range(n)]


def _doc(rows=None, **over) -> dict:
    """🔴 **ONE DOCUMENT FIXTURE, DERIVED FROM THE CONTRACT — the row lesson, one level up.**

    Twenty-seven document literals in this file were written as `{"declarations": [...]}`, with
    **neither §6.4 stamp**, because `rows_of` never read them. A verifier measured what that hid:
    **24 of 24 cells SERVED** — four exported doors handing rows to a consumer out of a document
    carrying `manifest_version: 999`, `contract_version: "banana"`, either stamp missing, or an
    undefined top-level key, all of which `load()` refuses.

    So the fixtures were a shape the manifest can never produce, and every test built on one was
    exercising a door the reader half never sees. That is the same sentence `_VALID_ROW`'s comment
    already carries, and completing a document by hand at each site is how the next omission
    arrives.
    """
    return {"manifest_version": 1, "contract_version": "1.0.0",
            "declarations": _rows() if rows is None else rows, **over}


def _tool(id_: str = "book_list", **kw) -> Declaration:
    kw.setdefault("source_path", "services/book-service/internal/api/list.go")
    return Declaration(id=id_, kind="tool", **kw)


def _skill(id_: str = "world_setup", members=("book_list",)) -> Declaration:
    return Declaration(id=id_, kind="skill", members=tuple(members),
                       source_path="services/chat-service/app/skills/world.py")



def _dead_imports(src: str, label: str = "<module>") -> list[str]:
    """Every import in `src` that binds a name the module never uses. **One implementation.**

    \U0001F534 The first version of this rule counted a name appearing in **any whitespace-delimited
    token of any string literal** as a use. A verifier restored the exact seven-round B18-11 defect
    with the suite green: re-add `from . import canon`, put the bare token `canon` in a docstring,
    **1 passed**. Not adversarial prose - ORDINARY prose, in files whose docstrings are rewritten
    every round. Fourth "a test satisfied by a comment" in this run, and the second inside a repair
    for another.

    Enumerated by that verifier at **3 of 11** shapes caught. The naive repair is also wrong and was
    executed: deleting the string term reds **~30 re-exports in `__init__.py`**, which are used only
    through the `__all__` string list. So the term is load-bearing for exactly one construct, and the
    narrowing is to that construct.

    \U0001F534 **AND IT LIVES HERE, ONCE.** The gate and its control had two copies of this walk, and
    the duplicate-import clause went into one of them - two implementations of one rule, which is the
    defect this run has recorded twelve times, committed inside the repair for it.
    """
    import ast

    tree = ast.parse(src)
    dead: list[str] = []

    bound: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        # `from __future__ import ...` binds a COMPILER DIRECTIVE, not a name. Excluded by module
        # rather than by name, so a future feature added later is covered too.
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
        for a in node.names:
            if a.name == "*":
                continue
            # A dotted `import a.b.c` with no `as` is either used as `a.b.c...` - in which case the
            # Name `a` appears - or it is a SIDE-EFFECT import, a legitimate registration pattern and
            # this gate's one measured false positive. Exempted deliberately; the residual is that a
            # dead `import os.path` is missed, which is the safe direction.
            if isinstance(node, ast.Import) and "." in a.name and not a.asname:
                continue
            # A LIST, not a dict keyed by name: the second dead import of a doubly-imported name was
            # overwritten and never reported.
            bound.append(((a.asname or a.name).split(".")[0], node.lineno))

    seen: dict[str, int] = {}
    for name, lineno in list(bound):
        if name in seen:
            dead.append(f"{label}:{lineno} imports {name} a second time, shadowing line {seen[name]}")
        else:
            seen[name] = lineno

    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    def _binds_locally(fn, name) -> bool:
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)) \
                    and n.id == name:
                return True
            if isinstance(n, ast.arg) and n.arg == name:
                return True
        return False

    def _shadowed(node, name) -> bool:
        # \U0001F534 **A LOCAL THAT SHADOWS THE IMPORT IS NOT A USE OF IT.** `import re` followed by a
        # function doing `re = 1; return re` reads as "used" to any flat name scan - measured.
        cur = parent.get(node)
        while cur is not None:
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) \
                    and _binds_locally(cur, name):
                return True
            cur = parent.get(cur)
        return False

    # `Load` context only, and \U0001F534 the `n.attr` term is GONE: it made an unrelated `c.re` count
    # as a use of `import re`, and it was never needed - `canon.digest` is an `Attribute` whose
    # `.value` is the `Name` `canon`, which this already sees.
    used = {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and not _shadowed(n, n.id)}
    # The string term, narrowed from "every token of every literal" to the elements of a
    # module-level `__all__` - the one construct where a name is genuinely used through a string.
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            continue
        for el in ast.walk(node):
            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                used.add(el.value)

    for name, lineno in bound:
        # \U0001F534 The `startswith("__")` exclusion is gone: it exempted a dead `__`-prefixed alias,
        # which is a name like any other. `__future__` is excluded by module above.
        if name not in used:
            dead.append(f"{label}:{lineno} imports {name}, which it never uses")
    return dead


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
        # `{}` is malformed in three ways at once, and the DOCUMENT check now reaches it first —
        # which is the finding of the round that added `check_document` working. Both refusals are
        # asserted, because "the exported reader refuses a broken document" is the claim and
        # matching only `rows_of`'s own sentence bound the test to whichever clause happened to fire
        # first.
        with pytest.raises(UntrustedRow, match="manifest_version"):
            declarations({})
        # ...and a document whose stamps are RIGHT and whose `declarations` key is absent still
        # reaches the sentence this test was written for. Without this half, moving the document
        # check ahead of the row check would have silently retired the guard.
        with pytest.raises(ValueError, match="malformed"):
            declarations({"manifest_version": 1, "contract_version": "1.0.0"})

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

    def test_the_allowlist_is_an_allowlist(self, tmp_path):
        """A denylist is default-permitted: a legacy module written tomorrow would be reachable
        until someone remembered to add it. The direction of the list is the gate.

        🔴 **THIS ASSERTED `ALLOWED_EXTERNAL == {}` UNTIL CP-2.1, AND THAT WAS THE WRONG PROPERTY
        ALL ALONG.** Emptiness was true and easy to check, and it would have been *deleted* by the
        first legitimate entry — which is what a guard that measures a coincidence rather than its
        subject always does. The subject is the DIRECTION: a module nobody decided about is
        refused. That is checked behaviourally here, against a name no allowlist will ever hold,
        so this guard survives every future entry instead of being edited away by one."""
        g = _gate()
        p = tmp_path / "assembly.py"          # the most-permitted file in the package
        p.write_text("import nobody_decided_about_this\n", encoding="utf-8")
        assert g._violations_in(p), "an undecided module was admitted - the list ran as a denylist"
        for module, reason in g.ALLOWED_EXTERNAL.items():
            assert len(reason) > 40 and "CP-" in reason, (
                f"{module} is admitted without a reason naming the decision that admitted it"
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
                   "lifecycle": "admitted", "contract_version": "1.0.0",
                   "admitted_against": "1.0.0", "members": []}
        planted_surfaced = {r["id"] for r in discover(_doc([planted]))}
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

    def test_THE_QUEUE_IS_EMPTY_BY_CONSTRUCTION__P4_IS_NOT_SATISFIED_HERE(self, monkeypatch, tmp_path):
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
        # 🔴 **AND IT WAS STILL BLIND TO THE ONE LANDING SITE §6.4.1's OWN ARGUMENT NAMES.** Four
        # consecutive verifiers built the mechanism inside `generate()` — the only real writer —
        # proved it on disk (`QUEUE=['book_get']`, draining to `[]`, the file loading cleanly) and
        # measured this test **green**, because its only exit is `build`'s refusal and the mechanism
        # does not touch `build`. The docstring above claimed it "reds the day the mechanism lands";
        # for the most likely landing site it did not, four rounds running.
        #
        # So the partial re-admission is now driven through **both** producers. A queue that appears
        # by either route reds.
        # ORDER MATTERS AND IT IS THE WHOLE POINT: the `generate()` route writes its pair at the
        # CURRENT version and amends afterwards, because a queue can only exist where a row's stamp
        # predates the document's. My first version amended first, so both files were written at one
        # version — and the test passed with a working mechanism underneath it, which is the same
        # vacuity it was being repaired for. Measured before it was believed.
        queue_gen = self._partial_via_generate(monkeypatch, tmp_path)   # amends to 3.0.0 inside
        queue_build = self._partial_via_build(after)                    # contract is 3.0.0 now
        for route, queue in (("generate()", queue_gen), ("build()", queue_build)):
            if queue:
                raise AssertionError(
                    f"§6.4's re-admission queue is NON-EMPTY via {route} ({queue}) — the "
                    f"grandfathering mechanism has LANDED. §6.4.1's FAIL record, §0.14.1c's row and "
                    f"this test are all stale now: replace them with a drain test (fills on a "
                    f"breaking amendment, empties as each declaration is re-admitted). This test "
                    f"asserts a defect, and the defect is gone."
                )

    @staticmethod
    def _queue_of(doc) -> list[str]:
        return sorted(r["id"] for r in doc["declarations"]
                      if r["admitted_against"] != doc["contract_version"])

    def _partial_via_build(self, previous):
        """`None` means the mechanism is absent: `build` refuses to lose the row. Today's state."""
        try:
            return self._queue_of(build([admit(_tool("book_list"))], previous=previous))
        except UntrustedRow:
            return None

    def _partial_via_generate(self, monkeypatch, tmp_path):
        """The same partial re-admission through **`generate()`**, reading the queue off the FILE.

        §6.4.1's own argument puts the grandfathering mechanism here, and a mechanism that lands
        here never reaches `build`'s refusal — which is exactly why the `build`-only version of this
        test stayed green while a verifier ran a working queue underneath it.
        """
        path = tmp_path / "agent-runtime-manifest.json"
        # The pair on disk, stamped at the version in force NOW...
        first = generate([admit(_tool("book_list")), admit(_tool("book_get"))],
                         path=path, bootstrap=True)
        assert self._queue_of(first) == [], "the pre-amendment file already has a queue"
        # ...then the breaking amendment, and only then the partial re-admission. Written this way
        # round because amending FIRST leaves both stamps equal, and a queue cannot form.
        self._amend(monkeypatch, "3.0.0")
        try:
            generate([admit(_tool("book_list"))], path=path)
        except UntrustedRow:
            return None                      # the row cannot be lost: the mechanism is absent
        return self._queue_of(json.loads(path.read_text("utf-8")))

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

    def test_A_ROWS_OWN_GET_CANNOT_SMUGGLE_A_ROW_PAST_THE_VALIDATOR(self):
        """🔴 **I MATERIALISED THE ITERATION AND RETURNED THE ORIGINAL CONTAINER.**

        The rows were copied so the loop could not be fed two different sequences — and then
        `return doc` handed back the document that came in. A row's `.get()` is **user code**, and
        the validator calls it inside its own loop: that call appended a hand-typed row to the
        caller's plain list. `validate_document` **accepted**, and every consumer then saw
        `['book_list', 'TYPED BY HAND!!']` with `contract_version: "banana"`. **No container
        subclass was needed** — the escape was the return value, not the input.
        """
        class Smuggler(dict):
            def __init__(self, real, target):
                super().__init__(real)
                self._target = target
                self._fired = False

            def get(self, key, default=None):
                if key == "members" and not self._fired:
                    self._fired = True
                    self._target.append({"id": "TYPED_BY_HAND", "kind": "tool",
                                         "owning_service": "book-service", "lifecycle": "admitted",
                                         "contract_version": "banana", "admitted_against": None,
                                         "members": []})
                return super().get(key, default)

        good = build([admit(_tool("book_list"))], previous=None)
        rows = good["declarations"]
        doc = {**good, "declarations": rows}
        rows[0] = Smuggler(rows[0], rows)

        # 🔴 **THIS TEST WENT VACUOUS AND REPORTED THE SAME GREEN AS A TEST THAT RAN.** Closing the
        # row schema made `check_row` refuse the `dict` subclass *before* its `.get` is ever called,
        # so control reached `except UntrustedRow: return` and the assertion below was never
        # evaluated — a verifier proved it by reverting the fix this test exists for and measuring
        # the suite still green. A coverage regression created by an improvement, invisible because
        # an early `return` is indistinguishable from a pass.
        #
        # So the refusal is now ASSERTED rather than caught, and the property the fix actually buys
        # gets its own assertion on a vehicle that survives every door.
        with pytest.raises(UntrustedRow, match="is a Smuggler"):
            validate_document(doc)

        # The live half: a plain, fully valid document. What R13's fix bought is that **nothing the
        # validator returns was read after it was checked** — neither the rows nor the two document
        # stamps. Reverting either half of `return {manifest_version, contract_version, [dict(r)…]}`
        # to `{**doc, …}` or to `return doc` reds one of these three.
        plain = build([admit(_tool("book_list"))], previous=None)
        out = validate_document(plain)
        assert out is not plain, "the validator returned the caller's own document object"
        assert out["declarations"][0] is not plain["declarations"][0], (
            "the validator returned the caller's own ROW object; a row's `.get` is user code and "
            "this function calls it, so the object that leaves must be the copy that was checked"
        )
        # ...and the stamps are the validated values, not a second read of the caller's container —
        # `contract_version` is §6.4's queue comparand, so a re-read is a different comparand.
        assert out["contract_version"] == plain["contract_version"]
        assert out["manifest_version"] == plain["manifest_version"]

    def test_EVERY_ROW_FIELD_IS_BOUNDED__not_only_the_id(self):
        """🔴 `id` was bounded and every other field steers a decision. `OrderBy` sorts on any field
        a pipeline names, `TakeWhileBudget` accumulates one, `Filter` compares one — so an **unknown
        key with an exotic value, in plain JSON**, reaches the ranking that decides what the model
        sees. And `members` was unbounded at four exported doors, so `members: ['ghost']` travelled
        to the wire.

        **Production-reachable without an adversary**: a hand-edited or mis-generated manifest is
        precisely what this door exists for.
        """
        base = dict(_VALID_ROW)
        from app.agentruntime.contract import ContractViolation
        for bad in ({"members": "not-a-list"}, {"members": [""]}, {"members": [None]},
                    # 🔴 The class the type bound could not reach: an **undefined** field. A verifier
                    # steered `TakeWhileBudget` with a plain `"cost": 1000000000`, and no value bound
                    # can refuse a well-typed integer. What IS refusable is a key the contract never
                    # named — the row passed no clause for it, and every stage will rank on it.
                    {"weight": 999}, {"": 1},
                    # 🔴 **AND THE FOUR RANKING FIELDS ARE IN THIS LIST NOW, WHICH IS THE POINT.**
                    # The previous round wrote "they are refused today on purpose" in a comment and
                    # then NAMED all four in `ROW_FIELDS` four lines below, so both doors accepted a
                    # hand-typed `cost` and a hand-typed `relevance` — and a verifier measured
                    # `relevance` choosing which SINGLE declaration survives `TopK(1)`. Removing the
                    # four entries refuses the forged value outright and breaks nothing, because
                    # §0.14.1c puts their producers at CP-2 and CP-4 and nothing writes them today.
                    {"cost": 1000000000}, {"relevance": 9999}, {"lane": "read"}, {"tier": "hot"}):
            with pytest.raises(ContractViolation):
                rows_of(_doc([{**base, **bad}]))
        # ...and the row the WRITER produces still passes, which is what makes the closure honest
        # rather than merely strict: `_row` emits exactly `ROW_FIELDS` and no more.
        rows_of(_doc([dict(_VALID_ROW)]))

    # ── The bounds that were tightened with no test over any of them ────────────────────────────
    #
    # 🔴 A verifier weakened each of the four one at a time and measured the suite **green** on
    # three, then proved each weakening restores a real defect end-to-end. *"A fix without a
    # red-able test is not a closed finding"* is a standing rule of this run, and three consecutive
    # rounds shipped strengthenings that nothing would notice being reverted. These are those tests,
    # and each names the defect its weakening restores rather than the line it covers.

    def test_BOTH_DOORS_REFUSE_THE_SAME_ROW__and_the_consumer_door_is_not_the_weaker_one(self):
        """🔴 **THE CONSOLIDATION WAS OF THE SHAPE, AND THE VALIDITY STAYED SPLIT — IN THE LEAKING
        DIRECTION.** A verifier drove fifteen shapes through both doors and measured **nine** that
        `rows_of` accepted and `load()` refused. `rows_of` is the door `SurfaceAssembler`, `discover`
        and `declarations` all stand behind, and **none of them goes through `load()`** — so the
        weaker definition was the one facing the consumer. `members: ['ghost']` reached the wire for
        three consecutive rounds this way, each row individually valid.

        This also guards the `validate_document` half, which had **no test at all**: deleting its
        `check_row` call left the suite green while restoring the two-definitions defect the previous
        round was named for.
        """
        cases = {
            "unknown kind": {"kind": "nonsense"},
            "unknown lifecycle": {"lifecycle": "??"},
            "id matching no identifier pattern": {"id": "!!! HAND TYPED !!!"},
            "empty id": {"id": ""},
            "a skill with no members": {"kind": "skill", "members": []},
            "a tool WITH members": {"kind": "tool", "members": ["t9"]},
            "a member naming nothing": {"kind": "skill", "members": ["ghost"]},
            "an owner nothing could derive": {"owning_service": ""},
            "an unreadable §6.4 stamp": {"admitted_against": "banana"},
        }
        for name, bad in cases.items():
            doc = {"manifest_version": 1, "contract_version": "1.0.0",
                   "declarations": [{**_VALID_ROW, **bad}]}
            with pytest.raises(UntrustedRow):
                validate_document(doc)
            with pytest.raises(UntrustedRow):
                rows_of(doc)
            # ...and through the two exported doors that reach a consumer without `load()`.
            with pytest.raises(UntrustedRow):
                discover(doc)
            with pytest.raises(UntrustedRow):
                SurfaceAssembler(doc).assemble(pass_number=1)

    def test_A_MISSING_REQUIRED_FIELD_IS_A_REFUSAL__not_an_uncaught_KeyError(self):
        """`check_row` dereferences `row["members"]` and `row["id"]` unconditionally, so the
        required-field loop is load-bearing for its OWN safety: removing it turns both exported
        doors into an uncaught `KeyError`, which is a stack trace at a boundary whose whole job is
        to produce a C-12 message naming the field."""
        for missing in sorted(_VALID_ROW):
            row = {k: v for k, v in _VALID_ROW.items() if k != missing}
            for door in (rows_of, validate_document):
                with pytest.raises(ContractViolation) as exc:
                    door({"manifest_version": 1, "contract_version": "1.0.0",
                          "declarations": [row]})
                assert missing in str(exc.value), (
                    f"the refusal for a missing {missing!r} does not name the field (C-12)"
                )

    def test_THE_SHAPE_HALF_REFUSES_AN_EMPTY_ID_ON_ITS_OWN(self):
        """🔴 **The guard the consolidation DELETED, and its restoration was SILENT.**

        `rows_of` carried `not _is_exactly(r.get("id"), str) or not r.get("id")`; moving it into
        `check_row_shape` reproduced the type half and dropped the non-empty half, so `id: ""` was
        refused before and accepted after — measured in one process against both sources.

        Restoring it in `check_row_shape` was not enough to make it *observable*: `check_row` also
        runs `check_contract`, whose identifier pattern refuses `""` for its own reason, so deleting
        the clause again left every door still red. **A guard that only ever fires behind another
        guard is untested by every test that goes through the door**, which is why this one is
        asserted at the shape function directly — the only place its absence can be seen.
        """
        from app.agentruntime.contract import check_row_shape
        check_row_shape(dict(_VALID_ROW), "row")                       # the control
        with pytest.raises(ContractViolation, match="is empty"):
            check_row_shape({**_VALID_ROW, "id": ""}, "row")

    def test_THE_DOCUMENT_IS_EXACTLY_A_DICT__the_fifth_TOCTOU(self):
        """🔴 **Open four rounds, and it survived this round's first fix too.** Every ROW was
        exact-typed while the DOCUMENT supplying them was only `isinstance`-checked — inside the same
        function. Measured: a `dict` subclass answered `manifest_version=1` / `contract_version=
        '1.0.0'` to the checks and `999` / `'banana'` to the `{**doc}` at the return.
        `contract_version` is §6.4's queue comparand, so the document that left carried a different
        comparand from the one that was validated.

        It needs its own vehicle: the smuggler test's row subclass is refused by `check_row` long
        before the document is re-read, so that test cannot see this.
        """
        class LyingDoc(dict):
            def __init__(self, real):
                super().__init__(real)
                self._reads = 0

            def get(self, key, default=None):
                if key == "contract_version":
                    self._reads += 1
                    return "1.0.0" if self._reads == 1 else "banana"
                return super().get(key, default)

        good = build([admit(_tool("book_list"))], previous=None)
        with pytest.raises(UntrustedRow, match="LyingDoc"):
            validate_document(LyingDoc(good))

    def test_THE_ROW_TYPE_BOUND_IS_EXACT__because_isinstance_restores_the_TOCTOU(self):
        """🔴 Weakening `type(row) is not dict` to `isinstance` restores the sixth TOCTOU **in
        full** — measured: the validator contract-checked `'book_list'` and the consumer received
        `'!! HAND TYPED !!'`. The closure of that finding rests entirely on this one line, and
        nothing could see it."""
        class LyingRow(dict):
            def __init__(self, real):
                super().__init__(real)
                self._reads = 0

            def get(self, key, default=None):
                if key == "id":
                    self._reads += 1
                    return "book_list" if self._reads == 1 else "!! HAND TYPED !!"
                return super().get(key, default)

        doc = {"manifest_version": 1, "contract_version": "1.0.0",
               "declarations": [LyingRow(_VALID_ROW)]}
        for door in (rows_of, validate_document):
            with pytest.raises(UntrustedRow, match="LyingRow"):
                door(doc)

    def test_THE_FIELD_TYPE_BOUND_IS_EXACT__because_isinstance_restores_ARM_E_at_the_row(self):
        """🔴 Weakening the per-field bound to `isinstance` restores §0.14.1 **at the row**: a `str`
        subclass `id` whose `__eq__` lies made `AllowList(names=('NOTHING_MATCHES_THIS',))` keep the
        row — an unlisted declaration on the wire with no record at all, which is arm E reached
        through the data instead of through the rule. The subclass passes the identifier pattern, so
        the exact type is the only thing that refuses it."""
        class SneakyId(str):
            def __eq__(self, other):
                return True

            def __hash__(self):
                return hash("t0")

        doc = {"manifest_version": 1, "contract_version": "1.0.0",
               "declarations": [{**_VALID_ROW, "id": SneakyId("t0")}]}
        for door in (rows_of, validate_document):
            with pytest.raises(ContractViolation, match="SneakyId"):
                door(doc)

    def test_THE_WRITER_CHECKS_ITS_OWN_OUTPUT__the_third_door(self):
        """🔴 **The only function in this repository that PRODUCES a row did not consult the one
        definition of a row.** A verifier gave `_row` one plausible CP-4 field: `build()` accepted
        it, `generate()` wrote it to disk, and the refusal landed afterwards — at the next `load()`,
        or in CI. CP-4 adding a row field is a scheduled occurrence of exactly that.

        Driven through a real drift between a derivation and the contract, which is the shape that
        would actually produce it: `identity_of` is a separate function, and a row is assembled from
        what it returns rather than from what `check_contract` just approved.
        """
        from app.agentruntime import manifest as _m
        good = build([admit(_tool("book_list"))], previous=None)
        assert good["declarations"][0]["id"] == "book_list", "the control did not build"

        import app.agentruntime.contract as _c
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(_m, "identity_of", lambda d: _c.Identity(
                id="", owning_service="book-service", lifecycle="admitted"))
            with pytest.raises(ContractViolation, match="row.id"):
                build([admit(_tool("book_list"))], previous=None)

    def test_BUILD_PREVIOUS_USES_THE_SAME_DEFINITION__the_fourth_door(self):
        """🔴 `build(previous=)` held a third, weaker, hand-written definition — `isinstance(r,
        dict)`, `r.get("id")`, `r.get("contract_version")` — so a previous row carrying an undefined
        key, a dict-valued field or a non-string key was accepted here and refused by `rows_of`.
        `previous` is caller-supplied through the exported `build()`, in plain JSON."""
        prev = build([admit(_tool("book_list"))], previous=None)
        for bad in ({"weight": 999}, {"cost": 3}, {"lifecycle": {"a": 1}}, {"id": ""}):
            broken = {**prev, "declarations": [{**prev["declarations"][0], **bad}]}
            # 🔴 **AND THE CLASS AND ITS FIELDS ARE ASSERTED, NOT JUST THE REFUSAL.** Unifying the
            # exception hierarchy made `except UntrustedRow` here catch `ContractViolation` — a
            # subclass it did not have when the handler was written — and re-raise it FLAT, so the
            # same row refused by `rows_of` with a C-12 field path was refused here with prose. A
            # broader `except` catches more the moment the class it names gains a child, and the
            # test that only asked "did it refuse" could not see the difference.
            with pytest.raises(ContractViolation) as exc:
                build([admit(_tool("book_list"))], previous=broken)
            assert exc.value.field_path and exc.value.accepted, (
                f"C-12's structured fields were destroyed by a re-raise: {exc.value!r}"
            )

    def test_AN_EXPORTED_DOOR_REFUSES_WITH_ONE_DOCUMENTED_CLASS(self):
        """🔴 `rows_of` raised **`ContractViolation`** for a bad row and a bare **`ValueError`** for
        a bad document — two unrelated classes at one exported door, and neither was `UntrustedRow`,
        whose docstring is verbatim this case. It was also a breaking change: every pre-consolidation
        refusal there was a `ValueError`, and callers catch what a door used to raise. One class now,
        and it is still a `ValueError`, so no caller's `except` stopped working."""
        assert issubclass(ContractViolation, UntrustedRow)
        assert issubclass(UnresolvedReference, UntrustedRow)
        assert issubclass(UntrustedRow, ValueError)
        with pytest.raises(UntrustedRow):
            rows_of({})                                    # the document half
        with pytest.raises(UntrustedRow):
            rows_of({"declarations": [{**_VALID_ROW, "weight": 1}]})    # the row half

    def test_THE_SCHEMA_ITSELF_CANNOT_BE_MUTATED_AT_RUNTIME(self):
        """`check_row_shape` reads `ROW_FIELDS` twice — `key not in ROW_FIELDS`, then
        `ROW_FIELDS[key]` — while `ROW_REQUIRED` two lines away was already a `frozenset`. A verifier
        mutated the module global at runtime with no complaint, which is a check-read and a use-read
        over a mutable global: the new read-twice site introduced by the round that was measuring
        read-twice sites."""
        from app.agentruntime.contract import ROW_FIELDS, ROW_REQUIRED
        with pytest.raises(TypeError):
            ROW_FIELDS["cost"] = (int,)
        assert set(ROW_REQUIRED) <= set(ROW_FIELDS), "a required field the schema does not define"

    def test_AN_OPTIONAL_FIELD_IS_EXPRESSIBLE__because_CP2_needs_one(self):
        """🔴 The guard for the tier itself, not for today's contents. `ROW_REQUIRED =
        frozenset(ROW_FIELDS)` compares equal to the writer's output *and* leaves no optional tier,
        so a test over today's seven fields cannot tell the two apart — which is why the previous
        version of this guard was SILENT when the derivation was put back.

        What must stay true is that **naming a field does not make it mandatory**: CP-2 adds
        `relevance` and CP-4 adds `lane`/`tier`/`cost` to rows that already exist on disk, and if
        every new field is required on arrival those rows can only be migrated by deleting the
        manifest, which erases every origin stamp.

        🔴 **AND THIS GUARD IS DECLARED UNGUARDED, WITH THE REASON.** Reverting `ROW_REQUIRED` to
        `frozenset(ROW_FIELDS)` leaves it GREEN, because the derivation runs at import and a
        runtime patch of `ROW_FIELDS` cannot re-trigger it. The property — *naming a field does not
        make it mandatory* — has no subject until an optional field exists, which is CP-2. Saying so
        is the point: a red-ability sweep that counts this row as covered would be reporting the
        builder's intention rather than the tree's behaviour, and that is the exact failure a
        verifier caught in the previous round's self-measurement.
        """
        import app.agentruntime.contract as _c
        from types import MappingProxyType

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(_c, "ROW_FIELDS",
                       MappingProxyType({**_c.ROW_FIELDS, "relevance": (int,)}))
            _c.check_row(dict(_VALID_ROW), "row")              # absent: still valid
            _c.check_row({**_VALID_ROW, "relevance": 7}, "row")  # present: also valid
            with pytest.raises(ContractViolation):
                _c.check_row({**_VALID_ROW, "relevance": "7"}, "row")   # still bounded

    def test_NAMING_A_FIELD_DOES_NOT_MAKE_IT_MANDATORY(self):
        """🔴 **I DECLARED THIS UNGUARDABLE, WITH A REASON, AND THE REASON WAS TRUE OF ONE
        TECHNIQUE RATHER THAN OF THE PROPERTY.**

        I wrote: *"the derivation runs at import and a runtime patch of `ROW_FIELDS` cannot
        re-trigger it"* — correct about `monkeypatch`, and then used as a conclusion about whether
        the property has a subject at all. A verifier showed it does, in about ten lines, using an
        idiom this suite already uses: **re-execute the module's source with one field injected**,
        which separates the two states exactly. Literal `ROW_REQUIRED` → the row without the new
        field is valid; `frozenset(ROW_FIELDS)` → `ContractViolation: … is missing`.

        That was the third consecutive self-measurement wrong in the flattering direction, and a new
        species of it: **a negative existence claim from a single failed attempt.** A claim that
        something cannot be done deserves what a claim that something is broken gets — an execution.

        The property itself is what CP-2 and CP-4 need: `relevance`, `lane`, `tier` and `cost` all
        arrive on rows that already exist, and if naming a field makes it mandatory those rows can
        only be migrated by deleting the manifest, which erases every origin stamp.
        """
        import pathlib

        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "agentruntime" / "contract.py").read_text("utf-8")
        # 🔴 **RE-ANCHORED 2026-08-09 WHEN CP-4.c ADDED `lane`/`tier`/`cost`.** The probe was pinned
        # to `members` being the last entry, and it said so itself — *"the schema literal moved;
        # this probe is stale"* — rather than passing over a literal it no longer described. That is
        # the anchor discipline working: the guard failed loudly on a real edit instead of quietly
        # testing the wrong text. The property is unchanged and is now the one CP-4 depends on.
        anchor = '    "cost": (int,),\n})'
        assert src.count(anchor) == 1, "the schema literal moved; this probe is stale"
        injected = src.replace(anchor, '    "cost": (int,),\n    "salience": (int,),\n})')

        def _exec(text):
            # Executed under the package's own name so `from . import canon` resolves — the module
            # is real source, not a fixture, which is the point: the probe must see what ships.
            import sys
            import types
            ns = types.ModuleType("app.agentruntime._contract_probe")
            ns.__package__ = "app.agentruntime"
            sys.modules[ns.__name__] = ns
            try:
                exec(compile(text, "<probe>", "exec"), ns.__dict__)
                return ns.__dict__
            finally:
                sys.modules.pop(ns.__name__, None)

        mod = _exec(injected)
        assert "salience" in mod["ROW_FIELDS"], "the injection did not take"
        # The row a writer produces TODAY, with no `salience` — it must remain valid.
        mod["check_row"](dict(_VALID_ROW), "row")

        # ...and the control: derive REQUIRED from ALLOWED and the same row is refused, which is the
        # state this test exists to keep out.
        derived = injected.replace(
            'ROW_REQUIRED = frozenset({\n    "id", "kind", "owning_service", "lifecycle", '
            '"contract_version", "admitted_against", "members",\n})',
            "ROW_REQUIRED = frozenset(ROW_FIELDS)")
        assert derived != injected, "the control injection did not take, so this proves nothing"
        ctl = _exec(derived)
        with pytest.raises(ctl["ContractViolation"], match="salience"):
            ctl["check_row"](dict(_VALID_ROW), "row")

    def test_A_DUPLICATE_DECLARATION_ID_IS_REFUSED_AT_EVERY_DOOR(self):
        """A load-bearing check with no test, named by a verifier's own gap list. Two rows with one
        id make `AllowList`, `DenyList` and every `by-id` lookup answer for whichever the iteration
        reached first — the surface then depends on dict ordering rather than on the manifest."""
        doc = {"manifest_version": 1, "contract_version": "1.0.0",
               "declarations": [dict(_VALID_ROW), dict(_VALID_ROW)]}
        for door in (rows_of, validate_document):
            with pytest.raises(UntrustedRow, match="duplicate"):
                door(doc)

    def test_A_MALFORMED_PREVIOUS_IS_NOT_AN_EMPTY_ONE(self):
        """`previous={"declarations": None}` silently disabled the loss guard — the `or []` turned a
        malformed document into an empty one, which is the same "serve a broken thing as empty" that
        `rows_of` refuses by name. Load-bearing, and nothing checked it."""
        prev = build([admit(_tool("book_list"))], previous=None)
        for broken in (None, 0, "", {}, (r for r in ())):
            with pytest.raises(UntrustedRow):
                build([admit(_tool("book_get"))],
                      previous={**prev, "declarations": broken})

    def test_THE_DOCUMENT_SCHEMA_IS_CLOSED_TOO(self):
        """The row schema is closed and the document's was not, so a top-level key nothing defines
        passed no clause and `{**doc}` carried it to every reader. Same argument, one level up."""
        good = build([admit(_tool("book_list"))], previous=None)
        with pytest.raises(UntrustedRow, match="does not define"):
            validate_document({**good, "digest": "sha256:whatever"})

    def test_THE_REQUIRED_SET_IS_WHAT_THE_WRITER_ACTUALLY_EMITS__and_no_more(self):
        """🔴 **`ROW_REQUIRED = frozenset(ROW_FIELDS)` HAD NO OPTIONAL TIER, AND THAT MADE THE NEXT
        CHECKPOINT UNSHIPPABLE.** Deriving *required* from *allowed* stops the two drifting and makes
        every new field mandatory the instant it is named — so CP-2 adding `relevance` fails every
        row already on disk, and a verifier measured that there is no migration: `generate(path=)`
        raises, `bootstrap=True` does not apply while the file exists, and `rm` + bootstrap **erases
        every origin stamp** — the operation `generate`'s own guard exists to prevent — while §6.4's
        queue is not built.

        The sets are separate again, and this is the gate that keeps them honest: it compares
        `ROW_REQUIRED` against what the writer really emits, so a field added to `_row` without a
        decision about whether it is required fails here rather than at the next `load()`. An
        OPTIONAL field is now expressible, which is exactly what CP-2 and CP-4 need."""
        from app.agentruntime.contract import ROW_REQUIRED

        # 🔴 **THIS ASSERTED EQUALITY, WHICH IS `frozenset(ROW_FIELDS)` MOVED FROM THE
        # DEFINITION INTO THE TEST.** A verifier ran all three branches the failure message
        # prescribes and showed the one that matters: a field that is optional **and emitted** —
        # which is exactly what CP-2's `relevance` will be, because §0.14.1c gives it a producer —
        # reds this gate. So the comment saying an optional field is "expressible, which is what
        # CP-2 and CP-4 need" was false of the case it names.
        #
        # The three sets have an ORDER, not an identity: every REQUIRED field must be emitted (or
        # the writer produces rows its own reader refuses), and everything emitted must be ALLOWED.
        # A field between the two is optional, which is the tier the whole fix exists to create.
        from app.agentruntime.contract import ROW_FIELDS

        emitted = set(build([admit(_tool("book_list"))], previous=None)["declarations"][0])
        assert set(ROW_REQUIRED) <= emitted <= set(ROW_FIELDS), (
            f"the writer emits {sorted(emitted)}; ROW_REQUIRED is {sorted(ROW_REQUIRED)} and "
            f"ROW_FIELDS is {sorted(ROW_FIELDS)}. A required field the writer does not emit makes "
            f"every generated row fail its own reader; an emitted field the schema does not allow "
            f"makes `generate()` write a document `load()` refuses."
        )

    def test_a_document_with_NO_declarations_key_is_not_an_empty_one(self):
        """`.get("declarations", [])` served a missing key as empty — the exact confusion `rows_of`
        refuses by name two modules over, inside the function whose job is to notice a declaration
        that vanished. Reachable with plain JSON: a caller that built the dict wrong disabled the
        loss guard."""
        with pytest.raises(UntrustedRow, match="no `declarations` key"):
            build([admit(_tool("book_list"))], previous={"manifest_version": 1})

    def test_the_OUTER_previous_is_checked_too_not_only_the_inner_one(self):
        """The inner `previous.declarations` was guarded and the outer `previous or {}` was not —
        eight malformed shapes still accepted, the previous round's finding verbatim. Fixing the
        member a reviewer named rather than the set is this run's most-repeated failure."""
        for bad in ([], "not a doc", 7, ("declarations", [])):
            with pytest.raises(UntrustedRow, match="not a plain object"):
                build([admit(_tool("book_list"))], previous=bad)

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

    This package imports the standard library, itself, and — since CP-2.1 — `pydantic_ai` in one
    scoped file (M2's allowlist). That is what makes the regression testable at all: every one of
    those resolves from the interpreter rather than from the tree, so the package can be copied to
    any depth and imported there. 🔴 The sentence here used to say *"only the standard library and
    itself"*, and it was corrected in the same change that made it false rather than in the round
    that found it.
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
        # Fully stamped, so the DOCUMENT check passes and the missing `declarations` key is the one
        # thing left to refuse. The previous fixture (`{"manifest_version": 1}`) was malformed twice
        # over and would have gone on passing while binding nothing.
        with pytest.raises(ValueError, match="malformed"):
            SurfaceAssembler({"manifest_version": 1, "contract_version": "1.0.0"})
        # ...and the document half is refused at this door too — the 24-of-24 finding, at the door
        # the consumer actually stands behind.
        with pytest.raises(UntrustedRow, match="contract_version"):
            SurfaceAssembler({"manifest_version": 1, "declarations": []})

    def test_an_explicitly_empty_catalog_is_accepted(self):
        assert SurfaceAssembler(_doc([])).assemble(pass_number=1).is_empty


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
        # 🔴 THE FIXTURE WAS A PARTIAL ROW — `{id, kind, cost, lane}` and nothing else — so every
        # ranking test ran against a shape the manifest can never produce. Completing it by hand
        # then made it carry `cost` and `lane`, which the contract does not define **and now
        # refuses**: §0.14.1c puts their producers at CP-4, so a row carrying one came from a hand
        # edit. The fixture is a real row; the budget tests moved BELOW the door, where their
        # subject actually lives (see `_ranked`).
        return _doc(_rows(n))

    def _ranked(self, n=4):
        """Rows as a ranking stage sees them — **below the door, deliberately and with the reason
        stated.**

        `TakeWhileBudget` accumulates `cost`, and **no row can carry `cost` today**: §0.14.1c records
        its producer as CP-4 and the schema refuses the field, so the only way one appears on a
        manifest row is a text editor. Driving the budget through `assemble()` therefore requires a
        fixture that is a forgery, which is what the previous version of this class silently was.

        So the budget's semantics are exercised against rows handed straight to `_narrow`, and the
        DOOR's refusal of those same rows is asserted separately
        (`test_EVERY_ROW_FIELD_IS_BOUNDED__not_only_the_id`). Two mechanisms, two assertions — the
        pattern this file learned the hard way when one `pytest.raises` was made to stand for both
        and stopped being able to tell them apart.
        """
        return [{**r, "cost": i + 1} for i, r in enumerate(_rows(n))]

    def test_a_budget_walks_the_ranking_and_cuts_the_tail(self):
        kept = SurfaceAssembler(_doc([]))._narrow(
            self._ranked(), TakeWhileBudget("token_budget", "over budget", budget=6),
            pass_number=1, ordered_by=(("id", "asc"),),
        )
        assert [r["id"] for r in kept] == ["t0", "t1", "t2"]   # 1+2+3 fits, 4 does not

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
        a = SurfaceAssembler(_doc([]))
        a._narrow(self._ranked(), TakeWhileBudget("token_budget", "over budget", budget=6),
                  pass_number=1, ordered_by=(("owning_service", "asc"), ("id", "asc")))
        cut = a.log.records()[0]
        assert cut["tool"] == "t3" and cut["rank"] == 3
        assert cut["ordered_by"] == [["owning_service", "asc"], ["id", "asc"]]

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
        """And it is now unreachable any other way: `cost` is not a field a row may carry, so a
        budget over a manifest surface **always** takes this path until CP-4 builds the producer.
        That is the honest state of §0.14.1c rows 1–3 and it should be visible as a test, not only
        as a table cell."""
        with pytest.raises(ValueError, match="rejection, not a fallback"):
            SurfaceAssembler(self._doc(1)).assemble(pass_number=1, pipeline=[
                OrderBy(keys=(("owning_service", "asc"),)),
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

    def test_THE_OPERAND_SET_COMES_FROM_THE_DATACLASS_NOT_FROM_A_LIST_OF_CASES(self):
        """🔴 **CP-1 RECONCILIATION, 2026-08-09 — 1.8a's guard had the shape of 1.8a's defect.**

        The finding (A-3) was that the first fix *"bounded `Filter.value` and left SIX other
        operands open, because it reasoned about the field the verifier had pointed at rather than
        about the set."* The repair is real and every named operand is bounded — but the guard next
        door is **nine hand-written cases**, so a SEVENTH operand added tomorrow is unguarded and
        nothing says so. That is the same reasoning failure one layer up, and it is why this row sat
        `FAIL at round 8, fixed after, builder-only` until it was re-checked.

        So the denominator comes from `dataclasses.fields()` — the compiler's own list of what each
        stage kind carries — and every field must be named in a type-bounding call somewhere in the
        module. A new field cannot arrive unguarded and quietly pass.

        **The stated approximation:** the search is module-wide rather than per-class, so a field
        bounded inside a *different* class would count. Field names here are distinctive
        (`cost_field`, `keys`, `names`, `budget`), and the case this must catch — a NEW operand
        nobody bounded at all — is caught exactly. Narrowing it further would mean modelling
        inheritance of `__post_init__`, which buys nothing this row needs.
        """
        import ast
        import dataclasses

        from app.agentruntime.surface import STAGE_KINDS

        src = (_REPO / "services" / "chat-service" / "app" / "agentruntime"
               / "surface.py").read_text(encoding="utf-8")
        tree = ast.parse(src)

        #: Every `self.X` that reaches a call which BOUNDS a type. `_plain(self.x, ...)`,
        #: `type(self.x) is not ...` and `_is_exactly(self.x, ...)` are the three forms the module
        #: uses; anything else reading `self.x` is not a bound and must not count as one.
        bounded: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if fname not in {"_plain", "_is_exactly", "type"}:
                continue
            # Any attribute access, not only `self.x`: `AllowList.names` and `DenyList.names` are
            # bounded in a module-level validator that takes `stage`, so a `self.`-only scan called
            # them unbounded and would have driven a code change to satisfy the test rather than
            # the property. The receiver is not what makes a bound a bound.
            for arg in node.args:
                for n in ast.walk(arg):
                    if isinstance(n, ast.Attribute):
                        bounded.add(n.attr)

        unbounded = {}
        for kind in STAGE_KINDS:
            if not dataclasses.is_dataclass(kind):
                continue
            missing = [f.name for f in dataclasses.fields(kind) if f.name not in bounded]
            if missing:
                unbounded[kind.__name__] = missing
        assert not unbounded, (
            f"{unbounded} — a stage kind carries an operand that no type-bounding call names. "
            f"Every one of these reaches the narrowing decision, and an unbounded operand is "
            f"arbitrary logic deciding which declarations reach the model: a custom `__lt__` cuts "
            f"every row, a forged `__hash__`/`__eq__` chooses which column is read, an `__index__` "
            f"rewrites a slice. Bind it in `__post_init__` in the same change."
        )
        assert bounded, "the AST scan found no bounding calls at all; it is green over nothing"

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

        # 🔴 **I LOOSENED THIS TO `"plain integer|plain scalar"` SO IT WOULD PASS, AND WROTE
        # "BOTH GUARDS STAY" NEXT TO IT.** A verifier measured the consequence: with the
        # alternation, downgrading the door's bound to `isinstance` was **green**, because the test
        # could no longer tell the door's refusal from the budget's. The comment described a property
        # the assertion had just stopped checking.
        #
        # 🔴 **AND THE SPLIT THAT FIXED IT RE-LOOSENED THE DOOR HALF IN A NEW SPELLING** —
        # `pytest.raises((ValueError, _CV))` is the same alternation written as a type tuple, and the
        # next verifier measured the same weakening green through it. **Second consecutive round in
        # which this one assertion described a property it did not check.** The lesson that finally
        # took: an alternation over two mechanisms is not two assertions, whichever syntax spells it.
        #
        # So the budget's guard is asserted here, on the budget, by handing `_narrow` a row the door
        # never saw...
        with pytest.raises(ValueError, match="plain integer"):
            SurfaceAssembler(_doc([]))._narrow(
                [{"id": "t0", "cost": SneakyCost(9)}],
                TakeWhileBudget("token_budget", "over budget", budget=6),
                pass_number=1, ordered_by=(("id", "asc"),),
            )
        # ...and the door's is asserted on the door, with ONE class and the door's OWN reason.
        #
        # 🔴 **THE DOOR'S REASON CHANGED AT CP-4.c, AND IT CHANGED TO A STRONGER ONE.** Until then
        # `cost` was not a field a row could carry, so this forgery was refused by the *schema*
        # ("does not define") — a refusal that would have evaporated the moment CP-4 defined the
        # field, which is exactly what just happened. It is now refused by the **exact-type bound**:
        # `check_row_shape` compares `type(val) is int`, and `SneakyCost` is an int SUBCLASS, so the
        # very thing that makes the forgery work is what the door catches it on.
        #
        # This is the assertion this test has twice been caught weakening, so it is worth being
        # explicit that the criterion did not move: still ONE exception class, still ONE reason,
        # still no alternation. A different reason for a defined field is not a looser test than an
        # absent field's reason — `isinstance` here would make it green again, which is the check.
        with pytest.raises(ContractViolation, match="exactly int"):
            rows_of(_doc([{**_VALID_ROW, "cost": SneakyCost(9)}]))

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

    def test_C12s_STRUCTURED_FIELDS_SURVIVE_EVERY_RE_RAISE(self):
        """🔴 **I RECORDED THIS UNREPRODUCED AND MY PROBE WAS THE DEFECT.** I *deleted* the
        re-raise wrapper, which preserves the exception class and reads green; a verifier
        *downgraded* it and lost `.field_path` at `rows_of`, `validate_document` and
        `build(previous=)` **simultaneously**, suite green. Even deletion degrades the path from
        `declarations[0].kind` to `kind`, which is the half C-12 exists for: *name the field path
        rejected*, not the field.

        A probe that disagrees with a verifier is a reason to re-measure, and re-measuring is what
        settled it: the hole was real and my instrument missed it."""
        bad = {"manifest_version": 1, "contract_version": "1.0.0",
               "declarations": [{**_VALID_ROW, "kind": "nonsense"}]}
        prev = build([admit(_tool("book_list"))], previous=None)
        broken_prev = {**prev, "declarations": [{**prev["declarations"][0], "kind": "nonsense"}]}

        doors = {
            "rows_of": lambda: rows_of(bad),
            "validate_document": lambda: validate_document(bad),
            "build(previous=)": lambda: build([admit(_tool("book_list"))], previous=broken_prev),
        }
        for name, call in doors.items():
            with pytest.raises(ContractViolation) as exc:
                call()
            # The PATH, not merely the field: a bare `kind` cannot tell a caller which row.
            assert "declarations[" in exc.value.field_path and "kind" in exc.value.field_path, (
                f"{name} lost C-12's field PATH: {exc.value.field_path!r}"
            )
            assert exc.value.accepted, f"{name} lost C-12's `accepted`"

    def test_A_TOOL_WITH_RESOLVING_MEMBERS_IS_STILL_A_TOOL_WITH_MEMBERS(self):
        """🔴 **The second one my probe missed, and it missed it by using the stock fixture.**
        `members: ['ghost']` trips **M5** (`UnresolvedReference`) before the kind clause is reached,
        so the refusal looked like the clause working. A member that **resolves** separates them:
        with the clause gone, a tool carrying a real declaration id is ACCEPTED at three doors.

        A fixture chosen for convenience answered a different question than the one being asked."""
        doc = {"manifest_version": 1, "contract_version": "1.0.0", "declarations": [
            {**_VALID_ROW, "id": "t0", "members": ["t1"]},
            {**_VALID_ROW, "id": "t1"},
        ]}
        for name, door in (("rows_of", rows_of), ("validate_document", validate_document),
                           ("declarations", lambda d: declarations(d))):
            with pytest.raises(ContractViolation, match="a tool has no members"):
                door(doc)

    def test_THE_ROW_COPY_IS_WHAT_LEAVES_THE_VALIDATOR(self):
        """The third. `dict(r)` is what stops the caller's own row object reaching a consumer after
        validation, and nothing asserted the copy itself."""
        # 🔴 **AND THE FIRST VERSION OF THIS TEST GUARDED THE SIBLING.** The finding named
        # `surface.py`'s `rows_of`; I wrote the test against `validate_document`, whose copy already
        # had a red-able test. Net new coverage: **zero** — the seventh time in this run a fix went
        # to the site a verifier pointed AT rather than the one it named. Both doors are asserted
        # now, and the `rows_of` half is the one the finding was about.
        good = build([admit(_tool("book_list"))], previous=None)

        rows = rows_of(good)
        assert rows[0] is not good["declarations"][0]
        rows[0]["id"] = "MUTATED"
        assert good["declarations"][0]["id"] == "book_list", (
            "`rows_of` handed the consumer the caller's own row object; every narrowing stage then "
            "writes through into the document the assembler was given"
        )

        out = validate_document(good)
        assert out["declarations"][0] is not good["declarations"][0]
        out["declarations"][0]["id"] = "MUTATED"
        assert good["declarations"][0]["id"] == "book_list", (
            "the validator returned the caller's own row object; mutating what it handed back "
            "changed what it had validated"
        )

    def test_THE_ROW_COPY_IS_NOT_SHALLOW__members_is_the_one_mutable_value_a_row_carries(self):
        """🔴 **FIVE ROUNDS, AND ITS OWN GUARD REQUIRED THE DEFECT TO STAY.** `dict(r)` was added at
        both doors to stop the caller's row object reaching a consumer — and `dict()` is shallow, so
        every row still handed back **the source document's own `members` list**. The test above
        asserts non-mutation of `id`, a `str`, which a shallow copy protects; it therefore passes in
        both states and could never have named this.

        `members` is a skill's foreign-key list. A consumer appending to it writes into the document
        the assembler was given, so the *next* read of that document resolves M5 against members
        nothing admitted.

        The vehicle is the assertion the sibling test could not make: **identity of the list**, and
        then a write through it.
        """
        good = build([admit(_skill("world_setup", members=("book_list",))),
                      admit(_tool("book_list"))], previous=None)
        src_row = next(r for r in good["declarations"] if r["id"] == "world_setup")

        for name, door in (("rows_of", rows_of),
                           ("validate_document",
                            lambda d: validate_document(d)["declarations"]),
                           ("declarations", lambda d: declarations(d))):
            out = door(good)
            row = next(r for r in out if r["id"] == "world_setup")
            assert row["members"] is not src_row["members"], (
                f"{name} handed back the source document's own `members` list; `dict(r)` is a "
                f"shallow copy and `members` is the only mutable value a row carries"
            )
            row["members"].append("TYPED BY HAND")
            assert src_row["members"] == ["book_list"], (
                f"{name}: appending to the row it returned changed the document it validated — M5 "
                f"resolved against members nothing admitted"
            )

    def test_AN_ID_IS_A_KEY_AND_A_KEY_IS_BOUNDED(self):
        """🔴 **SIX ROUNDS, VEHICLE = PLAIN JSON.** `^[a-z][a-z0-9_]*$` bounded the alphabet and not
        the length, and a 300-character id was measured travelling through `check_row`, `rows_of`
        and `validate_document` end to end. An id is the `AllowList`/`DenyList` membership key, the
        `OrderBy` tie-break, M5's foreign key, and text rendered into the prompt the model reads.

        Both `_ID` sites are driven, because the regex governs the id AND every member — the member
        half sits behind a second refusal, and fixing one spelling of a shared pattern is this run's
        most-repeated failure.
        """
        from app.agentruntime.contract import ID_MAX_LEN, check_row

        at_limit = "a" * ID_MAX_LEN
        over = "a" * (ID_MAX_LEN + 1)

        check_row({**_VALID_ROW, "id": at_limit}, "row")           # the bound is inclusive, stated

        with pytest.raises(ContractViolation, match="not a stable identifier"):
            check_row({**_VALID_ROW, "id": over}, "row")
        with pytest.raises(ContractViolation, match="not a declaration id"):
            check_row({**_VALID_ROW, "id": "s0", "kind": "skill", "members": [over]}, "row")

        for name, door in (("rows_of", rows_of), ("validate_document", validate_document),
                           ("declarations", lambda d: declarations(d))):
            doc = {"manifest_version": 1, "contract_version": "1.0.0",
                   "declarations": [{**_VALID_ROW, "id": over}]}
            with pytest.raises(ContractViolation, match="not a stable identifier"):
                door(doc)

    def test_THE_ALPHABET_ADMITS_EVERY_ID_THIS_REPOSITORY_ALREADY_DECLARES(self):
        """🔴 **SIX ROUNDS WENT INTO THE *LENGTH* HALF OF `_ID` WHILE THE *ALPHABET* HALF REFUSED
        9 OF 9 REAL WORKFLOW IDS.**

        `^[a-z][a-z0-9_]*$` was a builder choice — `ARCHITECTURE.md` C-0 says *"id"* and specifies no
        alphabet — and every workflow this repository declares is hyphenated. At CP-4 `check_contract`
        would have refused **100% of one declaration kind**, printing a message that leads with the
        length. **One command over the same corpus that justified `ID_MAX_LEN = 64` would have found
        it**, and the question asked was *"is the length bounded"* rather than *"what does this regex
        do to the real data"*.

        So the property is stated over the **real registries** rather than over a fixture: every id
        this repository already declares must be admissible. The next kind that arrives with a new
        spelling is then refused **here**, where the answer is a design decision, instead of at CP-4
        inside the admission of the first declaration — where the ids are already persisted and
        §6.4's re-admission queue, the mechanism that would migrate them, is not built.
        """
        from app.agentruntime.contract import ID_MAX_LEN, _ID
        from app.services.intent_workflows import _COMPILED
        from app.services.skill_registry import LOADABLE_SKILL_CODES

        corpus: dict[str, list[str]] = {
            "workflow": [w for w, _ in _COMPILED],
            "skill": list(LOADABLE_SKILL_CODES),
        }
        snapshot = _REPO / "services" / "chat-service" / "tests" / "fixtures" / \
            "tools-list.snapshot.json"
        if snapshot.exists():
            data = json.loads(snapshot.read_text("utf-8"))
            tools = data.get("tools", data) if isinstance(data, dict) else data
            corpus["tool"] = [t["name"] for t in tools if isinstance(t, dict) and "name" in t]

        assert sum(len(v) for v in corpus.values()) >= 15, (
            f"the corpus collapsed to {corpus}; a registry moved and this gate would pass over "
            f"nothing, which is the vacuity failure it exists to prevent"
        )
        refused = {kind: sorted(i for i in ids if not _ID.match(i))
                   for kind, ids in corpus.items()}
        refused = {k: v for k, v in refused.items() if v}
        assert not refused, (
            f"`_ID` refuses ids this repository already declares: {refused}. These are PERSISTED — "
            f"renaming them is a migration, and §6.4's re-admission queue is not built (§6.4.1). "
            f"Decide the alphabet here, at CP-1, not inside CP-4's first admission."
        )
        # ...and the length half, over the same corpus, so the number in the docstring is measured
        # rather than asserted. A verifier derived it first: 334 ids, max 38, 0 over 64.
        longest = max((len(i), i) for ids in corpus.values() for i in ids)
        assert longest[0] <= ID_MAX_LEN, (
            f"{longest[1]!r} is {longest[0]} characters and ID_MAX_LEN is {ID_MAX_LEN}"
        )

    def test_ID_MAX_LEN_IS_THE_NUMBER_THE_DOCSTRING_ARGUES_FOR(self):
        """🔴 **THE BOUND WAS GUARDED ONLY FROM BELOW.** A verifier swept the constant against the
        whole suite: 9 → 9 failed, 12 → 1 failed, and **32, 64, 300, 10 000 and 1 000 000 all
        GREEN**. The guard derives its vehicles (`at_limit`, `over`) from `ID_MAX_LEN` itself, so
        what it binds is *"a bound exists"*, never *"the bound is the one argued for"* — the
        self-derived-denominator failure applied to a constant, which is a failure this run has a
        standard about and had not thought to apply to a number.

        So the vehicles here are **literals**, and the constant is asserted against the measurement
        that justifies it rather than against itself.
        """
        from app.agentruntime.contract import ID_MAX_LEN, check_row

        assert ID_MAX_LEN == 64, (
            f"ID_MAX_LEN is {ID_MAX_LEN}. 64 is the stated number and it is defensible against a "
            f"measurement: 334 real declaration ids, longest 38, none over 64 — 1.68x the observed "
            f"maximum. Changing it is a decision that belongs in the comment beside it, with what "
            f"was measured."
        )
        check_row({**_VALID_ROW, "id": "a" * 64}, "row")            # literal, not derived
        for literal in (65, 300, 10_000):
            with pytest.raises(ContractViolation, match="not a stable identifier"):
                check_row({**_VALID_ROW, "id": "a" * literal}, "row")

    def test_A_KEY_IS_BOUNDED_ON_BOTH_SIDES_OF_THE_COMPARISON(self):
        """🔴 **SIX ROUNDS BOUNDED THE ROW SIDE AND ZERO OF SEVEN COMPARAND DOORS.** A verifier
        drove a 300-character key through every stage parameter that is compared against an id and
        found all of them accepting it. *"An id is a key"* is a claim about the KEY, and a key has
        two sides.

        The consequence is stated at its true size rather than inflated: an unmatchable `AllowList`
        name cannot match a bounded row, so it narrows to **zero** — an asymmetry, and a loud one,
        because the drop registers. Under `not_in` it inverts: an unmatchable operand removes
        **nothing** and registers nothing, which is the silent deny-list this package exists to make
        impossible, arriving through a typo instead of through a rule.

        Bounded here rather than at CP-2 because the parameter is in the tree today and the vehicle
        is a config read that returned the wrong string.

        **The field-name doors are deliberately NOT bounded** — `OrderBy`'s field and
        `TakeWhileBudget.cost_field` name a ROW FIELD, not an id, and bounding them to `ROW_FIELDS`
        is a different claim whose answer changes at CP-2 (which adds `relevance`). Stated so the
        omission is a decision rather than the next round's finding.
        """
        long = "a" * 300
        for kind, make in (
            ("AllowList", lambda v: AllowList("s", "r", names=(v,))),
            ("DenyList", lambda v: DenyList("s", "r", names=(v,))),
            ("Filter eq", lambda v: Filter("s", "r", field="id", op="eq", value=v)),
            ("Filter in", lambda v: Filter("s", "r", field="id", op="in", value=(v,))),
            ("Filter not_in", lambda v: Filter("s", "r", field="id", op="not_in", value=(v,))),
        ):
            for bad in (long, "Not An Id", "", "UPPER"):
                with pytest.raises(ValueError):
                    make(bad)
            make("book_list")           # ...and a real id still constructs, at every door
            make("kg-build")            # ...including the hyphenated spelling CP-4 will bring

        # A filter on a NON-id field is untouched: the bound is about ids, not about strings.
        Filter("s", "r", field="owning_service", op="eq", value=long)

    def test_CHECK_ROW_RAISES_EXACTLY_ONE_CLASS__so_a_second_handler_is_dead_code(self):
        """🔴 **TWO `except UntrustedRow` CLAUSES SAT IN THE ALLOWLIST AS "REFUSALS NOTHING
        CHECKS", AND THEY COULD NEVER FIRE.** A verifier proved it two ways — an AST call-closure
        over `contract.py`, and 25 executed malformed rows, 25 of 25 `ContractViolation`. Nothing
        checked them because nothing could reach them, which is a different category, and carrying
        them as allowlisted debt made the instrument's own count wrong by two.

        Both are deleted. This is what keeps that true: it asserts the **closure**, not the deletion,
        so widening `check_row` to raise a second class fails here — where the answer is *"then the
        handler comes back, deliberately"* — rather than silently restoring an unreachable branch.
        """
        import ast

        from app.agentruntime.contract import check_row

        pkg = Path(__file__).resolve().parents[1] / "app" / "agentruntime"
        tree = ast.parse((pkg / "contract.py").read_text("utf-8"))
        fns = {f.name: f for f in ast.walk(tree)
               if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}

        seen: set[str] = set()
        reached: set[str] = set()

        def walk(name):
            if name in seen or name not in fns:
                return
            seen.add(name)
            for n in ast.walk(fns[name]):
                if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call):
                    cls = getattr(n.exc.func, "id", getattr(n.exc.func, "attr", "?"))
                    reached.add(cls)
                elif isinstance(n, ast.Call):
                    callee = getattr(n.func, "id", None)
                    if callee in fns:
                        walk(callee)

        walk("check_row")
        assert reached == {"ContractViolation"}, (
            f"`check_row`'s transitive raise closure is {sorted(reached)}, not just "
            f"{{'ContractViolation'}}. `manifest.build` and `manifest.validate_document` each "
            f"dropped an `except UntrustedRow` on the strength of that closure; a second class "
            f"means those refusals now vanish silently."
        )
        # ...and driven, because an AST closure is an argument about code and this is a claim about
        # behaviour. Every malformed shape a row can take, through the one door.
        for bad in ({"id": ""}, {"id": "Not An Id"}, {"kind": "nope"}, {"lifecycle": "nope"},
                    {"members": "x"}, {"members": [""]}, {"members": [None]}, {"weight": 1},
                    {"contract_version": "x"}, {"admitted_against": 7}, {"id": "a" * 300},
                    {"kind": "skill"}):
            with pytest.raises(ContractViolation):
                check_row({**_VALID_ROW, **bad}, "row")
        # ...and the shapes that are not an OVERLAY of a valid row, which the loop above cannot
        # express: `{**_VALID_ROW, **{}}` is a valid row, and writing `{}` in that list was a
        # vehicle that asserted nothing.
        for whole in ({}, [], "row", None, 7, {"id": "t0"}):
            with pytest.raises(ContractViolation):
                check_row(whole, "row")

    def test_EVERY_DOOR_READS_THE_DOCUMENTS_OWN_STAMPS(self):
        """🔴 **24 OF 24 CELLS SERVED, AND I HAD MOVED THIS TO CP-2 ON A CRITERION THE BOARD NEVER
        STATED.** The ROW definition was consolidated across every door; the DOCUMENT definition was
        left in `validate_document` alone. So `rows_of`, `declarations`, `discover` and
        `SurfaceAssembler` handed rows to a consumer out of a manifest carrying `manifest_version:
        999`, `contract_version: "banana"`, either stamp missing, or an undefined top-level key —
        every one of which `load()` refuses. `contract_version` is §6.4's queue COMPARAND.

        The stated criterion for a transfer is *"no SUBJECT until a later checkpoint's code
        exists"*; the reason I recorded was *"production-reachable at CP-2"*. **Those are different
        predicates, and the nine items I kept were judged on the first.** A verifier moved it back
        in one command, so it is fixed here and the transfer block is corrected at the claim.

        This is the nine-classes finding one level up, and this is its enumeration: 6 document
        defects × 6 doors.
        """
        good = build([admit(_tool("book_list"))], previous=None)
        defects = {
            "manifest_version missing": {k: v for k, v in good.items() if k != "manifest_version"},
            "manifest_version 999": {**good, "manifest_version": 999},
            "contract_version missing": {k: v for k, v in good.items() if k != "contract_version"},
            "contract_version banana": {**good, "contract_version": "banana"},
            "an undefined top-level key": {**good, "lane": "read"},
            "the document is not a dict": [good],
        }
        doors = {
            "rows_of": rows_of,
            "declarations": lambda d: declarations(d),
            "discover": lambda d: discover(d),
            "SurfaceAssembler": lambda d: SurfaceAssembler(d),
            "validate_document": validate_document,
            "build(previous=)": lambda d: build([admit(_tool("book_get"))], previous=d),
        }
        served = []
        for label, doc in defects.items():
            for name, door in doors.items():
                try:
                    door(doc)
                    served.append(f"{name} SERVED {label}")
                except (UntrustedRow, TypeError, AttributeError):
                    pass
        assert not served, (
            f"{len(served)} of {len(defects) * len(doors)} cells serve rows from a document the "
            f"reader cannot make claims about: {served}"
        )

    def test_A_KEY_PAIR_THAT_IS_NOT_A_PAIR_IS_REFUSED__and_the_vehicle_is_a_LIST(self):
        """🔴 **FIVE ROUNDS SILENT, AND THE REASON IS WHY THE OTHER VEHICLES PROVE NOTHING.**
        `OrderBy` refuses a key that is not a 2-tuple, and the census records that refusal as one
        the suite does not notice being removed. Neuter it and try the obvious probes: a 3-tuple, a
        1-tuple and a 2-character `str` all still raise `ValueError` — from `field, direction =
        pair`, Python's own unpacking, which says nothing about this check.

        **A 2-element LIST is the one vehicle the unpacking does not mask**: it unpacks cleanly,
        both halves are plain `str`, the direction is legal, and the ranking that decides which
        declarations reach the model is then built from a container that decides its own iteration.
        """
        with pytest.raises(ValueError, match=r"is not a \(field, direction\) pair"):
            OrderBy(keys=(["id", "asc"],))
        # ...and the shape it exists to accept still constructs, so this is not a blanket refusal.
        assert OrderBy(keys=(("id", "asc"),)).effective_keys() == (("id", "asc"),)

    def test_A_STR_SUBCLASS_KEY_OR_MEMBER_IS_NOT_A_STR(self):
        """🔴 **B18-8 — SEVEN ROUNDS, AND `1 OF 3 PINS` HAD A TEST.** `check_row_shape` bounds three
        places a `str` can arrive: the row's KEYS, the `members` elements, and every VALUE via
        `ROW_FIELDS`. Only the value pin was guarded, so the census recorded the other two as
        refusals nothing checks.

        A `str` subclass is not a cosmetic distinction here. `in`, `[]` and `==` all dispatch to
        user code, so the object that answers `"id"` to the validator can answer something else to
        the consumer — the TOCTOU this package has already paid for five times, arriving through the
        one type nobody thought to bound because it *is* the bound.

        `isinstance` cannot express this and `type(x) is str` is the only comparison Python does not
        dispatch, which is why both pins spell it that way and why both need a test that reds when
        they stop.
        """
        from app.agentruntime.contract import check_row_shape

        class Forged(str):
            pass

        row = dict(_VALID_ROW)
        row[Forged("id")] = row.pop("id")
        with pytest.raises(ContractViolation, match="non-string key"):
            check_row_shape(row, "row")

        with pytest.raises(ContractViolation, match="members"):
            check_row_shape({**_VALID_ROW, "id": "s0", "kind": "skill",
                             "members": [Forged("book_list")]}, "row")

        # 🔴 **AND THE TWIN — `check_contract` STILL USED `isinstance`, TWO FUNCTIONS AWAY.** A
        # verifier executed it: `admit(Declaration(id=SubStr("book_list")))` **succeeded**, and so
        # did a subclass MEMBER. So the one door whose entire job is to be the boundary accepted the
        # exact forgery the row-shape pins had just been guarded against.
        #
        # **And my first repair of this shipped with no test at all** — my own reversion prover
        # caught it: switching both pins back to `isinstance` left the suite GREEN, because the
        # guard above is scoped to `check_row_shape`. A fix without a red-able test is not a closed
        # finding, which is a standing rule of this run, and this is the second time in two rounds it
        # was broken inside the repair for a twin.
        with pytest.raises(ContractViolation, match="not a stable identifier"):
            admit(Declaration(id=Forged("book_list"), kind="tool",
                              source_path="services/book-service/x.go"))
        with pytest.raises(ContractViolation, match="not a declaration id"):
            admit(Declaration(id="world_setup", kind="skill", members=(Forged("book_list"),),
                              source_path="services/chat-service/app/skills/world.py"))
        # ...and the real spellings still admit at that door, so this is not a blanket refusal.
        admit(_tool("book_list"))
        admit(_skill("world_setup", members=("book_list",)))

    def test_AN_IMPORT_IS_A_CLAIM_ABOUT_WHAT_A_MODULE_DEPENDS_ON(self):
        """🔴 **B18-11 — `canon` was imported by two modules and called by neither, seven rounds.**
        The one `canon.nfc(...)` call was removed when a verifier refuted the harm its comment
        described; the imports it existed for stayed, and `check_row`'s surviving comment mentions
        `canon.digest` four times — so every reader of this package saw a contract that consults the
        canonical serialisation, and grep confirmed it.

        Named as a property rather than as two deletions, because the deletions would go stale and
        the property will not: **a module may not import a name it does not use.**

        🔴 **AND THE FIRST VERSION OF THIS GATE WAS DEFEATED BY ONE WORD OF PROSE.** It counted a
        name appearing in **any whitespace-delimited token of any string literal** as a use, so a
        verifier restored the exact seven-round defect with the suite green: re-add
        `from . import canon`, change one docstring phrase so it contains the bare token `canon`,
        **1 passed**. Same for `import re`. Not adversarial prose — *ordinary* prose, in files whose
        docstrings are rewritten every round. **Fourth "a test satisfied by a comment" in this run,
        and this one was inside the repair for the finding it closes.**

        Enumerated by that verifier at **3 of 11** dead-import shapes caught, plus one
        false-positive class. The naive repair is also wrong and was executed: deleting the
        string-literal term reds **~30 re-exports in `__init__.py`**, which are "used" only through
        the `__all__` string list. So the term is load-bearing for exactly one construct, and the
        correct narrowing is to **that construct** — `__all__`'s elements — rather than to every
        token of every string.

        Six shapes are closed here, each named where it is closed. What remains open is stated in
        the assertion rather than left for the next round to find.
        """
        pkg = Path(__file__).resolve().parents[1] / "app" / "agentruntime"
        dead = []
        # `rglob`, not `glob`: a dead import in a sub-package was invisible. The package is flat
        # today, which is exactly why the non-recursive form looked correct.
        for path in sorted(pkg.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            dead += _dead_imports(path.read_text("utf-8"), path.name)
        assert not dead, (
            f"{dead} — an import is a claim about what a module depends on, and a reader (or a "
            f"grep) takes it at face value. `canon` was imported by two modules with zero call "
            f"sites in either for seven consecutive rounds; this gate's first run found a THIRD "
            f"(`manifest.import re`) that eight rounds of review had not named; and its FIRST "
            f"version was then defeated by putting the word `canon` in a docstring."
        )

        # 🔴 **THE CONTROL, AND WITHOUT IT THE NARROWING WAS ITSELF UNGUARDED.** My own reversion
        # prover caught that: re-widening the string term left the suite GREEN, because a looser
        # gate simply finds nothing. The property here is not *"no dead import exists"* — it is
        # **"a dead import cannot be hidden"**, and only an injection can say that.
        #
        # Shapes 1-2 are the exact defeat a verifier executed: re-add the import AND put the bare
        # token in prose. Shapes 3-6 are the other misses it enumerated. Shape 7 is the one
        # construct the blanket term was actually buying, and it must stay GREEN.
        MUST_CATCH = {
            "a bare dead import": 'import re\n',
            "the name as a bare word in the DOCSTRING": '"""we do not parse with re here."""\nimport re\n',
            "the name in an unrelated message string": 'import re\nX = "re is not used"\n',
            "the name shadowed by an unrelated attribute": 'import re\nX = c.re\n',
            "the name reused as a local": 'import re\ndef f():\n    re = 1\n    return re\n',
            "a dead `__`-prefixed alias": 'import re as __re\n',
            "the SECOND dead import of a doubly-imported name": 'import re\nimport re\nY = re\n',
        }
        MUST_NOT_CATCH = {
            "a re-export through `__all__`": 'from x import Admitted\n__all__ = ["Admitted"]\n',
            "a genuinely used import": 'import re\nY = re.compile("x")\n',
            "a side-effect-only dotted import": 'import app.agentruntime.canon\n',
        }
        missed = [k for k, src in MUST_CATCH.items() if not _dead_imports(src)]
        assert not missed, (
            f"{missed} hide a dead import from this gate. The first version was defeated by ONE "
            f"WORD OF PROSE — a verifier restored the seven-round B18-11 defect with the suite "
            f"green — which is the fourth 'a test satisfied by a comment' in this run and the "
            f"second inside a repair for another."
        )
        wrong = [k for k, src in MUST_NOT_CATCH.items() if _dead_imports(src)]
        assert not wrong, (
            f"{wrong} are CORRECT code and this gate reds on them. The naive repair — deleting the "
            f"string term outright — reds ~30 `__init__.py` re-exports, which is why the narrowing "
            f"is to `__all__`'s elements and not to nothing."
        )

    def test_A_STAGE_MUST_NAME_THE_FIELD_IT_READS__and_the_order_it_ranks_by(self):
        """🔴 **The fifth unguarded load-bearing check, found by a verifier enumerating raise
        sites rather than reading the diff.** `Filter(field="")` narrows the surface to **zero**
        under `eq` and to **nothing** under `not_in` — `withheld=0`, so the record cannot even say
        what happened — and the check that refuses it had no test. `OrderBy(keys=())` silently falls
        back to id-order, which its own docstring forbids by name."""
        with pytest.raises(ValueError, match="must name the field it reads"):
            Filter("s", "r", field="", op="eq", value="t0")
        with pytest.raises(ValueError, match="must name at least one field"):
            OrderBy(keys=())
        with pytest.raises(ValueError, match="must name the field it accumulates"):
            TakeWhileBudget("s", "r", budget=1, cost_field="")

    def test_A_GENERATOR_PIPELINE_IS_NOT_A_SILENT_NO_OP(self):
        """`pipeline = list(pipeline)` in `assemble` — without it a bare generator is validated once
        and then iterated empty, so a `Filter` keeping one declaration returns all four and the
        conservation law balances. The comment above it records the defect; nothing tested it."""
        doc = {"manifest_version": 1, "contract_version": "1.0.0", "declarations": _rows(4)}
        stages = (s for s in [Filter("intent_gate", "off", field="id", op="eq", value="t0")])
        s = SurfaceAssembler(doc).assemble(pass_number=1, pipeline=stages)
        assert s.names == ("t0",), (
            f"a generator pipeline was a silent no-op: {s.names}. Validated once, iterated empty."
        )

    def test_THE_CENSUS_DOES_NOT_WRITE_INTO_THE_LIVE_TREE(self, tmp_path):
        """🔴 **THE PREVIOUS VERSION OF THIS TEST WAS GREEN OVER THE CENSUS'S OWN REMOVAL.**

        Two verifiers enumerated it independently: **8 of 8 bypasses green** — `if: false`,
        `--selftest`, `continue-on-error`, a job-level `if`, a YAML **comment**, `::deadbeef`×13,
        `getattr(atexit, 'register')`, and a re-spelled live-tree write. One control failed to red at
        all: renaming `_mirror` → `_mirrorX`, over a census that then dies with `NameError`.

        Every one of those assertions was a **substring over source text**. The delta's headline
        property — *the instrument does not write into its subject* — was guarded by the spelling
        `PKG.glob`, so `(ROOT / _PKG_REL).glob` restored live-tree neutering with the gate green. That
        is **GATE HÌNH DẠNG, KHÔNG GATE HÀNH VI**, and it is the rule this run states in capitals.

        Worse, the assertion written to *replace* the one a comment defeated was **also defeated by a
        comment** — third instance. A test that reads source text is testing that someone typed a
        word.

        So this **runs the thing**: it drives `census()` over a two-site fixture package with a real
        neutering loop, and asserts the live tree is byte-identical afterwards. It reds when the
        mirror is removed, when it is bypassed, and when it is renamed — because none of those
        survive execution.
        """
        import hashlib
        import importlib.util
        import pathlib

        spec = importlib.util.spec_from_file_location(
            "_census_probe", _REPO / "scripts" / "agentruntime-census.py")
        census_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(census_mod)

        # 🔴 **AND THIS GUARD BROKE THE THING IT GUARDS.** `census()` runs the membrane suite
        # inside its mirror 68 times — and this file is in that suite, so the guard re-entered
        # `census()`, whose `_mirror()` ran `git ls-files` in a directory with no `.git`. The
        # subprocess died, `_suite_is_green` read every non-zero exit as "the suite noticed", and
        # the census reported **68 red, 0 silent** with thirteen `NOW GUARDED ... good news` lines.
        # The selftest passed throughout, because its positive control runs in the mirror too.
        #
        # A guard that executes the instrument must not execute inside it. The mirror has no `.git`;
        # that is the signal, and skipping is honest here because the outer run is the one measuring.
        # \U0001F534 **AND THE DOCSTRING ABOVE DESCRIBED A CAPABILITY I HAD NOT WRITTEN.** It says this
        # drives `census()` over a two-site FIXTURE package; it called the real one. Running the
        # instrument over the real package from inside the suite the instrument runs is what caused
        # the recursion in the first place, and a skip only papered over it: in the live tree the
        # guard still launched a full ten-minute census inside another suite run.
        #
        # It now does what the docstring said. A two-site fixture makes the run seconds instead of
        # minutes, removes the re-entrancy entirely, and — the part that matters — lets the
        # assertion below be about **the real package's bytes**, which a fixture run must never
        # touch.
        import tempfile

        # 🔴 **AND THIS LINE LEAKED 455 DIRECTORIES.** It was `mkdtemp(prefix="lw-census-fixture-")`
        # with no cleanup — in the guard written to police an instrument whose own recorded finding
        # is *"mirrors never removed, 6.71 GB measured"*. Measured on one machine: **455 fixture
        # directories and 12 mirrors, 2.4 GB**, and it was found by listing `%TEMP%` rather than by
        # any gate. `tmp_path` is removed by pytest, so the leak cannot come back by omission.
        fixture = tmp_path / "lw-census-fixture"
        fixture.mkdir()
        (fixture / "probe.py").write_text(
            "def a(x):\n"
            "    if not x:\n"
            '        raise ValueError("a")\n'
            "def b(x):\n"
            "    if x:\n"
            '        raise TypeError("b")\n', encoding="utf-8")
        pkg = _REPO / "services" / "chat-service" / "app" / "agentruntime"
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(pkg.glob("*.py"))}
        assert len(before) >= 6, "the package moved; this probe would assert nothing"

        # A suite runner that is instant and always green, so `census()` does its neutering, its
        # restores and its file writes at full speed while asserting nothing about pytest.
        # 🔴 **AND MY FIRST VERSION OF THIS TEST COMPARED THE TREE BEFORE AND AFTER, WHICH
        # THE CENSUS'S OWN RESTORE SATISFIES.** Re-spelling the mirror binding to `pkg, cs = PKG, CS`
        # writes production source into the live tree, runs against it, and puts it back - so the
        # hashes match and the test passed. Measured. The property is not "the tree ends unchanged",
        # it is **"the tree is never written"**, and only an observation DURING the run can tell
        # those apart. A restore is exactly what fails when the process dies.
        seen, writes = [], []
        _real_write = pathlib.Path.write_bytes

        def _watch(self, data):
            writes.append(pathlib.Path(self))
            return _real_write(self, data)

        def _instant_green(cwd=None):
            seen.append(pathlib.Path(cwd) if cwd else None)
            return True

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(census_mod, "_suite_is_green", _instant_green)
            mp.setattr(census_mod, "PKG", fixture)
            mp.setattr(census_mod, "_mirror", lambda: fixture.parent)
            mp.setattr(census_mod, "_PKG_REL", pathlib.Path(fixture.name))
            mp.setattr(census_mod, "_CS_REL", pathlib.Path(fixture.name))
            mp.setattr(pathlib.Path, "write_bytes", _watch)
            results = census_mod.census()

        _live = [w for w in writes if _REPO in w.parents]
        assert not _live, (
            f"the census wrote {len(_live)} time(s) into the live tree, first {_live[0]}. It "
            f"restores afterwards, which is why a before/after comparison cannot see this - and a "
            f"restore is precisely what does not run when the process is killed."
        )

        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(pkg.glob("*.py"))}
        assert after == before, (
            "the census wrote into the LIVE package. It neuters production source, so a run that "
            "touches the real tree leaves a `raise -> pass` behind on any interruption, and it "
            "corrupts every concurrent suite run - both measured, and both are why it must work in "
            "a mirror."
        )
        assert len(results) == 2, (
            f"the fixture has two refusals and the census found {len(results)}; the probe is not "
            f"exercising the enumeration it claims to"
        )
        # Outside the repo entirely - `pkg not in s.parents` was backwards, since the suite's cwd is
        # an ANCESTOR of the package, so it passed for the live tree too.
        assert seen and all(s is not None and _REPO not in s.parents and s != _REPO for s in seen), (
            f"the census ran the suite against the LIVE tree at {seen[:2]}; the mirror exists but "
            f"is not what was measured, which is a fix landing beside its subject"
        )

    def test_NO_LIVE_TREE_PATH_REACHES_A_MUTATING_CALL__the_property_not_the_API_LIST(self):
        """🔴 **THE CELL LIST WAS THE WRONG AXIS, AND A VERIFIER PREDICTED THE NEXT ROUND'S FAILURE
        BEFORE I COULD COMMIT IT.**

        The previous guard enumerated `{2 writers} × {4 write APIs}` and called it complete. It was
        **the space a previous verdict happened to name**, adopted as though it were the space: A
        derived **19** write APIs and measured **5 caught**. Blind to `io.open`, `os.open`+`os.write`,
        `Path.touch`, `Path.mkdir`, `shutil.copytree`, `os.replace`, `os.rename`,
        `NamedTemporaryFile`, `subprocess`, `os.link`, `mmap` — and **to every deletion API,
        including `shutil.rmtree`, which this census calls at three live sites on a path returned by
        a monkeypatchable `_mirror()`, and which is the exact API of the `%TEMP%`-deletion incident
        the fix two commits earlier was written for.** The guard built after that incident could not
        observe the call that caused it.

        And the prediction: *"if C1 is repaired by adding the fourteen APIs I named as fourteen more
        cells, the fifteenth will be found next round."* That is correct, and it is why this is not
        that repair.

        **The property is not about the API. It is about the PATH.** Python's filesystem surface is
        open-ended; the set of expressions that can name the live tree is small and closed —
        `ROOT`, `PKG`, `CS`, and whatever is derived from them. So this taints those three names,
        propagates the taint through assignment to a fixed point, and refuses any tainted value
        reaching **any call at all** except a read. One clause covers all nineteen of A's vehicles
        and the twentieth nobody has written, because a write it cannot see is still a write whose
        path came from here.

        The behavioural drive stays below it: an AST rule is an argument about code, and the census
        has already shipped two of those that were green over the thing they described.
        """
        import ast

        script = _REPO / "scripts" / "agentruntime-census.py"
        tree = ast.parse(script.read_text("utf-8"))

        #: The names that denote the LIVE tree. Everything else in the module is a mirror path.
        LIVE = {"ROOT", "PKG", "CS", "ALLOWLIST"}
        #: Attributes that only READ. Anything not here is treated as a mutation, which is the safe
        #: direction: a new read is a one-line addition to this set, made deliberately; a new write
        #: is refused by default. `glob`/`rglob`/`read_bytes` are how the census enumerates sites,
        #: and `relative_to`/`parents`/`name`/`parent` are path arithmetic.
        READS = {"glob", "rglob", "read_bytes", "read_text", "exists", "is_file", "is_dir",
                 "relative_to", "parents", "parent", "name", "resolve", "as_posix", "stat",
                 "joinpath", "with_suffix", "splitlines", "decode", "encode", "startswith"}
        #: The subset of `READS` that turns a PATH into CONTENT. Everything else in `READS` is a
        #: transform that carries the path onward — a distinction the vehicle table forced.
        CONSUMES = {"read_bytes", "read_text", "glob", "rglob", "stat", "exists", "is_file",
                    "is_dir"}
        #: Callables that cannot touch a filesystem no matter what they are handed. A live path
        #: flowing into one of these is arithmetic or a message, not an operation on the tree.
        #: Kept deliberately small: `subprocess.run` is NOT here, which is how the `cwd=CS` default
        #: that ran pytest in the live tree was found — by this gate, on its first run.
        PURE = {"sorted", "list", "set", "tuple", "len", "str", "repr", "print", "any", "all",
                "enumerate", "zip", "max", "min", "next", "iter", "sum", "SystemExit", "Path",
                "_sites", "_neutered", "_shape_digest", "_own_mirror", "_discard"}
        #: The two functions allowed to hold a live path, each for a stated reason.
        EXEMPT = {
            # It READS the live tree to build the mirror — that is its entire job — and its only
            # live-path calls are `git ls-files` (cwd=ROOT) and `shutil.copyfile(src, dst)`.
            "_mirror",
            # `--write` regenerates the allowlist, which IS a live file and is meant to be. The one
            # deliberate live write in this module, and it is not a source file.
            "main",
        }

        tainted_fns: dict[str, set[str]] = {}

        def _carries_live(node, tainted) -> bool:
            """Does this expression still carry a live-tree PATH, rather than data read from one?

            Walks the expression but refuses to descend through a READ: `p.read_bytes()` yields
            bytes, `p.glob()` yields paths that are separately tainted by their own binding, and
            neither hands `p` onward. Without this, every read-and-transform chain in the module
            reads as "a live path reached a call".
            """
            if isinstance(node, ast.Name):
                return node.id in tainted
            # 🔴 **`READS` IS THE WRONG SET TO STOP AT, AND THE VEHICLE TABLE SAID SO IMMEDIATELY.**
            # It holds two different kinds of call: ones that turn a path into CONTENT
            # (`read_bytes`, `glob`, `stat`) and ones that merely transform it (`decode`, `encode`,
            # `resolve`, `joinpath`). Stopping at both made `str(ROOT / 'x').encode()` — the `ctypes`
            # vehicle — read as data, because `.encode()` was in the set. Only a CONSUMER breaks the
            # chain; a transform carries the path onward, which is exactly what the vehicle does.
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) in CONSUMES:
                return False
            return any(_carries_live(c, tainted) for c in ast.iter_child_nodes(node))

        def _offenders(tree) -> list[str]:
            found: list[str] = []
            _scan(tree, found)
            return found

        def _scan(tree, offenders):
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if fn.name in EXEMPT:
                    continue
                _scan_fn(fn, offenders)

        def _scan_fn(fn, offenders):
            # Taint to a fixed point: a name assigned from anything carrying a live root is live.
            tainted = set(LIVE)
            for _ in range(12):
                grew = False
                for n in ast.walk(fn):
                    # 🔴 **`for` AND COMPREHENSION TARGETS WERE NOT BINDERS, AND THAT IS THE
                    # CENSUS'S OWN INNER-LOOP SHAPE.** A verifier measured the cost: 20 of 24 axis
                    # vehicles blind, and then drove it to the end — `for p in sorted(PKG.glob(...))`
                    # followed by a write through `p` put **8 directories inside the live
                    # `app/agentruntime/` package while this suite reported `152 passed`.**
                    #
                    # The axis was right and the walk was incomplete: a binding is a binding however
                    # Python spells it, and I had enumerated three spellings out of five.
                    if isinstance(n, (ast.For, ast.AsyncFor)):
                        value, targets = n.iter, [n.target]
                    elif isinstance(n, ast.comprehension):
                        value, targets = n.iter, [n.target]
                    elif isinstance(n, ast.withitem):
                        value, targets = n.context_expr, ([n.optional_vars]
                                                          if n.optional_vars else [])
                    elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                        value = n.value
                        targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                    else:
                        continue
                    if value is None:
                        continue
                    if not any(isinstance(x, ast.Name) and x.id in tainted
                               for x in ast.walk(value)):
                        continue
                    for t in targets:
                        for el in ([t] if isinstance(t, ast.Name)
                                   else getattr(t, "elts", [])):
                            if isinstance(el, ast.Name) and el.id not in tainted:
                                tainted.add(el.id)
                                grew = True
                if not grew:
                    break
            tainted_fns[fn.name] = tainted

            for call in ast.walk(fn):
                if not isinstance(call, ast.Call):
                    continue
                attr = getattr(call.func, "attr", None)
                receiver_live = isinstance(call.func, ast.Attribute) and any(
                    isinstance(x, ast.Name) and x.id in tainted
                    for x in ast.walk(call.func.value))
                arg_live = any(
                    isinstance(x, ast.Name) and x.id in tainted
                    for a in list(call.args) + [k.value for k in call.keywords]
                    for x in ast.walk(a))
                callee = attr or getattr(call.func, "id", "?")
                # 🔴 **A READ TURNS A PATH INTO DATA, AND THE FIRST VERSION COULD NOT TELL.**
                # `ast.parse(path.read_bytes().decode("utf-8"))` carries a tainted NAME in its
                # argument while the value that arrives is a `str`. Widening `PURE` with `parse`
                # would have worked and would have been the wrong move — a verifier warned in the
                # same round that `READS`/`PURE` are allow-lists a new entry widens silently, and
                # `PURE` is the one that grants passage. So the rule is about the EXPRESSION: a
                # tainted name consumed by a read does not propagate past it.
                if arg_live and not any(
                        _carries_live(a, tainted)
                        for a in list(call.args) + [k.value for k in call.keywords]):
                    arg_live = False
                if receiver_live and callee not in READS:
                    offenders.append(
                        f"{fn.name}:{call.lineno} calls `{callee}` ON a live-tree path")
                elif arg_live and callee not in READS | PURE:
                    offenders.append(
                        f"{fn.name}:{call.lineno} passes a live-tree path INTO `{callee}`")

        offenders = _offenders(tree)
        assert not offenders, (
            f"{offenders} — a value derived from {sorted(LIVE)} reaches a call that is not a read. "
            f"The census neuters production source; anything it does to the live tree is a "
            f"`raise -> pass` left in a tracked module on the next interruption, and every "
            f"concurrent suite run reddening blaming a test. Both measured. If the call really is "
            f"read-only, add it to READS in the same change and say why."
        )
        # 🔴 **A NO-VACUITY ASSERTION STOOD HERE AND IT WAS A TAUTOLOGY.** It read
        # `assert LIVE <= set(tainted_fns["census"])` — and `tainted` is initialised
        # `= set(LIVE)` unconditionally, so it could not fail. A verifier proved it by renaming every
        # live root out of the module and watching it stay True. **Third control-agreeing-with-its-
        # seed in this run, and I shipped it inside the fix for an axis I was changing because the
        # previous enumeration had been too small.**
        #
        # It is DELETED rather than replaced. The vehicle table below is the real anti-vacuity
        # check: it requires an offender for every one of 23 shapes, three of which reach the tree
        # only through a tainted LOCAL, so the fixed point cannot be dead and the roots cannot be
        # missing. A second control that restates the first is what produced the tautology.

        # 🔴 **THE CONTROL — all nineteen APIs a verifier enumerated, plus the two shapes it
        # predicted would be found NEXT round.** Every one of them is caught by ONE clause, because
        # each names the live tree and none of them can avoid doing so. That is the whole argument
        # for binding the path instead of the API: the API list is open, and this one is not.
        VEHICLES = {
            "Path.write_bytes": "(ROOT / 'x').write_bytes(b'x')",
            "Path.write_text": "(ROOT / 'x').write_text('x')",
            "Path.open('wb')": "(ROOT / 'x').open('wb').write(b'x')",
            "builtins.open('w')": "open(str(ROOT / 'x'), 'w').write('x')",
            "shutil.copyfile": "__import__('shutil').copyfile('a', ROOT / 'x')",
            "io.open": "__import__('io').open(str(ROOT / 'x'), 'w')",
            "os.open+os.write": "__import__('os').write(__import__('os').open(str(ROOT / 'x'), 1), b'x')",
            "Path.touch": "(ROOT / 'x').touch()",
            "Path.mkdir": "(ROOT / 'x').mkdir()",
            "shutil.copytree": "__import__('shutil').copytree('a', ROOT / 'x')",
            "os.replace": "__import__('os').replace('a', ROOT / 'x')",
            "os.rename": "__import__('os').rename('a', ROOT / 'x')",
            "NamedTemporaryFile": "__import__('tempfile').NamedTemporaryFile(dir=ROOT, delete=False)",
            "subprocess": "subprocess.run(['sh', '-c', 'x'], cwd=ROOT)",
            "os.link": "__import__('os').link('a', ROOT / 'x')",
            "mmap": "__import__('mmap').mmap(__import__('os').open(str(ROOT / 'x'), 2), 0)",
            "os.remove": "__import__('os').remove(ROOT / 'x')",
            "Path.unlink": "(ROOT / 'x').unlink()",
            "shutil.rmtree": "__import__('shutil').rmtree(ROOT)",
            # ...and the two the verifier said a cell-list repair would miss next round.
            "ctypes": "__import__('ctypes').CDLL(None).unlink(str(ROOT / 'x').encode())",
            "a re-exported pathlib": "__import__('pathlib').Path(ROOT / 'x').write_bytes(b'x')",
            # ...and one through an intermediate local, which is what the fixed point is for.
            "an aliased local": "_p = ROOT / 'x'\n_p.write_bytes(b'x')",
            # 🔴 **THE CENSUS'S OWN INNER-LOOP SHAPE**, which the first version of this gate was
            # blind to because a `for` target was not treated as a binder. A verifier drove it to 8
            # directories inside the live package with this suite reporting `152 passed`.
            "a `for` target": "for _q in sorted(PKG.glob('*.py')):\n    _q.write_bytes(b'x')",
            "a comprehension target": "[_r.write_bytes(b'x') for _r in PKG.glob('*.py')]",
            "a `with ... as` target": "import contextlib\n"
                                      "with contextlib.nullcontext(ROOT / 'x') as _s:\n"
                                      "    _s.write_bytes(b'x')",
        }
        blind = []
        for label, stmt in VEHICLES.items():
            mutated = ast.parse(script.read_text("utf-8"))
            fn = next(n for n in mutated.body
                      if isinstance(n, ast.FunctionDef) and n.name == "census")
            fn.body[1:1] = ast.parse(stmt).body
            ast.fix_missing_locations(mutated)
            if not _offenders(mutated):
                blind.append(label)
        assert not blind, (
            f"{len(blind)} of {len(VEHICLES)} live-tree write vehicles are invisible: {blind}. "
            f"The previous guard patched four Python-level entry points and a verifier found "
            f"fourteen more; the answer is not fifteen more cells, it is that a write this gate "
            f"cannot name is still a write whose PATH came from here."
        )

    def test_NEITHER_CENSUS_WRITER_CAN_REACH_THE_LIVE_TREE__all_8_cells(self):
        """🔴 **THE GUARD ABOVE WATCHES ONE WRITER THROUGH ONE API: 1 OF 8 CELLS.**

        The census has **two** functions that write source files — `census()` and `_selftest()` —
        and a verifier enumerated the space as {2 writers} × {4 write APIs}. The existing guard
        drives `census()` and patches `pathlib.Path.write_bytes`, so seven of the eight ways to put
        a `raise -> pass` into a tracked module go unobserved. That is not hypothetical arithmetic:
        **the fix that moved the neutering into a mirror moved `census()`'s writer and left
        `_selftest`'s behind**, twenty lines away, and the guard stayed green through it — the tenth
        pair in this run repaired at one end.

        So this drives BOTH writers with every write API wrapped, and then **enumerates all eight
        cells as controls**: for each (writer, API) it injects a live-tree write into that writer,
        by AST, and requires the watcher to catch it. A guard whose failure mode is unmeasured is
        the thing the census exists to replace.

        The interception never lets a live-tree write reach the disk, so the controls cannot leave
        debris — an instrument that manufactures findings is the defect one level up.
        """
        import ast as _ast
        import io
        import pathlib
        import shutil as _shutil
        import tempfile
        import types

        script = _REPO / "scripts" / "agentruntime-census.py"
        source = script.read_text("utf-8")
        real_pkg = _REPO / "services" / "chat-service" / "app" / "agentruntime"

        def _load(inject_into=None, statement=None):
            """The census module, optionally with `statement` spliced into `inject_into`'s body."""
            tree = _ast.parse(source)
            if inject_into is not None:
                fn = next(n for n in tree.body
                          if isinstance(n, _ast.FunctionDef) and n.name == inject_into)
                fn.body.insert(1, _ast.parse(statement).body[0])
                _ast.fix_missing_locations(tree)
            mod = types.ModuleType("_census_cell_probe")
            mod.__file__ = str(script)
            exec(compile(tree, str(script), "exec"), mod.__dict__)   # noqa: S102 - the subject
            return mod

        def _run(mod):
            """Drive both writers with every write API watched. Returns the live-tree writes seen."""
            # One mirror PER `_mirror()` call, named exactly as the real one is, so the leak check
            # below is about what each writer does with the directory it was given.
            made: list[pathlib.Path] = []

            def _fake_mirror():
                d = pathlib.Path(tempfile.mkdtemp(prefix="lw-census-"))
                _shutil.copytree(real_pkg, d / mod._PKG_REL)
                made.append(d)
                return d

            writes: list[pathlib.Path] = []

            def _is_live(p) -> bool:
                p = pathlib.Path(p)
                return p == _REPO or _REPO in p.parents

            _rb, _rt = pathlib.Path.write_bytes, pathlib.Path.write_text
            _ro, _rbo = pathlib.Path.open, __builtins__["open"] if isinstance(
                __builtins__, dict) else __builtins__.open

            def _w_bytes(self, data, *a, **kw):
                if _is_live(self):
                    writes.append(pathlib.Path(self))
                    return len(data)
                return _rb(self, data, *a, **kw)

            def _w_text(self, data, *a, **kw):
                if _is_live(self):
                    writes.append(pathlib.Path(self))
                    return len(data)
                return _rt(self, data, *a, **kw)

            def _p_open(self, mode="r", *a, **kw):
                if set(mode) & set("wax+") and _is_live(self):
                    writes.append(pathlib.Path(self))
                    return io.BytesIO() if "b" in mode else io.StringIO()
                return _ro(self, mode, *a, **kw)

            def _b_open(file, mode="r", *a, **kw):
                if set(str(mode)) & set("wax+") and _is_live(file):
                    writes.append(pathlib.Path(file))
                    return io.BytesIO() if "b" in str(mode) else io.StringIO()
                return _rbo(file, mode, *a, **kw)

            def _fake_green(cwd):
                # 🔴 This used to answer on `cwd is None`, which stopped working the moment
                # `_suite_is_green`'s live-tree `cwd` DEFAULT was removed — the baseline and the
                # probe run now pass the same argument, as they should. A counter would have worked
                # and would have been a fake that agrees with the drive by construction.
                #
                # So it answers the question the real suite answers: **is the package under `cwd`
                # still the package on disk?** Green until something is neutered, red the moment
                # anything is — which is what makes `census()`'s 68 iterations and `_selftest`'s
                # two-direction check both behave like the real thing without pytest.
                pkg = pathlib.Path(cwd) / "app" / "agentruntime"
                return all(p.read_bytes() == (real_pkg / p.name).read_bytes()
                           for p in sorted(pkg.glob("*.py")))

            try:
                with pytest.MonkeyPatch.context() as mp:
                    mp.setattr(mod, "_suite_is_green", _fake_green)
                    mp.setattr(mod, "_mirror", _fake_mirror)
                    mp.setattr(pathlib.Path, "write_bytes", _w_bytes)
                    mp.setattr(pathlib.Path, "write_text", _w_text)
                    mp.setattr(pathlib.Path, "open", _p_open)
                    mp.setattr("builtins.open", _b_open)
                    results = mod.census()
                    rc = mod._selftest()
                return writes, results, rc, [d for d in made if d.exists()]
            finally:
                for d in made:
                    _shutil.rmtree(d, ignore_errors=True)

        # The pristine instrument, both writers, every API watched.
        live, results, rc, leaked = _run(_load())
        assert not live, (
            f"the census wrote into the live tree, first {live[0]}. It neuters production source, "
            f"so any interruption leaves a `raise -> pass` behind in a tracked module and every "
            f"concurrent suite run reddens blaming a test — both measured."
        )
        # 🔴 Without these two, the cells below would prove only that the WATCHER sees four APIs:
        # the injected statement is the writer's first line, so it fires even from a function that
        # bails immediately afterwards. These are what make the drive a drive.
        assert len(results) >= 50, (
            f"the census enumerated {len(results)} sites over the real package; the drive is not "
            f"exercising the loop it claims to and the cells below would be measuring the patches"
        )
        assert rc == 0, (
            "`_selftest()` did not complete under the drive, so its four cells below fire from a "
            "function that never reaches its own writer"
        )
        # 🔴 **THE LEAK, AND IT WAS FOUND BY LISTING `%TEMP%` RATHER THAN BY ANY GATE.** Measured on
        # one machine: **12 mirrors and 455 fixture directories, 2.4 GB** — a previous round had
        # already recorded 6.71 GB of exactly this, and the fix landed on `census()` alone while
        # `_selftest()` twenty lines below had **no cleanup at all**. The tenth pair in this run
        # repaired at one end, in the file whose docstring says an instrument that leaves debris is
        # an instrument that manufactures findings.
        #
        # The property is per-writer and deterministic: **each returns having removed the directory
        # it was given.** `atexit` is the kill path and cannot be asserted from inside the process
        # that would have to exit for it to run.
        assert not leaked, (
            f"{len(leaked)} mirror(s) survived the writers that created them: {leaked}. Each is a "
            f"239 MB copy of the repository held for the length of a CI run and left behind after "
            f"it — the finding this instrument has recorded twice about itself."
        )

        # ...and the eight cells, so "the watcher would notice" is a measurement.
        _APIS = {
            "Path.write_bytes": "(ROOT / '_lwcensus_live_probe.tmp').write_bytes(b'x')",
            "Path.write_text": "(ROOT / '_lwcensus_live_probe.tmp').write_text('x')",
            "Path.open(w)": "(ROOT / '_lwcensus_live_probe.tmp').open('wb').write(b'x')",
            "builtins.open(w)": "open(str(ROOT / '_lwcensus_live_probe.tmp'), 'w').write('x')",
        }
        blind = []
        for writer in ("census", "_selftest"):
            for api, statement in _APIS.items():
                if not _run(_load(writer, statement))[0]:
                    blind.append(f"{writer}() via {api}")
        assert not blind, (
            f"{len(blind)} of {2 * len(_APIS)} cells are invisible to this guard: {blind}. Each is "
            f"a way the instrument can write into its own subject with the gate green — which is "
            f"exactly how `_selftest`'s writer stayed in the live tree for a full round after "
            f"`census`'s was moved out."
        )
        assert not (_REPO / "_lwcensus_live_probe.tmp").exists(), (
            "a control actually created a file in the repository; the interception is supposed to "
            "record the write and stop it, so the experiment cannot leave debris behind"
        )

    #: The CI half, expressed once so a CONTROL can run it against a deliberately broken workflow.
    #:
    #: 🔴 **THE ASSERTIONS BELOW WERE MEASURED GREEN UNDER 15 OF 16 WAYS TO DISABLE THE JOB.** The
    #: previous version parsed the YAML rather than grepping it, which fixed the two shapes a
    #: verifier had named and left the rest: a step-level `if`, a job-level `continue-on-error`,
    #: `; exit 0`, `set +e`, a commented-out `run:`, an `on:` narrowed so the workflow never fires on
    #: a PR, and the install landing after the run. **A gate over CI that is not itself controlled is
    #: a gate about which nobody has measured anything** — which is this file's own standard, applied
    #: to the file's own CI wiring for the first time.
    @staticmethod
    def _assert_census_ci(wf) -> None:
        """Everything CI must be true for the census to be a gate. Raises `AssertionError`."""
        def _live(run: str) -> str:
            """The commands, with comment lines removed — a `#`-commented `run:` satisfied every
            substring check written over it, twice, in two different tests."""
            out = []
            for line in str(run).splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    out.append(stripped)
            return "\n".join(out)

        #: 🔴 **THE COMMAND CLAUSES WERE A BLACKLIST, AND A BLACKLIST OF SHELL SPELLINGS IS NOT A
        #: SPACE.** The previous version refused `||`, `set +e` and a whole-line `exit 0`; a verifier
        #: walked past it with `; true` on the same line, `&`, `| cat`, `echo …`, `--help`,
        #: `if false; then … fi`, `trap 'exit 0' ERR`, and a mid-line `#` comment. Nine more
        #: spellings would have been nine more clauses and a tenth spelling.
        #:
        #: So the command is a **whitelist**: the census step's live command, whitespace-normalised,
        #: must be exactly this. One clause, and the space it covers is closed.
        #: The whitelist, and it is exactly two spellings. `--force` is admitted for one reason
        #: and it is not convenience: it **disables the local verdict cache**, so CI re-derives the
        #: answer from nothing every run. It can only make the gate do MORE work, which is the
        #: opposite of every command this clause exists to refuse — `--write` regenerates the
        #: allowlist instead of checking it, `--help` exits 0 having measured nothing. A cached
        #: verdict must never be able to certify a branch, and `--force` is what guarantees that.
        EXPECTED = "python scripts/agentruntime-census.py"
        ALLOWED = (EXPECTED, EXPECTED + " --force")

        triggers = wf.get("on") or wf.get(True)          # PyYAML parses bare `on:` as the bool True
        # 🔴 An INTERSECTION: one key sufficed, so deleting `pull_request` left the check green over
        # a census that never gates a PR. Both are required, and so are their VALUES — `paths`,
        # `paths-ignore`, `branches` and `types` each narrow a trigger to nothing while the key
        # remains, and none of them was read.
        assert isinstance(triggers, dict), f"the workflow's triggers are {triggers!r}"
        for needed in ("push", "pull_request"):
            assert needed in triggers, (
                f"the workflow does not fire on `{needed}`: a census that does not gate a pull "
                f"request is a gate nobody passes through"
            )
            cfg = triggers[needed] or {}
            assert not isinstance(cfg, dict) or not (set(cfg) & {"paths", "paths-ignore", "types"}), (
                f"`on.{needed}` is narrowed by {sorted(set(cfg) & {'paths', 'paths-ignore', 'types'})}"
                f", so the workflow can be silently skipped for the changes this gate is about"
            )
            branches = (cfg or {}).get("branches") if isinstance(cfg, dict) else None
            assert branches is None or "main" in branches, (
                f"`on.{needed}.branches` is {branches!r} and does not include `main`"
            )
        # `defaults.run.shell` at workflow level can swallow a non-zero rc for every step below it.
        assert "defaults" not in wf, "a workflow-level `defaults` can redefine the shell rc handling"

        job = (wf.get("jobs") or {}).get("agentruntime-census")
        assert job, "the census job is not in the workflow"
        assert "if" not in job, "the census job is conditional, so it can be skipped silently"
        assert not job.get("continue-on-error"), (
            "the census JOB is continue-on-error, so every step inside it can fail green — the "
            "step-level check below never sees this one"
        )
        # 🔴 None of these five was read, and each disables the job while leaving every `run:`
        # string intact: a never-matching runner label, a dependency on a job that skips, a matrix
        # that excludes every combination, and a shell override at either level.
        assert job.get("runs-on") in ("ubuntu-latest", "ubuntu-22.04", "ubuntu-24.04"), (
            f"`runs-on` is {job.get('runs-on')!r}; a label no runner carries queues forever and the "
            f"check never reports"
        )
        assert "needs" not in job, (
            f"the census `needs` {job.get('needs')!r}: if that job is skipped this one is skipped "
            f"too, and the workflow still succeeds"
        )
        assert "strategy" not in job, (
            "a matrix can exclude every combination, producing zero jobs and a green workflow"
        )
        assert "defaults" not in job, "a job-level `defaults` can redefine the shell rc handling"

        steps = job.get("steps") or []
        runs = [_live(s.get("run", "")) for s in steps]
        census_steps = [(s, r) for s, r in zip(steps, runs)
                        if "agentruntime-census.py" in r or "agentruntime-census.py" in
                        str(s.get("uses", ""))]
        assert census_steps, "no step runs the census; installing its dependencies is not running it"
        for s, r in census_steps:
            # The whitelist. Every command family the blacklist chased — `--write`, `--selftest`,
            # `|| true`, `; true`, `&`, `| cat`, `echo`, `--help`, `if false`, `trap` — fails this
            # one clause, and so does the eleventh spelling nobody has written.
            assert " ".join(r.split()) in ALLOWED, (
                f"the census step runs {r!r}, not one of {ALLOWED!r}. Anything else is a command "
                f"whose exit code this check has not established reaches the job: a trailing "
                f"`; true`, a `| cat`, a `&`, an `echo`, a `--help`, or a flag that regenerates the "
                f"allowlist instead of checking it."
            )
            assert "shell" not in s, (
                f"the step overrides its `shell` ({s.get('shell')!r}), which decides whether a "
                f"non-zero exit fails the step at all"
            )
            assert "if" not in s, (
                f"the census STEP is conditional, so the job can be green having never run it: "
                f"{s.get('if')!r}"
            )
            assert not s.get("continue-on-error"), "the census step cannot fail the build"
        installs = "\n".join(runs).split("agentruntime-census.py")[0]
        assert "requirements-test.txt" in installs, (
            "the job installs no pytest BEFORE the census runs, so the census's selftest runs the "
            "suite and can only fail - a gate whose green state is unreachable"
        )

    def test_THE_ALLOCATOR_FREES_WHAT_IT_ALLOCATED_WHEN_IT_FAILS(self):
        """🔴 **THE TWELFTH PAIR REPAIRED AT ONE END, AND MY FIRST FIX FOR IT HAD NO TEST.**

        `census()` and `_selftest()` each free their mirror in a `finally`. A verifier then pointed
        at the third site: **`_mirror()` itself**. It calls `mkdtemp` and *then* does work that can
        fail — `git ls-files` erroring, a permission error, a Windows path-length limit on a deep
        tracked path under the long temp prefix this very verification workflow checks out into.
        When it raises, neither writer's `try` has been entered, so neither `finally` covers it and
        `census()`'s `atexit` is not registered yet. Executed by that verifier both ways: an empty
        directory on the `git` failure, and one holding a **partial copy of the repository** on a
        mid-copy `OSError` — 239 MB of a tree that is not the tree, which is worse debris than none.

        And my repair shipped unguarded: the 8-cell drive **patches `_mirror`**, so the real one's
        failure path is never exercised there. My own reversion prover caught it — removing the
        `except` left the suite green. **A function that allocates before it can fail owns what it
        allocated until it returns**, and that is what this drives, on both failure paths.
        """
        import importlib.util
        import pathlib
        import subprocess
        import tempfile

        spec = importlib.util.spec_from_file_location(
            "_census_alloc_probe", _REPO / "scripts" / "agentruntime-census.py")
        census_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(census_mod)

        # 🔴 **THIS TRACKED WHAT THE ALLOCATOR ALLOCATED, AFTER GLOBBING THE WHOLE TEMP ROOT.**
        # `temp_root.glob("lw-census-*")` is a GLOBAL predicate standing in for a question about one
        # operation, and it made this test a false witness the moment anything else on the machine
        # held a mirror: a parallel census gives every worker its own `lw-census-*` directory, so
        # this assertion saw a *sibling's* mirror appear between `before` and `leaked` and failed —
        # reddening the suite, and with it reporting whichever refusal was under measurement as RED.
        # Two sites flipped SILENT→RED that way, non-deterministically, which is worse than a stable
        # wrong answer because a re-run moves it.
        #
        # `mkdtemp` is the allocator. Recording what IT returns answers the actual question — *did
        # this call free what this call created* — and is blind to every other directory in the
        # world, which is the property a leak check needs and a glob cannot have.
        allocated: list[pathlib.Path] = []
        _real_mkdtemp = tempfile.mkdtemp

        def _recording_mkdtemp(*a, **k):
            d = _real_mkdtemp(*a, **k)
            allocated.append(pathlib.Path(d))
            return d

        for label, boom in (
            ("`git ls-files` fails", lambda *a, **k: (_ for _ in ()).throw(
                subprocess.CalledProcessError(128, "git"))),
            ("the copy loop raises mid-way", None),
        ):
            allocated.clear()
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(tempfile, "mkdtemp", _recording_mkdtemp)
                if boom is not None:
                    mp.setattr(census_mod.subprocess, "run", boom)
                else:
                    calls = {"n": 0}

                    def _fail_after_a_few(src, dst):
                        calls["n"] += 1
                        if calls["n"] > 5:
                            raise OSError(36, "File name too long")
                        return None

                    # `shutil` is imported INSIDE `_mirror`, so it is not an attribute of the
                    # module — patch the real one, which is what `_mirror` will look up.
                    import shutil as _sh
                    mp.setattr(_sh, "copyfile", _fail_after_a_few)
                with pytest.raises(BaseException):        # noqa: B017 - the failure is the input
                    census_mod._mirror()
            leaked = sorted(str(p) for p in allocated if p.exists())
            assert not leaked, (
                f"{label}: `_mirror()` left {leaked} behind. It allocated before it could fail, so "
                f"nothing else can free it: neither writer's `try` has been entered and the "
                f"`atexit` is not registered yet."
            )

    def test_THE_DIGEST_IS_BLIND_TO_PROSE__including_an_f_STRING(self):
        """🔴 **AN f-STRING WAS NOT PROSE-BLIND, AND THE DRIFT CHECK COULD NOT SEE THE CHURN.**

        `_shape_digest` blanks `ast.Constant` strings so that rewording a refusal keeps its
        allowlist row. An f-string is a `JoinedStr` whose `FormattedValue` carries a bare `ast.Name`
        — so adding `{ID_MAX_LEN}` to one message moved `check_contract::ContractViolation::7` from
        `6899e25d` to `179f246e`, and the census printed **`NOW GUARDED — drop it from the
        allowlist`** for a row whose id had simply ceased to exist.

        **The half that matters is why nobody could have noticed.** On a RED site the churn is
        invisible: the old id leaves the allowlist and reads as a closed finding, and the new id,
        being red, never appears as `NEWLY SILENT`. So *"zero NEWLY SILENT, therefore the digest did
        not churn"* is an inference whose control and seed agree by construction — and I published
        it as evidence. A verifier caught it.

        My repair also shipped unguarded, which my own prover caught: removing `visit_JoinedStr`
        left the suite green.
        """
        import ast
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_census_digest_probe", _REPO / "scripts" / "agentruntime-census.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        def _digest(src: str) -> str:
            node = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Raise))
            return mod._shape_digest(node)

        # The same refusal, three ways of writing its message. All three must be one row.
        plain = 'raise ValueError("the id is not acceptable")'
        reworded = 'raise ValueError("this identifier cannot be admitted, and here is why")'
        fstring = 'raise ValueError(f"the id is not acceptable: at most {LIMIT} characters")'
        fstring2 = 'raise ValueError(f"nope: {OTHER_NAME} and {A_THIRD}")'
        digests = {k: _digest(v) for k, v in
                   {"plain": plain, "reworded": reworded, "f-string": fstring,
                    "another f-string": fstring2}.items()}
        assert len(set(digests.values())) == 1, (
            f"the digest is not blind to prose: {digests}. A reworded message must keep its "
            f"allowlist row — and an f-string is a message. When it does not, a row silently "
            f"relocates and the drift check reports it as a CLOSED FINDING, because a churn on a "
            f"RED site produces a `NOW GUARDED` line with no matching `NEWLY SILENT`."
        )
        # ...and the control: a STRUCTURAL change must still move the row, or the digest is blind
        # to everything and every site collapses onto one id.
        assert _digest('raise TypeError("the id is not acceptable")') not in digests.values(), (
            "the digest no longer distinguishes the exception CLASS; blanking has gone from "
            "prose-blind to blind"
        )
        assert _digest('raise ValueError("x", "y")') not in digests.values(), (
            "the digest no longer distinguishes the refusal's ARITY"
        )

    def test_EVERY_GUARD_DECLARES_WHETHER_IT_CAN_FAIL(self):
        """🔴 **SIX ROUNDS FOUND THAT THE GUARDS, NOT THE FIXES, ARE WHERE THE DEFECTS NOW LIVE.**

        R26 is the clean case: every one of its ten findings was a guard rather than a defect — a
        control that could not fail (`tainted = set(LIVE)` is unconditional, so the assertion over it
        was a tautology), a column that reddened for the declaration-loss clause instead of the one
        it was testing, an anti-vacuity check calibrated below the thing it guarded. Sibling pairs
        fixed at both ends across the run: **3 of 12**.

        *"A fix without a red-able test is not a closed finding"* has been a standing rule the whole
        time. It did not hold, because it is a thing a person is supposed to remember at the moment
        they are most convinced they have just fixed something. **In R26 the reversion prover caught
        four fixes shipped with no guard at all**, before either verifier saw the tree.

        So the rule becomes a partition, and this is the clause that enforces it: **every guard in
        these two suites is either falsified, deliberately unfalsifiable with a stated reason, or in
        the checked-in backlog.** A guard in none of the three fails here — on the day it is written,
        not six rounds later.

        The denominator is enumerated from the suites by AST, never from a list, because a
        hand-maintained denominator is the failure this run has paid for five times.

        This is the CHEAP half — it checks the partition, not the falsifiers. Running them is
        `scripts/agentruntime-falsification.py --run`, ~2 minutes, and it has its own CI job.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_falsify_probe", _REPO / "scripts" / "agentruntime-falsification.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # 🔴 **AN UNTRACKED REGISTER IS A REGISTER NOBODY ELSE HAS**, and the census found this one
        # within minutes of the instrument being written: its own three files were untracked, so the
        # live tree was green and **every clean checkout — including CI — was red**. That is the
        # census's mirror-of-tracked-files design catching a defect in the gate written beside it.
        #
        # It is the same shape as a gate whose file set is typed out: the thing that decides the
        # answer is not the thing the next machine will see.
        # 🔴 **AND THE FIRST VERSION OF THIS CLAUSE CONFLATED "CANNOT ASK" WITH "ANSWERED NO" —
        # WHICH IS THE DEFECT `_suite_is_green` RECORDS IN CAPITALS, TWENTY LINES OF READING AWAY.**
        # `git ls-files` exits **128** inside the census's mirror, because a mirror is a copy of
        # tracked files and has no `.git`. Treating every non-zero exit as "not tracked" turned a
        # question that could not be asked into a failing answer, and reddened the census's own
        # selftest against a tree that was fine. *"pytest reserves exit 1 for test failures; 2–5
        # mean it did not get to run them, and that is a broken harness, not a guarded refusal."*
        # Same sentence, different command.
        import subprocess as _sp

        _is_repo = _sp.run(["git", "rev-parse", "--git-dir"], cwd=_REPO,
                           capture_output=True).returncode == 0
        if _is_repo:
            untracked = [
                rel for rel in ("scripts/agentruntime-falsification.py",
                                "scripts/agentruntime_falsifiers.py",
                                "contracts/agentruntime-falsification-unproven.txt")
                if _sp.run(["git", "ls-files", "--error-unmatch", rel], cwd=_REPO,
                           capture_output=True).returncode == 1
            ]
            assert not untracked, (
                f"{untracked} are not tracked. The falsification gate would pass here and fail in "
                f"every other checkout, which is worse than not having it — the census found "
                f"exactly that within minutes of this instrument being written."
            )

        guards = mod._guards()
        assert len(guards) >= 250, (
            f"the enumeration found only {len(guards)} guards; it broke, and a partition over "
            f"nothing is exactly the vacuity this instrument exists to end"
        )
        # 🔴 **AND THE TOTAL IS NOT ENOUGH.** A floor over the sum stays green while ONE suite
        # silently contributes nothing — which is R26's headline shape exactly (an anti-vacuity
        # assertion calibrated below the thing it guarded, over a corpus that had collapsed to 19
        # of 334). Per suite, so a suite that stops parsing is a failure rather than a rounding.
        per_suite = {s: sum(1 for v in guards.values() if v == s) for s in mod.SUITES}
        assert all(per_suite.values()), f"a suite contributed no guards at all: {per_suite}"
        recorded = sorted(
            l.strip() for l in mod.UNPROVEN.read_text("utf-8").splitlines()
            if l.strip() and not l.startswith("#"))
        declared = set(mod.FALSIFIERS) | set(mod.UNFALSIFIED) | set(recorded)

        undeclared = sorted(set(guards) - declared)
        assert not undeclared, (
            f"{len(undeclared)} guard(s) declare nothing about whether they can fail: "
            f"{undeclared[:8]}. Write a falsifier in `scripts/agentruntime_falsifiers.py`, or "
            f"record it in the backlog with `--write`, or say in `UNFALSIFIED` why no edit can make "
            f"it red. Doing none of the three is how four fixes shipped unguarded in one round."
        )
        stale = sorted(declared - set(guards))
        assert not stale, (
            f"{stale} name no guard in either suite — a register that has gone stale claims "
            f"coverage it does not have, which is the shape six consecutive rounds of a hand-typed "
            f"record already produced here."
        )

    def test_A_STALE_FALSIFIER_ANCHOR_IS_CAUGHT_WITHOUT_RUNNING_A_SUITE(self):
        """REJECTS: a falsifier that no longer applies, discovered fifteen minutes into `--run`.

        🔴 **CP-2 PRODUCED TWO OF THESE IN ONE SESSION.** A falsifier is *data about the tree*, and
        data about the tree goes stale when the tree moves: CP-2.1's census row anchored on a
        `return` I then replaced, and CP-2.2's rewrite of the `withheld` expression invalidated a
        row written twenty minutes earlier. `_apply` refuses both — correctly — but it refuses them
        mid-run, after however many suites have already executed.

        Checking an anchor is a string comparison. Paying for it with a suite run was a choice
        nobody made on purpose.

        Both halves are asserted: the tree is clean **and** the check can fire. The second is the
        one that matters — a `stale_anchors` that always returns `[]` would satisfy the first
        forever.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_falsify_probe3", _REPO / "scripts" / "agentruntime-falsification.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod.stale_anchors() == [], "a recorded falsifier no longer applies to this tree"

        real = dict(mod.FALSIFIERS)
        try:
            mod.FALSIFIERS.clear()
            mod.FALSIFIERS["test_fabricated"] = [
                ("scripts/agentruntime-falsification.py", "a string that is not in this file", "x")
            ]
            assert mod.stale_anchors(), "the check did not fire on an anchor that matches nothing"
            mod.FALSIFIERS["test_fabricated"] = [
                ("scripts/no-such-file-at-all.py", "anything", "x")
            ]
            assert mod.stale_anchors(), "the check did not fire on a file that does not exist"
        finally:
            mod.FALSIFIERS.clear()
            mod.FALSIFIERS.update(real)

    def test_THE_SUITE_LIST_IS_EVERY_CP_SUITE_ON_DISK(self):
        """REJECTS: a new checkpoint suite whose guards are outside the partition entirely.

        🔴 **THE PARTITION IS ONLY AS HONEST AS ITS DENOMINATOR, AND `SUITES` IS THE DENOMINATOR'S
        DENOMINATOR.** Everything above enumerates guards *from the files named in `SUITES`* — so a
        suite that is simply not in that tuple is 100% declared, by arithmetic, without a single
        falsifier being written. That is the self-derived-total failure this instrument exists to
        end, arriving through its own front door: CP-2 adds a suite, its 27 guards are invisible,
        and the gate reports a clean partition over a corpus that has quietly stopped growing.

        The floor is what is ON DISK, discovered by glob, so adding `tests/test_cp3_*.py` fails
        here on the day it is created rather than in whatever round someone notices.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_falsify_probe2", _REPO / "scripts" / "agentruntime-falsification.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        tests_dir = _REPO / "services" / "chat-service" / "tests"
        on_disk = sorted(f"tests/{p.name}" for p in tests_dir.glob("test_cp*.py"))
        assert sorted(mod.SUITES) == on_disk, (
            f"SUITES is {sorted(mod.SUITES)} and the checkpoint suites on disk are {on_disk}. "
            f"A suite outside the tuple is 100% declared by arithmetic — every guard in it is "
            f"unmeasured while the gate prints a clean partition."
        )

    def test_THE_CENSUS_RUNS_EVERY_CP_SUITE_NOT_ONLY_THE_ONE_IT_WAS_BORN_WITH(self):
        """REJECTS: a refusal guarded by a suite the census does not run, reported as SILENT.

        🔴 **CP-2.1 IS WHAT TURNED A HARD-CODED `SUITE` INTO A DEFECT.** `assembly.py` shipped two
        refusals guarded entirely by `tests/test_cp2_assembly.py`; with the census running the CP-1
        suite alone, neutering either left it green and **both would have been named SILENT** — the
        census asking a person to explain two refusals that are, in fact, guarded.

        The direction is the safe one (a false SILENT is a finding, never a false green) and it is
        still a false finding, which is the defect one level up: an instrument that manufactures
        work. Derived rather than listed, for the reason five published denominators in this run
        have already demonstrated.

        **The subject is the PREDICATE, computed here independently of the census's own walk** — a
        guard that called `_suites` and compared it to `_suites` would be the tautology R26 found.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_census_probe", _REPO / "scripts" / "agentruntime-census.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        cs = _REPO / "services" / "chat-service"
        # Independently derived: a plain text scan, not the census's AST walk.
        importers = sorted(
            f"tests/{p.name}" for p in (cs / "tests").glob("test_*.py")
            if "import app.agentruntime" in p.read_text("utf-8")
            or "from app.agentruntime" in p.read_text("utf-8")
        )
        assert mod._suites(cs) == importers, (
            f"the census would run {mod._suites(cs)} while the suites that can observe the package "
            f"are {importers}. A refusal guarded only by an unrun suite is reported SILENT."
        )
        assert "tests/test_cp2_assembly.py" in importers, (
            "the CP-2 suite no longer imports the package; this guard would then agree with a "
            "census that runs whatever is left, which is how a shrinking denominator reads as "
            "agreement"
        )

    def test_THE_CENSUS_IS_WIRED_TO_RUN_IN_CI(self):
        """The real workflow satisfies every clause. `_assert_census_ci` is the whole check; the
        test below is what establishes the check can fail."""
        import yaml

        wf = yaml.safe_load((_REPO / ".github" / "workflows" / "lint-foundation.yml")
                            .read_text("utf-8"))
        self._assert_census_ci(wf)

    def test_THE_CI_CHECK_REDS_ON_EVERY_WAY_TO_DISABLE_THE_CENSUS(self):
        """🔴 **THE ENUMERATION, AND IT IS THE POINT OF THE PREVIOUS TEST.** Two verifiers measured
        the CI half green under 15 of 16 disable shapes; the answer to that is not more clauses, it
        is a control per shape, so the count is measured rather than asserted.

        Each entry below turns the workflow into one that does **not** gate anything. Every one must
        make `_assert_census_ci` raise. A shape that stays green here is a documented hole, and this
        list is the only honest place to record one.
        """
        import yaml

        real = yaml.safe_load((_REPO / ".github" / "workflows" / "lint-foundation.yml")
                              .read_text("utf-8"))
        JOB, RUN = "agentruntime-census", "python scripts/agentruntime-census.py"

        def _census_step(wf):
            job = wf["jobs"][JOB]
            return next(s for s in job["steps"] if "agentruntime-census.py" in str(s.get("run", "")))

        def _install_step(wf):
            job = wf["jobs"][JOB]
            return next(s for s in job["steps"] if "requirements-test.txt" in str(s.get("run", "")))

        def _drop_job(wf):
            del wf["jobs"][JOB]

        def _job_if_false(wf):
            wf["jobs"][JOB]["if"] = "false"

        def _step_if_false(wf):
            _census_step(wf)["if"] = "false"

        def _job_continue_on_error(wf):
            wf["jobs"][JOB]["continue-on-error"] = True

        def _step_continue_on_error(wf):
            _census_step(wf)["continue-on-error"] = True

        def _write_flag(wf):
            _census_step(wf)["run"] = RUN + " --write"

        def _selftest_only(wf):
            _census_step(wf)["run"] = RUN + " --selftest"

        def _or_true(wf):
            _census_step(wf)["run"] = RUN + " || true"

        def _exit_zero(wf):
            _census_step(wf)["run"] = RUN + "\nexit 0\n"

        def _set_plus_e(wf):
            _census_step(wf)["run"] = "set +e\n" + RUN

        def _comment_out(wf):
            _census_step(wf)["run"] = "# " + RUN + "\necho skipped"

        def _drop_step(wf):
            job = wf["jobs"][JOB]
            job["steps"] = [s for s in job["steps"]
                            if "agentruntime-census.py" not in str(s.get("run", ""))]

        def _drop_install(wf):
            _install_step(wf)["run"] = "python -m pip install --quiet -r requirements.txt"

        def _install_after(wf):
            job, inst = wf["jobs"][JOB], _install_step(wf)
            job["steps"] = [s for s in job["steps"] if s is not inst] + [inst]

        def _dispatch_only(wf):
            wf.pop("on", None), wf.pop(True, None)
            wf["on"] = {"workflow_dispatch": None}

        def _rename_script(wf):
            _census_step(wf)["run"] = "python scripts/agentruntime-membrane-gate.py"

        def _empty_steps(wf):
            wf["jobs"][JOB]["steps"] = []

        # 🔴 **A VERIFIER ENUMERATED 22 MORE AND THE CHECK SURVIVED 19 OF THEM.** My seventeen were
        # one narrow family — the text of a `run:` string plus `if`/`continue-on-error` at two
        # levels — and I published them as the space. They are all here now, as controls, because a
        # count of shapes I chose is a count of what I thought of.
        def _semicolon_true(wf):
            _census_step(wf)["run"] = RUN + " ; true"

        def _background(wf):
            _census_step(wf)["run"] = RUN + " &"

        def _pipe_cat(wf):
            _census_step(wf)["run"] = RUN + " | cat"

        def _echoed(wf):
            _census_step(wf)["run"] = "echo " + RUN

        def _help_flag(wf):
            _census_step(wf)["run"] = RUN + " --help"

        def _if_false(wf):
            _census_step(wf)["run"] = "if false; then " + RUN + "; fi"

        def _trap_exit(wf):
            _census_step(wf)["run"] = "trap 'exit 0' ERR\n" + RUN

        def _midline_comment(wf):
            _census_step(wf)["run"] = "echo stub  # " + RUN

        def _paths_ignore(wf):
            wf.pop("on", None), wf.pop(True, None)
            wf["on"] = {"push": {"paths-ignore": ["**"]}, "pull_request": {"paths-ignore": ["**"]}}

        def _paths_docs(wf):
            wf.pop("on", None), wf.pop(True, None)
            wf["on"] = {"push": {"paths": ["docs/**"]}, "pull_request": {"paths": ["docs/**"]}}

        def _no_such_branch(wf):
            wf.pop("on", None), wf.pop(True, None)
            wf["on"] = {"push": {"branches": ["no-such-branch"]},
                        "pull_request": {"branches": ["no-such-branch"]}}

        def _pr_types_labeled(wf):
            wf.pop("on", None), wf.pop(True, None)
            wf["on"] = {"push": {"branches": ["main"]}, "pull_request": {"types": ["labeled"]}}

        def _push_only(wf):
            wf.pop("on", None), wf.pop(True, None)
            wf["on"] = {"push": {"branches": ["main"]}}

        def _never_matching_runner(wf):
            wf["jobs"][JOB]["runs-on"] = ["self-hosted", "never-exists"]

        def _needs_a_skippable_job(wf):
            wf["jobs"][JOB]["needs"] = ["lint"]

        def _matrix_all_excluded(wf):
            wf["jobs"][JOB]["strategy"] = {"matrix": {"x": [1], "exclude": [{"x": 1}]}}

        def _workflow_defaults_shell(wf):
            wf["defaults"] = {"run": {"shell": "bash -c 'eval \"$0\"; exit 0' {0}"}}

        def _job_defaults_shell(wf):
            wf["jobs"][JOB]["defaults"] = {"run": {"shell": "bash -c 'eval \"$0\"; exit 0' {0}"}}

        def _step_shell(wf):
            _census_step(wf)["shell"] = "bash -c 'eval \"$0\"; exit 0' {0}"

        SHAPES = {
            "`; true` on the same line": _semicolon_true,
            "`&` backgrounds it": _background,
            "`| cat` takes the pipeline's rc": _pipe_cat,
            "the command is echoed, not run": _echoed,
            "`--help` instead of a census": _help_flag,
            "`if false; then ... fi`": _if_false,
            "`trap 'exit 0' ERR` before it": _trap_exit,
            "a MID-LINE `#` hides the command": _midline_comment,
            "`paths-ignore: ['**']` on both triggers": _paths_ignore,
            "`paths: ['docs/**']`": _paths_docs,
            "`branches: [no-such-branch]`": _no_such_branch,
            "`pull_request: {types: [labeled]}`": _pr_types_labeled,
            "`pull_request` deleted, push-only": _push_only,
            "a never-matching `runs-on` label": _never_matching_runner,
            "`needs:` a job that can skip": _needs_a_skippable_job,
            "a matrix with every combination excluded": _matrix_all_excluded,
            "workflow-level `defaults.run.shell` swallows rc": _workflow_defaults_shell,
            "job-level `defaults.run.shell` swallows rc": _job_defaults_shell,
            "step-level `shell:` swallows rc": _step_shell,
            "the job is deleted": _drop_job,
            "the job is `if: false`": _job_if_false,
            "the STEP is `if: false`": _step_if_false,
            "the JOB is continue-on-error": _job_continue_on_error,
            "the STEP is continue-on-error": _step_continue_on_error,
            "`--write` regenerates instead of checking": _write_flag,
            "`--selftest` only, so no site is enumerated": _selftest_only,
            "`|| true` swallows the exit code": _or_true,
            "`exit 0` on the next line discards it": _exit_zero,
            "`set +e` disables error propagation": _set_plus_e,
            "the `run:` is commented out": _comment_out,
            "the census step is removed": _drop_step,
            "requirements-test.txt is not installed": _drop_install,
            "the install lands AFTER the census": _install_after,
            "`on:` is narrowed to workflow_dispatch": _dispatch_only,
            "the step runs a different script": _rename_script,
            "the job has no steps at all": _empty_steps,
        }

        survived = []
        for label, mutate in SHAPES.items():
            wf = copy.deepcopy(real)
            mutate(wf)
            try:
                self._assert_census_ci(wf)
            except AssertionError:
                continue
            except (KeyError, StopIteration) as exc:      # the mutation itself did not apply
                survived.append(f"{label} (the control did not take: {exc!r})")
                continue
            survived.append(label)
        assert not survived, (
            f"{len(survived)} of {len(SHAPES)} ways to disable the census leave the CI check GREEN: "
            f"{survived}. Each is a way this gate can stop gating with nobody informed."
        )
        # 🔴 **AND THE ONE SHAPE NO YAML CHECK CAN EVER SEE, RECORDED RATHER THAN LEFT IMPLICIT.**
        # Branch protection may simply not require `agentruntime-census`, and nothing in this
        # repository can observe that: the setting lives in GitHub, not in the tree. It is a
        # **permanent named residual**, not a gap to be closed later, and the honest place for it is
        # beside the enumeration that would otherwise read as complete. Every count above is
        # therefore "of the shapes expressible in this file".
        assert len(SHAPES) >= 36, (
            f"the enumeration shrank to {len(SHAPES)}; it was 39 shapes across two independent "
            f"derivations and shrinking it is how a published count becomes a lower bound again"
        )

    def test_THE_MANIFEST_IS_WRITTEN_WITH_LF_ON_EVERY_PLATFORM(self, tmp_path):
        """🔴 **`generate()` — the only writer this code has — emitted CRLF on Windows**,
        and a verifier measured it rewriting the committed manifest line for line. **The M1 drift
        gate is a byte-equality check** and `canon.digest` hashes bytes, so the same declarations
        written on two machines were two different documents: a drift alarm for a change nobody
        made, which is the failure §0.14.2's normalisation doors exist to prevent, one layer down.

        `Path.write_text` translates the newline to the platform's. That is not a quirk to
        remember — it is what the function does — and the same defect landed three times in one
        week: in a verifier's restore harness, in the census script written to end this class of
        failure, and here, in production. A manifest is a contract artifact: committed, diffed,
        compared across machines.
        """
        path = tmp_path / "m.json"
        generate([admit(_tool("book_list"))], path=path, bootstrap=True)
        raw = path.read_bytes()
        assert b"\r\n" not in raw, (
            "the manifest was written with CRLF; the M1 drift gate compares bytes, so this "
            "document differs from the identical one written on another platform"
        )
        assert raw.endswith(b"\n"), "the manifest has no trailing newline"
        # ...and pinning the newline did not change what is stored.
        assert load(path=path)["declarations"][0]["id"] == "book_list"


class TestAGateVerdictIsAboutOneTree:
    """REJECTS: a recorded verdict that certifies a tree it was not measured on.

    The cache exists to enforce *a gate's recorded answer must be about the tree you are
    committing* — not to run gates less often. Every guard here is about that property, and each is
    deliberately cheap: this file runs once per raise site inside the census, so a second of work
    here is a minute and a half of gate time.
    """

    @staticmethod
    def _gatecache():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_gatecache_probe", _REPO / "scripts" / "agentruntime_gatecache.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @staticmethod
    def _gate_scripts():
        import ast
        return {p.name: ast.parse(p.read_text(encoding="utf-8"))
                for p in (_REPO / "scripts").glob("agentruntime-*.py")}

    def test_THE_DIGEST_CANNOT_BE_COMPUTED_AT_THE_MOMENT_OF_RECORDING(self):
        """`digest` is keyword-only and required, so a caller cannot forget to hand one in.

        The first version computed it inside `store()`. These runs take minutes; a file edited while
        one is in flight would have been stamped into the verdict as though it had been measured,
        and the gate would certify a tree it never saw — the *measured-on-a-dirty-tree* failure,
        reproduced inside the mechanism built to end it.
        """
        import inspect
        sig = inspect.signature(self._gatecache().store)
        p = sig.parameters.get("digest")
        assert p is not None and p.kind is inspect.Parameter.KEYWORD_ONLY, (
            f"store() takes {list(sig.parameters)}; `digest` must be keyword-only and required"
        )
        assert p.default is inspect.Parameter.empty, (
            "`digest` has a default, so a caller can omit it and get a verdict stamped with "
            "whatever the tree happened to be at the moment of writing"
        )

    def test_NO_GATE_COMPUTES_ITS_DIGEST_AT_THE_STORE_CALL(self):
        """AST: `digest=` must be a NAME bound earlier, never a call evaluated inline.

        `store(..., digest=_gatecache.tree_digest())` type-checks, satisfies the signature guard
        above, and reintroduces the entire defect. The property is *when* the digest is taken.
        """
        import ast
        offenders = []
        for name, tree in self._gate_scripts().items():
            for call in ast.walk(tree):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "store"):
                    continue
                for kw in call.keywords:
                    if kw.arg == "digest" and not isinstance(kw.value, ast.Name):
                        offenders.append(f"{name}:{call.lineno} digest={ast.unparse(kw.value)}")
        assert offenders == [], (
            f"{offenders} — the digest is evaluated AT the store call, so it describes the tree "
            f"as it is when the answer is written rather than when it was measured. Bind it before "
            f"the run and pass the name."
        )

    def test_BOTH_GATES_MIRROR_THE_SAME_FILE_SET(self):
        """One home for *what can this measurement see*, because the cache key IS that set.

        The digest is sound only because it covers exactly what the gates copy. Two hand-kept
        prefix lists would drift the first time one was widened, and the key would then certify a
        tree while a file outside it moved the answer — the approximation this design refuses.
        """
        import ast
        users = []
        for name, tree in self._gate_scripts().items():
            src = ast.unparse(tree)
            if "mkdtemp" not in src:
                continue
            assert "MIRROR_PREFIXES" in src, (
                f"{name} builds a mirror without filtering on the shared MIRROR_PREFIXES; its "
                f"mirror and the cache key now describe different file sets"
            )
            users.append(name)
        assert len(users) >= 2, f"expected both gate scripts to build mirrors, found {users}"

    def test_A_VERDICT_FILE_IS_NOT_PART_OF_ITS_OWN_KEY(self):
        """A tracked verdict under `contracts/` would otherwise be stale the instant it was written.

        Excluded by SUFFIX rather than by exact name, so a second gate cannot reintroduce the cycle
        by choosing a new filename — the pair-fixed-at-one-end failure this run has recorded
        thirteen times.
        """
        g = self._gatecache()
        # The FILTER, not the tracked set: verdict files are git-ignored, so asserting their
        # absence from `mirrored_files()` would be vacuously true — a guard whose subject cannot
        # exist, which is one of this run's named failure shapes.
        assert not g.is_mirrored("contracts/agentruntime-census-verdict.json"), (
            "a verdict file is inside its own key: writing it changes the digest that certifies "
            "it, so every verdict would be stale the moment it was recorded"
        )
        assert g.is_mirrored("contracts/agentruntime-census-allowlist.txt"), (
            "the suffix exclusion is too broad and now drops a file the gates genuinely read"
        )
        # 🔴 **`is_mirrored()` ONLY — `mirrored_files()` SHELLS OUT TO `git ls-files`, AND A CENSUS
        # MIRROR IS NOT A GIT REPO.** The first version called it and died with exit 128 inside every
        # one of the 90 neutered runs, so the whole census reported SELFTEST FAIL. It passed locally,
        # where the tree is a repo — which is precisely the class of thing the mirror exists to catch,
        # and it caught mine. Every property below is about the FILTER, and the filter is pure.
        assert g.is_mirrored("services/chat-service/app/agentruntime/surface.py"), (
            "the key does not cover the package the census neuters — it would call a verdict "
            "current across a change to the very code being measured"
        )
        assert g.is_mirrored("services/chat-service/tests/test_cp1_membrane.py"), (
            "the key does not cover the suite whose sensitivity decides every verdict"
        )
        assert not g.is_mirrored("frontend/src/main.tsx"), (
            "the key covers the whole repository again, so every unrelated commit invalidates "
            "every verdict and the cache stops removing any work"
        )

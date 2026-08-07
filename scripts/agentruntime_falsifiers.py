"""The falsifier for each CP-0/CP-1 guard: the exact edit that must make it RED.

🔴 **WHY THIS FILE EXISTS, AND WHY IT IS DATA RATHER THAN PROSE.**

Six verification rounds produced the same shape every time: **the fixes land, and the guards written
for them have holes.** R26 is the clearest case — every one of its ten findings was a guard, not a
defect. Sibling pairs fixed at both ends across the run: **3 of 12**.

The one instrument that has never flattered the builder is the reversion prover: apply the exact
inverse of a fix, and require the guard that names it to go red. In R26 it caught **four fixes
shipped with no guard at all** before either verifier saw the tree — `check_contract`'s two pins, the
allocator, the digest, and the import gate. Reverting each left the suite green.

So *"a fix without a red-able test is not a closed finding"* stops being a standing rule that a
person is supposed to remember and becomes **a row in a file**.

**Two rules learned by getting them wrong, both in R26:**

* **A reversion that does not restore the defect proves nothing.** One mutation made a gate
  *stricter*; another never restored the `.split()` that was the actual defect. Both produced a
  green result that read as "unguarded". A falsifier must reproduce the ORIGINAL behaviour — verify
  that before believing a row.
* **A falsifier that reds a DIFFERENT test than the one it names has measured a bystander.** The
  runner requires the named test to be the failing one.

Anchors are matched against source with line endings normalised, because this tree is CRLF in some
checkouts and LF in others and both verifiers measured a different answer from the builder.
"""
from __future__ import annotations

CS = "services/chat-service"
PKG = f"{CS}/app/agentruntime"
T1 = f"{CS}/tests/test_cp1_membrane.py"
T0 = f"{CS}/tests/test_cp0_instrument.py"
T2 = f"{CS}/tests/test_cp2_assembly.py"
CENSUS = "scripts/agentruntime-census.py"
GATE = "scripts/agentruntime-membrane-gate.py"
FALSIFY = "scripts/agentruntime-falsification.py"
REQS = f"{CS}/requirements.txt"

#: `{test name: [(file, old, new), ...]}` — apply every mutation, then that test must RED.
FALSIFIERS: dict[str, list[tuple[str, str, str]]] = {
    # ── the membrane ────────────────────────────────────────────────────────────────────────
    "test_THE_ALPHABET_ADMITS_EVERY_ID_THIS_REPOSITORY_ALREADY_DECLARES": [
        (f"{PKG}/contract.py",
         '_ID = re.compile(r"^[a-z][a-z0-9_-]{0,%d}$" % (ID_MAX_LEN - 1))',
         '_ID = re.compile(r"^[a-z][a-z0-9_]{0,%d}$" % (ID_MAX_LEN - 1))'),
    ],
    "test_ID_MAX_LEN_IS_THE_NUMBER_THE_DOCSTRING_ARGUES_FOR": [
        (f"{PKG}/contract.py", "ID_MAX_LEN = 64", "ID_MAX_LEN = 1_000_000"),
    ],
    "test_A_STR_SUBCLASS_KEY_OR_MEMBER_IS_NOT_A_STR": [
        (f"{PKG}/contract.py",
         'if type(d.id) is not str or not _ID.match(d.id or ""):',
         'if not isinstance(d.id, str) or not _ID.match(d.id or ""):'),
        (f"{PKG}/contract.py",
         'if type(m) is not str or not _ID.match(m or ""):',
         'if not isinstance(m, str) or not _ID.match(m or ""):'),
    ],
    "test_A_KEY_IS_BOUNDED_ON_BOTH_SIDES_OF_THE_COMPARISON": [
        (f"{PKG}/surface.py",
         "unadmittable = [n for n in stage.names if not _ID.match(n)]",
         "unadmittable = []"),
    ],
    "test_EVERY_DOOR_READS_THE_DOCUMENTS_OWN_STAMPS": [
        (f"{PKG}/surface.py", 'check_document(manifest_doc, "manifest document")', "pass"),
    ],
    "test_THE_ROW_COPY_IS_NOT_SHALLOW__members_is_the_one_mutable_value_a_row_carries": [
        (f"{PKG}/surface.py",
         'out.append({**r, "members": list(r["members"])})', "out.append(dict(r))"),
    ],
    "test_A_KEY_PAIR_THAT_IS_NOT_A_PAIR_IS_REFUSED__and_the_vehicle_is_a_LIST": [
        (f"{PKG}/surface.py",
         'raise ValueError(f"keys[{i}] is not a (field, direction) pair: {pair!r}")', "pass"),
    ],
    "test_AN_IMPORT_IS_A_CLAIM_ABOUT_WHAT_A_MODULE_DEPENDS_ON": [
        # The ACTUAL defeated behaviour: every whitespace-delimited TOKEN of every string literal.
        # A first attempt at this row dropped the `.split()` and therefore restored something
        # looser-but-not-defeated, which is the "a reversion that does not restore the defect"
        # error this file's docstring names.
        (T1,
         "    for node in tree.body:\n"
         "        targets = node.targets if isinstance(node, ast.Assign) else (\n"
         "            [node.target] if isinstance(node, ast.AnnAssign) else [])\n"
         '        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):\n'
         "            continue\n"
         "        for el in ast.walk(node):\n"
         "            if isinstance(el, ast.Constant) and isinstance(el.value, str):\n"
         "                used.add(el.value)\n",
         "    for el in ast.walk(tree):\n"
         "        if isinstance(el, ast.Constant) and isinstance(el.value, str):\n"
         "            used.update(el.value.split())\n"),
    ],
    # ── the instruments ─────────────────────────────────────────────────────────────────────
    "test_NO_LIVE_TREE_PATH_REACHES_A_MUTATING_CALL__the_property_not_the_API_LIST": [
        (CENSUS, "    mirror = _mirror()\n    pkg, cs = mirror / _PKG_REL",
         "    mirror = _mirror()\n    __import__('shutil').rmtree(ROOT / 'x', ignore_errors=True)"
         "\n    pkg, cs = mirror / _PKG_REL"),
    ],
    "test_THE_ALLOCATOR_FREES_WHAT_IT_ALLOCATED_WHEN_IT_FAILS": [
        (CENSUS, "    except BaseException:\n        # `BaseException`",
         "    except () :\n        # `BaseException`"),
    ],
    "test_THE_DIGEST_IS_BLIND_TO_PROSE__including_an_f_STRING": [
        (CENSUS, "    def visit_JoinedStr(self, node):\n        return ast.Constant(value=\"\\u0000\")",
         "    def visit_JoinedStr(self, node):\n        return node"),
    ],
    "test_THE_CI_CHECK_REDS_ON_EVERY_WAY_TO_DISABLE_THE_CENSUS": [
        (T1, 'assert " ".join(r.split()) == EXPECTED, (', 'assert "||" not in r, ('),
    ],
    "test_ONLY_THE_FIRST_STATEMENT_OF_A_TRY_BODY_IS_UNCONDITIONAL": [
        (T0, "            yield from _unconditional_calls(s.body[:1], pred, narrows)\n"
             "        elif isinstance(s, ast.Try):",
             "            yield from _unconditional_calls(s.body, pred, narrows)\n"
             "        elif isinstance(s, ast.Try):"),
    ],
    "test_the_TERMINAL_GATE_sees_THE_COLUMN_NAME_HOISTED_TO_A_CONSTANT": [
        (T0, "                for c in ast.iter_child_nodes(n):\n                    go(c)",
             "                for c in ast.walk(n):\n"
             "                    if c is not n and isinstance(c, ast.Constant) "
             "and isinstance(c.value, str):\n                        parts.append(c.value)"),
    ],
    "test_the_TERMINAL_GATE_DOES_NOT_RED_ON_CORRECT_CODE_IN_ANOTHER_MODULE": [
        (T0, "            _col_aliases.clear()\n"
             "            _col_aliases.update(_visible_strs(mod, tree))\n"
             "            global_sql_names = _visible_sql(mod, tree)",
             "            _col_aliases.update(_visible_strs(mod, tree))\n"
             "            global_sql_names = set()\n"
             "            for _m2, _t2 in zip(_mods, trees_all):\n"
             "                global_sql_names |= _visible_sql(_m2, _t2)"),
    ],
    "test_EVERY_PROBE_IS_WRITTEN_INTO_THE_TREE_THE_GATES_ACTUALLY_SWEEP": [
        (T0, "                if any((isinstance(x, ast.Name) and x.id in derived)\n"
             "                       or (isinstance(x, ast.Attribute) and x.attr in derived)\n"
             "                       for x in ast.walk(path)):\n                    continue",
             "                if any((isinstance(x, ast.Name) and x.id in derived)\n"
             "                       or (isinstance(x, ast.Attribute) and x.attr in derived)\n"
             "                       for x in ast.walk(scope)):\n                    continue"),
    ],

    # ── CP-2.1 · P4 assembly on the bought toolset ───────────────────────────────────────────
    #
    # 🔴 **THESE ARRIVED WITH THEIR GUARDS RATHER THAN AFTER THEM, AND THAT IS THE POINT.** The
    # standing debt at CP-1's close was 246 guards nobody had shown could fail. A new checkpoint
    # that adds 25 more to the backlog makes the number rise while the instrument built to lower
    # it prints a clean partition. So CP-2's first item ships 25 falsified guards and 0 backlogged
    # ones, and the debt is the only thing that moved.
    "test_THE_DEFERRING_API_KEEPS_A_WITHHELD_DECLARATION_REACHABLE": [
        # The item, inverted: stop putting the withheld declarations in the toolset at all. That is
        # `.filtered()` by hand, and the reveal at turn 2 then has nothing to reveal.
        (f"{PKG}/assembly.py",
         "    defs += [_tool_def(by_id[name], excluded_by=excluded_by[name]) for name in withheld_ids]",
         "    defs += []"),
    ],
    "test_THE_CEILING_API_MAKES_IT_UNREACHABLE__the_control_that_gives_the_test_above_meaning": [
        # A control must be able to fail as a CONTROL: make the "ceiling" toolset keep everything,
        # and the disagreement it exists to demonstrate disappears.
        (T2, "                [d for d in _defs(full) if d.name in offered], executor=ex",
             "                _defs(full), executor=ex"),
    ],
    "test_EACH_PASS_DEFERS_ITS_OWN_WITHHELD_SET_NOT_A_PREVIOUS_PASSES": [
        # Make one pass's deferral carry into the next by seeding it from the whole turn's log
        # rather than from this assembly's own contribution.
        (f"{PKG}/assembly.py",
         '    withheld_ids = tuple(w["tool"] for w in withheld_records)',
         '    withheld_ids = tuple(dict.fromkeys(\n'
         '        list(_CARRIED) + [w["tool"] for w in withheld_records]))\n'
         '    _CARRIED.extend(withheld_ids)'),
        (f"{PKG}/assembly.py", 'TOOLSET_ID = "agentruntime"',
                               'TOOLSET_ID = "agentruntime"\n_CARRIED: list = []'),
    ],
    "test_A_QUERY_FILTER_SHARING_THE_LOG_DOES_NOT_DEFER_WHAT_THE_ASSEMBLY_OFFERS": [
        # 🔴 The `_log_mark` fix, reverted. This reds the guard through the CONSERVATION LAW rather
        # than through the guard's own `deferred_names` assertion - and that is the mechanism
        # working, not a bystander: the post-condition in `assemble` is what enforces the property,
        # and the guard observes it end to end. Recorded here so nobody has to re-derive it.
        (f"{PKG}/surface.py",
         "        mine = [e for e in self._log.entries[_log_mark:]\n"
         "                if e.pass_number == pass_number and e.declaration_id not in widened]",
         "        mine = [e for e in self._log.entries\n"
         "                if e.pass_number == pass_number and e.declaration_id not in widened]"),
    ],
    "test_THE_TOOLSET_HOLDS_EVERY_ADMITTED_DECLARATION_NOT_ONLY_THE_OFFERED_ONES": [
        (f"{PKG}/assembly.py",
         "    defs += [_tool_def(by_id[name], excluded_by=excluded_by[name]) for name in withheld_ids]",
         "    defs += []"),
    ],
    "test_THE_WITHHELD_ONE_IS_MARKED_AND_THE_OFFERED_ONES_ARE_NOT": [
        (f"{PKG}/assembly.py",
         "    return toolset.defer_loading(withheld_ids)",
         "    return toolset.defer_loading(())"),
    ],
    "test_WITH_NOTHING_WITHHELD_NOTHING_IS_DEFERRED__tool_names_None_would_defer_EVERYTHING": [
        # The library's own default, which hides the entire surface while every count balances.
        (f"{PKG}/assembly.py",
         "    return toolset.defer_loading(withheld_ids)",
         "    return toolset.defer_loading(withheld_ids or None)"),
    ],
    "test_A_DECLARATION_THAT_WAS_NEVER_ADMITTED_IS_ABSENT_RATHER_THAN_DEFERRED": [
        # Fabricate a declaration AFTER both reconciliation checks, so the guard reds on its own
        # clause rather than on an AssemblyMismatch raised upstream - a red for a different reason
        # is a bystander, and this file's header says so.
        (f"{PKG}/assembly.py",
         "    toolset = DeclarationToolset(defs, executor=executor)",
         "    defs.append(_tool_def({**by_id[offered[0]], 'id': 'legacy_tool'}, excluded_by=None))\n"
         "    toolset = DeclarationToolset(defs, executor=executor)"),
    ],
    "test_THE_WITHHELD_RECORD_IS_CARRIED_ON_THE_META_CHANNEL": [
        (f"{PKG}/assembly.py",
         '        metadata["excluded_by"] = excluded_by',
         '        metadata["excluded_by"] = {}'),
    ],
    "test_AN_OFFERED_DECLARATION_CARRIES_NO_EXCLUSION_RECORD": [
        (f"{PKG}/assembly.py",
         "    defs = [_tool_def(by_id[name], excluded_by=excluded_by.get(name)) for name in offered]",
         "    defs = [_tool_def(by_id[name], excluded_by=excluded_by.get(name) or {}) for name in offered]"),
    ],
    "test_NO_REASON_TEXT_IS_ON_ANY_DESCRIPTION": [
        (f"{PKG}/assembly.py", "        description=None,",
         '        description="a tool that was withheld",'),
    ],
    "test_A_DECLARATION_BOTH_OFFERED_AND_WITHHELD_IS_CAUGHT_BY_THE_COUNT_NOT_THE_SET": [
        (f"{PKG}/assembly.py",
         "    if len(offered) + len(withheld_ids) != len(rows):",
         "    if False:"),
    ],
    "test_A_STALE_SURFACE_IS_REFUSED_RATHER_THAN_RECONCILED": [
        (f"{PKG}/assembly.py", "    if accounted != set(by_id):", "    if False:"),
    ],
    "test_A_SURFACE_NAMING_AN_UNADMITTED_DECLARATION_IS_REFUSED": [
        (f"{PKG}/assembly.py", "    if accounted != set(by_id):", "    if False:"),
    ],
    "test_THE_EXECUTOR_IS_A_REQUIRED_KEYWORD": [
        (f"{PKG}/assembly.py", "        executor: Executor,", "        executor: Executor = None,"),
    ],
    "test_A_CALL_GOES_TO_THE_INJECTED_EXECUTOR_AND_NOWHERE_ELSE": [
        (f"{PKG}/assembly.py",
         "        return await self._executor(name, tool_args, ctx)",
         '        return "ok"'),
    ],
    "test_EVERY_TOOL_IS_BUILT_WITH_ZERO_RETRIES": [
        (f"{PKG}/assembly.py", "                max_retries=0,", "                max_retries=1,"),
    ],
    "test_THE_PARAMETER_SCHEMA_IS_CLOSED_NOT_OPEN": [
        (f"{PKG}/assembly.py",
         '"additionalProperties": False}', '"additionalProperties": True}'),
    ],
    "test_NO_CEILING_CALL_EXISTS_IN_THE_PACKAGE": [
        (f"{PKG}/assembly.py",
         "    return toolset.defer_loading(withheld_ids)",
         "    return toolset.defer_loading(withheld_ids) if defs else toolset.filtered(None)"),
    ],
    "test_THE_GATE_FIRES_ON_A_CEILING_CALL": [
        # 🔴 The first version wrote `= {} or {`, which evaluates to the NON-empty dict - `{}` is
        # falsy, so `or` returns the right operand and nothing changed. Second dud in one round,
        # same class: an edit that looks like a reversion and is not one. Disable the CHECK instead,
        # which is unambiguous.
        (GATE, "            elif isinstance(fn, ast.Attribute) and fn.attr in CEILING_METHODS:",
               "            elif False:"),
    ],
    "test_THE_GATE_IS_SILENT_ON_THE_DEFERRING_CALL": [
        # The other direction: a gate that convicts the deferring API makes the item unshippable
        # while every red-ness case stays green.
        (GATE, '    "filtered": "removes the declaration',
               '    "defer_loading": "x",\n    "filtered": "removes the declaration'),
    ],
    "test_THE_ALLOWANCE_IS_SCOPED_TO_THE_ONE_FILE_THAT_NEEDS_IT": [
        (GATE, '    "pydantic_ai": frozenset({"assembly.py"}),',
               '    "pydantic_ai": frozenset({"assembly.py", "surface.py"}),'),
    ],
    "test_ASSEMBLY_IS_THE_ONLY_FILE_IN_THE_PACKAGE_THAT_IMPORTS_IT": [
        (f"{PKG}/narrowing.py", "from dataclasses import dataclass, field",
         "import pydantic_ai\nfrom dataclasses import dataclass, field"),
    ],
    "test_THE_DEPENDENCY_IS_DECLARED_BY_THE_SERVICE_THAT_IMPORTS_IT": [
        # 🔴 The first version of this row replaced the pin with `# pydantic-ai-slim removed`,
        # which still CONTAINS the string the guard looks for. It read GREEN and would have been
        # filed as "the guard requires nothing" - a reversion that does not restore the defect
        # proves nothing, and the runner caught it on the first pass.
        (REQS, "pydantic-ai-slim>=2.26,<3", "# the pin was deleted"),
    ],
    "test_THE_PACKAGE_STILL_IMPORTS_AT_THE_CONTAINERS_DEPTH": [
        (f"{PKG}/__init__.py", "from .assembly import (\n    TOOLSET_ID,\n",
                               "from .assembly import (\n"),
    ],
    "test_A_STALE_FALSIFIER_ANCHOR_IS_CAUGHT_WITHOUT_RUNNING_A_SUITE": [
        (FALSIFY, "    out: list[str] = []\n    for test, edits in sorted(FALSIFIERS.items()):",
                  "    out: list[str] = []\n    return out\n    for test, edits in sorted(FALSIFIERS.items()):"),
    ],
    "test_THE_SUITE_LIST_IS_EVERY_CP_SUITE_ON_DISK": [
        (FALSIFY, '    "tests/test_cp2_assembly.py",\n', ""),
    ],
    "test_THE_CENSUS_RUNS_EVERY_CP_SUITE_NOT_ONLY_THE_ONE_IT_WAS_BORN_WITH": [
        # The state the census was in until CP-2.1: one suite, typed out.
        #
        # 🔴 **THE FIRST VERSION OF THIS ROW ANCHORED ON A LINE I HAD ALREADY REPLACED**, and the
        # runner refused to apply it — `ANCHOR STALE … 0 occurrences (want 1)`. Third dud falsifier
        # in this session and the only one caught by REFUSAL rather than by a green result, which
        # is the stricter of the two failures: a stale anchor cannot silently certify anything.
        (CENSUS, '                out.append(f"tests/{p.name}")',
                 '                out.append("tests/test_cp1_membrane.py")'),
    ],
    "test_THE_NAMED_RESIDUAL_IS_STILL_NAMED": [
        (f"{PKG}/assembly.py", "discoverable **by name tokens only**", "discoverable"),
    ],

    # ── CP-2.2 · the widening rule (§4.3) ────────────────────────────────────────────────────
    #
    # `_NO_WIDENING` is the state the runtime was in before this item: the pipeline decides, and a
    # plan step that names a budget-dropped declaration gets prose instead of a tool call. It is
    # the exact configuration the `co_write` incident ran in.
    "test_A_REQUIRED_DECLARATION_SURVIVES_A_STAGE_THAT_REMOVED_IT": [
        (f"{PKG}/surface.py", "        if required:\n            by_id =",
                              "        if False:\n            by_id ="),
    ],
    "test_A_REQUIRED_DECLARATION_SURVIVES_A_RANK_DEPENDENT_CUT_TOO": [
        (f"{PKG}/surface.py", "        if required:\n            by_id =",
                              "        if False:\n            by_id ="),
    ],
    "test_THE_WIDENED_DECLARATION_REACHES_THE_TOOLSET_AS_ADVERTISED": [
        (f"{PKG}/surface.py", "        if required:\n            by_id =",
                              "        if False:\n            by_id ="),
    ],
    "test_THE_NARROWING_RECORD_SURVIVES_THE_WIDENING": [
        # The shorter implementation: drop the narrowing and let conservation rebalance. It works,
        # and it destroys the record of the disagreement that is the whole point of the event.
        (f"{PKG}/narrowing.py",
         "        self.widenings.append(\n"
         "            Widening(declaration_id, reason, pass_number, over_stage, over_reason))",
         "        self.widenings.append(\n"
         "            Widening(declaration_id, reason, pass_number, over_stage, over_reason))\n"
         "        self.entries[:] = [e for e in self.entries\n"
         "                           if not (e.declaration_id == declaration_id\n"
         "                                   and e.pass_number == pass_number)]"),
    ],
    "test_THE_WIDENING_RECORD_NAMES_WHAT_IT_OVERRULED": [
        (f"{PKG}/narrowing.py",
         '            "over": {"stage": self.over_stage, "reason": self.over_reason},\n', ""),
    ],
    "test_CONSERVATION_STILL_HOLDS_WITH_A_WIDENING_IN_PLAY": [
        # Restore the declaration to `kept` and leave it in `withheld` too - counted on both sides.
        (f"{PKG}/surface.py",
         "                if e.pass_number == pass_number and e.declaration_id not in widened]",
         "                if e.pass_number == pass_number]"),
    ],
    "test_A_REQUIRED_DECLARATION_THE_MANIFEST_DOES_NOT_ADMIT_IS_REFUSED": [
        (f"{PKG}/surface.py", "        if unadmitted:", "        if False:"),
    ],
    "test_THE_REFUSAL_IS_ITS_OWN_CLASS_NOT_UNRESOLVED_REFERENCE": [
        (f"{PKG}/contract.py", "class RequirementNotAdmitted(UntrustedRow):",
                               "class RequirementNotAdmitted(Exception):"),
    ],
    "test_A_REQUIRED_NAME_IS_BOUNDED_LIKE_EVERY_OTHER_OPERAND": [
        # 🔴 Note what this row proves and what it does NOT. Without the bound the assembly still
        # raises - `RequirementNotAdmitted` is a `ValueError` - so a guard asserting only the TYPE
        # stays green. The falsifier reds it because the guard matches the MESSAGE, which is the
        # correction this row is the record of.
        (f"{PKG}/surface.py", '            _plain(name, str, "required declaration")',
                              "            pass"),
    ],
    "test_AN_EMPTY_REQUIREMENT_CHANGES_NOTHING": [
        # The `tool_names=None` trap from CP-2.1, one layer over: an empty obligation read as
        # "everything is required" widens the entire surface while every count still balances.
        (f"{PKG}/surface.py", "        required = list(required)",
                              '        required = list(required) or [r["id"] for r in self._rows]'),
    ],
    "test_THE_REQUIREMENT_IS_MATERIALISED_BEFORE_IT_IS_CHECKED": [
        (f"{PKG}/surface.py", "        required = list(required)", "        required = required"),
    ],
}

#: Guards whose falsifier is a DECISION not to write one, each with a stated reason.
#:
#: A row here is a claim that the guard cannot be falsified by an edit to the tree — not that nobody
#: got round to it. That is what `contracts/agentruntime-falsification-unproven.txt` is for, and the
#: difference between the two files is the difference between a decision and a backlog.
UNFALSIFIED: dict[str, str] = {}

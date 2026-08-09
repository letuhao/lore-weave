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
GATECACHE = "scripts/agentruntime_gatecache.py"
REQS = f"{CS}/requirements.txt"

#: `{test name: [(file, old, new), ...]}` — apply every mutation, then that test must RED.
FALSIFIERS: dict[str, list[tuple[str, str, str]]] = {
    # ── CP-3 · the plan ─────────────────────────────────────────────────────────────────────
    # The load-bearing one. Degrading to "ask the model for it" reintroduces the 61.8% failure --
    # silently, and only where the carrier has already failed.
    "test_A_MISSING_VALUE_IS_A_REFUSAL_NOT_A_FALLBACK_TO_ASKING_THE_MODEL": [
        (f"{PKG}/plan.py",
         "        if b.from_emit not in produced:",
         "        if False and b.from_emit not in produced:"),
    ],
    # 0.8: hashing the whole spec instead of the gated steps invalidates an approval on ANY edit,
    # which trains a user to re-approve reflexively.
    "test_AN_UNGATED_EDIT_DOES_NOT_INVALIDATE_AN_APPROVAL": [
        (f"{PKG}/plan.py",
         "            [i, _step_payload(s)] for i, s in enumerate(self.steps) if s.gated",
         "            [i, _step_payload(s)] for i, s in enumerate(self.steps)"),
    ],
    # 6.2: a binding checked at runtime has a failure mode of ALLOW.
    "test_A_BINDING_NOBODY_EMITS_IS_A_GENERATION_ERROR_NOT_A_RUNTIME_ONE": [
        (f"{PKG}/plan.py",
         "        check_bindings(self.steps)",
         "        pass  # bindings unchecked"),
    ],
    # 3.6: an end that names nobody is exits #2 and #4 restored.
    "test_AN_END_THAT_IS_NOT_DONE_WHEN_MUST_NAME_SOMEONE": [
        (f"{PKG}/plan.py",
         '        if self.scope != "done_when" and not self.hand_to_human:',
         '        if False and not self.hand_to_human:'),
    ],
    # C-13: re-running a step that committed an effect duplicates it.
    "test_A_STEP_THAT_COMMITTED_AN_EFFECT_IS_NOT_AUTO_RE_RUNNABLE": [
        (f"{PKG}/plan.py",
         "    return not any(e.step_index == step_index for e in state.committed_effects())",
         "    return True"),
    ],
    # 3.3 obligation 4: an identifier that gets abridged is the 61.8% failure one step earlier.
    "test_AN_IDENTIFIER_IS_NEVER_COMPRESSED": [
        (f"{PKG}/planproject.py",
         '            lines.append(f"      {name} = {value!r}")',
         '            lines.append(f"      {name} = {str(value)[:8]!r}")'),
    ],
    # ── CP-4 · the declaration producer ─────────────────────────────────────────────────────
    # One edit, two guards. `settings_*` is served by provider-registry-service, and the obvious
    # derivation — service = f"{prefix}-service" — is wrong exactly there. Both were driven red by
    # this substitution before either was committed.
    "test_THE_CASE_A_PREFIX_GUESS_GETS_WRONG": [
        (f"{PKG}/derive.py",
         '("settings", "provider-registry-service", ("settings_", "web_")),',
         '("settings", "settings-service", ("settings_", "web_")),'),
    ],
    "test_EVERY_DERIVED_SOURCE_PATH_IS_A_REAL_DIRECTORY": [
        (f"{PKG}/derive.py",
         '("settings", "provider-registry-service", ("settings_", "web_")),',
         '("settings", "settings-service", ("settings_", "web_")),'),
    ],
    # 4.c — §0.14.1a rule 2: a missing ranking field is a REJECTION, never a fallback. Disabling
    # the clause lets a half-ranked row through, which is how arm E was arrived at by default.
    "test_ALL_THREE_OR_NONE_A_HALF_RANKED_ROW_IS_REFUSED": [
        (f"{PKG}/contract.py",
         "    if present and present != FACET_FIELDS:",
         "    if False and present != FACET_FIELDS:"),
    ],
    # The writer must COMPUTE the rank. Dropping the merge leaves rows the ranking cannot order.
    "test_A_ROW_BUILT_FROM_A_DEFINITION_CARRIES_ALL_THREE": [
        (f"{PKG}/manifest.py",
         "        row.update(facets_for(tool_def))",
         "        pass  # facets dropped"),
    ],
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
         'if type(d.id) is not str or not _ID_RE.match(d.id or ""):',
         'if not isinstance(d.id, str) or not _ID_RE.match(d.id or ""):'),
        (f"{PKG}/contract.py",
         'if type(m) is not str or not _ID_RE.match(m or ""):',
         'if not isinstance(m, str) or not _ID_RE.match(m or ""):'),
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
        (T1, 'assert " ".join(r.split()) in ALLOWED, (', 'assert "||" not in r, ('),
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
         "    defs = offered_defs + withheld_defs",
         "    defs = offered_defs"),
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
         "    defs = offered_defs + withheld_defs",
         "    defs = offered_defs"),
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
         "        [_tool_def(by_id[name], excluded_by=excluded_by.get(name)) for name in offered],",
         "        [_tool_def(by_id[name], excluded_by=excluded_by.get(name) or {}) for name in offered],"),
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

    # ── CP-2.10 · relevance comes from its own scoring stage ──────────────────────────────────
    "test_A_PIPELINE_RANKS_BY_THE_RELEVANCE_ITS_OWN_STAGE_PRODUCED": [
        (f"{PKG}/surface.py", "        return [{**r, self.field: by_id[r['id']]} for r in rows]"
                              .replace("'", '"'),
                              "        return rows"),
    ],
    "test_A_HAND_TYPED_RELEVANCE_ON_DISK_IS_STILL_REFUSED": [
        # The field coming back is the whole forgery: a hand-typed 9999 selected which single
        # declaration the model saw.
        (f"{PKG}/contract.py", '    "members": (list, tuple),',
                               '    "members": (list, tuple),\n    "relevance": (int,),'),
    ],
    "test_RANKING_ON_RELEVANCE_WITH_NO_PRODUCER_RAISES": [
        (f"{PKG}/surface.py", "                if field not in r:", "                if False:"),
    ],
    "test_A_PARTIAL_SCORE_SET_IS_A_REJECTION_NOT_A_ZERO": [
        # The zero-fill: ranking a declaration last because nobody scored it.
        (f"{PKG}/surface.py", "        unscored = sorted(r[\"id\"] for r in rows if r[\"id\"] not in by_id)",
                              "        unscored = []\n"
                              "        by_id = {r['id']: by_id.get(r['id'], 0) for r in rows}"),
    ],
    "test_A_SCORE_FOR_A_DECLARATION_THIS_PASS_DOES_NOT_CARRY_IS_REFUSED": [
        (f"{PKG}/surface.py",
         '        absent_here = sorted(set(by_id) - {r["id"] for r in rows})',
         "        absent_here = []"),
    ],
    "test_A_SCORE_IS_A_PLAIN_INT": [
        (f"{PKG}/surface.py", "            if type(value) is not int:",
                              "            if not isinstance(value, int):"),
    ],
    # Both census-found: they shipped with nothing checking them.
    "test_THE_SCORE_SET_IS_A_TUPLE_NOT_A_LAZY_OR_MUTABLE_CONTAINER": [
        (f"{PKG}/surface.py", "        if type(self.scores) is not tuple:", "        if False:"),
    ],
    "test_A_SCORE_ENTRY_IS_AN_ID_AND_A_SCORE_AND_NOTHING_ELSE": [
        # Anchored with its own line ending, because `OrderBy` carries an identical pair check and
        # the stale-anchor gate reported the ambiguity in one second the first time.
        (f"{PKG}/surface.py",
         '            if type(pair) is not tuple or len(pair) != 2:\n'
         '                raise ValueError(f"Score.scores holds {pair!r}, which is not an (id, score) pair")',
         '            if False:\n'
         '                raise ValueError(f"Score.scores holds {pair!r}, which is not an (id, score) pair")'),
    ],
    "test_TWO_SCORES_FOR_ONE_DECLARATION_IS_REFUSED": [
        (f"{PKG}/surface.py", "            if name in seen:", "            if False:"),
    ],
    "test_THE_SCORES_ARE_DATA_NOT_A_CALLABLE": [
        (f"{PKG}/surface.py", "    scores: tuple[tuple[str, int], ...]",
                              "    scores: Callable"),
    ],
    "test_THE_SCORING_STAGE_REMOVES_NOTHING__it_is_a_producer": [
        (f"{PKG}/surface.py", "        return [{**r, self.field: by_id[r['id']]} for r in rows]"
                              .replace("'", '"'),
                              "        return [{**r, self.field: by_id[r['id']]} for r in rows][:1]"
                              .replace("['id']", '["id"]')),
    ],
    "test_THE_BUDGET_ARRIVES_AS_A_PARAMETER_AND_NOTHING_READS_THE_ENVIRONMENT": [
        (f"{PKG}/canon.py", "from __future__ import annotations",
                            "from __future__ import annotations\n\nimport os  # noqa: F401"),
    ],

    # ── CP-2.8 · the arm label at a structural chokepoint ─────────────────────────────────────
    #
    # `INSTR` is the legacy instrument, which is also CP-2's CONTROL arm. Every falsifier below
    # restores the state this row repaired: a label a caller passes, defaulting to a constant.
    "test_THE_LABEL_IS_NOT_A_PARAMETER_A_CALLER_CAN_PASS_AT_ALL": [
        (f"{CS}/app/services/instrument.py", "    declaration: str | None = None,\n) -> dict:",
         "    declaration: str | None = None,\n    runtime_variant: str = RUNTIME_LEGACY,\n"
         ") -> dict:"),
    ],
    "test_ON_THE_NEW_ARM_EVERY_STAMP_SAYS_AGENTRUNTIME": [
        (f"{CS}/app/services/instrument.py",
         '    chunk["runtime_variant"] = current_runtime_variant()',
         '    chunk["runtime_variant"] = RUNTIME_LEGACY'),
    ],
    "test_THE_CONTROL_ARM_IS_BYTE_IDENTICAL__the_reason_this_row_could_be_built_at_all": [
        # The other direction: a derivation that gets the CONTROL wrong moves CP-2's control group,
        # which is the one outcome CP-1.9 spent an item forbidding.
        (f"{CS}/app/services/instrument.py",
         "    return RUNTIME_AGENTRUNTIME if settings.agentruntime_arm else RUNTIME_LEGACY",
         "    return RUNTIME_AGENTRUNTIME"),
    ],
    "test_THE_BACKFILL_PATH_DERIVES_IT_TOO__not_only_the_stamping_one": [
        # The pair repaired at ONE end - thirteen instances in this run.
        (f"{CS}/app/services/instrument.py",
         '    chunk.setdefault("runtime_variant", current_runtime_variant())',
         '    chunk.setdefault("runtime_variant", RUNTIME_LEGACY)'),
    ],
    "test_NO_SITE_IN_THE_SERVICE_STILL_WRITES_THE_CONSTANT": [
        (f"{CS}/app/services/instrument.py",
         '    chunk["runtime_variant"] = current_runtime_variant()',
         '    chunk["runtime_variant"] = RUNTIME_LEGACY'),
    ],

    # ── CP-2.9 · prompt_hash ──────────────────────────────────────────────────────────────────
    "test_AN_EDITED_PROMPT_PRODUCES_A_DIFFERENT_DIGEST": [
        (f"{PKG}/observation.py", "    return digest(prompt)", '    return "constant"'),
    ],
    "test_THE_SAME_PROMPT_PRODUCES_THE_SAME_DIGEST": [
        # A digest that is not a function of its input answers no question at all.
        # 🔴 The first version appended `str(len(repr(object())))` - whose LENGTH is CONSTANT
        # across calls, so the digest never varied and the row read GREEN. The SECOND attempt used
        # `id(object())`, which is worse: CPython reuses the freed address, so it returns the
        # SAME value twice in a row. Both are the same mistake - reaching for something
        # ASSUMED to vary. A counter varies because it is made to.
        (f"{PKG}/observation.py", "    return digest(prompt)",
         '    prompt_hash.__dict__["n"] = prompt_hash.__dict__.get("n", 0) + 1\n'
         '    return digest(prompt + str(prompt_hash.__dict__["n"]))'),
    ],
    "test_NFD_AND_NFC_OF_ONE_PROMPT_ARE_ONE_DIGEST": [
        # 🔴 Anchored on `canon._norm`, because that is where the normalisation LIVES. The first
        # version removed an `nfc(...)` call in `prompt_hash` and read GREEN - `digest` already
        # normalises, so the removed call was redundant and the docstring calling it load-bearing
        # was false. The runner found the claim, not a reviewer.
        (f"{PKG}/canon.py", "        return nfc(value)", "        return value"),
    ],
    "test_THE_THREE_RED_TEAM_KILLED_ARE_STILL_ABSENT": [
        (f"{PKG}/observation.py", "    * **`code_revision`**", "    * **`code-revision`**"),
    ],

    # ── CP-2.7 · THE ROUTE ────────────────────────────────────────────────────────────────────
    "test_THE_CONTROL_ARM_IS_UNTOUCHED_WHEN_THE_FLAG_IS_OFF": [
        # The route taken unconditionally: CP-2's control group stops serving the legacy
        # catalogue, and the comparison is invalid before it starts (CP-1.9's argument).
        (f"{CS}/app/services/stream_service.py",
         "    if settings.agentruntime_arm:", "    if True:"),
    ],
    "test_ON_THE_NEW_ARM_AN_EMPTY_MANIFEST_ADVERTISES_NOTHING_AT_ALL": [
        (f"{CS}/app/services/stream_service.py",
         "    if settings.agentruntime_arm:", "    if False:"),
    ],
    "test_NO_LEGACY_DECLARATION_SURVIVES_THE_ROUTE__item_B": [
        (f"{CS}/app/services/stream_service.py",
         "    if settings.agentruntime_arm:", "    if False:"),
    ],
    "test_THE_BRANCH_READS_NOTHING_FROM_THE_LEGACY_CATALOG": [
        # The merge that would make item B unmeasurable: one legacy read inside the branch.
        (f"{CS}/app/services/stream_service.py",
         "        payload, _surface = _agentruntime_advertise(_agentruntime_load(), pass_number=1)\n"
         "        return payload",
         "        payload, _surface = _agentruntime_advertise(_agentruntime_load(), pass_number=1)\n"
         "        return payload or list(extra_frontend)"),
    ],
    "test_THE_MODEL_IS_TOLD_WHICH_EMPTINESS_THIS_IS__item_A": [
        # Collapse the two emptinesses - §0.14.3's failure, at the one place they are separated.
        (f"{PKG}/serve.py", "    if not surface.names and not surface.withheld:",
                            "    if False:"),
    ],
    "test_THE_ROUTE_RETURNS_THE_SURFACE_SO_P1_IS_RECORDABLE__items_C_and_D": [
        # Two assemblies instead of one: the payload and the record stop being one computation,
        # which is the eight-frame defect ("the record is built somewhere else from something
        # else") reintroduced at the route.
        (f"{PKG}/serve.py",
         "    return payload_from_defs(offered_defs_for(manifest_doc, surface)), surface",
         "    other = SurfaceAssembler(manifest_doc, log=None).assemble(pass_number=pass_number)\n"
         "    return payload_from_defs(offered_defs_for(manifest_doc, other)), surface"),
    ],
    "test_A_DEFERRED_DECLARATION_IS_NOT_ON_THE_WIRE": [
        (f"{PKG}/assembly.py",
         "    return _defs_for(by_id, tuple(surface.names), tuple(surface.withheld))[0]",
         "    return sum(_defs_for(by_id, tuple(surface.names), tuple(surface.withheld)), [])"),
    ],

    # ── CP-2.7 (part) · M4 — the registration entry point refuses to boot ─────────────────────
    "test_REMOVE_ONE_REQUIRED_CLAUSE_AND_THE_SERVICE_FAILS_TO_START": [
        # The state M4 was in for eleven rounds: nothing refuses, so the service starts with a
        # manifest it cannot serve.
        (f"{PKG}/boot.py", "    except UntrustedRow as exc:", "    except SystemExit as exc:"),
    ],
    "test_A_COMPLETE_MANIFEST_BOOTS": [
        # The other direction: a boot that refuses everything makes the membrane unshippable while
        # every red-ness case above stays green.
        (f"{PKG}/boot.py", "        return load()",
                           "        raise UntrustedRow('nope')\n        return load()"),
    ],
    "test_AN_ABSENT_MANIFEST_IS_A_LEGITIMATE_EMPTY_STATE_NOT_A_REFUSAL": [
        # Confusing "nothing is declared" with "something is wrong" - the two facts this effort
        # keeps separating, collapsed at the boot path.
        (f"{PKG}/boot.py", "        return load()",
                           "        doc = load()\n"
                           "        if not doc['declarations']:\n"
                           "            raise UntrustedRow('empty')\n"
                           "        return doc"),
    ],
    "test_THE_SERVICE_STARTUP_ACTUALLY_CALLS_IT": [
        (f"{CS}/app/main.py", "    from app.agentruntime.boot import boot\n    boot()\n", ""),
    ],
    "test_BOOT_DOES_NOT_REIMPLEMENT_WHAT_VALIDITY_MEANS": [
        (f"{PKG}/boot.py", "        return load()",
                           "        doc = load()\n"
                           "        if len(doc['declarations']) > 99:\n"
                           "            raise ContractViolation('x', 'y', 'z', 'w')\n"
                           "        return doc"),
    ],

    # ── CP-2.5 · P5 on every path, and the guardrail shadow arm ───────────────────────────────
    "test_A_TURN_THAT_CANNOT_ANSWER_ALL_FOUR_FIELDS_PRODUCES_NO_RECORD_AT_ALL": [
        # Give the four fields the plausible defaults. Each one is a CONSTANT at a write boundary,
        # which is P4's violation - and it makes a partial record expressible again.
        (f"{PKG}/observation.py", "    advertised: tuple[dict, ...]\n",
                                  "    advertised: tuple[dict, ...] = ()\n"),
        # Re-anchored at CP-2.6: `source` gained a comment block above it explaining why it is
        # not a parameter, and this anchor spanned the two fields across it. Caught by
        # `stale_anchors()` in one second rather than by a fifteen-minute run -- which is the
        # whole reason that check was promoted into the gate's default mode.
        (f"{PKG}/observation.py", "    withheld: tuple[dict, ...]\n",
                                  "    withheld: tuple[dict, ...] = ()\n"),
        (f"{PKG}/observation.py", "    source: str\n    outcome: str\n",
                                  '    source: str = "tool"\n    outcome: str = "done"\n'),
    ],
    "test_EVERY_PLAUSIBLE_DEFAULT_IS_A_CONSTANT_AT_A_WRITE_BOUNDARY": [
        # Re-anchored at CP-2.6: `source` gained a comment block above it explaining why it is
        # not a parameter, and this anchor spanned the two fields across it. Caught by
        # `stale_anchors()` in one second rather than by a fifteen-minute run -- which is the
        # whole reason that check was promoted into the gate's default mode.
        (f"{PKG}/observation.py", "    withheld: tuple[dict, ...]\n",
                                  "    withheld: tuple[dict, ...] = ()\n"),
        (f"{PKG}/observation.py", "    source: str\n    outcome: str\n",
                                  '    source: str = "tool"\n    outcome: str = "done"\n'),
    ],
    "test_ADVERTISED_IS_PER_PASS__and_a_scalar_would_lose_the_mid_turn_change": [
        # The scalar column: keep only the last pass, which is what a `text[]` would have held.
        (f"{PKG}/observation.py",
         "        advertised=tuple(\n"
         '            {"pass": s.pass_number, "tool_choice": tool_choice, "names": tuple(s.names)}\n'
         "            for s in surfaces\n        ),",
         "        advertised=tuple(\n"
         '            {"pass": s.pass_number, "tool_choice": tool_choice, "names": tuple(s.names)}\n'
         "            for s in surfaces[-1:]\n        ),"),
    ],
    "test_TWO_ENTRIES_FOR_ONE_PASS_IS_REFUSED": [
        (f"{PKG}/observation.py", "            if p in seen:", "            if False:"),
    ],
    # 🔴 The three below exist because the CENSUS found them, not because I wrote guards for them:
    # all three refusals shipped in this item's own module with nothing checking them, and were
    # reported `NEWLY SILENT` on the first run after the module landed.
    "test_AN_ADVERTISED_ENTRY_IS_EXACTLY_THREE_KEYS": [
        (f"{PKG}/observation.py",
         '            if type(entry) is not dict or set(entry) != {"pass", "tool_choice", "names"}:',
         "            if False:"),
    ],
    "test_A_PASS_NUMBER_IS_A_1_BASED_INT": [
        (f"{PKG}/observation.py", "            if type(p) is not int or p < 1:",
                                  "            if False:"),
    ],
    "test_ADVERTISED_NAMES_IS_A_TUPLE_NOT_A_MUTABLE_OR_LAZY_CONTAINER": [
        (f"{PKG}/observation.py", '            if type(entry["names"]) is not tuple:',
                                  "            if False:"),
    ],
    "test_SOURCE_IS_ONE_OF_THREE_AND_NOT_A_FREE_STRING": [
        (f"{PKG}/observation.py",
         "        if type(self.source) is not str or self.source not in SOURCES:",
         "        if False:"),
    ],
    "test_OUTCOME_IS_C14s_TYPED_ENUM_NOT_OK_BOOL": [
        (f"{PKG}/observation.py",
         "        if type(self.outcome) is not str or self.outcome not in OUTCOMES:",
         "        if False:"),
    ],
    "test_THE_RECORD_IS_DERIVED_FROM_THE_SURFACES_NOT_HAND_TYPED": [
        (f"{PKG}/observation.py",
         "        withheld=tuple(record for s in surfaces for record in s.withheld),",
         "        withheld=(),"),
    ],
    "test_THE_WRONG_OBJECT_COUNTER_IS_NOT_A_P5_FIELD": [
        # §0.6: a counter without a detector ships reading zero.
        (f"{PKG}/observation.py", "    source: str\n    outcome: str",
                                  "    source: str\n    outcome: str\n    wrong_object_count: int = 0"),
    ],
    "test_A_GUARDRAIL_THAT_ACTED_CANNOT_BE_CONSTRUCTED": [
        (f"{PKG}/observation.py", "        if self.acted:", "        if False:"),
    ],
    "test_THE_DEFAULT_IS_NOT_ACTING__not_a_flag_someone_must_remember": [
        (f"{PKG}/observation.py", "    acted: bool = False", "    acted: bool = True"),
    ],
    "test_A_FIRE_WITHOUT_DETERMINISTIC_EVIDENCE_IS_REFUSED": [
        (f"{PKG}/observation.py", "        if self.fired and not self.evidence.strip():",
                                  "        if False:"),
    ],
    "test_A_FIRE_WITH_NO_TRANSITION_IS_A_STOP_AND_IS_REFUSED": [
        (f"{PKG}/observation.py", "        if self.fired and not self.transition.strip():",
                                  "        if False:"),
    ],
    "test_A_GUARDRAIL_THAT_DID_NOT_FIRE_NEEDS_NEITHER": [
        # Drop the `fired and` conjunct: every quiet turn is then forced to invent evidence, which
        # is the fabrication these checks exist to prevent.
        (f"{PKG}/observation.py", "        if self.fired and not self.evidence.strip():",
                                  "        if not self.evidence.strip():"),
    ],

    # ── CP-2.4 · withheld is reachable AND distinguishable from never-existed ─────────────────
    "test_A_WITHHELD_DECLARATION_AND_A_NEVER_ADMITTED_ONE_END_DIFFERENTLY": [
        # Drop the withheld ones out of the toolset - `.filtered()` by hand - and the two searches
        # come back identical, which is §0.14.3's failure exactly.
        (f"{PKG}/assembly.py",
         "    defs = offered_defs + withheld_defs",
         "    defs = offered_defs"),
    ],
    "test_THE_MODEL_IS_TOLD_UNPROMPTED_THAT_SOMETHING_WAS_WITHHELD": [
        # The state before this item: reachable, and never mentioned.
        (f"{PKG}/assembly.py", "    n = len(surface.withheld)\n    if not n:",
                               "    n = len(surface.withheld)\n    if True:"),
    ],
    "test_NOTHING_WITHHELD_MEANS_NO_NOTICE_AT_ALL__not_a_notice_saying_zero": [
        (f"{PKG}/assembly.py", "    n = len(surface.withheld)\n    if not n:",
                               "    n = len(surface.withheld)\n    if False:"),
    ],
    "test_THE_NOTICE_COUNTS_AND_DOES_NOT_NAME": [
        (f"{PKG}/assembly.py",
         '        f"operation you need before concluding that no tool provides it."',
         '        f"operation you need before concluding that no tool provides it: "\n'
         '        + ", ".join(w["tool"] for w in surface.withheld)'),
    ],
    "test_THE_NOTICE_SAYS_THEY_EXIST__it_is_the_sentence_the_model_got_wrong": [
        # The hedge that reads as compatible with "does not exist at all".
        (f"{PKG}/assembly.py",
         '        f"{n} declaration{\'s\' if n != 1 else \'\'} that exist and are admitted were not offered on "',
         '        f"{n} tool{\'s\' if n != 1 else \'\'} may not be available on "'),
    ],

    # ── CP-2.3 · deterministic tool ordering ─────────────────────────────────────────────────
    #
    # `NAMES` is the one line, and it has two wrong values rather than one: alphabetical (the
    # state before this item - deterministic, and the rank thrown away) and a set comprehension
    # (the LEGACY state - the rank thrown away AND the order changing every restart).
    "test_THE_SURFACE_IS_IN_THE_PIPELINES_ORDER_NOT_ALPHABETICAL": [
        (f"{PKG}/surface.py", '            names=tuple(r["id"] for r in kept),',
                              '            names=tuple(sorted(r["id"] for r in kept)),'),
    ],
    "test_A_RANK_DEPENDENT_CUT_PRESENTS_ITS_SURVIVORS_IN_RANK_ORDER": [
        (f"{PKG}/surface.py", '            names=tuple(r["id"] for r in kept),',
                              '            names=tuple(sorted(r["id"] for r in kept)),'),
    ],
    "test_WITH_NO_ORDER_BY_THE_ORDER_IS_THE_MANIFESTS_OWN": [
        (f"{PKG}/surface.py", '            names=tuple(r["id"] for r in kept),',
                              '            names=tuple(sorted(r["id"] for r in kept)),'),
    ],
    "test_THE_TOOLSET_PRESENTS_THE_SURFACE_IN_THAT_ORDER": [
        (f"{PKG}/surface.py", '            names=tuple(r["id"] for r in kept),',
                              '            names=tuple(sorted(r["id"] for r in kept)),'),
    ],
    "test_THE_ORDER_IS_IDENTICAL_IN_A_FRESH_INTERPRETER_UNDER_FOUR_HASH_SEEDS": [
        # The legacy shape, transplanted: a set of strings, iterated.
        (f"{PKG}/surface.py", '            names=tuple(r["id"] for r in kept),',
                              '            names=tuple({r["id"] for r in kept}),'),
    ],
    "test_THE_MANIFEST_IS_WRITTEN_IN_A_CANONICAL_ORDER__which_is_what_makes_that_stable": [
        (f"{PKG}/manifest.py", '        "declarations": sorted(rows, key=lambda r: r["id"]),',
                               '        "declarations": rows,'),
    ],
    "test_THE_HASH_SEED_HARNESS_CAN_ACTUALLY_DETECT_NON_DETERMINISM": [
        # Pin the seed and the harness stops being able to see anything - which is precisely the
        # state in which the guard above passes while measuring nothing.
        (T2, '        env = {**os.environ, "PYTHONHASHSEED": seed}',
             '        env = {**os.environ, "PYTHONHASHSEED": "0"}'),
    ],

    # ── CP-2.6 · `source` is a property of WHERE THE CODE IS ────────────────────────────────
    #
    # Every mutation below restores CP-0.3's shape rather than merely breaking a guard: a source
    # that is a VALUE somebody supplies, chooses, or looks up. The behaviour is often unchanged --
    # `SOURCES[2]` is still `"meta"` -- and that is the point. The defect this row closes was never
    # a wrong string; it was a right string arrived at by inference.
    "test_NO_PUBLIC_ENTRY_POINT_ACCEPTS_A_source_ARGUMENT": [
        (f"{PKG}/observation.py",
         'def observe_dispatch(\n    surfaces: Sequence,\n    *,\n    outcome: str,',
         'def observe_dispatch(\n    surfaces: Sequence,\n    *,\n    source: str = "tool",\n'
         '    outcome: str,'),
    ],
    "test_THE_ONE_FUNCTION_THAT_TAKES_source_IS_PRIVATE_AND_UNEXPORTED": [
        (f"{PKG}/observation.py",
         '__all__ = ["ERROR_CLASSES", "FAILED",',
         '__all__ = ["_observe", "ERROR_CLASSES", "FAILED",'),
    ],
    "test_EACH_ENTRY_POINT_IS_PINNED_TO_EXACTLY_ONE_LITERAL": [
        # Behaviour identical, structure inverted: the origin is now READ OUT OF THE ENUM instead
        # of stated. This is the falsifier that proves the guard is about location, not value.
        (f"{PKG}/observation.py",
         'surfaces, source="meta", outcome=outcome, error_class=error_class,',
         'surfaces, source=SOURCES[2], outcome=outcome, error_class=error_class,'),
    ],
    "test_THE_THREE_LITERALS_COVER_THE_ENUM_AND_NOTHING_ELSE": [
        (f"{PKG}/observation.py",
         'SOURCES = ("tool", "breaker", "meta")',
         'SOURCES = ("tool", "breaker", "meta", "cache")'),
    ],
    "test_NO_OTHER_MODULE_IN_THE_PACKAGE_WRITES_A_source": [
        (f"{PKG}/serve.py",
         "from __future__ import annotations",
         'from __future__ import annotations\n_SECOND_WRITER = dict(source="breaker")'),
    ],
    "test_AN_ENTRY_POINT_IS_NEVER_USED_AS_A_VALUE": [
        # CP-0.3's lookup, restored one frame up and inside the module that forbids it.
        (f"{PKG}/observation.py",
         '__all__ = ["ERROR_CLASSES", "FAILED",',
         '_BY_NAME = {"tool": observe_dispatch, "breaker": observe_breaker, "meta": observe_meta}\n'
         '\n\n__all__ = ["ERROR_CLASSES", "FAILED",'),
    ],
    "test_NOTHING_OUTSIDE_observation_PY_CONSTRUCTS_AN_Observation": [
        # `source=_s` deliberately, not a literal: this must red the CONSTRUCTION guard on its own
        # merits rather than by tripping the literal guard next door.
        (f"{PKG}/narrowing.py",
         "from __future__ import annotations",
         "from __future__ import annotations\n\n\ndef _forge(_s):\n"
         "    return Observation(advertised=(), withheld=(), source=_s, outcome='done')"),
    ],
    "test_THE_PACKAGE_HAS_NO_source_inferred_FLAG": [
        (f"{PKG}/observation.py",
         'SOURCES = ("tool", "breaker", "meta")',
         'SOURCES = ("tool", "breaker", "meta")\nSOURCE_INFERRED_KEY = "source_inferred"'),
    ],
    "test_THE_CONTROL_GROUP_KEEPS_ITS_INFERENCE_FLAG": [
        # §7, from the other direction: a tidy-up that removes the control arm's self-reporting.
        (f"{CS}/app/services/instrument.py",
         'chunk["source_inferred"] = True',
         'chunk["classified"] = True'),
    ],

    # ── CP-2.6 · C-7's error class is an ENUM, not a reading ─────────────────────────────────
    "test_THE_FOUR_CLASSES_ARE_THE_SPECS_FOUR_NOT_A_LIST_I_TYPED": [
        (f"{PKG}/observation.py", '    "terminal_budget",\n', ""),
    ],
    "test_THE_ANTI_ORACLE_CLASS_IS_PRESENT_BY_THE_NAME_THE_RULING_GIVES_IT": [
        # The 239 rows behind the anti-oracle get forced into another class again -- the exact
        # hiding V-METRIC's overturn condition names.
        (f"{PKG}/observation.py", '"unresolved_or_forbidden",', '"unresolved",'),
    ],
    "test_THE_UNCLASSIFIABLE_DEFAULT_FAILS_CLOSED": [
        (f"{PKG}/observation.py",
         'UNCLASSIFIABLE = "terminal_permanent"',
         'UNCLASSIFIABLE = "retryable_transient"'),
    ],
    "test_A_FAILED_RECORD_CARRIES_ANY_CLASS_IN_THE_ENUM": [
        # A narrowed vocabulary: two legal classes become unrecordable. Sliced at 3 so that
        # `UNCLASSIFIABLE` stays admissible and this reds on its own claim.
        (f"{PKG}/observation.py",
         'if type(self.error_class) is not str or self.error_class not in ERROR_CLASSES:',
         'if type(self.error_class) is not str or self.error_class not in ERROR_CLASSES[:3]:'),
    ],
    "test_A_FAILED_RECORD_WITHOUT_A_CLASS_IS_NOT_A_RECORD": [
        # Totality removed: a failure may again arrive with nothing but its prose.
        (f"{PKG}/observation.py",
         'if self.outcome == FAILED:\n',
         'if self.outcome == FAILED and self.error_class is not None:\n'),
    ],
    "test_A_CLASS_OUTSIDE_THE_ENUM_IS_REFUSED_ON_A_FAILURE": [
        (f"{PKG}/observation.py",
         'if type(self.error_class) is not str or self.error_class not in ERROR_CLASSES:',
         'if False:'),
    ],
    "test_A_CLASS_ON_ANY_OTHER_OUTCOME_IS_A_CATEGORY_ERROR": [
        # Disjointness removed: `partial` may carry a retryability again, and the column starts
        # answering a question that has no answer.
        (f"{PKG}/observation.py",
         'elif self.error_class is not None:',
         'elif False:'),
    ],
    "test_EVERY_NON_FAILED_OUTCOME_STILL_RECORDS_WITH_NO_CLASS": [
        # The over-correction: disjointness enforced so hard that ordinary outcomes stop recording.
        (f"{PKG}/observation.py",
         'elif self.error_class is not None:',
         'elif self.error_class is None:'),
    ],
    "test_THE_REFINEMENT_HOLDS_AT_ALL_THREE_ORIGINS": [
        # Breaker failures exempted -- and breakers are 58-66% of what the model sees as an error,
        # so the enum would cover the minority and the aggregate stay a reading.
        (f"{PKG}/observation.py",
         'if self.outcome == FAILED:\n',
         'if self.outcome == FAILED and self.source != "breaker":\n'),
    ],
    "test_NO_error_class_IN_THE_PACKAGE_IS_COMPUTED": [
        # The quiet undo: a helper that maps prose to a class. Well-typed, enum-valued, and every
        # other guard in this file stays green.
        (f"{PKG}/observation.py",
         'surfaces, source="breaker", outcome=outcome, error_class=error_class,',
         'surfaces, source="breaker", outcome=outcome,\n'
         '        error_class=error_class or ("terminal_permanent" if outcome == FAILED else None),'),
    ],
    "test_THE_LIMIT_OF_THIS_ROW_IS_WRITTEN_DOWN_WHERE_THE_ENUM_IS": [
        (f"{PKG}/observation.py",
         "class 3 is **scoreable in the NEW ARM ONLY**",
         "class 3 is now measurable"),
    ],

    # -- F-50 -- the early-return read of a later local -------------------------------------
    # The mutation restores F-50 IN FULL: un-hoist, and put the assignments back below.
    # Deleting them alone would not do -- a name bound nowhere reads as a global and the
    # static check skips it. The defect is the ORDER, so the falsifier must restore order.
    "test_NO_EARLY_RETURN_BRANCH_READS_A_LOCAL_BOUND_BELOW_IT": [
        (f"{CS}/app/services/stream_service.py",
         "    _advertised_json = json.dumps(advertised_tools) if advertised_tools else None\n    _withheld_json = json.dumps(withheld_tools) if withheld_tools else None\n    if not content and not reasoning and not tool_calls_history:",
         "    if not content and not reasoning and not tool_calls_history:"),
        (f"{CS}/app/services/stream_service.py",
         "    # `_advertised_json` / `_withheld_json` are bound at the top of the function — see F-50.\n",
         "    _advertised_json = json.dumps(advertised_tools) if advertised_tools else None\n    _withheld_json = json.dumps(withheld_tools) if withheld_tools else None\n"),
    ],
    "test_AN_EMPTY_TERMINAL_TURN_ISSUES_THE_ORPHAN_UPDATE": [
        (f"{CS}/app/services/stream_service.py",
         "    _advertised_json = json.dumps(advertised_tools) if advertised_tools else None\n    _withheld_json = json.dumps(withheld_tools) if withheld_tools else None\n    if not content and not reasoning and not tool_calls_history:",
         "    if not content and not reasoning and not tool_calls_history:"),
        (f"{CS}/app/services/stream_service.py",
         "    # `_advertised_json` / `_withheld_json` are bound at the top of the function — see F-50.\n",
         "    _advertised_json = json.dumps(advertised_tools) if advertised_tools else None\n    _withheld_json = json.dumps(withheld_tools) if withheld_tools else None\n"),
    ],
    "test_THE_CHECK_FINDS_F50_WHEN_IT_IS_PUT_BACK": [
        # Blind the branch finder: the control must notice it can no longer convict.
        (T0, "for i, stmt in enumerate(fn.body[:-1]):",
             "for i, stmt in enumerate(fn.body[:0]):"),
    ],

    # -- F-50 second layer -- EXCLUDED exists only in an upsert ------------------------------
    "test_THE_EXCLUDED_FORM_APPEARS_ONLY_INSIDE_AN_ON_CONFLICT_STATEMENT": [
        # The shipped statement, restored exactly: the default form in a plain UPDATE.
        (f"{CS}/app/services/stream_service.py",
         "instrument.segment_merge_sql('withheld_tools', incoming='$3::jsonb')",
         "instrument.segment_merge_sql('withheld_tools')"),
    ],
    "test_A_CALLER_SUPPLIED_EXPRESSION_IS_REFUSED": [
        (f"{CS}/app/services/instrument.py",
         "elif not _INCOMING_PLACEHOLDER.match(incoming):",
         "elif False:"),
    ],
    "test_THE_TWO_FORMS_DIFFER_ONLY_IN_THE_INCOMING_TERM": [
        # Drift: one branch keeps EXCLUDED while the rest is parameterised -- which is what a
        # second hand-written copy of this expression would look like after one edit.
        (f"{CS}/app/services/instrument.py",
         "WHEN {incoming} IS NULL THEN chat_messages.{column}",
         "WHEN EXCLUDED.{column} IS NULL THEN chat_messages.{column}"),
    ],

    # -- the gate verdict cache: an answer is about ONE tree ---------------------------------
    "test_THE_DIGEST_CANNOT_BE_COMPUTED_AT_THE_MOMENT_OF_RECORDING": [
        (GATECACHE, "def store(path: pathlib.Path, payload: dict, *, digest: str) -> None:",
                    'def store(path: pathlib.Path, payload: dict, *, digest: str = "") -> None:'),
    ],
    "test_NO_GATE_COMPUTES_ITS_DIGEST_AT_THE_STORE_CALL": [
        # Type-correct, signature-satisfying, and the whole defect back: the digest now describes
        # the tree as it is when the answer is WRITTEN, not when it was measured.
        (CENSUS, "digest=started_on)", "digest=_gatecache.tree_digest())"),
    ],
    "test_BOTH_GATES_MIRROR_THE_SAME_FILE_SET": [
        (FALSIFY, "for pref in _gatecache.MIRROR_PREFIXES)", "for pref in ())"),
    ],
    "test_A_VERDICT_FILE_IS_NOT_PART_OF_ITS_OWN_KEY": [
        (GATECACHE, 'VERDICT_SUFFIX = "-verdict.json"', 'VERDICT_SUFFIX = "-never-matches.json"'),
    ],

    # -- CP-1 reconciliation: 1.8a's guard had the shape of 1.8a's defect --------------------
    "test_THE_OPERAND_SET_COMES_FROM_THE_DATACLASS_NOT_FROM_A_LIST_OF_CASES": [
        # Unbind one operand. `cost_field` is a `row.get()` key, so a forged `__hash__`/`__eq__`
        # chooses which column the budget accumulates -- the A-3 defect, restored on one field.
        (f"{PKG}/surface.py", '_plain(self.cost_field, str, "cost_field")',
                              'pass  # unbound'),
    ],
}

#: Guards whose falsifier is a DECISION not to write one, each with a stated reason.
#:
#: A row here is a claim that the guard cannot be falsified by an edit to the tree — not that nobody
#: got round to it. That is what `contracts/agentruntime-falsification-unproven.txt` is for, and the
#: difference between the two files is the difference between a decision and a backlog.
UNFALSIFIED: dict[str, str] = {}

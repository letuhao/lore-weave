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
CENSUS = "scripts/agentruntime-census.py"

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
}

#: Guards whose falsifier is a DECISION not to write one, each with a stated reason.
#:
#: A row here is a claim that the guard cannot be falsified by an edit to the tree — not that nobody
#: got round to it. That is what `contracts/agentruntime-falsification-unproven.txt` is for, and the
#: difference between the two files is the difference between a decision and a backlog.
UNFALSIFIED: dict[str, str] = {}

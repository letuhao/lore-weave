#!/usr/bin/env python3
"""authorable-surface-gate — the enumeration of what an author may declare must
match the types that actually accept it.

  RULE  `contracts/ruleset/authorable-surface.v1.yaml` lists every key of every
        patch type reachable from `RulesetPatch`, and lists nothing else.

WHY THIS EXISTS
---------------
`G-S5a` of the BOOK -> REALITY pipeline index asked for a derived statement of
"what an author may say". The answer already exists in executable form —
`RulesetPatch` is `deny_unknown_fields`, so the loader can already say yes or no
to any key — but it had never been written down, and a manifest builder cannot
be specified against a shape nobody has stated.

Writing it down is the easy half. Keeping it true is this file. An enumeration of
a code-derived set is a LIST THAT MUST CONTAIN EVERY MEMBER OF A SET THE COMPILER
KNOWS, which is precisely the drift `closed-set-gate` exists to prevent:

    "Rust forces you to HANDLE every variant (a wildcard-free match) but cannot
     force an ARRAY to CONTAIN every variant, so the list drifts silently."

Add a field to `VerbPatch` and every test still passes, the loader happily
accepts the new key, and the document that a manifest builder is being written
against is quietly wrong.

SCOPE IS A PREDICATE, NOT A LIST
--------------------------------
The types checked are the TRANSITIVE CLOSURE of `RulesetPatch`'s field types,
computed here rather than enumerated. This matters more than it looks: an
enumerated list of patch structs would be DEFAULT-UNCOVERED (`NV-3`) the day
someone adds a nested table, which is the same shape as an enumerated file list.
Reaching the closure instead means a new nested type is in scope the moment a
field points at it.

It also excludes the right things for the right reason. `ruleset-loader` holds
other `Deserialize` structs — `labels.rs` (the unhashed label sidecar),
`binding.rs` — and they are NOT the authored ruleset surface. A predicate of
"any Deserialize struct in this crate" would drag them in; the closure does not,
because nothing in `RulesetPatch` points at them.

THE OTHER HALF
--------------
This is the SOURCE check. `crates/ruleset-loader/tests/authorable_surface.rs` is
the BEHAVIOURAL one: the real loader must accept every key listed here and refuse
one that is not. Neither alone suffices — this file would pass on a key the
loader rejects for some other reason, and the behavioural test cannot notice a
field nobody enumerated.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "crates" / "ruleset-loader" / "src"
CONTRACT = REPO / "contracts" / "ruleset" / "authorable-surface.v1.yaml"
DEFAULTS = REPO / "crates" / "ruleset-loader" / "artifacts" / "engine_default.toml"

#: Where the closure starts. The ONE name this gate hardcodes, because it is the
#: root of the authored file — `parse.rs` deserializes a layer into exactly this.
ROOT = "RulesetPatch"

#: A walk that reaches nothing and a clean tree are byte-identical, including the
#: exit code. Measured 8 types / 72 keys; the floors sit below that and above
#: zero so they are live and unsaturated, and they are deliberately NOT set at
#: the measured value — a floor AT the subject count makes every arm above it
#: unreachable (`BDR-82`).
MIN_TYPES = 5
MIN_KEYS = 40

_STRUCT = re.compile(r"^pub struct (\w+)\s*\{", re.MULTILINE)
_FIELD = re.compile(r"^\s{4}pub (\w+)\s*:\s*(.+?),\s*$", re.MULTILINE)
_RENAME = re.compile(r'#\[serde\(rename\s*=\s*"([^"]+)"')


def struct_bodies() -> dict[str, tuple[str, str]]:
    """`{StructName: (body, relative source path)}` for the whole crate."""
    out: dict[str, tuple[str, str]] = {}
    if not SRC.is_dir():
        sys.exit(f"authorable-surface-gate: MISUSE — no loader source at {SRC}")
    for path in sorted(SRC.rglob("*.rs")):
        text = path.read_text(encoding="utf-8")
        for m in _STRUCT.finditer(text):
            start = m.end()
            depth = 1
            i = start
            while i < len(text) and depth:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                i += 1
            out[m.group(1)] = (text[start : i - 1], str(path.relative_to(REPO)).replace("\\", "/"))
    return out


def fields_of(body: str) -> list[tuple[str, str]]:
    """`[(authored key, rust type)]`, honouring `#[serde(rename)]`.

    The rename matters and is not hypothetical: `ProgressionKindPatch.kind_type`
    is authored as `type`, because `type` is a Rust keyword. A gate reading field
    names alone would enumerate a key no author can write, and miss the one they
    must.
    """
    out = []
    for m in _FIELD.finditer(body):
        name, ty = m.group(1), m.group(2).strip()
        # The attributes for this field are the lines between the previous
        # field (or the start) and this one.
        head = body[: m.start()]
        tail = head.rsplit("\n\n", 1)[-1]
        last_field = list(_FIELD.finditer(head))
        if last_field:
            tail = head[last_field[-1].end() :]
        ren = _RENAME.search(tail)
        out.append((ren.group(1) if ren else name, ty))
    return out


def local_types(rust_type: str, known: set[str]) -> list[str]:
    """The locally-declared struct names appearing in a field's type."""
    return [w for w in re.findall(r"\w+", rust_type) if w in known]


def closure(bodies: dict[str, tuple[str, str]]) -> dict[str, list[tuple[str, str]]]:
    """Every patch type reachable from [`ROOT`], with its authored keys."""
    if ROOT not in bodies:
        sys.exit(
            f"authorable-surface-gate: MISUSE — `{ROOT}` not found in {SRC.relative_to(REPO)}. "
            f"If the root of the authored file was renamed, this gate must be pointed at it; "
            f"a closure from a missing root reaches nothing and would pass."
        )
    known = set(bodies)
    seen: dict[str, list[tuple[str, str]]] = {}
    stack = [ROOT]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        flds = fields_of(bodies[name][0])
        seen[name] = flds
        for _, ty in flds:
            for dep in local_types(ty, known):
                if dep not in seen:
                    stack.append(dep)
    return seen


# ─────────────────────────────────────────────────────────────────────────────
# The contract side.
#
# A REAL parser, not a hand-rolled reader. The first version of this function was
# four regexes, on the reasoning `provisioner_live::manifest_ids` gives for the
# same choice — "the shape is a stable contract stated in the file's own header".
# It was wrong within a minute of running: a section's `- key:` line comes BEFORE
# its `rust_type:`, so every section's own name was attributed to the PREVIOUS
# type, and the gate reported seven phantom keys against a correct contract.
# `generation-guard-gate` and `slo-latency-lint` already take the PyYAML
# dependency; nesting is exactly the thing a line-oriented reader gets wrong.
# ─────────────────────────────────────────────────────────────────────────────

def contract_keys() -> dict[str, set[str]]:
    """`{rust_type: {authored keys}}` as the contract declares them."""
    if not CONTRACT.is_file():
        sys.exit(f"authorable-surface-gate: MISUSE — no contract at {CONTRACT.relative_to(REPO)}")
    import yaml

    doc = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or "root_type" not in doc:
        sys.exit("authorable-surface-gate: MISUSE — the contract declares no `root_type:`")

    per_type: dict[str, set[str]] = {}
    sections = doc.get("sections") or []
    nested = doc.get("nested") or []

    # The root's keys ARE the section names: a top-level `[combat]` in the
    # authored file is the `combat` field of `RulesetPatch`.
    per_type[doc["root_type"]] = {s["key"] for s in sections if "key" in s}

    for entry in list(sections) + list(nested):
        rust_type = str(entry.get("rust_type", "")).strip()
        # `quantities` is `Vec<String>` — a section with no struct behind it, so
        # there is nothing to compare field-wise. Skipped by SHAPE (not a bare
        # identifier) rather than by name.
        if not re.fullmatch(r"\w+", rust_type):
            continue
        per_type[rust_type] = {f["key"] for f in (entry.get("fields") or []) if "key" in f}
    return per_type


#: The two refusal lists and the classifier live in `ruleset-core`, not the
#: loader — a different crate, which is why they are read separately.
CORE = REPO / "crates" / "ruleset-core" / "src"

_CONST = r"pub const {name}: &\[\(&str, &str\)\] = &\[(.*?)\n\];"
_TUPLE_KEY = re.compile(r'\(\s*\n?\s*"([^"]+)"\s*,', re.MULTILINE)
_CLASSIFY_ROW = re.compile(
    r"^\s*(\w+)\s*=>\s*Floor::(\w+),\s*Mutability::(\w+),\s*Strategy::(\w+)", re.MULTILINE
)


def _core_text() -> str:
    if not CORE.is_dir():
        sys.exit(f"authorable-surface-gate: MISUSE — no core source at {CORE}")
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(CORE.rglob("*.rs")))


def forbidden_keys(const_name: str, text: str) -> list[str]:
    """The keys of a `&[(&str, &str)]` refusal table, by name."""
    m = re.search(_CONST.format(name=const_name), text, re.DOTALL)
    if not m:
        sys.exit(
            f"authorable-surface-gate: MISUSE — `{const_name}` not found in ruleset-core. "
            f"A refusal list that cannot be located reads as an empty list, and an empty "
            f"refusal list agrees with a contract that refuses nothing."
        )
    return [k for k in _TUPLE_KEY.findall(m.group(1))]


def classify_rows(struct: str, text: str) -> list[tuple[str, str, str, str]]:
    """`[(field, floor, mutability, strategy)]` from `classify!(Struct { … })`."""
    m = re.search(rf"classify!\({struct}\s*\{{(.*?)\n\}}\);", text, re.DOTALL)
    if not m:
        return []
    return _CLASSIFY_ROW.findall(m.group(1))


def check() -> list[str]:
    bodies = struct_bodies()
    reached = closure(bodies)
    declared = contract_keys()
    fails: list[str] = []
    fails += check_refusals()
    fails += check_classification()
    fails += check_engine_defaults()

    total_keys = sum(len(v) for v in reached.values())
    if len(reached) < MIN_TYPES:
        fails.append(
            f"REACH: the closure from `{ROOT}` reached only {len(reached)} type(s) "
            f"(floor {MIN_TYPES}). A closure that reaches nothing agrees with any contract."
        )
    if total_keys < MIN_KEYS:
        fails.append(
            f"REACH: parsed only {total_keys} authored key(s) across the closure "
            f"(floor {MIN_KEYS}). The field parser is not reading the structs."
        )

    for name, flds in sorted(reached.items()):
        keys = {k for k, _ in flds}
        if name not in declared:
            fails.append(
                f"{name} is reachable from `{ROOT}` — an author can write it — but the contract "
                f"never names it. Add a section or a `nested:` entry with `rust_type: {name}`."
            )
            continue
        missing = keys - declared[name]
        extra = declared[name] - keys
        if missing:
            fails.append(
                f"{name}: {len(missing)} authored key(s) the contract does not list: "
                f"{sorted(missing)}. The loader accepts them; a manifest builder written "
                f"against the contract would not offer them."
            )
        if extra:
            fails.append(
                f"{name}: the contract lists {len(extra)} key(s) that are not fields: "
                f"{sorted(extra)}. `deny_unknown_fields` means the loader REFUSES these, so "
                f"the contract is promising an author something that errors."
            )

    for name in sorted(declared):
        if name not in reached and name != ROOT:
            fails.append(
                f"the contract declares `rust_type: {name}`, which is not reachable from "
                f"`{ROOT}`. Either it is dead, or a field pointing at it was removed."
            )
    return fails


def _contract_doc() -> dict:
    import yaml

    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def check_refusals() -> list[str]:
    """What an author may NOT say must match, in both directions.

    A key silently dropped from `FORBIDDEN_KEYS` becomes authorable with nothing
    saying so, and the contract would still be telling authors it is refused —
    which is the worse direction, because it reads as a guarantee.
    """
    text = _core_text()
    doc = _contract_doc()
    fails = []
    for field, const in (("refused", "FORBIDDEN_KEYS"), ("refused_in_verb_rows", "FORBIDDEN_VERB_KEYS")):
        block = doc.get(field) or {}
        listed = {k["key"] for k in (block.get("keys") or []) if "key" in k}
        actual = set(forbidden_keys(block.get("const", const), text))
        if not actual:
            fails.append(f"REACH: `{const}` parsed to zero keys; the refusal reader is not reading it")
        for k in sorted(actual - listed):
            fails.append(
                f"`{const}` refuses `{k}` and the contract's `{field}:` does not list it. "
                f"An author who writes it gets a refusal the derived surface never warned about."
            )
        for k in sorted(listed - actual):
            fails.append(
                f"the contract's `{field}:` lists `{k}` as refused, but `{const}` does not refuse "
                f"it. Either the refusal was dropped — in which case the key is now authorable and "
                f"nothing says so — or the contract is warning about nothing."
            )
    return fails


def check_engine_defaults() -> list[str]:
    """The contract's `engine_default:` values must BE the artifact's.

    Added late, and for a reason worth recording: writing the defaults into the
    contract created a THIRD copy of the same numbers — `engine_default.toml`,
    `Ruleset::engine_default()`, and now this — with a check between only the
    first two (`engine_default_matches_the_code`). An artifact whose entire
    purpose is to stop a hand-maintained list drifting from a code-derived set
    must not ship a hand-maintained copy of the numbers with nothing comparing
    them. `RLS-D2` made the artifact authoritative precisely so the values would
    have one home.

    Both directions: a contract default that is not the artifact's, and an
    artifact key the contract gives no default for.
    """
    import tomllib

    if not DEFAULTS.is_file():
        sys.exit(
            f"authorable-surface-gate: MISUSE — no engine-default artifact at "
            f"{DEFAULTS.relative_to(REPO).as_posix()}. `RLS-D2` makes it the authority for every "
            f"value the contract quotes; without it there is nothing to compare against."
        )
    artifact = tomllib.loads(DEFAULTS.read_text(encoding="utf-8"))
    doc = _contract_doc()
    fails: list[str] = []
    compared = 0

    for section in doc.get("sections") or []:
        key = section["key"]
        fields = section.get("fields") or []
        table = artifact.get(key)
        if table is None:
            # Only sections the engine declares a default FOR are compared.
            # `quantities`/`resources`/`verbs`/`progression_kinds` have an empty
            # engine layer by design, which the contract states as `[]`.
            for f in fields:
                if "engine_default" in f:
                    fails.append(
                        f"`{key}.{f['key']}` carries an `engine_default:` but "
                        f"{DEFAULTS.name} declares no `[{key}]` table — so quoting one invents a "
                        f"value the engine does not have."
                    )
            continue
        for f in fields:
            if "engine_default" not in f:
                continue
            want = table.get(f["key"], "<absent from the artifact>")
            compared += 1
            if f["engine_default"] != want:
                fails.append(
                    f"`{key}.{f['key']}`: the contract says the engine default is "
                    f"{f['engine_default']!r}, {DEFAULTS.name} says {want!r}. The artifact is the "
                    f"authority (`RLS-D2`); an author reading the contract would be told the "
                    f"wrong number."
                )
        listed = {f["key"] for f in fields if "engine_default" in f}
        for missing in sorted(set(table) - listed):
            fails.append(
                f"{DEFAULTS.name} declares `[{key}] {missing}` and the contract gives no "
                f"`engine_default:` for it. An author is left guessing what omitting the key does."
            )

    if compared < 15:
        fails.append(
            f"REACH: only {compared} engine default(s) compared (floor 15); the artifact is not "
            f"being read."
        )
    return fails


def check_classification() -> list[str]:
    """A section claiming a class must have it on EVERY row of `classify!`.

    Stated per section rather than per field because all 20 rows agree today —
    but a summary that nothing checks is how a `Frozen` field ends up advertised
    as `Tunable`. `classify!`'s own totality is a compile error; this is the
    other half, tying that table to what an author is told.
    """
    text = _core_text()
    doc = _contract_doc()
    fails = []
    checked = 0
    for section in doc.get("sections") or []:
        cls = section.get("classification")
        if not cls:
            continue
        over = cls.get("classify_over")
        rows = classify_rows(over, text)
        if not rows:
            fails.append(
                f"section `{section['key']}` claims `classify_over: {over}`, and no "
                f"`classify!({over} {{ … }})` block was found. A classification claim checked "
                f"against nothing is the shape this gate exists to refuse."
            )
            continue
        want = (cls.get("floor"), cls.get("mutability"), cls.get("strategy"))
        for fld, floor, mut, strat in rows:
            checked += 1
            if (floor, mut, strat) != want:
                fails.append(
                    f"section `{section['key']}` advertises {want} for every field, but "
                    f"`{over}.{fld}` is ({floor}, {mut}, {strat}). Split the claim per field, "
                    f"or the contract is telling an author they may tune something they may not."
                )
    if checked < 15:
        fails.append(
            f"REACH: only {checked} classification row(s) compared (floor 15); the `classify!` "
            f"reader is not reaching the tables."
        )
    return fails


# ─────────────────────────────────────────────────────────────────────────────
# SELF-TEST — the arms proven on synthetic input, per the teeth ratchet.
# ─────────────────────────────────────────────────────────────────────────────

_SELFTEST_SRC = """
pub struct RootPatch {
    #[serde(default)]
    pub alpha: AlphaPatch,
    #[serde(default)]
    pub rows: Vec<RowPatch>,
}
pub struct AlphaPatch {
    pub one: Option<i64>,
    pub two: Option<i64>,
}
pub struct RowPatch {
    pub name: String,
    #[serde(rename = "type")]
    pub kind_type: String,
}
pub struct NotReachable {
    pub nope: String,
}
"""


def _selftest() -> int:
    cases: list[tuple[str, object, bool]] = []

    bodies = {}
    for m in _STRUCT.finditer(_SELFTEST_SRC):
        start = m.end()
        depth, i = 1, start
        while i < len(_SELFTEST_SRC) and depth:
            depth += (_SELFTEST_SRC[i] == "{") - (_SELFTEST_SRC[i] == "}")
            i += 1
        bodies[m.group(1)] = (_SELFTEST_SRC[start : i - 1], "synthetic")

    global ROOT
    saved, ROOT = ROOT, "RootPatch"
    try:
        reached = closure(bodies)
    finally:
        ROOT = saved

    cases.append(("the closure reaches a nested list type", "RowPatch" in reached, True))
    cases.append(("the closure reaches a nested table type", "AlphaPatch" in reached, True))
    cases.append(
        ("an unreferenced Deserialize struct stays OUT of the closure",
         "NotReachable" in reached, False))
    cases.append(("the root itself is in the closure", "RootPatch" in reached, True))

    # `.get`, not `[...]`. The first version indexed, so a closure that stopped
    # recursing died with a `KeyError` traceback instead of naming the arm that
    # noticed — rc=1 for the right reason with a message nobody can act on, which
    # is the shape `BDR-84` had a bite harness reject.
    row = dict(reached.get("RowPatch", []))
    alpha = dict(reached.get("AlphaPatch", []))
    cases.append(("a `serde(rename)` field is read by its AUTHORED key",
                  "type" in row, True))
    cases.append(("...and NOT by its Rust field name",
                  "kind_type" in row, False))
    cases.append(("a plain field keeps its name", "name" in row, True))
    cases.append(("field types are captured", alpha.get("one"), "Option<i64>"))

    # The real contract must actually cover the real closure — the arm that
    # would catch this gate being pointed at nothing.
    real_declared = contract_keys()
    cases.append(("the shipped contract declares the root", ROOT in real_declared, True))
    cases.append(("the shipped contract lists >= 7 types", len(real_declared) >= 7, True))

    bad = 0
    for label, got, want in cases:
        if got != want:
            print(f"  SELFTEST FAIL: {label} — got {got!r}, want {want!r}", file=sys.stderr)
            bad += 1
    if bad:
        print(f"authorable-surface-gate: SELFTEST FAILED — {bad}/{len(cases)}", file=sys.stderr)
        return 1
    print(
        f"authorable-surface-gate: SELFTEST PASS — {len(cases)} case(s); it proves the closure "
        f"reaches nested types, EXCLUDES an unreferenced struct, and reads a `serde(rename)` by "
        f"its authored key rather than its field name"
    )
    return 0


def main() -> int:
    if "--self-test" in sys.argv or "--selftest" in sys.argv:
        return _selftest()
    if _selftest():
        return 1
    fails = check()
    if fails:
        print("authorable-surface-gate: FAIL", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\n  The contract is `contracts/ruleset/authorable-surface.v1.yaml`. It is the "
            "derived statement of what an author may declare (`G-S5a`); a field that is not in "
            "it is a capability nothing downstream knows exists.",
            file=sys.stderr,
        )
        return 1
    bodies = struct_bodies()
    reached = closure(bodies)
    text = _core_text()
    doc = _contract_doc()
    n_refused = len(forbidden_keys("FORBIDDEN_KEYS", text)) + len(
        forbidden_keys("FORBIDDEN_VERB_KEYS", text)
    )
    n_def = sum(
        1
        for s in (doc.get("sections") or [])
        for f in (s.get("fields") or [])
        if "engine_default" in f and isinstance(f["engine_default"], (int, list))
    )
    n_class = sum(
        len(classify_rows(s["classification"]["classify_over"], text))
        for s in (doc.get("sections") or [])
        if s.get("classification")
    )
    print(
        f"authorable-surface-gate: OK — {len(reached)} patch type(s) reachable from `{ROOT}`, "
        f"{sum(len(v) for v in reached.values())} authored key(s), all enumerated in "
        f"{CONTRACT.relative_to(REPO).as_posix()} and nothing enumerated that is not a field; "
        f"{n_refused} refused key(s) match both ways; {n_class} classification row(s) agree with "
        f"the class their section advertises; {n_def} engine default(s) match the artifact; reach floors >= {MIN_TYPES} type(s), >= {MIN_KEYS} key(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

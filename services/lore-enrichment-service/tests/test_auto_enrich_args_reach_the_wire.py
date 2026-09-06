"""TOOLV2 LOOP #267 — a ten-field argument object with nothing on the wire to explain it.

`lore_enrichment_auto_enrich` is a paid, async, book-scoped tool. Its nested `args` object carried
ten fields and, in the federated schema, every one of them serialized bare:

    {"title": "Technique", "type": "string"}
    {"title": "Coverage Limit", "type": "integer"}
    {"title": "Eval Reserve Fraction", "type": "number"}
    {"title": "Targets", "anyOf": [{"items": {"additionalProperties": true, ...}}, ...]}

No descriptions at all, unlike every other tool in this catalogue. A model choosing
`coverage_limit` or `eval_reserve_fraction` had nothing to choose from, and `targets` is an
unconstrained object array whose required shape was written down — in a source COMMENT, three
lines above the field, which never reaches the wire. That is the same discard this loop keeps
finding between a computed value and its caller.

`technique` was the sharpest case. It is a closed set of five (template, retrieval, fabrication,
recook, compose_draft) declared as a bare `str` with no enum, no description, and a refusal that
named none of them:

    technique="not_a_technique"  ->  "unknown technique 'not_a_technique'"

so an agent could not learn the valid set from the schema, the description, or the error. The very
next check in that same file already does it right — "compose_draft is the draft input's technique
— use input_source='draft'" — so the discipline was one line below the omission, three times over.

Also measured and NOT fixed here: the missing-required-field error is a raw Pydantic dump
("2 validation errors for ... [type=missing, input_value={...}] For further information visit
https://errors.pydantic.dev/..."), where the rest of this catalogue answers "invalid arguments for
X — `field`: Field required. Fix the argument and call the tool again." That is a kit-level
formatting difference, recorded in the ledger rather than patched per-service.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _args_model() -> str:
    body = (APP / "mcp" / "server.py").read_text(encoding="utf-8").replace("\r\n", "\n")
    start = body.index("class _AutoEnrichArgs(")
    return body[start: body.index("\n@mcp_server.tool", start)]


def test_every_field_carries_a_description():
    """A bare title/type pair is not documentation. Any field without one fails here, including
    a field added later."""
    model = _args_model()
    fields = re.findall(r"^    ([a-z_]+): ", model, re.M)
    assert fields, "the arg model has no fields — the parser is wrong, not the model"
    missing = []
    for f in fields:
        seg = model[model.index(f"    {f}: "):]
        seg = seg[: seg.index("\n    ", 1) if "\n    " in seg[1:] else len(seg)]
        # the field's own declaration runs to the next top-level field
        nxt = re.search(r"\n    [a-z_]+: ", model[model.index(f"    {f}: ") + 1:])
        decl = model[model.index(f"    {f}: "):][: nxt.start() if nxt else None]
        if "description=" not in decl:
            missing.append(f)
    assert missing == [], f"these args reach the wire with no description: {missing}"


def test_the_targets_shape_is_on_the_wire_not_in_a_comment():
    model = _args_model()
    assert "{canonical_name, target_ref?, entity_kind?, mention_count?, " in model, (
        "the targets shape is back in a comment (or gone); it is an unconstrained object array, "
        "so the shape is the only thing making it usable"
    )
    # It must be inside a description=, not a `#` comment.
    decl = model[model.index("    targets: "):]
    assert "description=" in decl and "canonical_name" in decl.split("description=")[1]


def test_the_technique_field_names_its_closed_set():
    model = _args_model()
    decl = model[model.index("    technique: "):]
    decl = decl[: decl.index("\n    max_gaps")]
    for value in ("retrieval", "template", "fabrication", "recook", "compose_draft"):
        assert value in decl, f"technique's description omits {value!r}"


def test_no_technique_refusal_anywhere_hides_the_valid_set():
    """#267 CORRECTION — scan the TREE, do not count occurrences in the file you found first.

    My census found 3 sites in compose.py and I fixed exactly those. There were six: a fourth in
    that same file at a different indent, one in gaps.py — the path auto_enrich actually takes,
    so the tool I was proving still answered with the old dead end after I had "fixed" it — and
    one in jobs.py. Twice in one iteration a hand-rolled census under-counted, which is the same
    failure #253 wrote a tree-wide regex for. This is that regex.
    """
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"unknown technique[^\n]*", text):
            line = m.group(0)
            # The worker's resume path logs "unknown technique → cannot re-drive; drop" about a
            # job it cannot restart. That is a log line, not a caller-facing refusal.
            if "cannot re-drive" in line:
                continue
            if "valid:" not in line:
                offenders.append(f"{path.relative_to(APP)}: {line[:70]}")
    assert offenders == [], (
        "these refusals reject a technique without naming the valid set:\n  "
        + "\n  ".join(offenders)
    )


def test_the_valid_set_is_derived_from_the_enum():
    """A typed-out list goes stale the first time a technique is added."""
    hits = 0
    for path in sorted(APP.rglob("*.py")):
        hits += path.read_text(encoding="utf-8").count('", ".join(t.value for t in Technique)')
    assert hits >= 6, f"expected the enum-derived list at every refusal site, found {hits}"


def test_the_sibling_refusal_that_already_did_it_right_is_untouched():
    """compose_draft's rejection names the remedy ('use input_source=draft'). It was the
    precedent for this fix and must not be swept along with it."""
    body = (APP / "api" / "compose.py").read_text(encoding="utf-8")
    assert "use input_source='draft'" in body

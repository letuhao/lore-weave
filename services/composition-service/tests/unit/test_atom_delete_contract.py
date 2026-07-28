"""THE ATOM DELETE CONTRACT — every destructive atom op declares what it owes (F3).

WHY THIS EXISTS. The atom families were built one at a time, each choosing its own delete
semantics, and nothing forced them to agree or even to say. The result was three defects of one
shape in a single track:

  · 4 of 6 PlanForge kinds     — delete silently no-op'd (deep-merge kept the removed member)
  · scene_link, entity_override — hard-deleted AUTHORED content, one with `undo_hint: None`
  · the error-block undo hint   — named a READ op that reverted nothing

Same class every time: a sibling surface that does not carry its siblings' guarantees. The RULE
already existed (`canon_rules.restore` calls itself "the UNDO the DELETE promises"); what was
missing was the gate. This repo's meta-pattern is rule + SoT + gate + test, and this file is the
gate.

WHAT IT DOES *NOT* DO: force uniformity. `motif_link` hard-deletes and that is CORRECT — its row is
`(from_motif_id, to_motif_id, kind, ord)` with no authored text, so re-creating the edge costs
exactly what undoing it would. Meanwhile `scene_link` carried an authored `label` and
`entity_override` an authored JSONB blob, and losing those irreversibly destroys work only the
author can reconstruct. The distinction is the PAYLOAD, not the shape.

So the contract makes each family DECLARE its tier and justify a hard delete — and, most
importantly, **fails when a family appears that has not declared at all**. That last property is
the anti-drift one: a new `*_edit` tool with a destructive op cannot ship silently.
"""

from __future__ import annotations

import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SERVER = _ROOT / "app" / "mcp" / "server.py"
_MIGRATE = _ROOT / "app" / "db" / "migrate.py"

# Ops that DESTROY or hide a row. `restore`/`reopen` are the reverses, not destructive.
_DESTRUCTIVE = {"delete", "archive", "dismiss", "unbind"}
# The reverse ops that satisfy a soft-delete declaration.
_REVERSE = {"restore", "reopen", "bind"}


class AtomDelete:
    """One family's declaration.

    `flag` names HOW the row is hidden, because the families do not agree — and that disagreement
    is itself the finding this contract exists to make visible. Three vocabularies are in use:

        is_archived BOOLEAN   outline_node · canon_rule · structure_template · scene_link ·
                              entity_override · chapter_error_block
        status='archived'     motif · arc_template · composition_work

    Both work. Neither is wrong. But nothing ever forced a family to say which it used, so a
    reader (or a gate) had to go and look each time — the same "no declared contract" root the
    hard-vs-soft split came from. Declaring it does not unify them; it stops the next family from
    inventing a THIRD spelling by accident.
    """

    def __init__(self, tier: str, table: str | None = None, why: str = "",
                 flag: str = "is_archived"):
        assert tier in ("soft", "hard", "pair"), tier
        self.tier, self.table, self.why, self.flag = tier, table, why, flag


# ── THE SoT ────────────────────────────────────────────────────────────
# Adding a destructive op to a family? Add its row here, with a reason if it is `hard`.
CONTRACT: dict[str, AtomDelete] = {
    "composition_outline_node_edit": AtomDelete("soft", "outline_node"),
    "composition_canon_rule_edit": AtomDelete("soft", "canon_rule"),
    "composition_scene_link_edit": AtomDelete(
        "soft", "scene_link",
        why="F3: was a hard DELETE returning `undo_hint: None`. The row carries an AUTHORED "
            "`label` and the author's declared setup/payoff connection.",
    ),
    "composition_entity_override_edit": AtomDelete(
        "soft", "entity_override",
        why="F3: was a hard DELETE. `overridden_fields` is an authored JSONB blob — how this dị "
            "bản's entity differs — and re-authoring it from memory is real lost work.",
    ),
    "composition_derivative_edit": AtomDelete("soft", "composition_work", flag="status"),
    "composition_motif_edit": AtomDelete("soft", "motif", flag="status"),
    "composition_arc_edit": AtomDelete("soft", "outline_node"),
    "composition_arc_template_edit": AtomDelete("soft", "arc_template", flag="status"),
    "composition_error_block_edit": AtomDelete("soft", "chapter_error_block"),
    "composition_structure_template_edit": AtomDelete("soft", "structure_template"),
    # ── the DEFENSIBLE hard delete ──
    "composition_motif_link_edit": AtomDelete(
        "hard",
        why="The row is (from_motif_id, to_motif_id, kind, ord) — ids, a closed-set kind and an "
            "ordinal, with NO authored text. Re-creating the edge costs exactly what undoing it "
            "would, so an undo buys nothing and an is_archived column would only add a filter "
            "every read must remember. Contrast scene_link, whose authored `label` made the same "
            "shape a real data-loss bug.",
    ),
    # ── a PAIR op: the reverse is the other half of the same tool ──
    "composition_motif_bind_edit": AtomDelete(
        "pair",
        why="`unbind` is not a delete — `bind`/`unbind` are two halves of one toggle, and the "
            "tool exposes both, so the reverse is always reachable.",
    ),
}


def _declared_families() -> dict[str, str]:
    """{tool_name: op-csv} for every unified op-dispatch tool, read from the REAL server module.

    Parsed from source rather than imported so the gate keeps working when the module cannot be
    imported (missing env), and so it sees exactly what a reviewer would read.
    """
    src = _SERVER.read_text(encoding="utf-8")
    argops = {
        m.group(1): m.group(2).replace('"', "").replace(" ", "")
        # `op:` is not necessarily the next line. A class may carry a DOCSTRING (arc, motif) or
        # leading `#` COMMENTS (structure_template) first. Both variants cost this gate a family
        # while it still reported green:
        #   v1 (`\s*\n\s*op:`)        saw 6 of 14 — missed every docstring'd family
        #   v2 (docstring only)       saw 13 of 14 — missed structure_template, which HAS an
        #                             `archive` op and so went entirely unchecked
        # A gate with a silent blind spot is worse than no gate, because it certifies what it
        # never looked at. `test_the_parser_sees_the_AWKWARD_shapes` below pins both variants.
        for m in re.finditer(
            r'class (_\w+)\(ForbidExtra\):\s*\n'
            r'(?:\s*"""(?:.|\n)*?"""\s*\n)?'      # optional docstring
            r'(?:\s*#[^\n]*\n)*'                  # optional leading comments
            r'\s*op:\s*Literal\[([^\]]*)\]',
            src,
        )
    }
    out: dict[str, str] = {}
    last: str | None = None
    for line in src.split("\n"):
        n = re.search(r'^\s*name="([a-z_]+)",', line)
        if n:
            last = n.group(1)
        d = re.search(r'^async def \w+\(ctx: MCPContext, args: (_\w+)\)', line)
        if d and last and d.group(1) in argops:
            out[last] = argops[d.group(1)]
    return out


def _destructive_families() -> dict[str, set[str]]:
    return {
        tool: set(ops.split(","))
        for tool, ops in _declared_families().items()
        if _DESTRUCTIVE & set(ops.split(","))
    }


def test_the_parser_actually_finds_the_families():
    """A gate that silently matches nothing passes forever. Pin that it sees real families."""
    fams = _declared_families()
    assert len(fams) >= 12, f"only found {len(fams)} op-dispatch tools — the parser has drifted"
    assert "composition_canon_rule_edit" in fams


def test_the_parser_sees_the_AWKWARD_shapes():
    """The two class layouts that each silently cost this gate a family while it reported green.

    Named explicitly rather than trusting the count: a future family could be added at the same
    time one is missed, keeping the total plausible while coverage quietly drops.
    """
    fams = _declared_families()
    assert "composition_arc_edit" in fams, "docstring-before-op class is being skipped again"
    assert "composition_structure_template_edit" in fams, (
        "comment-before-op class is being skipped again — this family HAS an `archive` op, so "
        "missing it means a destructive op ships entirely unchecked"
    )


def test_every_destructive_family_has_DECLARED_its_tier():
    """The anti-drift property. A new `*_edit` with a delete op cannot ship without saying whether
    the row is recoverable — which is exactly what nobody was forced to say before."""
    undeclared = sorted(set(_destructive_families()) - set(CONTRACT))
    assert not undeclared, (
        "these families have a destructive op but no row in CONTRACT:\n  "
        + "\n  ".join(undeclared)
        + "\n\nDeclare the tier. `soft` needs is_archived + a reverse op; `hard` needs a written "
          "reason why losing the row costs the author nothing."
    )


def test_the_contract_has_no_stale_rows():
    """A family that lost its destructive op should lose its row, or the SoT rots into fiction."""
    fams = _destructive_families()
    stale = sorted(k for k in CONTRACT if k not in fams)
    assert not stale, f"CONTRACT rows for families with no destructive op: {stale}"


@pytest.mark.parametrize("tool", sorted(k for k, v in CONTRACT.items() if v.tier == "soft"))
def test_a_soft_delete_exposes_a_REVERSE_op(tool):
    """`canon_rules.restore` calls itself 'the UNDO the DELETE promises'. If a family declares soft
    but exposes no way back, the promise is unkeepable — and the author only finds out after."""
    ops = set(_declared_families()[tool].split(","))
    assert _REVERSE & ops, (
        f"{tool} declares tier=soft but exposes none of {sorted(_REVERSE)} — the row is hidden "
        f"with no way to bring it back, which is worse than a hard delete because it looks "
        f"recoverable."
    )


@pytest.mark.parametrize(
    "tool,table,flag",
    sorted((k, v.table, v.flag) for k, v in CONTRACT.items() if v.tier == "soft" and v.table),
)
def test_a_soft_delete_has_somewhere_to_put_the_flag(tool, table, flag):
    """Declaring soft while the table has no column to hold it means the delete is really hard and
    the declaration is just a comment. Checked against the actual DDL, and against the flag the
    family DECLARED — an earlier version assumed every family spelled it `is_archived` and reported
    motif/arc_template/composition_work as broken when they simply use `status='archived'`.
    Assuming one spelling is the same mistake the contract exists to catch."""
    ddl = _MIGRATE.read_text(encoding="utf-8")
    block = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", ddl, re.S)
    assert block, f"no CREATE TABLE for {table!r} in migrate.py"
    has_col = flag in block.group(1) or re.search(
        rf"ALTER TABLE {table}[^;]*ADD COLUMN IF NOT EXISTS {flag}", ddl
    )
    assert has_col, (
        f"{tool} declares tier=soft on {table} via `{flag}`, but that column is not in the DDL — "
        f"either the delete is really destroying the row, or the declared flag name is wrong."
    )


@pytest.mark.parametrize("tool", sorted(k for k, v in CONTRACT.items() if v.tier != "soft"))
def test_a_hard_delete_must_JUSTIFY_itself(tool):
    """Uniformity is not the goal — motif_link's hard delete is correct. But the reason has to be
    written down, because the next person will otherwise copy the shape onto a family whose row
    DOES carry authored content, which is exactly how scene_link happened."""
    why = CONTRACT[tool].why
    assert len(why) > 60, (
        f"{tool} declares tier={CONTRACT[tool].tier} without a real justification. Say why losing "
        f"this row costs the author nothing (no authored text? trivially re-creatable?)."
    )

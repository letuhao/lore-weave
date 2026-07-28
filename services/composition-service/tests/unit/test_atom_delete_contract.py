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

So the contract makes each family DECLARE its tier and justify a non-recoverable delete — and, most
importantly, **fails when a destructive surface appears that has not declared at all**.

HOW IT FINDS THE SURFACES — and why the first version got this wrong. v1/v2 of this gate parsed
`server.py` with a regex, on the stated grounds that the module "cannot be imported without env".
That was false: `tests/conftest.py` sets all four required vars, so the module imports fine under
pytest. The regex bought nothing and cost two silent blind spots (v1 saw 6 of 14 families, v2 saw
13 of 14 — missing `structure_template`, which HAS an `archive` op and so went wholly unchecked),
plus a third it never even aimed at (the 12 legacy standalone `*_delete`/`*_archive` tools).

This version asks the LIVE MCP REGISTRY instead: `list_tools()` → `inputSchema.properties.op.enum`.
A JSON schema has no docstrings or comments to trip over, and it is exactly the surface the model
sees. That removes the blind-spot CLASS rather than its two instances.

The three properties that make under-discovery impossible are pinned below:
  1. every op verb in the service is CLASSIFIED (an unclassified verb fails — a new `purge`
     cannot slip in as benign-by-default);
  2. every legacy destructive door resolves through its own `superseded_by` meta to a DECLARED
     family (the 12 standalone tools the earlier gate could not see at all);
  3. the declared tier is checked against the DDL / the service, not taken on faith.
"""

from __future__ import annotations

import asyncio
import functools
import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_MIGRATE = _ROOT / "app" / "db" / "migrate.py"
_RUN_SERVICE = _ROOT / "app" / "services" / "authoring_run_service.py"


# ── OP VERB CLASSIFICATION ─────────────────────────────────────────────
# EVERY verb the service exposes must appear in exactly one of these sets. `test_every_op_verb_is
# _CLASSIFIED` fails on an unknown one, which is the property the previous version lacked: it held
# a `_DESTRUCTIVE` ALLOWLIST, so anything not on it was benign by default — and `revert_all`, which
# server.py itself labels "destructive + irreversible", was silently waved through.

# Removes or hides an atom ROW.
_DESTRUCTIVE = {"delete", "archive", "dismiss", "unbind"}
# Does not touch the row, but REVERTS AUTHORED PROSE to an earlier revision. Recoverable through
# the revision chain rather than an archive flag — a real guarantee, but a different one.
_REVERSION = {"revert_all", "reject_unit"}
# The reverses that satisfy a soft-delete declaration.
_REVERSE = {"restore", "reopen", "bind"}
# Everything else: creates, reads, lifecycle transitions, and job control. Listed explicitly so
# that adding a verb is a decision someone made, not a default someone inherited.
_BENIGN = {
    "create", "add", "update", "patch", "update_spec", "clone", "move", "assign_chapters",
    "list", "status", "resolve",
    "start", "resume", "pause", "close", "cancel", "gate",
    "accept_unit", "approve_plan", "approve_edges", "project_kg",
}
_CLASSIFIED = _DESTRUCTIVE | _REVERSION | _REVERSE | _BENIGN


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

    Tiers:
        soft      the row is hidden by `flag` and a reverse op brings it back
        hard      the row is really gone, and losing it costs the author nothing (must justify)
        pair      the "destructive" op is half of a toggle whose other half is on the same tool
        revision  authored prose is reverted, recoverable via the chapter revision chain

    `rest_reverse` names the route a HUMAN reaches the undo through, and exists because checking
    only the MCP surface let a real bug through this very gate. F3 converted `scene_link` and
    `entity_override` from hard delete to soft, and added `op=restore` — on MCP only. The row
    survived, the agent could undo it, and the author could not: no REST route, and the list reads
    filter `NOT is_archived`, so the id was not even discoverable. That is worse than the hard
    delete it replaced, because the delete now LOOKS recoverable. A soft delete is a promise made
    to the author, so it has to be checked on the surface the author actually uses.
    """

    def __init__(self, tier: str, table: str | None = None, why: str = "",
                 flag: str = "is_archived", rest_reverse: str | None = None):
        assert tier in ("soft", "hard", "pair", "revision"), tier
        self.tier, self.table, self.why, self.flag = tier, table, why, flag
        self.rest_reverse = rest_reverse


# ── THE SoT ────────────────────────────────────────────────────────────
# Adding a destructive op to a family? Add its row here, with a reason unless it is `soft`.
CONTRACT: dict[str, AtomDelete] = {
    "composition_outline_node_edit": AtomDelete(
        "soft", "outline_node", rest_reverse="/outline/nodes/{node_id}/restore"),
    "composition_canon_rule_edit": AtomDelete(
        "soft", "canon_rule", rest_reverse="/canon-rules/{rule_id}/restore"),
    "composition_scene_link_edit": AtomDelete(
        "soft", "scene_link", rest_reverse="/scene-links/{link_id}/restore",
        why="F3: was a hard DELETE returning `undo_hint: None`. The row carries an AUTHORED "
            "`label` and the author's declared setup/payoff connection.",
    ),
    "composition_entity_override_edit": AtomDelete(
        "soft", "entity_override",
        rest_reverse="/works/{project_id}/entity-overrides/{override_id}/restore",
        why="F3: was a hard DELETE. `overridden_fields` is an authored JSONB blob — how this dị "
            "bản's entity differs — and re-authoring it from memory is real lost work.",
    ),
    # The reverse here is the generic PATCH (status back to active), not a dedicated /restore —
    # declared explicitly rather than assumed, because assuming ONE shape is the mistake this
    # contract exists to catch.
    "composition_derivative_edit": AtomDelete(
        "soft", "composition_work", flag="status", rest_reverse="/works/{project_id}"),
    "composition_motif_edit": AtomDelete(
        "soft", "motif", flag="status", rest_reverse="/motifs/{motif_id}/restore"),
    "composition_arc_edit": AtomDelete(
        "soft", "outline_node", rest_reverse="/arcs/{node_id}/restore"),
    "composition_arc_template_edit": AtomDelete(
        "soft", "arc_template", flag="status", rest_reverse="/arc-templates/{arc_id}/restore"),
    "composition_error_block_edit": AtomDelete(
        "soft", "chapter_error_block", rest_reverse="/error-blocks/{block_id}/restore"),
    "composition_structure_template_edit": AtomDelete(
        "soft", "structure_template", rest_reverse="/templates/{template_id}/restore"),
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
    # ── REVISION tier: these destroy no row, they roll authored PROSE back ──
    # Both were invisible to the previous gate: its `_DESTRUCTIVE` allowlist held only row verbs,
    # so `revert_all` passed as benign despite server.py:3221 calling it "destructive+irreversible".
    "composition_authoring_run_manage": AtomDelete(
        "revision",
        why="`revert_all` restores every drafted/accepted unit to its `pre_revision_id`, so the "
            "prose is recoverable through the chapter revision chain rather than an archive flag. "
            "It is irreversible FROM THE UI, which is why it is Tier-W confirm-gated — the confirm "
            "token is the guarantee here, standing in for a reverse op.",
    ),
    "composition_authoring_run_review": AtomDelete(
        "revision",
        why="`reject_unit` reverts one unit (and cascades downstream) back to its "
            "`pre_revision_id`. Same guarantee as revert_all at single-unit granularity: the "
            "revision chain holds the prose, so nothing the author wrote is unrecoverable.",
    ),
}


@functools.lru_cache(maxsize=1)
def _live_tools():
    """Every registered tool, from the REAL MCP registry.

    Imported, not regex-parsed: `tests/conftest.py` provides the env the settings model needs, so
    the import that the earlier version of this gate declared impossible is in fact what
    `test_mcp_server.py` has been doing all along.
    """
    from app.mcp.server import mcp_server

    return asyncio.run(mcp_server.list_tools())


def _declared_families() -> dict[str, set[str]]:
    """{tool_name: {op, …}} for every unified op-dispatch tool, read from its published schema."""
    out: dict[str, set[str]] = {}
    for t in _live_tools():
        enum = (t.inputSchema.get("properties", {}).get("op") or {}).get("enum")
        if enum:
            out[t.name] = set(enum)
    return out


def _destructive_families() -> dict[str, set[str]]:
    return {
        tool: ops for tool, ops in _declared_families().items()
        if (_DESTRUCTIVE | _REVERSION) & ops
    }


def _legacy_destructive_doors() -> dict[str, str | None]:
    """{tool_name: superseded_by} for standalone (non-op-dispatch) tools that destroy something.

    These are the 12 pre-unification `*_delete` / `*_archive` / `*_unbind` / `revert_all` tools.
    They are still registered and still callable, so they are still doors onto the same rows — and
    the previous gate, which only looked at op-dispatch classes, could not see a single one.
    """
    families = _declared_families()
    verbs = _DESTRUCTIVE | _REVERSION
    out: dict[str, str | None] = {}
    for t in _live_tools():
        if t.name in families:
            continue
        tail = t.name.removeprefix("composition_")
        if any(tail.endswith(v) or f"_{v}" in tail or tail.startswith(v) for v in verbs):
            out[t.name] = (t.meta or {}).get("superseded_by")
    return out


def test_the_registry_actually_yields_the_families():
    """A gate that silently matches nothing passes forever. Pin that it sees real families."""
    fams = _declared_families()
    assert len(fams) >= 15, f"only found {len(fams)} op-dispatch tools — discovery has drifted"
    assert "composition_canon_rule_edit" in fams


def test_the_registry_sees_the_shapes_the_REGEX_could_not():
    """The class layouts that each silently cost the earlier gate a family while it reported green.

    `composition_arc_edit` carries a docstring before `op:`; `composition_structure_template_edit`
    carries `#` comments. Both are invisible in a JSON schema — which is the point — but they are
    named here so a future regression to source-parsing is caught by the test that documents why.
    """
    fams = _declared_families()
    assert "composition_arc_edit" in fams
    assert "composition_structure_template_edit" in fams, (
        "this family HAS an `archive` op — missing it means a destructive op ships unchecked"
    )


def test_every_op_verb_is_CLASSIFIED():
    """No benign-by-default. An allowlist of destructive verbs lets a new `purge`/`remove`/`prune`
    through silently, which is exactly how `revert_all` — labelled destructive in its own source
    comment — passed the previous gate."""
    seen = set().union(*_declared_families().values())
    unknown = sorted(seen - _CLASSIFIED)
    assert not unknown, (
        f"unclassified op verbs: {unknown}\n\nAdd each to _DESTRUCTIVE (removes/hides a row), "
        f"_REVERSION (rolls authored prose back), _REVERSE (an undo) or _BENIGN. Deciding is the "
        f"point — a verb nobody classified is a verb nobody checked."
    )


def test_every_destructive_family_has_DECLARED_its_tier():
    """The anti-drift property. A new `*_edit` with a delete op cannot ship without saying whether
    what it removes is recoverable — which is exactly what nobody was forced to say before."""
    undeclared = sorted(set(_destructive_families()) - set(CONTRACT))
    assert not undeclared, (
        "these families have a destructive op but no row in CONTRACT:\n  "
        + "\n  ".join(undeclared)
        + "\n\nDeclare the tier. `soft` needs its flag column + a reverse op; `hard` needs a "
          "written reason why losing the row costs the author nothing."
    )


def test_the_contract_has_no_stale_rows():
    """A family that lost its destructive op should lose its row, or the SoT rots into fiction."""
    fams = _destructive_families()
    stale = sorted(k for k in CONTRACT if k not in fams)
    assert not stale, f"CONTRACT rows for families with no destructive op: {stale}"


def test_every_LEGACY_destructive_door_resolves_to_a_declared_family():
    """The 12 standalone `*_delete`/`*_archive` tools are still registered and still callable, so
    they are still doors onto the same rows. Each carries `superseded_by` pointing at the unified
    family — follow that edge rather than hand-maintaining a map, and a legacy door whose successor
    was never declared (or which lost its `superseded_by`) fails here."""
    doors = _legacy_destructive_doors()
    assert len(doors) >= 12, f"only found {len(doors)} legacy destructive doors — discovery drifted"
    broken = {
        name: sup for name, sup in doors.items()
        if sup is None or sup not in CONTRACT
    }
    assert not broken, (
        "legacy destructive tools that do not resolve to a declared family:\n  "
        + "\n  ".join(f"{k} → superseded_by={v!r}" for k, v in sorted(broken.items()))
        + "\n\nA still-registered tool is a live door onto the row. Point it at the unified "
          "family (and declare that family) or de-register it."
    )


@pytest.mark.parametrize("tool", sorted(k for k, v in CONTRACT.items() if v.tier == "soft"))
def test_a_soft_delete_exposes_a_REVERSE_op(tool):
    """`canon_rules.restore` calls itself 'the UNDO the DELETE promises'. If a family declares soft
    but exposes no way back, the promise is unkeepable — and the author only finds out after."""
    ops = _declared_families()[tool]
    assert _REVERSE & ops, (
        f"{tool} declares tier=soft but exposes none of {sorted(_REVERSE)} — the row is hidden "
        f"with no way to bring it back, which is worse than a hard delete because it looks "
        f"recoverable."
    )


@pytest.mark.parametrize(
    "tool,route",
    sorted((k, v.rest_reverse) for k, v in CONTRACT.items() if v.tier == "soft"),
)
def test_a_soft_delete_exposes_the_reverse_to_the_HUMAN_too(tool, route):
    """The MCP `restore` op is the AGENT's door. This is the author's.

    Checking only MCP is how F3 shipped an agent-only undo: scene_link and entity_override went
    soft + `op=restore`, the row survived — and with no REST route and `NOT is_archived` on every
    list read, the author could neither restore it nor discover its id. The previous version of
    this gate passed that, because it inspected one surface of three.
    """
    assert route, f"{tool} declares tier=soft but names no `rest_reverse` — say where the author "\
                  f"clicks to undo, or the promise is only kept for the agent."
    routers = "\n".join(
        p.read_text(encoding="utf-8") for p in (_ROOT / "app" / "routers").glob("*.py")
    )
    assert re.search(rf'@router\.(post|patch)\(\s*"{re.escape(route)}"', routers), (
        f"{tool} declares tier=soft with the author's undo at `{route}`, but no router exposes "
        f"it. The row is hidden and only an MCP client can bring it back — which is worse than a "
        f"hard delete, because the delete now LOOKS recoverable."
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


@pytest.mark.parametrize("tool", sorted(k for k, v in CONTRACT.items() if v.tier == "revision"))
def test_a_revision_revert_actually_has_a_revision_to_go_back_to(tool):
    """tier=revision claims the prose survives in the chapter revision chain. That claim is only
    true if the run unit actually captured a pre-revision to restore — the same check in spirit as
    `test_a_soft_delete_has_somewhere_to_put_the_flag`: a declared guarantee must have a mechanism
    behind it, not just a sentence."""
    src = _RUN_SERVICE.read_text(encoding="utf-8")
    # Both halves, not just the name: the column EXISTING proves nothing (migrate.py mentions it
    # too, which is how a first attempt at this test passed against the wrong file). The guarantee
    # is that the revert path reads the captured revision AND hands it to a restore.
    assert re.search(r"if\s+\w+\.pre_revision_id\s+is\s+not\s+None", src), (
        f"{tool} declares tier=revision, but the revert path never checks `pre_revision_id` — "
        f"nothing proves a pre-revision was captured before the prose was overwritten."
    )
    assert re.search(r"await\s+restore\(", src), (
        f"{tool} declares tier=revision, but authoring_run_service.py never calls `restore(...)` "
        f"— the captured revision is read and then not used, so the revert is unrecoverable."
    )


@pytest.mark.parametrize("tool", sorted(k for k, v in CONTRACT.items() if v.tier != "soft"))
def test_a_non_soft_delete_must_JUSTIFY_itself(tool):
    """Uniformity is not the goal — motif_link's hard delete is correct. But the reason has to be
    written down, because the next person will otherwise copy the shape onto a family whose row
    DOES carry authored content, which is exactly how scene_link happened."""
    why = CONTRACT[tool].why
    assert len(why) > 60, (
        f"{tool} declares tier={CONTRACT[tool].tier} without a real justification. Say why losing "
        f"this row costs the author nothing (no authored text? trivially re-creatable? held in "
        f"the revision chain?)."
    )

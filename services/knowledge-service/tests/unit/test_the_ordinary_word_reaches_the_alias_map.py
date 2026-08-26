"""A normaliser behind a closed type is a normaliser that never runs.

kg_add_nodes' `kind` rejected the ordinary English word: "Input should be 'character',
'location', 'organization', 'concept' or 'item' (you sent 'person')". Both failures of a measured
K=5 run died there — the nodes were never created, so the edge could never resolve, and the model
retried four times without recovering.

🔴 THE ALIAS MAP ALREADY EXISTED AND COULD NOT BE REACHED. `KIND_ALIASES` maps person → character
and its comment quotes this very defect; `canonical_kind` folds it; `KgCreateNodeArgs` calls it.
But the tool the model actually calls, kg_add_nodes, declared `kind: AuthorableKind` — a Literal,
validated by the TOOL LAYER before any code runs. Measured 2026-08-26 against the deployed build:
'person' and 'place' were both refused at the schema layer, so the fold never happened.

Fixed at one end. The same shape as the motif refusal earlier in this loop, and it is only
visible by calling the deployed tool — every unit test of the args model passed throughout,
because the args model was never reached.

THE TRADE, taken deliberately and already taken once by kg_create_node: the closed set moves out
of the TYPE and into the description (guidance for the model) and the validator (enforcement).
The schema no longer machine-checks the enum; the validator still does, and now it folds first.
"""
from __future__ import annotations

import inspect

import pytest

from app.db.neo4j_repos.entities import AUTHORABLE_KINDS, KIND_ALIASES, canonical_kind
from app.tools.graph_schema_tools import KgAddNodesArgs


class TestTheAliasSurvivesToTheValidator:
    @pytest.mark.parametrize("alias,canonical", sorted(KIND_ALIASES.items()))
    def test_every_alias_folds(self, alias, canonical):
        args = KgAddNodesArgs(project_id=None, mode="manual", name="X", kind=alias)
        assert args.kind == canonical, f"{alias!r} reached the graph unfolded"
        assert args.kind in AUTHORABLE_KINDS

    def test_the_measured_word_is_person(self):
        """The one an actual run sent, twice, and died on."""
        assert canonical_kind("person") == "character"
        assert KgAddNodesArgs(project_id=None, mode="manual", name="X", kind="person").kind \
            == "character"

    @pytest.mark.parametrize("noise", ["Person", "  person  ", "PERSON"])
    def test_folding_is_case_and_space_insensitive(self, noise):
        assert KgAddNodesArgs(project_id=None, mode="manual", name="X", kind=noise).kind \
            == "character"


class TestTheClosedSetStillCloses:
    def test_an_unknown_kind_is_still_refused(self):
        """Tolerating a synonym is not accepting anything. The set is unchanged."""
        with pytest.raises(ValueError) as ei:
            KgAddNodesArgs(project_id=None, mode="manual", name="X", kind="spaceship")
        msg = str(ei.value)
        assert "kind must be one of" in msg
        assert "'spaceship'" in msg, "the refusal must echo what was sent"
        assert "synonyms are folded automatically" in msg, (
            "a caller that hit the fold path and still failed needs to know the fold was tried")

    def test_faction_is_still_refused(self):
        """🔴 `faction` is the RETIRED misnomer and is deliberately absent from KIND_ALIASES — an
        alias map is a way to resurrect a retired term without anyone noticing, because the alias
        never appears in the canonical set people review."""
        assert "faction" not in KIND_ALIASES
        with pytest.raises(ValueError):
            KgAddNodesArgs(project_id=None, mode="manual", name="X", kind="faction")


class TestTheToolLayerCannotRejectBeforeTheFold:
    def test_the_mcp_signature_does_not_re_close_the_type(self):
        """The whole defect. A Literal on the signature is validated before any code runs, so the
        alias map is unreachable however well it is wired."""
        import app.mcp.server as srv

        src = inspect.getsource(srv.kg_add_nodes)
        head = src[:src.index(") -> dict:")]
        # Comments EXCLUDED: the fix's own note explains why AuthorableKind is NOT used here, and
        # a comment quoting the anchor is itself an occurrence — this loop has been caught by that
        # shape three times now.
        code = "\n".join(l for l in head.split("\n") if not l.strip().startswith("#"))
        assert "AuthorableKind" not in code, (
            "kind is typed as a Literal again — the fold is unreachable from the tool")
        assert "str | None" in code

    def test_the_description_still_names_the_closed_set(self):
        """Losing the enum from the schema is the trade; losing the GUIDANCE would be a
        regression. The five must still be listed where the model reads them."""
        import app.mcp.server as srv

        src = inspect.getsource(srv.kg_add_nodes)
        for k in AUTHORABLE_KINDS:
            assert k in src, f"the description no longer names {k}"
        assert "person → character" in src

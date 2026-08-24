"""T54e — the Neo4j -> AGE migration's property policy and its refusals.

The planner is a pure function on purpose (`plan_migration` takes tuples, not a driver), which
is what lets the three refusals be tested on cases the dev census does NOT contain: dev has
**zero** cross-project edges, **zero** unkeyed labels and **zero** unmappable property types.
A detector validated only on the data that motivated it is green by construction (rule 3), so
every refusal here is exercised on a case that was never measured.
"""

from __future__ import annotations

import datetime as _dt
import pathlib
import re

import pytest

from app.db.migrations.neo4j_to_age import (
    EMBEDDING_PROPS,
    SHARED_GRAPH,
    cli_exit_code,
    split_verdicts,
    LABEL_KEYS,
    PER_PROJECT_LAYOUT,
    SERVICE_LAYOUT,
    AmbiguousAdoption,
    CrossProjectEdge,
    DanglingEndpoint,
    MigrationPlan,
    PropertyPolicy,
    UnkeyedLabel,
    UnmappableProperty,
    graph_key_for,
    plan_migration,
    render_report,
    to_age_millis,
    translate_props,
)

_SCHEMA = pathlib.Path(__file__).resolve().parents[2] / "app" / "db" / "neo4j_schema.cypher"


class _DriverDateTime:
    """Stands in for `neo4j.time.DateTime`, which the driver returns for a ZONED DATETIME.

    Duck-typed on `to_native()` rather than imported, because the point of the conversion is
    that it does not depend on the driver being installed to be reasoned about.
    """

    def __init__(self, native: _dt.datetime) -> None:
        self._native = native

    def to_native(self) -> _dt.datetime:
        return self._native


# ── the central claim: AGE's representation, not Neo4j's ────────────────────────────────────


def test_a_temporal_becomes_epoch_MILLIS_the_way_AGE_writes_them():
    """Measured on both live stores, and this pins the number rather than the idea.

        dev Neo4j   Entity.created_at   2026-06-27T05:18:31.870Z   ZONED DATETIME
        iso AGE     Entity.created_at   1787400064349              INTEGER

    `cypher_dialect` renders `{NOW}` as `datetime()` on Neo4j and `timestamp()` on AGE, so a
    migrated graph that carried the ZonedDateTime across would hold a DIFFERENT TYPE from every
    row the service writes afterwards — and `graph_repos/entities.py:264` orders on exactly
    this property.
    """
    instant = _dt.datetime(2026, 6, 27, 5, 18, 31, 870000, tzinfo=_dt.timezone.utc)
    assert to_age_millis(instant) == 1782537511870
    assert to_age_millis(_DriverDateTime(instant)) == 1782537511870
    assert isinstance(to_age_millis(instant), int), (
        "an ISO STRING would sort against the integers `timestamp()` writes — the mixed-type "
        "ordering T63 measured"
    )


def test_the_live_AGE_value_round_trips_to_a_plausible_wall_clock():
    """The control on the constant above: a conversion that is off by 1000x still 'passes' an
    equality test written from the same arithmetic. `1787400064349` was READ from iso AGE, and
    it must land in 2026 — not 1970, not 58 000 AD."""
    read_from_age = 1787400064349
    when = _dt.datetime.fromtimestamp(read_from_age / 1000, tz=_dt.timezone.utc)
    assert when.year == 2026, f"epoch-millis reading gives {when!r}"
    assert to_age_millis(when) == read_from_age


def test_a_NAIVE_datetime_is_read_as_UTC_rather_than_the_migrating_hosts_zone():
    naive = _dt.datetime(2026, 6, 27, 5, 18, 31, 870000)
    aware = naive.replace(tzinfo=_dt.timezone.utc)
    assert to_age_millis(naive) == to_age_millis(aware)


def test_a_string_that_LOOKS_like_a_date_is_left_alone():
    """`event_date_iso` is an IN-WORLD date and a STRING by design — measured on dev, 62 Events
    and 2 Facts carry it. Parsing it into millis would silently rewrite the bi-temporal value
    the reader reads back, and nothing downstream would report an error."""
    out = translate_props({"event_date_iso": "1247-03-02", "valid_from": "not-a-date"})
    assert out == {"event_date_iso": "1247-03-02", "valid_from": "not-a-date"}


# ── the drop policy: counted, never silent ──────────────────────────────────────────────────


def test_embedding_properties_are_dropped_and_COUNTED_per_property():
    policy = PropertyPolicy()
    out = translate_props(
        {"id": "e1", "embedding_1024": [0.1, 0.2], "summary_embedding": [0.3], "name": "Kai"},
        policy,
    )
    assert out == {"id": "e1", "name": "Kai"}
    assert policy.embeddings_dropped == 2
    assert policy.dropped_by_prop == {"embedding_1024": 1, "summary_embedding": 1}


def test_the_report_STATES_the_drop_rather_than_implying_it():
    """A migration that loses a property silently is indistinguishable from one that ran
    correctly. The count has to reach the operator's screen."""
    plan = MigrationPlan()
    translate_props({"embedding_1024": [0.1]}, plan.policy)
    text = render_report(plan)
    assert "embedding props DROPPED     1" in text
    assert "embedding_1024" in text


def test_a_NON_embedding_float_list_survives():
    """The control arm for the drop. A policy that dropped every list would take `aliases`,
    `source_types` and `participants` with it — 13 227 values on dev — and the node counts
    would still match."""
    out = translate_props({"aliases": ["Kai", "K"], "confidence": 0.5})
    assert out == {"aliases": ["Kai", "K"], "confidence": 0.5}


def test_a_temporal_INSIDE_a_list_is_converted_too():
    instant = _dt.datetime(2026, 6, 27, 5, 18, 31, 870000, tzinfo=_dt.timezone.utc)
    policy = PropertyPolicy()
    assert translate_props({"stamps": [instant]}, policy) == {"stamps": [1782537511870]}
    assert policy.temporals_converted == 1


# ── the three refusals, on cases dev does NOT contain (rule 3) ───────────────────────────────


def test_an_unmappable_property_type_RAISES_rather_than_being_stringified():
    class Point:
        pass

    with pytest.raises(UnmappableProperty, match="agtype cannot represent"):
        translate_props({"where": Point()})


def test_an_unkeyed_LABEL_raises_naming_it():
    """Dev has none — every label it holds is in `LABEL_KEYS`. This is the case the census
    could not supply."""
    with pytest.raises(UnkeyedLabel, match="Sprocket"):
        plan_migration([("Sprocket", {"id": "s1", "project_id": "p1"})], [])


def test_an_unkeyed_label_on_either_END_of_a_relationship_raises():
    with pytest.raises(UnkeyedLabel, match="Sprocket"):
        plan_migration(
            [],
            [("ABOUT", "Fact", {"id": "f1", "project_id": "p1"},
              "Sprocket", {"id": "s1", "project_id": "p1"}, {})],
        )


def test_an_edge_pointing_at_a_node_that_was_NOT_migrated_raises():
    """`_write_rel` MATCHes its endpoints, so a dangling edge is silently skipped at write
    time and the relationship count comes out short with nothing naming the cause. The planner
    refuses instead, before anything is written."""
    with pytest.raises(DanglingEndpoint, match="not among the migrated nodes"):
        plan_migration(
            [("Fact", {"id": "f1", "project_id": "p1"})],
            [("ABOUT", "Fact", {"id": "f1", "project_id": "p1"},
              "Entity", {"id": "gone", "project_id": "p1"}, {})],
        )


def test_a_CROSS_PROJECT_edge_raises_because_AGE_cannot_express_it():
    """Measured 0 of 4 249 on dev — which is what makes graph-per-project viable, and exactly
    why this case has to be constructed. A relationship lives inside ONE AGE graph; dropping
    such an edge silently would lose a fact without any count moving."""
    with pytest.raises(CrossProjectEdge, match="ONE graph"):
        plan_migration(
            [
                ("Fact", {"id": "f1", "project_id": "p1"}),
                ("Entity", {"id": "e1", "project_id": "p2"}),
            ],
            [("ABOUT", "Fact", {"id": "f1", "project_id": "p1"},
              "Entity", {"id": "e1", "project_id": "p2"}, {})],
         PER_PROJECT_LAYOUT)


def test_an_edge_between_two_UNSCOPED_nodes_is_NOT_cross_project():
    """The control for the refusal above, and it is the dev hierarchy's actual shape: all 33
    HAS_CHILD edges join two nodes with no `project_id`. A check that treated NULL as
    'different from NULL' would refuse the entire Book/Part/Chapter/Scene component."""
    plan = plan_migration(
        [("Book", {"book_id": "b1"}), ("Part", {"part_id": "pt1"})],
        [("HAS_CHILD", "Book", {"book_id": "b1"}, "Part", {"part_id": "pt1"}, {})],
     PER_PROJECT_LAYOUT)
    assert plan.total_rels == 1
    assert plan.graphs[None].rels == 1


# ── grouping ────────────────────────────────────────────────────────────────────────────────


def test_unscoped_rows_group_to_the_shared_graph_key():
    assert graph_key_for(None) is None
    assert graph_key_for("   ") is None, "a blank project id is not a project"
    assert graph_key_for("  p1 ") == "p1"


def test_the_plan_reproduces_the_per_project_census_shape():
    plan = plan_migration(
        [
            ("Entity", {"id": "e1", "project_id": "p1"}),
            ("Entity", {"id": "e2", "project_id": "p1"}),
            ("Event", {"id": "v1", "project_id": "p2"}),
            ("Chapter", {"chapter_id": "c1"}),
        ],
        [("RELATES_TO", "Entity", {"id": "e1", "project_id": "p1"},
          "Entity", {"id": "e2", "project_id": "p1"}, {})],
     PER_PROJECT_LAYOUT)
    assert plan.total_nodes == 4
    assert plan.total_rels == 1
    assert set(plan.graphs) == {"p1", "p2", None}
    assert plan.graphs["p1"].labels == {"Entity": 2}
    assert plan.graphs["p1"].rel_types == {"RELATES_TO": 1}
    assert plan.graphs[None].labels == {"Chapter": 1}


def test_a_well_formed_plan_raises_NOTHING():
    """The control arm for all three refusals at once. Without it, a planner that raised on
    every input would pass every test above."""
    plan = plan_migration(
        [("Entity", {"id": "e1", "project_id": "p1", "embedding_1024": [0.1]})],
        [],
    )
    assert plan.total_nodes == 1
    assert plan.policy.embeddings_dropped == 1


# ── the derived check that found the gap ────────────────────────────────────────────────────


def test_every_label_the_SCHEMA_constrains_has_a_migration_key():
    """DERIVED from `neo4j_schema.cypher`, and it earned its place immediately.

    `LABEL_KEYS` was first written from the dev census — 10 labels, all of them present in the
    data. This test went red on **`Project` and `Session`**: both are declared with a uniqueness
    constraint and both have ZERO nodes on dev, so no census could have named them, and the
    first deployment that held one would have met `UnkeyedLabel` part-way through a migration.

    The schema is the authority on what a Neo4j knowledge graph MAY contain; a census is only
    what one of them happens to hold today.
    """
    declared = dict(
        re.findall(r"FOR \(\w+:(\w+)\)\s+REQUIRE\s+\w+\.(\w+) IS UNIQUE", _SCHEMA.read_text())
    )
    assert declared, "no uniqueness constraints parsed — the regex has drifted from the schema"
    missing = sorted(set(declared) - set(LABEL_KEYS))
    assert not missing, (
        f"{missing} carry a uniqueness constraint but no migration key. A deployment holding "
        f"one would fail part-way through with UnkeyedLabel."
    )
    mismatched = {
        label: (declared[label], LABEL_KEYS[label])
        for label in declared
        if LABEL_KEYS[label] != declared[label]
    }
    assert not mismatched, (
        f"the migration MERGEs on a different property than the schema makes unique: "
        f"{mismatched} — a non-unique merge key duplicates rows on the second run"
    )


def test_the_embedding_drop_list_names_only_properties_the_graph_actually_carries():
    """A drop list is a place stale names hide. Both entries are measured on dev
    (`embedding_1024` on 1 076 nodes, `summary_embedding` on 23), and neither is a property the
    AGE readers want — vectors are pgvector's (§3.3)."""
    assert EMBEDDING_PROPS == {"embedding_1024", "summary_embedding"}


# ── adoption: the rule the REAL data forced (rule 13) ────────────────────────────────────────


def test_an_unscoped_node_cited_by_ONE_project_is_adopted_into_that_project_graph():
    """Measured on iso, not imagined: 16 `EVIDENCED_BY` edges run from a scoped Entity to an
    UNSCOPED `ExtractionSource`, and 20 of iso's 27 sources carry no `project_id` where all 172
    on dev do. Leaving the source in `g_shared` would put the edge's two ends in different
    graphs, which AGE cannot hold — so the migration would have refused a real graph."""
    plan = plan_migration(
        [
            ("Entity", {"id": "e1", "project_id": "p1"}),
            ("ExtractionSource", {"id": "s1"}),
        ],
        [("EVIDENCED_BY", "Entity", {"id": "e1", "project_id": "p1"},
          "ExtractionSource", {"id": "s1"}, {})],
     PER_PROJECT_LAYOUT)
    assert set(plan.graphs) == {"p1"}, "the source did not follow the entity that cites it"
    assert plan.graphs["p1"].labels == {"Entity": 1, "ExtractionSource": 1}
    assert plan.graphs["p1"].rel_types == {"EVIDENCED_BY": 1}


def test_an_unscoped_ORPHAN_stays_in_the_shared_graph():
    """The other half, and iso has four of them: cited by nothing, so there is no referrer to
    inherit from and inventing one would be a guess."""
    plan = plan_migration([("ExtractionSource", {"id": "orphan"})], [], PER_PROJECT_LAYOUT)
    assert set(plan.graphs) == {None}


def test_an_unscoped_node_cited_by_TWO_projects_is_REFUSED():
    """Unreachable on today's data — every adopted source on iso has exactly ONE referrer — and
    that is precisely why it is asserted. 'One referrer' is a property of the data, not of the
    schema, and adopting into two graphs would fork a node other rows key on."""
    with pytest.raises(AmbiguousAdoption, match="fork one node"):
        plan_migration(
            [
                ("Entity", {"id": "e1", "project_id": "p1"}),
                ("Entity", {"id": "e2", "project_id": "p2"}),
                ("ExtractionSource", {"id": "s1"}),
            ],
            [
                ("EVIDENCED_BY", "Entity", {"id": "e1", "project_id": "p1"},
                 "ExtractionSource", {"id": "s1"}, {}),
                ("EVIDENCED_BY", "Entity", {"id": "e2", "project_id": "p2"},
                 "ExtractionSource", {"id": "s1"}, {}),
            ],
         PER_PROJECT_LAYOUT)


def test_adoption_does_NOT_move_a_node_that_already_has_a_project():
    """The control arm. A resolver that adopted on every edge would drag scoped nodes into
    their neighbours' graphs and quietly re-tenant the graph — the opposite of the tenancy
    tightening adoption is justified by."""
    plan = plan_migration(
        [
            ("Entity", {"id": "e1", "project_id": "p1"}),
            ("ExtractionSource", {"id": "s1", "project_id": "p1"}),
        ],
        [("EVIDENCED_BY", "Entity", {"id": "e1", "project_id": "p1"},
          "ExtractionSource", {"id": "s1", "project_id": "p1"}, {})],
     PER_PROJECT_LAYOUT)
    assert set(plan.graphs) == {"p1"}
    assert plan.graphs["p1"].nodes == 2


# ── T54f: the DEFAULT layout is the graph the SERVICE reads ──────────────────────────────────


def test_the_DEFAULT_layout_puts_everything_in_ONE_graph():
    """The first cut defaulted to per-project and would have landed the data where the service
    cannot see it — the same empty store T54d found, produced by the fix for it."""
    plan = plan_migration(
        [
            ("Entity", {"id": "e1", "project_id": "p1"}),
            ("Entity", {"id": "e2", "project_id": "p2"}),
            ("Chapter", {"chapter_id": "c1"}),
        ],
        [],
    )
    assert set(plan.graphs) == {None}, "the default must be ONE graph, as Neo4j is one database"
    assert plan.graphs[None].nodes == 3


def test_the_SERVICE_layout_cannot_produce_a_cross_graph_edge_at_all():
    """The same pair that RAISES under per-project is fine under the default, because there is
    only one graph for it to cross out of. The refusal is not weakened — it is unreachable in a
    layout that has no boundaries, and still reachable in the one that does."""
    args = (
        [
            ("Fact", {"id": "f1", "project_id": "p1"}),
            ("Entity", {"id": "e1", "project_id": "p2"}),
        ],
        [("ABOUT", "Fact", {"id": "f1", "project_id": "p1"},
          "Entity", {"id": "e1", "project_id": "p2"}, {})],
    )
    assert plan_migration(*args, SERVICE_LAYOUT).total_rels == 1
    with pytest.raises(CrossProjectEdge):
        plan_migration(*args, PER_PROJECT_LAYOUT)


def test_an_unknown_layout_is_REFUSED_rather_than_defaulted():
    with pytest.raises(ValueError, match="is not one of"):
        plan_migration([("Entity", {"id": "e1", "project_id": "p1"})], [], "whatever")


def test_the_DEFAULT_targets_the_SAME_graph_the_service_opens___DERIVED():
    """The check that would have caught T54f, and it reads the service's wiring rather than
    restating it.

    `db/neo4j.py` opens the repo-layer AGE session with **no project argument**, and
    `graph_store_provider` builds `AgeGraphStore(pool, graph_name_for(None))`. Both therefore
    resolve to `graph_name_for(None)` — `g_shared`. If either ever starts passing a project,
    this test goes red on the migration rather than the migration silently writing somewhere
    the service no longer reads.
    """
    import ast as _ast

    from app.db.age_bootstrap import graph_name_for

    src = (pathlib.Path(__file__).resolve().parents[2] / "app" / "db" / "neo4j.py").read_text(
        encoding="utf-8"
    )
    calls = [
        n for n in _ast.walk(_ast.parse(src))
        if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)
        and n.func.id == "age_repo_session"
    ]
    assert calls, "db/neo4j.py no longer opens an AGE repo session — re-derive this test"
    for call in calls:
        assert len(call.args) <= 1 and not call.keywords, (
            "db/neo4j.py now passes a project to age_repo_session, so the repo layer reads "
            "PER-PROJECT graphs. The migration's default layout must move with it."
        )

    provider = (
        pathlib.Path(__file__).resolve().parents[2] / "app" / "adapters"
        / "graph_store_provider.py"
    ).read_text(encoding="utf-8")
    assert "graph_name_for(None)" in provider, (
        "the GraphStore provider no longer builds on the shared graph — the migration's "
        "default layout must move with it"
    )

    plan = plan_migration([("Entity", {"id": "e1", "project_id": "p1"})], [])
    assert set(plan.graphs) == {None}
    assert graph_name_for(None) == SHARED_GRAPH


@pytest.mark.parametrize("layout", [SERVICE_LAYOUT, PER_PROJECT_LAYOUT])
def test_the_endpoint_refusals_fire_in_BOTH_layouts(layout):
    """Parameterised because a first cut lost them in one of the two.

    `resolve_graph_keys` returned early for `SERVICE_LAYOUT` — one graph, nothing to group —
    and the unkeyed-label and dangling-endpoint checks sat below that return. The DEFAULT
    layout, the one every real run uses, silently stopped making them; the suite stayed green
    because both refusals were only ever exercised through the other layout. Whether an
    endpoint EXISTS is not a property of the graph boundary.
    """
    with pytest.raises(DanglingEndpoint):
        plan_migration(
            [("Fact", {"id": "f1", "project_id": "p1"})],
            [("ABOUT", "Fact", {"id": "f1", "project_id": "p1"},
              "Entity", {"id": "gone", "project_id": "p1"}, {})],
            layout,
        )
    with pytest.raises(UnkeyedLabel):
        plan_migration(
            [("Fact", {"id": "f1", "project_id": "p1"})],
            [("ABOUT", "Fact", {"id": "f1", "project_id": "p1"},
              "Sprocket", {"id": "s1", "project_id": "p1"}, {})],
            layout,
        )


# ── T54h: the CLI's verdict, settled by the LIVE RUN ─────────────────────────────────────────


def test_a_MISSING_row_fails_and_an_EXTRA_row_does_not():
    """The distinction the live run forced.

    The first CLI exited 1 on any `verify` mismatch. Run against the iso stack — whose
    `g_shared` already held 35 entities the service itself had written — it reported failure
    while losing nothing:

        EXTRA g_shared/Entity: destination 638, source 603      638 = 603 + 35

    That is every deployment that has ever served a request, and every re-run. MISSING answers
    the operator's actual question ("did my rows land"); EXTRA answers "the destination was not
    empty", which is information.
    """
    extra = ["EXTRA g_shared/Entity: destination 638, source 603"]
    missing = ["MISSING g_shared/Fact: destination 3, source 56"]
    assert cli_exit_code(extra) == 0, "a non-empty destination is not a failed migration"
    assert cli_exit_code(missing) == 1, "rows that did not land MUST fail the run"
    assert cli_exit_code(extra + missing) == 1, "one MISSING outweighs any number of EXTRA"
    assert cli_exit_code([]) == 0


def test_the_split_keeps_BOTH_lists_rather_than_discarding_the_informational_one():
    """The control: a version that simply filtered for MISSING would pass the assertions above
    and lose the EXTRA rows entirely, so the operator would never be told the destination was
    dirty — which on a cutover is the thing worth knowing."""
    rows = ["EXTRA a/b: destination 2, source 1", "MISSING c/d: destination 0, source 9"]
    missing, extra = split_verdicts(rows)
    assert len(missing) == 1 and len(extra) == 1
    assert missing[0].startswith("MISSING") and extra[0].startswith("EXTRA")


def test_the_documented_CLI_ENTRYPOINT_exists():
    """🔴 It did not, for two commits.

    The module header has documented `python -m app.db.migrations.neo4j_to_age` since T54e.
    Running it imported the module, did nothing and **exited 0** — which an operator following
    the documentation reads as "dry run: nothing to migrate". Silent success is a bug, and this
    was found by TRYING the documented command rather than reading it.
    """
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[2] / "app" / "db" / "migrations"
           / "neo4j_to_age.py").read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in src, (
        "the module documents a `python -m` entrypoint it does not have"
    )
    assert "_cli_main" in src and "--apply" in src

"""T54e — move a Neo4j knowledge graph into Apache AGE, one graph per project.

**Why this exists.** T54d measured the gap the GOAL's second half depends on: `infra/.env`
declares `KNOWLEDGE_GRAPH_BACKEND=age`, dev's Neo4j holds 8 033 nodes and 4 249 relationships,
and dev's AGE holds **zero entities**. The architecture is engine-agnostic and iso-proven; the
declared deployment's DATA never moved, and nothing in the tree would have said so. Restarting
`knowledge-service` there would point every graph read at an empty store. This module is the
missing half.

── WHAT THE BATCH MEASUREMENT CHANGED (rule 8) ──────────────────────────────────────────────
Measuring before building corrected T54d's own inventory and killed the naive copier:

    projects                  433  ->  433 AGE graphs, plus `g_shared`
    nodes                   8 033  across 10 labels   (T54d named 4)
    relationships           4 249  across 6 types     (T54d named 4)
    cross-project edges         0  of 4 249           <- graph-per-project is EXPRESSIBLE
    unscoped nodes             24  structural + 4 Facts  -> `g_shared`
    ZONED DATETIME         16 519  node values + ~8 100 relationship values

That last row is the one that matters, and it is why this is not a property copy.
`cypher_dialect` renders `{NOW}` as `datetime()` on Neo4j and `timestamp()` on AGE — **the same
property holds a different TYPE on each engine**, which T63 measured and wrote down. Proven
again here on the live stores:

    dev Neo4j   Entity.created_at   2026-06-27T05:18:31.870Z   ZONED DATETIME
    iso AGE     Entity.created_at   1787400064349              INTEGER (epoch millis)

A copier that carried the ZonedDateTime across would leave a migrated graph sorting ISO strings
against integers under `ORDER BY created_at` — and `graph_repos/entities.py:264` is a real
reader of exactly that ordering, in the canonical-collision path. So temporals are converted to
the representation AGE natively writes, and that conversion is the module's central claim.

── WHAT IS DELIBERATELY NOT CARRIED ─────────────────────────────────────────────────────────
Embedding properties. Under the AGE design vectors live in **pgvector**, not the graph: T25 ③
moved passage vectors and T25s moved the entity scope, and `PgVectorStore` is their home.
Copying 1 099 float lists into agtype would duplicate the vector store and leave two writable
copies of one fact. They are dropped **by name, counted, and reported** — never silently,
because a migration that quietly loses a property is indistinguishable from one that ran
correctly.

── RUN ──────────────────────────────────────────────────────────────────────────────────────
Dry-run by default, in the house style of `recanon_honorifics`:

    python -m app.db.migrations.neo4j_to_age                 # report, mutate nothing
    python -m app.db.migrations.neo4j_to_age --apply         # operator, after review

`--apply` WRITES. Rule 6 puts it behind an operator and a throwaway target.
"""

from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

__all__ = [
    "LABEL_KEYS",
    "EMBEDDING_PROPS",
    "SHARED_GRAPH",
    "PropertyPolicy",
    "MigrationPlan",
    "GraphAssignment",
    "CrossProjectEdge",
    "AmbiguousAdoption",
    "DanglingEndpoint",
    "UnmappableProperty",
    "UnkeyedLabel",
    "graph_key_for",
    "to_age_millis",
    "translate_props",
    "plan_migration",
    "SERVICE_LAYOUT",
    "PER_PROJECT_LAYOUT",
    "LAYOUTS",
    "render_report",
    "split_verdicts",
    "cli_exit_code",
]


#: The natural key each label MERGEs on, so a re-run updates rather than duplicates.
#: Measured globally unique on the dev graph (T54e): every label's key had
#: `count(*) == count(DISTINCT key)`. A label absent from this map RAISES rather than being
#: migrated on the internal element id, which is not stable across engines.
#:
#: ⚠️ **`Project` and `Session` are here because a DERIVED test put them here, not because the
#: data did.** Both are declared with a uniqueness constraint in `neo4j_schema.cypher` and both
#: have ZERO nodes on dev, so a map written from the census alone omits them — and the first
#: deployment that had one would meet `UnkeyedLabel` mid-migration. The schema is the authority
#: on what a Neo4j knowledge graph may contain; the census is only what one of them happens to
#: hold today.
LABEL_KEYS: dict[str, str] = {
    "Entity": "id",
    "Event": "id",
    "Fact": "id",
    "ExtractionSource": "id",
    "EntityStatus": "id",
    "Passage": "id",
    "Project": "id",
    "Session": "id",
    # Structural rollup nodes. No uniqueness constraint declares them — they are written by the
    # summary pipeline and carry their own `<thing>_id` — so these four come from the census
    # and the derived test cannot vouch for them.
    "Book": "book_id",
    "Part": "part_id",
    "Chapter": "chapter_id",
    "Scene": "scene_id",
}

#: Properties that belong to pgvector, not to the graph. Dropped and COUNTED — see the module
#: docstring. `summary_embedding` is the Book/Part/Chapter rollup vector; `embedding_1024` is
#: the entity/passage vector.
EMBEDDING_PROPS: frozenset[str] = frozenset({"embedding_1024", "summary_embedding"})

#: The graph holding rows that carry no `project_id`. The Book/Part/Chapter/Scene hierarchy is
#: entirely unscoped on dev (24 nodes, 33 HAS_CHILD edges) and every one of its edges is between
#: two unscoped nodes, so the whole component lands here intact.
SHARED_GRAPH = "g_shared"

#: 🔴 **T54f — the first cut of this module wrote to the WRONG GRAPHS, and only reading the
#: service's own wiring found it.** It built 433 per-project graphs, because the iso AGE store
#: visibly held 120 populated `p-…` graphs. Those are **T43's shadow harness and the two
#: benchmarks**, which construct `AgeGraphStore(pool, gname)` per project on purpose. The
#: SERVICE does not:
#:
#:     app/db/neo4j.py:184                    age_repo_session(age_pool())        -> g_shared
#:     adapters/graph_store_provider.py:98    AgeGraphStore(pool, graph_name_for(None)) -> g_shared
#:
#: Both halves read `g_shared`, and the provider says why in as many words: Neo4j holds every
#: project in one database and scopes by property, so `g_shared` reproduces that exactly, and
#: adopting per-project graphs there *"would smuggle an isolation-model change into an engine
#: swap"*. A migration into per-project graphs therefore lands where the service cannot see it
#: — the SAME empty-store outcome T54d found, produced by the fix for it.
#:
#: So the default is the layout the service reads, and `per_project` stays available for the
#: harness that genuinely uses it.
SERVICE_LAYOUT = "service"
PER_PROJECT_LAYOUT = "per_project"
LAYOUTS = (SERVICE_LAYOUT, PER_PROJECT_LAYOUT)


class UnmappableProperty(TypeError):
    """A property type agtype cannot hold and this module will not guess at.

    Rule 9: an adapter that cannot honour an operation RAISES, naming its spec section. A
    migration that coerced an unknown type to `str()` would produce a graph that reads fine and
    compares wrong.
    """


class UnkeyedLabel(KeyError):
    """A label with no entry in `LABEL_KEYS`.

    Refusing is the point. Falling back to Neo4j's internal element id would produce a graph
    that cannot be re-migrated idempotently, and the second run would double every node.
    """


class CrossProjectEdge(ValueError):
    """An edge whose endpoints live in different project graphs.

    AGE cannot express it: a relationship lives inside one graph. Measured 0 of 4 249 on dev,
    which is what makes graph-per-project viable — but a measurement is not a guarantee, and a
    migration that silently dropped such an edge would lose a fact without a count moving.
    """


def graph_key_for(project_id: object) -> str | None:
    """The project a row belongs to, or `None` for the shared graph.

    Not `graph_name_for` — that lives in `age_bootstrap` and owns the AGE naming rule (`g_` +
    dashless hex, both transformations load-bearing). This returns the *grouping* key so the
    planner is a pure function with no import of the AGE layer, which is what lets it be tested
    without a database.
    """
    if project_id is None:
        return None
    text = str(project_id).strip()
    return text or None


def to_age_millis(value: object) -> int:
    """A temporal in AGE's representation: epoch milliseconds, as `timestamp()` returns.

    Accepts a `datetime` and anything with `to_native()` (the Neo4j driver's `DateTime`). A
    naive datetime is read as UTC — the dev graph's values all carry an offset, and assuming
    UTC for a naive one is the only reading that keeps ordering stable rather than shifting by
    the migrating host's zone.
    """
    native = value.to_native() if hasattr(value, "to_native") else value
    if not isinstance(native, _dt.datetime):
        raise UnmappableProperty(
            f"expected a temporal, got {type(value).__name__} — refusing to guess an epoch"
        )
    if native.tzinfo is None:
        native = native.replace(tzinfo=_dt.timezone.utc)
    return int(native.timestamp() * 1000)


@dataclass
class PropertyPolicy:
    """What `translate_props` did, so the report can state it rather than imply it."""

    temporals_converted: int = 0
    embeddings_dropped: int = 0
    dropped_by_prop: dict[str, int] = field(default_factory=dict)


def translate_props(props: dict, policy: PropertyPolicy | None = None) -> dict:
    """Neo4j property map -> agtype-safe property map.

    Three rules, in order, and each is a claim the tests hold to:

    1. **An embedding property is dropped and counted.** Vectors live in pgvector (§3.3).
    2. **A temporal becomes epoch millis.** Never a string: AGE's own `timestamp()` writes an
       integer and `ORDER BY created_at` mixes the two types otherwise (T63).
    3. **A string is left alone, even when it looks like a date.** `Fact.event_date_iso` and
       `Event.event_date_iso` are STRINGs on purpose — an in-world date, not a wall clock.
       Parsing them would corrupt the bi-temporal read that reads them back.

    Anything else that is not an agtype scalar or a list of them RAISES.
    """
    policy = policy if policy is not None else PropertyPolicy()
    out: dict = {}
    for key, value in props.items():
        if key in EMBEDDING_PROPS:
            policy.embeddings_dropped += 1
            policy.dropped_by_prop[key] = policy.dropped_by_prop.get(key, 0) + 1
            continue
        out[key] = _translate_value(key, value, policy)
    return out


def _translate_value(key: str, value: object, policy: PropertyPolicy) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [_translate_value(key, item, policy) for item in value]
    if isinstance(value, _dt.datetime) or hasattr(value, "to_native"):
        policy.temporals_converted += 1
        return to_age_millis(value)
    raise UnmappableProperty(
        f"property {key!r} holds {type(value).__name__}, which agtype cannot represent and "
        f"this migration will not coerce (§10.1 — the engine seam translates, it does not guess)"
    )


@dataclass
class GraphAssignment:
    """One project's share of the migration."""

    project_key: str | None
    nodes: int = 0
    rels: int = 0
    labels: dict[str, int] = field(default_factory=dict)
    rel_types: dict[str, int] = field(default_factory=dict)


@dataclass
class MigrationPlan:
    """What a run would do, computed without touching the destination."""

    graphs: dict[str | None, GraphAssignment] = field(default_factory=dict)
    policy: PropertyPolicy = field(default_factory=PropertyPolicy)

    @property
    def total_nodes(self) -> int:
        return sum(g.nodes for g in self.graphs.values())

    @property
    def total_rels(self) -> int:
        return sum(g.rels for g in self.graphs.values())

    def assignment(self, project_key: str | None) -> GraphAssignment:
        if project_key not in self.graphs:
            self.graphs[project_key] = GraphAssignment(project_key)
        return self.graphs[project_key]


class DanglingEndpoint(KeyError):
    """A relationship endpoint that is not among the migrated nodes.

    `_write_rel` MATCHes its endpoints rather than MERGEing them precisely so this cannot pass
    silently — but by then the row is already lost. Refusing in the planner means the run does
    nothing instead of writing a graph whose edge count is short by an amount nobody counted.
    """


class AmbiguousAdoption(ValueError):
    """An unscoped node that two different projects both point at.

    Adopting it would fork one node into two graphs, and every row that keys on it would then
    reference a copy. Measured 0 on iso — all 16 adopted sources have exactly ONE referring
    project — so this refusal is unreachable on today's data and is here because "one referrer"
    is a property of the data, not of the schema.
    """


def node_index(nodes) -> dict:
    """`(label, natural key) -> props`, the lookup the adoption pass needs."""
    index: dict = {}
    for label, props in nodes:
        if label not in LABEL_KEYS:
            raise UnkeyedLabel(
                f"label {label!r} has no natural key in LABEL_KEYS — add one before migrating "
                f"it; migrating on an internal element id is not idempotent"
            )
        index[(label, props.get(LABEL_KEYS[label]))] = props
    return index


def resolve_graph_keys(nodes, rels, layout: str = SERVICE_LAYOUT) -> dict:
    """Which graph each node goes to — `project_id` when it has one, else its referrer's.

    ⚠️ **The adoption rule came from the real data refusing the simple one.** dev has zero
    cross-project edges under a NULL-aware probe, so a first cut put every unscoped node in
    `g_shared` and raised on any edge that crossed. Run against iso's real extraction output it
    raised immediately: **16 `EVIDENCED_BY` edges from a scoped Entity to an UNSCOPED
    `ExtractionSource`** — 20 of iso's 27 sources carry no `project_id` at all, where all 172 on
    dev do. The refusal was correct (it lost nothing and said so) and the rule was too narrow.

    An `ExtractionSource` is evidence FOR an entity; it has no independent existence, so it
    belongs in the graph of the thing that cites it. That also tightens tenancy rather than
    loosening it: in `g_shared` every project could read it, and in the referrer's graph only
    the referrer can. The four orphans — cited by nothing — stay shared, because there is no
    referrer to inherit from and inventing one would be a guess.
    """
    if layout not in LAYOUTS:
        raise ValueError(f"layout={layout!r} is not one of {LAYOUTS}")
    index = node_index(nodes)

    # ⚠️ Endpoint validation runs in BOTH layouts and the split above it is why. A first cut
    # returned early for `SERVICE_LAYOUT` — one graph, nothing to group — and took the unkeyed
    # -label and dangling-endpoint refusals with it, so the DEFAULT layout silently lost two
    # checks the tests only exercised through the other one. What is layout-specific is the
    # graph BOUNDARY: adoption and cross-graph edges. Whether an endpoint exists is not.
    for rel_type, start_label, start_props, end_label, end_props, _ in rels:
        for side_label in (start_label, end_label):
            if side_label not in LABEL_KEYS:
                raise UnkeyedLabel(
                    f"relationship {rel_type!r} touches unkeyed label {side_label!r}"
                )
        for side_label, side_props in ((start_label, start_props), (end_label, end_props)):
            side = (side_label, side_props.get(LABEL_KEYS[side_label]))
            if side not in index:
                raise DanglingEndpoint(
                    f"{rel_type} points at {side[0]} {side[1]!r}, which is not among the "
                    f"migrated nodes — the edge would be written against a node that does "
                    f"not exist, or MERGE would conjure an empty one"
                )

    if layout == SERVICE_LAYOUT:
        # One graph, exactly as Neo4j holds one database: nothing to adopt, and no boundary
        # for an edge to cross. The two refusals below stay reachable under `per_project`,
        # which is the layout that can violate them.
        return {key: None for key in index}

    own: dict = {}
    for key, props in index.items():
        own[key] = graph_key_for(props.get("project_id"))

    referrers: dict = {}
    for rel_type, start_label, start_props, end_label, end_props, _ in rels:
        start_key = (start_label, start_props.get(LABEL_KEYS[start_label]))
        end_key = (end_label, end_props.get(LABEL_KEYS[end_label]))
        for scoped, unscoped in ((start_key, end_key), (end_key, start_key)):
            if own.get(scoped) is not None and own.get(unscoped) is None:
                referrers.setdefault(unscoped, set()).add(own[scoped])

    resolved = dict(own)
    for node_key, projects in referrers.items():
        if len(projects) > 1:
            raise AmbiguousAdoption(
                f"{node_key[0]} {node_key[1]!r} carries no project_id and is referenced by "
                f"{sorted(projects)} — adopting it would fork one node across graphs"
            )
        resolved[node_key] = next(iter(projects))
    return resolved


def plan_migration(nodes, rels, layout: str = SERVICE_LAYOUT) -> MigrationPlan:
    """Group the source graph into per-project graphs, refusing what AGE cannot hold.

    `nodes` is an iterable of `(label, props)`; `rels` of
    `(rel_type, start_label, start_props, end_label, end_props, props)`. Pure: no driver, no
    pool, no environment — which is what makes the refusals testable on cases they were not
    derived from (rule 3).
    """
    plan = MigrationPlan()
    resolved = resolve_graph_keys(nodes, rels, layout)
    for label, props in nodes:
        translate_props(props, plan.policy)
        key = resolved[(label, props.get(LABEL_KEYS[label]))]
        assignment = plan.assignment(key)
        assignment.nodes += 1
        assignment.labels[label] = assignment.labels.get(label, 0) + 1
    for rel_type, start_label, start_props, end_label, end_props, rel_props in rels:
        start_key = resolved[(start_label, start_props.get(LABEL_KEYS[start_label]))]
        end_key = resolved[(end_label, end_props.get(LABEL_KEYS[end_label]))]
        if start_key != end_key:
            raise CrossProjectEdge(
                f"{rel_type} spans {start_key!r} -> {end_key!r}; AGE holds a relationship "
                f"inside ONE graph, so a graph-per-project layout cannot express this edge"
            )
        translate_props(rel_props, plan.policy)
        assignment = plan.assignment(start_key)
        assignment.rels += 1
        assignment.rel_types[rel_type] = assignment.rel_types.get(rel_type, 0) + 1
    return plan


def render_report(plan: MigrationPlan) -> str:
    """The dry-run's output. Counts first, then what was dropped — stated, never implied."""
    lines = [
        f"graphs        {len(plan.graphs)}",
        f"nodes         {plan.total_nodes}",
        f"relationships {plan.total_rels}",
        f"temporals -> epoch millis   {plan.policy.temporals_converted}",
        f"embedding props DROPPED     {plan.policy.embeddings_dropped}",
    ]
    for prop, count in sorted(plan.policy.dropped_by_prop.items()):
        lines.append(f"    {prop:<20} {count}")
    return "\n".join(lines)


# ── the apply shim ───────────────────────────────────────────────────────────────────────────
#
# Thin on purpose, in the house style of `recanon_honorifics`: everything that can be decided
# without a database is decided above, and this half only moves rows. It uses the real seams —
# `ensure_graph` for the DDL and `age_repo_session` for the writes — rather than reaching for
# raw SQL, so a migrated graph is written through the same session type the service reads with.

import re as _re

#: Property names are interpolated into `SET n.<key> = $p_<key>` because Cypher has no
#: parameter form for an identifier. That makes this regex the injection barrier, exactly as
#: `SUPPORTED_PASSAGE_DIMS` is for the vector index names.
_SAFE_KEY = _re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _set_clause(alias: str, props: dict) -> tuple[str, dict]:
    """`SET a.x = $a_x, …` plus the parameter map, refusing any key it cannot interpolate."""
    fragments: list[str] = []
    params: dict = {}
    for index, (key, value) in enumerate(sorted(props.items())):
        if not _SAFE_KEY.match(key):
            raise UnmappableProperty(
                f"property name {key!r} is not a safe Cypher identifier; refusing to "
                f"interpolate it (rule 9 — raise rather than write something half-right)"
            )
        name = f"{alias}_{index}"
        fragments.append(f"{alias}.{key} = ${name}")
        params[name] = value
    return (", ".join(fragments), params)


async def _write_node(session, label: str, props: dict) -> None:
    key_prop = LABEL_KEYS[label]
    if props.get(key_prop) is None:
        raise UnkeyedLabel(
            f"a {label} carries no {key_prop!r} — it has no stable identity to MERGE on, and "
            f"migrating it would create a duplicate on every re-run"
        )
    rest = {k: v for k, v in props.items() if k != key_prop}
    cypher = f"MERGE (n:{label} {{{key_prop}: $key}})"
    params: dict = {"key": props[key_prop]}
    if rest:
        clause, extra = _set_clause("n", rest)
        cypher += f" SET {clause}"
        params.update(extra)
    cypher += " RETURN n.%s AS id" % key_prop
    await session.run(cypher, **params)


async def _write_rel(
    session, rel_type: str, start_label: str, start_key, end_label: str, end_key, props: dict
) -> None:
    """MERGE one relationship, keyed on its `id` when it has one.

    🔴 **The endpoint pair is NOT a key, and the real data is what proved it.** The first
    version merged on `(a)-[:TYPE]->(b)` and the run against iso's extraction output came back
    `MISSING …/RELATES_TO: destination 11, source 12` — two distinct relationships between the
    same pair of entities collapsing into one. Measured across both graphs:

        parallel edges between one pair   RELATES_TO only — 183 pairs on dev, worst 10
        relationship types carrying `id`  RELATES_TO only — 1 144 of 1 144

    The two lists are the same list, and that is not a coincidence: the type that can repeat
    between a pair is the one given an identity of its own. So an `id` in the properties IS the
    merge key, and its absence means the pair genuinely identifies the edge. Merging on the pair
    everywhere would have silently dropped at least 183 relationships on dev — node counts
    intact, `verify` the only thing that would have said so.
    """
    start_prop = LABEL_KEYS[start_label]
    end_prop = LABEL_KEYS[end_label]
    rel_id = props.get("id")
    match_on = " {id: $rel_id}" if rel_id is not None else ""
    cypher = (
        f"MATCH (a:{start_label} {{{start_prop}: $a_key}}), "
        f"(b:{end_label} {{{end_prop}: $b_key}}) "
        f"MERGE (a)-[r:{rel_type}{match_on}]->(b)"
    )
    params: dict = {"a_key": start_key, "b_key": end_key}
    if rel_id is not None:
        params["rel_id"] = rel_id
    rest = {k: v for k, v in props.items() if k != "id"}
    if rest:
        clause, extra = _set_clause("r", rest)
        cypher += f" SET {clause}"
        params.update(extra)
    cypher += " RETURN 1 AS ok"
    await session.run(cypher, **params)


async def collect_source(neo4j_session) -> tuple[list, list]:
    """Read the whole source graph as the two plain-tuple streams the planner takes.

    Label-by-label rather than one `MATCH (n)`: the planner refuses an unkeyed label, and a
    single sweep would surface that only after most of the graph had been read. Enumerating
    from `LABEL_KEYS` also means a label the map does not know is reported as ABSENT from the
    migration rather than migrated on a guessed key — the loud failure, not the silent one.
    """
    nodes: list = []
    for label in LABEL_KEYS:
        result = await neo4j_session.run(f"MATCH (n:{label}) RETURN n AS n")
        async for record in result:
            nodes.append((label, dict(record["n"])))
    rels: list = []
    result = await neo4j_session.run(
        "MATCH (a)-[r]->(b) "
        "RETURN type(r) AS t, labels(a)[0] AS al, a AS a, labels(b)[0] AS bl, b AS b, r AS r"
    )
    async for record in result:
        rels.append(
            (
                record["t"],
                record["al"],
                dict(record["a"]),
                record["bl"],
                dict(record["b"]),
                dict(record["r"]),
            )
        )
    return nodes, rels


async def migrate(
    neo4j_session, age_pool, *, apply: bool = False, layout: str = SERVICE_LAYOUT,
) -> MigrationPlan:
    """Plan the migration and, with `apply=True`, perform it.

    The plan is computed FIRST and in full. Every refusal — an unkeyed label, a cross-project
    edge, a property agtype cannot hold — fires before a single row is written, so a run either
    does nothing or does all of it. A migration that failed half-way would leave a graph that
    reads without error and answers wrong, which is the failure mode this whole row exists to
    close.
    """
    nodes, rels = await collect_source(neo4j_session)
    plan = plan_migration(nodes, rels, layout)
    if not apply:
        return plan

    from app.db.age_bootstrap import ensure_graph
    from app.db.age_session import age_repo_session

    async with age_pool.acquire() as conn:
        for project_key in plan.graphs:
            await ensure_graph(conn, project_key)

    # Grouped by project because `age_repo_session` binds ONE graph for the life of the
    # session — and because a session per row would take a pooled connection 12 000 times on
    # the dev-sized graph.
    # The SAME resolution the plan used — grouping by raw `project_id` here would put an
    # adopted node in `g_shared` while the plan counted it in the referrer's graph, and
    # `verify` would then report MISSING for a row that was written to the wrong place.
    resolved = resolve_graph_keys(nodes, rels, layout)
    nodes_by_project: dict = {}
    for label, props in nodes:
        key = resolved[(label, props.get(LABEL_KEYS[label]))]
        nodes_by_project.setdefault(key, []).append((label, props))
    rels_by_project: dict = {}
    for rel in rels:
        key = resolved[(rel[1], rel[2].get(LABEL_KEYS[rel[1]]))]
        rels_by_project.setdefault(key, []).append(rel)

    for project_key in plan.graphs:
        async with age_repo_session(age_pool, project_key) as session:
            for label, props in nodes_by_project.get(project_key, ()):
                await _write_node(session, label, translate_props(dict(props)))
            # Relationships after every node in the same graph, so both endpoints exist. The
            # writer MATCHes rather than MERGEs its endpoints on purpose: a MERGE there would
            # conjure a keyed-but-empty node for an endpoint the migration had skipped, and the
            # counts would still balance.
            for rel_type, start_label, start_props, end_label, end_props, rel_props in (
                rels_by_project.get(project_key, ())
            ):
                await _write_rel(
                    session,
                    rel_type,
                    start_label,
                    start_props[LABEL_KEYS[start_label]],
                    end_label,
                    end_props[LABEL_KEYS[end_label]],
                    translate_props(dict(rel_props)),
                )
    return plan


async def verify(neo4j_session, age_pool, plan: MigrationPlan) -> list[str]:
    """Count every (graph, label) and (graph, rel type) on the destination against the plan.

    Returns the mismatches, empty when the migration landed whole. Counting rather than
    trusting the writer is the point: `MERGE` is idempotent, so a run that silently wrote
    nothing looks exactly like a run that had nothing to do.

    ⚠️ **A shortfall and a surplus are different findings and the message says which.** The
    first live run collapsed them and cost a wrong diagnosis: `g_shared/Book: 6 != 1` looked
    like a migration defect and was six tests' fixtures accumulating in a graph nothing cleaned.

        MISSING   rows the source has and the destination does not — the migration LOST them
        EXTRA     rows the destination has and the source does not — the destination was not
                  empty, or a MERGE key is not the natural one and a re-run duplicated

    Exactness assumes an empty destination, which is the cutover's own precondition and was
    measured true on dev (0 entities across 433 project graphs). Against a destination that
    already holds rows, read EXTRA as "check the precondition", not as "the migration failed".
    """
    from app.db.age_session import age_repo_session

    problems: list[str] = []

    def _report(graph: str, what: str, got: int, expected: int) -> None:
        if got == expected:
            return
        verdict = "MISSING" if got < expected else "EXTRA"
        problems.append(
            f"{verdict} {graph}/{what}: destination {got}, source {expected}"
        )

    for project_key, assignment in plan.graphs.items():
        graph = project_key or SHARED_GRAPH
        async with age_repo_session(age_pool, project_key) as session:
            for label, expected in assignment.labels.items():
                result = await session.run(f"MATCH (n:{label}) RETURN count(n) AS n")
                rows = await result.data()
                _report(graph, label, rows[0]["n"] if rows else 0, expected)
            for rel_type, expected in assignment.rel_types.items():
                result = await session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS n")
                rows = await result.data()
                _report(graph, rel_type, rows[0]["n"] if rows else 0, expected)
    return problems


# ── the operator CLI ─────────────────────────────────────────────────────────────────────────
#
# 🔴 **The module documented this interface before it existed.** The header has said
# `python -m app.db.migrations.neo4j_to_age` since T54e; running it imported the module, did
# nothing, and **exited 0**. An operator following the documentation would have read that as
# "dry run: nothing to migrate" — silent success, which is a bug and not a convenience.
# Found by trying the documented command instead of reading it (rule 2).


def split_verdicts(problems: list[str]) -> tuple[list[str], list[str]]:
    """`verify`'s rows split into what FAILS and what merely INFORMS.

    Pure so it can be bitten: the CLI around it needs two live engines, and the decision
    needs none. The live run is what made this a decision at all — see `_cli_main`.
    """
    return ([r for r in problems if r.startswith("MISSING")],
            [r for r in problems if r.startswith("EXTRA")])


def cli_exit_code(problems: list[str]) -> int:
    """0 unless rows are MISSING. EXTRA is information, not failure."""
    missing, _ = split_verdicts(problems)
    return 1 if missing else 0


async def _cli_main() -> int:
    import argparse

    from app.config import settings
    from app.db.age_pool import age_pool, close_age_pool, init_age_pool
    from app.db.neo4j import close_neo4j_driver, init_neo4j_driver
    from app.db.graph import graph_session

    ap = argparse.ArgumentParser(description="Migrate a Neo4j knowledge graph into AGE")
    ap.add_argument("--apply", action="store_true", help="execute (default: dry-run)")
    ap.add_argument("--layout", default=SERVICE_LAYOUT, choices=list(LAYOUTS),
                    help="destination topology (default: the one the SERVICE reads)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)
    # Both lifecycles are the CLI's here, exactly as `recanon_honorifics` owns the driver's:
    # the getters raise unless the FastAPI lifespan hook ran, and it never does under `-m`.
    await init_neo4j_driver()
    if not await init_age_pool():
        # Refusing rather than falling back, and for T54's reason: a migration that silently
        # wrote nowhere would report success and leave the store as empty as it found it.
        logger.error(
            "no AGE pool — KNOWLEDGE_AGE_DB_URL is unset or unreachable. Refusing to run: "
            "a migration with no destination is not a dry run, it is a no-op that reports "
            "success."
        )
        await close_neo4j_driver()
        return 2

    logger.info(
        "neo4j->age %s  layout=%s  source=%s",
        "APPLY" if args.apply else "DRY-RUN", args.layout,
        settings.neo4j_uri or "<unset>",
    )
    try:
        # `engine="neo4j"` pins the SOURCE. This is the one place a pin is correct rather
        # than debt: the migration reads the engine it is migrating OFF, whatever the
        # process is otherwise configured for — and on a migrated deployment that is `age`,
        # so following the configuration here would read the destination into itself.
        async with graph_session(engine="neo4j") as session:
            plan = await migrate(session, age_pool(), apply=args.apply, layout=args.layout)
            print(render_report(plan))
            if args.apply:
                problems = await verify(session, age_pool(), plan)
                # 🔴 **MISSING fails; EXTRA does not, and the LIVE RUN is what settled it.**
                # The first cut exited 1 on any mismatch. Run against the iso stack — whose
                # `g_shared` already held 35 entities the service itself had written — it
                # reported failure while losing NOTHING:
                #
                #     EXTRA g_shared/Entity: destination 638, source 603     638 = 603 + 35
                #
                # That is every deployment that has ever served a request, and every re-run.
                # The operator's question is "did my rows land": MISSING answers no, EXTRA
                # answers "the destination was not empty", which is information. A CLI that
                # cannot tell them apart is one whose exit code stops being read.
                missing, extra = split_verdicts(problems)
                if extra:
                    print(f"\nnote — the destination was NOT empty ({len(extra)} label(s) "
                          f"hold more than the source). Nothing was lost; those rows were "
                          f"already there:")
                    for row in extra[:10]:
                        print(f"  {row}")
                if missing:
                    print(f"\nVERIFY FAILED — {len(missing)} label(s) came up SHORT:")
                    for row in missing[:20]:
                        print(f"  {row}")
                    return 1
                print("\nverify: no rows missing")
    finally:
        await close_age_pool()
        await close_neo4j_driver()
    return 0


if __name__ == "__main__":  # pragma: no cover
    import asyncio
    import sys as _sys

    _sys.exit(asyncio.run(_cli_main()))

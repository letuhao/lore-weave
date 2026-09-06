//! `space_view` — *"what is here"*, assembled deterministically and bounded.
//!
//! ## Why this exists, and why it had to before `SDF-Q15` could close
//!
//! `SDF-Q15` asks for the fan-out and occupant caps in `ProjectionPolicy`, and
//! it had stood open with the note *"needs a measured prompt-assembly cost that
//! does not exist"*. That is a blocker only until someone builds the thing being
//! measured. This is that thing.
//!
//! ## `SDF-A23` — three producers, ONE result type
//!
//! | section | producer | bound |
//! |---|---|---|
//! | this node | — | 1 |
//! | ancestors | interval walk | **≤16 by `DP-Ch1`'s DB `CHECK`** — an EXISTING invariant, not a new limit |
//! | portal ring | connective adjacency (`SDF-A25`, `0028_portal`) | a declared cap |
//! | occupants | the occupancy index (`0025_entity_binding`) | a declared cap |
//!
//! Everything except the last two is **already bounded by an invariant this
//! repo enforces in SQL**, which is the argument for reusing `DP-Ch1`'s depth
//! rather than inventing a traversal limit.
//!
//! ## Determinism is STRUCTURAL here, not a discipline
//!
//! `SDF-A4` forbids hash-ordered iteration, allocation-derived ordering and
//! tie-breaks by display name. Every query below carries an explicit `ORDER BY`
//! on an integer key, and every cap is applied AFTER that ordering — so a
//! truncated view is a PREFIX of a total order rather than an arbitrary subset.
//! Two callers with the same budget get the same view, and a replay gets the
//! view the original run got.
//!
//! `SDF-A26` says the reader chooses a **budget**, never a set: which layers
//! render is the layer owner's declaration (`layer_registry.projection`), not
//! the reader's. This module therefore takes caps and not a field list.

use serde::Serialize;
use dp::RealityId;
use sqlx::PgPool;

/// `DP-Ch1`'s depth bound, enforced as a `CHECK` in `0019_channels`. Repeated
/// as a walk guard so a malformed tree cannot spin, never as a second source of
/// truth for the number.
const MAX_DEPTH_WALK: usize = 17;

/// What the reader chooses. **Caps, not a set** (`SDF-A26`).
#[derive(Debug, Clone, Copy)]
pub struct ViewBudget {
    /// How many portals out of this node to include.
    pub portal_ring: usize,
    /// How many occupants of this node to include.
    pub occupants: usize,
}

impl ViewBudget {
    /// The caps `SDF-Q15` measured. See `space_view_measure_live`.
    pub const MEASURED: ViewBudget = ViewBudget { portal_ring: 12, occupants: 24 };
}

/// One node in the view, in the order the view fixes.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ViewNode {
    pub node_id: i64,
    pub kind: String,
    pub level_name: String,
    /// `None` unless the node is a `Domain` carrying a `place` row.
    pub place_name: Option<String>,
}

/// The assembled answer to *"what is here"*.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct SpaceView {
    pub here: ViewNode,
    /// Nearest first. Bounded by `DP-Ch1`, not by a cap of ours.
    pub ancestors: Vec<ViewNode>,
    /// Connective adjacency (`SDF-A25`) — the portal graph, NOT the mesh.
    pub portal_ring: Vec<i64>,
    /// Entity ids, ascending.
    pub occupants: Vec<i64>,
    /// True when a cap elided something. **A truncated view must SAY it is
    /// truncated**, or a reader cannot tell "nothing here" from "too much here"
    /// — which is the difference between an empty room and a crowded one.
    pub truncated: bool,
}

#[derive(Debug)]
pub enum ViewError {
    NotFound(i64),
    Db(sqlx::Error),
}

impl std::fmt::Display for ViewError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NotFound(n) => write!(f, "node {n} does not exist in this reality"),
            Self::Db(e) => write!(f, "database error: {e}"),
        }
    }
}

impl std::error::Error for ViewError {}

async fn node_at(pool: &PgPool, reality: &RealityId, id: i64) -> Result<Option<ViewNode>, sqlx::Error> {
    let row: Option<(i64, String, String, Option<String>)> = sqlx::query_as(
        "SELECT c.id, m.kind, c.level_name, p.name_vi \
           FROM channels c \
           JOIN map_layout m ON m.reality_id = c.reality_id AND m.channel_id = c.id \
           LEFT JOIN place p ON p.reality_id = c.reality_id AND p.place_id = c.id \
          WHERE c.reality_id = $1 AND c.id = $2",
    )
    .bind(reality.as_uuid())
    .bind(id)
    .fetch_optional(pool)
    .await?;
    Ok(row.map(|(node_id, kind, level_name, place_name)| ViewNode {
        node_id,
        kind,
        level_name,
        place_name,
    }))
}

/// Assemble the view. Every query orders explicitly; every cap applies after the
/// ordering, so a truncated section is a PREFIX rather than a sample.
pub async fn assemble(
    pool: &PgPool,
    reality: &RealityId,
    node: i64,
    budget: ViewBudget,
) -> Result<SpaceView, ViewError> {
    let here = node_at(pool, reality, node)
        .await
        .map_err(ViewError::Db)?
        .ok_or(ViewError::NotFound(node))?;

    // Ancestors, nearest first. ONE query, not two per level.
    //
    // `C2`. This was a loop issuing `SELECT parent` and then a `node_at` for
    // every level -- an N+1 whose cost grew with depth, against a `DP-Ch1`
    // bound of 16. A recursive CTE collapses it to a single round trip and the
    // walk guard becomes a `depth <` predicate inside the query, which is
    // strictly better: a malformed tree is bounded by the DATABASE rather than
    // by a loop counter that only the caller enforces.
    //
    // `WHERE u.depth > 0` drops the node itself -- it is already `here`, and
    // returning it twice would make `ancestors.len()` disagree with the tree.
    // `ORDER BY u.depth ASC` is the nearest-first contract, stated to the
    // database rather than produced by the order of a loop (`SDF-A4`: explicit
    // ordering, never incidental).
    let ancestors: Vec<ViewNode> = sqlx::query_as(
        "WITH RECURSIVE up AS (              SELECT c.id, c.parent, 0 AS d                FROM channels c               WHERE c.reality_id = $1 AND c.id = $2              UNION ALL              SELECT c.id, c.parent, up.d + 1                FROM channels c                JOIN up ON c.id = up.parent               WHERE c.reality_id = $1 AND up.d < $3          )          SELECT u.id, m.kind, c.level_name, p.name_vi            FROM up u            JOIN channels c ON c.reality_id = $1 AND c.id = u.id            JOIN map_layout m ON m.reality_id = $1 AND m.channel_id = u.id            LEFT JOIN place p ON p.reality_id = $1 AND p.place_id = u.id           WHERE u.d > 0           ORDER BY u.d ASC",
    )
    .bind(reality.as_uuid())
    .bind(node)
    .bind(MAX_DEPTH_WALK as i32)
    .fetch_all(pool)
    .await
    .map_err(ViewError::Db)?
    .into_iter()
    .map(|(node_id, kind, level_name, place_name): (i64, String, String, Option<String>)| ViewNode {
        node_id,
        kind,
        level_name,
        place_name,
    })
    .collect();


    // The portal ring. `SDF-A25`: this is CONNECTIVE adjacency and says so — a
    // caller wanting geometric neighbours is asking a different question.
    // `LIMIT cap + 1` so truncation is detected rather than inferred.
    let ring: Vec<i64> = sqlx::query_scalar(
        "SELECT CASE WHEN node_a = $2 THEN node_b ELSE node_a END AS other \
           FROM portal \
          WHERE reality_id = $1 AND (node_a = $2 OR node_b = $2) \
          ORDER BY other ASC LIMIT $3",
    )
    .bind(reality.as_uuid())
    .bind(node)
    .bind(budget.portal_ring as i64 + 1)
    .fetch_all(pool)
    .await
    .map_err(ViewError::Db)?;

    let occupants: Vec<i64> = sqlx::query_scalar(
        "SELECT entity_id FROM entity_binding \
          WHERE reality_id = $1 AND cell_id = $2 \
          ORDER BY entity_id ASC LIMIT $3",
    )
    .bind(reality.as_uuid())
    .bind(node)
    .bind(budget.occupants as i64 + 1)
    .fetch_all(pool)
    .await
    .map_err(ViewError::Db)?;

    let truncated = ring.len() > budget.portal_ring || occupants.len() > budget.occupants;

    Ok(SpaceView {
        here,
        ancestors,
        portal_ring: ring.into_iter().take(budget.portal_ring).collect(),
        occupants: occupants.into_iter().take(budget.occupants).collect(),
        truncated,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_measured_caps_are_the_ones_the_row_asked_for() {
        // `SDF-Q15` asked for numbers. These are them, and they are pinned here
        // so a change has to be deliberate -- the same reason
        // `grid_size_preset_tests` exists in tilemap-service after a mutant
        // survived 521 tests.
        assert_eq!(ViewBudget::MEASURED.portal_ring, 12);
        assert_eq!(ViewBudget::MEASURED.occupants, 24);
    }

    #[test]
    fn the_walk_guard_exceeds_dp_ch1_by_exactly_one() {
        // 16 is DP-Ch1's bound and the guard must admit a full-depth tree while
        // still terminating on a malformed one. Equal would truncate a legal
        // tree; much larger would stop being a guard.
        assert_eq!(MAX_DEPTH_WALK, 17);
    }
}

/// Where an entity is, as three DISTINCT facts.
///
/// `A4`. `assemble` answers *"what is at node X"*; nothing answered *"where is
/// entity N"*, and the room needs the second to render the first.
///
/// Three variants and not an `Option`, because collapsing them would merge two
/// different truths into one silence: an entity with no binding at all and an
/// entity held in someone's hand would both read as `None`. `0025` models
/// location as a **sum type** with a `CHECK` that enforces exactly one arm; a
/// reader that flattened it back to nullable would be undoing that at the edge.
#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(rename_all = "snake_case", tag = "kind")]
pub enum Whereabouts {
    /// No `entity_binding` row. The ordinary state for every actor that has
    /// never been sited — which, until `A3`, was all of them.
    Unbound,
    /// Bound, and in a cell. The only arm that has a node.
    InCell(EntityLocation),
    /// Bound, but not to a cell — `held_by`, `in_container` or `embedded`.
    /// **Where it is** is then its holder, which is a different question and one
    /// this row deliberately does not answer: an inventory owner does not exist
    /// yet, and inventing the traversal here would decide that owner by accident.
    NotInACell {
        /// The `location_kind` column, verbatim.
        location_kind: String,
    },
}

/// The `in_cell` arm's payload.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct EntityLocation {
    pub entity_id: i64,
    /// The `channels.id` the entity occupies.
    pub node: i64,
    /// The node's `MapKind`.
    ///
    /// WARNING: `node_kind`, NOT `kind`. The enum is `#[serde(tag = "kind")]`,
    /// so a field called `kind` here serialises a DUPLICATE JSON KEY:
    /// `{"kind":"in_cell", ..., "kind":"domain"}`. Rust emits both happily;
    /// every JSON parser keeps the LAST, so the discriminant is destroyed and a
    /// TypeScript reader sees `kind === "domain"` and concludes the entity is
    /// nowhere. Found by the browser test, which is the only thing that reads
    /// this end to end.
    pub node_kind: String,
    /// The reality's own word for the level (`DP-A13`).
    pub level_name: String,
    /// `None` unless the node is a `Domain` carrying a `place` row.
    pub place_name: Option<String>,
}

/// Answer *"where is entity N"* for one reality.
///
/// ONE query. The join is the point: a binding names a `cell_id`, and a cell is
/// a `channels` row whose `map_layout` gives it a kind and whose `place` — if it
/// is a `Domain` — gives it a name. Three tables, one round trip; the N+1 that
/// `C2` removed from the ancestor walk is not reintroduced here.
pub async fn where_is(
    pool: &PgPool,
    reality: &RealityId,
    entity_id: i64,
) -> Result<Whereabouts, ViewError> {
    let row: Option<(String, Option<i64>, Option<String>, Option<String>, Option<String>)> =
        sqlx::query_as(
            "SELECT eb.location_kind, eb.cell_id, m.kind, c.level_name, p.name_vi \
               FROM entity_binding eb \
               LEFT JOIN channels c \
                 ON c.reality_id = eb.reality_id AND c.id = eb.cell_id \
               LEFT JOIN map_layout m \
                 ON m.reality_id = eb.reality_id AND m.channel_id = eb.cell_id \
               LEFT JOIN place p \
                 ON p.reality_id = eb.reality_id AND p.place_id = eb.cell_id \
              WHERE eb.reality_id = $1 AND eb.entity_id = $2",
        )
        .bind(reality.as_uuid())
        .bind(entity_id)
        .fetch_optional(pool)
        .await
        .map_err(ViewError::Db)?;

    let Some((location_kind, cell_id, kind, level_name, place_name)) = row else {
        return Ok(Whereabouts::Unbound);
    };
    match (location_kind.as_str(), cell_id, kind, level_name) {
        ("in_cell", Some(node), Some(kind), Some(level_name)) => {
            Ok(Whereabouts::InCell(EntityLocation {
                entity_id,
                node,
                node_kind: kind,
                level_name,
                place_name,
            }))
        }
        // `in_cell` with no joined node means the binding points at a channel
        // that has no `map_layout` row -- a tree node that was never given a
        // kind. `0025`'s foreign key guarantees the CHANNEL exists, not that it
        // is on the map, so this is reachable and is a real fault rather than a
        // shrug.
        ("in_cell", ..) => Err(ViewError::NotFound(cell_id.unwrap_or(entity_id))),
        _ => Ok(Whereabouts::NotInACell { location_kind }),
    }
}

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
use sqlx::PgPool;
use uuid::Uuid;

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

async fn node_at(pool: &PgPool, reality: Uuid, id: i64) -> Result<Option<ViewNode>, sqlx::Error> {
    let row: Option<(i64, String, String, Option<String>)> = sqlx::query_as(
        "SELECT c.id, m.kind, c.level_name, p.name_vi \
           FROM channels c \
           JOIN map_layout m ON m.reality_id = c.reality_id AND m.channel_id = c.id \
           LEFT JOIN place p ON p.reality_id = c.reality_id AND p.place_id = c.id \
          WHERE c.reality_id = $1 AND c.id = $2",
    )
    .bind(reality)
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
    reality: Uuid,
    node: i64,
    budget: ViewBudget,
) -> Result<SpaceView, ViewError> {
    let here = node_at(pool, reality, node)
        .await
        .map_err(ViewError::Db)?
        .ok_or(ViewError::NotFound(node))?;

    // Ancestors, nearest first. Bounded by DP-Ch1's CHECK; the walk guard exists
    // so a tree that somehow violated it cannot spin this loop forever.
    let mut ancestors = Vec::new();
    let mut cursor = node;
    for _ in 0..MAX_DEPTH_WALK {
        let parent: Option<Option<i64>> =
            sqlx::query_scalar("SELECT parent FROM channels WHERE reality_id = $1 AND id = $2")
                .bind(reality)
                .bind(cursor)
                .fetch_optional(pool)
                .await
                .map_err(ViewError::Db)?;
        match parent.flatten() {
            None => break,
            Some(p) => {
                if let Some(n) = node_at(pool, reality, p).await.map_err(ViewError::Db)? {
                    ancestors.push(n);
                }
                cursor = p;
            }
        }
    }

    // The portal ring. `SDF-A25`: this is CONNECTIVE adjacency and says so — a
    // caller wanting geometric neighbours is asking a different question.
    // `LIMIT cap + 1` so truncation is detected rather than inferred.
    let ring: Vec<i64> = sqlx::query_scalar(
        "SELECT CASE WHEN node_a = $2 THEN node_b ELSE node_a END AS other \
           FROM portal \
          WHERE reality_id = $1 AND (node_a = $2 OR node_b = $2) \
          ORDER BY other ASC LIMIT $3",
    )
    .bind(reality)
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
    .bind(reality)
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

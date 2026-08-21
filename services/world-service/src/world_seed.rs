//! `world_seed` — the world-structure step of reality bootstrap.
//!
//! ## What was missing, measured rather than assumed
//!
//! [`crate::reality_seeder`] already runs in the `seeding` lifecycle stage that
//! [`crate::provisioner`] step 9 transitions into, and it seeds **canon**:
//! authored entries pulled from `glossary-service` into `canon_projection`. It
//! does not create a single channel. Grepped before this module was written:
//! **every `INSERT INTO channels` in the repository is in a test.** So a
//! provisioned reality reaches `active` with an empty space tree — no node, no
//! kind, no place — and an actor has nowhere to be.
//!
//! This module is that step. It implements `PF_001` §5's numbered bootstrap
//! order, whose step 5 is the spawn.
//!
//! ## The three tables it writes, and why it is allowed to
//!
//! | table | migration | what it means |
//! |---|---|---|
//! | `channels` | `0019` | the tree — per-reality, parent-linked, acyclic by construction |
//! | `map_layout` | `0024` | the node's `MapKind` and its parent-relative position |
//! | `place` | `0026` | `PF_001` semantic identity, 1:1 with a `Domain` |
//!
//! `0025_entity_binding` is deliberately **not** written here: siting an actor
//! is `PF_001`'s step 5, and `PF_001` states in its own header that
//! *"spawn-into-place is consumer responsibility"*. This module makes the place
//! exist and stops.
//!
//! ## ONE DELIBERATE DEVIATION FROM `PF_001` §5, and it is stated rather than
//! ## silently taken
//!
//! The numbered order is: (1) channels, (2) places, (3) **validate** that every
//! leaf node has a place, rejecting with `place.missing_decl`. Validating third
//! means a rejected bootstrap has **already written** its channel hierarchy.
//!
//! This module validates FIRST and writes nothing on rejection. The reason is
//! the failure mode the repo already owns: `orphan_scan` exists because a
//! half-provisioned reality sits at `status=provisioning` until a 7-day grace
//! collects it. A bootstrap that half-writes and then refuses manufactures that
//! state deliberately. **The rules are `PF_001`'s and unchanged; only the moment
//! of checking moved earlier**, and moving it earlier can only turn a partial
//! write into no write.
//!
//! ## Idempotency
//!
//! Provisioning steps are re-drivable (`provisioner.rs`: *"a partial prior run
//! that crashed between e.g. step 5 and step 6 can be re-driven to completion"*),
//! so seeding is too: every insert is `ON CONFLICT DO NOTHING` and a second run
//! over the same declaration is a no-op that reports zero new rows.

use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use uuid::Uuid;

/// The closed `MapKind` set as the database spells it (`0024_map_layout`'s
/// `map_layout_kind_closed`). `Vessel` is reserved in doc 36 and is absent here
/// for the same reason it is absent from the CHECK: a kind the engine cannot
/// interpret should not be writable.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MapKind {
    /// The root of a coordinate space; contains worlds.
    Universe,
    /// A planet or plane -- a whole generated surface.
    World,
    /// A geographic subdivision of a `World`, and RECURSIVE: a `Region` may hold
    /// `Region`s, which is why the retired ladder's three middle rungs collapse
    /// into this one kind (`SPG-R14`).
    Region,
    /// The tilemap-bearing kind (`SPG-R9`) -- a settlement-sized surface.
    Locale,
    /// An interior. The only kind a `place` row may describe (`0026`).
    Domain,
    /// A way between places, first-class because routing engines pay to get here.
    Passage,
    /// A space carved for an encounter; optional, per `R-6`.
    Arena,
}

impl MapKind {
    /// The lowercase spelling `0024_map_layout`s CHECK accepts.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Universe => "universe",
            Self::World => "world",
            Self::Region => "region",
            Self::Locale => "locale",
            Self::Domain => "domain",
            Self::Passage => "passage",
            Self::Arena => "arena",
        }
    }
}

/// `PF_001` §3.1's scalar core. The declaration an author writes.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlaceDecl {
    /// One of `PF_001` section 4s ten, lowercased.
    pub place_type: String,
    /// `BookCanonRef` — a shared schema whose ownership is deferred (`PF-D12`),
    /// so it travels as JSON rather than being given a shape here.
    pub canon_ref: serde_json::Value,
    /// Required at V1 -- the projects primary locale.
    pub name_vi: String,
    /// Optional at V1.
    pub name_en: Option<String>,
}

/// One node of the authored world.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeDecl {
    /// The `channels.id` this node will occupy, and therefore its `PlaceId`.
    pub id: i64,
    /// `None` for the single root; `0019` permits exactly one per reality.
    pub parent: Option<i64>,
    /// The reality's own word for this level — `DP-A13` keeps the data plane
    /// agnostic to it, which is why it is free text here and `kind` is not.
    pub level_name: String,
    /// The structural kind. Authoritative on the row, never derived (`SPG-Q1`).
    pub kind: MapKind,
    /// Parent-relative X in `MAP_001`s 0..1000 frame (`SPG-A5`).
    pub pos_x: i32,
    /// Parent-relative Y in the same frame.
    pub pos_y: i32,
    /// Required when `kind == Domain`, forbidden otherwise. Both directions are
    /// rejections, not warnings.
    pub place: Option<PlaceDecl>,
}

/// Why a bootstrap was refused. Each carries the `place.*` / `map.*` reject-rule
/// id it corresponds to, so the wire vocabulary is the one already registered in
/// `_boundaries/02_extension_contracts.md` rather than a second one invented here.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SeedReject {
    /// `place.missing_decl` — a `Domain` with no place declaration.
    MissingPlaceDecl { node: i64 },
    /// `place.invalid_place_type_for_channel_tier` — a place on a node whose
    /// kind is not `Domain`. The rule id keeps its name: an id is a contract,
    /// and the words inside it are not (`SPG-R14`).
    PlaceOnNonDomain { node: i64, kind: &'static str },
    /// Two declarations claiming one id.
    DuplicateNode { node: i64 },
    /// A parent that no declaration defines.
    UnknownParent { node: i64, parent: i64 },
    /// `map.containment_violation`'s structural half — the depth walk did not
    /// terminate, so the declaration is cyclic. `0019`'s `parent_depth` would
    /// refuse it too; catching it here means refusing before writing.
    CyclicParent { node: i64 },
    /// `DP-Ch1`'s `depth <= 16`, checked before the database has to.
    TooDeep { node: i64, depth: i32 },
    /// A root is a node with no parent. `0019`'s `channels_root_single` permits
    /// exactly one per reality.
    MultipleRoots { first: i64, second: i64 },
    /// No root at all — a forest is not a tree.
    NoRoot,
}

impl SeedReject {
    /// The registered reject-rule id, so a caller reports the vocabulary the
    /// boundary registry already owns.
    pub fn rule_id(&self) -> &'static str {
        match self {
            Self::MissingPlaceDecl { .. } => "place.missing_decl",
            Self::PlaceOnNonDomain { .. } => "place.invalid_place_type_for_channel_tier",
            Self::DuplicateNode { .. }
            | Self::UnknownParent { .. }
            | Self::CyclicParent { .. }
            | Self::TooDeep { .. }
            | Self::MultipleRoots { .. }
            | Self::NoRoot => "map.containment_violation",
        }
    }
}

/// What a successful seed wrote. Zeroes on a re-run are the idempotent case, not
/// a failure.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SeedReport {
    /// New `channels` rows. Zero on a re-run.
    pub channels_written: u64,
    /// New `map_layout` rows. Zero on a re-run.
    pub layouts_written: u64,
    /// New `place` rows. Zero on a re-run.
    pub places_written: u64,
}

/// `DP-Ch1`. Repeated here so the refusal happens before the database has to
/// make it — the same number, checked one layer earlier.
const MAX_DEPTH: i32 = 16;

/// Validate the whole declaration set. **Pure** — it touches no database, which
/// is what makes "reject writes nothing" true by construction rather than by
/// ordering discipline.
///
/// Returns each node's computed depth, in the declaration's own order.
pub fn validate(decls: &[NodeDecl]) -> Result<Vec<(i64, i32)>, SeedReject> {
    use std::collections::{HashMap, HashSet};

    let mut by_id: HashMap<i64, &NodeDecl> = HashMap::new();
    for d in decls {
        if by_id.insert(d.id, d).is_some() {
            return Err(SeedReject::DuplicateNode { node: d.id });
        }
    }

    // Exactly one root. `0019`'s `channels_root_single` is a partial unique
    // index and would refuse a second one; refusing here refuses it earlier.
    let mut root: Option<i64> = None;
    for d in decls {
        if d.parent.is_none() {
            match root {
                None => root = Some(d.id),
                Some(first) => {
                    return Err(SeedReject::MultipleRoots { first, second: d.id })
                }
            }
        }
    }
    if root.is_none() {
        return Err(SeedReject::NoRoot);
    }

    // Place declarations, both directions.
    for d in decls {
        match (d.kind, d.place.is_some()) {
            (MapKind::Domain, false) => {
                return Err(SeedReject::MissingPlaceDecl { node: d.id })
            }
            (k, true) if k != MapKind::Domain => {
                return Err(SeedReject::PlaceOnNonDomain {
                    node: d.id,
                    kind: k.as_str(),
                })
            }
            _ => {}
        }
    }

    // Depth by walking to the root. A walk longer than the node count cannot
    // terminate, which is the cycle.
    let n = decls.len();
    let mut depths: Vec<(i64, i32)> = Vec::with_capacity(n);
    for d in decls {
        let mut depth = 0i32;
        let mut cur = d;
        let mut seen: HashSet<i64> = HashSet::new();
        seen.insert(cur.id);
        while let Some(parent) = cur.parent {
            let next = by_id
                .get(&parent)
                .ok_or(SeedReject::UnknownParent { node: d.id, parent })?;
            if !seen.insert(next.id) {
                return Err(SeedReject::CyclicParent { node: d.id });
            }
            depth += 1;
            if depth > MAX_DEPTH {
                return Err(SeedReject::TooDeep { node: d.id, depth });
            }
            cur = next;
        }
        depths.push((d.id, depth));
    }

    Ok(depths)
}

/// Seed one reality's world structure. Validates the whole set first and writes
/// nothing if any rule refuses; otherwise writes all three tables in one
/// transaction, so a crash mid-write leaves no partial tree either.
pub async fn seed_world(
    pool: &PgPool,
    reality_id: Uuid,
    decls: &[NodeDecl],
) -> Result<SeedReport, SeedError> {
    let depths = validate(decls).map_err(SeedError::Rejected)?;
    let depth_of: std::collections::HashMap<i64, i32> = depths.into_iter().collect();

    let mut tx = pool.begin().await.map_err(SeedError::Db)?;
    let mut report = SeedReport {
        channels_written: 0,
        layouts_written: 0,
        places_written: 0,
    };

    // Parents before children, or the foreign key refuses a child whose parent
    // has not landed. Sorting by depth is the topological order for a tree.
    let mut ordered: Vec<&NodeDecl> = decls.iter().collect();
    ordered.sort_by_key(|d| (depth_of[&d.id], d.id));

    for d in &ordered {
        let depth = depth_of[&d.id];
        let r = sqlx::query(
            "INSERT INTO channels (reality_id, id, parent, level_name, depth, lifecycle) \
             VALUES ($1, $2, $3, $4, $5, 'active') ON CONFLICT DO NOTHING",
        )
        .bind(reality_id)
        .bind(d.id)
        .bind(d.parent)
        .bind(&d.level_name)
        .bind(depth as i16)
        .execute(&mut *tx)
        .await
        .map_err(SeedError::Db)?;
        report.channels_written += r.rows_affected();

        let r = sqlx::query(
            "INSERT INTO map_layout (reality_id, channel_id, kind, pos_x, pos_y) \
             VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING",
        )
        .bind(reality_id)
        .bind(d.id)
        .bind(d.kind.as_str())
        .bind(d.pos_x)
        .bind(d.pos_y)
        .execute(&mut *tx)
        .await
        .map_err(SeedError::Db)?;
        report.layouts_written += r.rows_affected();

        if let Some(p) = &d.place {
            let r = sqlx::query(
                "INSERT INTO place (reality_id, place_id, place_type, canon_ref, name_vi, name_en) \
                 VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING",
            )
            .bind(reality_id)
            .bind(d.id)
            .bind(&p.place_type)
            .bind(&p.canon_ref)
            .bind(&p.name_vi)
            .bind(&p.name_en)
            .execute(&mut *tx)
            .await
            .map_err(SeedError::Db)?;
            report.places_written += r.rows_affected();
        }
    }

    tx.commit().await.map_err(SeedError::Db)?;
    Ok(report)
}

/// A refusal is not a database error and the two must not be conflated — the
/// caller retries one and reports the other.
#[derive(Debug)]
pub enum SeedError {
    /// A rule refused the declaration. Retrying without changing it will refuse
    /// again -- this is the operator's to fix, not the scheduler's.
    Rejected(SeedReject),
    /// The database failed. Retryable, and not the caller's fault.
    Db(sqlx::Error),
}

impl std::fmt::Display for SeedError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Rejected(r) => write!(f, "{} ({:?})", r.rule_id(), r),
            Self::Db(e) => write!(f, "database error: {e}"),
        }
    }
}

impl std::error::Error for SeedError {}

#[cfg(test)]
mod tests {
    use super::*;

    fn node(id: i64, parent: Option<i64>, kind: MapKind) -> NodeDecl {
        NodeDecl {
            id,
            parent,
            level_name: format!("n{id}"),
            kind,
            pos_x: 1,
            pos_y: 1,
            place: if kind == MapKind::Domain {
                Some(PlaceDecl {
                    place_type: "tavern".into(),
                    canon_ref: serde_json::json!({"kind": "BookChapter"}),
                    name_vi: "Quan Tra".into(),
                    name_en: None,
                })
            } else {
                None
            },
        }
    }

    #[test]
    fn a_legal_world_validates_and_reports_depths() {
        let d = vec![
            node(1, None, MapKind::World),
            node(2, Some(1), MapKind::Region),
            node(3, Some(2), MapKind::Domain),
        ];
        let depths = validate(&d).expect("legal world");
        assert_eq!(depths, vec![(1, 0), (2, 1), (3, 2)]);
    }

    #[test]
    fn a_domain_without_a_place_is_refused() {
        let mut d = vec![node(1, None, MapKind::World), node(2, Some(1), MapKind::Domain)];
        d[1].place = None;
        assert_eq!(
            validate(&d).unwrap_err(),
            SeedReject::MissingPlaceDecl { node: 2 }
        );
        assert_eq!(validate(&d).unwrap_err().rule_id(), "place.missing_decl");
    }

    #[test]
    fn a_place_on_a_non_domain_is_refused() {
        let mut d = vec![node(1, None, MapKind::World), node(2, Some(1), MapKind::Locale)];
        d[1].place = Some(PlaceDecl {
            place_type: "tavern".into(),
            canon_ref: serde_json::json!({}),
            name_vi: "x".into(),
            name_en: None,
        });
        assert_eq!(
            validate(&d).unwrap_err(),
            SeedReject::PlaceOnNonDomain { node: 2, kind: "locale" }
        );
    }

    #[test]
    fn two_roots_are_refused() {
        let d = vec![node(1, None, MapKind::World), node(2, None, MapKind::World)];
        assert_eq!(
            validate(&d).unwrap_err(),
            SeedReject::MultipleRoots { first: 1, second: 2 }
        );
    }

    #[test]
    fn no_root_is_refused() {
        // A two-node cycle has no root, and NoRoot is found first.
        let d = vec![node(1, Some(2), MapKind::World), node(2, Some(1), MapKind::World)];
        assert_eq!(validate(&d).unwrap_err(), SeedReject::NoRoot);
    }

    #[test]
    fn a_cycle_below_a_root_is_refused() {
        let d = vec![
            node(1, None, MapKind::World),
            node(2, Some(3), MapKind::Region),
            node(3, Some(2), MapKind::Region),
        ];
        assert_eq!(validate(&d).unwrap_err(), SeedReject::CyclicParent { node: 2 });
    }

    #[test]
    fn an_unknown_parent_is_refused() {
        let d = vec![node(1, None, MapKind::World), node(2, Some(99), MapKind::Region)];
        assert_eq!(
            validate(&d).unwrap_err(),
            SeedReject::UnknownParent { node: 2, parent: 99 }
        );
    }

    #[test]
    fn a_duplicate_id_is_refused() {
        let d = vec![node(1, None, MapKind::World), node(1, Some(1), MapKind::Region)];
        assert_eq!(validate(&d).unwrap_err(), SeedReject::DuplicateNode { node: 1 });
    }

    #[test]
    fn depth_past_dp_ch1s_sixteen_is_refused() {
        let mut d = vec![node(1, None, MapKind::World)];
        for i in 2..=19i64 {
            d.push(node(i, Some(i - 1), MapKind::Region));
        }
        match validate(&d).unwrap_err() {
            SeedReject::TooDeep { node, depth } => {
                assert_eq!(node, 18);
                assert_eq!(depth, 17);
            }
            other => panic!("wanted TooDeep, got {other:?}"),
        }
    }
}

//! The per-reality actor registry — `S-9`'s conversion site, and the PRODUCER
//! `actor_control_binding` has been pointing at since migration `034`.
//!
//! # Why this is a library module and not SQL in a handler
//!
//! Two callers need it and they need different halves. Creating an actor is a
//! write; *checking* that an actor exists is a read the GRANT path must do
//! before it records a binding — because a binding to an actor that does not
//! exist is the dangling pointer `S-9` describes, and refusing it at the write
//! edge is cheaper than discovering it in a resolver at turn time.
//!
//! # `actors` is a PER-REALITY table
//!
//! So the SQL is here rather than behind the Go meta-write bridge. `I8` and
//! `meta-write-discipline-lint` govern the META tables — the lint derives its
//! table list from `migrations/meta/*.up.sql`, and `actors` is not in it. The
//! audit trail for who created an actor is the `actor.control.granted` event on
//! the binding, which is a meta write and does go through `MetaWrite`.

use dp::RealityId;
use sqlx::{PgPool, Row};
use uuid::Uuid;

use crate::errors::ProvisionerError;
use crate::spawn::Siting;

/// One row of the registry: the platform's identity, and the island's.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ActorRow {
    /// What `actor_control_binding.actor_id` points at.
    pub actor_id: Uuid,
    /// What the island acts on — `sim_core::EntityId`'s inner `u64`.
    ///
    /// `i64` here and `u64` there: Postgres has no unsigned integer, and the
    /// registry ALLOCATES from an identity column, so the values are small and
    /// positive by construction. The conversion is the caller's and is checked
    /// at the one place it happens rather than assumed all over.
    pub entity_id: i64,
}

/// Create an actor in `reality`, letting the registry allocate its `entity_id`.
///
/// The allocation is the point. If the island kept assigning ids and this table
/// merely recorded them, the two would be a second SSOT for one number and
/// would drift the first time an actor was created twice.
pub async fn create_actor(
    reality_pool: &PgPool,
    reality: &RealityId,
    siting: Option<&Siting>,
) -> Result<ActorRow, ProvisionerError> {
    let actor_id = Uuid::new_v4();

    // ONE TRANSACTION, and `A3` is the reason. An actor row that exists with
    // nowhere to be is the half-written state `world_seed` refuses on the world
    // side -- and there the repo at least has `orphan_scan` to collect the
    // wreckage. An actor with no binding has no collector at all, so the two
    // writes commit together or neither does.
    let mut tx = reality_pool
        .begin()
        .await
        .map_err(|e| ProvisionerError::Bridge(format!("begin: {e}")))?;

    let row = sqlx::query(
        "INSERT INTO actors (reality_id, actor_id) VALUES ($1, $2) RETURNING entity_id",
    )
    .bind(reality.as_uuid())
    .bind(actor_id)
    .fetch_one(&mut *tx)
    .await
    .map_err(|e| ProvisionerError::Bridge(format!("create actor: {e}")))?;
    let entity_id = row.get::<i64, _>("entity_id");

    if let Some(s) = siting {
        crate::spawn::site_in_cell(&mut tx, reality.as_uuid(), entity_id, s).await?;
    }

    tx.commit().await.map_err(|e| ProvisionerError::Bridge(format!("commit: {e}")))?;
    Ok(ActorRow { actor_id, entity_id })
}

/// Adopt an entity the island already has, under an explicit `entity_id`.
///
/// Exists for exactly one reason: `bin/spine.rs` hardcodes `EntityId(1)`, `(2)`
/// and `(3)`, and those actors are real in every running island. Without a way
/// to register them at their existing ids, the registry could only describe
/// actors created after it shipped, and the demo spine would be undrivable by
/// the feature built to drive it.
pub async fn adopt_actor(
    reality_pool: &PgPool,
    reality: &RealityId,
    siting: Option<&Siting>,
    entity_id: i64,
) -> Result<ActorRow, ProvisionerError> {
    // REFUSE AN ID THE ISLAND CANNOT HOLD, at the edge that can still say no —
    // see [`checked_island_id`] for what "cannot hold" means and why it was
    // reachable at all.
    let entity_id = checked_island_id(reality, entity_id)?;

    let actor_id = Uuid::new_v4();

    // ONE TRANSACTION -- `A3`. Same reason as `create_actor`, plus one this path
    // already documented below: the row and the sequence advance are one fact,
    // and committing the row without the advance is the collision that comment
    // predicts. A transaction is strictly stronger than the "re-run the adopt"
    // repair it currently offers.
    let mut tx = reality_pool
        .begin()
        .await
        .map_err(|e| ProvisionerError::Bridge(format!("begin: {e}")))?;

    sqlx::query("INSERT INTO actors (reality_id, actor_id, entity_id) VALUES ($1, $2, $3)")
        .bind(reality.as_uuid())
        .bind(actor_id)
        .bind(entity_id)
        .execute(&mut *tx)
        .await
        .map_err(|e| ProvisionerError::Bridge(format!("adopt actor {entity_id}: {e}")))?;

    if let Some(s) = siting {
        crate::spawn::site_in_cell(&mut tx, reality.as_uuid(), entity_id, s).await?;
    }

    // ADVANCE THE SEQUENCE PAST WHAT WE JUST ADOPTED.
    //
    // `GENERATED BY DEFAULT AS IDENTITY` does not move its sequence when the
    // value is supplied explicitly. So adopting the spine's `EntityId(1)` and
    // then allocating leaves the allocator still sitting at 1 — the very next
    // `create_actor` claims 1, hits `actors_entity_id_unique`, and dies with
    // `duplicate key value violates unique constraint`. Measured against a real
    // Postgres, and it fires in exactly the scenario adoption exists for:
    // register the island's existing 1..3, then create anyone new.
    //
    // The constraint means nothing is corrupted — the write is refused — but a
    // refusal an operator cannot read is still an outage. `setval` over the
    // table's MAX is the standard repair and is idempotent: adopting a LOWER id
    // than one already present leaves the sequence where it was.
    sqlx::query(
        "SELECT setval(pg_get_serial_sequence('actors', 'entity_id'), \
         GREATEST((SELECT COALESCE(MAX(entity_id), 1) FROM actors), 1))",
    )
    .execute(&mut *tx)
    .await
    .map_err(|e| {
        ProvisionerError::Bridge(format!(
            "adopt actor {entity_id}: the identity sequence did not \
             advance ({e}); the transaction rolled back, so a re-run is safe"
        ))
    })?;

    tx.commit().await.map_err(|e| ProvisionerError::Bridge(format!("commit: {e}")))?;
    Ok(ActorRow { actor_id, entity_id })
}

/// Is this `BIGINT` a number the island can actually hold?
///
/// `actors.entity_id` is `BIGINT`; `sim_core::EntityId` is a `u64`. `0022` put
/// no `CHECK` on the column, and it had a reason not to need one — the identity
/// sequence allocates positives. But `GENERATED BY DEFAULT` exists precisely so
/// an explicit value CAN be supplied, and [`adopt_actor`] is the one place that
/// supplies one, straight from an operator's `--entity-id`.
///
/// So `admin reality create-actor --entity-id -1` succeeded; the grant that
/// followed succeeded; and the actor was then permanently unable to act —
/// `commit_service::subject` refuses a negative with `NotAnEntityId` at turn
/// time, correctly, because `-1 as u64` is `u64::MAX`: a well-typed number
/// naming an entity that does not exist. A character that could be created and
/// granted and never used, with nothing on the path saying so.
///
/// **One function, called from both edges**, because the two halves of that
/// sentence have to agree: [`adopt_actor`] refuses to CREATE one, and
/// `actor_control_flow::resolve_subject` refuses to REPORT one that predates
/// the guard. A rule enforced by two `u64::try_from` calls in two files is a
/// rule that gets half-changed.
///
/// A `CHECK (entity_id >= 0)` on the table would be stronger still and is not
/// here: `0022` is applied per reality at provision time, so a new migration
/// only reaches worlds provisioned after it. That is the migrate-existing-
/// realities job, not this one — recorded, not skipped.
pub fn checked_island_id(reality: &RealityId, entity_id: i64) -> Result<i64, ProvisionerError> {
    if is_island_id(entity_id) {
        Ok(entity_id)
    } else {
        Err(ProvisionerError::CorruptEntityId(reality.as_uuid().to_string(), entity_id))
    }
}

/// The RULE itself, with no reality attached.
///
/// Split out from [`checked_island_id`] for two reasons that point the same
/// way. `reality-id-adoption-gate` is the first: a function on a bindable path
/// taking a bare `Uuid` is adoptable debt, and the fix is to take
/// [`RealityId`] — which has no public constructor, so a unit test cannot make
/// one. Rather than exempt the gate or drop the test, the predicate that
/// actually needs testing moved somewhere a test can reach it.
///
/// The second is that it is the honest decomposition anyway: whether a number
/// is an island id has nothing to do with which reality it is in. Only the
/// ERROR needs the reality, and only to name it.
pub fn is_island_id(entity_id: i64) -> bool {
    u64::try_from(entity_id).is_ok()
}

/// Does this actor exist in this reality?
///
/// The GRANT path's precondition. `034` left `actor_id` unconstrained because
/// its FK lives in another database — that is a correct reason not to have a
/// foreign key and a bad reason to skip the check, so the check happens here,
/// in the one process that can reach both databases.
pub async fn actor_exists(
    reality_pool: &PgPool,
    reality: &RealityId,
    actor_id: Uuid,
) -> Result<bool, ProvisionerError> {
    let row = sqlx::query("SELECT 1 FROM actors WHERE reality_id = $1 AND actor_id = $2")
        .bind(reality.as_uuid())
        .bind(actor_id)
        .fetch_optional(reality_pool)
        .await
        .map_err(|e| ProvisionerError::Bridge(format!("actor lookup: {e}")))?;
    Ok(row.is_some())
}

/// The island id for an actor, or `None` when the actor is unknown here.
///
/// This is the function `S-9` says has zero instances. Everything else in this
/// module exists so that this one can answer.
pub async fn entity_id_for(
    reality_pool: &PgPool,
    reality: &RealityId,
    actor_id: Uuid,
) -> Result<Option<i64>, ProvisionerError> {
    let row = sqlx::query("SELECT entity_id FROM actors WHERE reality_id = $1 AND actor_id = $2")
        .bind(reality.as_uuid())
        .bind(actor_id)
        .fetch_optional(reality_pool)
        .await
        .map_err(|e| ProvisionerError::Bridge(format!("entity_id lookup: {e}")))?;
    Ok(row.map(|r| r.get::<i64, _>("entity_id")))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The guard refuses exactly what the island cannot hold, and nothing else.
    ///
    /// Both directions on purpose. A test that only checked `-1` would pass
    /// just as well against `Err(_)` for every input — which would make the
    /// spine's own `EntityId(1)`, the case adoption exists for, unadoptable.
    #[test]
    fn a_negative_island_id_is_refused_and_a_real_one_is_not() {
        assert!(is_island_id(1), "the spine's EntityId(1) must adopt");
        assert!(is_island_id(0));
        assert!(is_island_id(i64::MAX));

        // Non-vacuity in both directions. A predicate that answered `false` for
        // everything would satisfy the negatives below and make the spine's own
        // actors unadoptable — the case adoption exists for.
        for bad in [-1_i64, i64::MIN] {
            assert!(!is_island_id(bad), "a negative is not an island id: {bad}");
        }
    }

    /// What the unchecked version would have produced instead of a refusal.
    ///
    /// The same assertion `commit_service::subject` makes, restated at the
    /// WRITE edge: `-1 as u64` is not a rejected value, it is
    /// `18446744073709551615` — a perfectly well-typed entity id naming nobody.
    /// That is a wrong subject presented as a valid one, which is worse than
    /// the refusal it replaces.
    #[test]
    fn casting_instead_of_checking_would_have_invented_an_entity() {
        assert_eq!(-1_i64 as u64, u64::MAX);
        assert!(u64::try_from(-1_i64).is_err());
    }
}

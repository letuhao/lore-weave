//! `spawn` — siting an entity in a place. `PF_001` §5 step 5.
//!
//! ## Why this is its own module and not part of `world_seed`
//!
//! [`crate::world_seed`] stops deliberately, and says so in its own header:
//! *"`0025_entity_binding` is deliberately **not** written here: siting an actor
//! is `PF_001`'s step 5, and `PF_001` states in its own header that
//! **spawn-into-place is consumer responsibility**. This module makes the place
//! exist and stops."*
//!
//! This is the consumer. It is not `world_seed`'s job and it is not
//! actor-specific either — `entity_binding` holds items and environment objects
//! under the same primary key, so a module named for actors would have to grow
//! a second name the first time an item was dropped on the floor.
//!
//! ## `Q1` — who owns spawn, answered by copying rather than deciding
//!
//! `entity_binding` is a join between two owners: the actor registry knows what
//! an entity IS, and the space tree knows where a place is. That is exactly why
//! it had no producer. The plan's `Q1` said to follow an existing two-owner
//! write in this repo rather than invent an answer, and there is one:
//! `actor_registry::create_actor` already writes `actors` in the reality's own
//! database, holding both facts at once. Spawn rides the same path, in the same
//! database, in the **same transaction**.
//!
//! ## `Q2` — spawn is an ADMIN act, not a proposal
//!
//! The proven gameplay pipeline is `browser -> proposal -> spine -> hub ->
//! events -> DOM`, and a player-initiated MOVE belongs in it. **Arriving does
//! not.** An actor is created by an operator or a bootstrap through
//! `POST /internal/v1/actors`, never by the actor, so the act that puts it
//! somewhere is the same kind of act that brought it into being. Siting rides
//! actor creation for that reason and not for convenience.
//!
//! ## ATOMICITY IS THE PROPERTY, and it is why this takes a transaction
//!
//! An actor row that exists with nowhere to be is precisely the half-written
//! state [`crate::world_seed`] refuses on the world side — and there the repo's
//! own reason was `orphan_scan`, which exists because a half-provisioned reality
//! sits until a 7-day grace collects it. An actor with no binding has no such
//! collector at all.
//!
//! So [`site_in_cell`] takes a `&mut PgConnection` rather than a pool: the
//! caller owns the transaction, the actor row and the binding land together or
//! neither does, and a bad node id takes the actor row down with it.
//!
//! ## What this module will NOT choose
//!
//! `lifecycle_state` is a **declared ordinal**, and `0025`'s own comment says
//! why: *"`D-12`: a DECLARED state ordinal, not a closed engine enum. Existing /
//! Suspended / Destroyed / Removed is ONE REALITY'S VOCABULARY, not the
//! engine's."* No reality has declared one yet — `contracts/meta/transitions.yaml`
//! carries the `reality` resource and nothing for entities — so the caller
//! supplies the ordinal and this module does not default it. **A hardcoded `0`
//! here would be the engine deciding a reality's vocabulary**, which is the rot
//! this repo names by example.

use serde::{Deserialize, Serialize};
use sqlx::PgConnection;
use uuid::Uuid;

use crate::errors::ProvisionerError;

/// `0025_entity_binding`'s `entity_binding_type_closed` CHECK, as a type.
///
/// Closed here as well as in SQL for the reason `0025` gives about its own
/// repeated CHECK: an enumerated set of call sites is default-uncovered
/// (`NV-3`). A `&str` would let a typo reach the database and come back as a
/// constraint violation with no name attached to the mistake.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EntityType {
    /// A player character.
    Pc,
    /// A non-player character.
    Npc,
    /// An item.
    Item,
    /// Scenery an entity can interact with.
    EnvObject,
}

impl EntityType {
    /// The wire and column spelling. Matches `entity_binding_type_closed`.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Pc => "pc",
            Self::Npc => "npc",
            Self::Item => "item",
            Self::EnvObject => "env_object",
        }
    }
}

/// Where an entity is being put, and as what.
///
/// Only the `in_cell` variant of `EntityLocation` is expressible here. The other
/// three (`held_by`, `in_container`, `embedded`) are real and are **not** this
/// row's business: an item in a backpack arrives by being put there, which is an
/// inventory operation with an owner that does not exist yet. Adding the fields
/// now would decide that owner by accident.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Siting {
    /// The `channels.id` to site the entity in. A real node in THIS reality —
    /// `0025`'s foreign key is `ON DELETE RESTRICT`, so a bad id is refused
    /// rather than silently nulled.
    pub node: i64,
    /// The discriminator `EF_001` §3.1 stores denormalised.
    pub entity_type: EntityType,
    /// The reality's declared lifecycle ordinal. **Not defaulted** — see the
    /// module header.
    pub lifecycle_state: i16,
}

/// Site an entity in a cell, on a connection the CALLER holds a transaction on.
///
/// Takes `&mut PgConnection` and not `&PgPool` on purpose: see the module
/// header. A pool would let this commit independently of whatever created the
/// entity, which is the orphan this module exists to make impossible.
///
/// Idempotent by primary key: re-siting an entity already bound is an error, not
/// a silent move. Moving is a different verb with different rules (`R-52`
/// evacuate-never-delete), and letting an INSERT double as a move would make the
/// two indistinguishable in the log.
pub async fn site_in_cell(
    conn: &mut PgConnection,
    reality: Uuid,
    entity_id: i64,
    siting: &Siting,
) -> Result<(), ProvisionerError> {
    sqlx::query(
        "INSERT INTO entity_binding \
         (reality_id, entity_id, entity_type, location_kind, cell_id, lifecycle_state) \
         VALUES ($1, $2, $3, 'in_cell', $4, $5)",
    )
    .bind(reality)
    .bind(entity_id)
    .bind(siting.entity_type.as_str())
    .bind(siting.node)
    .bind(siting.lifecycle_state)
    .execute(conn)
    .await
    .map_err(|e| ProvisionerError::InvalidState(format!("site entity {entity_id}: {e}")))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_entity_type_spells_itself_the_way_the_check_does() {
        // `0025_entity_binding`'s `entity_binding_type_closed` enumerates these
        // four. A rename here that the CHECK does not know about is refused by
        // Postgres at INSERT time -- at which point the failure is a constraint
        // violation in a log, not a test naming the mistake.
        assert_eq!(EntityType::Pc.as_str(), "pc");
        assert_eq!(EntityType::Npc.as_str(), "npc");
        assert_eq!(EntityType::Item.as_str(), "item");
        assert_eq!(EntityType::EnvObject.as_str(), "env_object");
    }

    #[test]
    fn the_wire_form_and_the_column_form_are_the_same_string() {
        // Two spellings of one value is the drift `world_seed`'s wire-spelling
        // pin exists to prevent, one table over. `serde(rename_all)` and
        // `as_str` are two implementations, so they get compared rather than
        // assumed equal.
        for t in [EntityType::Pc, EntityType::Npc, EntityType::Item, EntityType::EnvObject] {
            let wire = serde_json::to_string(&t).expect("serialize");
            assert_eq!(wire.trim_matches('"'), t.as_str(), "{t:?}");
        }
    }
}

//! `actor_control_binding` — the OWNER-SCOPED read, and the only sanctioned
//! one in Rust.
//!
//! # Why this lives in `meta-rs` and not in the two services that need it
//!
//! `scripts/meta-sensitive-read-bypass-lint.sh` forbids a bare
//! `SELECT … FROM actor_control_binding` anywhere under `services/`,
//! `contracts/` or `crates/`, and excuses individual files by NAME. Until this
//! module existed its exclusion list carried `commit-service/src/subject.rs`
//! with a comment stating the problem out loud:
//!
//! > *"There is NO RUST-SIDE SANCTIONED READER. The audit wrapper this lint
//! > points callers at is `contracts/meta`, which is Go… A Rust service
//! > therefore cannot comply by any route — the only compliant Rust read is one
//! > that does not happen."*
//!
//! A second Rust caller would have added a second name to that list, and a list
//! that grows by one per caller is `NV-3`'s default-uncovered shape: the next
//! author adds a line and the gate keeps saying PASS. So the read moved to the
//! Meta Access Library, which is what the lint already treats as the compliant
//! home for `contracts/meta` on the Go side. **The exclusion list now names one
//! LIBRARY instead of one caller per service.**
//!
//! # Owner-scoped is a different tier from cross-user, and the contract says so
//!
//! `contracts/meta/meta-sensitive-read-paths.yml` describes the audited path
//! `actor_binding_cross_user` as, verbatim:
//!
//! ```text
//! SELECT * FROM actor_control_binding WHERE user_ref_id != $caller_user
//! ```
//!
//! The `!=` is the registration. *"Which actor do I drive?"* is a question
//! about yourself, and it writes no `meta_read_audit` row — the same reason the
//! GDPR erasure cascade's owner-scoped read does not. The cross-user direction
//! ("who drives THIS actor") is a separate capability that goes through the Go
//! bridge and IS audited; nothing here reaches it, and [`OWNER_SCOPED_SQL`]'s
//! test is what keeps that true.

use uuid::Uuid;

use crate::errors::MetaError;

/// The query, as a `const` so a test can assert on the bytes that actually run.
///
/// **Not a source scan of some other file — this is the string handed to
/// Postgres.** The three predicates each close a distinct hole, and losing any
/// one of them turns a sanctioned read into something else entirely while it
/// sits inside the bypass lint's exclusion, which is the worst place in the
/// repo for that drift to be invisible:
///
/// * `reality_id = $1` — a human exists across realities, so an unscoped read
///   would answer with a binding from a world the caller never named.
/// * `user_ref_id = $2` — **drop this one and the function is a cross-user
///   read**, the exact shape `actor_binding_cross_user` registers as sensitive,
///   living in the one module the lint has been told to ignore.
/// * `revoked_at IS NULL` — a revoked binding is history. Treating it as
///   authority is precisely the hole the revoke exists to close.
pub const OWNER_SCOPED_SQL: &str = "SELECT actor_id FROM actor_control_binding \
     WHERE reality_id = $1 AND user_ref_id = $2 AND revoked_at IS NULL";

/// Which actor does `user_ref_id` currently drive in `reality_id`?
///
/// `None` means they drive nobody there — the ordinary answer for a spectator,
/// and the ordinary answer one instant after a revoke. It is a normal state,
/// not an error, which is why it is an `Option` and not a `MetaError` variant.
///
/// The returned `actor_id` is the PLATFORM identity. Converting it to the
/// island's `entity_id` is a second hop into the PER-REALITY database, which
/// this crate deliberately does not open — see the crate's own
/// `[package.metadata.dp]` note: it resolves routing for others rather than
/// consuming it.
#[cfg(feature = "sqlx-pg")]
pub async fn live_binding_actor(
    meta: &sqlx::PgPool,
    reality_id: Uuid,
    user_ref_id: Uuid,
) -> Result<Option<Uuid>, MetaError> {
    use sqlx::Row;

    let row = sqlx::query(OWNER_SCOPED_SQL)
        .bind(reality_id)
        .bind(user_ref_id)
        .fetch_optional(meta)
        .await
        .map_err(|e| MetaError::Backend(Box::new(e)))?;
    Ok(row.map(|r| r.get::<Uuid, _>("actor_id")))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Every predicate that makes this read owner-scoped, asserted on the
    /// string that is actually executed.
    ///
    /// This is not decoration. The module is EXCLUDED from
    /// `meta-sensitive-read-bypass-lint.sh` — deleting ` AND user_ref_id = $2`
    /// would turn `live_binding_actor` into an unaudited cross-user read and
    /// the lint, by construction, would not look. The compiler would not
    /// either: the function still compiles with two bind calls and one
    /// placeholder, and fails only at runtime against a live database.
    #[test]
    fn the_query_is_scoped_to_one_reality_and_one_user_and_ignores_revoked_rows() {
        assert!(
            OWNER_SCOPED_SQL.contains("reality_id = $1"),
            "unscoped by reality: {OWNER_SCOPED_SQL}"
        );
        assert!(
            OWNER_SCOPED_SQL.contains("user_ref_id = $2"),
            "THIS IS A CROSS-USER READ — it must not live in a module the bypass \
             lint excuses: {OWNER_SCOPED_SQL}"
        );
        assert!(
            OWNER_SCOPED_SQL.contains("revoked_at IS NULL"),
            "a revoked binding is history, not authority: {OWNER_SCOPED_SQL}"
        );
        // The registered sensitive path is the `!=` direction. A query built
        // here must never be it, however it came to be spelled.
        assert!(
            !OWNER_SCOPED_SQL.contains("!="),
            "the cross-user direction is a different, AUDITED capability: {OWNER_SCOPED_SQL}"
        );
    }

    /// The read touches exactly one table, and it is the one the doc names.
    ///
    /// A `JOIN` added here would pull a second meta table into a path the
    /// sensitive-read contract has scoped to one — and the contract lists
    /// tables per path, so the join partner would be governed by nothing.
    #[test]
    fn it_reads_one_table_and_joins_nothing() {
        assert_eq!(OWNER_SCOPED_SQL.matches(" FROM ").count(), 1);
        assert!(!OWNER_SCOPED_SQL.to_ascii_uppercase().contains("JOIN"));
        assert!(OWNER_SCOPED_SQL.contains("FROM actor_control_binding"));
    }
}

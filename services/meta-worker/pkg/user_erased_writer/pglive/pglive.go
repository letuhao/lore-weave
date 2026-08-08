// Package pglive is the production pgx implementation of user_erased_writer's
// UserRealityLookup + PerRealityDB interfaces (P2/071 Slice 1).
//
// The user_erased_writer package is driver-clean (interfaces only); these
// adapters add the pgx dependency:
//   - PgUserRealityLookup reads the META control plane
//     (actor_control_binding) to find which realities a user drives an actor in.
//   - PgPerRealityScrubber scrubbed the user's PII in a PER-REALITY projection.
//     **It has nothing to scrub since 2026-08-04 — see below.**
//
// `pc_projection` was the ONLY per-reality projection that referenced `user_id`
// (verified against contracts/migrations/per_reality/0006_projections), and
// `0017` dropped it. So NO per-reality projection carries a user reference any
// more, and the per-reality leg of the erasure cascade has no subject.
//
// Left issuing its UPDATE, it would have been worse than useless: the statement
// targets a table Postgres no longer has, so it errors, the handler NACKs (by
// design — leaving PII alive is the unsafe direction), and the erasure retries
// forever without ever completing. A GDPR pipeline wedged shut is not a safe
// failure just because it fails closed.
package pglive

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	uew "github.com/loreweave/foundation/services/meta-worker/pkg/user_erased_writer"
)

// PgUserRealityLookup resolves the realities a user touched from the meta
// control plane's user->actor bindings.
type PgUserRealityLookup struct {
	meta *pgxpool.Pool
}

// NewPgUserRealityLookup binds the meta pool.
func NewPgUserRealityLookup(meta *pgxpool.Pool) *PgUserRealityLookup {
	return &PgUserRealityLookup{meta: meta}
}

var _ uew.UserRealityLookup = (*PgUserRealityLookup)(nil)

// RealitiesForUser returns the distinct realities where the user drives an actor.
//
// Q-L5H-1 inverted: over-inclusion is safe (the cascade is idempotent), which is
// why there is NO `revoked_at IS NULL` filter. A revoked binding still means the
// user was there, and a reality the cascade skips is PII left alive — the unsafe
// direction. Reading every row is the conservative choice and it is deliberate,
// not an omission.
//
// OWNER-scoped (`WHERE user_ref_id = $1`), so this is not the cross-user read
// registered as `actor_binding_cross_user`; scripts/meta-sensitive-read-bypass-lint.sh
// exempts this package for exactly that reason.
// **W6 addition — OWNED realities count too.** This used to read only
// `actor_control_binding`, so a user who OWNS a reality but drives no actor in
// it was invisible to the entire cascade: every per-reality scrub skipped it,
// and the reality kept their data. Ownership arrived in migration 036 and this
// query did not move with it. The UNION is the conservative direction the
// paragraph above already argues for.
func (l *PgUserRealityLookup) RealitiesForUser(ctx context.Context, userID uuid.UUID) ([]uuid.UUID, error) {
	rows, err := l.meta.Query(ctx,
		`SELECT reality_id FROM actor_control_binding WHERE user_ref_id = $1
         UNION
         SELECT reality_id FROM reality_registry   WHERE owner_user_id = $1`, userID)
	if err != nil {
		return nil, fmt.Errorf("pglive: query realities for user %s: %w", userID, err)
	}
	defer rows.Close()
	var out []uuid.UUID
	for rows.Next() {
		var rid uuid.UUID
		if err := rows.Scan(&rid); err != nil {
			return nil, fmt.Errorf("pglive: scan reality_id: %w", err)
		}
		out = append(out, rid)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("pglive: iterate realities: %w", err)
	}
	return out, nil
}

// PoolResolver maps a reality_id to its per-reality DB pool. Production binds
// this to the meta-worker's per-reality pool set (realityreg); tests inject a
// single-pool resolver.
type PoolResolver func(realityID uuid.UUID) (*pgxpool.Pool, error)

// PgPerRealityScrubber scrubs a user's PII references in one reality's
// projections. **Currently a no-op with no subject** — see ScrubUserRefs.
//
// The type and its wiring are kept rather than deleted because the SEAM is real:
// the cascade must reach every reality a user touched, and the first per-reality
// table to carry a user reference will need exactly this. What is NOT kept is a
// pretence that it is doing something.
type PgPerRealityScrubber struct {
	resolve PoolResolver
}

// NewPgPerRealityScrubber binds the per-reality pool resolver.
func NewPgPerRealityScrubber(resolve PoolResolver) *PgPerRealityScrubber {
	return &PgPerRealityScrubber{resolve: resolve}
}

var _ uew.PerRealityDB = (*PgPerRealityScrubber)(nil)

// ScrubUserRefs has NO PER-REALITY PII TO SCRUB since `0017`.
//
// It still resolves the reality's pool, because a reality the cascade cannot
// reach at all is a real failure worth surfacing (the lookup said the user
// touched it) and because that is the check the first real scrub will need. It
// then does nothing and reports success, which is the honest outcome when the
// set of columns to scrub is empty.
//
// **The emptiness is not assumed, it is asserted**:
// TestNoPerRealityTableCarriesAUserReference walks the migrations and fails the
// moment a surviving per-reality table declares a `user_id`, naming this method
// as the thing that must be written. Without that test this would be a silent
// erasure hole the day such a column lands — which is a far worse bug than the
// one it replaces.
func (s *PgPerRealityScrubber) ScrubUserRefs(_ context.Context, in uew.ScrubIntent) error {
	if _, err := s.resolve(in.RealityID); err != nil {
		return fmt.Errorf("pglive: resolve pool for reality %s: %w", in.RealityID, err)
	}
	return nil
}

// PgMetaScrubber removes the user's META references — since migration 034/035,
// their `actor_control_binding` rows.
//
// **What changed, and why it is a DELETE and not a scrub.** It used to tombstone
// `player_character_index.pc_name` to a sentinel, because that column was the
// last PII the meta tier held about a user's characters. `actor_control_binding`
// has no name, no presence and no status — it is three opaque uuids — so there
// is nothing left to overwrite, and what erasure owes is removal of the
// REFERENCE itself. That is the `@erasure_method: hard_delete` the migration
// header declares; leaving the annotation with no deleter would be a promise
// nothing keeps.
//
// It routes through contracts/meta MetaWriteBatch (one DELETE intent per row) so
// each removal is same-TX-audited in meta_write_audit and (if cfg.Outbox is set)
// emits `actor.control.erased`. Enumerate-then-batch — the shape the KEK shred
// uses — keeps a multi-actor erasure atomic, and an empty enumeration makes a
// re-run a no-op, which is the idempotence the writer contract requires.
//
// ⚠ ORDER IS LOAD-BEARING: `Writer.Handle` runs this AFTER the per-reality
// cascade, and it must stay that way. These rows ARE the input to
// `RealitiesForUser`; deleting them first would leave the cascade with an empty
// list of realities to visit and report success over nothing.
type PgMetaScrubber struct {
	meta    *pgxpool.Pool
	cfg     *meta.Config
	actorID string
}

// NewPgMetaScrubber binds the meta pool + the MetaWrite Config + the actor
// recorded in meta_write_audit (the meta-worker service performing the scrub).
func NewPgMetaScrubber(metaPool *pgxpool.Pool, cfg *meta.Config, actorID string) *PgMetaScrubber {
	return &PgMetaScrubber{meta: metaPool, cfg: cfg, actorID: actorID}
}

var _ uew.MetaScrubber = (*PgMetaScrubber)(nil)

// ScrubUserMetaRefs removes every meta-tier reference to the user.
//
// TWO INDEPENDENT OBLIGATIONS, and they must stay independent. The first
// version ran the ownership reassignment as the last statement of the binding
// deleter, *after* its `if len(found) == 0 { return nil }` — so a user who
// OWNED a reality but drove no actor in it returned early and their
// `owner_user_id` survived, while the erasure reported success.
//
// That is the very case the same commit fixed in `RealitiesForUser`: the
// lookup learned about owned realities and the writer, one function later, did
// not. It was not hypothetical — at the time it was found, BOTH user-owned
// realities in the live meta database belonged to a user with zero bindings, so
// erasing that user was a no-op on `reality_registry`.
//
// Each obligation now owns its own enumeration and its own early return.
func (s *PgMetaScrubber) ScrubUserMetaRefs(ctx context.Context, userID uuid.UUID) error {
	if err := s.eraseActorBindings(ctx, userID); err != nil {
		return err
	}
	return s.reassignOwnedRealities(ctx, userID)
}

// eraseActorBindings deletes every actor_control_binding row for the user, via
// MetaWriteBatch. See the type doc for why erasure here is a DELETE.
func (s *PgMetaScrubber) eraseActorBindings(ctx context.Context, userID uuid.UUID) error {
	// No `revoked_at IS NULL` filter, for the reason RealitiesForUser gives: a
	// revoked binding is still a reference to this user, and erasure owes
	// removal of every one of them.
	rows, err := s.meta.Query(ctx,
		`SELECT reality_id, actor_id FROM actor_control_binding WHERE user_ref_id = $1`, userID)
	if err != nil {
		return fmt.Errorf("pglive: enumerate actor bindings for user %s: %w", userID, err)
	}
	type binding struct{ reality, actor uuid.UUID }
	var found []binding
	for rows.Next() {
		var b binding
		if err := rows.Scan(&b.reality, &b.actor); err != nil {
			rows.Close()
			return fmt.Errorf("pglive: scan actor_control_binding pk: %w", err)
		}
		found = append(found, b)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return fmt.Errorf("pglive: iterate actor bindings: %w", err)
	}
	if len(found) == 0 {
		return nil // already erased / never bound — idempotent
	}
	intents := make([]meta.MetaWriteIntent, 0, len(found))
	for _, b := range found {
		intents = append(intents, meta.MetaWriteIntent{
			Table:     "actor_control_binding",
			Operation: meta.OpDelete,
			PK:        map[string]any{"reality_id": b.reality, "actor_id": b.actor},
			Actor:     meta.Actor{Type: meta.ActorService, ID: s.actorID},
			Reason:    "gdpr erasure: remove the user->actor control binding (P2/071)",
		})
	}
	if _, err := meta.MetaWriteBatch(ctx, s.cfg, intents); err != nil {
		return fmt.Errorf("pglive: erase actor_control_binding for user %s: %w", userID, err)
	}
	return nil
}

// reassignOwnedRealities discharges the `@erasure_method:
// reassign_to_system_on_user_erasure` that migration 036 declares.
//
// **It is a REASSIGN, not a delete.** A reality may hold other users' play, so
// erasing one person must not destroy the world; what erasure owes is removal
// of the REFERENCE. Setting (owner_kind='system', owner_user_id=NULL) severs the
// person from the reality and leaves it running — and the table's CHECK
// constraints make that the only well-formed way to do it: clearing the id
// alone is refused by `reality_registry_owner_user_set`, so a partial erasure
// cannot be written even by mistake.
//
// This was declared in the migration header and implemented NOWHERE — the exact
// "promise nothing keeps" the sibling comment above warns about, written by
// someone who had just read it. It went unnoticed because the mechanism built
// for this class, `TestNoPerRealityTableCarriesAUserReference`, walks only
// `contracts/migrations/per_reality`; W6 put `owner_user_id` in
// `migrations/meta`, the one tree that gate never visits. Default-uncovered,
// NV-3. `TestMetaMigrationsDeclareAnImplementedErasure` now walks that tree.
func (s *PgMetaScrubber) reassignOwnedRealities(ctx context.Context, userID uuid.UUID) error {
	rows, err := s.meta.Query(ctx,
		`SELECT reality_id FROM reality_registry WHERE owner_user_id = $1`, userID)
	if err != nil {
		return fmt.Errorf("pglive: enumerate realities owned by %s: %w", userID, err)
	}
	var owned []uuid.UUID
	for rows.Next() {
		var rid uuid.UUID
		if err := rows.Scan(&rid); err != nil {
			rows.Close()
			return fmt.Errorf("pglive: scan owned reality_id: %w", err)
		}
		owned = append(owned, rid)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return fmt.Errorf("pglive: iterate owned realities: %w", err)
	}
	if len(owned) == 0 {
		return nil // never owned one / already reassigned — idempotent
	}

	intents := make([]meta.MetaWriteIntent, 0, len(owned))
	for _, rid := range owned {
		intents = append(intents, meta.MetaWriteIntent{
			Table:     "reality_registry",
			Operation: meta.OpUpdate,
			PK:        map[string]any{"reality_id": rid},
			// BOTH columns, together: the pair must stay consistent or the
			// CHECK rejects the write.
			NewValues: map[string]any{"owner_kind": "system", "owner_user_id": nil},
			Actor:     meta.Actor{Type: meta.ActorService, ID: s.actorID},
			Reason:    "gdpr erasure: reassign the reality to the platform (migration 036 @erasure_method)",
		})
	}
	if _, err := meta.MetaWriteBatch(ctx, s.cfg, intents); err != nil {
		return fmt.Errorf("pglive: reassign realities owned by %s: %w", userID, err)
	}
	return nil
}

// LogAuditSink is a V1 structured-log AuditSink for the per-reality scrub
// (P2/071). Durable audit-table persistence is deferred — the per-reality scrub
// is a per-reality projection write (not a meta-table MetaWrite), so its audit
// home (a per-reality audit table vs service_to_service_audit) is a follow-up
// decision; for V1 we emit a structured log line per scrub (Q-L1A-3 visibility).
type LogAuditSink struct{}

var _ uew.AuditSink = LogAuditSink{}

// WriteAudit logs the scrub. Never errors (a log write must not NACK erasure).
func (LogAuditSink) WriteAudit(_ context.Context, e uew.AuditEntry) error {
	slog.Info("[user-erased] per-reality scrub",
		"event_id", e.EventID, "user_id", e.UserID, "reality_id", e.RealityID,
		"outcome", e.Outcome, "erased_at", e.ErasedAt, "scrubbed_at", e.ScrubbedAt)
	return nil
}

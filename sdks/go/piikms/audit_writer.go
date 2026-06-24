package piikms

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/pii"
)

// PgReadAuditWriter implements contracts/pii.AuditWriter by inserting directly
// into meta_read_audit (migration 014 + 029). The cycle-4 pii.SDK calls this on
// every GetPII / ErasePII — for ErasePII it is a FORENSIC INVARIANT (the SDK
// returns a hard error if the audit write fails, so the erasure is provably
// recorded or provably not done).
//
// Direct INSERT (not via MetaWrite): meta_read_audit is itself an audit table;
// routing it through MetaWrite would emit a meta_write_audit row ABOUT an audit
// row. The table is INSERT-only (migration 014 REVOKEs UPDATE/DELETE).
//
// query_type MUST be one of the migration-029 enum ids and actor_type one of
// the migration-014 actor_type ids — the SDK's SensitiveReadEntry.Validate
// checks shape, but the DB CHECK is the real gate, so callers must wire
// ActorType to an enum-valid value (e.g. "admin"). WriteSensitiveRead surfaces
// a CHECK violation as a plain error.
type PgReadAuditWriter struct {
	db *pgxpool.Pool
}

// NewPgReadAuditWriter binds the meta pool (caller-owned).
func NewPgReadAuditWriter(db *pgxpool.Pool) *PgReadAuditWriter {
	return &PgReadAuditWriter{db: db}
}

var _ pii.AuditWriter = (*PgReadAuditWriter)(nil)

// WriteSensitiveRead inserts one meta_read_audit row. created_at is a GENERATED
// column and is never inserted.
func (w *PgReadAuditWriter) WriteSensitiveRead(ctx context.Context, entry pii.SensitiveReadEntry) error {
	// Defense-in-depth: re-validate shape before the DB round-trip (the SDK
	// validates too, but this writer may gain other callers).
	if err := entry.Validate(); err != nil {
		return fmt.Errorf("piikms: invalid meta_read_audit entry: %w", err)
	}
	// Parameters → JSONB. Marshal to text and cast (passing []byte would bind to
	// bytea, not jsonb). nil map marshals to "null"; default to "{}" to match
	// the column DEFAULT and avoid a JSONB null.
	params := entry.Parameters
	if params == nil {
		params = map[string]string{}
	}
	paramsJSON, err := json.Marshal(params)
	if err != nil {
		return fmt.Errorf("piikms: marshal meta_read_audit parameters: %w", err)
	}
	_, err = w.db.Exec(ctx,
		`INSERT INTO meta_read_audit
		   (audit_id, query_type, parameters, actor_id, actor_type, result_count, created_at_nanos)
		 VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)`,
		entry.AuditID,
		string(entry.QueryType),
		string(paramsJSON),
		entry.ActorID,
		entry.ActorType,
		entry.ResultCount,
		entry.CreatedAtNanos,
	)
	if err != nil {
		return fmt.Errorf("piikms: insert meta_read_audit (query_type=%s, actor_type=%s): %w",
			entry.QueryType, entry.ActorType, err)
	}
	return nil
}

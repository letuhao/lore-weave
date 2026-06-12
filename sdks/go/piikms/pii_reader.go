package piikms

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
)

// PgPIIReader implements contracts/meta.PIIReader against the meta DB
// (pii_registry + pii_kek). It is the production driver the cycle-3
// interface-only meta library + the cycle-4 pii.SDK depend on — a
// driver-clean library ships with no concrete reader until someone writes
// one. READ-ONLY: every method is a single SELECT; no row is ever written
// (so it is safe to call on a GDPR dry-run preview path).
//
// Timestamp note: meta.PIIRow/KEKRow carry unix-nanos ints, but the DB
// columns are TIMESTAMPTZ — we scan into time.Time and convert. NULL
// erased_at/destroyed_at map to a nil *int64 ("not erased / active").
type PgPIIReader struct {
	db *pgxpool.Pool
}

// NewPgPIIReader binds the meta pool. The pool is owned by the caller.
func NewPgPIIReader(db *pgxpool.Pool) *PgPIIReader { return &PgPIIReader{db: db} }

var _ meta.PIIReader = (*PgPIIReader)(nil)

// ReadPIIRow returns the encrypted envelope + KEK pointer for a user.
// meta.ErrPIINotFound when no pii_registry row exists.
func (r *PgPIIReader) ReadPIIRow(ctx context.Context, userRefID uuid.UUID) (meta.PIIRow, error) {
	var (
		row         meta.PIIRow
		lastRotated time.Time
		erasedAt    *time.Time
	)
	err := r.db.QueryRow(ctx,
		`SELECT user_ref_id, kek_id, encrypted_blob, blob_schema_ver, last_rotated_at, erased_at
		   FROM pii_registry
		  WHERE user_ref_id = $1`,
		userRefID,
	).Scan(&row.UserRefID, &row.KEKID, &row.EncryptedBlob, &row.BlobSchemaVer, &lastRotated, &erasedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return meta.PIIRow{}, meta.ErrPIINotFound
		}
		return meta.PIIRow{}, fmt.Errorf("piikms: read pii_registry for user %s: %w", userRefID, err)
	}
	row.LastRotatedAt = lastRotated.UnixNano()
	row.ErasedAt = nanosPtr(erasedAt)
	return row, nil
}

// ReadKEKRow returns the KEK envelope + destroyed_at marker.
// meta.ErrPIINotFound when no pii_kek row exists.
func (r *PgPIIReader) ReadKEKRow(ctx context.Context, kekID uuid.UUID) (meta.KEKRow, error) {
	var (
		row         meta.KEKRow
		destroyedAt *time.Time
	)
	err := r.db.QueryRow(ctx,
		`SELECT kek_id, user_ref_id, key_material, kms_key_ref, destroyed_at
		   FROM pii_kek
		  WHERE kek_id = $1`,
		kekID,
	).Scan(&row.KEKID, &row.UserRefID, &row.KeyMaterial, &row.KMSKeyRef, &destroyedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return meta.KEKRow{}, meta.ErrPIINotFound
		}
		return meta.KEKRow{}, fmt.Errorf("piikms: read pii_kek %s: %w", kekID, err)
	}
	row.DestroyedAt = nanosPtr(destroyedAt)
	return row, nil
}

// nanosPtr converts a nullable TIMESTAMPTZ (scanned as *time.Time) to the
// *int64 unix-nanos the meta row structs expect. nil stays nil.
func nanosPtr(t *time.Time) *int64 {
	if t == nil {
		return nil
	}
	n := t.UnixNano()
	return &n
}

// Package metapg is the production pgx driver for the driver-clean
// contracts/meta MetaWrite library (073 prerequisite). contracts/meta defines
// meta.DB/meta.Tx as tiny interfaces so the library has no driver dependency;
// this package supplies the real *pgxpool.Pool-backed implementation so
// MetaWrite() can run in production (admin-cli, and any future caller).
package metapg

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
)

// DB adapts a *pgxpool.Pool to meta.DB.
type DB struct {
	pool *pgxpool.Pool
}

// New wraps a pgx pool as a meta.DB. Reusable by every MetaWrite caller.
func New(pool *pgxpool.Pool) *DB { return &DB{pool: pool} }

var _ meta.DB = (*DB)(nil)

// BeginTx starts a pgx transaction and returns it as a meta.Tx plus
// commit/rollback finalizers. MetaWrite's pattern is `defer rollback()` then
// `commit()` on success; pgx makes a Rollback after Commit a no-op
// (pgx.ErrTxClosed), which the caller swallows — so the deferred rollback is
// safe after a successful commit.
func (d *DB) BeginTx(ctx context.Context) (meta.Tx, func() error, func() error, error) {
	tx, err := d.pool.Begin(ctx)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("metapg: begin: %w", err)
	}
	commit := func() error { return tx.Commit(ctx) }
	rollback := func() error {
		err := tx.Rollback(ctx)
		if err == nil || err == pgx.ErrTxClosed {
			return nil // already committed/rolled back — not an error
		}
		return err
	}
	return &pgTx{tx: tx}, commit, rollback, nil
}

// pgTx adapts a pgx.Tx to meta.Tx.
type pgTx struct {
	tx pgx.Tx
}

// Exec runs a parameterized statement and returns rowsAffected.
func (t *pgTx) Exec(ctx context.Context, query string, args ...any) (int64, error) {
	tag, err := t.tx.Exec(ctx, query, args...)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

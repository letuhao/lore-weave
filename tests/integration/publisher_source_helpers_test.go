// publisher_source_helpers_test.go — shared in-memory poll_loop.Source /
// poll_loop.Batch fakes for the publisher integration tests.
//
// The publisher's poll_loop was refactored (DEFERRED 054) from separate
// Fetcher+StateWriter interfaces to a transactional Source→Batch pair so the
// SELECT … FOR UPDATE SKIP LOCKED and the row UPDATEs share one tx. These
// fakes let the in-memory tests (publisher_lag, xreality_propagation) drive
// the loop without a real Postgres.
//
//go:build integration
// +build integration

package integration

import (
	"context"
	"time"

	"github.com/loreweave/foundation/services/publisher/pkg/poll_loop"
	"github.com/loreweave/foundation/services/publisher/pkg/types"
)

// memBatch records Mark calls + commit/rollback for one reality drain.
type memBatch struct {
	rows       []types.OutboxRow
	pub        int
	retr       int
	dl         int
	committed  bool
	rolledBack bool
}

func (b *memBatch) Rows() []types.OutboxRow                     { return b.rows }
func (b *memBatch) MarkPublished(context.Context, string) error { b.pub++; return nil }
func (b *memBatch) MarkRetry(context.Context, string, int, string, time.Time) error {
	b.retr++
	return nil
}
func (b *memBatch) MarkDeadLetter(context.Context, string, int, string) error { b.dl++; return nil }
func (b *memBatch) Commit(context.Context) error                              { b.committed = true; return nil }
func (b *memBatch) Rollback(context.Context) error                            { b.rolledBack = true; return nil }

// memSource hands its rows out exactly once (one batch), then empties.
type memSource struct {
	rows  []types.OutboxRow
	done  bool
	batch *memBatch
}

func (s *memSource) Begin(_ context.Context, _ string, _ int) (poll_loop.Batch, error) {
	var rows []types.OutboxRow
	if !s.done {
		rows = s.rows
		s.done = true
	}
	s.batch = &memBatch{rows: rows}
	return s.batch, nil
}

//go:build integration

package integration

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/loreweave/foundation/services/admin-cli/commands"
)

type fakeMetaWriter struct {
	got commands.OverrideRecord
	err error
}

func (w *fakeMetaWriter) WriteOverride(_ context.Context, rec commands.OverrideRecord) error {
	w.got = rec
	return w.err
}

// TestCapacityOverride_Grants24h_AutoExpires — L1.L §10 acceptance.
func TestCapacityOverride_Grants24h_AutoExpires(t *testing.T) {
	w := &fakeMetaWriter{}
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	req := commands.CapacityOverrideRequest{
		ShardHost: "pg-shard-3.prod",
		Reason:    "Black Friday launch traffic spike",
		Hours:     24,
		Actor:     "user-uuid-sre1",
	}
	rec, err := commands.Apply(context.Background(), req, w, func() time.Time { return now })
	if err != nil {
		t.Fatal(err)
	}
	expectedExpiry := now.Add(24 * time.Hour).UnixNano()
	if rec.ExpiresAtNanos != expectedExpiry {
		t.Errorf("ExpiresAtNanos = %d, want %d", rec.ExpiresAtNanos, expectedExpiry)
	}
}

func TestCapacityOverride_AuditRowWritten(t *testing.T) {
	w := &fakeMetaWriter{}
	req := commands.CapacityOverrideRequest{
		ShardHost: "pg-shard-3.prod", Reason: "x", Hours: 12, Actor: "u",
	}
	_, err := commands.Apply(context.Background(), req, w, time.Now)
	if err != nil {
		t.Fatal(err)
	}
	if w.got.Reason != "x" || w.got.Actor != "u" {
		t.Errorf("audit row missing context: %+v", w.got)
	}
}

func TestCapacityOverride_RejectsBeyond24h(t *testing.T) {
	req := commands.CapacityOverrideRequest{
		ShardHost: "pg-shard-3.prod", Reason: "x", Hours: 48, Actor: "u",
	}
	_, err := commands.Apply(context.Background(), req, &fakeMetaWriter{}, time.Now)
	if !errors.Is(err, commands.ErrInvalidOverride) {
		t.Errorf("48h request should be rejected; err = %v", err)
	}
}

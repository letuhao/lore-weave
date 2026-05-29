package commands

import (
	"context"
	"errors"
	"testing"
	"time"
)

type recordingWriter struct {
	got OverrideRecord
	err error
}

func (w *recordingWriter) WriteOverride(_ context.Context, rec OverrideRecord) error {
	w.got = rec
	return w.err
}

func fixedClock(t time.Time) ClockFn { return func() time.Time { return t } }

func TestCapacityOverride_Apply_HappyPath(t *testing.T) {
	w := &recordingWriter{}
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	req := CapacityOverrideRequest{
		ShardHost: "pg-shard-1.prod",
		Reason:    "burst traffic from launch event",
		Hours:     12,
		Actor:     "user-uuid-1",
	}
	rec, err := Apply(context.Background(), req, w, fixedClock(now))
	if err != nil {
		t.Fatalf("Apply err = %v", err)
	}
	if rec.ExpiresAtNanos != now.Add(12*time.Hour).UnixNano() {
		t.Errorf("expires_at mismatch: %d", rec.ExpiresAtNanos)
	}
	if w.got.ShardHost != "pg-shard-1.prod" {
		t.Errorf("WriteOverride saw wrong shard: %+v", w.got)
	}
}

func TestCapacityOverride_Apply_Rejects25h(t *testing.T) {
	// S5-D5: hours capped at 24
	req := CapacityOverrideRequest{
		ShardHost: "pg-shard-1.prod", Reason: "x", Hours: 25, Actor: "u",
	}
	_, err := Apply(context.Background(), req, &recordingWriter{}, time.Now)
	if !errors.Is(err, ErrInvalidOverride) {
		t.Errorf("err = %v, want ErrInvalidOverride", err)
	}
}

func TestCapacityOverride_Apply_RejectsZeroHours(t *testing.T) {
	req := CapacityOverrideRequest{
		ShardHost: "pg-shard-1.prod", Reason: "x", Hours: 0, Actor: "u",
	}
	_, err := Apply(context.Background(), req, &recordingWriter{}, time.Now)
	if !errors.Is(err, ErrInvalidOverride) {
		t.Errorf("err = %v, want ErrInvalidOverride", err)
	}
}

func TestCapacityOverride_Apply_RequiresReason(t *testing.T) {
	req := CapacityOverrideRequest{
		ShardHost: "pg-shard-1.prod", Reason: "", Hours: 12, Actor: "u",
	}
	_, err := Apply(context.Background(), req, &recordingWriter{}, time.Now)
	if !errors.Is(err, ErrInvalidOverride) {
		t.Errorf("err = %v, want ErrInvalidOverride", err)
	}
}

func TestCapacityOverride_Apply_RequiresActor(t *testing.T) {
	req := CapacityOverrideRequest{
		ShardHost: "pg-shard-1.prod", Reason: "x", Hours: 12, Actor: "",
	}
	_, err := Apply(context.Background(), req, &recordingWriter{}, time.Now)
	if !errors.Is(err, ErrInvalidOverride) {
		t.Errorf("err = %v, want ErrInvalidOverride", err)
	}
}

func TestCapacityOverride_Apply_WriterErrorPropagates(t *testing.T) {
	w := &recordingWriter{err: errors.New("rpc timeout")}
	req := CapacityOverrideRequest{
		ShardHost: "pg-shard-1.prod", Reason: "x", Hours: 12, Actor: "u",
	}
	_, err := Apply(context.Background(), req, w, time.Now)
	if err == nil || !contains(err.Error(), "rpc timeout") {
		t.Errorf("err should wrap writer error: %v", err)
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}

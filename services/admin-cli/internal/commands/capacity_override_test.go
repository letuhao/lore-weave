package commands

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

type fakeScalingWriter struct {
	got ScalingOverride
	n   int
	err error
}

func (f *fakeScalingWriter) WriteOverride(_ context.Context, ov ScalingOverride) error {
	f.n++
	f.got = ov
	return f.err
}

func fixedClock(t time.Time) func() time.Time { return func() time.Time { return t } }

func validOverrideReq() CapacityOverrideRequest {
	return CapacityOverrideRequest{
		ShardHost: "pg-shard-3.internal",
		Reason:    "drain for incident INC-42",
		Hours:     6,
		Actor:     uuid.NewString(),
	}
}

func TestRunCapacityOverride_WritesAndBoundsExpiry(t *testing.T) {
	now := time.Date(2026, 6, 3, 10, 0, 0, 0, time.UTC)
	w := &fakeScalingWriter{}
	req := validOverrideReq()
	out, err := RunCapacityOverride(context.Background(), req, w, fixedClock(now))
	if err != nil {
		t.Fatalf("RunCapacityOverride: %v", err)
	}
	if w.n != 1 {
		t.Fatalf("expected 1 write, got %d", w.n)
	}
	if !w.got.ExpiresAt.Equal(now.Add(6 * time.Hour)) {
		t.Errorf("expiry = %s, want now+6h", w.got.ExpiresAt)
	}
	if !w.got.CreatedAt.Equal(now) {
		t.Errorf("created = %s, want %s", w.got.CreatedAt, now)
	}
	if !strings.Contains(out, "pg-shard-3.internal") || !strings.Contains(out, "6h") {
		t.Errorf("confirmation missing shard/hours:\n%s", out)
	}
}

func TestRunCapacityOverride_DryRunDoesNotWrite(t *testing.T) {
	w := &fakeScalingWriter{}
	req := validOverrideReq()
	req.DryRun = true
	out, err := RunCapacityOverride(context.Background(), req, w, fixedClock(time.Now()))
	if err != nil {
		t.Fatalf("dry-run: %v", err)
	}
	if w.n != 0 {
		t.Fatalf("dry-run must not write, got %d writes", w.n)
	}
	if !strings.Contains(out, "DRY-RUN") {
		t.Errorf("dry-run output missing marker:\n%s", out)
	}
}

func TestRunCapacityOverride_RejectsOver24h(t *testing.T) {
	req := validOverrideReq()
	req.Hours = 25
	_, err := RunCapacityOverride(context.Background(), req, &fakeScalingWriter{}, nil)
	if !errors.Is(err, ErrInvalidOverride) {
		t.Fatalf("hours=25 must reject, got %v", err)
	}
}

func TestRunCapacityOverride_ValidateFields(t *testing.T) {
	cases := map[string]func(*CapacityOverrideRequest){
		"empty shard":  func(r *CapacityOverrideRequest) { r.ShardHost = "" },
		"empty reason": func(r *CapacityOverrideRequest) { r.Reason = "" },
		"zero hours":   func(r *CapacityOverrideRequest) { r.Hours = 0 },
		"empty actor":  func(r *CapacityOverrideRequest) { r.Actor = "" },
	}
	for name, mut := range cases {
		t.Run(name, func(t *testing.T) {
			req := validOverrideReq()
			mut(&req)
			if _, err := RunCapacityOverride(context.Background(), req, &fakeScalingWriter{}, nil); !errors.Is(err, ErrInvalidOverride) {
				t.Fatalf("%s must reject with ErrInvalidOverride, got %v", name, err)
			}
		})
	}
}

func TestRunCapacityOverride_WriterErrorPropagates(t *testing.T) {
	w := &fakeScalingWriter{err: errors.New("db down")}
	_, err := RunCapacityOverride(context.Background(), validOverrideReq(), w, nil)
	if err == nil || !strings.Contains(err.Error(), "db down") {
		t.Fatalf("writer error must propagate, got %v", err)
	}
}

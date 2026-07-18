package scheduler

import (
	"testing"
	"time"
)

func TestComputeNextFireAt(t *testing.T) {
	// 2026-07-15 10:00 UTC.
	now := time.Date(2026, 7, 15, 10, 0, 0, 0, time.UTC)

	// UTC 21:00 today is still ahead of 10:00 → today at 21:00 UTC.
	got, err := ComputeNextFireAt("21:00", "UTC", now)
	if err != nil {
		t.Fatal(err)
	}
	if want := time.Date(2026, 7, 15, 21, 0, 0, 0, time.UTC); !got.Equal(want) {
		t.Fatalf("UTC 21:00 → %v, want %v", got, want)
	}

	// UTC 09:00 already passed today → tomorrow 09:00 UTC.
	got, _ = ComputeNextFireAt("09:00", "UTC", now)
	if want := time.Date(2026, 7, 16, 9, 0, 0, 0, time.UTC); !got.Equal(want) {
		t.Fatalf("UTC 09:00 → %v, want %v", got, want)
	}

	// tz-aware: 21:00 in Asia/Ho_Chi_Minh (UTC+7) = 14:00 UTC (same day, ahead of 10:00 UTC).
	got, err = ComputeNextFireAt("21:00", "Asia/Ho_Chi_Minh", now)
	if err != nil {
		t.Fatal(err)
	}
	if want := time.Date(2026, 7, 15, 14, 0, 0, 0, time.UTC); !got.Equal(want) {
		t.Fatalf("VN 21:00 → %v UTC, want %v", got, want)
	}

	// unknown tz → UTC fallback (no error).
	got, err = ComputeNextFireAt("21:00", "Mars/Olympus", now)
	if err != nil || !got.Equal(time.Date(2026, 7, 15, 21, 0, 0, 0, time.UTC)) {
		t.Fatalf("bad-tz fallback → %v err=%v", got, err)
	}

	// bad HH:MM → error.
	if _, err := ComputeNextFireAt("25:99", "UTC", now); err == nil {
		t.Fatal("expected an error for out-of-range HH:MM")
	}

	// the result is always strictly AFTER now.
	if !got.After(now) {
		t.Fatal("next_fire_at must be strictly after now")
	}
}

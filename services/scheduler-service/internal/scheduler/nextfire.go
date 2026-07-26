package scheduler

import (
	"fmt"
	"time"
)

// ComputeNextFireAt (WS-3.2) — the next UTC instant at which it is `fireLocalTime` (HH:MM) in the
// user's IANA `tz`, strictly AFTER `now`. This is how a per-user LOCAL end-of-day becomes a concrete
// armed instant: 21:00 in Asia/Ho_Chi_Minh and 21:00 in America/New_York fire at different UTC times,
// and DST transitions are handled by resolving the wall-clock time in the zone. An unknown tz falls
// back to UTC (the day bucket degrades safely, matching the distiller's UTC default).
func ComputeNextFireAt(fireLocalTime, tz string, now time.Time) (time.Time, error) {
	hh, mm, err := parseHHMM(fireLocalTime)
	if err != nil {
		return time.Time{}, err
	}
	loc, err := time.LoadLocation(tz)
	if err != nil || tz == "" {
		loc = time.UTC
	}
	nowLocal := now.In(loc)
	// Today's occurrence of the wall-clock time in the zone.
	candidate := time.Date(nowLocal.Year(), nowLocal.Month(), nowLocal.Day(), hh, mm, 0, 0, loc)
	if !candidate.After(now) {
		candidate = candidate.AddDate(0, 0, 1) // already passed today → tomorrow
	}
	return candidate.UTC(), nil
}

func parseHHMM(s string) (int, int, error) {
	var hh, mm int
	if _, err := fmt.Sscanf(s, "%d:%d", &hh, &mm); err != nil {
		return 0, 0, fmt.Errorf("invalid fire_local_time %q (want HH:MM)", s)
	}
	if hh < 0 || hh > 23 || mm < 0 || mm > 59 {
		return 0, 0, fmt.Errorf("fire_local_time %q out of range", s)
	}
	return hh, mm, nil
}

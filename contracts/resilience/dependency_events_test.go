package resilience

import (
	"errors"
	"testing"
	"time"
)

func TestAllEventTypes_TenEntries(t *testing.T) {
	// SR06 §12AI.9 fixes the event_type set at 10 values. Lock with a count
	// test so a future caller can't append without updating SQL CHECK + tests.
	if got := len(AllEventTypes()); got != 10 {
		t.Errorf("AllEventTypes() = %d, want exactly 10 per SR06 §12AI.9", got)
	}
}

func TestNewDependencyEvent_RequiredFields(t *testing.T) {
	now := time.Now()
	cases := []struct {
		name string
		args func() (string, string, string, EventType, string, time.Time)
	}{
		{"empty event_id", func() (string, string, string, EventType, string, time.Time) {
			return "", "d", "s", EventTimeoutBurst, "rate=10/s", now
		}},
		{"empty dep", func() (string, string, string, EventType, string, time.Time) {
			return "id", "", "s", EventTimeoutBurst, "rate=10/s", now
		}},
		{"empty service", func() (string, string, string, EventType, string, time.Time) {
			return "id", "d", "", EventTimeoutBurst, "rate=10/s", now
		}},
		{"unknown event_type", func() (string, string, string, EventType, string, time.Time) {
			return "id", "d", "s", EventType("weather_outage"), "r", now
		}},
		{"zero occurred_at", func() (string, string, string, EventType, string, time.Time) {
			return "id", "d", "s", EventTimeoutBurst, "r", time.Time{}
		}},
		{"reason required for circuit_open", func() (string, string, string, EventType, string, time.Time) {
			return "id", "d", "s", EventCircuitOpen, "", now
		}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, err := NewDependencyEvent(c.args())
			if !errors.Is(err, ErrInvalidDependencyEvent) {
				t.Errorf("err = %v, want ErrInvalidDependencyEvent", err)
			}
		})
	}
}

func TestNewDependencyEvent_HappyPath(t *testing.T) {
	now := time.Now()
	ev, err := NewDependencyEvent("evt-1", "llm-anthropic", "roleplay-service", EventCircuitOpen, "error_rate=0.42 over 100req", now)
	if err != nil {
		t.Fatal(err)
	}
	if ev.EventID != "evt-1" || ev.DepName != "llm-anthropic" {
		t.Errorf("fields lost: %+v", ev)
	}
	if ev.EventType != EventCircuitOpen {
		t.Errorf("EventType = %v", ev.EventType)
	}
}

func TestNewDependencyEvent_ReasonOptionalForBurstEvents(t *testing.T) {
	// timeout_burst / bulkhead_full_burst / retry_exhausted may carry empty
	// reason — metrics_snapshot is enough for postmortem.
	for _, t2 := range []EventType{EventTimeoutBurst, EventBulkheadFullBurst, EventRetryExhausted, EventFailoverUsed} {
		_, err := NewDependencyEvent("id", "d", "s", t2, "", time.Now())
		if err != nil {
			t.Errorf("type=%q should not require reason; got err=%v", t2, err)
		}
	}
}

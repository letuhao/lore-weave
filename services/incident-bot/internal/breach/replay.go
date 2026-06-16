package breach

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/contracts/incidents"
	gbf "github.com/loreweave/foundation/services/incident-bot/internal/gdpr_breach_flow"
)

// replayEvent is a minimally-parsed stream entry for monitor reconstruction.
type replayEvent struct {
	eventType  string
	incidentID string
	opened     *incidents.GDPRBreachOpenedV1 // set only for opened events
	missed     bool                          // a deadline event with state=missed (terminal)
}

// reconstructOpen rebuilds the set of STILL-OPEN breaches from the ORDERED stream
// events. The stream is an ordered log, so reconstruction is LAST-EVENT-WINS per
// incident_id: an `opened` (re)opens (and clears any prior terminal — handling the
// rare same-id re-declaration after a missed), a `missed` deadline marks terminal (the
// Monitor prunes a missed breach, so it must not be re-tracked). A breach is returned
// iff its latest relevant event left it open. Returned in first-opened order. Pure
// function — unit-tested without Redis.
//
// At-least-once caveat (107): replay cannot know whether an "approaching" reminder
// already fired before the restart, so a duplicate approaching reminder is possible.
// That is acceptable — a duplicate deadline reminder is safe; a missed one is not.
func reconstructOpen(events []replayEvent) []*gbf.BreachRecord {
	opened := map[string]incidents.GDPRBreachOpenedV1{}
	var order []string
	missed := map[string]bool{}
	for _, ev := range events {
		switch {
		case ev.opened != nil:
			if _, seen := opened[ev.incidentID]; !seen {
				order = append(order, ev.incidentID)
			}
			opened[ev.incidentID] = *ev.opened
			delete(missed, ev.incidentID) // a (re)open clears a prior terminal (ordered log, last-event-wins)
		case ev.eventType == incidents.TypeGDPRBreachDeadlineV1 && ev.missed:
			missed[ev.incidentID] = true
		}
	}
	var out []*gbf.BreachRecord
	for _, id := range order {
		if missed[id] {
			continue
		}
		o := opened[id]
		out = append(out, &gbf.BreachRecord{
			IncidentID:     o.IncidentID,
			DetectedAt:     o.DetectedAt,
			Deadline:       o.Deadline,
			DataCategories: o.DataCategories,
			AffectedCount:  o.AffectedCount,
		})
	}
	return out
}

// ReplayOpenBreaches XRANGEs the breach stream and reconstructs the still-open
// breaches to re-Track after a restart (D-BREACH-DURABLE-STORE). The Redis stream is
// the durable log — incident-bot holds NO DB (Q-L7-1 stateless). An empty stream
// yields no records. Unparseable/foreign entries are skipped (defensive), not fatal.
func ReplayOpenBreaches(ctx context.Context, rdb redis.Cmdable, stream string) ([]*gbf.BreachRecord, error) {
	if rdb == nil {
		return nil, errors.New("breach: nil redis client")
	}
	if stream == "" {
		stream = DefaultBreachStream
	}
	msgs, err := rdb.XRange(ctx, stream, "-", "+").Result()
	if err != nil {
		return nil, fmt.Errorf("breach: XRANGE %s: %w", stream, err)
	}
	events := make([]replayEvent, 0, len(msgs))
	for _, m := range msgs {
		if ev, ok := parseReplayMessage(m.Values); ok {
			events = append(events, ev)
		}
	}
	return reconstructOpen(events), nil
}

// parseReplayMessage extracts a replayEvent from a stream entry's fields. Returns
// ok=false for entries that cannot be interpreted (skipped, not fatal).
//
// XRANGE returns every stream field value as a string (Redis stream fields are bytes
// on the wire), so the `.(string)` comma-ok assertions below are total — a future
// producer cannot make a field a non-string scalar. A foreign producer or a missing
// payload simply yields ok=false (opened/deadline) or a fields-only event (default).
func parseReplayMessage(values map[string]any) (replayEvent, bool) {
	et, _ := values["event_type"].(string)
	if et == "" {
		return replayEvent{}, false
	}
	payload, _ := values["payload"].(string)
	switch et {
	case incidents.TypeGDPRBreachOpenedV1:
		var o incidents.GDPRBreachOpenedV1
		if payload == "" || json.Unmarshal([]byte(payload), &o) != nil || o.IncidentID == "" {
			return replayEvent{}, false
		}
		return replayEvent{eventType: et, incidentID: o.IncidentID, opened: &o}, true
	case incidents.TypeGDPRBreachDeadlineV1:
		var d incidents.GDPRBreachDeadlineV1
		if payload == "" || json.Unmarshal([]byte(payload), &d) != nil || d.IncidentID == "" {
			return replayEvent{}, false
		}
		return replayEvent{eventType: et, incidentID: d.IncidentID, missed: d.State == incidents.BreachDeadlineMissed}, true
	default:
		// dpo_notice_required or unknown — irrelevant to monitor reconstruction, but
		// keep the entry (with its incident_id if present) so the parse is total.
		id, _ := values["incident_id"].(string)
		return replayEvent{eventType: et, incidentID: id}, true
	}
}

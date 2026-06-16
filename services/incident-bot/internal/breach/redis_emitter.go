package breach

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/contracts/incidents"
)

// DefaultBreachStream is the Redis stream the breach lifecycle events are XADDed to.
// The delivery consumer (106) reads it AND the boot-replay (107) rebuilds the deadline
// monitor from it.
const DefaultBreachStream = "lw.incidents.breach"

// DefaultTrimHorizon bounds the stream by a TIME-based MINID trim (not a count-based
// MAXLEN). It MUST stay well above the Art.33 72h deadline (gdpr_breach_flow.
// NotificationDeadline) so a still-OPEN breach's `opened` event — the anchor the
// boot-replay depends on — can NEVER be trimmed (an open breach is <72h old, far
// inside a 7d window). A count-based MAXLEN would be unsafe here: a burst of recent
// events could evict a still-open breach's anchor. 7d ⇒ the boot-replay also scans
// only a bounded window, not the whole-stream history.
const DefaultTrimHorizon = 7 * 24 * time.Hour

// RedisEmitter is the EventEmitter backed by a Redis stream — the durable transport
// the 072 StructuredEmitter (stdout) stood in for (D-BREACH-BROKER-EMITTER). Each
// event is validated (fail-closed, like StructuredEmitter) then XADDed with an
// event_type discriminator + the full event JSON as `payload`, and the stream is
// trimmed to trimHorizon via an approximate MINID (anchor-safe — see DefaultTrimHorizon).
// Safe for concurrent use (go-redis clients are concurrency-safe + the only state is
// immutable config), so the Monitor goroutine and the HTTP handler can both emit.
type RedisEmitter struct {
	rdb         redis.Cmdable
	stream      string
	trimHorizon time.Duration
	now         func() time.Time
}

// NewRedisEmitter constructs a RedisEmitter. stream defaults to DefaultBreachStream;
// trimHorizon>0 trims the stream to events newer than now-trimHorizon on each XADD
// (0 ⇒ no trim); now defaults to time.Now (injected for deterministic tests).
func NewRedisEmitter(rdb redis.Cmdable, stream string, trimHorizon time.Duration, now func() time.Time) (*RedisEmitter, error) {
	if rdb == nil {
		return nil, errors.New("breach: nil redis client")
	}
	if stream == "" {
		stream = DefaultBreachStream
	}
	if now == nil {
		now = time.Now
	}
	if trimHorizon < 0 {
		trimHorizon = 0
	}
	return &RedisEmitter{rdb: rdb, stream: stream, trimHorizon: trimHorizon, now: now}, nil
}

var _ EventEmitter = (*RedisEmitter)(nil)

func (e *RedisEmitter) EmitBreachOpened(ctx context.Context, ev incidents.GDPRBreachOpenedV1) error {
	if err := ev.Validate(); err != nil {
		return err
	}
	return e.xadd(ctx, ev.Type, ev.IncidentID, ev)
}

func (e *RedisEmitter) EmitDPONoticeRequired(ctx context.Context, ev incidents.GDPRDPONoticeRequiredV1) error {
	if err := ev.Validate(); err != nil {
		return err
	}
	return e.xadd(ctx, ev.Type, ev.IncidentID, ev)
}

func (e *RedisEmitter) EmitBreachDeadline(ctx context.Context, ev incidents.GDPRBreachDeadlineV1) error {
	if err := ev.Validate(); err != nil {
		return err
	}
	return e.xadd(ctx, ev.Type, ev.IncidentID, ev)
}

func (e *RedisEmitter) xadd(ctx context.Context, eventType, incidentID string, ev any) error {
	minID := ""
	if e.trimHorizon > 0 {
		// Redis stream IDs are "<ms>-<seq>"; MINID "<cutoffMs>-0" trims everything
		// strictly older than the cutoff. Approx lets Redis trim at macro-node
		// boundaries (cheap). Anchor-safe: cutoff = now-7d ≪ any open breach (<72h).
		minID = fmt.Sprintf("%d-0", e.now().Add(-e.trimHorizon).UnixMilli())
	}
	args, err := breachXAddArgs(e.stream, eventType, incidentID, ev, minID)
	if err != nil {
		return err
	}
	if err := e.rdb.XAdd(ctx, args).Err(); err != nil {
		return fmt.Errorf("breach: XADD %s %s: %w", e.stream, eventType, err)
	}
	return nil
}

// breachXAddArgs builds the XADD args for a breach event. Extracted as a pure
// function so the field-shaping (event_type / incident_id / payload) is unit-testable
// without a Redis client. The full event is JSON-encoded into `payload`; event_type +
// incident_id are promoted to top-level fields for cheap consumer/replay routing.
// minID!="" sets an approximate MINID trim (time-based, anchor-safe — see the emitter).
func breachXAddArgs(stream, eventType, incidentID string, ev any, minID string) (*redis.XAddArgs, error) {
	payload, err := json.Marshal(ev)
	if err != nil {
		return nil, fmt.Errorf("breach: marshal %s: %w", eventType, err)
	}
	args := &redis.XAddArgs{
		Stream: stream,
		Values: map[string]any{
			"event_type":  eventType,
			"incident_id": incidentID,
			"payload":     string(payload),
		},
	}
	if minID != "" {
		args.MinID = minID
		args.Approx = true
	}
	return args, nil
}

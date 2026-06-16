// Package consume reads the lw.incidents.breach Redis stream via a consumer group
// and drives a per-message handler, acking only on a non-failure outcome (a failed
// delivery is left pending so Redis re-delivers it). It also reclaims this consumer's
// stale pending entries (XAUTOCLAIM) so a notice delivered to a consumer that crashed
// before ACK is not stuck forever — important for the "miss nothing" compliance rail.
package consume

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

// Message is one breach-stream entry.
type Message struct {
	ID     string
	Fields map[string]any
}

// EventType returns the entry's event_type field ("" if absent).
func (m Message) EventType() string {
	if v, ok := m.Fields["event_type"].(string); ok {
		return v
	}
	return ""
}

// Source is the stream abstraction (XReadGroup + XAUTOCLAIM + XACK). Prod: RedisSource;
// tests fake it.
type Source interface {
	EnsureGroup(ctx context.Context) error
	Read(ctx context.Context, batchSize int) ([]Message, error)
	// Reclaim returns this consumer's pending entries idle longer than minIdle
	// (crashed-before-ack messages) for re-processing.
	Reclaim(ctx context.Context, minIdle time.Duration, count int) ([]Message, error)
	Ack(ctx context.Context, m Message) error
}

// Config is the RedisSource constructor input.
type Config struct {
	RDB      redis.Cmdable
	Stream   string
	Group    string
	Consumer string
	Block    time.Duration
}

// RedisSource reads via a consumer group (mirror meta-worker/pkg/redisconsume).
type RedisSource struct {
	rdb      redis.Cmdable
	stream   string
	group    string
	consumer string
	block    time.Duration
}

// NewRedisSource constructs a RedisSource.
func NewRedisSource(c Config) (*RedisSource, error) {
	if c.RDB == nil {
		return nil, errors.New("consume: nil redis client")
	}
	if c.Stream == "" || c.Group == "" || c.Consumer == "" {
		return nil, errors.New("consume: stream/group/consumer required")
	}
	return &RedisSource{rdb: c.RDB, stream: c.Stream, group: c.Group, consumer: c.Consumer, block: c.Block}, nil
}

var _ Source = (*RedisSource)(nil)

// EnsureGroup creates the consumer group (MKSTREAM), tolerating BUSYGROUP. Starts at
// "0" (the OLDEST retained entry), NOT "$": this is a GDPR Art.33 "miss nothing" rail,
// so a DPO notice emitted before the group existed (first deploy, or while the consumer
// was down) MUST still be consumed. incident-bot's MINID trim bounds the replayed
// window (~7d) and the handler's idempotency guard makes re-processing already-delivered
// notices a cheap no-op. Once the group exists, Read uses ">" and continues from the
// group's last-delivered id, so "0" only governs the FIRST creation.
func (s *RedisSource) EnsureGroup(ctx context.Context) error {
	if err := s.rdb.XGroupCreateMkStream(ctx, s.stream, s.group, "0").Err(); err != nil {
		if !strings.Contains(err.Error(), "BUSYGROUP") {
			return fmt.Errorf("consume: XGROUP CREATE %s/%s: %w", s.stream, s.group, err)
		}
	}
	return nil
}

// Read pulls up to batchSize NEW (">") messages.
func (s *RedisSource) Read(ctx context.Context, batchSize int) ([]Message, error) {
	res, err := s.rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
		Group:    s.group,
		Consumer: s.consumer,
		Streams:  []string{s.stream, ">"},
		Count:    int64(batchSize),
		Block:    s.block,
	}).Result()
	if errors.Is(err, redis.Nil) {
		return nil, nil // no messages this poll
	}
	if err != nil {
		return nil, fmt.Errorf("consume: XREADGROUP %s: %w", s.stream, err)
	}
	return collect(res), nil
}

// Reclaim XAUTOCLAIMs entries pending for the group longer than minIdle, reassigning
// them to this consumer for re-processing (H2: recover crashed-before-ack notices).
func (s *RedisSource) Reclaim(ctx context.Context, minIdle time.Duration, count int) ([]Message, error) {
	msgs, _, err := s.rdb.XAutoClaim(ctx, &redis.XAutoClaimArgs{
		Stream:   s.stream,
		Group:    s.group,
		Consumer: s.consumer,
		MinIdle:  minIdle,
		Start:    "0",
		Count:    int64(count),
	}).Result()
	if err != nil {
		return nil, fmt.Errorf("consume: XAUTOCLAIM %s: %w", s.stream, err)
	}
	out := make([]Message, 0, len(msgs))
	for _, m := range msgs {
		out = append(out, Message{ID: m.ID, Fields: m.Values})
	}
	return out, nil
}

func collect(res []redis.XStream) []Message {
	var out []Message
	for _, st := range res {
		for _, m := range st.Messages {
			out = append(out, Message{ID: m.ID, Fields: m.Values})
		}
	}
	return out
}

// Ack XACKs the message.
func (s *RedisSource) Ack(ctx context.Context, m Message) error {
	if err := s.rdb.XAck(ctx, s.stream, s.group, m.ID).Err(); err != nil {
		return fmt.Errorf("consume: XACK %s/%s: %w", s.stream, m.ID, err)
	}
	return nil
}

// Outcome of handling one message.
type Outcome int

const (
	OutcomeIgnored          Outcome = iota // not a dpo_notice (foreign type) → ack + no-op
	OutcomeDelivered                       // delivered + recorded → ack
	OutcomeSkippedDuplicate                // already delivered → ack (idempotent)
	OutcomeMalformed                       // dpo_notice that failed to parse/validate → ack (drop; no redelivery loop)
	OutcomeFailed                          // delivery/record failed → do NOT ack (redeliver)
)

// HandlerFunc processes one message and returns its outcome (matches handler.Handle).
type HandlerFunc func(ctx context.Context, m Message) (Outcome, error)

// Stats counts a ProcessOne / ReclaimOnce batch.
type Stats struct {
	Read, Delivered, SkippedDuplicate, Ignored, Malformed, Failed, Acked int
}

// Processor reads/reclaims a batch + drives the handler, acking on non-failure outcomes.
type Processor struct {
	source  Source
	handler HandlerFunc
}

// NewProcessor ties a Source to a HandlerFunc.
func NewProcessor(source Source, handler HandlerFunc) (*Processor, error) {
	if source == nil || handler == nil {
		return nil, errors.New("consume: nil source/handler")
	}
	return &Processor{source: source, handler: handler}, nil
}

// ProcessOne reads up to batchSize NEW messages and handles each.
func (p *Processor) ProcessOne(ctx context.Context, batchSize int) (Stats, error) {
	msgs, err := p.source.Read(ctx, batchSize)
	if err != nil {
		return Stats{}, err
	}
	return p.handleBatch(ctx, msgs), nil
}

// ReclaimOnce reclaims stale pending entries (idle > minIdle) and handles each — the
// recovery path for messages whose consumer died before ack (H2).
func (p *Processor) ReclaimOnce(ctx context.Context, minIdle time.Duration, count int) (Stats, error) {
	msgs, err := p.source.Reclaim(ctx, minIdle, count)
	if err != nil {
		return Stats{}, err
	}
	return p.handleBatch(ctx, msgs), nil
}

// handleBatch dispatches each message; a Failed outcome is NOT acked (Redis
// re-delivers); everything else is acked. An ack failure is counted but not fatal (the
// work already happened). The handler logs its own errors.
func (p *Processor) handleBatch(ctx context.Context, msgs []Message) Stats {
	st := Stats{Read: len(msgs)}
	for _, m := range msgs {
		outcome, _ := p.handler(ctx, m)
		if outcome == OutcomeFailed {
			st.Failed++
			continue // leave pending for redelivery
		}
		switch outcome {
		case OutcomeDelivered:
			st.Delivered++
		case OutcomeSkippedDuplicate:
			st.SkippedDuplicate++
		case OutcomeMalformed:
			st.Malformed++
		default:
			st.Ignored++
		}
		if ackErr := p.source.Ack(ctx, m); ackErr == nil {
			st.Acked++
		}
	}
	return st
}

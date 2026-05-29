// Package consumer is the meta-worker's XREADGROUP loop.
//
// V1 ships as a SKELETON with an abstract `MessageSource` interface so
// tests can drive messages without a real Redis. Production wiring (cycle
// 11+) binds the real go-redis client.
//
// The consumer is INTENTIONALLY thin — its only job is:
//  1. Pull a batch from the next pending message on `xreality.*` streams.
//  2. Hand each message to `dispatch.Dispatcher.Dispatch`.
//  3. ACK on success; do NOT ACK on dispatch error (Redis Streams will
//     re-deliver after the consumer group's `pending entries list` ages
//     out — operational concern, not consumer code).
//
// The loop maintains a `lastConsumedAt` timestamp the operator can scrape
// via the `lw_meta_worker_lag_seconds` metric (gauge).
package consumer

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/loreweave/foundation/services/meta-worker/pkg/dispatch"
)

// Message is one xreality envelope as decoded from Redis Streams.
type Message struct {
	// Stream is the source stream name (e.g. "xreality.canon.promoted").
	Stream string
	// ID is the Redis Stream entry ID (e.g. "1700000000000-0"). Used by
	// AckedSource.Ack to mark the message processed.
	ID string
	// Fields is the parsed JSON envelope body.
	Fields map[string]any
}

// EventType returns the canonical event_type for this message, preferring
// the envelope's `event_type` field over the stream name (they should
// match — if they don't, the publisher wrote inconsistent data).
func (m Message) EventType() string {
	if v, ok := m.Fields["event_type"].(string); ok && v != "" {
		return v
	}
	return m.Stream
}

// MessageSource is the Redis Streams abstraction. Production binds
// go-redis's XReadGroup; tests drive it from in-memory channels.
//
// Read MUST block (or return zero messages with nil error) until a new
// message is available OR the context is cancelled. Returning an error
// causes the consumer to back off + retry.
type MessageSource interface {
	Read(ctx context.Context, batchSize int) ([]Message, error)
	Ack(ctx context.Context, m Message) error
}

// Consumer wires a MessageSource to a Dispatcher.
type Consumer struct {
	source         MessageSource
	dispatcher     *dispatch.Dispatcher
	lastConsumedAt time.Time
}

// New constructs a Consumer. Both args MUST be non-nil; the dispatcher
// MUST pass `ValidateAllowlist` (caller checks at startup).
func New(source MessageSource, d *dispatch.Dispatcher) (*Consumer, error) {
	if source == nil {
		return nil, errors.New("consumer: source nil")
	}
	if d == nil {
		return nil, errors.New("consumer: dispatcher nil")
	}
	return &Consumer{source: source, dispatcher: d}, nil
}

// ProcessOne pulls one batch and dispatches every message in order.
// Returns the per-call stats; the caller invokes ProcessOne in a loop.
//
// Behavior:
//   - Dispatch success → Ack.
//   - Dispatch error → do NOT Ack (Redis Streams re-delivers).
//   - Ack error → log + count, but don't fail the whole call (the
//     message has already been processed; Ack failure is a meta concern).
type ProcessStats struct {
	Read      int
	Dispatched int
	Acked      int
	NoHandler  int
	HandlerErr int
}

// ProcessOne reads one batch (up to batchSize) and dispatches every msg.
func (c *Consumer) ProcessOne(ctx context.Context, batchSize int) (ProcessStats, error) {
	stats := ProcessStats{}
	msgs, err := c.source.Read(ctx, batchSize)
	if err != nil {
		return stats, fmt.Errorf("consumer: read: %w", err)
	}
	stats.Read = len(msgs)
	for _, m := range msgs {
		derr := c.dispatcher.Dispatch(ctx, m.EventType(), m.Fields)
		if derr == nil {
			if ackErr := c.source.Ack(ctx, m); ackErr == nil {
				stats.Acked++
				stats.Dispatched++
			}
			c.lastConsumedAt = time.Now()
			continue
		}
		if errors.Is(derr, dispatch.ErrNoHandler) {
			stats.NoHandler++
		} else {
			stats.HandlerErr++
		}
	}
	return stats, nil
}

// LastConsumedAt exposes the wall-clock time of the most recent successful
// dispatch+ack. Used by the lag-seconds metric.
func (c *Consumer) LastConsumedAt() time.Time { return c.lastConsumedAt }

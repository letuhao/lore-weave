// Package xreality_fanout implements L2.L.2: when the poll loop sees an
// outbox row whose envelope metadata carries `cross_reality: true`, the
// publisher ALSO XADDs to the topic `xreality.<event_type>` so the
// meta-worker (sole consumer per I7) can dispatch it.
//
// ## Q-L2-4 topic naming convention
//
// `xreality.<entity>.<verb>` — verbatim from service map line 60. The
// EventType from the envelope ALREADY follows this shape (e.g.
// `xreality.canon.promoted`, `xreality.user.erased`). The fanout just
// uses EventType as the stream name (no rewriting); see TopicFor.
//
// ## Validation
//
// Defense-in-depth: the L2.F validator already checked the event payload
// matches its registered schema, but we re-check the `cross_reality` flag
// is `true` here. Calling Fanout on a non-xreality row is a programmer
// bug.
package xreality_fanout

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/loreweave/foundation/services/publisher/pkg/types"
)

// StreamEmitter writes to a named Redis Stream. Production binds to
// redis.Client.XAdd; tests use the in-memory fake.
//
// Per L1.K.12 outbox-event-emit-lint: only services/publisher/ may call
// XAdd directly. This package IS services/publisher/, so it's the
// legitimate emit site for xreality.* topics.
type StreamEmitter interface {
	XAdd(ctx context.Context, stream string, fields map[string]any) error
}

// ErrNotXReality is returned by Fanout when the row's metadata does NOT
// carry `cross_reality: true`. Defense-in-depth: the poll loop already
// gates on this; reaching Fanout without the flag is a programmer error.
var ErrNotXReality = errors.New("xreality_fanout: row is not cross_reality")

// ErrInvalidEventType is returned when EventType is empty or does not
// follow the `xreality.<entity>.<verb>` convention (Q-L2-4).
var ErrInvalidEventType = errors.New("xreality_fanout: event_type does not follow xreality.<entity>.<verb>")

// CanonFanoutTopic is the dedicated Redis Stream the canon mutation family
// (canon.* + admin.canon.override.*) fans out to. Per the events registry
// (_registry.yaml: "canon.entry.* … fans out as xreality.book.canon.updated")
// the OUTER topic is fixed while the INNER domain event_type is preserved in
// the envelope `event_type` field — the meta-worker dispatcher routes by that
// inner type (canon_writer handles canon.entry.*). I7 stays intact: the only
// ingress is this xreality.* stream.
const CanonFanoutTopic = "xreality.book.canon.updated"

// Fanouter is the publisher-side fanout. Implements the
// poll_loop.XRealityFanout interface.
type Fanouter struct {
	emitter StreamEmitter
}

// New constructs a Fanouter. Returns an error if emitter is nil.
func New(emitter StreamEmitter) (*Fanouter, error) {
	if emitter == nil {
		return nil, errors.New("xreality_fanout: emitter nil")
	}
	return &Fanouter{emitter: emitter}, nil
}

// TopicFor returns the canonical xreality topic name for an EventType.
// Validates the Q-L2-4 convention.
func TopicFor(eventType string) (string, error) {
	if eventType == "" {
		return "", fmt.Errorf("%w: empty", ErrInvalidEventType)
	}
	// Canon mutation family fans out via the dedicated canon stream; the
	// INNER event_type stays in the envelope for dispatch routing.
	if strings.HasPrefix(eventType, "canon.") || strings.HasPrefix(eventType, "admin.canon.override.") {
		return CanonFanoutTopic, nil
	}
	if !strings.HasPrefix(eventType, "xreality.") {
		return "", fmt.Errorf("%w: missing xreality. prefix: %q", ErrInvalidEventType, eventType)
	}
	parts := strings.Split(eventType, ".")
	// Want exactly: xreality.<entity>.<verb> — 3 parts.
	if len(parts) != 3 {
		return "", fmt.Errorf("%w: expected 3 dot-separated parts (xreality.<entity>.<verb>), got %q", ErrInvalidEventType, eventType)
	}
	for _, p := range parts[1:] {
		if p == "" {
			return "", fmt.Errorf("%w: empty segment in %q", ErrInvalidEventType, eventType)
		}
	}
	return eventType, nil
}

// Fanout XADDs the row's envelope to the xreality topic. NON-fatal for
// the publisher main loop — the poll_loop interprets a returned error as
// "increment fanout_error metric, continue".
func (f *Fanouter) Fanout(ctx context.Context, row types.OutboxRow) error {
	if !row.CrossReality() {
		return ErrNotXReality
	}
	topic, err := TopicFor(row.EventType)
	if err != nil {
		return err
	}
	fields := map[string]any{
		"event_id":          row.EventID.String(),
		"event_type":        row.EventType,
		"event_version":     row.EventVersion,
		"source_reality_id": row.RealityID.String(),
		"aggregate_type":    row.AggregateType,
		"aggregate_id":      row.AggregateID,
		"aggregate_version": row.AggregateVersion,
	}
	if row.Payload != nil {
		fields["payload"] = row.Payload
	}
	if row.Metadata != nil {
		fields["metadata"] = row.Metadata
	}
	return f.emitter.XAdd(ctx, topic, fields)
}

// Package breach wires the GDPR Art.33 personal-data-breach notification flow
// (gdpr_breach_flow) into a live path: an authenticated breach-declaration
// endpoint that starts the 72h clock, emits the breach lifecycle as events, and
// monitors the deadline.
//
// Architecture (Q-L7-1): incident-bot DECIDES + EMITS — it does NOT deliver or
// persist. So the DPO "notification" is an EMITTED OBLIGATION event
// (GDPRDPONoticeRequiredV1) that a downstream delivery consumer fulfills
// (tracked D-BREACH-DELIVERY-CONSUMER) — emission is NOT delivery. The breach
// record + deadline monitor are IN-PROCESS ONLY and do NOT survive a restart
// (tracked D-BREACH-DURABLE-STORE; the GDPRBreachOpenedV1 event is the anchor a
// durable consumer can replay to rebuild the monitor).
package breach

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"sync"

	"github.com/loreweave/foundation/contracts/incidents"
)

// EventEmitter publishes breach lifecycle events. Abstracted (like
// statuspage.EventEmitter) so transport is decoupled + tests need no broker.
type EventEmitter interface {
	EmitBreachOpened(ctx context.Context, ev incidents.GDPRBreachOpenedV1) error
	EmitDPONoticeRequired(ctx context.Context, ev incidents.GDPRDPONoticeRequiredV1) error
	EmitBreachDeadline(ctx context.Context, ev incidents.GDPRBreachDeadlineV1) error
}

// StructuredEmitter writes each event as one JSON line to w — the default
// transport (an audit/log-stream stand-in). The real broker emitter (Redis
// stream → the publisher path) is deferred: D-BREACH-BROKER-EMITTER. Validates
// every event before emit (fail-closed) and is safe for concurrent use (the
// Monitor goroutine and the HTTP handler both emit).
type StructuredEmitter struct {
	mu sync.Mutex
	w  io.Writer
}

// NewStructuredEmitter writes events to w (e.g. os.Stdout).
func NewStructuredEmitter(w io.Writer) *StructuredEmitter { return &StructuredEmitter{w: w} }

var _ EventEmitter = (*StructuredEmitter)(nil)

func (e *StructuredEmitter) EmitBreachOpened(_ context.Context, ev incidents.GDPRBreachOpenedV1) error {
	if err := ev.Validate(); err != nil {
		return err
	}
	return e.writeLine(ev)
}

func (e *StructuredEmitter) EmitDPONoticeRequired(_ context.Context, ev incidents.GDPRDPONoticeRequiredV1) error {
	if err := ev.Validate(); err != nil {
		return err
	}
	return e.writeLine(ev)
}

func (e *StructuredEmitter) EmitBreachDeadline(_ context.Context, ev incidents.GDPRBreachDeadlineV1) error {
	if err := ev.Validate(); err != nil {
		return err
	}
	return e.writeLine(ev)
}

func (e *StructuredEmitter) writeLine(v any) error {
	b, err := json.Marshal(v)
	if err != nil {
		return fmt.Errorf("breach: marshal event: %w", err)
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	if _, err := fmt.Fprintln(e.w, string(b)); err != nil {
		return fmt.Errorf("breach: emit event: %w", err)
	}
	return nil
}

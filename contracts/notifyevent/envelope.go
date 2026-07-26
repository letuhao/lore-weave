// Package notifyevent is the shared wire contract for the LLM-job terminal event
// published to the `loreweave.events` topic exchange when an async job reaches a
// terminal status (completed / failed / cancelled).
//
// It is the SINGLE source of truth for the producer (provider-registry-service
// jobs.Notifier) and every consumer (notification-service). Both sides previously
// hand-maintained a byte-identical struct joined only by JSON — a classic
// two-service contract drift risk (a field rename on the producer silently
// vanishes at the consumer). Importing this one type makes that drift impossible
// at compile time.
package notifyevent

import (
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
)

// EventsExchange is the durable RabbitMQ topic exchange terminal events are
// published to. Producer declares it; consumers bind to it.
const EventsExchange = "loreweave.events"

// TerminalEvent is the wire payload published when a job hits a terminal status.
// Mirrors the OpenAPI Job envelope subset that notification-service + downstream
// consumers actually use. JSON tags are LOAD-BEARING — they are the on-the-wire
// field names shared by producer + consumer; do not rename without bumping both
// sides (which now happens automatically, since both import this type).
type TerminalEvent struct {
	JobID        uuid.UUID       `json:"job_id"`
	OwnerUserID  uuid.UUID       `json:"owner_user_id"`
	Operation    string          `json:"operation"`
	Status       string          `json:"status"` // completed | failed | cancelled
	TraceID      string          `json:"trace_id,omitempty"`
	Result       json.RawMessage `json:"result,omitempty"`
	ErrorCode    string          `json:"error_code,omitempty"`
	ErrorMessage string          `json:"error_message,omitempty"`
	FinishReason string          `json:"finish_reason,omitempty"`
}

// RoutingKey produces the canonical topic key per the OpenAPI callback
// convention: user.{owner}.llm.{operation}.{status}. Consumers bind with
// `user.*.llm.#`.
func (ev TerminalEvent) RoutingKey() string {
	return fmt.Sprintf("user.%s.llm.%s.%s", ev.OwnerUserID, ev.Operation, ev.Status)
}

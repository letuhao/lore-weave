package jobs

// notifier.go — Phase 2c (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). Emits a
// terminal-state event to RabbitMQ topic `loreweave.events` whenever a
// job finishes (completed / failed / cancelled). Consumers route by
// the topic key:
//
//   user.{user_id}.llm.{operation}.{status}
//
// Notification-service (Phase 2d) consumes these and persists them to
// the user_notifications outbox; api-gateway-bff (Phase 2e) bridges
// from notifications → SSE so FE sees job-done events live.
//
// Webhook callbacks (callback.kind="webhook" with HMAC sig) are
// deferred to a Phase 2c-followup cycle.

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"

	rabbitmq "github.com/rabbitmq/amqp091-go"

	"github.com/google/uuid"
)

const (
	// Shared platform topic exchange. Mirrors translation-service's
	// broker.publish_event() pattern (services/translation-service/app/broker.py).
	llmEventsExchange = "loreweave.events"
)

// TerminalEvent is the wire payload published when a job hits a
// terminal status. Mirrors the openapi Job envelope subset that
// notification-service + downstream consumers actually use.
type TerminalEvent struct {
	JobID        uuid.UUID       `json:"job_id"`
	OwnerUserID  uuid.UUID       `json:"owner_user_id"`
	Operation    string          `json:"operation"`
	Status       string          `json:"status"`        // completed | failed | cancelled
	TraceID      string          `json:"trace_id,omitempty"`
	Result       json.RawMessage `json:"result,omitempty"`
	ErrorCode    string          `json:"error_code,omitempty"`
	ErrorMessage string          `json:"error_message,omitempty"`
	FinishReason string          `json:"finish_reason,omitempty"`
}

// RoutingKey produces the canonical topic key per openapi callback
// convention.
func (ev TerminalEvent) RoutingKey() string {
	return fmt.Sprintf("user.%s.llm.%s.%s", ev.OwnerUserID, ev.Operation, ev.Status)
}

// Notifier publishes TerminalEvents. Implementations:
//   - rabbitMQNotifier:  amqp091 publish to loreweave.events topic
//   - NoopNotifier:      no-op; used when RABBITMQ_URL is unset (dev/tests)
type Notifier interface {
	PublishTerminal(ctx context.Context, ev TerminalEvent) error
	Close() error
}

// NoopNotifier discards events. Constructed when RABBITMQ_URL is empty
// so dev/test runs without a broker keep working.
type NoopNotifier struct{}

func (NoopNotifier) PublishTerminal(_ context.Context, _ TerminalEvent) error { return nil }
func (NoopNotifier) Close() error                                              { return nil }

// rabbitMQNotifier holds a connection + channel. Both are reused across
// PublishTerminal calls; we re-declare the topic exchange on construction
// so the broker has it cached after the first cold-start round-trip.
type rabbitMQNotifier struct {
	conn   *rabbitmq.Connection
	ch     *rabbitmq.Channel
	logger *slog.Logger
	mu     sync.Mutex // serialize publishes; amqp091 channels are NOT goroutine-safe
}

// NewRabbitMQNotifier opens a connection + channel, declares the topic
// exchange (idempotent — durable + same name as translation-service),
// and returns a notifier ready for publishing.
func NewRabbitMQNotifier(amqpURL string, logger *slog.Logger) (Notifier, error) {
	if logger == nil {
		logger = slog.Default()
	}
	conn, err := rabbitmq.Dial(amqpURL)
	if err != nil {
		return nil, fmt.Errorf("amqp dial: %w", err)
	}
	ch, err := conn.Channel()
	if err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("amqp channel: %w", err)
	}
	if err := ch.ExchangeDeclare(
		llmEventsExchange,
		"topic",
		true,  // durable — survives broker restart
		false, // auto-delete
		false, // internal
		false, // no-wait
		nil,
	); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return nil, fmt.Errorf("amqp declare exchange: %w", err)
	}
	return &rabbitMQNotifier{conn: conn, ch: ch, logger: logger}, nil
}

func (n *rabbitMQNotifier) PublishTerminal(ctx context.Context, ev TerminalEvent) error {
	body, err := json.Marshal(ev)
	if err != nil {
		return fmt.Errorf("marshal event: %w", err)
	}
	n.mu.Lock()
	defer n.mu.Unlock()
	err = n.ch.PublishWithContext(
		ctx,
		llmEventsExchange,
		ev.RoutingKey(),
		false, // mandatory
		false, // immediate
		rabbitmq.Publishing{
			ContentType:  "application/json",
			DeliveryMode: rabbitmq.Persistent,
			Body:         body,
		},
	)
	if err != nil {
		n.logger.Warn("publish terminal event failed",
			"job_id", ev.JobID.String(), "status", ev.Status, "err", err)
		return fmt.Errorf("amqp publish: %w", err)
	}
	return nil
}

func (n *rabbitMQNotifier) Close() error {
	if n.ch != nil {
		_ = n.ch.Close()
	}
	if n.conn != nil {
		return n.conn.Close()
	}
	return nil
}

package consumer

// Phase 2d (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). RabbitMQ consumer for
// async LLM job terminal events. Binds a durable queue to
// `loreweave.events` (topic) with key `user.*.llm.#` so any user, any
// operation, any status flows in. Each event is translated into a
// notifications row so the FE's existing notification stream surfaces
// "chat completed", "extraction failed", etc. without per-feature
// wiring.
//
// Provider-registry is the publisher (services/provider-registry-service/
// internal/jobs/notifier.go). Stay binary-compatible with its
// TerminalEvent struct.

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	rabbitmq "github.com/rabbitmq/amqp091-go"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/loreweave/foundation/contracts/notifyevent"
	"github.com/loreweave/observability"

	"github.com/loreweave/notification-service/internal/category"
	"github.com/loreweave/notification-service/internal/prefs"
	"github.com/loreweave/notification-service/internal/push"
	"github.com/loreweave/notification-service/internal/redact"
)

const (
	exchangeName = notifyevent.EventsExchange
	queueName    = "notification-service.llm-jobs"
	bindingKey   = "user.*.llm.#"
)

// terminalEvent is the SHARED wire contract (contracts/notifyevent), aliased so
// this consumer's existing references keep working. The producer
// (provider-registry jobs.Notifier) imports the same type, so the struct can no
// longer drift between the two services (it used to be a hand-maintained copy).
type terminalEvent = notifyevent.TerminalEvent

// notificationArgs is the row-shape transformer output. Decoupled from
// the SQL itself so unit tests can verify shape without a DB.
type notificationArgs struct {
	UserID   uuid.UUID
	Category string
	Title    string
	Body     string
	Metadata []byte // JSON-encoded
	// D-NOTIF-I18N (NOTIF-1): i18n substrate written alongside the rendered
	// English Title/Body (which remain the fallback). MessageKey is a stable
	// per-(category,status) key; MessageParams carries the interpolation
	// values (operation, error_code) as JSON. A locale-aware FE renders from
	// these; any other client keeps showing Title/Body.
	MessageKey    string
	MessageParams []byte // JSON-encoded
	// DedupKey (P2·C) — idempotency key for the at-least-once AMQP delivery. A
	// broker redelivery (committed INSERT, lost ACK) carries the same job_id:status,
	// so the INSERT ... ON CONFLICT (user_id, dedup_key) DO NOTHING collapses it to
	// one row. Pure-derived here so the key shape is unit-locked.
	DedupKey string
}

// transformTerminalEvent converts a parsed event into the args we'll
// INSERT. Pure function — testable without a broker.
func transformTerminalEvent(ev terminalEvent) notificationArgs {
	const cat = "llm_job"
	title := titleFor(ev.Operation, ev.Status)
	// P2·C — scrub secret-shaped tokens an upstream error message may have echoed
	// before it lands in the notifications table / push feed.
	body := redact.Body(bodyFor(ev))
	meta, _ := json.Marshal(map[string]any{
		"job_id":        ev.JobID.String(),
		"operation":     ev.Operation,
		"status":        ev.Status,
		"trace_id":      ev.TraceID,
		"finish_reason": ev.FinishReason,
		"error_code":    ev.ErrorCode,
	})
	return notificationArgs{
		UserID:        ev.OwnerUserID,
		Category:      cat,
		Title:         title,
		Body:          body,
		Metadata:      meta,
		MessageKey:    messageKey(cat, ev.Status),
		MessageParams: messageParams(ev),
		DedupKey:      dedupKey(ev),
	}
}

// dedupKey is the at-least-once idempotency key for a terminal event: one row per
// (job, terminal status). A redelivery of the same terminal event collapses via
// ON CONFLICT; distinct statuses of one job (a job that emits running→completed is
// not this path — only terminal events reach here) stay distinct. Empty status
// falls back to job_id alone rather than a trailing colon, so the key is always
// well-formed.
func dedupKey(ev terminalEvent) string {
	if ev.Status == "" {
		return ev.JobID.String()
	}
	return ev.JobID.String() + ":" + ev.Status
}

// messageKey builds the stable i18n key: notif.<category>.<status>
// (e.g. notif.llm_job.completed). The status comes straight from the
// terminal event enum (completed | failed | cancelled); an unexpected
// status still yields a well-formed, deterministic key rather than an
// empty string, so the FE can fall back to title/body predictably.
func messageKey(category, status string) string {
	if status == "" {
		status = "unknown"
	}
	return fmt.Sprintf("notif.%s.%s", category, status)
}

// messageParams returns the JSON-encoded interpolation params a locale-aware
// FE substitutes into the localized template. Always carries `operation`;
// failures additionally carry `error_code` (when present) so a localized
// error notification can name the failure. Go's json.Marshal emits UTF-8
// (ML-5: no \uXXXX inflation) — operation/error_code are ASCII enum tokens
// anyway, but any future prose param stays UTF-8 on the wire.
func messageParams(ev terminalEvent) []byte {
	params := map[string]any{"operation": ev.Operation}
	if ev.Status == "failed" && ev.ErrorCode != "" {
		params["error_code"] = ev.ErrorCode
	}
	b, _ := json.Marshal(params)
	return b
}

// titleFor produces a short human-readable label per (operation, status).
// Operation strings come straight from the openapi enum.
func titleFor(operation, status string) string {
	op := opLabel(operation)
	switch status {
	case "completed":
		return op + " completed"
	case "failed":
		return op + " failed"
	case "cancelled":
		return op + " cancelled"
	default:
		return op + " " + status
	}
}

// opLabel turns the JobOperation enum (`entity_extraction`, `image_gen`,
// `video_gen`, etc.) into a human-readable label. Underscores become
// spaces; first letter capitalised. Generic — new operation names just
// need the consumer_test.go fixture to add an explicit assertion.
func opLabel(operation string) string {
	if operation == "" {
		return "Job"
	}
	s := strings.ReplaceAll(operation, "_", " ")
	return strings.ToUpper(s[:1]) + s[1:]
}

// bodyFor produces a one-sentence body summary. Empty string for
// successes (the title is enough); errors include code/message snippet.
func bodyFor(ev terminalEvent) string {
	if ev.Status == "failed" && ev.ErrorMessage != "" {
		// Cap message length so a verbose upstream doesn't blow up
		// the notifications table or the FE's truncated render.
		msg := ev.ErrorMessage
		if len(msg) > 240 {
			msg = msg[:240] + "..."
		}
		if ev.ErrorCode != "" {
			return fmt.Sprintf("[%s] %s", ev.ErrorCode, msg)
		}
		return msg
	}
	return ""
}

// Consumer owns the connection + channel + queue lifecycle for the LLM
// jobs subscription. Construct via Start.
type Consumer struct {
	conn   *rabbitmq.Connection
	ch     *rabbitmq.Channel
	pool   *pgxpool.Pool
	logger *slog.Logger
	sender *push.Sender // M5 — fires a content-free push on a fresh insert (may be a no-op)
}

// Start dials the broker, declares the topic exchange + queue + binding,
// and spawns a goroutine that consumes deliveries until ctx is cancelled
// (or the connection drops). Caller owns the returned Consumer's Close
// lifecycle. `sender` may be nil (push disabled) — handle() guards it.
func Start(ctx context.Context, amqpURL string, pool *pgxpool.Pool, logger *slog.Logger, sender *push.Sender) (*Consumer, error) {
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
	if err := ch.ExchangeDeclare(exchangeName, "topic", true, false, false, false, nil); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return nil, fmt.Errorf("declare exchange: %w", err)
	}
	if _, err := ch.QueueDeclare(queueName, true, false, false, false, nil); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return nil, fmt.Errorf("declare queue: %w", err)
	}
	if err := ch.QueueBind(queueName, bindingKey, exchangeName, false, nil); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return nil, fmt.Errorf("bind queue: %w", err)
	}
	deliveries, err := ch.Consume(queueName, "notification-service", false, false, false, false, nil)
	if err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return nil, fmt.Errorf("consume: %w", err)
	}

	c := &Consumer{conn: conn, ch: ch, pool: pool, logger: logger, sender: sender}
	go c.run(ctx, deliveries)
	logger.Info("llm-jobs consumer started",
		"exchange", exchangeName, "queue", queueName, "binding", bindingKey)
	return c, nil
}

func (c *Consumer) run(ctx context.Context, deliveries <-chan rabbitmq.Delivery) {
	for {
		select {
		case <-ctx.Done():
			return
		case d, ok := <-deliveries:
			if !ok {
				c.logger.Warn("llm-jobs consumer delivery channel closed")
				return
			}
			c.handle(ctx, d)
		}
	}
}

func (c *Consumer) handle(ctx context.Context, d rabbitmq.Delivery) {
	// Phase 6c — continue the producer's trace across the RabbitMQ hop.
	// Extract reads the traceparent provider-registry's notifier injected;
	// a delivery with no headers just starts a fresh root (no failure).
	ctx = observability.Extract(ctx, observability.AMQPCarrier(d.Headers))
	ctx, span := observability.Tracer("consumer").Start(ctx, "llm-event.consume",
		trace.WithSpanKind(trace.SpanKindConsumer),
		trace.WithAttributes(
			attribute.String("messaging.system", "rabbitmq"),
			attribute.String("messaging.rabbitmq.routing_key", d.RoutingKey),
		))
	defer span.End()

	var ev terminalEvent
	if err := json.Unmarshal(d.Body, &ev); err != nil {
		c.logger.Warn("malformed llm-job event — discarding", "err", err)
		span.RecordError(err)
		span.SetStatus(codes.Error, "malformed event body")
		// Don't requeue malformed messages; would just loop forever.
		_ = d.Nack(false, false)
		return
	}
	if ev.OwnerUserID == uuid.Nil || ev.JobID == uuid.Nil {
		c.logger.Warn("event missing owner or job_id — discarding", "routing_key", d.RoutingKey)
		span.SetStatus(codes.Error, "event missing owner or job_id")
		_ = d.Nack(false, false)
		return
	}
	span.SetAttributes(
		attribute.String("job.id", ev.JobID.String()),
		attribute.String("llm.operation", ev.Operation),
	)
	args := transformTerminalEvent(ev)
	// Route the consumer insert through the SAME validation the HTTP
	// ingress path uses (audit P0-4 / NOTIF-2): the consumer previously
	// inserted its category via raw SQL, bypassing validCategory. A
	// category not in the single source-of-truth set is a poison message —
	// discard without requeue so it can't loop forever.
	if !category.Valid(args.Category) {
		c.logger.Error("invalid notification category — discarding",
			"category", args.Category, "job_id", ev.JobID.String())
		span.SetStatus(codes.Error, "invalid notification category")
		_ = d.Nack(false, false)
		return
	}
	// P2·C (opt-out) — the user disabled this category → don't store/push. Ack (it's
	// a successful decision, not a failure); fail-OPEN on a lookup error so a prefs
	// hiccup never silently drops a notification.
	if suppressed, perr := prefs.Suppressed(ctx, c.pool, args.UserID, args.Category); perr != nil {
		c.logger.Warn("opt-out check failed — delivering anyway", "err", perr, "job_id", ev.JobID.String())
	} else if suppressed {
		span.SetAttributes(attribute.Bool("notification.suppressed", true))
		_ = d.Ack(false)
		return
	}
	// P2·C — dedup on (user_id, dedup_key): a broker redelivery of an already-
	// inserted terminal event is collapsed to one row (partial-unique index). The
	// ON CONFLICT predicate mirrors the index's WHERE so it targets that index.
	tag, err := c.pool.Exec(ctx, `
INSERT INTO notifications (user_id, category, title, body, metadata, message_key, message_params, dedup_key)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (user_id, dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING
`, args.UserID, args.Category, args.Title, args.Body, args.Metadata, args.MessageKey, args.MessageParams, args.DedupKey)
	if err != nil {
		c.logger.Error("notification insert failed — requeueing",
			"err", err, "job_id", ev.JobID.String())
		span.RecordError(err)
		span.SetStatus(codes.Error, "notification insert failed")
		// Requeue so a transient DB hiccup doesn't lose the event.
		_ = d.Nack(false, true)
		return
	}
	// B4 (§8-B4) exactly-once push: fire ONLY when this delivery actually INSERTED a row
	// (RowsAffected==1). Under at-least-once redelivery the ON CONFLICT DO NOTHING makes a
	// duplicate a 0-row no-op → no second buzz. Best-effort + out-of-band (the row is committed).
	if c.sender != nil && tag.RowsAffected() == 1 {
		go c.sender.MaybeSend(context.Background(), args.UserID, args.Category, args.MessageKey, "/activity", "")
	}
	_ = d.Ack(false)
}

func (c *Consumer) Close() error {
	if c.ch != nil {
		_ = c.ch.Close()
	}
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}

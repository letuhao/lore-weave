package jobs

// queue.go — LLM re-arch Phase 1 Commit 3. A durable work queue over RabbitMQ
// that REPLACES the direct `go Process(...)` dispatch + the governor's
// block-acquire-then-FAIL gate. Jobs wait IN the queue / on a per-kind
// semaphore (sized = governor.MaxFor(kind)); a slow job DELAYS the queue, it
// never cascades `ErrGovernorTimeout` to everyone behind it (the incident).
//
//   submit → Publish(job_id) → llm.jobs (durable, persistent)
//   one consumer, prefetch = P worker goroutines:
//     load job → resolve kind → acquire per-kind semaphore (local → 1 = the
//     single GPU; cloud → cloudMax) → Process (Phase-0 cancellable ctx) → ack
//   consumer crash → un-acked message redelivered. Redelivery RE-RUNS a job
//   that crashed BEFORE MarkRunning (still `pending`); a job that crashed AFTER
//   MarkRunning is `running`, and Process's `WHERE status='pending'` gate blocks
//   re-running it — that rare stuck-`running` row is recovered by the truth
//   sweeper (spec §5.6), not by redelivery.
//
// Design note (deviation from spec D1's per-kind queues): a SINGLE queue + a
// per-kind in-process semaphore handles ANY provider kind without enumerating
// kinds up front (a per-kind queue with no running consumer would strand its
// jobs). Concurrency bound + wait-not-fail are identical; durability +
// redelivery are preserved.
//
// Behind LLM_JOB_QUEUE_ENABLED (default off): when off, submit keeps today's
// direct goroutine path — zero-risk additive until enabled. The governor's
// atomic-Lua slot logic is retained as a SAFETY BELT inside Process (Guard).

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"

	rabbitmq "github.com/rabbitmq/amqp091-go"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/ratelimit"
)

const llmJobsQueue = "llm.jobs"

// queueMessage is the wire body. Minimal — the llm_jobs row is the source of
// truth; the consumer loads everything else by id (cheap redelivery, no large
// payload on the bus).
type queueMessage struct {
	JobID string `json:"job_id"`
}

// KindResolver returns the provider kind (governor concurrency class) for a job,
// or ok=false when the job/model is gone (consumer acks + drops).
type KindResolver func(ctx context.Context, jobID uuid.UUID) (kind string, ok bool)

// JobRunner runs a job to terminal SYNCHRONOUSLY (so the ack happens only after
// the job is terminal). The caller layers the Phase-0 cancellable ctx + the
// jobID→cancel registration so DELETE still aborts an in-flight queued job.
type JobRunner func(ctx context.Context, jobID uuid.UUID)

// JobQueue publishes jobs to the durable work queue and runs the consumer pool
// with a per-kind concurrency semaphore. amqp091 channels are NOT goroutine-safe
// (the publish channel is mutex-guarded; the consumer owns its own channel).
type JobQueue struct {
	conn   *rabbitmq.Connection
	pubCh  *rabbitmq.Channel
	pubMu  sync.Mutex
	logger *slog.Logger

	cloudMax int
	semMu    sync.Mutex
	sems     map[string]chan struct{} // per-kind concurrency semaphore (lazy)

	consumerCh *rabbitmq.Channel
}

// NewJobQueue dials RabbitMQ, opens the publish channel, and declares the
// durable work queue. cloudMax sizes the per-kind semaphore for cloud kinds.
func NewJobQueue(amqpURL string, cloudMax int, logger *slog.Logger) (*JobQueue, error) {
	if logger == nil {
		logger = slog.Default()
	}
	if cloudMax < 1 {
		cloudMax = 1
	}
	conn, err := rabbitmq.Dial(amqpURL)
	if err != nil {
		return nil, fmt.Errorf("job-queue dial: %w", err)
	}
	ch, err := conn.Channel()
	if err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("job-queue channel: %w", err)
	}
	if _, err := ch.QueueDeclare(llmJobsQueue, true, false, false, false, nil); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return nil, fmt.Errorf("job-queue declare: %w", err)
	}
	return &JobQueue{conn: conn, pubCh: ch, logger: logger, cloudMax: cloudMax, sems: map[string]chan struct{}{}}, nil
}

// Publish enqueues a job as a persistent message on the durable work queue.
func (q *JobQueue) Publish(ctx context.Context, jobID uuid.UUID) error {
	body, err := json.Marshal(queueMessage{JobID: jobID.String()})
	if err != nil {
		return fmt.Errorf("job-queue marshal: %w", err)
	}
	q.pubMu.Lock()
	defer q.pubMu.Unlock()
	return q.pubCh.PublishWithContext(ctx,
		"",           // default exchange → route by queue name
		llmJobsQueue, // routing key = queue name
		false,        // mandatory
		false,        // immediate
		rabbitmq.Publishing{
			ContentType:  "application/json",
			DeliveryMode: rabbitmq.Persistent, // survive broker restart
			Body:         body,
		},
	)
}

// semFor lazily builds the per-kind concurrency semaphore (a buffered channel of
// MaxFor(kind) tokens). Local kinds → 1 (the single GPU); cloud → cloudMax.
func (q *JobQueue) semFor(kind string) chan struct{} {
	q.semMu.Lock()
	defer q.semMu.Unlock()
	s, ok := q.sems[kind]
	if !ok {
		n := ratelimit.MaxFor(kind, q.cloudMax)
		s = make(chan struct{}, n)
		q.sems[kind] = s
	}
	return s
}

// StartConsumer opens the consumer channel, sets prefetch = workers, and runs
// `workers` goroutines. Each: load+resolve kind → acquire the per-kind semaphore
// (BLOCKS, queue-not-fail) → run the job → ack. prefetch = workers bounds the
// in-flight (unacked) set; jobs beyond that stay in the durable queue. A
// process crash leaves messages un-acked → redelivered (the reaper).
func (q *JobQueue) StartConsumer(ctx context.Context, workers int, resolve KindResolver, run JobRunner) error {
	if workers < 1 {
		workers = 1
	}
	ch, err := q.conn.Channel()
	if err != nil {
		return fmt.Errorf("job-queue consumer channel: %w", err)
	}
	if _, err := ch.QueueDeclare(llmJobsQueue, true, false, false, false, nil); err != nil {
		_ = ch.Close()
		return fmt.Errorf("job-queue consumer declare: %w", err)
	}
	if err := ch.Qos(workers, 0, false); err != nil {
		_ = ch.Close()
		return fmt.Errorf("job-queue qos: %w", err)
	}
	deliveries, err := ch.Consume(llmJobsQueue, "", false, false, false, false, nil)
	if err != nil {
		_ = ch.Close()
		return fmt.Errorf("job-queue consume: %w", err)
	}
	q.consumerCh = ch
	for i := 0; i < workers; i++ {
		go func() {
			for {
				select {
				case <-ctx.Done():
					return
				case d, ok := <-deliveries:
					if !ok {
						return
					}
					q.handleDelivery(ctx, d, resolve, run)
				}
			}
		}()
	}
	q.logger.Info("job-queue consumer started", "workers", workers, "cloud_max", q.cloudMax)
	return nil
}

// handleDelivery decodes one message, gates on the per-kind semaphore, runs the
// job synchronously, and acks. A malformed/gone job is acked + dropped (a
// redelivery would never resolve).
func (q *JobQueue) handleDelivery(ctx context.Context, d rabbitmq.Delivery, resolve KindResolver, run JobRunner) {
	var msg queueMessage
	if err := json.Unmarshal(d.Body, &msg); err != nil {
		q.logger.Warn("job-queue: undecodable message dropped", "err", err)
		_ = d.Ack(false)
		return
	}
	jobID, err := uuid.Parse(msg.JobID)
	if err != nil {
		q.logger.Warn("job-queue: bad job_id dropped", "job_id", msg.JobID)
		_ = d.Ack(false)
		return
	}
	kind, ok := resolve(ctx, jobID)
	if !ok {
		q.logger.Warn("job-queue: kind unresolved — dropping", "job_id", jobID.String())
		_ = d.Ack(false)
		return
	}
	sem := q.semFor(kind)
	select {
	case sem <- struct{}{}: // acquire (BLOCKS when the kind is at capacity → wait, not fail)
	case <-ctx.Done():
		// Shutting down — leave un-acked for redelivery.
		_ = d.Nack(false, true)
		return
	}
	defer func() { <-sem }() // release
	run(ctx, jobID)          // synchronous → ack only after the job is terminal
	_ = d.Ack(false)
}

// Close stops the consumer + publish channel + connection.
func (q *JobQueue) Close() error {
	if q.consumerCh != nil {
		_ = q.consumerCh.Close()
	}
	if q.pubCh != nil {
		_ = q.pubCh.Close()
	}
	if q.conn != nil {
		return q.conn.Close()
	}
	return nil
}

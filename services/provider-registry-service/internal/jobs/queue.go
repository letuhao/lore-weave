package jobs

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"

	rabbitmq "github.com/rabbitmq/amqp091-go"

	"github.com/google/uuid"
)

const llmJobsQueue = "llm.jobs"

type queueMessage struct {
	JobID string `json:"job_id"`
}

// ConcurrencyResolver returns an effective, positive credential cap. ok=false is
// reserved for a genuinely deleted model; lookup errors trigger a requeue.
type ConcurrencyResolver func(context.Context, uuid.UUID) (string, int, bool, error)
type JobRunner func(context.Context, uuid.UUID, string, int) error

type queueSlot struct {
	limit   int
	inUse   int
	waiters int
	changed chan struct{}
}

type JobQueue struct {
	conn       *rabbitmq.Connection
	pubCh      *rabbitmq.Channel
	pubMu      sync.Mutex
	logger     *slog.Logger
	semMu      sync.Mutex
	sems       map[string]*queueSlot
	consumerCh *rabbitmq.Channel
}

func NewJobQueue(amqpURL string, logger *slog.Logger) (*JobQueue, error) {
	if logger == nil {
		logger = slog.Default()
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
	return &JobQueue{conn: conn, pubCh: ch, logger: logger, sems: map[string]*queueSlot{}}, nil
}

func (q *JobQueue) Publish(ctx context.Context, jobID uuid.UUID) error {
	body, err := json.Marshal(queueMessage{JobID: jobID.String()})
	if err != nil {
		return fmt.Errorf("job-queue marshal: %w", err)
	}
	q.pubMu.Lock()
	defer q.pubMu.Unlock()
	return q.pubCh.PublishWithContext(ctx, "", llmJobsQueue, false, false, rabbitmq.Publishing{ContentType: "application/json", DeliveryMode: rabbitmq.Persistent, Body: body})
}

// semFor reserves a waiter reference atomically with finding/creating the slot,
// preventing an idle slot from being evicted between lookup and waiter count.
func (q *JobQueue) semFor(class string, limit int) *queueSlot {
	if limit <= 0 {
		return nil
	}
	q.semMu.Lock()
	defer q.semMu.Unlock()
	slot := q.sems[class]
	if slot == nil {
		slot = &queueSlot{limit: limit, changed: make(chan struct{})}
		q.sems[class] = slot
	}
	slot.waiters++
	return slot
}

func (q *JobQueue) deleteSlotIfIdleLocked(class string, slot *queueSlot) {
	if slot.inUse == 0 && slot.waiters == 0 && q.sems[class] == slot {
		delete(q.sems, class)
	}
}

func (q *JobQueue) StartConsumer(ctx context.Context, workers int, resolve ConcurrencyResolver, run JobRunner) error {
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
	q.logger.Info("job-queue consumer started", "workers", workers)
	return nil
}

func (q *JobQueue) handleDelivery(ctx context.Context, d rabbitmq.Delivery, resolve ConcurrencyResolver, run JobRunner) {
	if ctx.Err() != nil {
		_ = d.Nack(false, true)
		return
	}
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
	class, limit, ok, err := resolve(ctx, jobID)
	if err != nil {
		q.logger.Warn("job-queue: concurrency lookup failed — requeue", "job_id", jobID.String(), "err", err)
		_ = d.Nack(false, true)
		return
	}
	if !ok {
		q.logger.Warn("job-queue: model missing — dropping", "job_id", jobID.String())
		_ = d.Ack(false)
		return
	}

	slot := q.semFor(class, limit)
	if slot != nil {
		for {
			q.semMu.Lock()
			if slot.inUse < slot.limit {
				slot.waiters--
				slot.inUse++
				q.semMu.Unlock()
				defer func() {
					q.semMu.Lock()
					slot.inUse--
					close(slot.changed)
					slot.changed = make(chan struct{})
					q.deleteSlotIfIdleLocked(class, slot)
					q.semMu.Unlock()
				}()

				break
			}
			changed := slot.changed
			q.semMu.Unlock()
			select {
			case <-ctx.Done():
				q.semMu.Lock()
				slot.waiters--
				q.deleteSlotIfIdleLocked(class, slot)
				q.semMu.Unlock()
				_ = d.Nack(false, true)
				return

			case <-changed:
			}
		}
	}
	if err := run(ctx, jobID, class, limit); err != nil {
		q.logger.Warn("job-queue: runner failed — requeue", "job_id", jobID.String(), "err", err)
		_ = d.Nack(false, true)
		return
	}
	_ = d.Ack(false)
}

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

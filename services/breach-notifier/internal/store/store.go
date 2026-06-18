// Package store persists DPO-notice delivery state — the durable
// "delivery-confirmed" record distinct from the emitted obligation (the gap
// D-BREACH-DELIVERY-CONSUMER demanded: "DPO notified" must mean delivered, not queued).
package store

import (
	"context"
	"time"
)

// Delivery status lifecycle.
const (
	StatusDelivered = "delivered"
	StatusFailed    = "failed"
)

// Delivery is the persisted delivery state for one incident's DPO notice.
type Delivery struct {
	IncidentID  string
	Subject     string
	Deadline    time.Time
	Channel     string
	Status      string
	LastError   string
	DeliveredAt *time.Time
}

// DeliveryStore records + queries DPO-notice delivery state. Idempotency hinges on
// AlreadyDelivered: a notice whose incident already shows status=delivered is skipped
// so the DPO is never double-notified.
type DeliveryStore interface {
	AlreadyDelivered(ctx context.Context, incidentID string) (bool, error)
	// RecordAttempt upserts the row after a delivery attempt: status delivered/failed,
	// attempts incremented, delivered_at stamped (and retained) on success, last_error
	// captured on failure.
	RecordAttempt(ctx context.Context, d Delivery, at time.Time) error
}

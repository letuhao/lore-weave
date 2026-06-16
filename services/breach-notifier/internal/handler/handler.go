// Package handler routes a breach-stream message: only gdpr.dpo_notice_required.v1 is
// actioned (deliver the DPO notice + record confirmation). Idempotent — an
// already-delivered incident is skipped so the DPO is never double-notified.
package handler

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"time"
	"unicode/utf8"

	"github.com/loreweave/foundation/contracts/incidents"
	"github.com/loreweave/foundation/services/breach-notifier/internal/consume"
	"github.com/loreweave/foundation/services/breach-notifier/internal/deliver"
	"github.com/loreweave/foundation/services/breach-notifier/internal/store"
)

// Handler delivers DPO notices + records confirmation.
type Handler struct {
	notifier deliver.Notifier
	store    store.DeliveryStore
	now      func() time.Time
	logger   *slog.Logger
}

// New builds a Handler; fails closed on nil notifier/store.
func New(n deliver.Notifier, s store.DeliveryStore, now func() time.Time, l *slog.Logger) (*Handler, error) {
	if n == nil || s == nil {
		return nil, errors.New("handler: nil notifier/store")
	}
	if now == nil {
		now = time.Now
	}
	if l == nil {
		l = slog.Default()
	}
	return &Handler{notifier: n, store: s, now: now, logger: l}, nil
}

// Handle processes one stream message (matches consume.HandlerFunc).
func (h *Handler) Handle(ctx context.Context, m consume.Message) (consume.Outcome, error) {
	if m.EventType() != incidents.TypeGDPRDPONoticeRequiredV1 {
		return consume.OutcomeIgnored, nil // opened/deadline/foreign → ack + no-op
	}
	notice, ok := parseNotice(m)
	if !ok {
		// Malformed obligation → ack-and-drop (re-delivery would loop forever) but
		// counted distinctly (OutcomeMalformed → lw_breach_delivery_malformed_total) so
		// a spike of bad obligations is observable, not silent.
		h.logger.Warn("breach-notifier: malformed dpo_notice_required — dropping", "id", m.ID)
		return consume.OutcomeMalformed, nil
	}
	already, err := h.store.AlreadyDelivered(ctx, notice.IncidentID)
	if err != nil {
		h.logger.Error("breach-notifier: store idempotency check failed", "incident_id", notice.IncidentID, "err", err)
		return consume.OutcomeFailed, err // retry
	}
	if already {
		return consume.OutcomeSkippedDuplicate, nil // idempotent: do not double-notify
	}

	channel, derr := h.notifier.Deliver(ctx, notice)
	at := h.now().UTC()
	if derr != nil {
		h.logger.Error("breach-notifier: DPO delivery failed", "incident_id", notice.IncidentID, "err", derr)
		_ = h.store.RecordAttempt(ctx, store.Delivery{
			IncidentID: notice.IncidentID, Subject: notice.Subject, Deadline: notice.Deadline,
			Channel: channel, Status: store.StatusFailed, LastError: truncate(derr.Error(), 500),
		}, at)
		return consume.OutcomeFailed, derr // retry
	}
	if rerr := h.store.RecordAttempt(ctx, store.Delivery{
		IncidentID: notice.IncidentID, Subject: notice.Subject, Deadline: notice.Deadline,
		Channel: channel, Status: store.StatusDelivered,
	}, at); rerr != nil {
		// Delivered but NOT recorded → retry. A redelivery may re-notify (the record
		// that powers the idempotency guard didn't land) — accepted: a duplicate DPO
		// notice is far safer than a lost legal notification.
		h.logger.Error("breach-notifier: delivered but record failed (will retry)", "incident_id", notice.IncidentID, "err", rerr)
		return consume.OutcomeFailed, rerr
	}
	h.logger.Info("breach-notifier: DPO notice delivered + recorded", "incident_id", notice.IncidentID, "channel", channel)
	return consume.OutcomeDelivered, nil
}

// parseNotice extracts the obligation from the stream entry's JSON payload, validating
// it against the CONTRACT's own validator (incidents.GDPRDPONoticeRequiredV1.Validate)
// rather than a re-implemented subset — so consumer acceptance can't silently drift
// from producer emission as the contract evolves.
func parseNotice(m consume.Message) (deliver.DPONotice, bool) {
	payload, _ := m.Fields["payload"].(string)
	if payload == "" {
		return deliver.DPONotice{}, false
	}
	var ev incidents.GDPRDPONoticeRequiredV1
	if json.Unmarshal([]byte(payload), &ev) != nil {
		return deliver.DPONotice{}, false
	}
	if ev.Validate() != nil {
		return deliver.DPONotice{}, false
	}
	return deliver.DPONotice{
		IncidentID: ev.IncidentID, Subject: ev.Subject, Body: ev.Body, Deadline: ev.Deadline,
	}, true
}

// truncate caps s to n bytes WITHOUT splitting a multi-byte UTF-8 rune (a split rune
// would be invalid UTF-8 and pgx would reject the write).
func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	for n > 0 && !utf8.RuneStart(s[n]) {
		n--
	}
	return s[:n]
}

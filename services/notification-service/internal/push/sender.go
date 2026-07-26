package push

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	webpush "github.com/SherClockHolmes/webpush-go"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// VAPIDConfig is the server's Web Push identity. The private key comes from env and the service fails
// to start without it (platform infra — NEVER JWT_SECRET, §8-S2); the public key is served to the FE
// so a browser can subscribe. Subscriber is a mailto: contact required by the Web Push spec.
type VAPIDConfig struct {
	PublicKey  string
	PrivateKey string
	Subscriber string
}

// Configured reports whether a real VAPID keypair is present (both halves). When false the sender is
// a no-op — the platform can run without push configured (dev, or a deploy that hasn't set VAPID).
func (c VAPIDConfig) Configured() bool {
	return c.PublicKey != "" && c.PrivateKey != ""
}

// Sender delivers content-free Web Push messages, prunes dead endpoints, and never lets one bad
// device block the others.
type Sender struct {
	pool   *pgxpool.Pool
	vapid  VAPIDConfig
	logger *slog.Logger
}

func NewSender(pool *pgxpool.Pool, vapid VAPIDConfig, logger *slog.Logger) *Sender {
	if logger == nil {
		logger = slog.Default()
	}
	return &Sender{pool: pool, vapid: vapid, logger: logger}
}

type deviceRow struct {
	id       uuid.UUID
	endpoint string
	p256dh   string
	auth     string
}

// pushBody is the JSON the service worker receives. It embeds the CONTENT-FREE Payload plus a route
// key + opaque notification id for deep-linking on notificationclick (§8-S5) — neither carries content.
type pushBody struct {
	Payload
	Route          string `json:"route"`
	NotificationID string `json:"notification_id"`
}

// SendToUser pushes the content-free copy for `topic` to every device `userID` has subscribed. Dead
// subscriptions (404/410 Gone) are hard-deleted — the primary GC (§8-B3); transient failures
// (429/5xx / transport) bump fail_count for the stale sweep and are kept. Best-effort per device.
// A no-op (returns 0,0,nil) when VAPID isn't configured.
func (s *Sender) SendToUser(ctx context.Context, userID uuid.UUID, topic PushTopic, route, notificationID string) (sent, pruned int, err error) {
	if !s.vapid.Configured() {
		return 0, 0, nil
	}
	devices, err := s.loadDevices(ctx, userID)
	if err != nil {
		return 0, 0, err
	}
	body, _ := json.Marshal(pushBody{Payload: BuildPayload(topic), Route: route, NotificationID: notificationID})

	for _, d := range devices {
		// Bound EACH outbound send (cold-review HIGH-1 / DoS): webpush-go uses no default timeout, so
		// an un-timed context.Background() send to a slow/hung endpoint would block the goroutine and
		// leak an FD forever. Cap it.
		sendCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
		resp, sendErr := webpush.SendNotificationWithContext(sendCtx, body, &webpush.Subscription{
			Endpoint: d.endpoint,
			Keys:     webpush.Keys{P256dh: d.p256dh, Auth: d.auth},
		}, &webpush.Options{
			Subscriber:      s.vapid.Subscriber,
			VAPIDPublicKey:  s.vapid.PublicKey,
			VAPIDPrivateKey: s.vapid.PrivateKey,
			TTL:             86400,
		})
		if sendErr != nil {
			cancel()
			s.logger.Warn("push transport error", "err", sendErr, "sub", d.id)
			s.bumpFail(ctx, d.id)
			continue
		}
		status := resp.StatusCode
		_ = resp.Body.Close()
		cancel()
		switch {
		case status >= 200 && status < 300:
			sent++
			s.markSuccess(ctx, d.id)
		case status == 404 || status == 410:
			s.deleteByID(ctx, d.id) // Gone → prune (idempotent GC)
			pruned++
		default:
			s.bumpFail(ctx, d.id)
		}
	}
	return sent, pruned, nil
}

// MaybeSend is the ONE entry point both ingress paths (HTTP createNotification + the AMQP consumer)
// call after a notification row was actually inserted (exactly-once, §8-B4). It runs the FAIL-CLOSED
// gate (§8-H2) then delivers the content-free payload. No-op when VAPID is unconfigured. Best-effort:
// swallows errors (the in-app row already stands) but logs them.
func (s *Sender) MaybeSend(ctx context.Context, userID uuid.UUID, category, messageKey, route, notificationID string) {
	// This runs in a detached fire-and-forget goroutine OUTSIDE chi's request Recoverer, so a panic
	// here (a crafted key the webpush lib chokes on, a nil deref) would crash the whole service and
	// drop the in-app feed for everyone. Recover locally (cold-review MED-1).
	defer func() {
		if r := recover(); r != nil {
			s.logger.Error("push goroutine panic recovered", "panic", r, "user", userID)
		}
	}()
	if !s.vapid.Configured() {
		return
	}
	enabled, err := PushEnabled(ctx, s.pool, userID, category, messageKey)
	if err != nil {
		s.logger.Warn("push gate error — not pushing (fail closed)", "err", err, "user", userID)
		return
	}
	if !enabled {
		return // user muted this topic (or its default is off)
	}
	if _, _, sErr := s.SendToUser(ctx, userID, ResolveTopic(category, messageKey), route, notificationID); sErr != nil {
		s.logger.Warn("push send error", "err", sErr, "user", userID)
	}
}

func (s *Sender) loadDevices(ctx context.Context, userID uuid.UUID) ([]deviceRow, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE owner_user_id=$1`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []deviceRow
	for rows.Next() {
		var d deviceRow
		if err := rows.Scan(&d.id, &d.endpoint, &d.p256dh, &d.auth); err != nil {
			continue
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

func (s *Sender) markSuccess(ctx context.Context, id uuid.UUID) {
	_, _ = s.pool.Exec(ctx, `UPDATE push_subscriptions SET last_success_at=now(), fail_count=0 WHERE id=$1`, id)
}
func (s *Sender) bumpFail(ctx context.Context, id uuid.UUID) {
	_, _ = s.pool.Exec(ctx, `UPDATE push_subscriptions SET fail_count=fail_count+1 WHERE id=$1`, id)
}
func (s *Sender) deleteByID(ctx context.Context, id uuid.UUID) {
	_, _ = s.pool.Exec(ctx, `DELETE FROM push_subscriptions WHERE id=$1`, id)
}

// SweepStale hard-deletes subscriptions that have been failing for a while (fail_count over the
// threshold) — the secondary GC behind the 404/410 prune, for endpoints that go dark without a Gone.
func (s *Sender) SweepStale(ctx context.Context, failThreshold int) (int64, error) {
	tag, err := s.pool.Exec(ctx, `DELETE FROM push_subscriptions WHERE fail_count >= $1`, failThreshold)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

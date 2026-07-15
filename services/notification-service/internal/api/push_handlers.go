package api

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/google/uuid"

	"github.com/loreweave/notification-service/internal/push"
)

// M5 (D-MOB-4) — Web Push HTTP surface. Owner is always the JWT `sub` (§8-H4), never a body field.

// pushSubscriptionBody mirrors the browser's PushSubscription.toJSON(): an endpoint + the recipient
// public keys used to encrypt the payload. keys are PUBLIC (not secrets).
type pushSubscriptionBody struct {
	Endpoint string `json:"endpoint"`
	Keys     struct {
		P256dh string `json:"p256dh"`
		Auth   string `json:"auth"`
	} `json:"keys"`
}

func (s *Server) registerPushSubscription(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "NOTIF_AUTH_ERROR", "authentication required")
		return
	}
	var body pushSubscriptionBody
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "invalid body")
		return
	}
	if body.Endpoint == "" || body.Keys.P256dh == "" || body.Keys.Auth == "" {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "endpoint + keys required")
		return
	}
	// SSRF guard (cold-review HIGH-1): reject a non-https or private/internal endpoint before we
	// ever store (and later POST to) it.
	if err := push.ValidatePushEndpoint(body.Endpoint); err != nil {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "invalid push endpoint")
		return
	}
	if err := push.UpsertSubscription(r.Context(), s.pool, userID, body.Endpoint, body.Keys.P256dh, body.Keys.Auth, r.UserAgent()); err != nil {
		writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "register failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"registered": true})
}

func (s *Server) deletePushSubscription(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "NOTIF_AUTH_ERROR", "authentication required")
		return
	}
	// endpoint via ?endpoint= (the FE sends it on sign-out before clearing the JWT).
	endpoint := r.URL.Query().Get("endpoint")
	if endpoint == "" {
		// also accept a JSON body {endpoint}
		var body struct {
			Endpoint string `json:"endpoint"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		endpoint = body.Endpoint
	}
	if endpoint == "" {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "endpoint required")
		return
	}
	deleted, err := push.DeleteSubscription(r.Context(), s.pool, userID, endpoint)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "delete failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"deleted": deleted})
}

func (s *Server) getVAPIDPublicKey(w http.ResponseWriter, r *http.Request) {
	// Public by design (needs no auth). Empty when push isn't configured — the FE reads that as
	// "push unavailable" and falls back to the in-app feed (§8-S3).
	writeJSON(w, http.StatusOK, map[string]any{
		"public_key": s.vapid.PublicKey,
		"configured": s.vapid.Configured(),
	})
}

// getPushPreferences returns the EFFECTIVE per-topic push toggle for the user: the topic's code
// default overlaid by any explicit row. Every consumer inherits the same defaults (Settings-Boundary
// "effective value + source"). No secret hidden default.
func (s *Server) getPushPreferences(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "NOTIF_AUTH_ERROR", "authentication required")
		return
	}
	// Start from the code defaults, then apply the user's explicit rows.
	effective := map[string]bool{}
	source := map[string]string{}
	for _, t := range push.AllTopics {
		effective[string(t)] = push.TopicDefaults[t]
		source[string(t)] = "default"
	}
	rows, err := s.pool.Query(r.Context(), `SELECT push_topic, push_enabled FROM push_preferences WHERE user_id=$1`, userID)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var topic string
			var enabled bool
			if rows.Scan(&topic, &enabled) == nil {
				if _, known := effective[topic]; known {
					effective[topic] = enabled
					source[topic] = "user"
				}
			}
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"topics": effective, "source": source})
}

func (s *Server) setPushPreference(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "NOTIF_AUTH_ERROR", "authentication required")
		return
	}
	var body struct {
		PushTopic   string `json:"push_topic"`
		PushEnabled *bool  `json:"push_enabled"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.PushEnabled == nil {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "push_topic + push_enabled required")
		return
	}
	// Closed-set enum validation on write (Settings-Boundary / Frontend-Tool-Contract discipline).
	if !push.ValidTopic(body.PushTopic) {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "unknown push_topic")
		return
	}
	_, err := s.pool.Exec(r.Context(), `
INSERT INTO push_preferences (user_id, push_topic, push_enabled, updated_at)
VALUES ($1, $2, $3, now())
ON CONFLICT (user_id, push_topic) DO UPDATE SET push_enabled = EXCLUDED.push_enabled, updated_at = now()
`, userID, body.PushTopic, *body.PushEnabled)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "save failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"push_topic": body.PushTopic, "push_enabled": *body.PushEnabled})
}

// pushForNotification is the exactly-once hook the ingress paths call AFTER a notification row was
// actually INSERTED (RowsAffected==1, §8-B4). It resolves the topic, checks the FAIL-CLOSED push gate
// (§8-H2), and delegates to the sender (content-free payload). Best-effort: a push failure never
// affects the stored in-app row. `route` + `notificationID` ride as deep-link data (no content).
func (s *Server) pushForNotification(userID uuid.UUID, category, messageKey, route, notificationID string) {
	// Detached context so the push isn't cancelled when the triggering HTTP request completes
	// (best-effort, out-of-band). MaybeSend runs the fail-closed gate + content-free send.
	s.sender.MaybeSend(context.Background(), userID, category, messageKey, route, notificationID)
}

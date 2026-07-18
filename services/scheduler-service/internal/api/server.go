// Package api is scheduler-service's internal HTTP surface (X-Internal-Token, service-to-service).
// The gateway (behind the user's JWT) calls it when a user toggles a schedule (WS-3.2 opt-in path).
package api

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/scheduler-service/internal/scheduler"
)

type Server struct {
	pool          *pgxpool.Pool
	internalToken string
	now           func() time.Time // injectable for tests
}

func NewServer(pool *pgxpool.Pool, internalToken string) *Server {
	return &Server{pool: pool, internalToken: internalToken, now: func() time.Time { return time.Now().UTC() }}
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Get("/health", s.health)
	r.Group(func(r chi.Router) {
		r.Use(s.requireInternalToken)
		r.Get("/internal/schedules", s.listSchedules)
		r.Put("/internal/schedules", s.upsertSchedule)
		r.Post("/internal/away", s.addAway)
	})
	return r
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	if err := s.pool.Ping(r.Context()); err != nil {
		http.Error(w, "db down", http.StatusServiceUnavailable)
		return
	}
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

func (s *Server) requireInternalToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.internalToken == "" || r.Header.Get("X-Internal-Token") != s.internalToken {
			writeErr(w, http.StatusUnauthorized, "unauthorized")
			return
		}
		next.ServeHTTP(w, r)
	})
}

type upsertScheduleReq struct {
	UserID        uuid.UUID `json:"user_id"`
	JobKind       string    `json:"job_kind"`       // 'eod_distill' | 'weekly_rollup' | ...
	Cadence       string    `json:"cadence"`        // 'daily' | 'weekly'
	FireLocalTime string    `json:"fire_local_time"` // HH:MM (default 21:00)
	Timezone      string    `json:"timezone"`        // IANA; "" → UTC
	Enabled       bool      `json:"enabled"`
}

// upsertSchedule — PUT /internal/schedules. The opt-in write path (P3-D2). Creates/updates the user's
// schedule and returns the armed next_fire_at (when enabled).
func (s *Server) upsertSchedule(w http.ResponseWriter, r *http.Request) {
	var req upsertScheduleReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid body")
		return
	}
	if req.UserID == uuid.Nil || req.JobKind == "" {
		writeErr(w, http.StatusBadRequest, "user_id and job_kind are required")
		return
	}
	// L1 — closed-set job_kind (the driver only knows these; a typo would breaker-loop a row forever).
	switch req.JobKind {
	// C7 (SD-C7) — weekly_reflection (WS-3.8: the weekly reflection delivered on a schedule) and
	// proactive_nudge (WS-3.5: an assistant-initiated turn) join the closed set.
	case "eod_distill", "weekly_rollup", "nudge", "weekly_reflection", "proactive_nudge":
	default:
		writeErr(w, http.StatusBadRequest, "job_kind must be eod_distill|weekly_rollup|nudge|weekly_reflection|proactive_nudge")
		return
	}
	if req.Cadence == "" {
		req.Cadence = "daily"
	}
	if req.Cadence != "daily" && req.Cadence != "weekly" {
		writeErr(w, http.StatusBadRequest, "cadence must be daily|weekly")
		return
	}
	if req.FireLocalTime == "" {
		req.FireLocalTime = "21:00"
	}
	next, err := scheduler.UpsertSchedule(
		r.Context(), s.pool, req.UserID, req.JobKind, req.Cadence, req.FireLocalTime, req.Timezone,
		req.Enabled, s.now(),
	)
	if err != nil {
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}
	out := map[string]any{"enabled": req.Enabled, "job_kind": req.JobKind}
	if req.Enabled {
		out["next_fire_at"] = next.Format(time.RFC3339)
	}
	writeJSON(w, http.StatusOK, out)
}

// listSchedules — GET /internal/schedules?user_id=<uuid> (A3). Returns every schedule row the user has,
// so the gateway (behind the JWT) can render the autonomous-layer settings toggles with their effective
// enabled state. Owner-scoped by the user_id query param (the gateway binds it from the JWT sub).
func (s *Server) listSchedules(w http.ResponseWriter, r *http.Request) {
	uid, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil || uid == uuid.Nil {
		writeErr(w, http.StatusBadRequest, "user_id is required")
		return
	}
	rows, err := scheduler.ListSchedules(r.Context(), s.pool, uid)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "failed to list schedules")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"schedules": rows})
}

type addAwayReq struct {
	UserID   uuid.UUID `json:"user_id"`
	StartsOn string    `json:"starts_on"` // YYYY-MM-DD
	EndsOn   string    `json:"ends_on"`   // YYYY-MM-DD
}

// addAway — POST /internal/away (WS-3.4). Records a declared away span so nudges (and P5's gap
// detector) skip those days. The gateway calls it behind the user's JWT.
func (s *Server) addAway(w http.ResponseWriter, r *http.Request) {
	var req addAwayReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid body")
		return
	}
	start, err1 := time.Parse("2006-01-02", req.StartsOn)
	end, err2 := time.Parse("2006-01-02", req.EndsOn)
	if req.UserID == uuid.Nil || err1 != nil || err2 != nil {
		writeErr(w, http.StatusBadRequest, "user_id + starts_on/ends_on (YYYY-MM-DD) required")
		return
	}
	if end.Before(start) {
		writeErr(w, http.StatusBadRequest, "ends_on must be >= starts_on")
		return
	}
	if err := scheduler.AddAwayPeriod(r.Context(), s.pool, req.UserID, start, end); err != nil {
		writeErr(w, http.StatusInternalServerError, "failed to record away period")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"away": true, "starts_on": req.StartsOn, "ends_on": req.EndsOn})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

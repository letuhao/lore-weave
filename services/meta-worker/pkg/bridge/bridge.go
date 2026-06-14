// Package bridge is the W1.5 Rust→Go meta-write bridge: a SCOPED, internal HTTP
// surface on meta-worker that lets the Rust provisioner (world-service) perform
// the two meta writes it cannot do directly (every reality_registry write must
// go through Go MetaWrite so the meta_write_audit row lands in the same TX — I8).
//
// SCOPED, not a raw MetaWrite passthrough (plan review #1/#5): only two narrow
// operations, and the SERVER builds the intent, so the blast radius is the
// provisioner's own table:
//
//	POST /internal/provisioner/register-reality  → reality_registry INSERT
//	    (status forced to 'provisioning'; idempotent on reality_id PK conflict).
//	POST /internal/provisioner/transition        → AttemptStateTransition(reality)
//	    (CAS; stale FromState → 409 so the caller surfaces, never blind-retries).
//
// Security (review #5): fail-closed service token (the server REFUSES to start
// without one), constant-time compare, and one service_to_service_audit row per
// call (ok|deny|error). The TOKEN is the code-enforced control. The listener is
// internal — it DEFAULTS to a loopback bind, but "internal-only" is not itself
// code-enforced (an operator can set any METAWORKER_BRIDGE_ADDR); prod relies on
// the private-address default + network policy (review #8). It is NEVER exposed
// through the gateway.
//
// Collaborators (Registrar, AuditSink) are interfaces so the HTTP/auth/idempotency
// logic is unit-tested without a DB; the production impls wrap contracts/meta.
package bridge

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
)

// ErrAlreadyRegistered is returned by Registrar.Register when the reality_id
// already exists — the bridge treats it as idempotent SUCCESS (a retried
// register after a network blip must not 500).
//
// Idempotency assumes IDENTICAL retries (review #9): a retry carrying a
// DIFFERENT db_host/db_name for an already-registered reality_id still returns
// 200 — the existing row stands and is NOT diffed against the new payload. The
// single V1 caller (the provisioner) always retries the same intent, so this is
// safe; a future multi-caller surface that needs conflict detection must add an
// existing-row equality check.
var ErrAlreadyRegistered = errors.New("bridge: reality already registered")

// Registrar performs the two scoped meta writes.
type Registrar interface {
	Register(ctx context.Context, r RegisterReq) error
	Transition(ctx context.Context, t TransitionReq) (newState string, err error)
}

// AuditSink records one service_to_service_audit row per bridge call.
type AuditSink interface {
	Record(ctx context.Context, ev AuditEvent) error
}

// AuditEvent is one inter-service RPC audit row.
type AuditEvent struct {
	Caller  string
	RPC     string
	Result  string // ok | deny | error
	Latency time.Duration
}

// RegisterReq is the narrow register-reality payload (the server adds
// status='provisioning' + the session caps; the client cannot set them).
type RegisterReq struct {
	RealityID    string `json:"reality_id"`
	DBHost       string `json:"db_host"`
	DBName       string `json:"db_name"`
	Locale       string `json:"locale"`
	DeployCohort int    `json:"deploy_cohort"`
	Reason       string `json:"reason"`
}

// TransitionReq is the reality transition payload.
type TransitionReq struct {
	RealityID string         `json:"reality_id"`
	From      string         `json:"from"`
	To        string         `json:"to"`
	Reason    string         `json:"reason"`
	Payload   map[string]any `json:"payload,omitempty"`
}

// Server is the bridge HTTP surface.
type Server struct {
	reg    Registrar
	audit  AuditSink
	token  string
	caller string
	now    func() time.Time
}

// New builds the bridge. Fail-closed: an empty token is refused (the whole
// point of the internal boundary is that a write needs the secret).
func New(reg Registrar, audit AuditSink, token, caller string) (*Server, error) {
	if token == "" {
		return nil, errors.New("bridge: service token required (fail-closed)")
	}
	if reg == nil || audit == nil {
		return nil, errors.New("bridge: reg and audit required")
	}
	if caller == "" {
		caller = "world-service"
	}
	return &Server{reg: reg, audit: audit, token: token, caller: caller, now: time.Now}, nil
}

// Handler returns the routed, auth-wrapped mux.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /internal/provisioner/register-reality", s.guarded("register-reality", s.handleRegister))
	mux.HandleFunc("POST /internal/provisioner/transition", s.guarded("transition", s.handleTransition))
	return mux
}

// guarded enforces the token (fail-closed) + audits every call.
func (s *Server) guarded(rpc string, h func(http.ResponseWriter, *http.Request) (int, error)) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		start := s.now()
		if !s.authOK(r) {
			s.record(r.Context(), rpc, "deny", s.now().Sub(start))
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			return
		}
		code, err := h(w, r)
		result := "ok"
		if err != nil || code >= 500 {
			result = "error"
		}
		s.record(r.Context(), rpc, result, s.now().Sub(start))
	}
}

func (s *Server) authOK(r *http.Request) bool {
	tok := r.Header.Get("X-Service-Token")
	if tok == "" {
		// Also accept Authorization: Bearer <token>.
		if a := r.Header.Get("Authorization"); len(a) > 7 && a[:7] == "Bearer " {
			tok = a[7:]
		}
	}
	return tok != "" && subtle.ConstantTimeCompare([]byte(tok), []byte(s.token)) == 1
}

func (s *Server) record(ctx context.Context, rpc, result string, latency time.Duration) {
	_ = s.audit.Record(ctx, AuditEvent{Caller: s.caller, RPC: rpc, Result: result, Latency: latency})
}

func (s *Server) handleRegister(w http.ResponseWriter, r *http.Request) (int, error) {
	var req RegisterReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "bad json: " + err.Error()})
		return http.StatusBadRequest, nil
	}
	if req.RealityID == "" || req.DBHost == "" || req.DBName == "" || req.Locale == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "reality_id, db_host, db_name, locale required"})
		return http.StatusBadRequest, nil
	}
	err := s.reg.Register(r.Context(), req)
	switch {
	case errors.Is(err, ErrAlreadyRegistered):
		// Idempotent: a retried register is success, not a conflict.
		writeJSON(w, http.StatusOK, map[string]string{"status": "already_registered"})
		return http.StatusOK, nil
	case err != nil:
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return http.StatusInternalServerError, err
	default:
		writeJSON(w, http.StatusCreated, map[string]string{"status": "registered"})
		return http.StatusCreated, nil
	}
}

func (s *Server) handleTransition(w http.ResponseWriter, r *http.Request) (int, error) {
	var req TransitionReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "bad json: " + err.Error()})
		return http.StatusBadRequest, nil
	}
	if req.RealityID == "" || req.From == "" || req.To == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "reality_id, from, to required"})
		return http.StatusBadRequest, nil
	}
	newState, err := s.reg.Transition(r.Context(), req)
	switch {
	case errors.Is(err, meta.ErrConcurrentStateTransition):
		// Stale FromState — the caller must reload, NOT blind-retry.
		writeJSON(w, http.StatusConflict, map[string]string{"error": "concurrent_state_transition"})
		return http.StatusConflict, nil
	case errors.Is(err, meta.ErrInvalidTransition):
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_transition"})
		return http.StatusBadRequest, nil
	case err != nil:
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return http.StatusInternalServerError, err
	default:
		writeJSON(w, http.StatusOK, map[string]string{"new_state": newState})
		return http.StatusOK, nil
	}
}

func writeJSON(w http.ResponseWriter, code int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(body)
}

// ─── production collaborators ────────────────────────────────────────────────

// WorldServiceActorID is the fixed service-principal UUID recorded as the audit
// Actor.ID for the world-service caller. The meta audit tables key actor_id as a
// UUID (lifecycle_transition_audit.actor_id is UUID), so a human label like
// "world-service" can't be the Actor.ID — it is the s2s caller_service label.
const WorldServiceActorID = "00000000-0000-0000-0000-0000000000a1"

// MetaRegistrar builds the scoped intents and runs them through the canonical
// meta.Config (allowlist + scrubber + clock + uuidgen — review #4), with the
// REAL caller as the audit Actor (ActorType=service).
type MetaRegistrar struct {
	Cfg    *meta.Config
	Caller string // the caller's service-principal UUID (audit Actor.ID)
}

// Register INSERTs the reality_registry row via MetaWrite (I8). A reality_id PK
// conflict maps to ErrAlreadyRegistered (idempotent retry).
func (m MetaRegistrar) Register(ctx context.Context, r RegisterReq) error {
	rid, err := uuid.Parse(r.RealityID)
	if err != nil {
		return fmt.Errorf("register: reality_id not a uuid: %w", err)
	}
	intent := meta.MetaWriteIntent{
		Table:     "reality_registry",
		Operation: meta.OpInsert,
		PK:        map[string]any{"reality_id": rid},
		NewValues: map[string]any{
			"db_host":           r.DBHost,
			"db_name":           r.DBName,
			"status":            "provisioning", // SERVER-set; the client cannot choose
			"locale":            r.Locale,
			"deploy_cohort":     r.DeployCohort,
			"session_max_pcs":   10,
			"session_max_npcs":  10,
			"session_max_total": 20,
		},
		// ActorSystem (not Service): the lifecycle_transition_audit.actor_type
		// CHECK allows only owner/admin/system/cron, and the provisioner is a
		// system-initiated process. The real caller is the s2s caller_service
		// label + the world-service principal UUID in Actor.ID.
		Actor:  meta.Actor{Type: meta.ActorSystem, ID: m.Caller},
		Reason: orDefault(r.Reason, "provision: register reality"),
	}
	if _, err := meta.MetaWrite(ctx, m.Cfg, intent); err != nil {
		if isUniqueViolation(err) {
			return ErrAlreadyRegistered
		}
		return err
	}
	return nil
}

// Transition runs a CAS reality transition via AttemptStateTransition.
func (m MetaRegistrar) Transition(ctx context.Context, t TransitionReq) (string, error) {
	res, err := meta.AttemptStateTransition(ctx, m.Cfg, meta.TransitionRequest{
		ResourceType: "reality",
		ResourceID:   t.RealityID,
		FromState:    t.From,
		ToState:      t.To,
		Reason:       orDefault(t.Reason, "provision: transition"),
		Actor:        meta.Actor{Type: meta.ActorSystem, ID: m.Caller},
		Payload:      t.Payload,
	})
	if err != nil {
		return "", err
	}
	return res.NewState, nil
}

func isUniqueViolation(err error) bool {
	var pg *pgconn.PgError
	return errors.As(err, &pg) && pg.Code == "23505"
}

func orDefault(s, def string) string {
	if s == "" {
		return def
	}
	return s
}

// PgAuditSink writes service_to_service_audit rows directly (audit of the RPC
// call itself — distinct from the meta_write_audit the data write produces).
type PgAuditSink struct {
	Pool   *pgxpool.Pool
	Callee string // "meta-worker"
	NowNs  func() int64
}

// Record inserts one s2s audit row.
func (a PgAuditSink) Record(ctx context.Context, ev AuditEvent) error {
	nowNs := time.Now().UnixNano
	if a.NowNs != nil {
		nowNs = a.NowNs
	}
	callee := a.Callee
	if callee == "" {
		callee = "meta-worker"
	}
	_, err := a.Pool.Exec(ctx,
		`INSERT INTO service_to_service_audit
		   (audit_id, caller_service, callee_service, rpc_name, principal_mode,
		    result, latency_ms, created_at_nanos)
		 VALUES ($1, $2, $3, $4, 'system_only', $5, $6, $7)`,
		uuid.New(), ev.Caller, callee, ev.RPC, ev.Result,
		ev.Latency.Milliseconds(), nowNs())
	return err
}

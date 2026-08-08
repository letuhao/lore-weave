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
	"sort"
	"strings"
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
	// RecordOrphans replaces the finding set for one shard (W5-REMEDIATE).
	RecordOrphans(ctx context.Context, r RecordOrphansReq) (recorded, cleared int, err error)
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

	// OwnerUserID is the user who owns this reality (W6). EMPTY means the
	// platform owns it, which the server records as owner_kind='system'.
	//
	// The tier is DERIVED here rather than accepted from the client: a client
	// that could send owner_kind independently could send
	// ('system', <a user id>) or ('user', NULL), and the table's CHECK
	// constraints would reject the write at the very end of provisioning
	// instead of at its edge. One field in, one consistent pair out.
	OwnerUserID string `json:"owner_user_id,omitempty"`
}

// OrphanFinding is one row of a scan result (W5-REMEDIATE).
//
// `RealityID` is empty EXACTLY for an untracked database — a `lw_reality_*`
// database no registry row claims, which is the class that matters most because
// capacity counts registry rows and so cannot see it. The table's CHECK
// constraints enforce that correspondence; `deriveFindingReality` below refuses
// to send a payload that would violate them, so the database is not the first
// thing to notice a malformed finding.
type OrphanFinding struct {
	DBName       string         `json:"db_name"`
	FindingClass string         `json:"finding_class"`
	RealityID    string         `json:"reality_id,omitempty"`
	Detail       map[string]any `json:"detail,omitempty"`
}

// RecordOrphansReq replaces the finding set for one shard.
//
// WHOLE-SHARD REPLACE, not append: `orphan_scan_finding` is STATE ("what is
// wrong now"), so a finding that has cleared must disappear. Sending the full
// set and letting the server reconcile is what makes a cleared finding
// impossible to leave behind — an append-only protocol would need the client to
// remember what it reported last time, and a reaper that forgets grows a list
// of ghosts.
type RecordOrphansReq struct {
	ShardHost string          `json:"shard_host"`
	Findings  []OrphanFinding `json:"findings"`
	Reason    string          `json:"reason"`
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
	mux.HandleFunc("POST /internal/provisioner/record-orphans", s.guarded("record-orphans", s.handleRecordOrphans))
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

func (s *Server) handleRecordOrphans(w http.ResponseWriter, r *http.Request) (int, error) {
	var req RecordOrphansReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "bad json: " + err.Error()})
		return http.StatusBadRequest, nil
	}
	if strings.TrimSpace(req.ShardHost) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "shard_host required"})
		return http.StatusBadRequest, nil
	}
	// An EMPTY findings list is valid and meaningful: it says "this shard is
	// clean", and the reconcile below then clears every stale row. Rejecting it
	// would make a shard that just became healthy keep its old findings forever.
	recorded, cleared, err := s.reg.RecordOrphans(r.Context(), req)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return http.StatusInternalServerError, err
	}
	writeJSON(w, http.StatusOK, map[string]int{"recorded": recorded, "cleared": cleared})
	return http.StatusOK, nil
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
	// Pool is a READ handle, used only to decide insert-vs-update and to find
	// findings that have cleared. Every WRITE still goes through MetaWrite;
	// contracts/meta exposes no upsert (OpInsert/OpUpdate/OpDelete only), so
	// the reconcile has to know what is already there.
	Pool *pgxpool.Pool
}

// deriveOwner turns the ONE field a client may send into the (owner_kind,
// owner_user_id) pair `reality_registry` requires — W6's tenancy tier.
//
// Extracted and exported-to-tests because a cold-start review found this
// decision — the single place `owner_kind` is chosen — had **no test and no
// bite**: every `TestRegister*` routes through a fake Registrar and exercises
// the HTTP handler, so replacing the whole derivation with `ownerKind := "user"`
// left the entire Go suite green. The four bites that did exist all covered the
// argv TRANSPORT, never the DECISION.
//
// Returns `any` for the id so an absent owner becomes a real SQL NULL.
func deriveOwner(raw string) (kind string, id any, err error) {
	s := strings.TrimSpace(raw)
	if s == "" {
		// Platform-owned. A REAL category, not "unknown".
		return "system", nil, nil
	}
	oid, perr := uuid.Parse(s)
	if perr != nil {
		return "", nil, fmt.Errorf("register: owner_user_id not a uuid: %w", perr)
	}
	// The nil UUID is not an owner. Accepting it wrote ('user', 00000000-…) —
	// a reality owned by a user that cannot exist, which satisfies every CHECK
	// on the table and sits in the partial owner index. The same discipline is
	// already applied to reality_id (provision_reality.go rejects uuid.Nil);
	// it was simply not carried across to the new id column.
	//
	// It is REFUSED rather than coerced to system-owned: an operator who typed
	// an owner meant to set one, and silently producing a platform-owned
	// reality while reporting success is the worse of the two failures.
	if oid == uuid.Nil {
		return "", nil, fmt.Errorf(
			"register: owner_user_id must not be the nil UUID (omit the field for a platform-owned reality)")
	}
	return "user", oid, nil
}

// Register INSERTs the reality_registry row via MetaWrite (I8). A reality_id PK
// conflict maps to ErrAlreadyRegistered (idempotent retry).
func (m MetaRegistrar) Register(ctx context.Context, r RegisterReq) error {
	rid, err := uuid.Parse(r.RealityID)
	if err != nil {
		return fmt.Errorf("register: reality_id not a uuid: %w", err)
	}
	// W6 — ownership. The tier is derived from whether an owner was supplied,
	// so the pair written is consistent by construction and the table's
	// owner_system_null / owner_user_set CHECKs can never be the thing that
	// discovers a mistake.
	ownerKind, ownerUserID, err := deriveOwner(r.OwnerUserID)
	if err != nil {
		return err
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
			"owner_kind":        ownerKind,
			"owner_user_id":     ownerUserID,
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

// RecordOrphans replaces the finding set for one shard (W5-REMEDIATE).
//
// RECONCILE, not append. `orphan_scan_finding` is state, so this UPSERTs every
// finding the scanner reported and DELETEs every row for the shard it did not.
// A finding that has cleared must vanish, or the operator worklist becomes a
// list of ghosts and stops being read — the failure mode that makes a detector
// worthless faster than not having one.
//
// `first_seen_at` survives an upsert (only `last_seen_at` and `detail` move), so
// "this has been broken for six days" stays answerable. That is the number an
// operator actually triages on.
//
// Every write goes through MetaWrite so each lands its same-TX `meta_write_audit`
// row (I8). The scanner cannot write this table directly — the
// meta-write-discipline lint forbids any INSERT/UPDATE/DELETE on a meta table
// outside contracts/meta, which is exactly why this endpoint exists.
func (m MetaRegistrar) RecordOrphans(ctx context.Context, r RecordOrphansReq) (int, int, error) {
	shard := strings.TrimSpace(r.ShardHost)
	if shard == "" {
		return 0, 0, fmt.Errorf("record-orphans: shard_host required")
	}

	existing, err := m.shardFindings(ctx, shard)
	if err != nil {
		return 0, 0, err
	}

	reported := make(map[string]bool, len(r.Findings))
	intents := make([]meta.MetaWriteIntent, 0, len(r.Findings))
	for _, f := range r.Findings {
		name := strings.TrimSpace(f.DBName)
		if name == "" {
			return 0, 0, fmt.Errorf("record-orphans: a finding has no db_name")
		}
		rid, derr := deriveFindingReality(f.FindingClass, f.RealityID)
		if derr != nil {
			return 0, 0, derr
		}
		reported[name] = true
		detail := f.Detail
		if detail == nil {
			detail = map[string]any{}
		}
		vals := map[string]any{
			"reality_id":    rid,
			"finding_class": f.FindingClass,
			"detail":        detail,
			// Written on EVERY scan, insert or update. The first version left
			// this to the column DEFAULT, so it was set once and never moved —
			// the column said "last confirmed at" and meant "first seen at",
			// and an operator reading it would believe a finding was stale when
			// the scanner had just re-confirmed it a minute ago. Caught by
			// reading the readback rather than the exit code.
			"last_seen_at": time.Unix(0, m.Cfg.Clock.NowUnixNano()).UTC(),
		}
		op := meta.OpInsert
		if existing[name] {
			// UPDATE, so `first_seen_at` is untouched: "this has been broken
			// for six days" is the number an operator triages on, and an
			// insert-every-scan would reset it to now on every tick.
			op = meta.OpUpdate
		} else {
			vals["shard_host"] = shard
			vals["db_name"] = name
		}
		intents = append(intents, meta.MetaWriteIntent{
			Table:     "orphan_scan_finding",
			Operation: op,
			PK:        map[string]any{"shard_host": shard, "db_name": name},
			NewValues: vals,
			Actor:     meta.Actor{Type: meta.ActorSystem, ID: m.Caller},
			Reason:    orDefault(r.Reason, "orphan scan: record finding"),
		})
	}

	// Clear what the scanner no longer reports.
	var stale []string
	for name := range existing {
		if !reported[name] {
			stale = append(stale, name)
		}
	}
	sort.Strings(stale) // deterministic intent order
	for _, name := range stale {
		intents = append(intents, meta.MetaWriteIntent{
			Table:     "orphan_scan_finding",
			Operation: meta.OpDelete,
			PK:        map[string]any{"shard_host": shard, "db_name": name},
			Actor:     meta.Actor{Type: meta.ActorSystem, ID: m.Caller},
			Reason:    orDefault(r.Reason, "orphan scan: finding cleared"),
		})
	}

	if len(intents) == 0 {
		return 0, 0, nil
	}
	if _, werr := meta.MetaWriteBatch(ctx, m.Cfg, intents); werr != nil {
		return 0, 0, fmt.Errorf("record-orphans: %w", werr)
	}
	return len(r.Findings), len(stale), nil
}

// deriveFindingReality turns (class, id) into the reality_id column value,
// REFUSING any pair the table's CHECK constraints would reject.
//
// The correspondence is the point of the class: an untracked database is one no
// registry row claims, so it has no reality; every other class names a row and
// must carry its id. Validating here means a malformed finding fails at the
// edge with a sentence, rather than deep inside a MetaWriteBatch with a
// constraint name — the same reason `deriveOwner` exists one function up.
func deriveFindingReality(class, rawID string) (any, error) {
	const untracked = "orphan_untracked_database"
	id := strings.TrimSpace(rawID)
	if class == untracked {
		if id != "" {
			return nil, fmt.Errorf(
				"record-orphans: %s carries reality_id %q, but an untracked database is by "+
					"definition one no registry row claims", untracked, id)
		}
		return nil, nil
	}
	if id == "" {
		return nil, fmt.Errorf("record-orphans: finding_class %q requires a reality_id", class)
	}
	oid, err := uuid.Parse(id)
	if err != nil {
		return nil, fmt.Errorf("record-orphans: reality_id %q is not a uuid: %w", id, err)
	}
	if oid == uuid.Nil {
		return nil, fmt.Errorf("record-orphans: reality_id must not be the nil UUID")
	}
	return oid, nil
}

// shardFindings is the set of db_names currently recorded for the shard.
func (m MetaRegistrar) shardFindings(ctx context.Context, shard string) (map[string]bool, error) {
	if m.Pool == nil {
		return nil, fmt.Errorf("record-orphans: no read pool configured")
	}
	rows, err := m.Pool.Query(ctx,
		`SELECT db_name FROM orphan_scan_finding WHERE shard_host = $1`, shard)
	if err != nil {
		return nil, fmt.Errorf("record-orphans: read existing findings: %w", err)
	}
	defer rows.Close()
	out := map[string]bool{}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, fmt.Errorf("record-orphans: scan existing finding: %w", err)
		}
		out[name] = true
	}
	return out, rows.Err()
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

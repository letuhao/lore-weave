package bridge

// Actor-control grant/revoke — the WRITER `actor_control_binding` never had.
//
// Migration 034 created the table, `contracts/meta/events_allowlist.yaml`
// declared its three events, and the GDPR erasure cascade read it. **Nothing
// ever wrote it.** The only INSERT in the tree was a test fixture, so the table
// was empty by construction — the same state 035 recorded about the table 034
// replaced, and the reason that one was deleted rather than kept.
//
// SCOPED, like everything else on this bridge: two narrow operations whose
// intent the SERVER builds. The client sends three uuids and a reason; it
// cannot choose the table, the operation, the timestamps, or the audit actor.
//
// ── WHY GRANT AND REVOKE ARE NOT SYMMETRIC ──────────────────────────────────
//
// A grant is an INSERT of a new row; a revoke is an UPDATE of the live one. That
// asymmetry is not incidental — it is what makes the sealed event mapping
// truthful (INSERT -> actor.control.granted, UPDATE -> actor.control.revoked),
// and it is why migration 041 had to replace 034's primary key: under
// `PK (reality_id, actor_id)` a revoked row occupied the slot forever, so a
// handoff could only be an in-place UPDATE, which would have emitted "revoked"
// for a grant. See `docs/plans/2026-08-14-player-control-RUN-STATE.md` §P1a.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/meta"
)

// ErrActorAlreadyDriven — a DIFFERENT user already holds the live binding.
//
// A 409 and never an idempotent 200. `register-reality` treats a retry as
// success because a retried provision is the same intent; this is not the same
// intent, it is a second principal claiming a subject someone else holds — the
// confused-deputy state migration 034 exists to make unrepresentable. Answering
// 200 here would make the table's guarantee invisible to the caller.
var ErrActorAlreadyDriven = errors.New("bridge: actor already driven by another user")

// ErrAlreadyGranted — the SAME user already holds the live binding. Idempotent
// success: a retried grant carries the identical intent.
var ErrAlreadyGranted = errors.New("bridge: actor already granted to this user")

// ErrNoLiveBinding — revoke found nothing live for (reality, actor).
var ErrNoLiveBinding = errors.New("bridge: no live binding")

// ErrControlCASMismatch — the caller named the user it expected to revoke and
// somebody else holds the binding now.
//
// Mirrors `TransitionReq`'s stale-FromState discipline: a caller working from a
// stale read must SURFACE, never blind-retry. Without it, revoking "the driver
// of actor X" would silently remove whoever happens to hold it — including a
// player who took over one second ago.
var ErrControlCASMismatch = errors.New("bridge: expected_user_ref_id does not hold the live binding")

// GrantControlReq — give this human control of this actor in this reality.
type GrantControlReq struct {
	UserRefID string `json:"user_ref_id"`
	RealityID string `json:"reality_id"`
	ActorID   string `json:"actor_id"`
	Reason    string `json:"reason"`
}

// RevokeControlReq — end the live binding for (reality, actor).
//
// Deliberately keyed by the ACTOR and not by the user: the invariant is "one
// live driver per actor", so the actor is what names the row. ExpectedUserRefID
// is the optional CAS.
type RevokeControlReq struct {
	RealityID string `json:"reality_id"`
	ActorID   string `json:"actor_id"`
	// Optional. When set, the revoke applies only if this user still holds the
	// binding; otherwise ErrControlCASMismatch. Omit to revoke whoever holds it.
	ExpectedUserRefID string `json:"expected_user_ref_id,omitempty"`
	Reason            string `json:"reason"`
}

// BindingRead is one cross-user read of `actor_control_binding`, for the audit.
type BindingRead struct {
	RealityID   uuid.UUID
	ActorID     uuid.UUID
	Caller      string
	ResultCount int
}

// ReadAuditor records the `actor_binding_cross_user` row.
//
// An interface for the same reason `Registrar` and `AuditSink` are: the
// HTTP/auth/idempotency logic is unit-tested without a database, and the
// production impl — which builds the SDK-shaped `pii.SensitiveReadEntry` and
// writes it through `piikms.PgReadAuditWriter` — lives on the side of the
// module boundary where `contracts/pii` already is.
type ReadAuditor interface {
	RecordBindingRead(ctx context.Context, r BindingRead) error
}

// LiveBinding is the live row for one actor, or absent.
type LiveBinding struct {
	BindingID uuid.UUID
	UserRefID uuid.UUID
}

func (s *Server) handleGrantControl(w http.ResponseWriter, r *http.Request) (int, error) {
	var req GrantControlReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "bad json: " + err.Error()})
		return http.StatusBadRequest, nil
	}
	if req.UserRefID == "" || req.RealityID == "" || req.ActorID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "user_ref_id, reality_id, actor_id required"})
		return http.StatusBadRequest, nil
	}
	err := s.reg.GrantActorControl(r.Context(), req)
	switch {
	case errors.Is(err, ErrAlreadyGranted):
		writeJSON(w, http.StatusOK, map[string]string{"status": "already_granted"})
		return http.StatusOK, nil
	case errors.Is(err, ErrActorAlreadyDriven):
		writeJSON(w, http.StatusConflict, map[string]string{"error": "actor_already_driven"})
		return http.StatusConflict, nil
	case err != nil:
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return http.StatusInternalServerError, err
	default:
		writeJSON(w, http.StatusCreated, map[string]string{"status": "granted"})
		return http.StatusCreated, nil
	}
}

func (s *Server) handleRevokeControl(w http.ResponseWriter, r *http.Request) (int, error) {
	var req RevokeControlReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "bad json: " + err.Error()})
		return http.StatusBadRequest, nil
	}
	if req.RealityID == "" || req.ActorID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "reality_id, actor_id required"})
		return http.StatusBadRequest, nil
	}
	err := s.reg.RevokeActorControl(r.Context(), req)
	switch {
	case errors.Is(err, ErrNoLiveBinding):
		// 200 and not 404: the caller asked for "this actor has no driver" and
		// that is now true. Idempotent by END STATE, which is the property a
		// retry needs. The body says which of the two happened.
		writeJSON(w, http.StatusOK, map[string]string{"status": "already_revoked"})
		return http.StatusOK, nil
	case errors.Is(err, ErrControlCASMismatch):
		writeJSON(w, http.StatusConflict, map[string]string{"error": "expected_user_does_not_hold_binding"})
		return http.StatusConflict, nil
	case err != nil:
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return http.StatusInternalServerError, err
	default:
		writeJSON(w, http.StatusOK, map[string]string{"status": "revoked"})
		return http.StatusOK, nil
	}
}

// liveBinding reads the live row for (reality, actor) — nil when none.
//
// A READ handle, exactly as the `Pool` field's own comment permits: every WRITE
// still goes through MetaWrite. The read exists because `contracts/meta` has no
// upsert, so grant-vs-conflict has to be decided before the intent is built.
func (m MetaRegistrar) liveBinding(ctx context.Context, realityID, actorID uuid.UUID) (*LiveBinding, error) {
	row := m.Pool.QueryRow(ctx,
		`SELECT binding_id, user_ref_id FROM actor_control_binding
          WHERE reality_id = $1 AND actor_id = $2 AND revoked_at IS NULL`,
		realityID, actorID)
	var b LiveBinding
	found := 0
	var out *LiveBinding
	switch err := row.Scan(&b.BindingID, &b.UserRefID); {
	case err == nil:
		found, out = 1, &b
	case strings.Contains(err.Error(), "no rows"):
	default:
		return nil, fmt.Errorf("live binding read: %w", err)
	}

	// THIS READ IS CROSS-USER, and the discipline says so.
	//
	// It is keyed by ACTOR with no user predicate — "who drives this actor" —
	// which is `actor_binding_cross_user` in meta-sensitive-read-paths.yml, and
	// `034`'s own header calls it *"the identity-manipulation surface"*. The
	// GDPR cascade's exemption does not apply: that one reads OWNER-scoped
	// (`WHERE user_ref_id = $1`), the case the yml explicitly is not about.
	//
	// A failed audit does NOT fail the read. The row is the record, not the
	// gate; dropping a grant on the floor because an audit insert failed would
	// trade a missing log line for an outage. It is logged loudly instead.
	if m.ReadAudit != nil {
		if err := m.ReadAudit.RecordBindingRead(ctx, BindingRead{
			RealityID: realityID, ActorID: actorID, Caller: m.Caller, ResultCount: found,
		}); err != nil {
			slog.Error("bridge: meta_read_audit write failed for a cross-user binding read",
				"error", err, "reality_id", realityID, "actor_id", actorID)
		}
	}
	return out, nil
}

// GrantActorControl inserts a new live binding.
func (m MetaRegistrar) GrantActorControl(ctx context.Context, r GrantControlReq) error {
	userID, realityID, actorID, err := threeUUIDs(r.UserRefID, r.RealityID, r.ActorID)
	if err != nil {
		return err
	}
	live, err := m.liveBinding(ctx, realityID, actorID)
	if err != nil {
		return err
	}
	if live != nil {
		if live.UserRefID == userID {
			return ErrAlreadyGranted
		}
		return ErrActorAlreadyDriven
	}

	intent := meta.MetaWriteIntent{
		Table:     "actor_control_binding",
		Operation: meta.OpInsert,
		// `binding_id` is minted HERE, not defaulted by the database, so the
		// audit row and the outbox event both name the row that was written.
		// A server-side DEFAULT would leave `meta_write_audit.row_pk` pointing
		// at a value this process never saw.
		PK: map[string]any{"binding_id": uuid.New()},
		NewValues: map[string]any{
			"user_ref_id": userID,
			"reality_id":  realityID,
			"actor_id":    actorID,
		},
		Actor:  meta.Actor{Type: meta.ActorSystem, ID: m.Caller},
		Reason: orDefault(r.Reason, "grant actor control"),
	}
	if _, err := meta.MetaWrite(ctx, m.Cfg, intent); err != nil {
		// The partial unique index is the last line of defence behind the read
		// above — it catches the race the read cannot.
		if isUniqueViolation(err) {
			return ErrActorAlreadyDriven
		}
		return err
	}
	return nil
}

// RevokeActorControl ends the live binding for (reality, actor).
func (m MetaRegistrar) RevokeActorControl(ctx context.Context, r RevokeControlReq) error {
	realityID, err := uuid.Parse(r.RealityID)
	if err != nil {
		return fmt.Errorf("revoke: reality_id not a uuid: %w", err)
	}
	actorID, err := uuid.Parse(r.ActorID)
	if err != nil {
		return fmt.Errorf("revoke: actor_id not a uuid: %w", err)
	}
	live, err := m.liveBinding(ctx, realityID, actorID)
	if err != nil {
		return err
	}
	if live == nil {
		return ErrNoLiveBinding
	}
	if r.ExpectedUserRefID != "" {
		want, err := uuid.Parse(r.ExpectedUserRefID)
		if err != nil {
			return fmt.Errorf("revoke: expected_user_ref_id not a uuid: %w", err)
		}
		if want != live.UserRefID {
			return ErrControlCASMismatch
		}
	}

	intent := meta.MetaWriteIntent{
		Table:     "actor_control_binding",
		Operation: meta.OpUpdate,
		PK:        map[string]any{"binding_id": live.BindingID},
		NewValues: map[string]any{"revoked_at": time.Now().UTC()},
		// `revoked_at IS NULL` — the query builder renders a nil expected value
		// as an IS NULL predicate, and its own comment names migration 011's
		// single-transition consent revoke as the precedent. This closes the
		// window between the read above and this write.
		ExpectedBefore: map[string]any{"revoked_at": nil},
		Actor:          meta.Actor{Type: meta.ActorSystem, ID: m.Caller},
		Reason:         orDefault(r.Reason, "revoke actor control"),
	}
	res, err := meta.MetaWrite(ctx, m.Cfg, intent)
	if err != nil {
		return err
	}
	if res.RowsAffected == 0 {
		// The CAS lost: somebody revoked between the read and the write.
		//
		// ⚠ MetaWrite has ALREADY appended `actor.control.revoked` — it emits
		// the outbox event without consulting RowsAffected
		// (`contracts/meta/metawrite.go`, the append sits after the data
		// statement with no rows check). Outbox delivery is at-least-once by
		// contract, so a duplicate revoke for an already-revoked binding is
		// inside what a consumer must already tolerate; it is still an event
		// for a write that changed nothing. Recorded as `PC-METAWRITE-NOOP-EVENT`
		// rather than fixed here — the append is shared by every meta table.
		return ErrNoLiveBinding
	}
	return nil
}

func threeUUIDs(user, reality, actor string) (uuid.UUID, uuid.UUID, uuid.UUID, error) {
	u, err := uuid.Parse(user)
	if err != nil {
		return uuid.Nil, uuid.Nil, uuid.Nil, fmt.Errorf("grant: user_ref_id not a uuid: %w", err)
	}
	rl, err := uuid.Parse(reality)
	if err != nil {
		return uuid.Nil, uuid.Nil, uuid.Nil, fmt.Errorf("grant: reality_id not a uuid: %w", err)
	}
	a, err := uuid.Parse(actor)
	if err != nil {
		return uuid.Nil, uuid.Nil, uuid.Nil, fmt.Errorf("grant: actor_id not a uuid: %w", err)
	}
	return u, rl, a, nil
}

// ─── RA1 · the READ half ─────────────────────────────────────────────────────

// ReadControlReq asks who currently drives one actor in one reality.
//
// No user field, and that absence is the whole point: this is the cross-user
// question. A read keyed by (reality, actor, user) would be owner-scoped and
// would need no audit row; this one needs one, and gets one.
type ReadControlReq struct {
	RealityID string `json:"reality_id"`
	ActorID   string `json:"actor_id"`
}

// handleReadControl serves `POST /internal/provisioner/read-actor-control`.
//
// # Why this route exists at all
//
// `liveBinding` has been the only audited cross-user read of
// `actor_control_binding` since `034`, and it was PRIVATE — reachable only from
// inside the grant/revoke CAS. So a caller in another service that needed the
// same answer had exactly two options: write its own bare `SELECT`, which
// `meta-sensitive-read-bypass-lint` correctly refuses, or go without. That is
// `D-PC-NO-RUST-READ-AUDIT`: the discipline had no reachable path, so the first
// caller to need one would have bypassed it by default rather than by choice.
//
// The route changes nothing about the read. It reuses `liveBinding` unmodified,
// which means the `meta_read_audit` row is written by the same line that has
// always written it — the audit cannot be skipped by using this door, because
// there is no second implementation to skip it with.
//
// # 200 with a null body is the ANSWER, not a miss
//
// "Nobody drives this actor" is a fact about the world and a perfectly good
// reply. A `404` would make the caller's error path carry a normal outcome, and
// the first thing anyone writes against a 404 is a retry.
func (s *Server) handleReadControl(w http.ResponseWriter, r *http.Request) (int, error) {
	var req ReadControlReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "bad json: " + err.Error()})
		return http.StatusBadRequest, nil
	}
	if req.RealityID == "" || req.ActorID == "" {
		writeJSON(w, http.StatusBadRequest,
			map[string]string{"error": "reality_id and actor_id are required"})
		return http.StatusBadRequest, nil
	}
	realityID, err := uuid.Parse(req.RealityID)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "reality_id: " + err.Error()})
		return http.StatusBadRequest, nil
	}
	actorID, err := uuid.Parse(req.ActorID)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "actor_id: " + err.Error()})
		return http.StatusBadRequest, nil
	}

	b, err := s.reg.ReadActorControl(r.Context(), ReadControlReq{
		RealityID: realityID.String(), ActorID: actorID.String(),
	})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return http.StatusInternalServerError, err
	}
	if b == nil {
		writeJSON(w, http.StatusOK, map[string]any{"driven": false})
		return http.StatusOK, nil
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"driven":      true,
		"user_ref_id": b.UserRefID.String(),
		"binding_id":  b.BindingID.String(),
	})
	return http.StatusOK, nil
}

// ReadActorControl exposes the audited read on the production registrar.
//
// A one-line delegate on purpose. `liveBinding` stays the single implementation
// so the `meta_read_audit` write has exactly one home; a second query here —
// even an identical one — would be a second place for the audit to be forgotten,
// which is the shape `PD-10` recorded when this table's registered read path had
// no SDK constant to reach it.
func (m MetaRegistrar) ReadActorControl(ctx context.Context, r ReadControlReq) (*LiveBinding, error) {
	realityID, err := uuid.Parse(r.RealityID)
	if err != nil {
		return nil, fmt.Errorf("reality_id: %w", err)
	}
	actorID, err := uuid.Parse(r.ActorID)
	if err != nil {
		return nil, fmt.Errorf("actor_id: %w", err)
	}
	return m.liveBinding(ctx, realityID, actorID)
}

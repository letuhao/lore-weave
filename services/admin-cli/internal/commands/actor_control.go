// actor_control.go — `admin reality grant-control` / `revoke-control` /
// `create-actor` (SEALED-BINDING).
//
// The CALLER for `actor_control_binding`'s writer. Migration `034` shipped the
// table with a reader and no writer; feature #2 built the writer as two
// `require_internal` routes on world-service — correct for a service-to-service
// surface, and unreachable by any operator. So the writer had no invoker
// either, which is the same orphan shape one tier up. `035` deleted a whole
// table for it.
//
// Division of labour, and it is the point of the design:
//
//   - **Go owns governance.** The framework dispatcher has already validated the
//     admin JWT, checked `admin:write` for the tier, enforced the dry-run gate,
//     required a reason, and written the `admin_action_audit` "started" row
//     before this file runs. None of that is re-implemented here.
//   - **The Rust worker owns the operation.** It holds every DSN, binds the
//     reality through the control plane, checks the actor exists in the
//     per-reality database, and calls the Go meta-write bridge so the audit row
//     and the outbox event land in the binding's own transaction (I8).
//
// Why a subprocess and not an HTTP call: admin-cli has no HTTP invoker (every
// command is an exec or a direct pgxpool), and `contracts/service_acl/matrix.yaml`
// sanctions admin-cli as a caller of meta-worker, not of world-service. Calling
// the bridge directly WOULD be sanctioned — and would skip both safety checks,
// one of which cannot move into meta-worker because it reads the per-reality
// database meta-worker does not hold. So the seam is a subprocess, exactly as
// `reality provision` drives the `provision` worker.
package commands

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
)

// ErrInvalidActorControl is the sentinel for a malformed actor-control request.
var ErrInvalidActorControl = errors.New("admin-cli: actor control")

// ActorControlOp is the closed set of operations the worker accepts. Closed on
// purpose: a free string would let a typo reach the worker's argv and come back
// as an unknown-flag error two processes away from where it was typed.
type ActorControlOp string

const (
	// OpGrantControl gives a user the live binding for an actor.
	OpGrantControl ActorControlOp = "grant"
	// OpRevokeControl ends the live binding for an actor.
	OpRevokeControl ActorControlOp = "revoke"
	// OpCreateActor mints an actor in a reality's registry.
	OpCreateActor ActorControlOp = "create-actor"
)

// ActorControlRequest is the validated input to the actor-control flow.
type ActorControlRequest struct {
	Op        ActorControlOp
	RealityID uuid.UUID
	// UserRefID is WHO drives. Required for grant; absent otherwise.
	UserRefID uuid.UUID
	// ActorID is required for grant and revoke. For create-actor it must be
	// absent — the registry mints it, and a caller-supplied one would make the
	// CLI a second source for a value with one SSOT.
	ActorID uuid.UUID
	// ExpectedUserRefID is the optional CAS on a revoke: end the binding ONLY
	// while this user still holds it. Omit and you revoke whoever does —
	// including someone who took over since the character list was read.
	ExpectedUserRefID uuid.UUID
	// EntityID adopts an island id on create-actor instead of allocating one.
	// Zero means allocate. Exists because the spine hardcodes EntityId(1..3),
	// and without adoption every already-running island would be undrivable.
	EntityID int64
	Actor    string
	Reason   string
	DryRun   bool
	Confirm  bool
}

// Validate checks the request shape. The dispatcher separately enforces the
// reason length and the dry-run gate; this covers what is specific to actor
// control.
//
// The per-op rules are duplicated in the Rust worker's arg parser on purpose.
// This is NOT the "second, weaker check set" the flow extraction avoided: these
// are ARGUMENT rules, cheap and total, and checking them here means an operator
// sees the mistake in the message they typed rather than as a worker exit 2.
// The rules that touch the WORLD — the reality bind, the actor-exists
// precondition — exist in exactly one place, and it is not this file.
func (r ActorControlRequest) Validate() error {
	switch r.Op {
	case OpGrantControl, OpRevokeControl, OpCreateActor:
	default:
		return fmt.Errorf("%w: unknown op %q (want grant, revoke or create-actor)",
			ErrInvalidActorControl, r.Op)
	}
	if r.RealityID == uuid.Nil {
		return fmt.Errorf("%w: reality_id must not be the nil UUID", ErrInvalidActorControl)
	}
	switch r.Op {
	case OpGrantControl:
		if r.UserRefID == uuid.Nil {
			return fmt.Errorf("%w: user_ref_id is required for a grant", ErrInvalidActorControl)
		}
		if r.ActorID == uuid.Nil {
			return fmt.Errorf("%w: actor_id is required for a grant", ErrInvalidActorControl)
		}
		if r.ExpectedUserRefID != uuid.Nil {
			return fmt.Errorf(
				"%w: expected_user_ref_id is a revoke-only CAS and has no meaning on a grant",
				ErrInvalidActorControl)
		}
	case OpRevokeControl:
		if r.ActorID == uuid.Nil {
			return fmt.Errorf("%w: actor_id is required for a revoke", ErrInvalidActorControl)
		}
		if r.UserRefID != uuid.Nil {
			return fmt.Errorf(
				"%w: a revoke ends whoever holds the binding — pass expected_user_ref_id to "+
					"name who you expect, not user_ref_id",
				ErrInvalidActorControl)
		}
	case OpCreateActor:
		if r.ActorID != uuid.Nil {
			return fmt.Errorf(
				"%w: actor_id is not accepted for create-actor — the registry mints it",
				ErrInvalidActorControl)
		}
		if r.EntityID < 0 {
			return fmt.Errorf("%w: entity_id %d must be positive (omit it to allocate)",
				ErrInvalidActorControl, r.EntityID)
		}
	}
	return nil
}

// ActorControlOutcome is the worker's stdout JSON. One shape for all three ops
// and both modes; the fields a given branch does not populate stay zero.
type ActorControlOutcome struct {
	Op     string `json:"op"`
	Status string `json:"status"`
	Mode   string `json:"mode"`
	DryRun bool   `json:"dry_run"`

	RealityID string `json:"reality_id"`
	ActorID   string `json:"actor_id"`

	// Outcome is one of granted · already_granted · revoked · already_revoked ·
	// actor_created. Changed says whether anything was written — a re-run that
	// finds the state already correct is a success that wrote nothing, and an
	// operator deserves to be told which.
	Outcome string `json:"outcome"`
	Changed bool   `json:"changed"`

	// create-actor results.
	CreatedActorID string `json:"created_actor_id"`
	EntityID       int64  `json:"entity_id"`

	// Dry-run findings. Note the absence of any "current holder" field: see the
	// worker's module docs — reading it is a cross-user read of
	// actor_control_binding that only the audited write path may take.
	//
	// RealityAcceptsCommands is `true` whenever a dry run succeeds at all — a
	// refused bind exits 1 instead. It is carried so a machine reading the JSON
	// can see the check RAN, and it is deliberately NOT printed with `%t` in the
	// operator summary: rendering a constant as a measurement invites a reader to
	// believe the false case is reachable and was ruled out.
	RealityAcceptsCommands bool   `json:"reality_accepts_commands"`
	ActorExists            bool   `json:"actor_exists"`
	WouldGrant             bool   `json:"would_grant"`
	WouldRevoke            bool   `json:"would_revoke"`
	WouldCreateActor       bool   `json:"would_create_actor"`
	EntityIDSource         string `json:"entity_id_source"`
	Note                   string `json:"note"`

	// Conflict marks a refusal that is a statement about the WORLD (somebody
	// else drives this actor · the CAS named a user who no longer holds it ·
	// the reality is closed · the actor does not exist) rather than a fault on
	// our side. An operator who sees it should reload and decide; one who does
	// not should look at the bridge.
	Conflict bool   `json:"conflict"`
	Error    string `json:"error"`
}

// ActorControlInvoker runs the actor-control worker. The production
// implementation (SubprocessActorControlInvoker) execs the world-service
// `actor-control` binary; tests stub it.
type ActorControlInvoker interface {
	Run(ctx context.Context, req ActorControlRequest) (ActorControlOutcome, error)
}

// ActorControlDeps bundles the collaborators.
type ActorControlDeps struct {
	Invoker ActorControlInvoker
}

// RunActorControl validates, invokes the worker, and renders the operator
// summary.
//
// Like RunProvisionReality — and unlike RunRebuildProjection — the dry run is
// NOT short-circuited in Go. It has something real to report that only the
// worker can read: whether the control plane accepts the reality, and whether
// the actor has a durable identity. Answering from here would be asserting a
// state nothing measured.
func RunActorControl(ctx context.Context, req ActorControlRequest, deps ActorControlDeps) (string, error) {
	if err := req.Validate(); err != nil {
		return "", err
	}
	if deps.Invoker == nil {
		return "", fmt.Errorf("%w: no invoker configured", ErrInvalidActorControl)
	}

	out, err := deps.Invoker.Run(ctx, req)
	if err != nil {
		return "", err
	}

	if req.DryRun {
		return actorControlDryRunSummary(req, out), nil
	}

	// A report naming no outcome is not a report. This is the guard
	// `reality provision` had to learn the hard way: a renamed JSON key left
	// its `shard` empty and the command printed "provisioned on shard " with
	// exit 0. Here the same drift would print "grant-control: " — a success
	// message for an operation nobody can name.
	if strings.TrimSpace(out.Outcome) == "" {
		return "", fmt.Errorf(
			"%w: worker exited 0 for %s but named no outcome — refusing to report a result "+
				"it did not state (stale worker binary, or a changed output contract?)",
			ErrInvalidActorControl, req.RealityID)
	}

	if req.Op == OpCreateActor {
		// Same class of guard: an actor "created" with no id is not a created
		// actor, and the id is the only thing a follow-up grant can use.
		if strings.TrimSpace(out.CreatedActorID) == "" {
			return "", fmt.Errorf(
				"%w: worker reported an actor created in %s but named no actor_id",
				ErrInvalidActorControl, req.RealityID)
		}
		return fmt.Sprintf(
			"actor %s created in reality %s as entity %d. Grant it with:\n"+
				"  admin reality grant-control --reality-id %s --actor-id %s --user-ref-id <user> --reason <why>",
			out.CreatedActorID, req.RealityID, out.EntityID,
			req.RealityID, out.CreatedActorID,
		), nil
	}

	verb := "grant-control"
	if req.Op == OpRevokeControl {
		verb = "revoke-control"
	}
	if !out.Changed {
		return fmt.Sprintf(
			"%s: actor %s in reality %s was ALREADY in the requested state (%s). Nothing was written.",
			verb, req.ActorID, req.RealityID, out.Outcome,
		), nil
	}
	if req.Op == OpGrantControl {
		return fmt.Sprintf(
			"grant-control: user %s now drives actor %s in reality %s.",
			req.UserRefID, req.ActorID, req.RealityID,
		), nil
	}
	return fmt.Sprintf(
		"revoke-control: actor %s in reality %s has no driver. The binding is history, not "+
			"deleted, and the actor is drivable again.",
		req.ActorID, req.RealityID,
	), nil
}

// actorControlDryRunSummary renders the preview, and says out loud what it did
// NOT check.
//
// The silence is load-bearing. An operator reading "would grant" without the
// caveat would reasonably infer the slot was free; it was never checked,
// because checking it is a cross-user read of actor_control_binding that only
// the audited write path may take. A preview that quietly omitted that would be
// worse than one that refuses to preview at all.
func actorControlDryRunSummary(req ActorControlRequest, out ActorControlOutcome) string {
	head := fmt.Sprintf("%s DRY-RUN — reality %s", req.Op, req.RealityID)
	switch req.Op {
	case OpCreateActor:
		src := out.EntityIDSource
		if src == "" {
			src = "allocated"
		}
		return fmt.Sprintf(
			"%s accepts commands. Would create an actor with an %s entity id.\nNothing was written.",
			head, src)
	case OpRevokeControl:
		return fmt.Sprintf(
			"%s — would revoke the live binding for actor %s.\n"+
				"NOT CHECKED HERE: who currently holds it. That is a cross-user read of "+
				"actor_control_binding, which only the audited write path may take; the CAS is "+
				"evaluated inside the write transaction.\nNothing was written.",
			head, req.ActorID)
	default:
		if !out.ActorExists {
			return fmt.Sprintf(
				"%s accepts commands. Actor %s does NOT exist in its registry — the grant "+
					"would be REFUSED. Create it first with `admin reality create-actor`.\n"+
					"Nothing was written.",
				head, req.ActorID)
		}
		return fmt.Sprintf(
			"%s accepts commands. Actor %s exists; user %s would be granted control.\n"+
				"NOT CHECKED HERE: whether another user already drives it. That is a cross-user "+
				"read of actor_control_binding, which only the audited write path may take; a "+
				"real run refuses with a conflict if so.\nNothing was written.",
			head, req.ActorID, req.UserRefID)
	}
}

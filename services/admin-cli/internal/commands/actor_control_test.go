// actor_control_test.go — the caller for `actor_control_binding`'s writer.
//
// Every test here asserts the specific message or field, never merely that an
// error occurred. `is_err()` cannot tell two guards apart, so a suite built on
// it stays green while one of them is deleted.
package commands

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/google/uuid"
)

var (
	tcReality = uuid.MustParse("11111111-1111-4111-8111-111111111111")
	tcActor   = uuid.MustParse("22222222-2222-4222-8222-222222222222")
	tcUser    = uuid.MustParse("33333333-3333-4333-8333-333333333333")
	tcHeir    = uuid.MustParse("44444444-4444-4444-8444-444444444444")
)

// stubActorControlInvoker returns a canned outcome and records what it was asked to do.
type stubActorControlInvoker struct {
	got  ActorControlRequest
	out  ActorControlOutcome
	err  error
	runs int
}

func (s *stubActorControlInvoker) Run(_ context.Context, req ActorControlRequest) (ActorControlOutcome, error) {
	s.runs++
	s.got = req
	return s.out, s.err
}

func grantReq() ActorControlRequest {
	return ActorControlRequest{
		Op: OpGrantControl, RealityID: tcReality, ActorID: tcActor, UserRefID: tcUser,
		Actor: "admin@example.test", Reason: "the operator explained themselves",
	}
}

// ── validation ──────────────────────────────────────────────────────────────

func TestActorControlValidateNamesTheMissingIdentifier(t *testing.T) {
	cases := []struct {
		name string
		req  ActorControlRequest
		want string
	}{
		{"grant with no user", ActorControlRequest{Op: OpGrantControl, RealityID: tcReality, ActorID: tcActor}, "user_ref_id is required"},
		{"grant with no actor", ActorControlRequest{Op: OpGrantControl, RealityID: tcReality, UserRefID: tcUser}, "actor_id is required"},
		{"revoke with no actor", ActorControlRequest{Op: OpRevokeControl, RealityID: tcReality}, "actor_id is required"},
		{"no reality", ActorControlRequest{Op: OpGrantControl, ActorID: tcActor, UserRefID: tcUser}, "reality_id must not be the nil UUID"},
		{"unknown op", ActorControlRequest{Op: "posses", RealityID: tcReality}, "unknown op"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			err := c.req.Validate()
			if err == nil {
				t.Fatalf("expected a refusal, got nil")
			}
			if !strings.Contains(err.Error(), c.want) {
				t.Fatalf("error %q does not name %q", err, c.want)
			}
			if !errors.Is(err, ErrInvalidActorControl) {
				t.Fatalf("error %q is not the package sentinel", err)
			}
		})
	}
}

// Non-vacuity for the table above: a Validate that refused EVERYTHING would
// pass every case in it. The complete forms must be accepted.
func TestActorControlValidateAcceptsTheCompleteForms(t *testing.T) {
	for _, req := range []ActorControlRequest{
		grantReq(),
		{Op: OpRevokeControl, RealityID: tcReality, ActorID: tcActor},
		{Op: OpRevokeControl, RealityID: tcReality, ActorID: tcActor, ExpectedUserRefID: tcUser},
		{Op: OpCreateActor, RealityID: tcReality},
		{Op: OpCreateActor, RealityID: tcReality, EntityID: 3},
	} {
		if err := req.Validate(); err != nil {
			t.Fatalf("%s must be accepted: %v", req.Op, err)
		}
	}
}

// The CAS is revoke-only. Accepting it on a grant would let an operator write a
// flag that silently does nothing — the shape of every "the setting was stored
// but never read" bug.
func TestActorControlRefusesTheCasOnAGrant(t *testing.T) {
	req := grantReq()
	req.ExpectedUserRefID = tcHeir
	err := req.Validate()
	if err == nil || !strings.Contains(err.Error(), "revoke-only") {
		t.Fatalf("a CAS on a grant must be refused, got %v", err)
	}
}

// user_ref_id on a revoke is the dangerous confusion: an operator who means
// "revoke Alice" would otherwise get "revoke whoever holds it", and the flag
// they typed would be ignored.
func TestActorControlRefusesUserRefIDOnARevoke(t *testing.T) {
	req := ActorControlRequest{Op: OpRevokeControl, RealityID: tcReality, ActorID: tcActor, UserRefID: tcUser}
	err := req.Validate()
	if err == nil || !strings.Contains(err.Error(), "expected_user_ref_id") {
		t.Fatalf("user_ref_id on a revoke must be refused and point at the CAS, got %v", err)
	}
}

// The registry MINTS the actor id. A caller-supplied one would make the CLI a
// second source for a value with exactly one SSOT.
func TestCreateActorRefusesASuppliedActorID(t *testing.T) {
	req := ActorControlRequest{Op: OpCreateActor, RealityID: tcReality, ActorID: tcActor}
	err := req.Validate()
	if err == nil || !strings.Contains(err.Error(), "mints") {
		t.Fatalf("create-actor must refuse a supplied actor_id, got %v", err)
	}
}

// ── the argv contract ───────────────────────────────────────────────────────

// Three ops share one binary, so the difference between them is entirely which
// flags are present. Asserted on both sides: the flags that must appear, and
// the ones that must NOT.
func TestWorkerArgsCarryOnlyTheFlagsTheOpUses(t *testing.T) {
	grant := strings.Join(workerArgs(grantReq()), " ")
	for _, want := range []string{"--op grant", "--reality-id " + tcReality.String(),
		"--actor-id " + tcActor.String(), "--user-ref-id " + tcUser.String()} {
		if !strings.Contains(grant, want) {
			t.Fatalf("grant argv %q is missing %q", grant, want)
		}
	}
	if strings.Contains(grant, "--expected-user-ref-id") {
		t.Fatalf("grant argv must not carry the revoke-only CAS: %q", grant)
	}
	if strings.Contains(grant, "--dry-run") {
		t.Fatalf("a live grant must not carry --dry-run: %q", grant)
	}

	// The CAS reaches the worker when it is set — the other half of the
	// assertion above, without which "must not carry" could be satisfied by a
	// renderer that never emits the flag at all.
	cas := ActorControlRequest{Op: OpRevokeControl, RealityID: tcReality, ActorID: tcActor,
		ExpectedUserRefID: tcHeir, Reason: "r"}
	if got := strings.Join(workerArgs(cas), " "); !strings.Contains(got, "--expected-user-ref-id "+tcHeir.String()) {
		t.Fatalf("the CAS must reach the worker: %q", got)
	}

	// A zero EntityID means ALLOCATE. Emitting `--entity-id 0` would adopt
	// island entity zero instead, which is a different operation.
	alloc := strings.Join(workerArgs(ActorControlRequest{Op: OpCreateActor, RealityID: tcReality, Reason: "r"}), " ")
	if strings.Contains(alloc, "--entity-id") {
		t.Fatalf("an unset entity_id must mean ALLOCATE, not adopt entity 0: %q", alloc)
	}
	adopt := strings.Join(workerArgs(ActorControlRequest{Op: OpCreateActor, RealityID: tcReality, EntityID: 3, Reason: "r"}), " ")
	if !strings.Contains(adopt, "--entity-id 3") {
		t.Fatalf("an explicit entity_id must reach the worker: %q", adopt)
	}

	dry := ActorControlRequest{Op: OpRevokeControl, RealityID: tcReality, ActorID: tcActor, DryRun: true, Reason: "r"}
	if !strings.Contains(strings.Join(workerArgs(dry), " "), "--dry-run") {
		t.Fatalf("a dry run must reach the worker as --dry-run")
	}
}

// ── the summaries ───────────────────────────────────────────────────────────

func TestRunActorControlReportsAGrantThatChangedSomething(t *testing.T) {
	inv := &stubActorControlInvoker{out: ActorControlOutcome{Outcome: "granted", Changed: true}}
	got, err := RunActorControl(context.Background(), grantReq(), ActorControlDeps{Invoker: inv})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "now drives actor") || !strings.Contains(got, tcUser.String()) {
		t.Fatalf("summary does not report the grant: %q", got)
	}
}

// A re-run that finds the state already correct is a success that wrote
// nothing. Reporting it as a write would tell an operator they had just changed
// something when they had not.
func TestRunActorControlDistinguishesANoOp(t *testing.T) {
	inv := &stubActorControlInvoker{out: ActorControlOutcome{Outcome: "already_granted", Changed: false}}
	got, err := RunActorControl(context.Background(), grantReq(), ActorControlDeps{Invoker: inv})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "ALREADY") || !strings.Contains(got, "Nothing was written") {
		t.Fatalf("a no-op must not read as a write: %q", got)
	}
}

// The provision guard, relearned: a renamed JSON key once left `shard` empty
// and the command printed "provisioned on shard " with exit 0. Here the same
// drift would print a success message for an operation nobody can name.
func TestRunActorControlRefusesAnOutcomeTheWorkerDidNotName(t *testing.T) {
	inv := &stubActorControlInvoker{out: ActorControlOutcome{Changed: true}}
	_, err := RunActorControl(context.Background(), grantReq(), ActorControlDeps{Invoker: inv})
	if err == nil || !strings.Contains(err.Error(), "named no outcome") {
		t.Fatalf("an unnamed outcome must be refused, got %v", err)
	}
}

func TestRunActorControlRefusesACreatedActorWithNoID(t *testing.T) {
	inv := &stubActorControlInvoker{out: ActorControlOutcome{Outcome: "actor_created", Changed: true, EntityID: 7}}
	req := ActorControlRequest{Op: OpCreateActor, RealityID: tcReality, Reason: "r"}
	_, err := RunActorControl(context.Background(), req, ActorControlDeps{Invoker: inv})
	if err == nil || !strings.Contains(err.Error(), "named no actor_id") {
		t.Fatalf("an actor created with no id must be refused, got %v", err)
	}
}

// The created id is the ONLY thing a follow-up grant can use, so the summary
// hands the operator the exact next command rather than making them assemble it.
func TestCreateActorSummaryHandsOverTheGrantCommand(t *testing.T) {
	created := uuid.MustParse("55555555-5555-4555-8555-555555555555")
	inv := &stubActorControlInvoker{out: ActorControlOutcome{
		Outcome: "actor_created", Changed: true, CreatedActorID: created.String(), EntityID: 7,
	}}
	req := ActorControlRequest{Op: OpCreateActor, RealityID: tcReality, Reason: "r"}
	got, err := RunActorControl(context.Background(), req, ActorControlDeps{Invoker: inv})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, want := range []string{created.String(), "entity 7", "admin reality grant-control"} {
		if !strings.Contains(got, want) {
			t.Fatalf("summary %q is missing %q", got, want)
		}
	}
}

// ── the dry run, and the silence that is load-bearing ───────────────────────

// The preview must SAY what it did not check. An operator reading "would grant"
// without the caveat would reasonably infer the driver slot was free; it was
// never looked at, because looking is a cross-user read of
// actor_control_binding that only the audited write path may take.
func TestGrantDryRunDeclaresTheCheckItDidNotMake(t *testing.T) {
	inv := &stubActorControlInvoker{out: ActorControlOutcome{
		Mode: "dry-run", RealityAcceptsCommands: true, ActorExists: true, WouldGrant: true,
	}}
	req := grantReq()
	req.DryRun = true
	got, err := RunActorControl(context.Background(), req, ActorControlDeps{Invoker: inv})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, want := range []string{"NOT CHECKED HERE", "cross-user", "Nothing was written"} {
		if !strings.Contains(got, want) {
			t.Fatalf("preview %q is missing %q — the silence must be declared, not implied", got, want)
		}
	}
}

func TestRevokeDryRunDeclaresTheCheckItDidNotMake(t *testing.T) {
	inv := &stubActorControlInvoker{out: ActorControlOutcome{Mode: "dry-run", WouldRevoke: true}}
	req := ActorControlRequest{Op: OpRevokeControl, RealityID: tcReality, ActorID: tcActor, DryRun: true, Reason: "r"}
	got, err := RunActorControl(context.Background(), req, ActorControlDeps{Invoker: inv})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, want := range []string{"NOT CHECKED HERE", "cross-user", "CAS"} {
		if !strings.Contains(got, want) {
			t.Fatalf("preview %q is missing %q", got, want)
		}
	}
}

// A dry run over an actor with no registry row must say the real run would be
// REFUSED — not "would be granted". This is the one preview finding that
// changes what an operator does next.
func TestGrantDryRunSaysSoWhenTheActorDoesNotExist(t *testing.T) {
	inv := &stubActorControlInvoker{out: ActorControlOutcome{
		Mode: "dry-run", RealityAcceptsCommands: true, ActorExists: false, WouldGrant: false,
	}}
	req := grantReq()
	req.DryRun = true
	got, err := RunActorControl(context.Background(), req, ActorControlDeps{Invoker: inv})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "REFUSED") || !strings.Contains(got, "create-actor") {
		t.Fatalf("preview %q must say the grant would be refused and name the fix", got)
	}
}

// The dry run is NOT short-circuited in Go: it has something real to report
// that only the worker can read. Answering from here would assert a state
// nothing measured — the provision drill's defect in a new location.
func TestActorControlDryRunStillInvokesTheWorker(t *testing.T) {
	inv := &stubActorControlInvoker{out: ActorControlOutcome{Mode: "dry-run", RealityAcceptsCommands: true, ActorExists: true}}
	req := grantReq()
	req.DryRun = true
	if _, err := RunActorControl(context.Background(), req, ActorControlDeps{Invoker: inv}); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if inv.runs != 1 {
		t.Fatalf("the worker must be invoked on a dry run, ran %d times", inv.runs)
	}
	if !inv.got.DryRun {
		t.Fatalf("the worker must be told it is a dry run")
	}
}

func TestActorControlRefusesWithNoInvoker(t *testing.T) {
	_, err := RunActorControl(context.Background(), grantReq(), ActorControlDeps{})
	if err == nil || !strings.Contains(err.Error(), "no invoker configured") {
		t.Fatalf("a missing invoker must be named, got %v", err)
	}
}

// ── the worker env ──────────────────────────────────────────────────────────

// All missing names at once: an operator fixing env one round-trip at a time is
// the failure mode this avoids.
func TestActorControlWorkerEnvNamesEveryGap(t *testing.T) {
	err := ActorControlWorkerEnv{PGUser: "x"}.Validate()
	if err == nil {
		t.Fatal("an empty env must be refused")
	}
	for _, want := range []string{
		"ACTOR_CONTROL_META_DSN", "ACTOR_CONTROL_BRIDGE_URL", "ACTOR_CONTROL_BRIDGE_TOKEN",
		"ACTOR_CONTROL_SHARD_HOSTPORT", "ACTOR_CONTROL_META_ALLOWLIST",
	} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error %q does not name %q", err, want)
		}
	}
	if strings.Contains(err.Error(), "ACTOR_CONTROL_PG_USER") {
		t.Fatalf("a SUPPLIED variable must not be listed as missing: %q", err)
	}
}

// The password may legitimately be empty (peer/trust auth), so a complete env
// without one must pass. Without this, the test above would be satisfied by a
// Validate that refused everything.
func TestActorControlWorkerEnvAcceptsAnEmptyPassword(t *testing.T) {
	env := ActorControlWorkerEnv{
		MetaDSN: "postgres://x/meta", BridgeURL: "http://bridge", BridgeToken: "t",
		ShardHostPort: "host:5432", PGUser: "u", MetaAllowlist: "contracts/meta/events_allowlist.yaml",
	}
	if err := env.Validate(); err != nil {
		t.Fatalf("peer/trust auth is legitimate: %v", err)
	}
}

// Nothing ambient reaches the worker. An ACTOR_CONTROL_META_DSN left over in an
// operator's shell is precisely how a command lands on the wrong Postgres.
func TestActorControlWorkerEnvironIsExplicit(t *testing.T) {
	t.Setenv("ACTOR_CONTROL_META_DSN", "postgres://LEAKED/meta")
	env := ActorControlWorkerEnv{
		MetaDSN: "postgres://intended/meta", BridgeURL: "http://bridge", BridgeToken: "t",
		ShardHostPort: "host:5432", PGUser: "u", MetaAllowlist: "a.yaml",
	}
	joined := strings.Join(env.environ(), "\n")
	if strings.Contains(joined, "LEAKED") {
		t.Fatalf("the ambient DSN reached the worker: %q", joined)
	}
	if !strings.Contains(joined, "postgres://intended/meta") {
		t.Fatalf("the configured DSN did not reach the worker: %q", joined)
	}
}

func TestSubprocessInvokerRefusesWithNoBinary(t *testing.T) {
	env := ActorControlWorkerEnv{
		MetaDSN: "d", BridgeURL: "u", BridgeToken: "t", ShardHostPort: "h", PGUser: "p",
		MetaAllowlist: "a",
	}
	_, err := NewSubprocessActorControlInvoker("", env).Run(context.Background(), grantReq())
	if err == nil || !strings.Contains(err.Error(), "no actor-control worker binary") {
		t.Fatalf("a missing binary path must be named, got %v", err)
	}
}

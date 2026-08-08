package commands

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// ─── the fake worker ─────────────────────────────────────────────────────────
//
// SubprocessProvisionInvoker builds the child's environment EXPLICITLY, so the
// usual GO_WANT_HELPER_PROCESS trick cannot reach the child — the variable is
// stripped. PROVISION_SQL_DIR *is* forwarded, so it doubles as the mode channel
// here. That is a test-only convention; the production worker treats it as the
// directory it is.
const fakeWorkerPrefix = "FAKEWORKER:"

// TestMain turns this test binary into the fake worker when PROVISION_SQL_DIR
// carries the marker, so the exec path is exercised for real — a real process,
// real argv, real exit codes, real stdout — without shipping a fixture binary.
func TestMain(m *testing.M) {
	mode := os.Getenv("PROVISION_SQL_DIR")
	if !strings.HasPrefix(mode, fakeWorkerPrefix) {
		os.Exit(m.Run())
	}
	os.Exit(runFakeWorker(strings.TrimPrefix(mode, fakeWorkerPrefix)))
}

func runFakeWorker(mode string) int {
	// Echo the requested id back by default, so the happy paths agree.
	var reqID string
	sawDryRun := false
	for i, a := range os.Args {
		if a == "--reality-id" && i+1 < len(os.Args) {
			reqID = os.Args[i+1]
		}
		if a == "--dry-run" {
			sawDryRun = true
		}
	}
	// The dry-run modes assert on ARGV, not on the mode string. Without this,
	// "does --dry-run reach the worker?" would be answered by the mode channel
	// that selected the branch — a check that cannot fail (NV-1).
	if (mode == "ok-dry" || mode == "no-capacity") && !sawDryRun {
		fmt.Fprintln(os.Stderr, "fake worker: --dry-run was NOT passed")
		return 3
	}
	// Conversely a real run must not carry it.
	if mode == "ok" && sawDryRun {
		fmt.Fprintln(os.Stderr, "fake worker: --dry-run leaked into a real run")
		return 3
	}
	switch mode {
	case "ok":
		fmt.Printf(`{"mode":"provision","reality_id":%q,"shard":"shard-a","db_name":"lw_reality_abc","steps":11}`, reqID)
		return 0
	case "ok-dry":
		fmt.Printf(`{"mode":"dry-run","reality_id":%q,"shard":"shard-a","db_name":"lw_reality_abc","would_provision":true,`+
			`"shards":[{"shard":"shard-a","used":2,"total":50}]}`, reqID)
		return 0
	case "no-capacity":
		fmt.Printf(`{"mode":"dry-run","reality_id":%q,"would_provision":false,"error":"no shard capacity",`+
			`"shards":[{"shard":"shard-a","used":50,"total":50}]}`, reqID)
		return 1
	case "setup-fail":
		fmt.Fprintln(os.Stderr, "provision: NOTRUN(setup): missing required env: PROVISION_META_DSN")
		return 2
	case "mismatch":
		fmt.Print(`{"mode":"provision","reality_id":"99999999-9999-4999-8999-999999999999","shard":"shard-a","db_name":"x","steps":11}`)
		return 0
	case "garbage":
		fmt.Print("this is not json")
		return 0
	case "blank-db":
		fmt.Printf(`{"mode":"provision","reality_id":%q,"shard":"shard-a","db_name":"","steps":11}`, reqID)
		return 0
	case "echo-env":
		// Dump the child's actual environment so a test can assert what leaked.
		out, _ := json.Marshal(os.Environ())
		fmt.Print(string(out))
		return 0
	}
	fmt.Fprintf(os.Stderr, "fake worker: unknown mode %q\n", mode)
	return 3
}

// fakeWorkerEnv returns a fully-populated env whose SQLDir selects a mode.
func fakeWorkerEnv(mode string) ProvisionWorkerEnv {
	return ProvisionWorkerEnv{
		MetaDSN:       "postgres://meta",
		ShardAdminDSN: "postgres://shard",
		BridgeURL:     "http://bridge",
		BridgeToken:   "tok",
		ShardHostPort: "host:5432",
		PGUser:        "pg",
		PGPassword:    "pw",
		SQLDir:        fakeWorkerPrefix + mode,
	}
}

func selfBin(t *testing.T) string {
	t.Helper()
	exe, err := os.Executable()
	if err != nil {
		t.Fatalf("os.Executable: %v", err)
	}
	return exe
}

func mustUUID(t *testing.T) uuid.UUID {
	t.Helper()
	id, err := uuid.NewRandom()
	if err != nil {
		t.Fatalf("uuid: %v", err)
	}
	return id
}

// ─── request validation ──────────────────────────────────────────────────────

func TestProvisionRequest_RejectsNilUUID(t *testing.T) {
	err := ProvisionRealityRequest{RealityID: uuid.Nil}.Validate()
	if !errors.Is(err, ErrInvalidProvision) {
		t.Fatalf("want ErrInvalidProvision for nil uuid, got %v", err)
	}
}

func TestProvisionRequest_RejectsCohortOutOfRange(t *testing.T) {
	for _, c := range []int{-1, 100, 1000} {
		err := ProvisionRealityRequest{RealityID: mustUUID(t), DeployCohort: c}.Validate()
		if !errors.Is(err, ErrInvalidProvision) {
			t.Fatalf("cohort %d should be rejected, got %v", c, err)
		}
	}
}

func TestProvisionRequest_AcceptsCohortBoundaries(t *testing.T) {
	for _, c := range []int{0, 99} {
		if err := (ProvisionRealityRequest{RealityID: mustUUID(t), DeployCohort: c}).Validate(); err != nil {
			t.Fatalf("cohort %d should be accepted, got %v", c, err)
		}
	}
}

func TestProvisionRequest_EffectiveLocaleDefaults(t *testing.T) {
	if got := (ProvisionRealityRequest{}).EffectiveLocale(); got != DefaultProvisionLocale {
		t.Fatalf("want %q, got %q", DefaultProvisionLocale, got)
	}
	if got := (ProvisionRealityRequest{Locale: " ja-JP "}).EffectiveLocale(); got != "ja-JP" {
		t.Fatalf("want trimmed ja-JP, got %q", got)
	}
}

// ─── orchestration ───────────────────────────────────────────────────────────

type stubInvoker struct {
	out ProvisionOutcome
	err error
	got ProvisionRealityRequest
}

func (s *stubInvoker) Provision(_ context.Context, req ProvisionRealityRequest) (ProvisionOutcome, error) {
	s.got = req
	return s.out, s.err
}

func TestRunProvision_NilInvokerRefuses(t *testing.T) {
	_, err := RunProvisionReality(context.Background(),
		ProvisionRealityRequest{RealityID: mustUUID(t)}, ProvisionRealityDeps{})
	if !errors.Is(err, ErrInvalidProvision) {
		t.Fatalf("want ErrInvalidProvision, got %v", err)
	}
}

func TestRunProvision_DryRunReportsShardAndCapacity(t *testing.T) {
	id := mustUUID(t)
	inv := &stubInvoker{out: ProvisionOutcome{
		WouldProvision: true, Shard: "shard-a", DBName: "lw_reality_abc",
		Shards: []ShardSlot{{Shard: "shard-a", Used: 2, Total: 50}},
	}}
	got, err := RunProvisionReality(context.Background(),
		ProvisionRealityRequest{RealityID: id, Reason: "because", DryRun: true},
		ProvisionRealityDeps{Invoker: inv})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, want := range []string{"DRY-RUN", "shard-a", "lw_reality_abc", "2/50", "Nothing was written"} {
		if !strings.Contains(got, want) {
			t.Fatalf("summary missing %q:\n%s", want, got)
		}
	}
	if !inv.got.DryRun {
		t.Fatal("DryRun was not propagated to the invoker")
	}
}

// A dry run that finds no capacity must be an ERROR, not a cheerful summary —
// an operator reading exit 0 would schedule a provision that cannot succeed.
func TestRunProvision_DryRunNoCapacityIsError(t *testing.T) {
	inv := &stubInvoker{out: ProvisionOutcome{WouldProvision: false, Error: "no shard capacity"}}
	_, err := RunProvisionReality(context.Background(),
		ProvisionRealityRequest{RealityID: mustUUID(t), DryRun: true},
		ProvisionRealityDeps{Invoker: inv})
	if !errors.Is(err, ErrInvalidProvision) {
		t.Fatalf("want error when no capacity, got %v", err)
	}
}

// The guard against reporting a success we cannot point at.
func TestRunProvision_BlankDBNameIsError(t *testing.T) {
	inv := &stubInvoker{out: ProvisionOutcome{Shard: "shard-a", DBName: "  ", Steps: 11}}
	_, err := RunProvisionReality(context.Background(),
		ProvisionRealityRequest{RealityID: mustUUID(t)}, ProvisionRealityDeps{Invoker: inv})
	if err == nil || !strings.Contains(err.Error(), "named no database") {
		t.Fatalf("want 'named no database' error, got %v", err)
	}
}

func TestRunProvision_SuccessSummary(t *testing.T) {
	id := mustUUID(t)
	inv := &stubInvoker{out: ProvisionOutcome{Shard: "shard-a", DBName: "lw_reality_abc", Steps: 11}}
	got, err := RunProvisionReality(context.Background(),
		ProvisionRealityRequest{RealityID: id, Locale: "ja-JP", DeployCohort: 7},
		ProvisionRealityDeps{Invoker: inv})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, want := range []string{id.String(), "shard-a", "lw_reality_abc", "11 steps", "ja-JP", "cohort=7"} {
		if !strings.Contains(got, want) {
			t.Fatalf("summary missing %q:\n%s", want, got)
		}
	}
}

// ─── worker environment ──────────────────────────────────────────────────────

func TestProvisionWorkerEnv_NamesEveryMissingField(t *testing.T) {
	err := ProvisionWorkerEnv{}.Validate()
	if err == nil {
		t.Fatal("empty env must not validate")
	}
	for _, want := range []string{
		"PROVISION_META_DSN", "PROVISION_SHARD_ADMIN_DSN", "PROVISION_BRIDGE_URL",
		"PROVISION_BRIDGE_TOKEN", "PROVISION_SHARD_HOSTPORT", "PROVISION_PG_USER",
	} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error should name %s, got: %v", want, err)
		}
	}
}

// An empty password is legitimate (peer/trust auth), so it must NOT block.
func TestProvisionWorkerEnv_EmptyPasswordIsAllowed(t *testing.T) {
	e := fakeWorkerEnv("ok")
	e.PGPassword = ""
	if err := e.Validate(); err != nil {
		t.Fatalf("empty password should be allowed: %v", err)
	}
}

// The child's environment is BUILT, not inherited: an ambient PROVISION_* left
// in an operator's shell must not reach the worker, because that is how a
// command lands on the wrong Postgres.
func TestProvisionInvoker_ChildEnvIsNotInherited(t *testing.T) {
	t.Setenv("PROVISION_META_DSN", "postgres://AMBIENT-WRONG-HOST/should-not-leak")
	t.Setenv("SOME_UNRELATED_SECRET", "leak-me")

	inv := NewSubprocessProvisionInvoker(selfBin(t), fakeWorkerEnv("echo-env"))
	// echo-env dumps os.Environ() as JSON into db_name-less output, so parse raw.
	out, err := inv.Provision(context.Background(),
		ProvisionRealityRequest{RealityID: mustUUID(t), Reason: "env probe"})
	// The output is a JSON array, not a ProvisionOutcome, so a parse error is
	// expected — what we assert on is the message, which carries the dump.
	if err == nil {
		t.Fatalf("expected a parse error carrying the env dump, got outcome %+v", out)
	}
	dump := err.Error()
	if strings.Contains(dump, "AMBIENT-WRONG-HOST") {
		t.Fatal("ambient PROVISION_META_DSN leaked into the worker environment")
	}
	if strings.Contains(dump, "SOME_UNRELATED_SECRET") || strings.Contains(dump, "leak-me") {
		t.Fatal("unrelated host environment leaked into the worker")
	}
	if !strings.Contains(dump, "postgres://meta") {
		t.Fatalf("the configured DSN should have been passed; dump: %s", dump)
	}
}

// ─── subprocess exit-code contract ───────────────────────────────────────────

func TestProvisionInvoker_Exit2IsSetupFailure(t *testing.T) {
	inv := NewSubprocessProvisionInvoker(selfBin(t), fakeWorkerEnv("setup-fail"))
	_, err := inv.Provision(context.Background(),
		ProvisionRealityRequest{RealityID: mustUUID(t), Reason: "r"})
	if err == nil || !strings.Contains(err.Error(), "nothing was attempted") {
		t.Fatalf("exit 2 must surface as a setup failure, got %v", err)
	}
}

func TestProvisionInvoker_Exit1CarriesWorkerError(t *testing.T) {
	inv := NewSubprocessProvisionInvoker(selfBin(t), fakeWorkerEnv("no-capacity"))
	_, err := inv.Provision(context.Background(),
		ProvisionRealityRequest{RealityID: mustUUID(t), Reason: "r", DryRun: true})
	if err == nil || !strings.Contains(err.Error(), "no shard capacity") {
		t.Fatalf("exit 1 must carry the worker's own error text, got %v", err)
	}
}

// The worker echoes the id it acted on; reading another invocation's output as
// this one's would report a success that belongs to a different reality.
func TestProvisionInvoker_RealityIDMismatchRefused(t *testing.T) {
	inv := NewSubprocessProvisionInvoker(selfBin(t), fakeWorkerEnv("mismatch"))
	_, err := inv.Provision(context.Background(),
		ProvisionRealityRequest{RealityID: mustUUID(t), Reason: "r"})
	if err == nil || !strings.Contains(err.Error(), "but") {
		t.Fatalf("a reality_id mismatch must be refused, got %v", err)
	}
}

func TestProvisionInvoker_UnparseableOutputRefused(t *testing.T) {
	inv := NewSubprocessProvisionInvoker(selfBin(t), fakeWorkerEnv("garbage"))
	_, err := inv.Provision(context.Background(),
		ProvisionRealityRequest{RealityID: mustUUID(t), Reason: "r"})
	if err == nil || !strings.Contains(err.Error(), "unparseable") {
		t.Fatalf("garbage stdout must be refused, got %v", err)
	}
}

func TestProvisionInvoker_HappyPathParses(t *testing.T) {
	id := mustUUID(t)
	inv := NewSubprocessProvisionInvoker(selfBin(t), fakeWorkerEnv("ok"))
	out, err := inv.Provision(context.Background(),
		ProvisionRealityRequest{RealityID: id, Reason: "r"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out.DBName != "lw_reality_abc" || out.Steps != 11 || out.Shard != "shard-a" {
		t.Fatalf("outcome not parsed: %+v", out)
	}
	if out.RealityID != id.String() {
		t.Fatalf("reality id round-trip failed: %q vs %q", out.RealityID, id)
	}
}

func TestProvisionInvoker_DryRunFlagReachesWorker(t *testing.T) {
	// ok-dry only produces would_provision=true; if --dry-run were dropped the
	// fake worker would still answer, so assert through the full orchestration
	// that the dry-run summary (not the provisioned summary) comes back.
	inv := NewSubprocessProvisionInvoker(selfBin(t), fakeWorkerEnv("ok-dry"))
	got, err := RunProvisionReality(context.Background(),
		ProvisionRealityRequest{RealityID: mustUUID(t), Reason: "r", DryRun: true},
		ProvisionRealityDeps{Invoker: inv})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "DRY-RUN") || !strings.Contains(got, "2/50") {
		t.Fatalf("dry-run summary wrong:\n%s", got)
	}
}

func TestProvisionInvoker_NoBinaryConfigured(t *testing.T) {
	inv := NewSubprocessProvisionInvoker("", fakeWorkerEnv("ok"))
	_, err := inv.Provision(context.Background(),
		ProvisionRealityRequest{RealityID: mustUUID(t), Reason: "r"})
	if !errors.Is(err, ErrInvalidProvision) {
		t.Fatalf("want ErrInvalidProvision, got %v", err)
	}
}

func TestProvisionInvoker_IncompleteEnvRefusedBeforeExec(t *testing.T) {
	// Point at a binary that does not exist: if the env check did not run
	// first, this would fail with an exec error instead of the env error.
	inv := NewSubprocessProvisionInvoker("/nonexistent/worker", ProvisionWorkerEnv{MetaDSN: "x"})
	_, err := inv.Provision(context.Background(),
		ProvisionRealityRequest{RealityID: mustUUID(t), Reason: "r"})
	if err == nil || !strings.Contains(err.Error(), "env incomplete") {
		t.Fatalf("env must be validated before exec, got %v", err)
	}
}

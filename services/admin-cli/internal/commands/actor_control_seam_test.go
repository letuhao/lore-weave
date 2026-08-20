// actor_control_seam_test.go — `SC2`, the Go half of the seam contract.
//
// `D-PC-SEAM-NO-CONTRACT`. Go renders argv in `workerArgs` and unmarshals the
// reply into `ActorControlOutcome`; Rust parses that argv and emits that reply.
// Nothing compiles both, so a rename on either side keeps both unit suites green
// and breaks the live loop.
//
// This file holds Go to `contracts/actor-control-worker.contract.json`;
// `services/world-service/tests/worker_seam_contract.rs` holds Rust to the same
// file. Neither test knows about the other — they agree only by both being
// wrong about nothing.
//
// # Why reflection rather than a written list
//
// The struct's json tags ARE the Go side of the contract. A second hand-kept
// list of them in a test would be a third home, and the first thing to go stale
// when a field is added — which is the failure this whole run is closing.
// `reflect` reads what the compiler will actually use.
//
// The contract is read at RUNTIME, so a contract-only edit reds this without
// recompiling the package. That is deliberate: `go test` caches by build inputs,
// and a cached PASS over a changed contract would be a green that measured
// nothing. Run with `-count=1` when only the JSON moved.
package commands

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"

	"github.com/google/uuid"
)

type seamContract struct {
	Ops   []string `json:"ops"`
	Flags struct {
		Valued    []string `json:"valued"`
		Valueless []string `json:"valueless"`
	} `json:"flags"`
	OutcomeKeys struct {
		Always      []string `json:"always"`
		Conditional []string `json:"conditional"`
	} `json:"outcome_keys"`
	OutcomeValues struct {
		Status         []string `json:"status"`
		Outcome        []string `json:"outcome"`
		EntityIDSource []string `json:"entity_id_source"`
	} `json:"outcome_values"`
}

func loadContract(t *testing.T) seamContract {
	t.Helper()
	path := filepath.Join("..", "..", "..", "..", "contracts", "actor-control-worker.contract.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("the seam contract must be readable at %s: %v", path, err)
	}
	var c seamContract
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatalf("the seam contract must be valid JSON: %v", err)
	}
	return c
}

// A contract that parsed to nothing makes every assertion below vacuous — the
// NV-3 shape, where the scope reaching nothing is indistinguishable from the
// check passing. Floors rather than emptiness checks, so a truncated file is
// caught too.
func TestSeamContractHasSubjects(t *testing.T) {
	c := loadContract(t)
	if len(c.Ops) < 3 {
		t.Fatalf("contract declares %d op(s); the CLI has three", len(c.Ops))
	}
	if len(c.Flags.Valued) < 5 || len(c.Flags.Valueless) == 0 {
		t.Fatalf("contract flag lists look truncated: %+v", c.Flags)
	}
	if len(c.OutcomeKeys.Always) < 3 || len(c.OutcomeKeys.Conditional) < 10 {
		t.Fatalf("contract key lists look truncated: %+v", c.OutcomeKeys)
	}
}

// ── the reply ───────────────────────────────────────────────────────────────

func outcomeJSONTags(t *testing.T) []string {
	t.Helper()
	var out []string
	rt := reflect.TypeOf(ActorControlOutcome{})
	for i := range rt.NumField() {
		tag := rt.Field(i).Tag.Get("json")
		if tag == "" || tag == "-" {
			continue
		}
		out = append(out, strings.Split(tag, ",")[0])
	}
	sort.Strings(out)
	return out
}

// Reflection finding nothing would make the comparison below trivially true.
func TestTheReflectionCanSeeItsSubject(t *testing.T) {
	tags := outcomeJSONTags(t)
	if len(tags) < 15 {
		t.Fatalf("reflection found only %d json tag(s) on ActorControlOutcome: %v", len(tags), tags)
	}
}

// The struct's tags and the contract are the SAME SET, both directions.
//
// A contract key with no Go field is a value the worker sends and nobody reads.
// A Go field with no contract key is a field frozen at its zero value — the
// write-only-behaviour bug, one process over. Neither is visible to a unit test
// on either side, which is the entire reason this file exists.
func TestOutcomeTagsAreExactlyTheContract(t *testing.T) {
	c := loadContract(t)
	declared := map[string]bool{}
	for _, k := range append(append([]string{}, c.OutcomeKeys.Always...), c.OutcomeKeys.Conditional...) {
		declared[k] = true
	}
	have := map[string]bool{}
	for _, k := range outcomeJSONTags(t) {
		have[k] = true
	}

	var missing, extra []string
	for k := range declared {
		if !have[k] {
			missing = append(missing, k)
		}
	}
	for k := range have {
		if !declared[k] {
			extra = append(extra, k)
		}
	}
	sort.Strings(missing)
	sort.Strings(extra)

	if len(missing) > 0 {
		t.Errorf("the contract declares key(s) ActorControlOutcome does not read: %v — the "+
			"worker sends them and Go drops them silently", missing)
	}
	if len(extra) > 0 {
		t.Errorf("ActorControlOutcome reads key(s) the contract does not declare: %v — the "+
			"field is frozen at its zero value unless the worker emits it", extra)
	}
}

// ── the argv ────────────────────────────────────────────────────────────────

// Every flag `workerArgs` can render is declared, for every op.
//
// Iterates the ops from the CONTRACT rather than a literal list, so an op added
// to the contract and not to this test cannot pass by not being exercised.
func TestWorkerArgsRendersOnlyDeclaredFlags(t *testing.T) {
	c := loadContract(t)
	declared := map[string]bool{}
	for _, f := range append(append([]string{}, c.Flags.Valued...), c.Flags.Valueless...) {
		declared[f] = true
	}

	// One maximal request per op — every optional field populated, so no flag
	// escapes the sweep by being absent from the fixture.
	reqs := map[string]ActorControlRequest{
		"grant": {Op: OpGrantControl, RealityID: tcReality, ActorID: tcActor,
			UserRefID: tcUser, Reason: "seam", DryRun: true},
		"revoke": {Op: OpRevokeControl, RealityID: tcReality, ActorID: tcActor,
			ExpectedUserRefID: tcHeir, Reason: "seam", DryRun: true},
		"create-actor": {Op: OpCreateActor, RealityID: tcReality, EntityID: 7,
			Reason: "seam", DryRun: true},
	}

	seen := map[string]bool{}
	for _, op := range c.Ops {
		req, ok := reqs[op]
		if !ok {
			t.Fatalf("the contract declares op %q and this test has no request for it — "+
				"an op nobody exercises is an op nobody checks", op)
		}
		for _, a := range workerArgs(req) {
			if !strings.HasPrefix(a, "--") {
				continue
			}
			seen[a] = true
			if !declared[a] {
				t.Errorf("op %s renders flag %q, which the contract does not declare — the "+
					"worker will refuse it with `unknown flag`", op, a)
			}
		}
	}

	// The other direction: a declared flag no op ever renders is either dead in
	// the contract or a capability Go forgot to expose. Either way it is drift.
	for f := range declared {
		if !seen[f] {
			t.Errorf("the contract declares flag %q and no op renders it", f)
		}
	}
}

// The op constants and the contract agree, both directions.
func TestOpConstantsMatchTheContract(t *testing.T) {
	c := loadContract(t)
	have := map[string]bool{
		string(OpGrantControl): true, string(OpRevokeControl): true, string(OpCreateActor): true,
	}
	for _, op := range c.Ops {
		if !have[op] {
			t.Errorf("the contract declares op %q and admin-cli has no constant for it", op)
		}
		delete(have, op)
	}
	for op := range have {
		t.Errorf("admin-cli renders op %q and the contract does not declare it", op)
	}
}

// ── the closed-set values ───────────────────────────────────────────────────

// Every outcome word the Go summary branches on must be one the contract
// declares. `RunActorControl` reads `out.Outcome` and `out.Changed`; a word that
// drifted would fall through to a summary written for a different result.
func TestOutcomeWordsGoBranchesOnAreDeclared(t *testing.T) {
	c := loadContract(t)
	declared := map[string]bool{}
	for _, v := range c.OutcomeValues.Outcome {
		declared[v] = true
	}
	// Drive the real renderer with each declared word and assert it produces a
	// summary rather than the "named no outcome" refusal — which is what a word
	// Go does not understand would get.
	for _, word := range c.OutcomeValues.Outcome {
		req := grantReq()
		out := ActorControlOutcome{Outcome: word, Changed: word == "granted" || word == "revoked"}
		if word == "actor_created" {
			req = ActorControlRequest{Op: OpCreateActor, RealityID: tcReality, Reason: "seam"}
			out.CreatedActorID = uuid.NewString()
			out.Changed = true
		}
		if _, err := RunActorControl(t.Context(), req, ActorControlDeps{
			Invoker: &stubActorControlInvoker{out: out},
		}); err != nil {
			t.Errorf("declared outcome %q is not understood by RunActorControl: %v", word, err)
		}
	}
	if !declared["granted"] || !declared["actor_created"] {
		t.Fatalf("the contract's outcome list is missing a word this test relies on: %v",
			c.OutcomeValues.Outcome)
	}
}

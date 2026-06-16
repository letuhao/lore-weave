package runner

import (
	"context"
	"fmt"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/loreweave/foundation/tests/conformance/internal/catalog"
	"github.com/loreweave/foundation/tests/conformance/internal/verdict"
)

type fakeEnv struct {
	provides map[string]bool
	matches  map[string]bool
}

func (e fakeEnv) Provides(r string) bool { return e.provides[r] }
func (e fakeEnv) Matches(p string) bool  { return e.matches[p] }

type fakeExec struct {
	exit    int
	out     string
	err     error
	calls   int
	lastCmd []string
}

func (f *fakeExec) Run(_ context.Context, cmd []string) (int, string, error) {
	f.calls++
	f.lastCmd = cmd
	return f.exit, f.out, f.err
}

func lintCase(c catalog.Case) catalog.Case {
	c.ID = "c"
	c.Kind = catalog.KindLint
	if c.Command == nil {
		c.Command = []string{"true"}
	}
	return c
}

func TestClassifyTable(t *testing.T) {
	base := lintCase(catalog.Case{})
	fc := lintCase(catalog.Case{FailClosedOnSetupError: true})

	cases := []struct {
		name     string
		c        catalog.Case
		exit     int
		launch   error
		wantVerd verdict.Verdict
	}{
		{"exit0->pass", base, 0, nil, verdict.Pass},
		{"exit1->fail", base, 1, nil, verdict.Fail},
		{"exit2->notrun", base, 2, nil, verdict.Notrun},
		{"exit2+failclosed->fail", fc, 2, nil, verdict.Fail},
		{"launch->notrun", base, -1, errTest, verdict.Notrun},
		{"launch+failclosed->fail", fc, -1, errTest, verdict.Fail},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, _ := classify(tc.c, tc.exit, tc.launch)
			if got != tc.wantVerd {
				t.Errorf("classify = %q, want %q", got, tc.wantVerd)
			}
		})
	}
}

var errTest = errStr("boom")

type errStr string

func (e errStr) Error() string { return string(e) }

func TestRunCaseSkipWhenMatched(t *testing.T) {
	ex := &fakeExec{exit: 0}
	r := New(fakeEnv{matches: map[string]bool{"single-superuser": true}}, ex)
	c := lintCase(catalog.Case{SkipWhen: []string{"single-superuser"}})

	res := r.Run(context.Background(), []catalog.Case{c})[0]
	if res.Verdict != verdict.Skip {
		t.Errorf("want skip, got %q", res.Verdict)
	}
	if ex.calls != 0 {
		t.Error("executor must NOT run when skip_when matches")
	}
	if !strings.Contains(res.Reason, "single-superuser") {
		t.Errorf("reason should name the predicate: %q", res.Reason)
	}
}

func TestRunCaseRequiresUnmet(t *testing.T) {
	ex := &fakeExec{exit: 0}
	r := New(fakeEnv{provides: map[string]bool{}}, ex)
	c := lintCase(catalog.Case{Requires: []string{"docker"}})

	res := r.Run(context.Background(), []catalog.Case{c})[0]
	if res.Verdict != verdict.Notrun {
		t.Errorf("want notrun, got %q", res.Verdict)
	}
	if ex.calls != 0 {
		t.Error("executor must NOT run when a precondition is unmet")
	}
	if !strings.Contains(res.Reason, "docker") {
		t.Errorf("reason should name the requirement: %q", res.Reason)
	}
}

func TestRunCaseSkipBeatsRequires(t *testing.T) {
	// Both not-applicable AND missing infra → skip wins (intentional beats can't-run).
	ex := &fakeExec{exit: 0}
	r := New(fakeEnv{matches: map[string]bool{"no-provisioner": true}}, ex)
	c := lintCase(catalog.Case{SkipWhen: []string{"no-provisioner"}, Requires: []string{"docker"}})

	res := r.Run(context.Background(), []catalog.Case{c})[0]
	if res.Verdict != verdict.Skip {
		t.Errorf("skip_when must take precedence over requires; got %q", res.Verdict)
	}
}

func TestRunCasePassRunsCommand(t *testing.T) {
	ex := &fakeExec{exit: 0}
	r := New(fakeEnv{provides: map[string]bool{"docker": true}}, ex)
	c := lintCase(catalog.Case{Requires: []string{"docker"}, Command: []string{"bash", "x.sh"}})

	res := r.Run(context.Background(), []catalog.Case{c})[0]
	if res.Verdict != verdict.Pass {
		t.Errorf("want pass, got %q", res.Verdict)
	}
	if ex.calls != 1 || ex.lastCmd[0] != "bash" {
		t.Errorf("executor should run the case command, got calls=%d cmd=%v", ex.calls, ex.lastCmd)
	}
}

func TestRunCaseFailReasonIsOutputTail(t *testing.T) {
	ex := &fakeExec{exit: 1, out: "[lint] FAIL — uncovered event"}
	r := New(fakeEnv{}, ex)
	res := r.Run(context.Background(), []catalog.Case{lintCase(catalog.Case{})})[0]
	if res.Verdict != verdict.Fail {
		t.Fatalf("want fail, got %q", res.Verdict)
	}
	if !strings.Contains(res.Reason, "uncovered event") {
		t.Errorf("fail reason should carry the output tail: %q", res.Reason)
	}
}

func TestSummaryCountsAndGate(t *testing.T) {
	results := []verdict.Result{
		{ID: "a", Verdict: verdict.Pass},
		{ID: "b", Verdict: verdict.Notrun},
		{ID: "c", Verdict: verdict.Skip},
		{ID: "d", Verdict: verdict.Fail},
	}
	s := Summarize(results)
	c := s.Counts()
	if c[verdict.Pass] != 1 || c[verdict.Notrun] != 1 || c[verdict.Skip] != 1 || c[verdict.Fail] != 1 {
		t.Errorf("counts wrong: %+v", c)
	}
	if s.GateExitCode() != 1 {
		t.Error("a fail must make GateExitCode 1")
	}
	if len(s.Failed()) != 1 || s.Failed()[0].ID != "d" {
		t.Errorf("Failed() wrong: %+v", s.Failed())
	}
	if !strings.Contains(s.Render(), "1 fail") {
		t.Errorf("Render headline wrong: %q", s.Render())
	}
}

func TestSummaryGateGreenWithoutFail(t *testing.T) {
	s := Summarize([]verdict.Result{
		{ID: "a", Verdict: verdict.Pass},
		{ID: "b", Verdict: verdict.Notrun},
		{ID: "c", Verdict: verdict.Skip},
	})
	if s.GateExitCode() != 0 {
		t.Error("notrun/skip/pass only → gate must be green (0)")
	}
}

func TestOSExecutorLaunchFailure(t *testing.T) {
	// A binary that cannot be launched → launchErr != nil (cross-platform).
	_, _, err := OSExecutor{}.Run(context.Background(), []string{"this-binary-does-not-exist-xyzzy"})
	if err == nil {
		t.Error("launching a nonexistent binary must return a launch error")
	}
}

func TestOSExecutorEmptyCommand(t *testing.T) {
	_, _, err := OSExecutor{}.Run(context.Background(), nil)
	if err == nil {
		t.Error("empty command must return an error")
	}
}

func TestOutputTailTrims(t *testing.T) {
	long := strings.Repeat("x", 500)
	got := outputTail(long, 240)
	if len(got) > 240+len("…") { // 240 kept bytes + the 3-byte ellipsis marker
		t.Errorf("tail not trimmed: len=%d", len(got))
	}
	if !strings.HasPrefix(got, "…") {
		t.Errorf("trimmed tail should be marked with an ellipsis: %q", got[:6])
	}
	if outputTail("  short  ", 240) != "short" {
		t.Error("short output should be trimmed of surrounding space, not ellipsized")
	}
}

func TestClassifyKindFailsClosedByDefault(t *testing.T) {
	// go-test/rust-test exit ≥2 = build/compile failure = real breakage → fail,
	// not the lenient notrun that lint/live-probe get.
	goTest := catalog.Case{ID: "g", Kind: catalog.KindGoTest, Command: []string{"go", "test"}}
	if v, _ := classify(goTest, 2, nil); v != verdict.Fail {
		t.Errorf("go-test exit 2 (build failure) must be fail, got %q", v)
	}
	rustTest := catalog.Case{ID: "r", Kind: catalog.KindRustTest, Command: []string{"cargo", "test"}}
	if v, _ := classify(rustTest, -1, errTest); v != verdict.Fail {
		t.Errorf("rust-test launch error must be fail, got %q", v)
	}
	if v, _ := classify(lintCase(catalog.Case{}), 2, nil); v != verdict.Notrun {
		t.Errorf("lint exit 2 must stay notrun (lenient), got %q", v)
	}
}

type blockingExec struct{}

func (blockingExec) Run(ctx context.Context, _ []string) (int, string, error) {
	<-ctx.Done() // block until the per-case timeout cancels us
	return -1, "", ctx.Err()
}

func TestRunCaseTimeout(t *testing.T) {
	r := New(fakeEnv{}, blockingExec{}).WithCaseTimeout(20 * time.Millisecond)
	res := r.Run(context.Background(), []catalog.Case{lintCase(catalog.Case{})})[0]
	if res.Verdict != verdict.Notrun {
		t.Errorf("a timed-out lint case → notrun, got %q", res.Verdict)
	}
	if !strings.Contains(res.Reason, "timed out") {
		t.Errorf("reason should say timed out: %q", res.Reason)
	}
}

func TestRunCaseTimeoutFailClosed(t *testing.T) {
	// A timed-out go-test (fail-closed kind) → fail, not notrun.
	c := catalog.Case{ID: "t", Kind: catalog.KindGoTest, Command: []string{"x"}}
	r := New(fakeEnv{}, blockingExec{}).WithCaseTimeout(20 * time.Millisecond)
	res := r.Run(context.Background(), []catalog.Case{c})[0]
	if res.Verdict != verdict.Fail {
		t.Errorf("a timed-out fail-closed (go-test) case → fail, got %q", res.Verdict)
	}
}

func shellExit(code int) []string {
	if runtime.GOOS == "windows" {
		return []string{"cmd", "/c", fmt.Sprintf("exit %d", code)}
	}
	return []string{"sh", "-c", fmt.Sprintf("exit %d", code)}
}

func TestOSExecutorRealExitCodes(t *testing.T) {
	for _, code := range []int{0, 1, 2} {
		got, _, err := OSExecutor{}.Run(context.Background(), shellExit(code))
		if err != nil {
			t.Fatalf("exit %d: unexpected launch error: %v", code, err)
		}
		if got != code {
			t.Errorf("OSExecutor exit code = %d, want %d", got, code)
		}
	}
}

func TestOSEnvironmentProvides(t *testing.T) {
	env := OSEnvironment{}
	t.Setenv("DATABASE_URL", "")
	if env.Provides("database_url") {
		t.Error("empty DATABASE_URL → not provided")
	}
	t.Setenv("DATABASE_URL", "postgres://x")
	if !env.Provides("database_url") {
		t.Error("set DATABASE_URL → provided")
	}
	if env.Provides("totally-unknown-req") {
		t.Error("unknown requirement → not provided (fail-safe → notrun)")
	}
}

func TestOSEnvironmentMatches(t *testing.T) {
	env := OSEnvironment{}
	t.Setenv("CONFORMANCE_SINGLE_SUPERUSER", "1")
	if !env.Matches("single-superuser") {
		t.Error("CONFORMANCE_SINGLE_SUPERUSER=1 → matches")
	}
	t.Setenv("CONFORMANCE_SINGLE_SUPERUSER", "")
	if env.Matches("single-superuser") {
		t.Error("unset → no match")
	}
	if env.Matches("totally-unknown-pred") {
		t.Error("unknown predicate → no match (case still runs)")
	}
}

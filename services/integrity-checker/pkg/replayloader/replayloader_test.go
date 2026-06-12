package replayloader

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/tablemap"
)

// fakeRunner records the last invocation and returns a canned stdout / error.
type fakeRunner struct {
	gotDSN  string
	gotArgs []string
	out     []byte
	err     error
}

func (f *fakeRunner) Run(_ context.Context, dsn string, args []string) ([]byte, error) {
	f.gotDSN = dsn
	f.gotArgs = args
	return f.out, f.err
}

func argValue(args []string, flag string) string {
	for i, a := range args {
		if a == flag && i+1 < len(args) {
			return args[i+1]
		}
	}
	return ""
}

func argValues(args []string, flag string) []string {
	var out []string
	for i, a := range args {
		if a == flag && i+1 < len(args) {
			out = append(out, args[i+1])
		}
	}
	return out
}

func baseReq() ReplayRequest {
	return ReplayRequest{
		RealityID:       uuid.MustParse("00000000-0000-0000-0000-000000000001"),
		DSN:             "postgres://u:p@h/db",
		Projection:      "pc_inventory_projection",
		BoundaryEventID: uuid.MustParse("00000000-0000-0000-0000-0000000000aa"),
		Owning:          []tablemap.OwningAggregate{{Type: "pc", ID: "pc-1"}},
		PK:              map[string]string{"pc_id": "pc-1", "item_code": "sword"},
	}
}

func TestReplay_BuildsArgsAndPassesDSNAsEnv(t *testing.T) {
	fr := &fakeRunner{out: []byte(`{"found":true,"events_replayed":4,"status":"ok","payload":{"quantity":3}}`)}
	l, err := New(fr)
	if err != nil {
		t.Fatal(err)
	}
	res, err := l.Replay(context.Background(), baseReq())
	if err != nil {
		t.Fatalf("Replay: %v", err)
	}
	// DSN goes via the runner (→ REALITY_DB_URL), NOT the arg vector.
	if fr.gotDSN != "postgres://u:p@h/db" {
		t.Errorf("dsn not passed to runner: %q", fr.gotDSN)
	}
	for _, a := range fr.gotArgs {
		if strings.Contains(a, "postgres://") {
			t.Errorf("DSN leaked into args: %v", fr.gotArgs)
		}
	}
	if argValue(fr.gotArgs, "--reality-id") != "00000000-0000-0000-0000-000000000001" {
		t.Errorf("reality-id: %v", fr.gotArgs)
	}
	if argValue(fr.gotArgs, "--projection") != "pc_inventory_projection" {
		t.Errorf("projection: %v", fr.gotArgs)
	}
	if argValue(fr.gotArgs, "--boundary-event-id") != "00000000-0000-0000-0000-0000000000aa" {
		t.Errorf("boundary: %v", fr.gotArgs)
	}
	if got := argValues(fr.gotArgs, "--aggregate"); len(got) != 1 || got[0] != "pc:pc-1" {
		t.Errorf("aggregate: %v", got)
	}
	// PK is a JSON object carrying both composite columns.
	pk := argValue(fr.gotArgs, "--pk")
	if !strings.Contains(pk, `"pc_id":"pc-1"`) || !strings.Contains(pk, `"item_code":"sword"`) {
		t.Errorf("pk json: %q", pk)
	}
	// Result parsed.
	if !res.Found || res.EventsReplayed != 4 || res.Status != "ok" {
		t.Errorf("result: %+v", res)
	}
	if skip, _ := res.Skippable(); skip {
		t.Error("ok+events>0+found must not be skippable")
	}
}

func TestReplay_CrossAggregate(t *testing.T) {
	fr := &fakeRunner{out: []byte(`{"found":true,"events_replayed":7,"status":"ok","payload":{}}`)}
	l, _ := New(fr)
	req := baseReq()
	req.Projection = "npc_session_memory_projection"
	req.Owning = []tablemap.OwningAggregate{{Type: "session", ID: "s-9"}, {Type: "npc", ID: "n-3"}}
	req.PK = map[string]string{"npc_id": "n-3", "session_id": "s-9"}
	if _, err := l.Replay(context.Background(), req); err != nil {
		t.Fatal(err)
	}
	aggs := argValues(fr.gotArgs, "--aggregate")
	if len(aggs) != 2 || aggs[0] != "session:s-9" || aggs[1] != "npc:n-3" {
		t.Errorf("cross-aggregate flags: %v", aggs)
	}
}

func TestReplay_SkippableCases(t *testing.T) {
	cases := []struct {
		name string
		out  string
		skip bool
	}{
		{"replay error", `{"found":false,"events_replayed":0,"status":"error","error":"connect refused"}`, true},
		{"zero events", `{"found":false,"events_replayed":0,"status":"ok"}`, true},
		{"orphan row (found false but events>0)", `{"found":false,"events_replayed":5,"status":"ok"}`, false},
		{"clean", `{"found":true,"events_replayed":5,"status":"ok","payload":{}}`, false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			fr := &fakeRunner{out: []byte(c.out)}
			l, _ := New(fr)
			res, err := l.Replay(context.Background(), baseReq())
			if err != nil {
				t.Fatal(err)
			}
			if skip, _ := res.Skippable(); skip != c.skip {
				t.Errorf("Skippable()=%v want %v (%+v)", skip, c.skip, res)
			}
		})
	}
}

func TestReplay_RunErrorIsHardError(t *testing.T) {
	fr := &fakeRunner{err: errors.New("exit status 2")}
	l, _ := New(fr)
	if _, err := l.Replay(context.Background(), baseReq()); err == nil {
		t.Fatal("a non-zero bin exit must be a hard error")
	}
}

func TestReplay_BadJSONIsError(t *testing.T) {
	fr := &fakeRunner{out: []byte("not json")}
	l, _ := New(fr)
	if _, err := l.Replay(context.Background(), baseReq()); err == nil {
		t.Fatal("unparseable stdout must error")
	}
}

func TestBuildArgsValidation(t *testing.T) {
	bad := []func(*ReplayRequest){
		func(r *ReplayRequest) { r.Projection = "" },
		func(r *ReplayRequest) { r.Owning = nil },
		func(r *ReplayRequest) { r.PK = nil },
		func(r *ReplayRequest) { r.Owning = []tablemap.OwningAggregate{{Type: "pc", ID: ""}} },
	}
	for i, mut := range bad {
		req := baseReq()
		mut(&req)
		if _, err := buildArgs(req); err == nil {
			t.Errorf("case %d: expected validation error", i)
		}
	}
}

func TestNewRejectsNilRunner(t *testing.T) {
	if _, err := New(nil); err == nil {
		t.Fatal("New(nil) must error")
	}
}

func TestExecRunnerRejectsEmptyBinPath(t *testing.T) {
	if _, err := (ExecRunner{}).Run(context.Background(), "dsn", []string{"--x"}); err == nil {
		t.Fatal("empty BinPath must error")
	}
}

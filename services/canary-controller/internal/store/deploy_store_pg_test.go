package store

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
)

func TestParseHistory(t *testing.T) {
	if h, err := parseHistory(nil); err != nil || h != nil {
		t.Fatalf("nil -> (nil,nil), got (%v,%v)", h, err)
	}
	if h, err := parseHistory([]byte("[]")); err != nil || len(h) != 0 {
		t.Fatalf("empty array -> 0 entries, got (%v,%v)", h, err)
	}
	h, err := parseHistory([]byte(`[{"stage":1,"at":"2026-06-03T00:00:00Z","reason":"x"}]`))
	if err != nil || len(h) != 1 || h[0].Stage != 1 {
		t.Fatalf("valid -> 1 entry stage 1, got (%v,%v)", h, err)
	}
	if _, err := parseHistory([]byte("{not json")); err == nil {
		t.Fatal("bad JSON must error (a corrupt history must not read as empty)")
	}
}

func TestStageEnteredAt(t *testing.T) {
	started := time.Date(2026, 6, 3, 8, 0, 0, 0, time.UTC)
	s1 := "2026-06-03T09:00:00Z"
	s1b := "2026-06-03T10:00:00Z"
	hist := []historyEntry{
		{Stage: 1, At: s1, Reason: "to 1"},
		{Stage: 2, At: "2026-06-03T09:30:00Z", Reason: "to 2"},
		{Stage: 1, At: s1b, Reason: "re-enter 1"}, // most recent stage-1 entry wins
	}
	got := stageEnteredAt(hist, 1, started)
	if want, _ := time.Parse(time.RFC3339, s1b); !got.Equal(want) {
		t.Fatalf("stage 1 -> most recent entry %s, got %s", s1b, got)
	}
	// No matching entry -> started_at (stage 0 case).
	if got := stageEnteredAt(hist, 0, started); !got.Equal(started) {
		t.Fatalf("no entry -> started_at, got %s", got)
	}
	// Unparseable timestamp -> started_at fallback.
	bad := []historyEntry{{Stage: 3, At: "not-a-time", Reason: "x"}}
	if got := stageEnteredAt(bad, 3, started); !got.Equal(started) {
		t.Fatalf("bad ts -> started_at, got %s", got)
	}
}

func TestBaselineBurn(t *testing.T) {
	if got := baselineBurn(nil); got != 0 {
		t.Fatalf("no history -> 0, got %v", got)
	}
	if got := baselineBurn([]historyEntry{{Stage: 0}, {Stage: 1}}); got != 0 {
		t.Fatalf("no baseline captured -> 0, got %v", got)
	}
	hist := []historyEntry{{Stage: 0, BaselineBurn: 0.05}, {Stage: 1, BaselineBurn: 0.99}}
	if got := baselineBurn(hist); got != 0.05 {
		t.Fatalf("first positive baseline wins -> 0.05, got %v", got)
	}
}

func TestBuildAdvanceIntent(t *testing.T) {
	at := time.Date(2026, 6, 3, 11, 0, 0, 0, time.UTC)
	prior := []historyEntry{{Stage: 1, At: "2026-06-03T10:00:00Z", Reason: "to 1"}}
	in, err := buildAdvanceIntent("dep-1", 1, canary.Stage10pct, at, "advancing", prior)
	if err != nil {
		t.Fatal(err)
	}
	if in.Table != "deploy_audit" || in.Operation != meta.OpUpdate {
		t.Fatalf("table/op: %s/%s", in.Table, in.Operation)
	}
	if in.PK["deploy_id"] != "dep-1" {
		t.Fatalf("PK: %v", in.PK)
	}
	if in.ExpectedBefore["canary_stage"] != 1 {
		t.Fatalf("CAS must expect prior stage 1, got %v", in.ExpectedBefore["canary_stage"])
	}
	// CAS must ALSO guard rolled_back=false + completed_at IS NULL so a tick
	// cannot advance a deploy a concurrent abort/complete already finalized
	// (those change rolled_back/completed_at, NOT canary_stage).
	if in.ExpectedBefore["rolled_back"] != false {
		t.Fatalf("advance CAS must expect rolled_back=false, got %v", in.ExpectedBefore["rolled_back"])
	}
	if v, ok := in.ExpectedBefore["completed_at"]; !ok || v != nil {
		t.Fatalf("advance CAS must expect completed_at IS NULL (present+nil), got present=%t val=%v", ok, v)
	}
	if in.NewValues["canary_stage"] != int(canary.Stage10pct) {
		t.Fatalf("new stage: %v", in.NewValues["canary_stage"])
	}
	if in.Actor.Type != meta.ActorService || in.Actor.ID != "canary-controller" {
		t.Fatalf("actor: %v/%s", in.Actor.Type, in.Actor.ID)
	}
	// canary_history must be JSON bytes with the appended entry (prior preserved).
	raw, ok := in.NewValues["canary_history"].([]byte)
	if !ok {
		t.Fatalf("canary_history must be []byte (->jsonb), got %T", in.NewValues["canary_history"])
	}
	var got []historyEntry
	if err := json.Unmarshal(raw, &got); err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[1].Stage != int(canary.Stage10pct) || got[1].At != at.UTC().Format(time.RFC3339) {
		t.Fatalf("history append wrong: %+v", got)
	}
	// Builder must not mutate the caller's slice.
	if len(prior) != 1 {
		t.Fatalf("prior history mutated: %+v", prior)
	}
}

func TestBuildRollbackIntent(t *testing.T) {
	at := time.Date(2026, 6, 3, 12, 0, 0, 0, time.UTC)
	in := buildRollbackIntent("dep-2", "burn breach", at)
	if in.NewValues["rolled_back"] != true {
		t.Fatalf("rolled_back: %v", in.NewValues["rolled_back"])
	}
	if in.NewValues["rollback_reason"] != "burn breach" {
		t.Fatalf("reason: %v", in.NewValues["rollback_reason"])
	}
	if _, ok := in.NewValues["completed_at"]; !ok {
		t.Fatal("completed_at must be set (CHECK completed_after_started)")
	}
	// CAS on rolled_back=false -> idempotent abort (a 2nd abort matches 0 rows).
	if in.ExpectedBefore["rolled_back"] != false {
		t.Fatalf("CAS rolled_back: %v", in.ExpectedBefore["rolled_back"])
	}
}

func TestBuildCompleteIntent(t *testing.T) {
	at := time.Date(2026, 6, 3, 13, 0, 0, 0, time.UTC)
	in := buildCompleteIntent("dep-3", at)
	if _, ok := in.NewValues["completed_at"]; !ok {
		t.Fatal("completed_at must be set")
	}
	// ExpectedBefore must carry completed_at=nil so the builder renders IS NULL
	// (only complete a not-yet-complete row) — the KEY must be present.
	v, ok := in.ExpectedBefore["completed_at"]
	if !ok || v != nil {
		t.Fatalf("CAS completed_at must be present and nil, got present=%t val=%v", ok, v)
	}
}

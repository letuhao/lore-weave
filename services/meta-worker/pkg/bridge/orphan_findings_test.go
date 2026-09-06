package bridge

import (
	"strings"
	"testing"

	"github.com/google/uuid"
)

// deriveFindingReality is the decision this endpoint exists to get right: it
// turns (class, id) into the reality_id column, and every pair it emits must
// satisfy the table's CHECK constraints.
//
// Tested up front rather than after a review asks for it. The equivalent
// decision for W6 (deriveOwner) shipped with NO test and NO bite -- replacing
// its whole body with a constant left the entire Go suite green -- and every
// bite that did exist covered the transport rather than the decision.

const untrackedClass = "orphan_untracked_database"

func TestDeriveFindingReality_UntrackedCarriesNoReality(t *testing.T) {
	got, err := deriveFindingReality(untrackedClass, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != nil {
		t.Fatalf("an untracked database must map to SQL NULL, got %v", got)
	}
}

// The correspondence in the other direction: an untracked database that names a
// reality is a contradiction, and the DB would reject it with a constraint name
// far from the cause.
func TestDeriveFindingReality_UntrackedWithARealityIsRefused(t *testing.T) {
	_, err := deriveFindingReality(untrackedClass, uuid.New().String())
	if err == nil {
		t.Fatal("an untracked database cannot carry a reality_id")
	}
	if !strings.Contains(err.Error(), "no registry row claims") {
		t.Fatalf("the error should explain the contradiction, got: %v", err)
	}
}

func TestDeriveFindingReality_TrackedClassesRequireAReality(t *testing.T) {
	for _, class := range []string{
		"orphan_partial_provision", "orphan_missing_database", "orphan_drop_eligible",
	} {
		if _, err := deriveFindingReality(class, ""); err == nil {
			t.Fatalf("%s without a reality_id must be refused", class)
		}
		id := uuid.New()
		got, err := deriveFindingReality(class, id.String())
		if err != nil {
			t.Fatalf("%s with a reality_id: %v", class, err)
		}
		if got != id {
			t.Fatalf("%s: reality_id did not round-trip: %v", class, got)
		}
	}
}

func TestDeriveFindingReality_RejectsMalformedAndNil(t *testing.T) {
	if _, err := deriveFindingReality("orphan_partial_provision", "not-a-uuid"); err == nil {
		t.Fatal("a malformed reality_id must be refused")
	}
	_, err := deriveFindingReality("orphan_partial_provision", uuid.Nil.String())
	if err == nil || !strings.Contains(err.Error(), "nil UUID") {
		t.Fatalf("the nil UUID must be refused by name, got: %v", err)
	}
}

// Whatever the input, the emitted pair must be one the table accepts. This is
// the property; the cases above are its instances.
func TestDeriveFindingReality_NeverEmitsAPairTheTableRejects(t *testing.T) {
	id := uuid.New().String()
	for _, tc := range []struct{ class, raw string }{
		{untrackedClass, ""},
		{"orphan_partial_provision", id},
		{"orphan_missing_database", id},
		{"orphan_drop_eligible", id},
	} {
		got, err := deriveFindingReality(tc.class, tc.raw)
		if err != nil {
			t.Fatalf("%s: %v", tc.class, err)
		}
		if tc.class == untrackedClass && got != nil {
			t.Fatalf("%s must emit NULL (untracked_has_no_reality)", tc.class)
		}
		if tc.class != untrackedClass && got == nil {
			t.Fatalf("%s must emit a uuid (tracked_has_a_reality)", tc.class)
		}
	}
}

// ─── the HTTP surface ────────────────────────────────────────────────────────

func TestRecordOrphans_RequiresShardHost(t *testing.T) {
	f := &fakeReg{}
	rec := do(srv(t, f, &fakeAudit{}), tok, "/internal/provisioner/record-orphans", `{"findings":[]}`)
	if rec.Code != 400 {
		t.Fatalf("want 400 without shard_host, got %d", rec.Code)
	}
	if f.orphanCalls != 0 {
		t.Fatal("a malformed request must not reach the registrar")
	}
}

// An EMPTY finding list is the "this shard is clean" message, and it is the one
// that clears stale rows. Rejecting it would leave a healed shard showing old
// findings forever.
func TestRecordOrphans_EmptyFindingsIsValid(t *testing.T) {
	f := &fakeReg{orphanCleared: 3}
	rec := do(srv(t, f, &fakeAudit{}), tok, "/internal/provisioner/record-orphans",
		`{"shard_host":"pg-shard-0.internal","findings":[]}`)
	if rec.Code != 200 {
		t.Fatalf("want 200 for a clean shard, got %d: %s", rec.Code, rec.Body.String())
	}
	if f.orphanCalls != 1 {
		t.Fatalf("the registrar must still reconcile, calls=%d", f.orphanCalls)
	}
	if !strings.Contains(rec.Body.String(), `"cleared":3`) {
		t.Fatalf("the response should report what it cleared: %s", rec.Body.String())
	}
}

func TestRecordOrphans_UnauthorizedIsRefused(t *testing.T) {
	f := &fakeReg{}
	rec := do(srv(t, f, &fakeAudit{}), "wrong-token", "/internal/provisioner/record-orphans",
		`{"shard_host":"h","findings":[]}`)
	if rec.Code != 401 {
		t.Fatalf("want 401, got %d", rec.Code)
	}
	if f.orphanCalls != 0 {
		t.Fatal("an unauthenticated call must not reach the registrar")
	}
}

func TestRecordOrphans_PayloadReachesTheRegistrar(t *testing.T) {
	f := &fakeReg{}
	id := uuid.New().String()
	do(srv(t, f, &fakeAudit{}), tok, "/internal/provisioner/record-orphans",
		`{"shard_host":"pg-shard-0.internal","findings":[`+
			`{"db_name":"lw_reality_abc","finding_class":"orphan_partial_provision","reality_id":"`+id+`"}]}`)
	if f.orphanCalls != 1 {
		t.Fatalf("registrar calls=%d", f.orphanCalls)
	}
	got := f.lastOrphanReq
	if got.ShardHost != "pg-shard-0.internal" || len(got.Findings) != 1 {
		t.Fatalf("payload did not arrive intact: %+v", got)
	}
	if got.Findings[0].DBName != "lw_reality_abc" || got.Findings[0].RealityID != id {
		t.Fatalf("finding fields did not arrive intact: %+v", got.Findings[0])
	}
}

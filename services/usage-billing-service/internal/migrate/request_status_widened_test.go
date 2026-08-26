package migrate

import (
	"strings"
	"testing"
)

// A write that ALWAYS fails, silently, at scale.
//
// The producer (provider-registry-service) emits six terminal outcomes; the CHECK permitted three.
// Every row carrying one of the other three was rejected by Postgres and lost — the INSERT carries
// ON CONFLICT DO NOTHING, so the violation surfaced only in the postgres log. Measured against the
// running database on 2026-08-26: 65,847 rejected INSERTs in ONE two-hour window, 775,146 'failed'
// and 16,851 'cancelled' across 24h, and usage_logs holding ZERO rows of either value because none
// could ever be written. A failed or cancelled LLM request still consumed provider tokens up to the
// point it stopped, and those rows ARE the usage and billing record.

// theSixOutcomes is the producer's DECLARED set, not the two that happened to appear in a log
// window. Widening to what was observed would fix the instance and leave the class alive under the
// next name.
var theSixOutcomes = []string{
	"success", "provider_error", "billing_rejected", // what the CHECK already allowed
	"failed", "cancelled", "aborted", // what it silently discarded
}

func TestTheCheckAdmitsEveryOutcomeTheProducerEmits(t *testing.T) {
	i := strings.Index(schemaSQL, "usage_logs_request_status_check")
	if i < 0 {
		t.Fatal("no request_status constraint in the schema at all")
	}
	seg := schemaSQL[i:]
	for _, s := range theSixOutcomes {
		if !strings.Contains(seg, "'"+s+"'") {
			t.Errorf("request_status cannot be %q — rows carrying it are rejected and lost", s)
		}
	}
}

func TestTheWideningIsAnALTERNotAnEditToTheCreateTable(t *testing.T) {
	// The original CHECK lives inside CREATE TABLE IF NOT EXISTS, so editing it changes NOTHING on
	// a database that already has the table. That is the same silent no-op by which a fix lives in
	// the source and is absent from the server.
	//🔴 THE FIRST VERSION OF THIS GUARD PASSED ON A COMMENTED-OUT ALTER, and its own
	// falsifier caught that: prefixing the line with "--" left the substring intact and the test
	// green. A guard satisfied by SQL the database never executes is worse than no guard, because
	// it reports the fix as present. Match the statement at the START of a line instead.
	found := false
	for _, line := range strings.Split(schemaSQL, "\n") {
		if strings.HasPrefix(strings.TrimSpace(line),
			"ALTER TABLE usage_logs ADD CONSTRAINT usage_logs_request_status_check") {
			found = true
			break
		}
	}
	if !found {
		t.Fatal("the widening is not an EXECUTABLE ALTER — it will not move an existing database")
	}
}

func TestTheAlterIsGuardedSoItRevalidatesONCE(t *testing.T) {
	// DROP + ADD re-validates the whole table. Unguarded it would do that on every boot, which is
	// a full scan of the usage log on each restart.
	i := strings.Index(schemaSQL, "usage_logs_request_status_check")
	seg := schemaSQL[max(0, i-900) : i+900]
	if !strings.Contains(seg, "IF NOT EXISTS (") || !strings.Contains(seg, "pg_constraint") {
		t.Fatal("the ALTER is not guarded by the constraint's own current definition")
	}
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// actor_control_trigger_test.go — the ASSERTED TRIGGER for `D-PC-AGENT`.
//
// This file is not a test of behaviour. It is a deferral that reds when its own
// subject arrives, which is the shape `scripts/deferral-gate.py` asks for and
// the shape `D-PC-AGENT`'s row promised and did not deliver.
//
// # What is deferred
//
// Whether a controller can be an AGENT — an LLM driving an actor rather than a
// human with a GUI. The PO deferred it to the AI feature: *"not decide yet but
// we need agent runtime, state machine and more."* Migration `034` sealed the
// framing as *"a human with a GUI driving an actor"*, and whether a non-human
// driver is a principal with its own `user_ref_id` or wants a `controller_kind`
// column is that feature's call.
//
// # Why the trigger is a COLUMN COUNT and not something cleverer
//
// The wake-up is *"the first non-human principal appearing in
// actor_control_binding"*, and there is no way to assert that directly: nothing
// in the schema distinguishes a human `user_ref_id` from any other. But a
// non-human principal cannot arrive silently either — it has to announce itself
// in the schema, as a `controller_kind`, a `principal_type`, an `agent_id`, or
// a sibling table joined to this one. So the trigger asserts the column set the
// deferral was taken against: **six columns, and the moment there is a seventh,
// someone is changing what a driver IS and must re-read the row.**
//
// It is deliberately over-broad. A column added for an unrelated reason also
// reds it, and that is the correct trade: the cost is one developer reading a
// deferral row that turns out not to apply, and the cost of the alternative is
// the row being forgotten — which is exactly what happened. `D-PC-AGENT` said
// *"it must not be prose-only… the trigger goes in with `P1`"*; `P1` shipped
// 2026-08-14 with no trigger, and nothing noticed for six days because the id
// was not even in a form `deferral-gate.py` could see (`PC-` never matched its
// `D-` pattern).
//
// # Why it reads the MIGRATION and not a live database
//
// It must red in CI, on a checkout, with no Postgres. The migration files are
// the declaration; a live database would additionally require the stack and
// would then be asserting what someone applied rather than what the repo says.
package bridge

import (
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"
)

// The columns `D-PC-AGENT` was deferred against, from `034` (the CREATE TABLE)
// plus `041` (which added `binding_id` when the PK was repaired).
var actorControlBindingColumnsAtDeferral = []string{
	"actor_id",
	"binding_id",
	"created_at",
	"reality_id",
	"revoked_at",
	"user_ref_id",
}

func TestANonHumanPrincipalWouldWakeDPCAgent(t *testing.T) {
	got := actorControlBindingColumns(t)

	want := append([]string(nil), actorControlBindingColumnsAtDeferral...)
	sort.Strings(want)
	sort.Strings(got)

	if strings.Join(got, ",") == strings.Join(want, ",") {
		return // the deferral still holds
	}

	added, removed := diff(want, got)
	t.Fatalf(
		"`actor_control_binding` no longer has the columns D-PC-AGENT was deferred against.\n"+
			"  added:   %v\n  removed: %v\n\n"+
			"This test is a DEFERRAL TRIGGER, not a schema lock. If this change introduces a "+
			"non-human principal — a controller_kind, a principal_type, an agent id — then "+
			"D-PC-AGENT is DUE: decide whether an agent is a principal with its own user_ref_id "+
			"or a new column, and close the row in "+
			"docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md. If the column is unrelated, add it "+
			"to actorControlBindingColumnsAtDeferral and say in the commit message why the "+
			"deferral is untouched.",
		added, removed)
}

// Non-vacuity: the extractor must actually find the table, or the assertion
// above compares two empty lists and passes forever. This is the `NV-3` shape —
// a check whose scope silently reaches nothing — and it is the one that would
// make the whole file decoration.
func TestTheTriggerCanSeeItsSubject(t *testing.T) {
	cols := actorControlBindingColumns(t)
	if len(cols) == 0 {
		t.Fatal("the extractor found NO columns — the trigger above cannot fail, " +
			"which makes it worse than absent (it reports coverage it does not have)")
	}
	// The one column whose presence IS the deferral's subject matter: a binding
	// names WHO drives, and that is the field an agent principal would change.
	if !contains(cols, "user_ref_id") {
		t.Fatalf("the extractor is reading the wrong table: %v", cols)
	}
}

var (
	createRe  = regexp.MustCompile(`(?is)CREATE TABLE IF NOT EXISTS actor_control_binding\s*\((.*?)\n\);`)
	addColRe  = regexp.MustCompile(`(?i)ADD COLUMN(?:\s+IF NOT EXISTS)?\s+([a-z_][a-z0-9_]*)`)
	dropColRe = regexp.MustCompile(`(?i)DROP COLUMN(?:\s+IF EXISTS)?\s+([a-z_][a-z0-9_]*)`)
	colRe     = regexp.MustCompile(`(?im)^\s*([a-z_][a-z0-9_]*)\s+(?:UUID|TIMESTAMPTZ|TEXT|BOOLEAN|INTEGER|BIGINT|SMALLINT|JSONB|NUMERIC)\b`)
)

// actorControlBindingColumns replays every meta migration in order and returns
// the column set they leave behind.
func actorControlBindingColumns(t *testing.T) []string {
	t.Helper()
	dir := filepath.Join("..", "..", "..", "..", "migrations", "meta")
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("read %s: %v", dir, err)
	}
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".up.sql") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names) // numeric prefixes sort lexicographically here

	cols := map[string]bool{}
	for _, n := range names {
		b, err := os.ReadFile(filepath.Join(dir, n))
		if err != nil {
			t.Fatalf("read %s: %v", n, err)
		}
		sql := string(b)
		if m := createRe.FindStringSubmatch(sql); m != nil {
			for _, c := range colRe.FindAllStringSubmatch(m[1], -1) {
				cols[c[1]] = true
			}
		}
		// ALTERs are only counted when they name this table, so an unrelated
		// migration's ADD COLUMN cannot leak in.
		for _, stmt := range strings.Split(sql, ";") {
			if !strings.Contains(strings.ToLower(stmt), "actor_control_binding") {
				continue
			}
			for _, c := range addColRe.FindAllStringSubmatch(stmt, -1) {
				cols[c[1]] = true
			}
			for _, c := range dropColRe.FindAllStringSubmatch(stmt, -1) {
				delete(cols, c[1])
			}
		}
	}
	out := make([]string, 0, len(cols))
	for c := range cols {
		out = append(out, c)
	}
	sort.Strings(out)
	return out
}

func diff(want, got []string) (added, removed []string) {
	w, g := map[string]bool{}, map[string]bool{}
	for _, s := range want {
		w[s] = true
	}
	for _, s := range got {
		g[s] = true
	}
	for _, s := range got {
		if !w[s] {
			added = append(added, s)
		}
	}
	for _, s := range want {
		if !g[s] {
			removed = append(removed, s)
		}
	}
	return
}

func contains(xs []string, s string) bool {
	for _, x := range xs {
		if x == s {
			return true
		}
	}
	return false
}

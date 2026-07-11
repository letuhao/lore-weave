package api

import (
	"strings"
	"testing"
)

func sysRow(workflows ...string) ModeBindingRow {
	return ModeBindingRow{Tier: "system", InjectWorkflows: workflows}
}

func TestMergeModeBindings_NoRowsIsNil(t *testing.T) {
	// No tier declares anything ⇒ nil ⇒ the consumer behaves exactly as it did
	// before WS-3 existed. A zero-valued binding here would be a silent behavior
	// change on every turn of every mode with no row.
	if got := mergeModeBindings("write", nil); got != nil {
		t.Fatalf("expected nil for no rows, got %+v", got)
	}
}

func TestMergeModeBindings_UnionsAcrossTiers(t *testing.T) {
	got := mergeModeBindings("write", []ModeBindingRow{
		{Tier: "system", InjectSkills: []string{"plan_forge"}, InjectWorkflows: []string{"vision-to-book"}},
		{Tier: "user", InjectSkills: []string{"translation"}, SeedToolCategories: []string{"translation"}},
		{Tier: "book", InjectWorkflows: []string{"entity-triage"}},
	})
	if got == nil {
		t.Fatal("expected a binding")
	}
	if strings.Join(got.InjectSkills, ",") != "plan_forge,translation" {
		t.Fatalf("skills not unioned in tier order: %v", got.InjectSkills)
	}
	if strings.Join(got.InjectWorkflows, ",") != "vision-to-book,entity-triage" {
		t.Fatalf("workflows not unioned in tier order: %v", got.InjectWorkflows)
	}
	if strings.Join(got.SeedToolCategories, ",") != "translation" {
		t.Fatalf("categories not unioned: %v", got.SeedToolCategories)
	}
	if len(got.Sources) != 3 {
		t.Fatalf("every contributing tier must be visible in sources, got %v", got.Sources)
	}
}

// The reason disable_workflows exists at all: a pure union would leave a user unable to
// turn OFF a System pin, which makes the "setting" a global flag in disguise (a
// translator must be able to drop the co-writer rail). The subtraction runs LAST.
func TestMergeModeBindings_UserVetoesSystemPin(t *testing.T) {
	got := mergeModeBindings("write", []ModeBindingRow{
		sysRow("vision-to-book"),
		{Tier: "user", DisableWorkflows: []string{"vision-to-book"}},
	})
	if got == nil {
		t.Fatal("expected a binding")
	}
	if len(got.InjectWorkflows) != 0 {
		t.Fatalf("user's disable must veto the System pin, still pinned: %v", got.InjectWorkflows)
	}
	// The veto must remain INSPECTABLE — the user has to be able to see why the rail is
	// off (effective value + source tier), not just observe an empty list.
	if got.Sources["system"] == nil || len(got.Sources["system"].InjectWorkflows) != 1 {
		t.Fatalf("the System pin must stay visible in sources: %+v", got.Sources)
	}
}

func TestMergeModeBindings_BookVetoesForOneBookOnly(t *testing.T) {
	// A book-tier veto (this book is a translation project) drops the pin, while the
	// System row is untouched for every other book — proven by the sources record.
	got := mergeModeBindings("write", []ModeBindingRow{
		sysRow("vision-to-book"),
		{Tier: "book", DisableWorkflows: []string{"vision-to-book"}},
	})
	if len(got.InjectWorkflows) != 0 {
		t.Fatalf("book veto must drop the pin: %v", got.InjectWorkflows)
	}
	if got.Sources["book"] == nil || got.Sources["book"].DisableWorkflows[0] != "vision-to-book" {
		t.Fatalf("book veto must be visible in sources: %+v", got.Sources)
	}
}

func TestMergeModeBindings_DedupsAndDropsBlanks(t *testing.T) {
	got := mergeModeBindings("write", []ModeBindingRow{
		sysRow("vision-to-book"),
		{Tier: "user", InjectWorkflows: []string{"vision-to-book", " ", "entity-triage"}},
	})
	if strings.Join(got.InjectWorkflows, ",") != "vision-to-book,entity-triage" {
		t.Fatalf("expected dedup + blank-drop, got %v", got.InjectWorkflows)
	}
}

func TestMergeModeBindings_EmptyListsNeverNil(t *testing.T) {
	// The chat client reads these fields directly; a nil would marshal to JSON `null`
	// and force every consumer to null-guard. Always [].
	got := mergeModeBindings("ask", []ModeBindingRow{{Tier: "system"}})
	if got.InjectSkills == nil || got.InjectWorkflows == nil ||
		got.SeedToolCategories == nil || got.DisableWorkflows == nil {
		t.Fatalf("empty lists must marshal as [], not null: %+v", got)
	}
}

func TestCleanList_CapsAndDedups(t *testing.T) {
	out, ok := cleanList([]string{"a", "a", " b ", ""})
	if !ok || strings.Join(out, ",") != "a,b" {
		t.Fatalf("expected [a b], got %v ok=%v", out, ok)
	}
	if _, ok := cleanList([]string{strings.Repeat("x", 129)}); ok {
		t.Fatal("an over-long entry must be rejected")
	}
	long := make([]string, 33)
	for i := range long {
		long[i] = string(rune('a' + i%26))
	}
	if _, ok := cleanList(append(long, "zz1", "zz2", "zz3", "zz4", "zz5", "zz6", "zz7")); ok {
		t.Fatal("more than 32 entries must be rejected")
	}
}

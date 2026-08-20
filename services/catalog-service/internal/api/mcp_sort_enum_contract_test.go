package api

// T12-D1 — `sort` is a CLOSED SET and must be advertised as a JSON-schema enum.
//
// W0 #2's rule: a tool arg whose valid values are a finite, code-known set MUST declare a real
// `enum`, because a set that lives only in description prose is invisible to a weak model.
//
// This tool was worse than the usual case. An unrecognised `sort` does not fail — it falls
// through `queryPublicBooks`'s switch to the `default` arm and silently sorts by RECENT.
// Measured 2026-08-13 over the real wire: sort:"bogus" returned a normal, successful,
// recency-ordered result. The caller asked for one ordering and got another, with no signal.
//
// `lwmcp.ClosedSetSchema` is the shared kit helper glossary-service's local copy already
// delegates to, whose comment notes that keeping it glossary-only "is precisely how
// book-service shipped four enum-less closed-set args". catalog-service is the next service
// that never inherited it.

import (
	"encoding/json"
	"os"
	"sort"
	"strings"
	"testing"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

func readAPISource(t *testing.T, file string) string {
	t.Helper()
	b, err := os.ReadFile(file)
	if err != nil {
		t.Fatalf("cannot read %s: %v — this guard has gone blind; re-point it rather than "+
			"deleting it", file, err)
	}
	return string(b)
}

func TestCatalogSortIsAdvertisedAsAnEnum(t *testing.T) {
	schema := lwmcp.ClosedSetSchema[catalogListIn](map[string][]any{"sort": catalogSortValues})
	raw, err := json.Marshal(schema)
	if err != nil {
		t.Fatalf("marshal schema: %v", err)
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		t.Fatalf("unmarshal schema: %v", err)
	}
	props, _ := m["properties"].(map[string]any)
	sortProp, ok := props["sort"].(map[string]any)
	if !ok {
		t.Fatal("catalogListIn no longer carries a `sort` arg")
	}
	rawEnum, ok := sortProp["enum"].([]any)
	if !ok || len(rawEnum) == 0 {
		t.Fatalf("`sort` declares no enum (%v) — a closed set in prose only is invisible to a "+
			"weak model, and an unrecognised value here silently sorts by recent (T12-D1)", sortProp)
	}
	got := make([]string, 0, len(rawEnum))
	for _, v := range rawEnum {
		got = append(got, v.(string))
	}
	sort.Strings(got)
	if want := "alpha,chapters,popular,recent"; strings.Join(got, ",") != want {
		t.Errorf("`sort` enum = %v, want %s", got, want)
	}
}

func TestTheSortEnumIsActuallyWIREDIntoTheRegistration(t *testing.T) {
	// CALL-SITE guard. The test above proves the helper builds the right schema; it would stay
	// green if the registration never passed it. That exact shape — a correct fix not wired in —
	// is one this loop has already been bitten by, so assert the wiring itself.
	src := readAPISource(t, "mcp_server.go")
	idx := strings.Index(src, `"catalog_list_public_books"`)
	if idx < 0 {
		t.Fatal("catalog_list_public_books is no longer registered here")
	}
	block := src[idx:]
	if end := strings.Index(block, "addTool"); end > 0 {
		block = block[:end]
	}
	if !strings.Contains(src[:idx], "addToolWithSchema") {
		t.Error("catalog_list_public_books is no longer registered via addToolWithSchema, so it " +
			"cannot carry an InputSchema and the sort enum is not advertised (T12-D1)")
	}
	if !strings.Contains(block, "ClosedSetSchema[catalogListIn]") || !strings.Contains(block, `"sort"`) {
		t.Error("the registration no longer passes ClosedSetSchema[catalogListIn] with \"sort\" — " +
			"the enum is built but never advertised")
	}
}

func TestCatalogSortEnumMatchesTheHandler(t *testing.T) {
	// Keeps the two halves honest: every advertised value must be a real arm of
	// queryPublicBooks's switch, and every arm must be advertised. An enum that drifts from the
	// dispatch is the same defect wearing a schema.
	src := readAPISource(t, "server.go")
	for _, v := range catalogSortValues {
		s := v.(string)
		if s == "recent" {
			continue // served by the `default` arm, deliberately not a `case`
		}
		if !strings.Contains(src, "case \""+s+"\":") {
			t.Errorf("`sort` advertises %q but queryPublicBooks has no `case %q:` — the enum "+
				"promises an ordering the handler does not implement", s, s)
		}
	}
	for _, arm := range []string{"alpha", "chapters", "popular"} {
		found := false
		for _, v := range catalogSortValues {
			if v.(string) == arm {
				found = true
			}
		}
		if !found {
			t.Errorf("queryPublicBooks implements `case %q:` but the enum does not advertise it "+
				"— an ordering nobody can ask for", arm)
		}
	}
}

func TestTheDefaultArmIsStillAskable(t *testing.T) {
	// "recent" is served by the switch's `default`, so it must NOT be dropped from the enum on
	// the reasoning that it has no `case` — that would make the documented default unaskable.
	for _, v := range catalogSortValues {
		if v.(string) == "recent" {
			return
		}
	}
	t.Error("`recent` left the enum — it is the documented default and must stay askable")
}

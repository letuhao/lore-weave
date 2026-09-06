package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #314 — the twin of #313, and worse: its documented undo could not even be CALLED.
//
// world_map_remove_region's mechanics were right — the DELETE joins world_maps on owner_user_id,
// so a foreign or missing region removes 0 rows and returns the uniform "region not found", and a
// malformed id returns "region_id must be a UUID".
//
// Its description said: "Undoes world_map_add_region (re-add it with the same polygon to restore)."
// `name` is a REQUIRED argument of world_map_add_region. Measured live:
//
//	before   {name "The Shattered Coast", polygon [[.1,.1],[.4,.1],[.4,.4]], entity_id ...beef0}
//	remove   {"removed": true}   — no _meta on the response
//	restore  add_region(map_id, polygon)   ← exactly what the description said
//	result   VALIDATION: required: missing properties: ["name"]
//
// So the reversal was not merely lossy like the marker's — it was rejected outright, and the name
// and entity_id had already gone with the row. The only move left to an agent following the
// instruction was to invent a name for the user's region.
func TestRemoveRegionReturnsEverythingNeededToRestoreIt(t *testing.T) {
	fn := removeRegionBody(t)
	if !strings.Contains(fn, "RETURNING rg.map_id, rg.name, rg.polygon, rg.entity_id") {
		t.Fatal("the delete no longer RETURNs the region's state — its name and entity link " +
			"cannot be recovered once the row is gone")
	}
	if !strings.Contains(fn, `undoResult("world_map_add_region"`) {
		t.Error("no undo hint is emitted, so the caller has nothing to replay")
	}
	for _, field := range []string{`"map_id"`, `"name"`, `"polygon"`, `"entity_id"`} {
		if !strings.Contains(fn, field) {
			t.Errorf("the undo hint omits %s", field)
		}
	}
}

// `name` is what made the old recipe unexecutable, so it must never become conditional. entity_id
// is genuinely optional and must stay omitted-when-absent, because add_region parses it as a UUID
// and an empty string would fail.
func TestNameIsUnconditionalAndEntityIsNot(t *testing.T) {
	fn := removeRegionBody(t)
	i := strings.Index(fn, "undoArgs := map[string]any{")
	if i < 0 {
		t.Fatal("the undo args literal is gone")
	}
	lit := fn[i:]
	if j := strings.Index(lit, "}"); j > 0 {
		lit = lit[:j]
	}
	if !strings.Contains(lit, `"name": name`) {
		t.Error("name is no longer set unconditionally — a region restored without it is the " +
			"exact VALIDATION failure this fix exists to end")
	}
	if !strings.Contains(lit, `"polygon": polygon`) {
		t.Error("polygon is no longer set unconditionally")
	}
	if strings.Contains(lit, `"entity_id"`) {
		t.Error("entity_id is in the unconditional literal — a region with no entity would " +
			"replay a nil that add_region's UUID parse rejects")
	}
	if !strings.Contains(fn, "if entityID != nil {") {
		t.Error("entity_id is not conditionally added")
	}
}

// The polygon is stored as JSON and add_region's schema expects an ARRAY of [x,y] pairs. Handing
// back the raw bytes would replay a JSON STRING and fail validation — an undo that cannot run,
// which is the whole defect wearing a different hat.
func TestThePolygonIsReplayedAsAnArrayNotAJSONString(t *testing.T) {
	fn := removeRegionBody(t)
	if !strings.Contains(fn, "var polygon [][]float64") || !strings.Contains(fn, "json.Unmarshal(polygonJSON, &polygon)") {
		t.Error("the stored polygon JSON is no longer decoded before going into the undo hint; " +
			"replaying it as a string would fail add_region's array validation")
	}
	if strings.Contains(fn, `"polygon": polygonJSON`) {
		t.Error("the raw JSON bytes are put straight into the hint")
	}
}

// The description must not prescribe the unexecutable recipe again.
func TestTheRegionDescriptionNoLongerPrescribesAnUncallableRestore(t *testing.T) {
	// Scoped to the registration block, not the file: the handler's comment QUOTES the old recipe
	// to explain why it was wrong, and a whole-file match failed on that explanation. The string
	// that matters is the one shipped to the model.
	desc := toolRegistration(t, "world_map_remove_region")
	if strings.Contains(desc, "re-add it with the same polygon to restore") {
		t.Error("the description tells the agent to restore a region from the polygon alone, " +
			"which add_region rejects for a missing name")
	}
	if !strings.Contains(desc, "world_map_add_region requires a name") {
		t.Error("the description no longer warns that the polygon alone is not enough")
	}
}

// toolRegistration returns just the addTool(...) call for one tool, so an assertion about what the
// MODEL is told cannot be satisfied or broken by prose in a code comment.
func toolRegistration(t *testing.T, name string) string {
	t.Helper()
	src := mustReadFile(t, "mcp_maps.go")
	i := strings.Index(src, `addTool(srv, "`+name+`",`)
	if i < 0 {
		t.Fatalf("tool %s is not registered", name)
	}
	block := src[i:]
	if j := strings.Index(block, "lwmcp.NewToolMeta"); j > 0 {
		block = block[:j]
	}
	return block
}

func removeRegionBody(t *testing.T) string {
	t.Helper()
	src := mustReadFile(t, "mcp_maps.go")
	i := strings.Index(src, "func (s *Server) toolWorldMapRemoveRegion")
	if i < 0 {
		t.Fatal("toolWorldMapRemoveRegion is gone")
	}
	fn := src[i:]
	if j := strings.Index(fn, "\nfunc "); j > 0 {
		fn = fn[:j]
	}
	return fn
}

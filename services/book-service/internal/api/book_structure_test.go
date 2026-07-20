package api

// P1.1 — unit tests for the PURE grouping (buildBookStructure). No DB/port needed.

import "testing"

func sPart(id string, sortOrder int, active bool) structurePartInput {
	return structurePartInput{PartID: id, Title: id, SortOrder: sortOrder, Active: active}
}

func sLink(id string) structureChapterLink { return structureChapterLink{StructureNodeID: &id} }

var sNoLink = structureChapterLink{}

func TestBuildBookStructure_GroupsCountsAndSorts(t *testing.T) {
	proj := "proj-1"
	parts := []structurePartInput{sPart("p2", 2, true), sPart("p1", 1, true), sPart("pArch", 3, false)}
	chapters := []structureChapterLink{
		sLink("p1"), sLink("p1"), // 2 in p1
		sLink("p2"),      // 1 in p2
		sNoLink,          // null link → unassigned
		sLink("pArch"),   // archived (inactive) part → unassigned
		sLink("arcXYZ"),  // a foreign/arc id not in the active set → unassigned
	}
	got := buildBookStructure("book-1", chapters, parts,
		structureWork{ProjectID: &proj}, structureSources{Parts: "ok", Work: "ok"})

	if !got.KindsPresent.Parts {
		t.Error("kinds_present.parts should be true (an active part exists)")
	}
	if !got.KindsPresent.Outline {
		t.Error("kinds_present.outline should be true (active_work.project_id set)")
	}
	if len(got.Parts) != 2 {
		t.Fatalf("want 2 active parts (pArch excluded), got %d", len(got.Parts))
	}
	if got.Parts[0].PartID != "p1" || got.Parts[1].PartID != "p2" {
		t.Errorf("parts must be sorted by sort_order (p1 then p2), got %+v", got.Parts)
	}
	if got.Parts[0].ChapterCount != 2 {
		t.Errorf("p1 chapter_count want 2, got %d", got.Parts[0].ChapterCount)
	}
	if got.Parts[1].ChapterCount != 1 {
		t.Errorf("p2 chapter_count want 1, got %d", got.Parts[1].ChapterCount)
	}
	if got.UnassignedCount != 3 { // null + archived + foreign
		t.Errorf("unassigned_count want 3, got %d", got.UnassignedCount)
	}
}

func TestBuildBookStructure_NoParts_FlatBook(t *testing.T) {
	got := buildBookStructure("b", []structureChapterLink{sNoLink, sNoLink}, nil,
		structureWork{}, structureSources{Parts: "ok", Work: "ok"})
	if got.KindsPresent.Parts {
		t.Error("no active part → kinds_present.parts must be false (FE renders flat, no Unassigned banner)")
	}
	if got.KindsPresent.Outline {
		t.Error("no project_id → kinds_present.outline must be false")
	}
	if len(got.Parts) != 0 {
		t.Errorf("want 0 parts, got %d", len(got.Parts))
	}
	if got.UnassignedCount != 2 {
		t.Errorf("want 2 unassigned, got %d", got.UnassignedCount)
	}
}

// THE Bug-4-class guard: a chapter whose link points at a non-active / foreign / arc / dangling
// node must fall to Unassigned, never vanish. Conservation: parts' counts + unassigned == chapters in.
func TestBuildBookStructure_DanglingLinkNeverDropsAChapter(t *testing.T) {
	parts := []structurePartInput{sPart("p1", 1, true)}
	chapters := []structureChapterLink{sLink("p1"), sLink("ghost"), sLink("arc"), sNoLink}
	got := buildBookStructure("b", chapters, parts, structureWork{}, structureSources{})

	total := got.UnassignedCount
	for _, p := range got.Parts {
		total += p.ChapterCount
	}
	if total != len(chapters) {
		t.Errorf("chapter conservation broken: %d in, %d accounted (%d parts + %d unassigned)",
			len(chapters), total, len(got.Parts), got.UnassignedCount)
	}
	if got.Parts[0].ChapterCount != 1 {
		t.Errorf("p1 must hold exactly its 1 real chapter, got %d", got.Parts[0].ChapterCount)
	}
	if got.UnassignedCount != 3 {
		t.Errorf("ghost+arc+null must be 3 unassigned, got %d", got.UnassignedCount)
	}
}

func TestBuildBookStructure_SourcesPassThroughForNoSilentSeam(t *testing.T) {
	// A composition outage surfaces as sources.parts="unavailable" (never silently flattened).
	got := buildBookStructure("b", nil, nil, structureWork{},
		structureSources{Parts: "unavailable", Work: "unavailable"})
	if got.Sources.Parts != "unavailable" || got.Sources.Work != "unavailable" {
		t.Errorf("sources must pass through to surface a composition outage, got %+v", got.Sources)
	}
}

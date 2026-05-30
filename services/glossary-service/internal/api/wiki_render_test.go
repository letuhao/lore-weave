package api

import (
	"encoding/json"
	"strings"
	"testing"
)

func strptr(s string) *string { return &s }

// docText flattens every "text" node's text content for substring
// assertions, and collects every node's "source_type" attr value so
// tests can assert H0 marking without coupling to exact node shapes.
func docText(t *testing.T, body json.RawMessage) (string, []string) {
	t.Helper()
	var doc map[string]any
	if err := json.Unmarshal(body, &doc); err != nil {
		t.Fatalf("body is not valid JSON: %v", err)
	}
	if doc["type"] != "doc" {
		t.Fatalf("expected top-level type=doc, got %v", doc["type"])
	}
	var sb strings.Builder
	var sourceTypes []string
	var walk func(n any)
	walk = func(n any) {
		m, ok := n.(map[string]any)
		if !ok {
			return
		}
		if attrs, ok := m["attrs"].(map[string]any); ok {
			if st, ok := attrs["source_type"].(string); ok {
				sourceTypes = append(sourceTypes, st)
			}
		}
		if m["type"] == "text" {
			if txt, ok := m["text"].(string); ok {
				sb.WriteString(txt)
				sb.WriteString("\n")
			}
		}
		if content, ok := m["content"].([]any); ok {
			for _, c := range content {
				walk(c)
			}
		}
	}
	walk(doc)
	return sb.String(), sourceTypes
}

func TestRenderWikiBody_EmptyNeighborhood_MinimalBody(t *testing.T) {
	body := renderWikiBody(wikiRenderInput{
		DisplayName:  "玉虛宮",
		KindName:     "地点",
		Attributes:   nil,
		Neighborhood: nil,
	})
	text, _ := docText(t, body)
	if !strings.Contains(text, "玉虛宮") {
		t.Errorf("minimal body must contain the entity name; got: %q", text)
	}
	// Must be a non-empty doc (the whole point of C5 — never blank).
	var doc map[string]any
	_ = json.Unmarshal(body, &doc)
	content, _ := doc["content"].([]any)
	if len(content) == 0 {
		t.Fatal("minimal body must not be empty content")
	}
}

func TestRenderWikiBody_UnnamedEntity_DoesNotCrash(t *testing.T) {
	body := renderWikiBody(wikiRenderInput{})
	text, _ := docText(t, body)
	if !strings.Contains(text, "unnamed") {
		t.Errorf("unnamed entity should fall back to a placeholder; got %q", text)
	}
}

func TestRenderWikiBody_Attributes_Rendered(t *testing.T) {
	body := renderWikiBody(wikiRenderInput{
		DisplayName: "陳塘關",
		KindName:    "地点",
		Attributes: []wikiRenderAttr{
			{Label: "地理", Value: "东海之滨的军事关隘"},
			{Label: "空字段", Value: ""}, // empty → skipped
		},
	})
	text, _ := docText(t, body)
	if !strings.Contains(text, "基本资料") {
		t.Errorf("expected attributes heading 基本资料; got %q", text)
	}
	if !strings.Contains(text, "东海之滨的军事关隘") {
		t.Errorf("expected attribute value rendered; got %q", text)
	}
	if strings.Contains(text, "空字段") {
		t.Errorf("empty attribute value should be skipped; got %q", text)
	}
}

func TestRenderWikiBody_GlossaryRelations_RenderedAsCanon(t *testing.T) {
	nb := &kgNeighborhood{
		Found: true,
		Relations: []kgNeighborRelation{
			{
				Predicate:   "位于",
				SubjectName: strptr("玉虛宮"),
				ObjectName:  strptr("昆仑山"),
				Confidence:  1.0,
				SourceType:  sourceTypeGlossary,
			},
		},
		TotalRelations: 1,
	}
	body := renderWikiBody(wikiRenderInput{DisplayName: "玉虛宮", KindName: "地点", Neighborhood: nb})
	text, sourceTypes := docText(t, body)
	if !strings.Contains(text, "关系") {
		t.Errorf("expected 关系 heading for canon relations; got %q", text)
	}
	if !strings.Contains(text, "昆仑山") {
		t.Errorf("expected related entity name; got %q", text)
	}
	// H0: canon must NOT carry the enriched marker or the 增补 prefix.
	for _, st := range sourceTypes {
		if st == sourceTypeEnriched {
			t.Errorf("canon relation must not be marked enriched; sourceTypes=%v", sourceTypes)
		}
	}
	if strings.Contains(text, "【增补】") {
		t.Errorf("canon relation must not carry the 增补 prefix; got %q", text)
	}
}

func TestRenderWikiBody_EnrichedRelations_MarkedDistinct(t *testing.T) {
	nb := &kgNeighborhood{
		Found: true,
		Relations: []kgNeighborRelation{
			{
				Predicate:         "守护",
				SubjectName:       strptr("玉虛宮"),
				ObjectName:        strptr("镇元大仙"),
				Confidence:        0.6,
				PendingValidation: true,
				SourceType:        sourceTypeEnriched,
			},
		},
		TotalRelations: 1,
	}
	body := renderWikiBody(wikiRenderInput{DisplayName: "玉虛宮", KindName: "地点", Neighborhood: nb})
	text, sourceTypes := docText(t, body)
	// H0: enriched section heading + explicit unverified disclaimer.
	if !strings.Contains(text, "增补") {
		t.Errorf("expected enriched section labelled 增补; got %q", text)
	}
	if !strings.Contains(text, "尚未经作者校验") {
		t.Errorf("expected explicit unverified disclaimer for enriched; got %q", text)
	}
	if !strings.Contains(text, "【增补】") {
		t.Errorf("expected enriched item prefix 【增补】; got %q", text)
	}
	// H0: structural marker present.
	foundMarker := false
	for _, st := range sourceTypes {
		if st == sourceTypeEnriched {
			foundMarker = true
		}
	}
	if !foundMarker {
		t.Errorf("enriched relation must carry a structural source_type=enriched attr; sourceTypes=%v", sourceTypes)
	}
}

// H0 fail-safe: a relation whose source_type is neither 'glossary' nor a
// known marker (e.g. blank, or a future label) must be treated as
// enriched — never silently merged into canon.
func TestRenderWikiBody_UnknownSourceType_TreatedAsEnriched(t *testing.T) {
	nb := &kgNeighborhood{
		Found: true,
		Relations: []kgNeighborRelation{
			{Predicate: "关联", SubjectName: strptr("玉虛宮"), ObjectName: strptr("某物"), SourceType: ""},
			{Predicate: "关联", SubjectName: strptr("玉虛宮"), ObjectName: strptr("他物"), SourceType: "speculative"},
		},
		TotalRelations: 2,
	}
	canon, enriched := splitRelations(nb)
	if len(canon) != 0 {
		t.Errorf("unknown source_type must NOT count as canon; canon=%d", len(canon))
	}
	if len(enriched) != 2 {
		t.Errorf("unknown source_type must be quarantined as enriched; enriched=%d", len(enriched))
	}
	body := renderWikiBody(wikiRenderInput{DisplayName: "玉虛宮", Neighborhood: nb})
	text, _ := docText(t, body)
	if strings.Contains(text, "\n关系\n") {
		// crude: there should be no plain canon 关系 section for these
	}
	if !strings.Contains(text, "增补") {
		t.Errorf("unknown source_type relations must render under the enriched section; got %q", text)
	}
}

func TestRenderWikiBody_MixedCanonAndEnriched_BothPresent(t *testing.T) {
	nb := &kgNeighborhood{
		Found: true,
		Relations: []kgNeighborRelation{
			{Predicate: "位于", SubjectName: strptr("玉虛宮"), ObjectName: strptr("昆仑山"), Confidence: 1.0, SourceType: sourceTypeGlossary},
			{Predicate: "邻近", SubjectName: strptr("玉虛宮"), ObjectName: strptr("蓬萊"), Confidence: 0.5, PendingValidation: true, SourceType: sourceTypeEnriched},
		},
		TotalRelations: 2,
	}
	canon, enriched := splitRelations(nb)
	if len(canon) != 1 || len(enriched) != 1 {
		t.Fatalf("expected 1 canon + 1 enriched; got canon=%d enriched=%d", len(canon), len(enriched))
	}
	body := renderWikiBody(wikiRenderInput{DisplayName: "玉虛宮", Neighborhood: nb})
	text, _ := docText(t, body)
	if !strings.Contains(text, "昆仑山") || !strings.Contains(text, "蓬萊") {
		t.Errorf("both canon and enriched peers must appear; got %q", text)
	}
}

func TestRenderWikiBody_Truncation_Noted(t *testing.T) {
	nb := &kgNeighborhood{
		Found:              true,
		Relations:          []kgNeighborRelation{{Predicate: "位于", SubjectName: strptr("玉虛宮"), ObjectName: strptr("昆仑山"), Confidence: 1.0, SourceType: sourceTypeGlossary}},
		TotalRelations:     50,
		RelationsTruncated: true,
	}
	body := renderWikiBody(wikiRenderInput{DisplayName: "玉虛宮", Neighborhood: nb})
	text, _ := docText(t, body)
	if !strings.Contains(text, "50") {
		t.Errorf("expected truncation note mentioning total count; got %q", text)
	}
}

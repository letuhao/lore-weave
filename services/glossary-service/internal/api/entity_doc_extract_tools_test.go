package api

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// The parse+validate core is pure (no Server/DB/LLM), so it carries the bulk of the
// WS-4A coverage: kind/attribute filtering, dedup, stringify, notes, the repair trigger.

func extractTestMaps() (map[string]bool, map[string]map[string]bool) {
	validKinds := map[string]bool{"character": true, "place": true, "technique": true}
	attrCodesByKind := map[string]map[string]bool{
		"character": {"summary": true, "affiliation": true},
		"place":     {"summary": true},
		"technique": {"summary": true},
	}
	return validKinds, attrCodesByKind
}

func TestParseDocExtraction_HappyPath(t *testing.T) {
	vk, ac := extractTestMaps()
	text := `Here you go:
` + "```json" + `
{"candidates":[
  {"kind":"character","name":"Lâm Uyên","attributes":{"summary":"a young sect heir","affiliation":"Thiên Sect"}},
  {"kind":"technique","name":"Chân Linh","attributes":{"summary":"the core life-essence"}}
],"notes":["nothing else"]}
` + "```"
	out, err := parseDocExtraction(text, vk, ac, maxDocExtractCandidates)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out.Candidates) != 2 {
		t.Fatalf("want 2 candidates, got %d (%+v)", len(out.Candidates), out.Candidates)
	}
	c0 := out.Candidates[0]
	if c0.Kind != "character" || c0.Name != "Lâm Uyên" {
		t.Errorf("candidate 0 wrong: %+v", c0)
	}
	if c0.Attributes["summary"] != "a young sect heir" || c0.Attributes["affiliation"] != "Thiên Sect" {
		t.Errorf("candidate 0 attributes wrong: %+v", c0.Attributes)
	}
}

func TestParseDocExtraction_DropsUnknownKindAndNotes(t *testing.T) {
	vk, ac := extractTestMaps()
	text := `{"candidates":[
	  {"kind":"character","name":"Keeper"},
	  {"kind":"spaceship","name":"The Nomad"},
	  {"kind":"spaceship","name":"The Wanderer"}
	]}`
	out, err := parseDocExtraction(text, vk, ac, maxDocExtractCandidates)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out.Candidates) != 1 || out.Candidates[0].Name != "Keeper" {
		t.Fatalf("want only the valid-kind candidate, got %+v", out.Candidates)
	}
	// the two unknown-kind items must be reported, not silently dropped
	joined := strings.Join(out.Notes, " | ")
	if !strings.Contains(joined, "spaceship") || !strings.Contains(joined, "2 item") {
		t.Errorf("expected a note about 2 skipped spaceship items, got notes=%v", out.Notes)
	}
}

func TestParseDocExtraction_FiltersUnknownAttributesAndEmptyName(t *testing.T) {
	vk, ac := extractTestMaps()
	text := `{"candidates":[
	  {"kind":"character","name":"  ","attributes":{"summary":"ignored, name empty"}},
	  {"kind":"place","name":"Cloud Peak","attributes":{"summary":"a mountain","altitude":"9000m","affiliation":"not a place attr"}}
	]}`
	out, err := parseDocExtraction(text, vk, ac, maxDocExtractCandidates)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out.Candidates) != 1 {
		t.Fatalf("empty-name candidate should be dropped; got %+v", out.Candidates)
	}
	attrs := out.Candidates[0].Attributes
	if attrs["summary"] != "a mountain" {
		t.Errorf("valid attr missing: %+v", attrs)
	}
	if _, ok := attrs["altitude"]; ok {
		t.Errorf("unknown attr 'altitude' (not a 'place' attr) should be filtered: %+v", attrs)
	}
	if _, ok := attrs["affiliation"]; ok {
		t.Errorf("attr valid for 'character' but not 'place' should be filtered: %+v", attrs)
	}
}

func TestParseDocExtraction_DedupWithinDoc(t *testing.T) {
	vk, ac := extractTestMaps()
	text := `{"candidates":[
	  {"kind":"character","name":"Lâm Uyên"},
	  {"kind":"character","name":"lâm uyên"},
	  {"kind":"place","name":"Lâm Uyên"}
	]}`
	out, err := parseDocExtraction(text, vk, ac, maxDocExtractCandidates)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// same (kind, lowered-name) collapses to one; a different kind is a distinct entity
	if len(out.Candidates) != 2 {
		t.Fatalf("want 2 (char + place), got %d: %+v", len(out.Candidates), out.Candidates)
	}
}

func TestParseDocExtraction_StringifiesNonStringAttrValues(t *testing.T) {
	vk, ac := extractTestMaps()
	text := `{"candidates":[{"kind":"technique","name":"Rank","attributes":{"summary":3}}]}`
	out, err := parseDocExtraction(text, vk, ac, maxDocExtractCandidates)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := out.Candidates[0].Attributes["summary"]; got != "3" {
		t.Errorf("numeric attr should stringify to \"3\", got %q", got)
	}
}

// REGRESSION (/review-impl): every kind carries a required "name" attr_def, so it
// used to appear in the grounding prompt AND be accepted in a candidate's attributes,
// letting the model emit a second name that conflicts with the top-level one (inert at
// create, but a silent RENAME if fed to glossary_entity_set_attributes).
func TestOntologyExtractMaps_ExcludesNameFromAttributes(t *testing.T) {
	desc := "the entity's name"
	ont := &bookOntologyResp{
		Kinds: []bookKindResp{{BookKindID: "k1", Code: "character", Name: "Character"}},
		Attributes: []bookAttrResp{
			{KindID: "k1", Code: "name", Name: "Name", Description: &desc, FieldType: "text"},
			{KindID: "k1", Code: "summary", Name: "Summary", FieldType: "textarea"},
		},
	}
	_, attrCodesByKind := ontologyExtractMaps(ont)
	if attrCodesByKind["character"]["name"] {
		t.Error("`name` must NOT be an accepted candidate attribute code")
	}
	if !attrCodesByKind["character"]["summary"] {
		t.Error("`summary` should still be accepted")
	}
	if s := ontologyGroundingSummary(ont); strings.Contains(s, "· name") {
		t.Errorf("`name` must not be advertised as a settable attribute:\n%s", s)
	}
}

func TestParseDocExtraction_DropsNameAttributeFromCandidate(t *testing.T) {
	vk := map[string]bool{"character": true}
	ac := map[string]map[string]bool{"character": {"summary": true}} // no "name"
	text := `{"candidates":[{"kind":"character","name":"Lâm Uyên","attributes":{"name":"WRONG","summary":"a sect heir"}}]}`
	out, err := parseDocExtraction(text, vk, ac, maxDocExtractCandidates)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	c := out.Candidates[0]
	if c.Name != "Lâm Uyên" {
		t.Errorf("top-level name must win, got %q", c.Name)
	}
	if _, ok := c.Attributes["name"]; ok {
		t.Errorf("a `name` attribute must be filtered out, got %+v", c.Attributes)
	}
	if c.Attributes["summary"] != "a sect heir" {
		t.Errorf("valid attr lost: %+v", c.Attributes)
	}
}

func TestParseDocExtraction_InvalidJSONErrorsForRepair(t *testing.T) {
	vk, ac := extractTestMaps()
	if _, err := parseDocExtraction("not json at all", vk, ac, maxDocExtractCandidates); err == nil {
		t.Fatal("expected an error on unparseable output (it is what triggers the repair round)")
	}
}

func TestStringifyAttrValue(t *testing.T) {
	cases := map[string]struct {
		in   any
		want string
	}{
		"string":     {"hi", "hi"},
		"whole-num":  {float64(5), "5"},
		"float":      {float64(2.5), "2.5"},
		"bool":       {true, "true"},
		"nil":        {nil, ""},
		"trim":       {"  padded  ", "padded"},
		"list":       {[]any{"a", "b"}, `["a","b"]`},
	}
	for name, tc := range cases {
		if got := stringifyAttrValue(tc.in); got != tc.want {
			t.Errorf("%s: stringifyAttrValue(%v) = %q, want %q", name, tc.in, got, tc.want)
		}
	}
}

func TestFilterHintCodes(t *testing.T) {
	vk, _ := extractTestMaps()
	got := filterHintCodes([]string{"character", "dragon", "character", " place ", ""}, vk)
	// keeps valid, dedups, drops unknown ('dragon') and blanks; trims
	if len(got) != 2 || got[0] != "character" || got[1] != "place" {
		t.Errorf("filterHintCodes returned %v, want [character place]", got)
	}
}

// ── handler input-guard tests (no DB, no LLM — mirror propose_entity_test.go) ──
// (ctxWithUser is the shared package helper defined in propose_entity_test.go.)

func TestExtractEntitiesFromDoc_MissingIdentity(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolExtractEntitiesFromDoc(context.Background(), nil, extractEntitiesFromDocIn{
		BookID: uuid.NewString(), SourceMarkdown: "some notes",
	})
	if err == nil || !strings.Contains(err.Error(), "identity") {
		t.Fatalf("want missing-identity error, got %v", err)
	}
}

func TestExtractEntitiesFromDoc_BadBookID(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolExtractEntitiesFromDoc(ctxWithUser(uuid.New()), nil, extractEntitiesFromDocIn{
		BookID: "not-a-uuid", SourceMarkdown: "some notes",
	})
	if err == nil || !strings.Contains(err.Error(), "UUID") {
		t.Fatalf("want book_id UUID error, got %v", err)
	}
}

func TestExtractEntitiesFromDoc_EmptyDoc(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolExtractEntitiesFromDoc(ctxWithUser(uuid.New()), nil, extractEntitiesFromDocIn{
		BookID: uuid.NewString(), SourceMarkdown: "   ",
	})
	if err == nil || !strings.Contains(err.Error(), "source_markdown is required") {
		t.Fatalf("want empty-doc error, got %v", err)
	}
}

func TestExtractEntitiesFromDoc_DocTooLong(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolExtractEntitiesFromDoc(ctxWithUser(uuid.New()), nil, extractEntitiesFromDocIn{
		BookID: uuid.NewString(), SourceMarkdown: strings.Repeat("x", maxSourceMarkdownLen+1),
	})
	if err == nil || !strings.Contains(err.Error(), "too long") {
		t.Fatalf("want too-long error, got %v", err)
	}
}

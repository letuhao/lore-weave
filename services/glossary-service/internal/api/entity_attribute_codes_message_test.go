package api

import (
	"os"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// The measured incident, TOOLV2 LOOP #64: a model sent
// attributes {"status": "canonical"}, got "no valid attribute codes for this entity's kind",
// and its next move was to try `status` as a top-level ARGUMENT — which failed too, on
// "unexpected additional properties". It had no way to learn the alphabet, so it guessed at
// the grammar. The tool's DESCRIPTION already points at glossary_book_ontology_read for the
// valid codes; being told in prose is what had already failed.
func TestTheRefusalNamesTheCodesTheCallerCouldHaveSent(t *testing.T) {
	kind := uuid.New().String()
	other := uuid.New().String()
	defs := map[string]uuid.UUID{
		kind + ":name":        uuid.New(),
		kind + ":description": uuid.New(),
		kind + ":aliases":     uuid.New(),
		// A DIFFERENT kind's codes must not leak into this kind's advice — suggesting a code
		// that will be rejected on the retry is worse than suggesting nothing.
		other + ":faction": uuid.New(),
	}

	got := noValidAttrCodesMessage(defs, kind, []string{"status"})

	if !strings.Contains(got, "no valid attribute codes") {
		t.Fatalf("the original claim must survive; got %q", got)
	}
	for _, code := range []string{"name", "description", "aliases"} {
		if !strings.Contains(got, code) {
			t.Errorf("the message must name the valid code %q; got %q", code, got)
		}
	}
	if !strings.Contains(got, "status") {
		t.Errorf("the message must name what was REJECTED so the caller can tell which of "+
			"several attributes was the problem; got %q", got)
	}
	if strings.Contains(got, "faction") {
		t.Errorf("another kind's code must not be offered — the retry would fail again; got %q", got)
	}
}

// A kind with NO attributes is a different answer and must not read like the first: no
// argument could have succeeded, so the caller should stop retrying rather than hunt for a
// code that does not exist.
func TestAKindWithNoAttributesSaysSoInsteadOfOfferingAnEmptyList(t *testing.T) {
	kind := uuid.New().String()
	got := noValidAttrCodesMessage(map[string]uuid.UUID{}, kind, []string{"status"})

	if !strings.Contains(got, "no attributes defined") {
		t.Errorf("an attribute-less kind must say so; got %q", got)
	}
	if strings.Contains(got, "Valid codes") {
		t.Errorf("an empty list must not be presented as a list of options; got %q", got)
	}
}

// The cap exists so one rejection cannot become a wall of text, and the overflow must be
// declared — a silently truncated list reads as the complete alphabet, which is the same
// class of lie the loop keeps finding in denominators.
func TestAnOversizedCodeListIsCappedAndSaysHowManyItDropped(t *testing.T) {
	kind := uuid.New().String()
	defs := map[string]uuid.UUID{}
	for _, c := range []string{
		"a01", "a02", "a03", "a04", "a05", "a06", "a07", "a08", "a09", "a10",
		"a11", "a12", "a13", "a14", "a15", "a16", "a17", "a18", "a19", "a20",
		"a21", "a22", "a23", "a24", "a25", "a26", "a27",
	} {
		defs[kind+":"+c] = uuid.New()
	}

	got := noValidAttrCodesMessage(defs, kind, nil)

	if strings.Contains(got, "a26") || strings.Contains(got, "a27") {
		t.Errorf("the list must be capped at %d; got %q", _attrCodesInMessage, got)
	}
	if !strings.Contains(got, "(+2 more)") {
		t.Errorf("the truncation must be declared, or the list reads as complete; got %q", got)
	}
	// Sorted, so the same kind produces the same message twice — an unstable suggestion list
	// makes a repeated failure look like a different one.
	if strings.Index(got, "a01") > strings.Index(got, "a02") {
		t.Errorf("codes must be sorted for a stable message; got %q", got)
	}
}

// TOOLV2 LOOP #88 — the same lever as the attribute-code message above, on the kind code.
//
// The bare form was "unknown kind: werewolf" — the category the caller cannot use, and nothing
// else. Two lines up in the same function, the field_type rejection already names its whole
// valid set. And the batch entity tool already does this properly for the SAME concept: it
// explains what an unknown kind means and names the two tools that create one. This raise site
// was the one left behind.
func TestTheUnknownKindMessageNamesTheKindsTheBookHas(t *testing.T) {
	kinds := map[string]uuid.UUID{
		"character": uuid.New(), "place": uuid.New(), "faction": uuid.New(),
	}
	got := unknownKindMessage("werewolf", kinds)

	if !strings.Contains(got, "unknown kind: werewolf") {
		t.Fatalf("the original claim must survive: %q", got)
	}
	for _, k := range []string{"character", "place", "faction"} {
		if !strings.Contains(got, k) {
			t.Errorf("the book's kind %q must be named: %q", k, got)
		}
	}
	// And the way to ADD one, because the caller's kind may be legitimately new.
	if !strings.Contains(got, "glossary_adopt_standards") || !strings.Contains(got, "glossary_propose_kinds") {
		t.Errorf("both satisfiers must be named: %q", got)
	}
}

func TestABookWithNoKindsSaysSoInsteadOfListingNothing(t *testing.T) {
	got := unknownKindMessage("werewolf", map[string]uuid.UUID{})
	if !strings.Contains(got, "no kinds yet") {
		t.Errorf("an empty book must say so rather than offer an empty list: %q", got)
	}
	if strings.Contains(got, "Kinds in this book:") {
		t.Errorf("an empty list must not be presented as a set of options: %q", got)
	}
}

// The helper is only worth anything if the raise site USES it. A guard that calls
// unknownKindMessage directly stays green when the call site is reverted to the bare string —
// that happened twice in this loop, so the wiring gets its own anchor.
func TestTheRaiseSiteUsesTheUnknownKindHelper(t *testing.T) {
	src, err := os.ReadFile("action_propose_tools.go")
	if err != nil {
		t.Fatalf("read source: %v", err)
	}
	body := strings.ReplaceAll(string(src), "\r\n", "\n")
	if !strings.Contains(body, "errors.New(unknownKindMessage(kindCode, kindMap))") {
		t.Error("the kind lookup must return the helper's message, not a bare concatenation")
	}
	if strings.Contains(body, `errors.New("unknown kind: " + kindCode)`) {
		t.Error("the bare 'unknown kind: X' message is back at the raise site")
	}
}

package api

import (
	"reflect"
	"strings"
	"testing"
)

// V1 — a create that does not carry the prose makes a chapter the author cannot read.
//
// 🔴 MEASURED 2026-09-04 across two live authoring runs driving the real Studio.
//
// EVERY chapter left at 0 words was created TITLE-ONLY, and the turn ended before any
// book_chapter_save_draft filled it — four stranded chapters across the two runs. One of them was
// reported to the author like this, by a turn that had called only book_read:
//
//	"I have written and saved Chapter Five, 'The Unfamiliar Hand,' into your book.
//	 Status: Draft saved (Version 1). Word Count: 1,054 words."
//	 ... and, four lines later in the same reply: "The current chapter count is 4."
//
// EVERY create that PASSED a body produced a complete chapter in ONE call — 1,242 and 700 words,
// with no save_draft called at all. So the one-call path already worked. What the surface said
// about it, in full, was:
//
//	jsonschema:"plain-text body (optional)"
//
// Five words, which name neither what the field is for nor what omitting it costs — while the
// sibling field on book_chapter_save_draft gets a full sentence calling itself "the chapter's
// PROSE". The model reached for create, left body out, promised to save, and the turn ended.
//
// ⚠️ THIS IS AN AFFORDANCE FIX, NOT A GUARD, and that is deliberate. The end-of-turn detector for
// the adjacent shape (D-NARRATED-WRITE) FIRED on the measured run, named book_chapter_save_draft
// exactly, and nudged — and the model called book_chapter_create three more times regardless. A
// second detector on the same shape would be a mechanism that fires without mattering. Fixing what
// the tool says about its own argument changes the call that gets made.
//
// A title-only create stays LEGAL: building a skeleton of empty chapters is a real thing to want,
// so nothing here refuses or repairs. Only the description changed.
func TestCreateBodyIsDescribedAsTheProseAndNamesTheCostOfOmittingIt(t *testing.T) {
	f, ok := reflect.TypeOf(chapterCreateIn{}).FieldByName("Body")
	if !ok {
		t.Fatal("chapterCreateIn has no Body field")
	}
	desc := f.Tag.Get("jsonschema")

	// It must say what the field IS. "body" alone is what the five-word version said.
	if !strings.Contains(strings.ToUpper(desc), "PROSE") {
		t.Errorf("book_chapter_create.body must name itself as the chapter's PROSE — the model has "+
			"to know this is the same content save_draft takes; got: %q", desc)
	}
	// It must say what omitting it COSTS. This is the half that was missing, and the half the
	// four stranded chapters are evidence for: "(optional)" reads as "harmless".
	if !strings.Contains(strings.ToUpper(desc), "EMPTY") {
		t.Errorf("book_chapter_create.body must say that omitting it creates an EMPTY chapter — "+
			"\"optional\" alone reads as harmless, and four chapters were stranded that way; got: %q", desc)
	}
	// It must point at the tool that can still rescue such a chapter, so the advice is actionable
	// rather than merely a warning.
	if !strings.Contains(desc, "book_chapter_save_draft") {
		t.Errorf("book_chapter_create.body must name book_chapter_save_draft as the way a chapter "+
			"left empty is filled later; got: %q", desc)
	}
}

// 🔴 THE ARM THAT KEEPS THIS HONEST. A description is only advice if the field stays OPTIONAL.
// Making body required would refuse the skeleton-building case — chapters created up front and
// written later — which is legitimate authoring and was never the defect. The measured failure was
// a model that did not know where the prose went, not one that was allowed to omit it.
func TestCreateBodyStaysOptional(t *testing.T) {
	f, ok := reflect.TypeOf(chapterCreateIn{}).FieldByName("Body")
	if !ok {
		t.Fatal("chapterCreateIn has no Body field")
	}
	if !strings.Contains(f.Tag.Get("json"), "omitempty") {
		t.Error("body must remain optional — a required body refuses the legitimate case of " +
			"creating a chapter skeleton to fill in later, which was never the defect")
	}
	if !strings.Contains(strings.ToUpper(f.Tag.Get("jsonschema")), "OPTIONAL") {
		t.Error("body's description must still say OPTIONAL — the fix is that omitting it has a " +
			"stated cost, not that it is forbidden")
	}
}

// The sibling this borrows its language from must keep saying it, or the two surfaces drift and
// the model is back to guessing which one takes the prose.
func TestSaveDraftBodyStillNamesItselfAsTheProse(t *testing.T) {
	f, ok := reflect.TypeOf(saveDraftIn{}).FieldByName("Body")
	if !ok {
		t.Fatal("saveDraftIn has no Body field")
	}
	if !strings.Contains(strings.ToUpper(f.Tag.Get("jsonschema")), "PROSE") {
		t.Errorf("book_chapter_save_draft.body must keep naming itself the chapter's PROSE — "+
			"book_chapter_create.body now points at it by name; got: %q", f.Tag.Get("jsonschema"))
	}
}

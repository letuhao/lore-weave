package api

// T28-D1 — a search that matched NOTHING must say so.
//
// glossary_search falls back to the book's most recently touched entities when the query matches
// nothing. That is a useful orientation answer, but it arrived in the same `entities` array, with
// the same shape, as real matches — the payload carried no top-level signal at all, so a caller
// could not tell 4 MATCHES from 0 matches plus 4 recents.
//
// MEASURED 2026-08-13: searching a throwaway book for 'zzzznotathing' returned all four of its
// entities. Cycle 10 measured the live version of the same thing — searching for the character
// 'Lam Uyen' returned unrelated EVENTS ("Cuộc đối thoại với Tô Thanh Dao") at rank_score 0.1 as
// the top results.
//
// Same class as T7-D2 (a listing emptied by a filter that claimed no such tools existed), and the
// same rule the ai-gateway's find_tools states for itself: "keeps pure-noise near-misses out so a
// true 'no such tool' reads as empty (anti-false-suggestion), not a bogus match."

import "testing"

func ents(tiers ...string) []glossaryEntityForContext {
	out := make([]glossaryEntityForContext, 0, len(tiers))
	for _, t := range tiers {
		out = append(out, glossaryEntityForContext{Tier: t})
	}
	return out
}

func TestAllRecentIsAFallback(t *testing.T) {
	if !searchIsRecentFallback(ents(tierRecent, tierRecent)) {
		t.Error("every entity is the recent fallback, so the caller must be told nothing matched")
	}
}

func TestAnyRealMatchIsNotAFallback(t *testing.T) {
	// CONTROL, and the one that matters most: a genuine hit must never be labelled a non-match,
	// even when recents pad the tail.
	if searchIsRecentFallback(ents(tierExact, tierRecent, tierRecent)) {
		t.Error("an exact match is present, so this is NOT a fallback")
	}
}

func TestEmptyIsNotAFallback(t *testing.T) {
	// Zero results already read as "nothing found" on their own; adding the note there would be
	// noise, and `len(entities) == 0` is the honest signal.
	if searchIsRecentFallback(nil) || searchIsRecentFallback(ents()) {
		t.Error("an empty result set is not the recent fallback")
	}
}

func TestANonRecentTierAnywhereDefeatsIt(t *testing.T) {
	for _, tier := range []string{tierExact, "alias", "semantic", "pinned", ""} {
		if searchIsRecentFallback(ents(tierRecent, tier)) {
			t.Errorf("tier %q is not the recent fallback, so the set is not one either", tier)
		}
	}
}

func TestTheNoteIsWiredIntoTheHandler(t *testing.T) {
	// CALL-SITE guard. The helper above is pure; it would stay green if toolSearch never used it.
	src := readAPISourceForSearch(t)
	if !containsAll(src,
		"searchIsRecentFallback(resp.Entities)",
		"NO ENTITY MATCHED",
		`strings.TrimSpace(in.Query) != ""`,
	) {
		t.Error("toolSearch no longer sets the no-match note from searchIsRecentFallback, so a " +
			"search that matched nothing again returns recents indistinguishable from hits (T28-D1)")
	}
}

func TestTheNoteIsOmittedFromTheJSONWhenEmpty(t *testing.T) {
	// `omitempty` is what keeps a real match's payload byte-identical to before, so no consumer
	// starts branching on a field that is always present.
	src := readAPISourceForSearch(t)
	if !containsAll(src, `Note string `+"`"+`json:"note,omitempty"`+"`") {
		t.Error("the note field lost `omitempty`; it would then appear on every successful search")
	}
}

// ── T28-D1 ROUND 2 (2026-08-14) — the note was correct and the model ignored it ──────────────
//
// The original fix put the recents in `entities` and added a plain sentence beside them: "NO
// ENTITY MATCHED this query … returned for orientation only … Do NOT treat them as results for
// this search." Its own comment reasoned that "a caller that ignores it is never misled by its
// presence".
//
// Measured live 2026-08-14, K=3, through the real chat path: asked "Are there any suggested
// entries waiting for me to review?" against a book with exactly ONE queued entity, the model
// called glossary_search, received this fallback — three recents plus that exact note — and
// answered "3 suggested entries waiting for your review" on 3 of 3 runs. It used the data and
// dropped the sentence.
//
// A disclaimer is not a mechanism. These guards pin the SHAPE instead.

func TestNoMatchEmptiesEntitiesRatherThanLabellingThem(t *testing.T) {
	src := readAPISourceForSearch(t)
	if !containsAll(src,
		"out.RecentForOrientation = resp.Entities",
		"out.Entities = []glossaryEntityForContext{}",
	) {
		t.Error("a no-match must EMPTY `entities` and move the recents to " +
			"`recent_for_orientation`. Leaving them in `entities` beside a note was measured 3/3 " +
			"to be read as three search results (T28-D1 round 2)")
	}
}

func TestTheOrientationFieldIsOmittedOnARealMatch(t *testing.T) {
	// A real match must stay byte-identical to before, or every consumer starts branching on a
	// field that is always present — the same reasoning that put `omitempty` on Note.
	src := readAPISourceForSearch(t)
	if !containsAll(src, `RecentForOrientation []glossaryEntityForContext `+"`"+`json:"recent_for_orientation,omitempty"`+"`") {
		t.Error("recent_for_orientation lost `omitempty`; it would appear on successful searches")
	}
}

func TestTheNoteSaysEntitiesIsEmpty(t *testing.T) {
	// The note survives, but it now describes the SHAPE the caller can verify for itself rather
	// than asking it to disregard data it can see.
	src := readAPISourceForSearch(t)
	if !containsAll(src, "`entities` is empty") {
		t.Error("the no-match note no longer tells the caller that entities is empty")
	}
}

package domain

import (
	"testing"
	"time"

	"github.com/google/uuid"
)

// Every case below is a MEASURED one from 封神演義 (docs/specs/2026-08-02-entity-kind-resolution.md
// §1), not an invented example. The vote counts are the real ones.

var (
	kCharacter   = uuid.MustParse("00000000-0000-0000-0000-0000000000c1")
	kSpecies     = uuid.MustParse("00000000-0000-0000-0000-0000000000c2")
	kItem        = uuid.MustParse("00000000-0000-0000-0000-0000000000c3")
	kTerminology = uuid.MustParse("00000000-0000-0000-0000-0000000000c4")
	kTechnique   = uuid.MustParse("00000000-0000-0000-0000-0000000000c5")
	kPowerSystem = uuid.MustParse("00000000-0000-0000-0000-0000000000c6")
	kLocation    = uuid.MustParse("00000000-0000-0000-0000-0000000000c7")
	kOrg         = uuid.MustParse("00000000-0000-0000-0000-0000000000c8")
)

// The declared hierarchy: terminology is the generic bucket the model already treats as one.
func tree() map[uuid.UUID]uuid.UUID {
	return map[uuid.UUID]uuid.UUID{
		kTechnique:   kTerminology,
		kPowerSystem: kTerminology,
	}
}

func flat() map[uuid.UUID]uuid.UUID { return map[uuid.UUID]uuid.UUID{} }

func v(pairs ...any) []KindVote {
	out := make([]KindVote, 0, len(pairs)/2)
	for i := 0; i < len(pairs); i += 2 {
		out = append(out, KindVote{KindID: pairs[i].(uuid.UUID), Votes: pairs[i+1].(int)})
	}
	return out
}

// ── the defect this whole design exists for ──────────────────────────────────

func TestJiangZiyaStopsBeingASpecies(t *testing.T) {
	// The protagonist of 封神演義, frozen as `species` by the book's first extraction run at
	// 07:56 and never revisited, while the model went on to call him a character 64 times.
	got := ResolveKind(kSpecies, v(kCharacter, 64, kSpecies, 20), flat())
	if got.Primary != kCharacter || !got.Changed {
		t.Fatalf("64-vs-20 did not overturn the first sample: %+v", got)
	}
	if got.Refinement {
		t.Error("character is not a refinement of species -- they are different axes")
	}
}

func TestASingleStrayObservationDoesNotRekind(t *testing.T) {
	// The protection oldest-wins was RIGHT about: one mis-tag in one batch must not move a
	// settled entity. Only the "never revisit" half was wrong.
	got := ResolveKind(kCharacter, v(kCharacter, 40, kSpecies, 1), flat())
	if got.Changed {
		t.Fatalf("one stray vote re-kinded a settled entity: %+v", got)
	}
}

func TestANarrowLeadIsRecordedAsConflictNotApplied(t *testing.T) {
	// 西岐: organization 52, location 38. Neither is wrong and neither dominates. The kind
	// must not flip (each flip re-emits to the KG), and the disagreement must not vanish --
	// the writeback reported `updated` and never `conflict`, so this was invisible.
	got := ResolveKind(kLocation, v(kOrg, 52, kLocation, 38), flat())
	if got.Changed {
		t.Errorf("a 1.37x lead flipped the kind; SwitchRatio is %v", SwitchRatio)
	}
	if got.Conflict != kOrg {
		t.Errorf("the leading challenger was dropped instead of recorded: %+v", got)
	}
}

func TestHysteresisIsNotVacuous(t *testing.T) {
	// Guard for the test above: prove the SAME shape DOES switch once the lead is real, so
	// TestANarrowLeadIsRecorded cannot be passing because switching never happens at all.
	got := ResolveKind(kLocation, v(kOrg, 60, kLocation, 38), flat())
	if !got.Changed || got.Primary != kOrg {
		t.Fatalf("60-vs-38 (1.58x, over the %v threshold) failed to switch: %+v", SwitchRatio, got)
	}
}

// ── hierarchy ────────────────────────────────────────────────────────────────

func TestTerminologyToTechniqueIsARefinementAndNeedsNoMajority(t *testing.T) {
	// 土遁 and 五行方位 sit in `terminology` from before `technique` existed. Moving them
	// down is the same claim stated more precisely, so it must not have to win a vote --
	// otherwise correcting an ontology can never correct the data the old one produced.
	got := ResolveKind(kTerminology, v(kTechnique, 2), tree())
	if !got.Changed || got.Primary != kTechnique {
		t.Fatalf("refinement was blocked by the threshold: %+v", got)
	}
	if !got.Refinement {
		t.Error("a parent -> descendant move was not reported as a refinement")
	}
}

func TestGeneralisingBackUpIsNotFree(t *testing.T) {
	// The reverse is a normal challenge and DOES face the threshold -- otherwise a single
	// lazy `terminology` answer would undo every refinement.
	got := ResolveKind(kTechnique, v(kTerminology, 1, kTechnique, 5), tree())
	if got.Changed {
		t.Fatalf("child -> parent was treated as free: %+v", got)
	}
}

func TestSplitChildrenResolveToTheParent(t *testing.T) {
	// The rule that makes "if unsure, use the generic kind" real. Evenly split children mean
	// the text has not decided, and the honest answer is the parent -- not a coin toss
	// between two specific kinds that then freezes.
	got := ResolveKind(kCharacter, v(kTechnique, 5, kPowerSystem, 5), tree())
	if got.Primary != kTerminology {
		t.Fatalf("a 5-5 split between siblings did not fall back to the parent: %+v", got)
	}
}

func TestAClearChildStillWinsOverItsParent(t *testing.T) {
	// Vacuity guard for the test above: the fallback must not be "always the parent".
	got := ResolveKind(kCharacter, v(kTechnique, 10, kPowerSystem, 2), tree())
	if got.Primary != kTechnique {
		t.Fatalf("a 10-vs-2 child majority did not descend: %+v", got)
	}
}

func TestRollUpLetsABranchBeatASingleKind(t *testing.T) {
	// No single concept kind beats `character`'s 8 on its own votes, but "some kind of
	// concept" has 14. Without roll-up the branch loses to a kind it collectively outweighs.
	got := ResolveKind(kCharacter, v(kTechnique, 7, kPowerSystem, 7, kCharacter, 8), tree())
	if got.Primary != kTerminology {
		t.Fatalf("the branch's combined 14 lost to a single kind's 8: %+v", got)
	}
}

// ── facets ───────────────────────────────────────────────────────────────────

func TestBothReadingsSurviveAsALabel(t *testing.T) {
	// 西岐 is a place AND a polity. Multi-label exists so one of them stops being erased.
	got := ResolveKind(kOrg, v(kOrg, 52, kLocation, 38), flat())
	if len(got.Secondary) != 1 || got.Secondary[0] != kLocation {
		t.Fatalf("the second reading was dropped: %+v", got)
	}
}

func TestAnAncestorIsNotAFacet(t *testing.T) {
	// `terminology` votes on an entity resolved to `technique` are not a second AXIS -- they
	// are the same claim, less precisely. Surfacing them as a facet would put a generic
	// badge on every refined entity.
	got := ResolveKind(kTechnique, v(kTechnique, 10, kTerminology, 6), tree())
	if len(got.Secondary) != 0 {
		t.Fatalf("an ancestor was surfaced as a facet: %+v", got)
	}
}

func TestAStrayReadingIsNotAFacet(t *testing.T) {
	got := ResolveKind(kCharacter, v(kCharacter, 40, kItem, 1), flat())
	if len(got.Secondary) != 0 {
		t.Fatalf("a 1-vote stray became a label: %+v", got)
	}
}

// ── degenerate input ─────────────────────────────────────────────────────────

func TestNoVotesKeepsTheIncumbent(t *testing.T) {
	got := ResolveKind(kCharacter, nil, flat())
	if got.Primary != kCharacter || got.Changed {
		t.Fatalf("an entity with no observations was disturbed: %+v", got)
	}
}

func TestACycleInTheParentChainTerminates(t *testing.T) {
	// A parent chain is authored data, so a cycle is reachable by an admin mistake. It must
	// not hang the extraction writeback.
	cyc := map[uuid.UUID]uuid.UUID{kTechnique: kTerminology, kTerminology: kTechnique}
	done := make(chan Resolution, 1)
	go func() { done <- ResolveKind(kTechnique, v(kTechnique, 5, kTerminology, 3), cyc) }()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("a parent cycle hung the resolver")
	}
}

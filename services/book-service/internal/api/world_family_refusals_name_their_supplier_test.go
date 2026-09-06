package api

// The world/map family is UUID-only, and its refusals now say where an id comes from.
//
// MEASURED, batch 29 of the tool deep-dive, 25 live runs across five tools. Asked about a world
// or a map BY NAME -- the only way a person refers to one -- the model passed the name (or a
// token out of it) as the id, was refused with a bare "world not found" / "map not found", and
// stopped:
//
//	"I couldn't find a world with the exact name 'Emberfall Reach Zemozase' ... I need the
//	 specific ID for that world to list its maps."
//	"It seems 'Rubodebi' isn't the correct ID for the map you're looking for."
//
// Two things are worth separating there. The model never INVENTED a UUID -- the invented-id
// guard held every time -- and it never chained to the supplier either. It had nowhere to go: a
// bare "not found" says the id is wrong without saying what would make it right.
//
// This service already has the counter-example, and it is the best refusal the whole loop found:
// book_chapter_update_meta answers "no active chapter with that chapter_id in this book -- check
// the chapter_id (call book_list kind=chapters for valid ids)". It names the problem AND THE
// SUPPLIER. In the same batch that family resolved names 5/5.
//
// WHAT THIS TEST IS AND IS NOT. It pins the CONTRACT: the refusal names its supplier, and the
// two refusals stay identical between "not yours" and "no such row" so neither becomes an
// existence oracle for another account. It does NOT claim the model now chains -- that is a live
// A/B measurement, recorded in the batch evidence, and prose has been refuted as a lever in this
// repo before (rewording a refusal once moved a lookup 1/5 -> 0/5). The contract is worth
// holding either way.

import (
	"strings"
	"testing"
)

func TestWorldRefusalNamesItsSupplier(t *testing.T) {
	msg := errNoSuchWorld.Error()
	if !strings.Contains(msg, "world_list") {
		t.Errorf("the world refusal no longer names world_list, the only supplier of a "+
			"world_id: %q", msg)
	}
	if !strings.Contains(msg, "world_id") {
		t.Errorf("the refusal must name the ARGUMENT it is about: %q", msg)
	}
}

func TestMapRefusalNamesItsSupplier(t *testing.T) {
	msg := errNoSuchMap.Error()
	if !strings.Contains(msg, "world_map_list") {
		t.Errorf("the map refusal no longer names world_map_list, the only supplier of a "+
			"map_id: %q", msg)
	}
	if !strings.Contains(msg, "map_id") {
		t.Errorf("the refusal must name the ARGUMENT it is about: %q", msg)
	}
}

func TestTheTwoRefusalsAreDistinct(t *testing.T) {
	// A map tool answering the world wording (or vice versa) would send the model to the wrong
	// supplier, which is worse than saying nothing.
	if errNoSuchWorld.Error() == errNoSuchMap.Error() {
		t.Fatal("the world and map refusals are identical; each must point at its OWN supplier")
	}
	if strings.Contains(errNoSuchWorld.Error(), "world_map_list") {
		t.Error("the world refusal points at the MAP supplier")
	}
}

func TestTheRefusalsAreStillNotAnExistenceOracle(t *testing.T) {
	// The wording is one constant per kind, used for both "not yours" and "no such row". That
	// is the property that keeps it from telling one account about another's rows, and a
	// single shared constant is what makes it structurally true rather than a convention.
	for _, msg := range []string{errNoSuchWorld.Error(), errNoSuchMap.Error()} {
		for _, leak := range []string{"belongs to", "another", "not yours", "owned by"} {
			if strings.Contains(strings.ToLower(msg), leak) {
				t.Errorf("refusal %q distinguishes not-yours from no-such-row", msg)
			}
		}
	}
}

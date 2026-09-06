package api

// TOOL-V2 LOOP iteration 1 — glossary_propose_curation.
//
// The subject is measured, not imagined. Of the tool's 70 recorded calls, 42 are
// input_required suspensions (typed `deferred` — never failures) and 28 are genuine
// failures. 26 of those 28, across 15 distinct sessions, are ONE shape: `entity_id`
// (singular, a syntactically valid UUID) sent with op=status_change, which reads only
// `entity_ids`. The flat superset schema ACCEPTS entity_id — it is a declared field of
// this tool — and dispatch then silently drops it.
//
// These tests pin the repair AND the refusals it must not swallow. They need no DB.

import (
	"reflect"
	"testing"

	"github.com/google/uuid"
)

// TestCoalesceCurationEntityRef_TheRecordedFailure replays the corpus argument object
// VERBATIM. This is the falsifier for the fix: revert coalesceCurationEntityRef and this
// test goes red on the exact input 15 sessions produced.
func TestCoalesceCurationEntityRef_TheRecordedFailure(t *testing.T) {
	// Recorded 2026-08 in loreweave_chat, 26 calls / 15 sessions, all identical in shape:
	//   {"op":"status_change","status":"active","book_id":"…","entity_id":"019fea5a-…"}
	in := proposeCurationToolIn{
		Op:       "status_change",
		Status:   "active",
		BookID:   "019fea46-0694-76a9-94dd-a13c81b1f218",
		EntityID: "019fea5a-4ef0-74ee-a5c3-4bb3b1eaf6bc",
	}
	got := coalesceCurationEntityRef(in)
	if len(got.EntityIDs) != 1 || got.EntityIDs[0] != in.EntityID {
		t.Fatalf("the singular entity_id must reach op=status_change as a one-element list; got %#v",
			got.EntityIDs)
	}
	// parseEntityIDs is what the core runs next — the coalesced value has to survive it,
	// because a list that parses to zero ids produces the SAME misleading error.
	if len(parseEntityIDs(got.EntityIDs)) != 1 {
		t.Fatal("the coalesced id must parse as a UUID, or the core still refuses")
	}
}

func TestCoalesceCurationEntityRef_DoesNotOverrideAnExplicitList(t *testing.T) {
	a, b := uuid.NewString(), uuid.NewString()
	got := coalesceCurationEntityRef(proposeCurationToolIn{
		Op: "status_change", Status: "active",
		EntityID: uuid.NewString(), EntityIDs: []string{a, b},
	})
	if len(got.EntityIDs) != 2 || got.EntityIDs[0] != a || got.EntityIDs[1] != b {
		t.Fatalf("an explicit entity_ids list wins over the singular; got %#v", got.EntityIDs)
	}
}

// A blank-only list is not a list. Without the emptiness check being value-aware, [""] would
// shadow a perfectly good singular and hand the core a list that parses to zero ids.
func TestCoalesceCurationEntityRef_BlankListDoesNotShadowTheSingular(t *testing.T) {
	id := uuid.NewString()
	got := coalesceCurationEntityRef(proposeCurationToolIn{
		Op: "status_change", Status: "active", EntityID: id, EntityIDs: []string{"", "  "},
	})
	if len(got.EntityIDs) != 1 || got.EntityIDs[0] != id {
		t.Fatalf("a blank-only list must not shadow the singular; got %#v", got.EntityIDs)
	}
}

// The reverse arm. Zero measured occurrences — written because it is the same defect wearing
// the other shoe, and deliberately gated to EXACTLY ONE element.
func TestCoalesceCurationEntityRef_ReverseArmSingleElementOnly(t *testing.T) {
	one, two := uuid.NewString(), uuid.NewString()
	for _, op := range []string{"restore_revision", "reassign_kind"} {
		got := coalesceCurationEntityRef(proposeCurationToolIn{Op: op, EntityIDs: []string{one}})
		if got.EntityID != one {
			t.Errorf("%s: a one-element entity_ids must fill the singular; got %q", op, got.EntityID)
		}
		// Two entities and one singular slot has NO coherent reading. Picking one would be a
		// repair that emits parseable-but-wrong output — it must keep refusing.
		if got := coalesceCurationEntityRef(
			proposeCurationToolIn{Op: op, EntityIDs: []string{one, two}}); got.EntityID != "" {
			t.Errorf("%s: a multi-element list must NOT be narrowed to one; got %q", op, got.EntityID)
		}
	}
}

// merge declares no singular counterpart, and an unknown op must not be quietly normalised
// into a shape the dispatch default would then reject with a different story.
func TestCoalesceCurationEntityRef_LeavesOtherOpsUntouched(t *testing.T) {
	for _, op := range []string{"merge", "", "bogus_op"} {
		in := proposeCurationToolIn{
			Op: op, EntityID: uuid.NewString(), EntityIDs: []string{uuid.NewString()},
			WinnerID: uuid.NewString(), LoserIDs: []string{uuid.NewString()},
		}
		if got := coalesceCurationEntityRef(in); !reflect.DeepEqual(got, in) {
			t.Errorf("op=%q must pass through unchanged; got %#v", op, got)
		}
	}
}

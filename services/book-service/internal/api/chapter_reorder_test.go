package api

// The permutation itself, headless. `moveWithin` decides WHERE a chapter lands; the DB test proves
// the resulting sequence survives the partial unique index.

import (
	"testing"

	"github.com/google/uuid"
)

func ids(n int) []uuid.UUID {
	out := make([]uuid.UUID, n)
	for i := range out {
		out[i] = uuid.New()
	}
	return out
}

func eq(t *testing.T, got, want []uuid.UUID, msg string) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("%s: len %d, want %d", msg, len(got), len(want))
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("%s: [%d] = %s, want %s", msg, i, got[i], want[i])
		}
	}
}

func TestMoveWithin(t *testing.T) {
	c := ids(4)

	got, ok := moveWithin(c, c[3], &c[0])
	if !ok {
		t.Fatal("move after first: !ok")
	}
	eq(t, got, []uuid.UUID{c[0], c[3], c[1], c[2]}, "move last to after first")

	got, ok = moveWithin(c, c[0], nil)
	if !ok {
		t.Fatal("move to front: !ok")
	}
	eq(t, got, c, "moving the first chapter to the front is a no-op, not a rotation")

	got, ok = moveWithin(c, c[2], nil)
	if !ok {
		t.Fatal("to front: !ok")
	}
	eq(t, got, []uuid.UUID{c[2], c[0], c[1], c[3]}, "to front")

	// After the CURRENT last ⇒ becomes last.
	got, ok = moveWithin(c, c[0], &c[3])
	if !ok {
		t.Fatal("to back: !ok")
	}
	eq(t, got, []uuid.UUID{c[1], c[2], c[3], c[0]}, "to back")

	// Moving a chapter to directly after its own predecessor is a NO-OP — not a swap. This is the
	// case a naive "remove then insert at index" gets wrong by an off-by-one.
	got, ok = moveWithin(c, c[2], &c[1])
	if !ok {
		t.Fatal("no-op move: !ok")
	}
	eq(t, got, c, "after its own predecessor = unchanged")

	// Length is preserved and nothing is duplicated or dropped.
	got, _ = moveWithin(c, c[1], &c[3])
	seen := map[uuid.UUID]int{}
	for _, x := range got {
		seen[x]++
	}
	if len(seen) != 4 {
		t.Fatalf("permutation lost/duplicated an element: %v", got)
	}
}

func TestMoveWithin_RejectsUnknownIds(t *testing.T) {
	c := ids(3)
	stranger := uuid.New()

	if _, ok := moveWithin(c, stranger, nil); ok {
		t.Fatal("moving a chapter that isn't in the sequence must fail, not append it")
	}
	// An after_id outside the sequence must be REJECTED, not silently ignored (which would dump the
	// chapter at the front — a position the user never asked for).
	if _, ok := moveWithin(c, c[0], &stranger); ok {
		t.Fatal("an unknown after_id must fail, not fall back to the front")
	}
}

package api

import (
	"testing"

	"github.com/google/uuid"
)

// betterWinner picks the richest entity as the merge winner: more chapter links,
// then more evidence, then the smaller id (stable so a re-run is deterministic).
func TestBetterWinner(t *testing.T) {
	idA := uuid.MustParse("00000000-0000-0000-0000-0000000000aa")
	idB := uuid.MustParse("00000000-0000-0000-0000-0000000000bb")

	mk := func(id uuid.UUID, links, evid int) dedupEnt {
		return dedupEnt{id: id, linkCount: links, evidCount: evid}
	}

	cases := []struct {
		name      string
		cand, cur dedupEnt
		want      bool
	}{
		{"more links wins", mk(idB, 5, 0), mk(idA, 3, 9), true},
		{"fewer links loses", mk(idB, 1, 9), mk(idA, 3, 0), false},
		{"link tie → more evidence wins", mk(idB, 3, 7), mk(idA, 3, 2), true},
		{"link tie → fewer evidence loses", mk(idB, 3, 1), mk(idA, 3, 5), false},
		{"full tie → smaller id wins", mk(idA, 3, 5), mk(idB, 3, 5), true},
		{"full tie → larger id loses", mk(idB, 3, 5), mk(idA, 3, 5), false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := betterWinner(c.cand, c.cur); got != c.want {
				t.Errorf("betterWinner = %v, want %v", got, c.want)
			}
		})
	}
}

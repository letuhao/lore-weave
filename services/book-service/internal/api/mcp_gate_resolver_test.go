package api

import "testing"

// grantForOp maps a book action's op to the grant level its ACCEPT re-checks. The
// purge ops MUST require a higher level than a plain edit — a defense-in-depth
// regression here would let an EDIT collaborator drive an irreversible purge.
func TestGrantForOp(t *testing.T) {
	cases := map[string]GrantLevel{
		"publish":        GrantEdit,
		"unpublish":      GrantEdit,
		"delete_chapter": GrantEdit,
		"purge_chapter":  GrantManage,
		"purge_book":     GrantOwner,
		"delete_book":    GrantOwner,
		"unknown_op":     GrantEdit, // default floor
	}
	for op, want := range cases {
		if got := grantForOp(op); got != want {
			t.Errorf("grantForOp(%q) = %v, want %v", op, got, want)
		}
	}
}

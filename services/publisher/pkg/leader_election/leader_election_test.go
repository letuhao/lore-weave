package leader_election

import "testing"

func TestNoOp_AlwaysLeader(t *testing.T) {
	l := NewNoOp()
	if !l.IsLeader() {
		t.Fatal("V1 no-op leader MUST return true (Q-L2-5)")
	}
	l.Step() // no-op; must not panic
	l.Stop() // no-op; must not panic
	if !l.IsLeader() {
		t.Fatal("IsLeader must remain true after Step+Stop")
	}
}

// LeaderInterface compile-time check — guarantees NoOp matches the
// `Leader` contract so the V2+ swap is purely additive.
func TestNoOp_ImplementsLeader(t *testing.T) {
	var _ Leader = (*NoOp)(nil)
	var _ Leader = NewNoOp()
}

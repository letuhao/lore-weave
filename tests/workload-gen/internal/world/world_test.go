package world

import "testing"

func TestNextVersionMonotonicPerAggregate(t *testing.T) {
	w := New(1)
	r := w.AddReality()
	for i := uint64(1); i <= 3; i++ {
		if got := w.NextVersion(r, "npc", "npc-1"); got != i {
			t.Errorf("npc-1 version %d, want %d", got, i)
		}
	}
	// a different aggregate has its own independent cursor
	if got := w.NextVersion(r, "npc", "npc-2"); got != 1 {
		t.Errorf("npc-2 first version = %d, want 1", got)
	}
	if got := w.NextVersion(r, "region", "npc-1"); got != 1 {
		t.Errorf("a different aggregate_type with same id is a distinct cursor; got %d, want 1", got)
	}
}

func TestPickReturnsOnlyCreatedEntities(t *testing.T) {
	w := New(2)
	r := w.AddReality()
	if _, ok := w.PickRegion(r); ok {
		t.Error("PickRegion on an empty reality must return false (no forward reference)")
	}
	created := map[string]bool{}
	for i := 0; i < 5; i++ {
		created[w.AddRegion(r)] = true
	}
	for i := 0; i < 50; i++ {
		got, ok := w.PickRegion(r)
		if !ok || !created[got] {
			t.Fatalf("PickRegion returned an uncreated id %q (ok=%v)", got, ok)
		}
	}
}

func TestDeterminismSameSeedSameSequence(t *testing.T) {
	run := func(seed int64) []string {
		w := New(seed)
		r := w.AddReality()
		var trace []string
		trace = append(trace, r.String())
		for i := 0; i < 4; i++ {
			trace = append(trace, w.AddRegion(r))
			trace = append(trace, w.AddNpc(r))
		}
		// interleave some picks so RNG draws are part of the trace
		for i := 0; i < 6; i++ {
			if id, ok := w.PickRegion(r); ok {
				trace = append(trace, "pick:"+id)
			}
		}
		return trace
	}
	a, b := run(42), run(42)
	if len(a) != len(b) {
		t.Fatalf("trace lengths differ: %d vs %d", len(a), len(b))
	}
	for i := range a {
		if a[i] != b[i] {
			t.Fatalf("same seed diverged at %d: %q vs %q", i, a[i], b[i])
		}
	}
	// a different seed should produce a different reality id
	if run(43)[0] == a[0] {
		t.Error("different seeds should yield different entity ids")
	}
}

func TestEntityIDsAreDistinct(t *testing.T) {
	w := New(7)
	r := w.AddReality()
	seen := map[string]bool{r.String(): true}
	for i := 0; i < 20; i++ {
		for _, id := range []string{w.AddRegion(r), w.AddNpc(r), w.AddPc(r), w.AddSession(r)} {
			if seen[id] {
				t.Fatalf("duplicate entity id %q", id)
			}
			seen[id] = true
		}
	}
}

func TestAddUnderUnknownRealityPanics(t *testing.T) {
	defer func() {
		if recover() == nil {
			t.Error("AddRegion under an unknown reality must panic (programming error)")
		}
	}()
	w := New(1)
	other := New(99).AddReality() // a reality this World never created
	w.AddRegion(other)
}

package gen

import (
	"encoding/json"
	"testing"
)

func streamJSON(t *testing.T, s Stream) string {
	t.Helper()
	b, err := json.Marshal(s)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return string(b)
}

func distinctRealities(s Stream) int {
	seen := map[string]bool{}
	for _, e := range s {
		seen[e.RealityID.String()] = true
	}
	return len(seen)
}

func countType(s Stream, et string) int {
	n := 0
	for _, e := range s {
		if e.EventType == et {
			n++
		}
	}
	return n
}

func TestDeterminismAllProfiles(t *testing.T) {
	for name, p := range Profiles {
		a := streamJSON(t, New(7).Generate(p))
		b := streamJSON(t, New(7).Generate(p))
		if a != b {
			t.Errorf("%s: same seed produced different streams", name)
		}
	}
}

func TestDifferentSeedDiffers(t *testing.T) {
	p := Profiles["single-reality"]
	if streamJSON(t, New(1).Generate(p)) == streamJSON(t, New(2).Generate(p)) {
		t.Error("different seeds should yield different streams")
	}
}

func TestValidateAllProfiles(t *testing.T) {
	for name, p := range Profiles {
		s := New(3).Generate(p)
		if len(s) == 0 {
			t.Errorf("%s: empty stream", name)
			continue
		}
		if err := Validate(s); err != nil {
			t.Errorf("%s: generated stream failed Validate: %v", name, err)
		}
	}
}

func TestValidateCatchesDanglingReference(t *testing.T) {
	s := New(1).Generate(Profiles["micro"])
	corrupted := false
	for i := range s {
		if s[i].EventType == "npc.created" {
			s[i].Payload["spawn_region_id"] = "ghost-region"
			corrupted = true
			break
		}
	}
	if !corrupted {
		t.Fatal("test setup: micro stream had no npc.created to corrupt")
	}
	if Validate(s) == nil {
		t.Error("Validate must reject a dangling spawn_region_id reference")
	}
}

func TestValidateCatchesVersionGap(t *testing.T) {
	s := New(1).Generate(Profiles["micro"])
	s[0].AggregateVersion = 5 // the first event for an aggregate must be version 1
	if Validate(s) == nil {
		t.Error("Validate must reject a non-contiguous aggregate version")
	}
}

func TestProfileShapes(t *testing.T) {
	if n := distinctRealities(New(1).Generate(Profiles["micro"])); n != 1 {
		t.Errorf("micro realities = %d, want 1", n)
	}
	if n := distinctRealities(New(1).Generate(Profiles["multi-reality"])); n != 3 {
		t.Errorf("multi-reality realities = %d, want 3", n)
	}
	if n := countType(New(1).Generate(Profiles["multi-user-session"]), "session.started"); n < 4 {
		t.Errorf("multi-user-session session.started = %d, want >= 4", n)
	}
}

func TestSingleRealityCoversTheSurface(t *testing.T) {
	// One stream should exercise every aggregate family so the spine touches
	// all projection tables (broad surface).
	s := New(9).Generate(Profiles["single-reality"])
	for _, et := range []string{
		"region.created", "npc.created", "npc.said", "pc.spawned",
		"session.started", "session.participant_joined", "session.ended",
		"world.kv_set", "world.kv_unset", "canon.entry.created",
	} {
		if countType(s, et) == 0 {
			t.Errorf("single-reality stream is missing %q", et)
		}
	}
}

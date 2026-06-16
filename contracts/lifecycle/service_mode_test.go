package lifecycle

import (
	"errors"
	"testing"
)

func TestServiceMode_String_RoundTrip(t *testing.T) {
	for _, m := range AllModes() {
		s := m.String()
		round, err := ParseServiceMode(s)
		if err != nil {
			t.Errorf("ParseServiceMode(%q): %v", s, err)
			continue
		}
		if round != m {
			t.Errorf("round-trip drift: %v→%q→%v", m, s, round)
		}
	}
}

func TestParseServiceMode_AcceptsCanonicalAliases(t *testing.T) {
	cases := []struct {
		in   string
		want ServiceMode
	}{
		{"FULL", ModeFull},
		{"  limited ", ModeLimited},
		{"essentials", ModeEssentials},
		{"read_only", ModeReadOnly},
		{"readonly", ModeReadOnly}, // tolerant alias
		{"OFFLINE", ModeOffline},
	}
	for _, c := range cases {
		got, err := ParseServiceMode(c.in)
		if err != nil {
			t.Errorf("ParseServiceMode(%q) err=%v", c.in, err)
			continue
		}
		if got != c.want {
			t.Errorf("ParseServiceMode(%q) = %v, want %v", c.in, got, c.want)
		}
	}
}

func TestParseServiceMode_Invalid(t *testing.T) {
	for _, bad := range []string{"", "maintenance", "degraded", "panic"} {
		_, err := ParseServiceMode(bad)
		if !errors.Is(err, ErrInvalidServiceMode) {
			t.Errorf("ParseServiceMode(%q) err=%v, want ErrInvalidServiceMode", bad, err)
		}
	}
}

func TestAllModes_ExhaustiveExactly5(t *testing.T) {
	// SR06-D5 fixes the enum at 5 entries. Test pins this so a future
	// caller can't append "Maintenance" without updating this gate.
	if got := len(AllModes()); got != 5 {
		t.Fatalf("AllModes() = %d entries, want exactly 5 per SR06-D5", got)
	}
	want := []ServiceMode{ModeFull, ModeLimited, ModeEssentials, ModeReadOnly, ModeOffline}
	for i, m := range want {
		if AllModes()[i] != m {
			t.Errorf("AllModes()[%d] = %v, want %v", i, AllModes()[i], m)
		}
	}
}

func TestAcceptsWrites(t *testing.T) {
	cases := map[ServiceMode]bool{
		ModeFull:       true,
		ModeLimited:    true,
		ModeEssentials: true,
		ModeReadOnly:   false,
		ModeOffline:    false,
	}
	for m, want := range cases {
		if got := m.AcceptsWrites(); got != want {
			t.Errorf("%v.AcceptsWrites() = %v, want %v", m, got, want)
		}
	}
}

func TestAcceptsBackgroundJobs(t *testing.T) {
	cases := map[ServiceMode]bool{
		ModeFull:       true,
		ModeLimited:    true,
		ModeEssentials: false, // pauses background jobs to preserve critical path
		ModeReadOnly:   false,
		ModeOffline:    false,
	}
	for m, want := range cases {
		if got := m.AcceptsBackgroundJobs(); got != want {
			t.Errorf("%v.AcceptsBackgroundJobs() = %v, want %v", m, got, want)
		}
	}
}

func TestAcceptsFreshAckRequired(t *testing.T) {
	for _, m := range AllModes() {
		got := m.AcceptsFreshAckRequired()
		want := m == ModeFull
		if got != want {
			t.Errorf("%v.AcceptsFreshAckRequired() = %v, want %v", m, got, want)
		}
	}
}

func TestGreaterOrEqual_Ladder(t *testing.T) {
	if !ModeReadOnly.GreaterOrEqual(ModeLimited) {
		t.Error("ReadOnly should be >= Limited")
	}
	if ModeFull.GreaterOrEqual(ModeEssentials) {
		t.Error("Full should NOT be >= Essentials")
	}
	if !ModeFull.GreaterOrEqual(ModeFull) {
		t.Error("Full should be >= Full (reflexive)")
	}
}

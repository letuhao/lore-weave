package prompt

import (
	"errors"
	"testing"
)

func TestAllSectionsCount(t *testing.T) {
	if got, want := len(AllSections()), 8; got != want {
		t.Fatalf("AllSections count = %d; want %d (S09 §12Y.4 vocabulary)", got, want)
	}
}

func TestAllSectionsOrderFixed(t *testing.T) {
	want := []Section{
		SectionSystem,
		SectionWorldCanon,
		SectionSessionState,
		SectionActorContext,
		SectionMemory,
		SectionHistory,
		SectionInstruction,
		SectionInput,
	}
	got := AllSections()
	if len(got) != len(want) {
		t.Fatalf("AllSections length = %d; want %d", len(got), len(want))
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("AllSections[%d] = %q; want %q (order is FIXED — S09 §12Y.4)", i, got[i], want[i])
		}
	}
}

func TestAllSectionsCopyIsolated(t *testing.T) {
	// Mutating the returned slice MUST NOT leak into the internal
	// canonical sectionOrder slice (defensive copy).
	got := AllSections()
	got[0] = SectionInput
	again := AllSections()
	if again[0] != SectionSystem {
		t.Errorf("AllSections() returned a slice that aliases the internal order; first element was clobbered to %q", again[0])
	}
}

func TestParseSection_OK(t *testing.T) {
	for _, want := range AllSections() {
		got, err := ParseSection(string(want))
		if err != nil {
			t.Errorf("ParseSection(%q) err = %v; want nil", want, err)
			continue
		}
		if got != want {
			t.Errorf("ParseSection(%q) = %q; want %q", want, got, want)
		}
	}
}

func TestParseSection_Unknown(t *testing.T) {
	_, err := ParseSection("system") // lowercase = invalid (wire format is UPPERCASE)
	if err == nil {
		t.Fatalf("ParseSection(lowercase) returned nil err; want ErrUnknownSection")
	}
	if !errors.Is(err, ErrUnknownSection) {
		t.Errorf("ParseSection(lowercase) err = %v; want wraps ErrUnknownSection", err)
	}
}

func TestSection_IsUserSandbox(t *testing.T) {
	// Only SectionInput is the user-sandbox section.
	for _, s := range AllSections() {
		want := s == SectionInput
		if s.IsUserSandbox() != want {
			t.Errorf("IsUserSandbox(%q) = %v; want %v", s, s.IsUserSandbox(), want)
		}
	}
}

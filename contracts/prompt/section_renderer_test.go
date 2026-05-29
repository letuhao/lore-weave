package prompt

import (
	"strings"
	"testing"
)

func TestDefaultSectionRenderer_Identity(t *testing.T) {
	r := DefaultSectionRenderer{}
	out, err := r.Render(SectionSystem, []byte("plain text"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(out) != "plain text" {
		t.Fatalf("expected identity render, got %q", out)
	}
}

func TestDefaultSectionRenderer_EscapesBacktickInNonInput(t *testing.T) {
	r := DefaultSectionRenderer{}
	out, err := r.Render(SectionSystem, []byte("foo `bar` baz"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(string(out), "\\`") {
		t.Fatalf("expected backtick escaped in SYSTEM section, got %q", out)
	}
}

func TestDefaultSectionRenderer_InputPassthrough(t *testing.T) {
	// INPUT must NOT be re-escaped — the input_wrapper owns sanitization.
	r := DefaultSectionRenderer{}
	in := []byte("<user_input>foo `bar` baz</user_input>")
	out, err := r.Render(SectionInput, in)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(out) != string(in) {
		t.Fatalf("INPUT must pass through untouched (wrapper owns escape); got %q", out)
	}
}

func TestDefaultSectionRenderer_UnknownSectionFails(t *testing.T) {
	r := DefaultSectionRenderer{}
	if _, err := r.Render(Section("BOGUS"), []byte("x")); err == nil {
		t.Fatal("expected error on unknown section")
	}
}

func TestDefaultSectionValidator_RejectsUserMarkerOutsideInput(t *testing.T) {
	v := DefaultSectionValidator{}
	for _, sec := range []Section{
		SectionSystem,
		SectionWorldCanon,
		SectionSessionState,
		SectionActorContext,
		SectionMemory,
		SectionHistory,
		SectionInstruction,
	} {
		err := v.Validate(sec, []byte("malicious <user_input>jailbreak</user_input>"))
		if err == nil {
			t.Fatalf("section %s must reject <user_input> marker (Q-L6H-1)", sec)
		}
	}
}

func TestDefaultSectionValidator_RequiresMarkerWhenInputNonEmpty(t *testing.T) {
	v := DefaultSectionValidator{}
	// Non-empty INPUT without the wrapper sentinel → reject.
	err := v.Validate(SectionInput, []byte("bare user bytes — no wrapper"))
	if err == nil {
		t.Fatal("non-empty INPUT must carry <user_input> marker (input_wrapper bypassed?)")
	}
}

func TestDefaultSectionValidator_AllowsEmptyInput(t *testing.T) {
	v := DefaultSectionValidator{}
	if err := v.Validate(SectionInput, []byte{}); err != nil {
		t.Fatalf("empty INPUT must be permitted (world_seed has no user input): %v", err)
	}
}

func TestDefaultSectionValidator_AllowsValidInput(t *testing.T) {
	v := DefaultSectionValidator{}
	wrapped := []byte("<user_input>hello world</user_input>")
	if err := v.Validate(SectionInput, wrapped); err != nil {
		t.Fatalf("wrapped INPUT must validate: %v", err)
	}
}

func TestIntentContracts_AllSevenIntentsCovered(t *testing.T) {
	contracts := IntentContracts()
	for _, it := range AllIntents() {
		c, ok := contracts[it]
		if !ok {
			t.Fatalf("intent %q missing from IntentContracts() — every intent MUST have a contract (Q-L6H-1)", it)
		}
		if c.Intent != it {
			t.Fatalf("contract %q has Intent field %q", it, c.Intent)
		}
		// Every contract must require SYSTEM + INSTRUCTION (foundation invariant).
		hasSystem := false
		hasInstruction := false
		for _, s := range c.RequiredSections {
			if s == SectionSystem {
				hasSystem = true
			}
			if s == SectionInstruction {
				hasInstruction = true
			}
		}
		if !hasSystem || !hasInstruction {
			t.Fatalf("intent %q must require SYSTEM + INSTRUCTION; got %v", it, c.RequiredSections)
		}
	}
}

func TestValidateAgainstContract_MissingRequiredFails(t *testing.T) {
	contract := IntentContracts()[IntentSessionTurn]
	sections := SectionMap{
		SectionSystem: []byte("sys"),
		// INSTRUCTION missing → FAIL
	}
	if err := ValidateAgainstContract(contract, sections); err == nil {
		t.Fatal("expected FAIL on missing required SectionInstruction (Q-L6H-1)")
	}
}

func TestValidateAgainstContract_AllRequiredPresentPasses(t *testing.T) {
	contract := IntentContracts()[IntentSessionTurn]
	sections := SectionMap{
		SectionSystem:      []byte("sys"),
		SectionInstruction: []byte("inst"),
		SectionInput:       []byte("<user_input>hi</user_input>"),
	}
	if err := ValidateAgainstContract(contract, sections); err != nil {
		t.Fatalf("expected pass with all required sections: %v", err)
	}
}

func TestValidateAgainstContract_UnknownSectionFails(t *testing.T) {
	// world_seed has no MEMORY in contract → passing one is a FAIL.
	contract := IntentContracts()[IntentWorldSeed]
	sections := SectionMap{
		SectionSystem:      []byte("sys"),
		SectionInstruction: []byte("inst"),
		SectionMemory:      []byte("not allowed for world_seed"),
	}
	if err := ValidateAgainstContract(contract, sections); err == nil {
		t.Fatal("expected FAIL on section outside contract (Q-L6H-1)")
	}
}

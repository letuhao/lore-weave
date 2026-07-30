package main

import (
	"os"
	"strings"
	"testing"

	"github.com/loreweave/foundation/contracts/events"
)

// The registry as shipped must be clean. This is the arm that goes red the day
// someone adds an event and forgets the field map — which is exactly what
// happened to `ruleset.epoch_activated` on 2026-07-30, silently, in three
// languages.
func TestFieldMaps_ShippedRegistryIsClean(t *testing.T) {
	if err := checkFieldMaps(shippedRegistry(t)); err != nil {
		t.Fatalf("the shipped registry has a field-map defect:\n%v", err)
	}
}

// Every allowlisted event must actually BE in the registry with no map — the
// same shrink rule `checkFieldMaps` enforces, asserted here so the list cannot
// rot without a test noticing.
func TestFieldMaps_AllowlistIsNotStale(t *testing.T) {
	reg := shippedRegistry(t)
	for key, reason := range noFieldMapAllowed {
		if strings.TrimSpace(reason) == "" {
			t.Errorf("%s has an empty reason — a row nobody can retire", key)
		}
		name, version, ok := splitFieldMapKey(key)
		if !ok {
			t.Errorf("%s is not a `<event>@<version>` key", key)
			continue
		}
		if _, err := reg.LookupType(name); err != nil {
			t.Errorf("%s is allowlisted but not in the registry: %v", key, err)
			continue
		}
		if len(fieldsForEvent(name, version)) > 0 {
			t.Errorf("%s is allowlisted but HAS a field map — delete the row", key)
		}
	}
}

// NV-6: prove each arm can fail, rather than trusting that it would.
//
// A fixture registry is not enough on its own — the arms are driven by
// `fieldsForEvent`, which is a compiled switch and cannot be varied from a
// test. So each case varies the OTHER input (the registry) and asserts the
// message, which is the only degree of freedom a test has here.
func TestFieldMaps_EachArmCanFail(t *testing.T) {
	reg := shippedRegistry(t)

	t.Run("an unmapped, unexempted event fails", func(t *testing.T) {
		// `canon.change.recorded` has no map and IS exempt; drop its exemption
		// and the missing-map arm must fire.
		reason, had := noFieldMapAllowed["canon.change.recorded@1"]
		if !had {
			t.Fatal("fixture assumption broken: canon.change.recorded@1 is no longer exempt")
		}
		delete(noFieldMapAllowed, "canon.change.recorded@1")
		defer func() { noFieldMapAllowed["canon.change.recorded@1"] = reason }()

		err := checkFieldMaps(reg)
		if err == nil {
			t.Fatal("an event with no field map and no exemption passed the check")
		}
		if !strings.Contains(err.Error(), "canon.change.recorded@1") {
			t.Fatalf("the failure does not name the offender: %v", err)
		}
	})

	t.Run("an exemption for a mapped event fails", func(t *testing.T) {
		noFieldMapAllowed["reality.created@1"] = "bogus"
		defer delete(noFieldMapAllowed, "reality.created@1")

		err := checkFieldMaps(reg)
		if err == nil {
			t.Fatal("a stale exemption over a mapped event passed the check")
		}
		if !strings.Contains(err.Error(), "STALE") {
			t.Fatalf("the failure is not the shrink-rule message: %v", err)
		}
	})

	t.Run("an exemption for an event that left the registry fails", func(t *testing.T) {
		noFieldMapAllowed["ghost.event@1"] = "bogus"
		defer delete(noFieldMapAllowed, "ghost.event@1")

		err := checkFieldMaps(reg)
		if err == nil {
			t.Fatal("an exemption naming a nonexistent event passed the check")
		}
		if !strings.Contains(err.Error(), "no longer in the registry") {
			t.Fatalf("the failure does not say the event is gone: %v", err)
		}
	})
}

// `Run` must refuse BEFORE any emitter, so the empty files never reach disk.
// Asserting the error alone would not show that — an implementation that
// checked after emitting would return the same error over a written-out tree.
func TestFieldMaps_RunRefusesBeforeWritingAnything(t *testing.T) {
	reason := noFieldMapAllowed["canon.change.recorded@1"]
	delete(noFieldMapAllowed, "canon.change.recorded@1")
	defer func() { noFieldMapAllowed["canon.change.recorded@1"] = reason }()

	root := repoRoot(t)
	tmp := t.TempDir()
	err := Run(Config{
		RegistryPath: root + "/contracts/events/_registry.yaml",
		EventsDir:    root + "/contracts/events",
		OutDir:       tmp,
		Target:       "all",
	})
	if err == nil {
		t.Fatal("Run emitted a registry with a field-map gap")
	}
	entries, _ := os.ReadDir(tmp)
	if len(entries) > 0 {
		t.Fatalf("Run wrote %v before refusing — a reviewer would open empty structs", entries)
	}
}

// `--validate` is the mode whose job is to answer "is this registry OK to
// ship". It must not answer yes to one that generates empty contracts.
func TestFieldMaps_ValidateModeAlsoRefuses(t *testing.T) {
	reason := noFieldMapAllowed["canon.change.recorded@1"]
	delete(noFieldMapAllowed, "canon.change.recorded@1")
	defer func() { noFieldMapAllowed["canon.change.recorded@1"] = reason }()

	root := repoRoot(t)
	if err := Run(Config{
		RegistryPath: root + "/contracts/events/_registry.yaml",
		EventsDir:    root + "/contracts/events",
		OutDir:       t.TempDir(),
		Target:       "all",
		Validate:     true,
	}); err == nil {
		t.Fatal("--validate accepted a registry with a field-map gap")
	}
}

func shippedRegistry(t *testing.T) *events.Registry {
	t.Helper()
	reg, err := events.LoadRegistry(repoRoot(t) + "/contracts/events/_registry.yaml")
	if err != nil {
		t.Fatalf("load registry: %v", err)
	}
	return reg
}

func splitFieldMapKey(key string) (string, uint32, bool) {
	at := strings.LastIndex(key, "@")
	if at < 0 {
		return "", 0, false
	}
	var v uint32
	for _, r := range key[at+1:] {
		if r < '0' || r > '9' {
			return "", 0, false
		}
		v = v*10 + uint32(r-'0')
	}
	return key[:at], v, true
}

package meta

import (
	"os"
	"path/filepath"
	"testing"
)

func writeAllowlist(t *testing.T, body string) string {
	t.Helper()
	dir := t.TempDir()
	p := filepath.Join(dir, "events_allowlist.yaml")
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		t.Fatalf("write: %v", err)
	}
	return p
}

func TestLoadXRealityTopics_MapsOnlyDeclared(t *testing.T) {
	p := writeAllowlist(t, `
version: 1
entries:
  - table: pii_kek
    events:
      - op: UPDATE
        event_name: user.erased
        xreality_topic: xreality.user.erased
  - table: user_consent_ledger
    events:
      - op: INSERT
        event_name: user.consent.granted
      - op: UPDATE
        event_name: user.consent.revoked
`)
	got, err := LoadXRealityTopics(p)
	if err != nil {
		t.Fatalf("LoadXRealityTopics: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("want 1 mapped topic, got %d: %#v", len(got), got)
	}
	if got["user.erased"] != "xreality.user.erased" {
		t.Errorf("user.erased topic mismatch: %#v", got)
	}
	if _, ok := got["user.consent.revoked"]; ok {
		t.Errorf("meta-only event must not be mapped: %#v", got)
	}
}

func TestLoadXRealityTopics_ConflictIsError(t *testing.T) {
	p := writeAllowlist(t, `
version: 1
entries:
  - table: a
    events:
      - op: INSERT
        event_name: dup.event
        xreality_topic: xreality.a.one
  - table: b
    events:
      - op: INSERT
        event_name: dup.event
        xreality_topic: xreality.b.two
`)
	if _, err := LoadXRealityTopics(p); err == nil {
		t.Fatal("want conflict error for same event_name → two topics, got nil")
	}
}

func TestLoadXRealityTopics_RealAllowlistParses(t *testing.T) {
	// Guards the shipped events_allowlist.yaml: it must parse and the pii_kek
	// user.erased binding must carry the xreality.user.erased topic (071 rail).
	got, err := LoadXRealityTopics("events_allowlist.yaml")
	if err != nil {
		t.Fatalf("load shipped allowlist: %v", err)
	}
	if got["user.erased"] != "xreality.user.erased" {
		t.Errorf("shipped allowlist must map user.erased → xreality.user.erased, got %#v", got["user.erased"])
	}
}

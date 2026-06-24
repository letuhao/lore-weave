package main

import (
	"os"
	"testing"

	"github.com/loreweave/foundation/services/admin-cli/internal/framework"
)

// Guard-logic tests for buildAuditSink that do NOT open a DB pool (all the
// no-DB branches + the dev-token / allowlist refusals that return before the
// pool is opened).
func TestBuildAuditSink_Guards(t *testing.T) {
	stderr := os.Stderr

	t.Run("no DB + tier-3 informational → dev sink, ok", func(t *testing.T) {
		t.Setenv("META_DATABASE_URL", "")
		sink, cleanup, err := buildAuditSink(stderr, framework.Tier3Informational, false, false)
		if err != nil || sink == nil {
			t.Fatalf("tier-3 no-DB should yield a dev sink: sink=%v err=%v", sink, err)
		}
		cleanup()
	})

	t.Run("no DB + tier-2 destructive + real run → REFUSED (WARN-1: no confirm needed)", func(t *testing.T) {
		t.Setenv("META_DATABASE_URL", "")
		t.Setenv("ADMIN_CLI_ALLOW_UNAUDITED", "")
		// confirm=false, dryRun=false — a flagless tier-2 real run must still be refused.
		if _, _, err := buildAuditSink(stderr, framework.Tier2Griefing, false, false); err == nil {
			t.Fatal("flagless tier-2 destructive run with no DB must be refused (the tier-2 hole)")
		}
	})

	t.Run("no DB + tier-1 dry-run → allowed (dry-run is safe)", func(t *testing.T) {
		t.Setenv("META_DATABASE_URL", "")
		if _, cleanup, err := buildAuditSink(stderr, framework.Tier1Destructive, true, false); err != nil {
			t.Fatalf("dry-run must be allowed unaudited: %v", err)
		} else {
			cleanup()
		}
	})

	t.Run("no DB + tier-1 real run + ALLOW_UNAUDITED=1 → allowed", func(t *testing.T) {
		t.Setenv("META_DATABASE_URL", "")
		t.Setenv("ADMIN_CLI_ALLOW_UNAUDITED", "1")
		if _, cleanup, err := buildAuditSink(stderr, framework.Tier1Destructive, false, true); err != nil {
			t.Fatalf("explicit override should allow: %v", err)
		} else {
			cleanup()
		}
	})

	t.Run("DB set + dev tokens → REFUSED (non-UUID actor incompatible)", func(t *testing.T) {
		t.Setenv("META_DATABASE_URL", "postgres://x/y")
		t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
		if _, _, err := buildAuditSink(stderr, framework.Tier3Informational, false, false); err == nil {
			t.Fatal("dev tokens + META_DATABASE_URL must be refused")
		}
	})

	t.Run("DB set + no allowlist path → REFUSED", func(t *testing.T) {
		t.Setenv("META_DATABASE_URL", "postgres://x/y")
		t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "")
		t.Setenv("META_ALLOWLIST_PATH", "")
		if _, _, err := buildAuditSink(stderr, framework.Tier3Informational, false, false); err == nil {
			t.Fatal("META_ALLOWLIST_PATH required when DB set")
		}
	})
}

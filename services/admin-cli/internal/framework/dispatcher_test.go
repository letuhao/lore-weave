package framework

import (
	"context"
	"strings"
	"testing"

	"github.com/loreweave/foundation/services/admin-cli/internal/audit_emitter"
)

// These tests cover the F1 security hardening (PRR-05/29/43/44): typed
// confirmation, second-actor-token dual approval, and fail-closed NotWired
// handlers for destructive tiers.

const primaryTok = "dev:alice:sre:admin:destructive"

func tier1Cmd() *Command {
	return &Command{
		Domain:                 "reality",
		Name:                   "reality force-close",
		Verb:                   "force-close",
		ImpactClass:            Tier1Destructive,
		DryRunRequired:         true,
		DoubleApprovalRequired: true,
	}
}

func okHandler(_ context.Context, _ Invocation) (string, error) { return "ok", nil }

func newTestEmitter() *audit_emitter.Emitter {
	return audit_emitter.New(audit_emitter.NewMemorySink(), nil)
}

// baseTier1Inv returns a fully-valid tier-1 confirm invocation (challenge r-1).
func baseTier1Inv() Invocation {
	return Invocation{
		Params:           map[string]string{"reality_id": "r-1"},
		Confirm:          true,
		Reason:           "valid reason >=10 chars",
		SecondActor:      "bob",
		SecondActorToken: "dev:bob:sre:admin:destructive",
		ConfirmToken:     "r-1",
	}
}

func TestRun_Tier1_HappyPath(t *testing.T) {
	t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
	out, err := Run(context.Background(), tier1Cmd(), baseTier1Inv(), primaryTok, okHandler, newTestEmitter())
	if err != nil {
		t.Fatalf("happy path: %v", err)
	}
	if out != "ok" {
		t.Fatalf("want ok, got %q", out)
	}
}

func TestRun_Tier1_MissingConfirmToken(t *testing.T) {
	t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
	inv := baseTier1Inv()
	inv.ConfirmToken = "" // PRR-44
	_, err := Run(context.Background(), tier1Cmd(), inv, primaryTok, okHandler, newTestEmitter())
	if err == nil || !strings.Contains(err.Error(), "typed-confirmation") {
		t.Fatalf("want typed-confirmation error, got %v", err)
	}
}

func TestRun_Tier1_WrongConfirmToken(t *testing.T) {
	t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
	inv := baseTier1Inv()
	inv.ConfirmToken = "r-WRONG"
	if _, err := Run(context.Background(), tier1Cmd(), inv, primaryTok, okHandler, newTestEmitter()); err == nil {
		t.Fatal("want error on wrong confirm token")
	}
}

func TestRun_Tier1_MissingSecondActorToken(t *testing.T) {
	t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
	inv := baseTier1Inv()
	inv.SecondActorToken = "" // PRR-43: a name alone is not enough
	_, err := Run(context.Background(), tier1Cmd(), inv, primaryTok, okHandler, newTestEmitter())
	if err == nil || !strings.Contains(err.Error(), "second-actor-token") {
		t.Fatalf("want second-actor-token error, got %v", err)
	}
}

func TestRun_Tier1_SecondActorTokenSubjectMismatch(t *testing.T) {
	t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
	inv := baseTier1Inv()
	inv.SecondActorToken = "dev:carol:sre:admin:destructive" // subject carol != SecondActor bob
	_, err := Run(context.Background(), tier1Cmd(), inv, primaryTok, okHandler, newTestEmitter())
	if err == nil || !strings.Contains(err.Error(), "does not match") {
		t.Fatalf("want subject mismatch error, got %v", err)
	}
}

func TestRun_Tier1_SecondActorLacksScope(t *testing.T) {
	t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
	inv := baseTier1Inv()
	inv.SecondActorToken = "dev:bob:sre:admin:read" // lacks admin:destructive
	_, err := Run(context.Background(), tier1Cmd(), inv, primaryTok, okHandler, newTestEmitter())
	if err == nil || !strings.Contains(err.Error(), "lacks required scope") {
		t.Fatalf("want scope error, got %v", err)
	}
}

func TestNotWiredHandler_Tier1FailsClosed(t *testing.T) {
	h := NotWiredHandler("reality force-close", string(Tier1Destructive))
	if _, err := h(context.Background(), Invocation{}); err == nil {
		t.Fatal("PRR-05: tier-1 NotWired must return an error, not success")
	}
}

func TestNotWiredHandler_Tier2FailsClosed(t *testing.T) {
	h := NotWiredHandler("npc force-despawn", string(Tier2Griefing))
	if _, err := h(context.Background(), Invocation{}); err == nil {
		t.Fatal("PRR-05: tier-2 NotWired must return an error")
	}
}

func TestNotWiredHandler_Tier3Succeeds(t *testing.T) {
	h := NotWiredHandler("reality list", string(Tier3Informational))
	out, err := h(context.Background(), Invocation{})
	if err != nil || out == "" {
		t.Fatalf("tier-3 NotWired should return message,nil; got out=%q err=%v", out, err)
	}
}

func TestResolve_UnwiredTier1Errors(t *testing.T) {
	reg := NewHandlerRegistry()
	h := reg.Resolve(tier1Cmd())
	if _, err := h(context.Background(), Invocation{}); err == nil {
		t.Fatal("PRR-05: Resolve of unwired tier-1 must fail closed")
	}
}

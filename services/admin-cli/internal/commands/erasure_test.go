package commands

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

// fakeEraser records ErasePII calls; failIfCalled makes any call fail the test
// (used to prove the dry-run path never shreds).
type fakeEraser struct {
	t            *testing.T
	failIfCalled bool
	err          error
	calls        int
	order        *[]string
}

func (f *fakeEraser) ErasePII(_ context.Context, _ uuid.UUID, ticket, reason string) error {
	if f.failIfCalled {
		f.t.Fatalf("ErasePII must NOT be called in this path (dry-run zero-write invariant)")
	}
	if ticket == "" || reason == "" {
		f.t.Fatalf("ErasePII called without ticket/reason")
	}
	f.calls++
	if f.order != nil {
		*f.order = append(*f.order, "erase")
	}
	return f.err
}

type fakeConsent struct {
	t            *testing.T
	failIfRevoke bool
	active       []ConsentScope
	revokeErr    error
	alreadySet   map[string]bool // scope/version → return alreadyRevoked=true
	revoked      int
	order        *[]string
}

func (f *fakeConsent) ActiveScopes(_ context.Context, _ uuid.UUID) ([]ConsentScope, error) {
	return f.active, nil
}

func (f *fakeConsent) RevokeScope(_ context.Context, _ uuid.UUID, sc ConsentScope, reason string) (bool, error) {
	if f.failIfRevoke {
		f.t.Fatalf("RevokeScope must NOT be called in this path (dry-run zero-write invariant)")
	}
	if reason == "" {
		f.t.Fatalf("RevokeScope called without reason")
	}
	if f.revokeErr != nil {
		return false, f.revokeErr
	}
	if f.alreadySet[sc.Scope+"/"+sc.Version] {
		return true, nil
	}
	f.revoked++
	if f.order != nil {
		*f.order = append(*f.order, "revoke:"+sc.Scope)
	}
	return false, nil
}

type fakeBalance struct {
	rows int
	net  int64
}

func (f fakeBalance) CostLedgerSummary(_ context.Context, _ uuid.UUID) (int, int64, error) {
	return f.rows, f.net, nil
}

func baseReq(dryRun bool) ErasureRequest {
	return ErasureRequest{
		UserRefID:  uuid.New(),
		TicketID:   "TCK-123",
		Reason:     "user self-service deletion request per GDPR Art.17",
		LegalBasis: "self_request",
		DryRun:     dryRun,
	}
}

func TestRunUserErasure_DryRun_NoWrites(t *testing.T) {
	eraser := &fakeEraser{t: t, failIfCalled: true}
	consent := &fakeConsent{t: t, failIfRevoke: true, active: []ConsentScope{{"core_service", "v1"}, {"marketing_comms", "v2"}}}
	deps := ErasureDeps{Eraser: eraser, Consent: consent, Balance: fakeBalance{rows: 3, net: 0}, Clock: time.Now}

	out, err := RunUserErasure(context.Background(), baseReq(true), deps)
	if err != nil {
		t.Fatalf("dry-run err: %v", err)
	}
	if !strings.Contains(out, "DRY-RUN") || !strings.Contains(out, "WOULD-RUN") {
		t.Fatalf("dry-run report missing markers:\n%s", out)
	}
	if !strings.Contains(out, "would revoke 2 active scope(s)") {
		t.Fatalf("dry-run should preview 2 scopes:\n%s", out)
	}
	if eraser.calls != 0 || consent.revoked != 0 {
		t.Fatalf("dry-run wrote: erase=%d revoke=%d", eraser.calls, consent.revoked)
	}
}

func TestRunUserErasure_Confirm_RevokeBeforeShred(t *testing.T) {
	order := []string{}
	eraser := &fakeEraser{t: t, order: &order}
	consent := &fakeConsent{t: t, active: []ConsentScope{{"core_service", "v1"}, {"byok_telemetry", "v1"}}, order: &order}
	deps := ErasureDeps{Eraser: eraser, Consent: consent, Balance: fakeBalance{rows: 0, net: 0}, Clock: time.Now}

	out, err := RunUserErasure(context.Background(), baseReq(false), deps)
	if err != nil {
		t.Fatalf("confirm err: %v", err)
	}
	if eraser.calls != 1 {
		t.Fatalf("expected 1 ErasePII call, got %d", eraser.calls)
	}
	if consent.revoked != 2 {
		t.Fatalf("expected 2 revokes, got %d", consent.revoked)
	}
	// BLOCK#2 fail-safe order: every revoke precedes the (irreversible) shred.
	eraseIdx := -1
	for i, ev := range order {
		if ev == "erase" {
			eraseIdx = i
		}
	}
	if eraseIdx != len(order)-1 {
		t.Fatalf("crypto-shred must be LAST; order=%v", order)
	}
	if !strings.Contains(out, "CONFIRM") || !strings.Contains(out, "DEFERRED→071") {
		t.Fatalf("confirm report missing markers:\n%s", out)
	}
}

func TestRunUserErasure_InvalidLegalBasis(t *testing.T) {
	eraser := &fakeEraser{t: t, failIfCalled: true}
	consent := &fakeConsent{t: t, failIfRevoke: true}
	req := baseReq(false)
	req.LegalBasis = "because_i_said_so"
	_, err := RunUserErasure(context.Background(), req, ErasureDeps{Eraser: eraser, Consent: consent})
	if !errors.Is(err, ErrErasureIncomplete) {
		t.Fatalf("expected ErrErasureIncomplete, got %v", err)
	}
}

func TestRunUserErasure_ConsentFailsBeforeShred(t *testing.T) {
	// A revoke failure must abort BEFORE the irreversible crypto-shred.
	eraser := &fakeEraser{t: t, failIfCalled: true} // must not be reached
	consent := &fakeConsent{t: t, active: []ConsentScope{{"core_service", "v1"}}, revokeErr: errors.New("db down")}
	_, err := RunUserErasure(context.Background(), baseReq(false), ErasureDeps{Eraser: eraser, Consent: consent})
	if !errors.Is(err, ErrErasureIncomplete) {
		t.Fatalf("expected ErrErasureIncomplete, got %v", err)
	}
}

func TestRunUserErasure_IdempotentReRun(t *testing.T) {
	// Re-run: all scopes already revoked → skipped, but the shred still runs.
	eraser := &fakeEraser{t: t}
	consent := &fakeConsent{
		t:          t,
		active:     []ConsentScope{{"core_service", "v1"}},
		alreadySet: map[string]bool{"core_service/v1": true},
	}
	out, err := RunUserErasure(context.Background(), baseReq(false), ErasureDeps{Eraser: eraser, Consent: consent})
	if err != nil {
		t.Fatalf("re-run err: %v", err)
	}
	if eraser.calls != 1 {
		t.Fatalf("shred must still run on re-run, got %d calls", eraser.calls)
	}
	if !strings.Contains(out, "idempotent-skipped 1") {
		t.Fatalf("report should note the skip:\n%s", out)
	}
}

func TestRunUserErasure_MissingTicketOrReason(t *testing.T) {
	eraser := &fakeEraser{t: t, failIfCalled: true}
	consent := &fakeConsent{t: t, failIfRevoke: true}
	req := baseReq(false)
	req.TicketID = ""
	if _, err := RunUserErasure(context.Background(), req, ErasureDeps{Eraser: eraser, Consent: consent}); !errors.Is(err, ErrErasureIncomplete) {
		t.Fatalf("missing ticket must fail: %v", err)
	}
}

type fakeExistence struct {
	exists bool
	err    error
}

func (f fakeExistence) UserExists(_ context.Context, _ uuid.UUID) (bool, error) {
	return f.exists, f.err
}

func TestRunUserErasure_NonExistentUser_Refused(t *testing.T) {
	// BLOCK fix: a non-existent user_ref_id must be refused BEFORE the shred,
	// not silently no-op'd through every step.
	eraser := &fakeEraser{t: t, failIfCalled: true}
	consent := &fakeConsent{t: t, failIfRevoke: true}
	deps := ErasureDeps{Eraser: eraser, Consent: consent, Existence: fakeExistence{exists: false}}
	if _, err := RunUserErasure(context.Background(), baseReq(false), deps); !errors.Is(err, ErrErasureIncomplete) {
		t.Fatalf("non-existent user must be refused: %v", err)
	}
	if eraser.calls != 0 {
		t.Fatalf("shred must NOT run for a non-existent user; got %d calls", eraser.calls)
	}
}

func TestRunUserErasure_ExistenceProbeError(t *testing.T) {
	eraser := &fakeEraser{t: t, failIfCalled: true}
	consent := &fakeConsent{t: t, failIfRevoke: true}
	deps := ErasureDeps{Eraser: eraser, Consent: consent, Existence: fakeExistence{err: errors.New("db down")}}
	if _, err := RunUserErasure(context.Background(), baseReq(false), deps); !errors.Is(err, ErrErasureIncomplete) {
		t.Fatalf("existence probe error must abort: %v", err)
	}
}

func TestRunUserErasure_PartialRevokeFailure_ReportsPartial(t *testing.T) {
	// WARN1: a mid-loop revoke failure must surface the partial state in the
	// report AND abort before the shred.
	eraser := &fakeEraser{t: t, failIfCalled: true}
	consent := &fakeConsent{
		t:         t,
		active:    []ConsentScope{{"core_service", "v1"}, {"byok_telemetry", "v1"}},
		revokeErr: errors.New("db down"),
	}
	out, err := RunUserErasure(context.Background(), baseReq(false), ErasureDeps{Eraser: eraser, Consent: consent, Existence: fakeExistence{exists: true}})
	if !errors.Is(err, ErrErasureIncomplete) {
		t.Fatalf("expected ErrErasureIncomplete, got %v", err)
	}
	if !strings.Contains(out, "FAILED") || !strings.Contains(out, "re-run to complete") {
		t.Fatalf("partial-failure report must surface the aborted state:\n%s", out)
	}
}

func TestRunUserErasure_DeferredStepsReported(t *testing.T) {
	eraser := &fakeEraser{t: t}
	consent := &fakeConsent{t: t}
	out, err := RunUserErasure(context.Background(), baseReq(false), ErasureDeps{Eraser: eraser, Consent: consent})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	for _, want := range []string{"per-reality-pc-tombstone", "emit-user.erased", "cost-ledger-pseudonymize", "confirmation-email", "erasure-certificate-30d"} {
		if !strings.Contains(out, want) {
			t.Fatalf("report missing deferred/stub step %q:\n%s", want, out)
		}
	}
}

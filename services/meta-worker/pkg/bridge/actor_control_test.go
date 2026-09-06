package bridge

// Handler tests for `actor_control_binding`'s writer.
//
// Every case here is a STATUS CODE the caller depends on to tell apart four
// outcomes that all look like "the write did not create a row": already granted
// (fine), someone else drives it (not fine), already revoked (fine), and the
// user you meant no longer holds it (not fine). Collapsing any pair of those
// into one code is how a confused deputy gets built on top of a table written
// to prevent one.

import (
	"encoding/json"
	"net/http"
	"testing"
)

const (
	userA   = "11111111-1111-4111-8111-111111111111"
	userB   = "44444444-4444-4444-8444-444444444444"
	reality = "22222222-2222-4222-8222-222222222222"
	actorX  = "33333333-3333-4333-8333-333333333333"
)

const grantPath = "/internal/provisioner/grant-actor-control"
const revokePath = "/internal/provisioner/revoke-actor-control"

func grantBody(user string) string {
	return `{"user_ref_id":"` + user + `","reality_id":"` + reality + `","actor_id":"` + actorX + `","reason":"test"}`
}

func statusOf(t *testing.T, body []byte) string {
	t.Helper()
	var m map[string]string
	if err := json.Unmarshal(body, &m); err != nil {
		t.Fatalf("body not json: %v (%s)", err, body)
	}
	if s, ok := m["status"]; ok {
		return s
	}
	return "error:" + m["error"]
}

func TestGrantControlCreated(t *testing.T) {
	f := &fakeReg{}
	rec := do(srv(t, f, &fakeAudit{}), tok, grantPath, grantBody(userA))
	if rec.Code != http.StatusCreated {
		t.Fatalf("got %d, want 201: %s", rec.Code, rec.Body)
	}
	if got := statusOf(t, rec.Body.Bytes()); got != "granted" {
		t.Fatalf("status = %q, want granted", got)
	}
	if f.grantCalls != 1 || f.lastGrantReq.UserRefID != userA {
		t.Fatalf("registrar not called with the request: %d %+v", f.grantCalls, f.lastGrantReq)
	}
}

// A RETRY is success. Same principal, same intent — the `register-reality`
// precedent.
func TestGrantControlSameUserIsIdempotent(t *testing.T) {
	f := &fakeReg{grantErr: ErrAlreadyGranted}
	rec := do(srv(t, f, &fakeAudit{}), tok, grantPath, grantBody(userA))
	if rec.Code != http.StatusOK {
		t.Fatalf("got %d, want 200: %s", rec.Code, rec.Body)
	}
	if got := statusOf(t, rec.Body.Bytes()); got != "already_granted" {
		t.Fatalf("status = %q", got)
	}
}

// A DIFFERENT principal is NOT a retry, and must never be reported as one.
// This is the confused-deputy refusal; 200 here would hide it from the caller.
func TestGrantControlOtherUserConflicts(t *testing.T) {
	f := &fakeReg{grantErr: ErrActorAlreadyDriven}
	rec := do(srv(t, f, &fakeAudit{}), tok, grantPath, grantBody(userB))
	if rec.Code != http.StatusConflict {
		t.Fatalf("got %d, want 409: %s", rec.Code, rec.Body)
	}
}

func TestGrantControlRequiresAllThreeIDs(t *testing.T) {
	for name, body := range map[string]string{
		"no user":    `{"reality_id":"` + reality + `","actor_id":"` + actorX + `"}`,
		"no reality": `{"user_ref_id":"` + userA + `","actor_id":"` + actorX + `"}`,
		"no actor":   `{"user_ref_id":"` + userA + `","reality_id":"` + reality + `"}`,
	} {
		f := &fakeReg{}
		rec := do(srv(t, f, &fakeAudit{}), tok, grantPath, body)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("%s: got %d, want 400", name, rec.Code)
		}
		if f.grantCalls != 0 {
			t.Fatalf("%s: registrar was called with an incomplete binding", name)
		}
	}
}

func TestRevokeControlOK(t *testing.T) {
	f := &fakeReg{}
	rec := do(srv(t, f, &fakeAudit{}), tok, revokePath,
		`{"reality_id":"`+reality+`","actor_id":"`+actorX+`","reason":"test"}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("got %d, want 200: %s", rec.Code, rec.Body)
	}
	if got := statusOf(t, rec.Body.Bytes()); got != "revoked" {
		t.Fatalf("status = %q, want revoked", got)
	}
}

// Idempotent by END STATE: the caller asked for "this actor has no driver", and
// that is true. The body distinguishes it from a revoke that did something.
func TestRevokeControlNoLiveBindingIsOK(t *testing.T) {
	f := &fakeReg{revokeErr: ErrNoLiveBinding}
	rec := do(srv(t, f, &fakeAudit{}), tok, revokePath,
		`{"reality_id":"`+reality+`","actor_id":"`+actorX+`"}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("got %d, want 200: %s", rec.Code, rec.Body)
	}
	if got := statusOf(t, rec.Body.Bytes()); got != "already_revoked" {
		t.Fatalf("status = %q, want already_revoked", got)
	}
}

// The CAS. A caller working from a stale read must SURFACE — otherwise
// "revoke the driver of actor X" silently removes whoever took over.
func TestRevokeControlCASMismatchConflicts(t *testing.T) {
	f := &fakeReg{revokeErr: ErrControlCASMismatch}
	rec := do(srv(t, f, &fakeAudit{}), tok, revokePath,
		`{"reality_id":"`+reality+`","actor_id":"`+actorX+`","expected_user_ref_id":"`+userA+`"}`)
	if rec.Code != http.StatusConflict {
		t.Fatalf("got %d, want 409: %s", rec.Code, rec.Body)
	}
}

// The CAS is OPTIONAL, and its absence must reach the registrar as absence —
// not as an empty string the registrar might parse as a uuid.
func TestRevokeControlPassesTheCASThrough(t *testing.T) {
	f := &fakeReg{}
	h := srv(t, f, &fakeAudit{})

	do(h, tok, revokePath, `{"reality_id":"`+reality+`","actor_id":"`+actorX+`"}`)
	if f.lastRevokeReq.ExpectedUserRefID != "" {
		t.Fatalf("absent CAS became %q", f.lastRevokeReq.ExpectedUserRefID)
	}
	do(h, tok, revokePath,
		`{"reality_id":"`+reality+`","actor_id":"`+actorX+`","expected_user_ref_id":"`+userA+`"}`)
	if f.lastRevokeReq.ExpectedUserRefID != userA {
		t.Fatalf("CAS did not reach the registrar: %q", f.lastRevokeReq.ExpectedUserRefID)
	}
}

// Both new routes are behind the same fail-closed token as the other three.
// Without this the scoped surface would have grown two unauthenticated holes.
func TestActorControlRoutesRequireTheToken(t *testing.T) {
	for _, path := range []string{grantPath, revokePath} {
		f := &fakeReg{}
		rec := do(srv(t, f, &fakeAudit{}), "wrong-token", path, grantBody(userA))
		if rec.Code != http.StatusUnauthorized {
			t.Fatalf("%s: got %d, want 401", path, rec.Code)
		}
		if f.grantCalls != 0 || f.revokeCalls != 0 {
			t.Fatalf("%s: an unauthenticated call reached the registrar", path)
		}
	}
}

// Every bridge call writes one service_to_service_audit row, including these.
func TestActorControlIsAudited(t *testing.T) {
	a := &fakeAudit{}
	do(srv(t, &fakeReg{}, a), tok, grantPath, grantBody(userA))
	last := a.last()
	if last.RPC != "grant-actor-control" || last.Result != "ok" {
		t.Fatalf("audit row = %+v", last)
	}
}

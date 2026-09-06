// actor_control_read_test.go — `RA1`, the audited cross-user read as a route.
//
// `D-PC-NO-RUST-READ-AUDIT`: `liveBinding` has been the only audited cross-user
// read of `actor_control_binding` since migration `034`, and it was PRIVATE —
// reachable only from inside the grant/revoke CAS. A caller in another service
// had two options: write a bare `SELECT` that
// `meta-sensitive-read-bypass-lint` correctly refuses, or go without. The
// discipline had no reachable path, so the first caller to need one would have
// bypassed it by default rather than by choice.
package bridge

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"strings"
	"testing"

	"github.com/google/uuid"
)

const readPath = "/internal/provisioner/read-actor-control"

func readBody(reality, actor string) string {
	return `{"reality_id":"` + reality + `","actor_id":"` + actor + `"}`
}

func decodeRead(t *testing.T, raw []byte) map[string]any {
	t.Helper()
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		t.Fatalf("reply is not JSON: %v (%s)", err, raw)
	}
	return m
}

// A driven actor names its driver.
func TestReadControlReportsTheDriver(t *testing.T) {
	bid, uid := uuid.New(), uuid.MustParse(userA)
	f := &fakeReg{readBinding: &LiveBinding{BindingID: bid, UserRefID: uid}}
	rec := do(srv(t, f, &fakeAudit{}), tok, readPath, readBody(reality, actorX))
	if rec.Code != http.StatusOK {
		t.Fatalf("got %d, want 200: %s", rec.Code, rec.Body)
	}
	m := decodeRead(t, rec.Body.Bytes())
	if m["driven"] != true {
		t.Fatalf("driven = %v, want true: %s", m["driven"], rec.Body)
	}
	if m["user_ref_id"] != userA {
		t.Fatalf("user_ref_id = %v, want %s", m["user_ref_id"], userA)
	}
	if m["binding_id"] != bid.String() {
		t.Fatalf("binding_id = %v, want %s", m["binding_id"], bid)
	}
	if f.readCalls != 1 || f.lastReadReq.ActorID != actorX {
		t.Fatalf("registrar not called with the request: %d %+v", f.readCalls, f.lastReadReq)
	}
}

// "Nobody drives it" is a 200 with `driven:false`, NOT a 404.
//
// A 404 would push a normal outcome onto the caller's error path, and the first
// thing anyone writes against a 404 is a retry. The undriven actor is the case
// a grant preview most wants to hear about, so it must be the easy answer to
// consume, not the exceptional one.
func TestReadControlUndrivenIsAnAnswerNotAMiss(t *testing.T) {
	f := &fakeReg{readBinding: nil}
	rec := do(srv(t, f, &fakeAudit{}), tok, readPath, readBody(reality, actorX))
	if rec.Code != http.StatusOK {
		t.Fatalf("an undriven actor must be 200, got %d: %s", rec.Code, rec.Body)
	}
	m := decodeRead(t, rec.Body.Bytes())
	if m["driven"] != false {
		t.Fatalf("driven = %v, want false", m["driven"])
	}
	// And it must not invent a holder.
	if _, ok := m["user_ref_id"]; ok {
		t.Fatalf("an undriven actor must name no user: %s", rec.Body)
	}
}

// The token is the boundary. Without it the read must not happen at all —
// `who drives this actor` is exactly the question an unauthenticated caller
// must not get to ask.
func TestReadControlRequiresTheToken(t *testing.T) {
	f := &fakeReg{}
	rec := do(srv(t, f, &fakeAudit{}), "wrong-token", readPath, readBody(reality, actorX))
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("got %d, want 401: %s", rec.Code, rec.Body)
	}
	if f.readCalls != 0 {
		t.Fatalf("the read ran despite a bad token (%d call(s)) — the audit row would name "+
			"a caller that was never authorised", f.readCalls)
	}
}

// Malformed input is refused before the registrar is reached.
//
// Asserted per-case rather than as "some 400 happened": a handler that refused
// everything would pass a looser test, and this route's whole job is to reach
// the registrar when the input is good.
func TestReadControlRefusesMalformedInput(t *testing.T) {
	cases := []struct{ name, body string }{
		{"not json", `{`},
		{"no reality", `{"actor_id":"` + actorX + `"}`},
		{"no actor", `{"reality_id":"` + reality + `"}`},
		{"reality is not a uuid", `{"reality_id":"nope","actor_id":"` + actorX + `"}`},
		{"actor is not a uuid", `{"reality_id":"` + reality + `","actor_id":"nope"}`},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			f := &fakeReg{}
			rec := do(srv(t, f, &fakeAudit{}), tok, readPath, c.body)
			if rec.Code != http.StatusBadRequest {
				t.Fatalf("got %d, want 400: %s", rec.Code, rec.Body)
			}
			if f.readCalls != 0 {
				t.Fatalf("the registrar was reached with malformed input")
			}
		})
	}
	// Non-vacuity: a well-formed request DOES reach the registrar, or every
	// case above is satisfied by a handler that refuses unconditionally.
	f := &fakeReg{}
	if rec := do(srv(t, f, &fakeAudit{}), tok, readPath, readBody(reality, actorX)); rec.Code != http.StatusOK {
		t.Fatalf("a well-formed read must reach the registrar, got %d: %s", rec.Code, rec.Body)
	}
	if f.readCalls != 1 {
		t.Fatalf("the registrar was not reached by a valid request")
	}
}

// A registrar failure is ours, not the caller's.
func TestReadControlSurfacesARegistrarFailure(t *testing.T) {
	f := &fakeReg{readErr: errors.New("the pool is gone")}
	rec := do(srv(t, f, &fakeAudit{}), tok, readPath, readBody(reality, actorX))
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("got %d, want 500: %s", rec.Code, rec.Body)
	}
}

// THE ROUTE IS SERVED AT ALL.
//
// The handler tests above drive `s.Handler()`, so a route that was written and
// never registered would fail them — but it would fail them as a 404 decoded
// into an empty map, which reads like a body-shape problem. This says the thing
// directly, because "the mux forgot it" and "the JSON changed" are two very
// different mornings.
func TestReadControlIsRouted(t *testing.T) {
	rec := do(srv(t, &fakeReg{}, &fakeAudit{}), tok, readPath, readBody(reality, actorX))
	if rec.Code == http.StatusNotFound {
		t.Fatalf("%s is not registered on the mux", readPath)
	}
}

// THE AUDIT HAS EXACTLY ONE HOME, and this is the arm that keeps it there.
//
// The route tests above drive a FAKE registrar, so none of them touches
// `liveBinding` — which is where the `meta_read_audit` row is written. That is
// the correct shape for handler tests and it means the central claim of `RA1`
// ("the audit cannot be skipped by using this door, because there is no second
// implementation to skip it with") is not covered by any of them.
//
// It cannot be covered by a unit test either: proving the row lands needs a
// real pool. So this asserts the STRUCTURAL property that makes the claim true
// — `ReadActorControl` delegates and owns no query of its own. A future edit
// that inlines a `SELECT` here to "save a call" would keep every test above
// green while silently dropping the audit, and that is the whole failure class
// `D-PC-NO-RUST-READ-AUDIT` describes.
//
// Weaker than a live test, and said so rather than dressed up. The live proof
// is the row landing in `meta_read_audit` on a real stack.
//
// ⚠️ AND IT IS THE ONLY MECHANISM, not a second one. The obvious other guard —
// `meta-sensitive-read-bypass-lint` — cannot see this: it excludes
// `services/meta-worker/pkg/bridge/actor_control.go` WHOLESALE, because
// `liveBinding`'s own SELECT is the sanctioned audited read. That exclusion was
// granted for ONE function and silently covers every function in the file,
// including ones written afterwards. Measured by biting the mutant below past
// the lint: it passes. So the escape hatch does not reach its own reason, which
// is why this arm is load-bearing rather than belt-and-braces.
func TestTheAuditedReadHasOneImplementation(t *testing.T) {
	src, err := os.ReadFile("actor_control.go")
	if err != nil {
		t.Fatalf("read actor_control.go: %v", err)
	}
	body, ok := funcBody(string(src), "func (m MetaRegistrar) ReadActorControl(")
	if !ok {
		t.Fatal("ReadActorControl not found — this guard is reading the wrong file, and a " +
			"guard that cannot find its subject reports a pass it did not earn")
	}
	if !strings.Contains(body, "m.liveBinding(") {
		t.Error("ReadActorControl no longer delegates to liveBinding — the meta_read_audit " +
			"write lives there, and a second path to this data is a second path with no audit")
	}
	if strings.Contains(strings.ToUpper(body), "SELECT") {
		t.Error("ReadActorControl grew a query of its own. The audited read has one home; " +
			"a SELECT here bypasses RecordBindingRead and every test in this file stays green")
	}
}

// funcBody returns the text between the opening `{` of the named function and
// its matching `}`. Brace-counting rather than a regex, because a regex that
// stops at the first `}` reads a nested block as the whole body and would
// happily miss a SELECT two lines later.
func funcBody(src, header string) (string, bool) {
	i := strings.Index(src, header)
	if i < 0 {
		return "", false
	}
	rest := src[i:]
	open := strings.Index(rest, "{")
	if open < 0 {
		return "", false
	}
	depth := 0
	for j := open; j < len(rest); j++ {
		switch rest[j] {
		case '{':
			depth++
		case '}':
			depth--
			if depth == 0 {
				return rest[open : j+1], true
			}
		}
	}
	return "", false
}

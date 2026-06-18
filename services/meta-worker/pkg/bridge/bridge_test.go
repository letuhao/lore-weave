package bridge

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"github.com/loreweave/foundation/contracts/meta"
)

type fakeReg struct {
	registerErr error
	transErr    error
	newState    string
	registers   int
}

func (f *fakeReg) Register(context.Context, RegisterReq) error { f.registers++; return f.registerErr }
func (f *fakeReg) Transition(context.Context, TransitionReq) (string, error) {
	return f.newState, f.transErr
}

type fakeAudit struct {
	mu sync.Mutex
	ev []AuditEvent
}

func (a *fakeAudit) Record(_ context.Context, e AuditEvent) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.ev = append(a.ev, e)
	return nil
}
func (a *fakeAudit) last() AuditEvent {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.ev[len(a.ev)-1]
}

const tok = "s3cr3t-token"

func srv(t *testing.T, reg Registrar, audit AuditSink) http.Handler {
	t.Helper()
	s, err := New(reg, audit, tok, "world-service")
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return s.Handler()
}

func do(h http.Handler, token, path, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewBufferString(body))
	if token != "" {
		req.Header.Set("X-Service-Token", token)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestNewRefusesEmptyToken(t *testing.T) {
	if _, err := New(&fakeReg{}, &fakeAudit{}, "", "world-service"); err == nil {
		t.Fatal("expected fail-closed: empty token must be refused")
	}
}

func TestMissingTokenIsDeniedAndAudited(t *testing.T) {
	audit := &fakeAudit{}
	h := srv(t, &fakeReg{}, audit)
	rec := do(h, "", "/internal/provisioner/register-reality", `{}`)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", rec.Code)
	}
	if got := audit.last().Result; got != "deny" {
		t.Fatalf("want audit result=deny, got %q", got)
	}
}

func TestWrongTokenIsDenied(t *testing.T) {
	h := srv(t, &fakeReg{}, &fakeAudit{})
	rec := do(h, "nope", "/internal/provisioner/register-reality", `{}`)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", rec.Code)
	}
}

func TestRegisterOK(t *testing.T) {
	audit := &fakeAudit{}
	h := srv(t, &fakeReg{}, audit)
	body := `{"reality_id":"11111111-1111-1111-1111-111111111111","db_host":"pg-shard-0.internal","db_name":"lw_r","locale":"en"}`
	rec := do(h, tok, "/internal/provisioner/register-reality", body)
	if rec.Code != http.StatusCreated {
		t.Fatalf("want 201, got %d (%s)", rec.Code, rec.Body)
	}
	if audit.last().Result != "ok" {
		t.Fatalf("want audit ok, got %q", audit.last().Result)
	}
}

func TestRegisterIdempotentOnConflict(t *testing.T) {
	h := srv(t, &fakeReg{registerErr: ErrAlreadyRegistered}, &fakeAudit{})
	body := `{"reality_id":"11111111-1111-1111-1111-111111111111","db_host":"h","db_name":"d","locale":"en"}`
	rec := do(h, tok, "/internal/provisioner/register-reality", body)
	if rec.Code != http.StatusOK {
		t.Fatalf("idempotent register must be 200, got %d", rec.Code)
	}
}

func TestRegisterMissingFields(t *testing.T) {
	h := srv(t, &fakeReg{}, &fakeAudit{})
	rec := do(h, tok, "/internal/provisioner/register-reality", `{"reality_id":"x"}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("want 400, got %d", rec.Code)
	}
}

func TestTransitionStaleIsConflict(t *testing.T) {
	h := srv(t, &fakeReg{transErr: meta.ErrConcurrentStateTransition}, &fakeAudit{})
	body := `{"reality_id":"r","from":"active","to":"migrating"}`
	rec := do(h, tok, "/internal/provisioner/transition", body)
	if rec.Code != http.StatusConflict {
		t.Fatalf("stale CAS must be 409, got %d", rec.Code)
	}
}

func TestTransitionInvalidIsBadRequest(t *testing.T) {
	h := srv(t, &fakeReg{transErr: meta.ErrInvalidTransition}, &fakeAudit{})
	body := `{"reality_id":"r","from":"active","to":"dropped"}`
	rec := do(h, tok, "/internal/provisioner/transition", body)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("invalid transition must be 400, got %d", rec.Code)
	}
}

func TestTransitionOK(t *testing.T) {
	h := srv(t, &fakeReg{newState: "migrating"}, &fakeAudit{})
	body := `{"reality_id":"r","from":"active","to":"migrating"}`
	rec := do(h, tok, "/internal/provisioner/transition", body)
	if rec.Code != http.StatusOK {
		t.Fatalf("want 200, got %d (%s)", rec.Code, rec.Body)
	}
}

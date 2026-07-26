package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/notification-service/internal/push"
)

// These cover the validation + VAPID-key paths that DON'T touch the pool (the reject-before-DB and
// the public-key handler), so they run without a database.

const pushTestSecret = "12345678901234567890123456789012"

func pushBearer(t *testing.T) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   uuid.New().String(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(5 * time.Minute)),
	})
	s, err := tok.SignedString([]byte(pushTestSecret))
	if err != nil {
		t.Fatal(err)
	}
	return "Bearer " + s
}

func newPushServer(vapid push.VAPIDConfig) *Server {
	return &Server{secret: []byte(pushTestSecret), vapid: vapid}
}

func TestRegisterPushSubscription_RejectsBeforeDB(t *testing.T) {
	srv := newPushServer(push.VAPIDConfig{})

	// No bearer → 401 (never reaches the DB).
	r := httptest.NewRequest(http.MethodPost, "/", strings.NewReader(`{}`))
	w := httptest.NewRecorder()
	srv.registerPushSubscription(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no bearer: got %d want 401", w.Code)
	}

	// Missing endpoint/keys → 400 (validation before the upsert).
	r = httptest.NewRequest(http.MethodPost, "/", strings.NewReader(`{"endpoint":"","keys":{}}`))
	r.Header.Set("Authorization", pushBearer(t))
	w = httptest.NewRecorder()
	srv.registerPushSubscription(w, r)
	if w.Code != http.StatusBadRequest {
		t.Errorf("empty endpoint: got %d want 400", w.Code)
	}
}

func TestSetPushPreference_ValidatesTopicEnum(t *testing.T) {
	srv := newPushServer(push.VAPIDConfig{})

	// Unknown topic → 400 (closed-set enum validation before the DB).
	r := httptest.NewRequest(http.MethodPut, "/", strings.NewReader(`{"push_topic":"bogus","push_enabled":true}`))
	r.Header.Set("Authorization", pushBearer(t))
	w := httptest.NewRecorder()
	srv.setPushPreference(w, r)
	if w.Code != http.StatusBadRequest {
		t.Errorf("unknown topic: got %d want 400", w.Code)
	}

	// Missing push_enabled → 400.
	r = httptest.NewRequest(http.MethodPut, "/", strings.NewReader(`{"push_topic":"jobs"}`))
	r.Header.Set("Authorization", pushBearer(t))
	w = httptest.NewRecorder()
	srv.setPushPreference(w, r)
	if w.Code != http.StatusBadRequest {
		t.Errorf("missing push_enabled: got %d want 400", w.Code)
	}
}

func TestVAPIDPublicKey_PublicAndReportsConfigured(t *testing.T) {
	// Configured.
	srv := newPushServer(push.VAPIDConfig{PublicKey: "BPUBKEY", PrivateKey: "priv"})
	r := httptest.NewRequest(http.MethodGet, "/", nil) // no auth — the key is public by design
	w := httptest.NewRecorder()
	srv.getVAPIDPublicKey(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("got %d", w.Code)
	}
	var body map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["public_key"] != "BPUBKEY" || body["configured"] != true {
		t.Errorf("unexpected body %v", body)
	}

	// Not configured → configured:false, empty key (FE falls back to in-app).
	srv = newPushServer(push.VAPIDConfig{})
	w = httptest.NewRecorder()
	srv.getVAPIDPublicKey(w, httptest.NewRequest(http.MethodGet, "/", nil))
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["configured"] != false {
		t.Errorf("expected configured=false, got %v", body)
	}
}

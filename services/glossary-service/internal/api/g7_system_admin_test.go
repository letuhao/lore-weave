package api

// G7 / D-GKA-SYSTEM-TIER-ADMIN — the admin-only System-tier write surface.
// Proves: an RS256 admin JWT with admin:write can CRUD system genres/kinds/attrs;
// a fully-valid HS256 USER token is REJECTED (tenancy — a regular user never
// mutates System tier); a missing scope → 403; no token → 401; admin-not-configured
// → 503; and an edit recomputes content_hash so G5 Sync detects it. Requires
// GLOSSARY_TEST_DB_URL.

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/adminjwt"
	"github.com/loreweave/glossary-service/internal/config"
)

const adminTestSecret = "admin_test_jwt_secret_at_least_32_chars!!"

// newAdminTestServer builds a Server with admin verification enabled against a
// freshly generated RSA key, plus a mint() that signs admin tokens with the
// matching private key (the same RS256/iss/aud/kid contract auth-service emits).
func newAdminTestServer(t *testing.T, pool *pgxpool.Pool) (*Server, func(scopes []string) string) {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("genkey: %v", err)
	}
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatalf("marshal pub: %v", err)
	}
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	srv := NewServer(pool, &config.Config{JWTSecret: adminTestSecret, AdminJWTPublicKeyPEM: string(pubPEM)})
	if srv.adminPub == nil {
		t.Fatal("admin verification not enabled on the test server")
	}
	kid, err := adminjwt.KeyFingerprint(&priv.PublicKey)
	if err != nil {
		t.Fatalf("fingerprint: %v", err)
	}
	mint := func(scopes []string) string {
		claims := adminjwt.AdminClaims{
			Role:   "admin",
			Scopes: scopes,
			RegisteredClaims: jwt.RegisteredClaims{
				Issuer:    adminjwt.Issuer,
				Audience:  jwt.ClaimStrings{adminjwt.Audience},
				Subject:   uuid.NewString(),
				ID:        uuid.NewString(),
				ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
				IssuedAt:  jwt.NewNumericDate(time.Now()),
			},
		}
		tok := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
		tok.Header["kid"] = kid
		signed, err := tok.SignedString(priv)
		if err != nil {
			t.Fatalf("sign admin token: %v", err)
		}
		return signed
	}
	return srv, mint
}

// userHS256 mints a fully-valid regular access token (HS256, the same secret the
// service trusts for user auth) — to prove it is still rejected at the admin gate.
func userHS256(t *testing.T) string {
	t.Helper()
	claims := jwt.RegisteredClaims{
		Subject:   uuid.NewString(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	}
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := tok.SignedString([]byte(adminTestSecret))
	if err != nil {
		t.Fatalf("sign user token: %v", err)
	}
	return signed
}

func adminReq(t *testing.T, srv *Server, method, url, token, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, url, bytes.NewBufferString(body))
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	req.Header.Set("Content-Type", "application/json")
	rw := httptest.NewRecorder()
	srv.Router().ServeHTTP(rw, req)
	return rw
}

func TestSystemTierAdmin_CRUDAndGuards(t *testing.T) {
	pool := openTestDB(t)
	runMigrations(t, pool)
	ctx := context.Background()
	srv, mint := newAdminTestServer(t, pool)
	base := "/v1/glossary"
	admin := mint([]string{"admin:read", "admin:write"})

	// Deletes are now SOFT (G-C8) — the fixed-code rows linger as deprecated after the
	// test's own delete path, so hard-delete them to keep the test re-runnable.
	t.Cleanup(func() {
		c := context.Background()
		pool.Exec(c, `DELETE FROM system_attributes WHERE code='armor'`)        //nolint:errcheck
		pool.Exec(c, `DELETE FROM system_kinds WHERE code='mecha_g7'`)          //nolint:errcheck
		pool.Exec(c, `DELETE FROM system_genres WHERE code='cyberpunk_g7'`)     //nolint:errcheck
	})

	// ── create a system genre ────────────────────────────────────────────────
	cw := adminReq(t, srv, http.MethodPost, base+"/system-genres", admin,
		`{"name":"Cyberpunk","code":"cyberpunk_g7","icon":"🤖"}`)
	if cw.Code != http.StatusCreated {
		t.Fatalf("create genre: want 201, got %d (%s)", cw.Code, cw.Body.String())
	}
	var created struct {
		GenreID string `json:"genre_id"`
		Code    string `json:"code"`
	}
	_ = json.Unmarshal(cw.Body.Bytes(), &created)
	if created.GenreID == "" || created.Code != "cyberpunk_g7" {
		t.Fatalf("create genre: bad body %s", cw.Body.String())
	}
	// content_hash seeded = md5(code|name).
	var hash, wantHash string
	pool.QueryRow(ctx, `SELECT content_hash, md5('cyberpunk_g7'||'|'||'Cyberpunk') FROM system_genres WHERE genre_id=$1`, created.GenreID).Scan(&hash, &wantHash)
	if hash == "" || hash != wantHash {
		t.Fatalf("create genre hash: got %q want %q", hash, wantHash)
	}

	// ── TENANCY: a fully-valid USER token is rejected (401), never writes System ─
	uw := adminReq(t, srv, http.MethodPost, base+"/system-genres", userHS256(t), `{"name":"Hack"}`)
	if uw.Code != http.StatusUnauthorized {
		t.Fatalf("user token at admin gate: want 401, got %d", uw.Code)
	}
	// ── missing scope → 403 ───────────────────────────────────────────────────
	ro := adminReq(t, srv, http.MethodPost, base+"/system-genres", mint([]string{"admin:read"}), `{"name":"Hack"}`)
	if ro.Code != http.StatusForbidden {
		t.Fatalf("read-only scope: want 403, got %d", ro.Code)
	}
	// ── no token → 401 ────────────────────────────────────────────────────────
	nw := adminReq(t, srv, http.MethodPost, base+"/system-genres", "", `{"name":"Hack"}`)
	if nw.Code != http.StatusUnauthorized {
		t.Fatalf("no token: want 401, got %d", nw.Code)
	}

	// ── patch the genre → content_hash recomputed (D-GKA-SYNC-HASH-ON-ADMIN-EDIT) ─
	pw := adminReq(t, srv, http.MethodPatch, base+"/system-genres/"+created.GenreID, admin, `{"name":"Cyber"}`)
	if pw.Code != http.StatusOK {
		t.Fatalf("patch genre: want 200, got %d (%s)", pw.Code, pw.Body.String())
	}
	pool.QueryRow(ctx, `SELECT content_hash, md5('cyberpunk_g7'||'|'||'Cyber') FROM system_genres WHERE genre_id=$1`, created.GenreID).Scan(&hash, &wantHash)
	if hash != wantHash {
		t.Fatalf("patch genre hash not recomputed: got %q want %q", hash, wantHash)
	}

	// ── universal is never deletable (O4) ─────────────────────────────────────
	var universalID string
	pool.QueryRow(ctx, `SELECT genre_id::text FROM system_genres WHERE code='universal'`).Scan(&universalID)
	dw := adminReq(t, srv, http.MethodDelete, base+"/system-genres/"+universalID, admin, "")
	if dw.Code != http.StatusNotFound {
		t.Fatalf("delete universal: want 404 (guarded), got %d", dw.Code)
	}

	// ── kind: create + patch + delete ─────────────────────────────────────────
	kw := adminReq(t, srv, http.MethodPost, base+"/system-kinds", admin,
		`{"name":"Mecha","code":"mecha_g7","description":"giant robots"}`)
	if kw.Code != http.StatusCreated {
		t.Fatalf("create kind: want 201, got %d (%s)", kw.Code, kw.Body.String())
	}
	var ck struct {
		KindID string `json:"kind_id"`
	}
	_ = json.Unmarshal(kw.Body.Bytes(), &ck)

	// ── attribute on (mecha kind × cyberpunk genre): create → patch recomputes hash ─
	aw := adminReq(t, srv, http.MethodPost, base+"/system-attributes-admin", admin,
		`{"kind_id":"`+ck.KindID+`","genre_id":"`+created.GenreID+`","name":"Armor","code":"armor","field_type":"text"}`)
	if aw.Code != http.StatusCreated {
		t.Fatalf("create attr: want 201, got %d (%s)", aw.Code, aw.Body.String())
	}
	var ca struct {
		AttrID string `json:"attr_id"`
	}
	_ = json.Unmarshal(aw.Body.Bytes(), &ca)
	var beforeHash, afterHash string
	pool.QueryRow(ctx, `SELECT content_hash FROM system_attributes WHERE attr_id=$1`, ca.AttrID).Scan(&beforeHash)
	apw := adminReq(t, srv, http.MethodPatch, base+"/system-attributes-admin/"+ca.AttrID, admin, `{"is_required":true}`)
	if apw.Code != http.StatusOK {
		t.Fatalf("patch attr: want 200, got %d (%s)", apw.Code, apw.Body.String())
	}
	pool.QueryRow(ctx, `SELECT content_hash FROM system_attributes WHERE attr_id=$1`, ca.AttrID).Scan(&afterHash)
	if afterHash == "" || afterHash == beforeHash {
		t.Fatalf("attr hash not recomputed on edit: before=%q after=%q", beforeHash, afterHash)
	}

	// delete the attr + kind + genre we created (cleanup + delete path).
	for _, u := range []string{
		base + "/system-attributes-admin/" + ca.AttrID,
		base + "/system-kinds/" + ck.KindID,
		base + "/system-genres/" + created.GenreID,
	} {
		if rw := adminReq(t, srv, http.MethodDelete, u, admin, ""); rw.Code != http.StatusNoContent {
			t.Fatalf("delete %s: want 204, got %d (%s)", u, rw.Code, rw.Body.String())
		}
	}
}

// TestSystemTierAdmin_NotConfigured proves the endpoints fail closed (503) when no
// admin verify key is configured — never silently open.
func TestSystemTierAdmin_NotConfigured(t *testing.T) {
	pool := openTestDB(t)
	runMigrations(t, pool)
	srv := NewServer(pool, &config.Config{JWTSecret: adminTestSecret}) // no ADMIN_JWT_PUBLIC_KEY_PEM
	rw := adminReq(t, srv, http.MethodPost, "/v1/glossary/system-genres", "anything", `{"name":"x"}`)
	if rw.Code != http.StatusServiceUnavailable {
		t.Fatalf("admin not configured: want 503, got %d", rw.Code)
	}
}

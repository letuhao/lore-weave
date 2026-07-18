package api_test

// WS-1.0 — GET /internal/users/{user_id}/dek (DECISIONS-SEALED PO-2).
//
// The tests that matter are the ones about LOSING or LEAKING a user's key:
//   - it must FAIL CLOSED with no KEK (never let a deployment store diaries in the clear)
//   - it must be token-gated (a wrapped DEK is exactly the blob an offline attacker wants)
//   - it must be IDEMPOTENT — including under a concurrent double-provision. Minting two
//     DEKs for one user silently splits their data into two unreadable halves.
//   - it must return the WRAPPED key, never the plaintext one.
//
// Gated on AUTH_TEST_PG_URL like the other auth PG tests.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"sync"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/auth-service/internal/api"
	"github.com/loreweave/auth-service/internal/config"
	"github.com/loreweave/auth-service/internal/migrate"
)

const testKEK = "a-test-kek-value-for-wrapping-deks"

func dekServer(t *testing.T, kek string) (*api.Server, *pgxpool.Pool) {
	t.Helper()
	dsn := os.Getenv("AUTH_TEST_PG_URL")
	if dsn == "" {
		t.Skip("AUTH_TEST_PG_URL not set; skipping DEK PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	if err := migrate.Up(ctx, pool); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return api.NewServer(pool, &config.Config{
		JWTSecret:            "test-secret-at-least-32-characters-long!",
		InternalServiceToken: "itok",
		DiaryEncryptionKey:   kek,
	}), pool
}

func seedUser(t *testing.T, pool *pgxpool.Pool) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := pool.QueryRow(context.Background(),
		`INSERT INTO users (email, password_hash, display_name)
		 VALUES ($1,'x','DEK Test') RETURNING id`,
		"dek-"+uuid.NewString()+"@test.local",
	).Scan(&id); err != nil {
		t.Fatalf("seed user: %v", err)
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM users WHERE id=$1`, id)
	})
	return id
}

func getDEK(t *testing.T, s *api.Server, userID uuid.UUID, token string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/internal/users/"+userID.String()+"/dek", nil)
	if token != "" {
		req.Header.Set("X-Internal-Token", token)
	}
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func decodeDEK(t *testing.T, rr *httptest.ResponseRecorder) (wrapped, keyRef string) {
	t.Helper()
	var out struct {
		WrappedDEK string `json:"wrapped_dek"`
		KeyRef     string `json:"key_ref"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v (body=%s)", err, rr.Body.String())
	}
	return out.WrappedDEK, out.KeyRef
}

func TestUserDEK_ProvisionsOnFirstReadAndIsIdempotent_PG(t *testing.T) {
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)

	rr1 := getDEK(t, s, uid, "itok")
	if rr1.Code != http.StatusOK {
		t.Fatalf("first read = %d, body=%s", rr1.Code, rr1.Body.String())
	}
	w1, ref1 := decodeDEK(t, rr1)
	if w1 == "" || ref1 == "" {
		t.Fatal("first read returned an empty dek/key_ref")
	}

	// Second read must return the SAME key. A user with two DEKs has two unreadable
	// halves of a diary.
	rr2 := getDEK(t, s, uid, "itok")
	w2, ref2 := decodeDEK(t, rr2)
	if w2 != w1 || ref2 != ref1 {
		t.Fatalf("a second read minted a DIFFERENT dek (%q -> %q). Everything encrypted "+
			"under the first key would become unreadable.", w1, w2)
	}
}

func TestUserDEK_ConcurrentProvisionYieldsOneKey_PG(t *testing.T) {
	// Two services encrypting for the same user at the same moment (chat writing a
	// message while knowledge writes a fact) must NOT race into two DEKs.
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)

	const n = 8
	var wg sync.WaitGroup
	got := make([]string, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			rr := getDEK(t, s, uid, "itok")
			if rr.Code == http.StatusOK {
				var out struct {
					WrappedDEK string `json:"wrapped_dek"`
				}
				_ = json.Unmarshal(rr.Body.Bytes(), &out)
				got[i] = out.WrappedDEK
			}
		}(i)
	}
	wg.Wait()

	first := got[0]
	if first == "" {
		t.Fatal("no dek returned")
	}
	for i, g := range got {
		if g != first {
			t.Fatalf("concurrent provision produced DIFFERENT deks (caller %d). Exactly "+
				"one must win, and every caller must receive it — otherwise a user's data "+
				"is split across two keys and half of it is permanently unreadable.", i)
		}
	}

	var rows int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM user_deks WHERE user_id=$1`, uid).Scan(&rows); err != nil {
		t.Fatalf("count: %v", err)
	}
	if rows != 1 {
		t.Fatalf("user_deks rows = %d, want exactly 1", rows)
	}
}

func TestUserDEK_FailsClosedWithoutAKEK_PG(t *testing.T) {
	// A deployment with no KEK must REFUSE, not hand back something unusable and let the
	// caller write plaintext. "Temporarily unencrypted" is how it becomes permanent.
	s, pool := dekServer(t, "")
	uid := seedUser(t, pool)

	rr := getDEK(t, s, uid, "itok")
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("no-KEK read = %d, want 503. A missing KEK must fail CLOSED — never let a "+
			"deployment silently store diaries, assistant chat and facts in the clear.", rr.Code)
	}

	var rows int
	_ = pool.QueryRow(context.Background(),
		`SELECT count(*) FROM user_deks WHERE user_id=$1`, uid).Scan(&rows)
	if rows != 0 {
		t.Fatal("a failed (KEK-less) read must not have written a dek row")
	}
}

func TestUserDEK_RequiresTheInternalToken_PG(t *testing.T) {
	// The wrapped DEK is precisely the blob an attacker needs to attack offline once they
	// also obtain the KEK. It must never be anonymously readable.
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)

	rr := getDEK(t, s, uid, "") // no token
	if rr.Code == http.StatusOK {
		t.Fatal("the wrapped DEK was served WITHOUT the internal service token")
	}

	rr = getDEK(t, s, uid, "wrong-token")
	if rr.Code == http.StatusOK {
		t.Fatal("the wrapped DEK was served with a WRONG internal service token")
	}
}

func TestUserDEK_DoesNotReturnThePlaintextKey_PG(t *testing.T) {
	// The endpoint's whole design point: the plaintext key never crosses the network.
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)

	rr := getDEK(t, s, uid, "itok")
	body := rr.Body.String()

	var out map[string]any
	if err := json.Unmarshal([]byte(body), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	for _, forbidden := range []string{"dek", "plaintext_dek", "key"} {
		if _, present := out[forbidden]; present {
			t.Fatalf("the response carries a %q field — only the WRAPPED dek may leave "+
				"auth-service. body=%s", forbidden, body)
		}
	}
	if _, ok := out["wrapped_dek"]; !ok {
		t.Fatalf("missing wrapped_dek: %s", body)
	}
}

func shredDEK(t *testing.T, s *api.Server, userID uuid.UUID, token string, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodDelete, "/internal/users/"+userID.String()+"/dek", nil)
	if token != "" {
		req.Header.Set("X-Internal-Token", token)
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

// P3 (DBT-9) — the crypto-shred (the platform's most destructive irreversible op) must leave a
// DURABLE, attributed forensic trail that OUTLIVES the user, and must record a no-op shred rather
// than hide it.
func TestUserDEK_ShredWritesDurableAuditRow_PG(t *testing.T) {
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)
	ctx := context.Background()
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM dek_shred_audit WHERE user_id=$1`, uid) })

	if rr := getDEK(t, s, uid, "itok"); rr.Code != http.StatusOK { // provision
		t.Fatalf("provision: %d", rr.Code)
	}

	// (1) a real shred → 204 + an audit row with rows_shredded=1 + the actor/trace attribution.
	rr := shredDEK(t, s, uid, "itok", map[string]string{"X-Actor": "erasure-worker", "x-trace-id": "trace-abc"})
	if rr.Code != http.StatusNoContent {
		t.Fatalf("shred = %d, body=%s", rr.Code, rr.Body.String())
	}
	var rowsShredded int
	var actor, trace string
	if err := pool.QueryRow(ctx,
		`SELECT rows_shredded, coalesce(actor,''), coalesce(trace_id,'') FROM dek_shred_audit
		 WHERE user_id=$1 ORDER BY created_at DESC LIMIT 1`, uid).Scan(&rowsShredded, &actor, &trace); err != nil {
		t.Fatalf("no audit row written for the shred: %v", err)
	}
	if rowsShredded != 1 || actor != "erasure-worker" || trace != "trace-abc" {
		t.Fatalf("audit row wrong: rows=%d actor=%q trace=%q (want 1/erasure-worker/trace-abc)", rowsShredded, actor, trace)
	}

	// (2) a 2nd shred (already absent) → 204 (converges) + a NEW audit row with rows_shredded=0 —
	// a mis-targeted/no-op shred is RECORDED, never silently swallowed.
	if rr2 := shredDEK(t, s, uid, "itok", nil); rr2.Code != http.StatusNoContent {
		t.Fatalf("2nd shred (idempotent) = %d", rr2.Code)
	}
	var auditCount, zeroRowShreds int
	if err := pool.QueryRow(ctx,
		`SELECT count(*), count(*) FILTER (WHERE rows_shredded=0) FROM dek_shred_audit WHERE user_id=$1`, uid).
		Scan(&auditCount, &zeroRowShreds); err != nil {
		t.Fatalf("count audit: %v", err)
	}
	if auditCount != 2 || zeroRowShreds != 1 {
		t.Fatalf("want 2 audit rows incl. 1 no-op, got %d rows / %d no-op", auditCount, zeroRowShreds)
	}

	// (3) the audit OUTLIVES the user — deleting the user must NOT cascade-erase the forensic record.
	if _, err := pool.Exec(ctx, `DELETE FROM users WHERE id=$1`, uid); err != nil {
		t.Fatalf("delete user: %v", err)
	}
	var afterDelete int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM dek_shred_audit WHERE user_id=$1`, uid).Scan(&afterDelete); err != nil {
		t.Fatalf("count after user delete: %v", err)
	}
	if afterDelete != 2 {
		t.Fatalf("the shred audit was erased with the user (count=%d) — the forensic trail must survive", afterDelete)
	}
}

func TestUserDEK_IsErasedWithTheUser_PG(t *testing.T) {
	// D18 crypto-shred: deleting the user drops the DEK, and without the DEK their
	// ciphertext is unrecoverable — INCLUDING in any backup taken before the deletion.
	// This is the only erasure story that survives backup resurrection (T23).
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)

	if rr := getDEK(t, s, uid, "itok"); rr.Code != http.StatusOK {
		t.Fatalf("provision: %d", rr.Code)
	}

	if _, err := pool.Exec(context.Background(), `DELETE FROM users WHERE id=$1`, uid); err != nil {
		t.Fatalf("delete user: %v", err)
	}

	var rows int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM user_deks WHERE user_id=$1`, uid).Scan(&rows); err != nil {
		t.Fatalf("count: %v", err)
	}
	if rows != 0 {
		t.Fatal("deleting the user did NOT cascade-delete their DEK. Without that cascade " +
			"there is no crypto-shred, and a restored backup would resurrect readable " +
			"content the user asked us to erase.")
	}
}

package api_test

// WS-2.7 — DELETE /internal/users/{user_id}/dek, the D18 crypto-shred (PO-4 release req).
//
// The tests that matter here are about ERASURE actually happening and NOT being triggerable
// by the wrong party:
//   - the shred REMOVES the row (absence — a crypto-shred that leaves the key is no shred);
//   - it is IDEMPOTENT (204 on an already-absent DEK), because a retryable purge worker
//     drives it and a retry must converge, not 404;
//   - it is TOKEN-GATED, because an anonymous crypto-shred is a trivial, irreversible
//     denial-of-data attack — and a rejected attempt must LEAVE THE KEY INTACT;
//   - it does NOT require a KEK (deleting a row needs no key; a shred must fire even when the
//     KEK is misconfigured — "can't find the key" must never block "destroy the key");
//   - re-provisioning after a shred mints a DIFFERENT key — the old one does not come back,
//     so content encrypted under it is unrecoverable (the point of the shred).
//
// Reuses dekServer/seedUser/getDEK/decodeDEK/testKEK from user_dek_pg_test.go (same package).
// Gated on AUTH_TEST_PG_URL like the other auth PG tests.

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func deleteDEK(t *testing.T, s interface {
	Router() http.Handler
}, userID uuid.UUID, token string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodDelete, "/internal/users/"+userID.String()+"/dek", nil)
	if token != "" {
		req.Header.Set("X-Internal-Token", token)
	}
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func dekRows(t *testing.T, pool *pgxpool.Pool, uid uuid.UUID) int {
	t.Helper()
	var n int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM user_deks WHERE user_id=$1`, uid).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	return n
}

func TestUserDEK_ExplicitShred_RemovesTheRow_PG(t *testing.T) {
	// The core property (standing invariant #6: erasure asserts ABSENCE). Provision a DEK,
	// shred it via the endpoint, and the row must be GONE — not tombstoned, not hidden. Once
	// it is gone, every byte encrypted under it is unrecoverable, even from a backup.
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)

	if rr := getDEK(t, s, uid, "itok"); rr.Code != http.StatusOK {
		t.Fatalf("provision: %d", rr.Code)
	}
	if got := dekRows(t, pool, uid); got != 1 {
		t.Fatalf("precondition: want 1 dek row, got %d", got)
	}

	rr := deleteDEK(t, s, uid, "itok")
	if rr.Code != http.StatusNoContent {
		t.Fatalf("shred = %d, want 204. body=%s", rr.Code, rr.Body.String())
	}
	if got := dekRows(t, pool, uid); got != 0 {
		t.Fatalf("after the shred the DEK row still exists (%d). A crypto-shred that leaves "+
			"the key is not a shred — the content it protects remains recoverable.", got)
	}
}

func TestUserDEK_Shred_IsIdempotent_PG(t *testing.T) {
	// A retryable purge worker drives erasure. Shredding a DEK that was never provisioned,
	// and shredding twice, must both be success (204) — a retry after a partial failure has
	// to converge on "the key is gone", not error out because it is ALREADY gone.
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)

	// Never provisioned → still a clean 204.
	if rr := deleteDEK(t, s, uid, "itok"); rr.Code != http.StatusNoContent {
		t.Fatalf("shred of a never-provisioned DEK = %d, want 204 (idempotent)", rr.Code)
	}

	if rr := getDEK(t, s, uid, "itok"); rr.Code != http.StatusOK {
		t.Fatalf("provision: %d", rr.Code)
	}
	if rr := deleteDEK(t, s, uid, "itok"); rr.Code != http.StatusNoContent {
		t.Fatalf("first shred = %d, want 204", rr.Code)
	}
	if rr := deleteDEK(t, s, uid, "itok"); rr.Code != http.StatusNoContent {
		t.Fatalf("second shred = %d, want 204 (idempotent)", rr.Code)
	}
	if got := dekRows(t, pool, uid); got != 0 {
		t.Fatalf("row present after a double shred: %d", got)
	}
}

func TestUserDEK_Shred_RequiresTheInternalToken_PG(t *testing.T) {
	// A crypto-shred is irreversible. If it were anonymously triggerable, any caller who can
	// reach the internal network could destroy any user's data forever. A rejected attempt
	// must leave the key INTACT.
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)
	if rr := getDEK(t, s, uid, "itok"); rr.Code != http.StatusOK {
		t.Fatalf("provision: %d", rr.Code)
	}

	if rr := deleteDEK(t, s, uid, ""); rr.Code == http.StatusNoContent {
		t.Fatal("the DEK was crypto-shredded WITHOUT the internal service token")
	}
	if rr := deleteDEK(t, s, uid, "wrong-token"); rr.Code == http.StatusNoContent {
		t.Fatal("the DEK was crypto-shredded with a WRONG internal service token")
	}
	if got := dekRows(t, pool, uid); got != 1 {
		t.Fatalf("a rejected shred must LEAVE THE KEY INTACT, but the row count is %d", got)
	}
}

func TestUserDEK_Shred_WorksWithoutAKEK_PG(t *testing.T) {
	// D-R9: the read fails CLOSED without a KEK (503), but the shred must SUCCEED without one.
	// Deleting a row needs no key, and you never want a KEK misconfiguration to block erasure
	// — "I can't find the key" must not stop "destroy the key". Provision with a KEK, then
	// shred through a KEK-less server pointed at the same database.
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)
	if rr := getDEK(t, s, uid, "itok"); rr.Code != http.StatusOK {
		t.Fatalf("provision: %d", rr.Code)
	}

	noKEK, _ := dekServer(t, "") // same DSN, no KEK configured
	rr := deleteDEK(t, noKEK, uid, "itok")
	if rr.Code != http.StatusNoContent {
		t.Fatalf("shred without a KEK = %d, want 204. A shred must not depend on the KEK.", rr.Code)
	}
	if got := dekRows(t, pool, uid); got != 0 {
		t.Fatalf("KEK-less shred did not remove the row: %d", got)
	}
}

func TestUserDEK_Shred_IsScopedToTheTargetUser_PG(t *testing.T) {
	// A crypto-shred must destroy exactly ONE user's key. Without this test a refactor that
	// dropped the `WHERE user_id=$1` (or fat-fingered `!=`) would delete EVERY user's DEK and
	// stay green — the single seeded row in the other shred tests also goes to 0 when the whole
	// table is wiped. Seed a bystander and prove their key survives. (Review WS-2.7 M2.)
	s, pool := dekServer(t, testKEK)
	target := seedUser(t, pool)
	bystander := seedUser(t, pool)

	if rr := getDEK(t, s, target, "itok"); rr.Code != http.StatusOK {
		t.Fatalf("provision target: %d", rr.Code)
	}
	if rr := getDEK(t, s, bystander, "itok"); rr.Code != http.StatusOK {
		t.Fatalf("provision bystander: %d", rr.Code)
	}

	if rr := deleteDEK(t, s, target, "itok"); rr.Code != http.StatusNoContent {
		t.Fatalf("shred target = %d, want 204", rr.Code)
	}

	if got := dekRows(t, pool, target); got != 0 {
		t.Fatalf("the target's DEK was not shredded: %d", got)
	}
	if got := dekRows(t, pool, bystander); got != 1 {
		t.Fatalf("a shred of one user destroyed ANOTHER user's DEK (bystander rows=%d). The "+
			"delete is not scoped to its target — this would crypto-shred the whole deployment.", got)
	}
}

func TestUserDEK_DeletedAccount_CannotReprovisionAKey_PG(t *testing.T) {
	// The erasure completeness guard (H2). After a shred, a straggler read must NOT resurrect
	// a usable key for an account that is no longer active. Provision, shred, mark the account
	// deleted, then read: the read must FAIL CLOSED (409) and leave the row absent — otherwise
	// a redelivered event re-mints a key and re-enables encryptable content for an erased user.
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)

	if rr := getDEK(t, s, uid, "itok"); rr.Code != http.StatusOK {
		t.Fatalf("provision: %d", rr.Code)
	}
	if rr := deleteDEK(t, s, uid, "itok"); rr.Code != http.StatusNoContent {
		t.Fatalf("shred: %d", rr.Code)
	}
	if _, err := pool.Exec(context.Background(),
		`UPDATE users SET account_status='deleted' WHERE id=$1`, uid); err != nil {
		t.Fatalf("soft-delete: %v", err)
	}

	rr := getDEK(t, s, uid, "itok")
	if rr.Code != http.StatusConflict {
		t.Fatalf("read for a deleted account = %d, want 409. A non-active account must not be "+
			"able to re-provision a DEK — that resurrects encryptable content after erasure. body=%s",
			rr.Code, rr.Body.String())
	}
	if got := dekRows(t, pool, uid); got != 0 {
		t.Fatalf("a refused provision still wrote a DEK row for a deleted account: %d", got)
	}
}

func TestUserDEK_UnknownUser_IsNotProvisioned_PG(t *testing.T) {
	// A DEK read for a user id that does not exist must 404, not fabricate a users-less DEK
	// row. Minting for a phantom id (a typo'd erasure target, a dangling reference) would
	// leave an orphaned key nothing can ever reach or shred.
	s, _ := dekServer(t, testKEK)
	rr := getDEK(t, s, uuid.New(), "itok")
	if rr.Code != http.StatusNotFound {
		t.Fatalf("read for an unknown user = %d, want 404 (no phantom provisioning)", rr.Code)
	}
}

func TestUserDEK_ReprovisionAfterShred_MintsADifferentKey_PG(t *testing.T) {
	// The shred is real, not cosmetic: after it, a fresh read mints a NEW DEK. The old key
	// does not "come back", so anything encrypted under it stays unrecoverable. Two DEKs
	// generated from CSPRNG bytes are cryptographically certain to differ, so an equal
	// wrapped blob here would mean the delete silently didn't happen and the old key survived.
	s, pool := dekServer(t, testKEK)
	uid := seedUser(t, pool)

	rr1 := getDEK(t, s, uid, "itok")
	if rr1.Code != http.StatusOK {
		t.Fatalf("provision: %d", rr1.Code)
	}
	before, _ := decodeDEK(t, rr1)

	if rr := deleteDEK(t, s, uid, "itok"); rr.Code != http.StatusNoContent {
		t.Fatalf("shred: %d", rr.Code)
	}

	rr2 := getDEK(t, s, uid, "itok")
	if rr2.Code != http.StatusOK {
		t.Fatalf("re-provision after shred: %d", rr2.Code)
	}
	after, _ := decodeDEK(t, rr2)

	if after == "" {
		t.Fatal("re-provision returned an empty DEK")
	}
	if after == before {
		t.Fatal("the re-provisioned DEK is byte-identical to the shredded one — the shred did " +
			"not destroy the key, so the old content is still recoverable.")
	}
}

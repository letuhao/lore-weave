package api

// WS-1.0 — the per-user DEK endpoint (DECISIONS-SEALED PO-2).
//
// auth-service is the ONE home of a user's data-encryption key, for the same reason it is
// the home of their timezone and preferences: it is a platform-wide per-user fact (sealed
// decision T-1). It must be ONE key per user — chat-service encrypts a message and
// knowledge-service later decrypts it to extract from, so a per-service key would make
// cross-service reads impossible.
//
// ⚠️ THIS RETURNS THE **WRAPPED** DEK, NEVER THE PLAINTEXT ONE.
//
// The consumer unwraps it with the KEK from its own environment. So the plaintext key
// never crosses the network, and auth-service itself does not need the KEK at all — it
// stores an opaque blob it cannot read. (It is deliberately NOT a "give me the plaintext
// key" endpoint: that would put every user's live key on the wire, one SSRF or one log
// line away from disclosure.)
//
// What this protects: a stolen DB dump, a stolen backup, a curious DBA, a table/log leak.
// What it does NOT protect: an operator who controls a running consumer service and can
// read the unwrapped DEK from its memory. That is physics — a server-side AI pipeline
// must see plaintext. Say so plainly; do not let the claim drift.

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// internalGetUserDEK — GET /internal/users/{user_id}/dek
//
// Returns {wrapped_dek, key_ref}. PROVISIONS ON FIRST READ, idempotently: a user gets a
// DEK the moment anything first needs to encrypt for them, so there is no separate
// "enable encryption" step that could be skipped, forgotten, or fail half-way and leave
// content written in the clear.
//
// Token-gated (requireInternalServiceToken) — an unauthenticated wrapped-DEK read would
// hand an attacker the exact blob they need to attack offline once they also have the KEK.
func (s *Server) internalGetUserDEK(w http.ResponseWriter, r *http.Request) {
	userID, err := uuid.Parse(chi.URLParam(r, "user_id"))
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid user_id")
		return
	}
	if len(s.dekKEK) == 0 {
		// FAIL CLOSED. A deployment that stores private content without a KEK must not
		// quietly hand out an unencryptable "key" — it must refuse, loudly, so the
		// misconfiguration is fixed before any diary is written in the clear.
		writeErr(w, http.StatusServiceUnavailable, "AUTH_DEK_UNAVAILABLE",
			"DIARY_ENCRYPTION_KEY is not configured; private content cannot be stored")
		return
	}

	ctx := r.Context()

	var wrapped, keyRef string
	err = s.pool.QueryRow(ctx,
		`SELECT wrapped_dek, key_ref FROM user_deks WHERE user_id = $1`, userID,
	).Scan(&wrapped, &keyRef)
	if err == nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"user_id": userID.String(), "wrapped_dek": wrapped, "key_ref": keyRef,
		})
		return
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "failed to read dek")
		return
	}

	// Fail-CLOSED before minting: never provision a fresh DEK for a non-active account.
	// This endpoint provisions on read, so WITHOUT this guard a straggler read AFTER erasure
	// — an at-least-once redelivered event, a lagging worker whose cache expired — would
	// silently re-mint a usable key for a user whose data was supposed to be gone, resurrecting
	// encryptable content and defeating the crypto-shred. An active user re-provisioning after
	// erasing their *history* is legitimate (they keep using the assistant with a fresh key);
	// a DELETED/erased account acquiring a new key is not. (Review WS-2.7 H2.)
	var status string
	switch e := s.pool.QueryRow(ctx,
		`SELECT account_status FROM users WHERE id = $1`, userID).Scan(&status); {
	case errors.Is(e, pgx.ErrNoRows):
		// No such user — do not fabricate a key for a phantom id (a typo'd erasure target).
		writeErr(w, http.StatusNotFound, "AUTH_NOT_FOUND", "user not found")
		return
	case e != nil:
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "failed to read user status")
		return
	case status != "active":
		writeErr(w, http.StatusConflict, "AUTH_DEK_ACCOUNT_INACTIVE",
			"cannot provision a DEK for a non-active account")
		return
	}

	// First use → mint one. ON CONFLICT DO NOTHING + re-read makes this safe under a
	// concurrent double-provision (two services encrypting for the same user at once):
	// exactly one row wins and BOTH callers return the SAME key. Minting two DEKs for one
	// user would silently split their data into two unreadable halves.
	dek := make([]byte, 32)
	if _, err := rand.Read(dek); err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "failed to generate dek")
		return
	}
	// AAD binds the wrapped DEK to THIS user, so a DB-write adversary cannot move A's
	// wrapped_dek onto B's row and have it unwrap. Must match loreweave_crypto._wrap_aad
	// byte-for-byte (same domain separator + user_id), or Python cannot unwrap.
	newWrapped, err := sealWithKEK(s.dekKEK, dek, wrapAAD(userID))
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "failed to wrap dek")
		return
	}
	newRef := kekRef(s.dekKEK)

	if _, err := s.pool.Exec(ctx, `
INSERT INTO user_deks (user_id, wrapped_dek, key_ref) VALUES ($1, $2, $3)
ON CONFLICT (user_id) DO NOTHING`, userID, newWrapped, newRef); err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "failed to store dek")
		return
	}
	// Re-read: the row we return must be the row that WON the race, not the one we just
	// generated and possibly discarded.
	if err := s.pool.QueryRow(ctx,
		`SELECT wrapped_dek, key_ref FROM user_deks WHERE user_id = $1`, userID,
	).Scan(&wrapped, &keyRef); err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "failed to read dek")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"user_id": userID.String(), "wrapped_dek": wrapped, "key_ref": keyRef,
	})
}

// internalDeleteUserDEK — DELETE /internal/users/{user_id}/dek
//
// The D18 crypto-shred (T23), made REACHABLE. HARD-deletes the user's wrapped DEK so every
// byte of content encrypted under it — diary bodies, assistant chat, private facts —
// becomes permanently unrecoverable, INCLUDING from a restored backup: the ciphertext may
// survive a restore, but the only key that opens it is gone. A soft delete cannot tell this
// story (the DEK, and therefore the content, would come back with the row).
//
// This is DELIBERATELY a distinct endpoint, NOT wired into the account soft-delete
// (`DELETE /v1/account`, which keeps a recovery window). Shredding the key on a *recoverable*
// deletion would make "recoverable" a lie. Irreversible crypto-shred belongs to the explicit
// "erase my data forever" flow — the WS-2.7 erasure worker, which is NOT YET BUILT. TODAY this
// endpoint has NO caller: it is the reachable primitive. DBT-8 tracks wiring it into the GDPR
// erasure orchestrator (services/admin-cli/internal/commands/erasure.go, whose Eraser today
// shreds only the SEPARATE PII KEK and never this DEK) after the cross-service content-row
// deletion that must precede a shred. (D-R8.)
//
// IDEMPOTENT: erasure is driven by a retryable purge worker, so shredding an already-absent
// DEK is success (204), never 404 — a retry after a partial failure must CONVERGE, not error.
//
// NO KEK REQUIRED (unlike the read, which fails closed at 503 without one): deleting a row
// needs no key, and a shred must succeed even when the KEK is misconfigured — you never want
// "I can't find the key" to block "destroy the key." (D-R9.)
//
// TOKEN-GATED like the read: an anonymous caller must not be able to crypto-shred a user's
// key — that is a trivial, irreversible denial-of-data attack.
func (s *Server) internalDeleteUserDEK(w http.ResponseWriter, r *http.Request) {
	userID, err := uuid.Parse(chi.URLParam(r, "user_id"))
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid user_id")
		return
	}
	ctx := r.Context()
	// DBT-9 — the shred + its DURABLE audit row are ONE transaction, so a key can never be destroyed
	// without a forensic record (nor a record written without the destroy). The audit must outlive the
	// user, so its table has no FK to users (see migrate.go).
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "failed to shred dek")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	tag, err := tx.Exec(ctx, `DELETE FROM user_deks WHERE user_id = $1`, userID)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "failed to shred dek")
		return
	}
	if _, err := tx.Exec(ctx,
		`INSERT INTO dek_shred_audit (user_id, rows_shredded, actor, trace_id)
		 VALUES ($1, $2, NULLIF($3,''), NULLIF($4,''))`,
		userID, tag.RowsAffected(), r.Header.Get("X-Actor"), r.Header.Get("x-trace-id")); err != nil {
		// Fail-closed on the audit: a shred with no trail is exactly what DBT-9 forbids. Rolling back
		// leaves the DEK intact; the erasure worker retries and converges (D-R9 — a shred must converge).
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "failed to record shred audit")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "failed to shred dek")
		return
	}
	// No-silent-success (standing invariant #5): a shred that removed NOTHING is suspicious —
	// an erasure fired at the WRONG id destroys nothing while the caller records success. WARN
	// on a 0-row shred with a message that does NOT claim a key was destroyed, so a
	// mis-targeted erasure is visible in the record instead of masquerading as a completed
	// shred; INFO only when a key was actually crypto-shredded. (Review WS-2.7 M3/finding4.)
	if tag.RowsAffected() == 0 {
		slog.Warn("dek shred removed no row (already absent, or a wrong user_id)", "user_id", userID)
	} else {
		slog.Info("user dek crypto-shredded", "user_id", userID, "rows_shredded", tag.RowsAffected())
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── crypto (mirrors sdks/python/loreweave_crypto so both sides read one format) ──
//
// base64( nonce[12] || AES-GCM(kek, dek) ) — the same shape the usage_logs precedent uses,
// so an operator sees one ciphertext format across the platform.

// deriveKEK turns configured key material into a 32-byte AES key.
//
// SHA-256, never pad/truncate: a short env value silently truncated to a weak key is the
// classic footgun, and it fails silently (the code still "works").
func deriveKEK(raw string) []byte {
	if raw == "" {
		return nil
	}
	sum := sha256.Sum256([]byte(raw))
	return sum[:]
}

// kekRef is a NON-SECRET fingerprint of the KEK, stored beside each wrapped DEK so an
// operator can see at a glance which users are still wrapped under a retired key. Matches
// loreweave_crypto.key_ref byte-for-byte (same domain separator, same 16-hex prefix) — a
// drift here would make the rotation checklist lie.
func kekRef(kek []byte) string {
	h := sha256.New()
	h.Write([]byte("loreweave-kek-ref"))
	h.Write([]byte{0})
	h.Write(kek)
	return hex.EncodeToString(h.Sum(nil))[:16]
}

// wrapAAD mirrors loreweave_crypto._wrap_aad: b"loreweave-dek-wrap\x00" + user_id.
// A drift here makes every Go-wrapped DEK unreadable by the Python consumers — the golden
// vector test exists to catch exactly that.
func wrapAAD(userID uuid.UUID) []byte {
	return append([]byte("loreweave-dek-wrap\x00"), []byte(userID.String())...)
}

func sealWithKEK(kek, plain, aad []byte) (string, error) {
	block, err := aes.NewCipher(kek)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(gcm.Seal(nonce, nonce, plain, aad)), nil
}

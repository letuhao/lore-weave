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

	// First use → mint one. ON CONFLICT DO NOTHING + re-read makes this safe under a
	// concurrent double-provision (two services encrypting for the same user at once):
	// exactly one row wins and BOTH callers return the SAME key. Minting two DEKs for one
	// user would silently split their data into two unreadable halves.
	dek := make([]byte, 32)
	if _, err := rand.Read(dek); err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "failed to generate dek")
		return
	}
	newWrapped, err := sealWithKEK(s.dekKEK, dek)
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

func sealWithKEK(kek, plain []byte) (string, error) {
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
	return base64.StdEncoding.EncodeToString(gcm.Seal(nonce, nonce, plain, nil)), nil
}

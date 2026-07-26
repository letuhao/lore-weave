package api

// C5 / SD-C5 (P-12) — diary encryption-at-rest + crypto-shred.
//
// Diary chapter prose (kind='diary', journal_kind IS NOT NULL) is AES-GCM encrypted under the OWNER's
// per-user DEK (fetched from auth-service, unwrapped with book-service's dedicated DIARY_ENCRYPTION_KEY
// KEK). This raises the bar from "read a stolen DB dump / backup" to "subvert the running server". A
// server-side render still sees plaintext — that is physics; we do not over-claim.
//
// STORAGE. The prose lives in three columns; ALL are encrypted so a dump leaks nothing:
//   - chapter_raw_objects.body_text (TEXT)   — the canonical FE-read copy: stored as base64 ciphertext.
//   - chapter_drafts.body          (JSONB)   — stored as a JSON *string* of the ciphertext. The
//       block-extraction trigger then sees `body -> 'content'` = NULL and produces NO chapter_blocks,
//       so the 4th (trigger-derived) plaintext copy never exists for an encrypted diary — it degrades
//       to empty rather than erroring. word_count would derive to 0, so the writer sets it explicitly.
//   - chapter_revisions.body       (JSONB)   — same JSON-string ciphertext (encrypted audit history).
// The AAD binds each ciphertext to its chapter ("chapter:<id>"), so a DB-write adversary can't move a
// row's ciphertext to another chapter and have it decrypt.
//
// ROLLOUT (forward-encrypt). `chapters.body_encrypted` marks a row's storage format. New writes encrypt
// when a key is configured; existing plaintext rows stay readable (decrypt-on-read keys off the flag).
// A separate backfill job re-encrypts history — no big-bang re-encryption of live data (= no data-loss
// risk). If DIARY_ENCRYPTION_KEY is unset, encryption is OFF (writes stay plaintext) + a loud warning.
//
// CRYPTO-SHRED. On D-R27 erasure the diary rows are hard-deleted AND auth destroys the user's DEK, so
// any surviving backup ciphertext is permanently unreadable (the backup-resistant half P-12 wanted).

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"unicode"

	"github.com/google/uuid"
	crypto "github.com/loreweave/loreweave_crypto"
)

// diaryCrypto encrypts/decrypts diary prose under per-user DEKs. nil-safe: a zero value (Enabled()
// false) means encryption is off and every write stays plaintext — the un-keyed deployment path.
type diaryCrypto struct {
	ring     crypto.Keyring
	deks     *crypto.DEKClient
	enabled  bool
	authBase string // auth-service internal base — for the crypto-shred DELETE
	token    string
}

// newDiaryCrypto builds the component from config. Returns a disabled (plaintext) component + a loud
// warning when DIARY_ENCRYPTION_KEY is unset, so a deployment without the key still runs (novels are
// unaffected) but the operator is told diaries are NOT encrypted. Never JWT_SECRET (config guards that).
func newDiaryCrypto(authBaseURL, internalToken, activeKey, retiredKeys string) *diaryCrypto {
	if activeKey == "" {
		slog.Warn("book-service: DIARY_ENCRYPTION_KEY is not set — diary prose is stored in PLAINTEXT " +
			"at rest. Set a dedicated key (not JWT_SECRET) to enable encryption-at-rest (C5/P-12).")
		// Still record the auth coords so the crypto-shred on erasure can run even when this service
		// isn't itself encrypting (a mixed-fleet rollout: one replica keyed, another not).
		return &diaryCrypto{authBase: strings.TrimRight(authBaseURL, "/"), token: internalToken}
	}
	active, err := crypto.DeriveKey(activeKey)
	if err != nil {
		slog.Error("book-service: DIARY_ENCRYPTION_KEY is invalid — diary encryption DISABLED", "err", err)
		return &diaryCrypto{}
	}
	var retired [][]byte
	for _, part := range strings.Split(retiredKeys, ",") {
		if s := strings.TrimSpace(part); s != "" {
			if k, derr := crypto.DeriveKey(s); derr == nil {
				retired = append(retired, k)
			}
		}
	}
	ring := crypto.NewKeyring(active, retired...)
	return &diaryCrypto{
		ring:     ring,
		deks:     crypto.NewDEKClient(authBaseURL, internalToken, ring),
		enabled:  true,
		authBase: strings.TrimRight(authBaseURL, "/"),
		token:    internalToken,
	}
}

// Enabled reports whether encryption is on (a key is configured).
func (d *diaryCrypto) Enabled() bool { return d != nil && d.enabled }

func chapterAAD(chapterID uuid.UUID) string { return "chapter:" + chapterID.String() }

// encryptBody encrypts the plaintext diary body under the owner's DEK, bound to the chapter. Returns
// the ciphertext for the TEXT column (body_text) and the JSONB value (a JSON string of the same
// ciphertext) for chapter_drafts.body / chapter_revisions.body. RAISES on a DEK failure — the caller
// MUST abort the write, never fall back to plaintext (a "temporarily unencrypted" row is permanent and
// looks identical to an encrypted one to every future reader).
func (d *diaryCrypto) encryptBody(ctx context.Context, owner, chapterID uuid.UUID, plaintext string) (textCol string, jsonbCol []byte, err error) {
	dek, err := d.deks.Get(ctx, owner.String())
	if err != nil {
		return "", nil, fmt.Errorf("diary DEK unavailable — refusing to store plaintext: %w", err)
	}
	ct, err := crypto.Encrypt(dek, plaintext, chapterAAD(chapterID))
	if err != nil {
		return "", nil, fmt.Errorf("diary encrypt failed: %w", err)
	}
	// JSONB column: store the base64 ciphertext AS a JSON string (valid JSONB, and the trigger's
	// `body -> 'content'` yields NULL → no chapter_blocks, no plaintext leak there).
	jsonb, err := json.Marshal(ct)
	if err != nil {
		return "", nil, fmt.Errorf("diary encrypt marshal failed: %w", err)
	}
	return ct, jsonb, nil
}

// decryptBody decrypts a stored diary body. `stored` is the body_text column (base64 ciphertext when
// encrypted). A plaintext row (encrypted=false) is a pass-through — so decrypt-on-read tolerates BOTH
// formats during the forward-encrypt rollout. But an ENCRYPTED row when the component is disabled is a
// FAIL-CLOSED error (cold-review LOW-5): returning the raw base64 as if it were prose would silently
// serve ciphertext-as-text and mask a key-misconfiguration — never do that.
func (d *diaryCrypto) decryptBody(ctx context.Context, owner, chapterID uuid.UUID, stored string, encrypted bool) (string, error) {
	if !encrypted {
		return stored, nil
	}
	if !d.Enabled() {
		return "", fmt.Errorf("row is encrypted but DIARY_ENCRYPTION_KEY is not configured — refusing to serve ciphertext as prose")
	}
	dek, err := d.deks.Get(ctx, owner.String())
	if err != nil {
		return "", fmt.Errorf("diary DEK unavailable — cannot decrypt: %w", err)
	}
	pt, err := crypto.Decrypt(dek, stored, chapterAAD(chapterID))
	if err != nil {
		return "", fmt.Errorf("diary decrypt failed: %w", err)
	}
	return pt, nil
}

// forgetUser drops the cached DEK on crypto-shred / rotation (the prompt path; the client TTL is the
// backstop). Safe to call when disabled.
func (d *diaryCrypto) forgetUser(owner uuid.UUID) {
	if d.Enabled() {
		d.deks.Forget(owner.String())
	}
}

// prepDiaryBody prepares the values a diary write stores for `body`. When encryption is enabled it
// returns the ciphertext for body_text + a JSON-string ciphertext for the JSONB draft/revision columns
// (encrypted=true, an explicit word_count since the trigger would derive 0). When disabled it returns
// the plaintext body + the Tiptap JSON (encrypted=false, wordCount=-1 meaning "let the DB trigger
// compute it"). An encrypt failure is returned so the caller ABORTS the write (never stores plaintext).
func (s *Server) prepDiaryBody(ctx context.Context, owner, chapterID uuid.UUID, body string) (rawCol string, draftBody json.RawMessage, encrypted bool, wordCount int, err error) {
	jsonBody := plainTextToTiptapJSON(body)
	if !s.diaryCrypto.Enabled() {
		return body, jsonBody, false, -1, nil
	}
	ct, jsonb, eerr := s.diaryCrypto.encryptBody(ctx, owner, chapterID, body)
	if eerr != nil {
		return "", nil, false, 0, eerr
	}
	return ct, json.RawMessage(jsonb), true, diaryWordCount(body), nil
}

// destroyUserDEK crypto-shreds the user's per-user DEK at auth-service (DELETE /internal/users/{id}/dek):
// the backup-resistant half of D-R27 erasure — every byte encrypted under it (diary bodies) becomes
// permanently unrecoverable, INCLUDING from a restored backup (the ciphertext may survive, but the only
// key that opens it is gone). Idempotent (auth returns 204 for an already-absent key). Also drops the
// local DEK cache. Returns an error the caller SURFACES (a failed shred means the key survived — the
// erasure's row-delete still happened, but the backup-resistant guarantee did not). Uses the shared
// internalClient (traced transport).
func (d *diaryCrypto) destroyUserDEK(ctx context.Context, owner uuid.UUID) error {
	d.forgetUser(owner)
	if d.authBase == "" {
		return fmt.Errorf("no auth base configured — cannot crypto-shred the diary DEK for %s", owner)
	}
	url := fmt.Sprintf("%s/internal/users/%s/dek", d.authBase, owner.String())
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, url, nil)
	if err != nil {
		return fmt.Errorf("build DEK-shred request: %w", err)
	}
	req.Header.Set("X-Internal-Token", d.token)
	resp, err := internalClient.Do(req)
	if err != nil {
		return fmt.Errorf("auth DEK-shred unreachable for %s: %w", owner, err)
	}
	defer resp.Body.Close()
	// 204 (shredded or already-absent) is success; anything else means the key may survive.
	if resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusOK {
		return fmt.Errorf("auth DEK-shred returned %d for %s", resp.StatusCode, owner)
	}
	return nil
}

// diaryWordCount mirrors the DB's fn_word_count_for_text (cold-review LOW-6): CJK text char-counts
// (excluding whitespace/punctuation) because it has no word spaces, and Latin/other text counts
// whitespace-separated tokens. The block-extraction trigger derives word_count from chapter_blocks,
// which is EMPTY for an encrypted diary, so the writer computes it here — and it must match the DB
// heuristic so an encrypted CJK diary doesn't report ~3 words where a plaintext one reports ~500.
func diaryWordCount(plaintext string) int {
	hasCJK := false
	for _, r := range plaintext {
		// CJK ideographs/kana/hangul + fullwidth forms — the same ranges the DB regex class covers.
		if (r >= 0x3000 && r <= 0x9FFF) || (r >= 0xAC00 && r <= 0xD7AF) || (r >= 0xF900 && r <= 0xFAFF) || (r >= 0xFF00 && r <= 0xFFEF) {
			hasCJK = true
			break
		}
	}
	if hasCJK {
		n := 0
		for _, r := range plaintext {
			if !unicode.IsSpace(r) && !unicode.IsPunct(r) {
				n++
			}
		}
		return n
	}
	return len(strings.Fields(plaintext))
}

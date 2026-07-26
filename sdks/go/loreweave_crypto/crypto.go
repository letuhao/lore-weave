// Package loreweavecrypto is the Go port of sdks/python/loreweave_crypto (WS-1.0 / C5): envelope
// encryption for per-user private content, BYTE-FOR-BYTE format-compatible with the Python SDK and
// with auth-service's existing wrap.
//
// Format (one shape across the platform, matching the usage_logs precedent):
//
//	base64( nonce[12] || AES-256-GCM(ciphertext || tag) )
//
//   - key material → key: SHA-256(secret), never pad/truncate (a short env value silently truncated
//     to a weak key is the classic footgun).
//   - wrap AAD (binds a wrapped DEK to its owner):   "loreweave-dek-wrap\x00" + user_id
//   - content AAD (binds a ciphertext to a row):     "loreweave-content\x00" + aad
//   - key_ref: first 16 hex of SHA-256("loreweave-kek-ref\x00" + key) — a non-secret fingerprint.
//
// A DEK wrapped by auth-service (Go) or a Python service unwraps here; content encrypted here
// decrypts in Python. The golden-vector test pins that parity (a drift would make one side's
// ciphertext unreadable by the other — a silent data-loss class).
//
// WHAT THIS BUYS: a stolen DB dump / backup / a curious DBA's SELECT * → protected. An operator who
// controls the running server (can read the DEK from memory) → NOT protected. A server-side AI
// pipeline must see plaintext; that is physics, not laziness. Do not let the copy over-claim.
package loreweavecrypto

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"strings"
)

const (
	nonceLen = 12
	keyLen   = 32
)

// ErrCrypto wraps every wrap/unwrap/encrypt/decrypt failure. Deliberately its own sentinel (not a
// generic error) so a caller cannot accidentally swallow a decryption failure in a broad catch — a
// failed decrypt means tampering or the wrong key, never something to paper over with a default.
var ErrCrypto = errors.New("loreweave_crypto")

// DeriveKey turns configured key material into a 32-byte AES key via SHA-256. Matches
// loreweave_crypto._coerce_key. Empty material is an error (fail closed), never a zero key.
func DeriveKey(raw string) ([]byte, error) {
	if raw == "" {
		return nil, fmt.Errorf("%w: empty key material", ErrCrypto)
	}
	sum := sha256.Sum256([]byte(raw))
	return sum[:], nil
}

// KeyRef is a NON-SECRET 16-hex fingerprint of a KEK, stored beside a wrapped DEK so an operator can
// see which key wrapped a row. Matches loreweave_crypto.key_ref byte-for-byte.
func KeyRef(key []byte) string {
	h := sha256.New()
	h.Write([]byte("loreweave-kek-ref"))
	h.Write([]byte{0})
	h.Write(key)
	return hex.EncodeToString(h.Sum(nil))[:16]
}

// Keyring is the deployment's KEK set: an ACTIVE key (wraps every new DEK) plus RETIRED keys tried on
// the READ path only, so a KEK rotation does not orphan existing users' DEKs (and therefore their
// whole diary). Rotating without a retired keyring is a data-loss event.
type Keyring struct {
	active    []byte
	activeRef string
	retired   [][]byte
}

// NewKeyring builds a Keyring from raw 32-byte keys (already SHA-256-derived).
func NewKeyring(active []byte, retired ...[]byte) Keyring {
	return Keyring{active: active, activeRef: KeyRef(active), retired: retired}
}

// KeyringFromEnv builds from env: the active key (required — FAILS CLOSED so a service never silently
// starts with encryption off) and comma-separated retired keys. Each retired entry is STRIPPED before
// derivation (a stray space after a comma would derive SHA256(" old") — a key that unwraps nothing,
// bricking every user still on that KEK at rotation time). The active var must never be JWT_SECRET.
func KeyringFromEnv(activeVar, retiredVar string) (Keyring, error) {
	raw := os.Getenv(activeVar)
	if raw == "" {
		return Keyring{}, fmt.Errorf(
			"%w: %s is not set — private user content cannot be stored; refusing to run rather than "+
				"silently writing plaintext", ErrCrypto, activeVar)
	}
	active, err := DeriveKey(raw)
	if err != nil {
		return Keyring{}, err
	}
	var retired [][]byte
	for _, part := range strings.Split(os.Getenv(retiredVar), ",") {
		if s := strings.TrimSpace(part); s != "" {
			k, derr := DeriveKey(s)
			if derr != nil {
				return Keyring{}, derr
			}
			retired = append(retired, k)
		}
	}
	return NewKeyring(active, retired...), nil
}

// ActiveRef is the fingerprint of the active KEK (stored beside each new wrapped DEK).
func (r Keyring) ActiveRef() string { return r.activeRef }

func (r Keyring) allForRead() [][]byte {
	out := make([][]byte, 0, 1+len(r.retired))
	out = append(out, r.active)
	out = append(out, r.retired...)
	return out
}

// NewDEK generates a random 32-byte per-user data key.
func NewDEK() ([]byte, error) {
	dek := make([]byte, keyLen)
	if _, err := rand.Read(dek); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrCrypto, err)
	}
	return dek, nil
}

func wrapAAD(userID string) []byte {
	if userID == "" {
		return nil
	}
	return append([]byte("loreweave-dek-wrap\x00"), []byte(userID)...)
}

func contentAAD(aad string) []byte {
	if aad == "" {
		return nil
	}
	return append([]byte("loreweave-content\x00"), []byte(aad)...)
}

func sealBytes(key, plain, aad []byte) (string, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", fmt.Errorf("%w: %v", ErrCrypto, err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", fmt.Errorf("%w: %v", ErrCrypto, err)
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return "", fmt.Errorf("%w: %v", ErrCrypto, err)
	}
	return base64.StdEncoding.EncodeToString(gcm.Seal(nonce, nonce, plain, aad)), nil
}

func unsealBytes(key []byte, blob string, aad []byte) ([]byte, error) {
	raw, err := base64.StdEncoding.DecodeString(blob)
	if err != nil {
		return nil, fmt.Errorf("%w: ciphertext is not valid base64", ErrCrypto)
	}
	if len(raw) <= nonceLen {
		return nil, fmt.Errorf("%w: ciphertext too short", ErrCrypto)
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrCrypto, err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrCrypto, err)
	}
	pt, err := gcm.Open(nil, raw[:nonceLen], raw[nonceLen:], aad)
	if err != nil {
		return nil, fmt.Errorf("%w: decryption failed (wrong key, wrong AAD, or tampered ciphertext)", ErrCrypto)
	}
	return pt, nil
}

// WrapDEK wraps a user's DEK under the active KEK, BOUND to userID (AAD). Returns (wrappedB64, keyRef).
func WrapDEK(ring Keyring, dek []byte, userID string) (wrapped, keyRef string, err error) {
	if len(dek) != keyLen {
		return "", "", fmt.Errorf("%w: dek must be %d bytes, got %d", ErrCrypto, keyLen, len(dek))
	}
	w, err := sealBytes(ring.active, dek, wrapAAD(userID))
	if err != nil {
		return "", "", err
	}
	return w, ring.activeRef, nil
}

// UnwrapDEK unwraps a user's DEK, trying the active KEK then each retired one (what makes rotation
// safe). AES-GCM is authenticated, so a wrong key — or a wrapped DEK belonging to a DIFFERENT user
// (wrong AAD) — fails cleanly rather than yielding garbage.
func UnwrapDEK(ring Keyring, wrapped, userID string) ([]byte, error) {
	aad := wrapAAD(userID)
	var last error
	for _, kek := range ring.allForRead() {
		dek, err := unsealBytes(kek, wrapped, aad)
		if err == nil {
			if len(dek) != keyLen {
				return nil, fmt.Errorf("%w: unwrapped dek has the wrong length", ErrCrypto)
			}
			return dek, nil
		}
		last = err
	}
	return nil, fmt.Errorf("%w: could not unwrap the DEK with any configured KEK. If a KEK was "+
		"rotated, the previous value MUST be in the retired keyring; a moved row fails the AAD binding: %v",
		ErrCrypto, last)
}

// Encrypt encrypts user content under their DEK. Optional aad binds the ciphertext to a row identity
// (e.g. "chapter:<id>"), so a DB-write adversary cannot move a ciphertext between rows and have it
// still decrypt. Returns base64(nonce || ct).
func Encrypt(dek []byte, plaintext, aad string) (string, error) {
	if len(dek) != keyLen {
		return "", fmt.Errorf("%w: dek must be %d bytes, got %d", ErrCrypto, keyLen, len(dek))
	}
	return sealBytes(dek, []byte(plaintext), contentAAD(aad))
}

// Decrypt decrypts user content. Fails on a wrong key, a wrong AAD, OR any tampering — AES-GCM is
// authenticated, so a modified or moved row is detected, not silently returned. aad must match Encrypt.
func Decrypt(dek []byte, ciphertext, aad string) (string, error) {
	if len(dek) != keyLen {
		return "", fmt.Errorf("%w: dek must be %d bytes, got %d", ErrCrypto, keyLen, len(dek))
	}
	pt, err := unsealBytes(dek, ciphertext, contentAAD(aad))
	if err != nil {
		return "", err
	}
	return string(pt), nil
}

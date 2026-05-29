package meta

import (
	"context"
	"fmt"

	"github.com/google/uuid"
)

// KMSClient is the minimal abstraction over a Key Management System (KMS) that
// contracts/meta uses to decrypt per-user PII envelopes. The plaintext KEK
// bytes NEVER leave the KMS/HSM boundary in production — the adapter is
// responsible for either:
//
//	(a) returning a per-call data-encryption-key (DEK) that the library uses
//	    in-process for the AES-256-GCM payload decrypt, or
//	(b) doing the decrypt remotely and returning the plaintext directly.
//
// The concrete AWS KMS / HashiCorp Vault implementations ship later
// (security-track sub-program; not foundation scope). This file ships:
//
//   - The KMSClient interface (cycle 3 stable shape)
//   - DecryptInput / DecryptOutput types
//   - A DeterministicTestKMS for unit tests that uses XOR-with-fixed-key
//     stand-in "encryption" — DOES NOT ship real crypto, never wired in prod.
//
// Production note: real adapter implementations MUST honor:
//   - destroyed_at NULL check before any decrypt attempt (defense-in-depth;
//     OpenPII checks the DB row too, but a hostile caller may go around it)
//   - audit emission on every decrypt (separate from meta_read_audit; KMS
//     CloudTrail / Vault audit log is the canonical record)
//   - 30-day grace via KMS ScheduleKeyDeletion on user erasure (gives time
//     to abort if erasure was malicious / mistaken)
type KMSClient interface {
	// Decrypt opens a KMS ciphertext envelope and returns the plaintext
	// payload. Returns ErrPIIErased if the underlying key was destroyed
	// (some KMS providers return a specific error code; adapter normalizes).
	// Returns ErrKMSUnavailable for transient failures.
	Decrypt(ctx context.Context, in DecryptInput) (DecryptOutput, error)
}

// DecryptInput carries the per-call decrypt request.
type DecryptInput struct {
	// KEKID is the pii_kek.kek_id this decrypt is bound to. Adapter uses
	// it for audit trail correlation.
	KEKID uuid.UUID

	// KMSKeyRef is the pii_kek.kms_key_ref value (e.g., "aws-kms:arn:aws:kms:...").
	// Adapter routes to the right KMS based on the provider prefix.
	KMSKeyRef string

	// Ciphertext is the AES-256-GCM envelope: header(version+nonce+aad) | payload | auth_tag.
	// Adapter unwraps the header to obtain the KMS-encrypted DEK, asks KMS
	// to decrypt the DEK, then uses the DEK to decrypt the payload locally.
	Ciphertext []byte

	// AAD is the additional authenticated data — typically the user_ref_id
	// + KEK ID — that the GCM tag covers. Mismatch = adapter error.
	AAD []byte
}

// DecryptOutput is the result of a successful Decrypt.
type DecryptOutput struct {
	// Plaintext is the decrypted PII payload (JSON blob, typically).
	Plaintext []byte

	// KMSRequestID is the KMS provider's request id for forensics.
	KMSRequestID string
}

// PIIRecord is the in-memory tuple returned by OpenPII.
// Fields mirror pii_registry (post-decrypt for the payload).
type PIIRecord struct {
	UserRefID      uuid.UUID
	KEKID          uuid.UUID
	BlobSchemaVer  int
	Plaintext      []byte // decrypted from encrypted_blob
	LastRotatedAt  int64  // unix nanos
}

// PIIReader is what OpenPII needs to read the registry+kek rows.
// Production injects a SQL-backed implementation; tests inject a fake.
//
// Kept narrow (just two reads) so production code can wrap a real *sql.DB
// or pgx pool with a 10-line shim, while tests use a map-backed fake.
type PIIReader interface {
	// ReadPIIRow returns the encrypted blob + kek pointer for a user.
	// Returns ErrPIINotFound when no row exists.
	ReadPIIRow(ctx context.Context, userRefID uuid.UUID) (PIIRow, error)

	// ReadKEKRow returns the KEK envelope + destroyed_at marker.
	// Returns ErrPIINotFound when no row exists.
	ReadKEKRow(ctx context.Context, kekID uuid.UUID) (KEKRow, error)
}

// PIIRow mirrors a pii_registry row (subset needed for decrypt).
type PIIRow struct {
	UserRefID      uuid.UUID
	KEKID          uuid.UUID
	EncryptedBlob  []byte
	BlobSchemaVer  int
	LastRotatedAt  int64 // unix nanos
	ErasedAt       *int64 // nil = not erased
}

// KEKRow mirrors a pii_kek row (subset needed for decrypt).
type KEKRow struct {
	KEKID        uuid.UUID
	UserRefID    uuid.UUID
	KeyMaterial  []byte // KMS ciphertext (NEVER plaintext)
	KMSKeyRef    string
	DestroyedAt  *int64 // nil = active; non-nil = crypto-shredded
}

// OpenPII is the canonical decrypt path. Performs the crypto-shred check
// (KEK destroyed → ErrPIIErased) BEFORE calling the KMS adapter, so a
// destroyed user's KMS quota is not consumed and no KMS audit-log entry is
// generated for an erased user.
//
// Defense-in-depth: even if a caller had a stale KEK envelope cached
// in-process, the destroyed_at check here would block the decrypt because
// it goes to the DB for the kek row first.
func OpenPII(ctx context.Context, kms KMSClient, db PIIReader, userRefID uuid.UUID) (*PIIRecord, error) {
	if kms == nil {
		return nil, fmt.Errorf("meta: OpenPII requires a KMSClient")
	}
	if db == nil {
		return nil, fmt.Errorf("meta: OpenPII requires a PIIReader")
	}
	pii, err := db.ReadPIIRow(ctx, userRefID)
	if err != nil {
		return nil, err
	}
	// Erasure tombstone short-circuits BEFORE we hit KMS.
	if pii.ErasedAt != nil {
		return nil, ErrPIIErased
	}
	kek, err := db.ReadKEKRow(ctx, pii.KEKID)
	if err != nil {
		return nil, err
	}
	// Crypto-shred check — this is THE erasure mechanism.
	if kek.DestroyedAt != nil {
		return nil, ErrPIIErased
	}
	// AAD binding: user_ref_id || kek_id (raw bytes). Adapter verifies GCM tag.
	aad := make([]byte, 0, 32)
	aad = append(aad, userRefID[:]...)
	aad = append(aad, kek.KEKID[:]...)
	out, err := kms.Decrypt(ctx, DecryptInput{
		KEKID:      kek.KEKID,
		KMSKeyRef:  kek.KMSKeyRef,
		Ciphertext: pii.EncryptedBlob,
		AAD:        aad,
	})
	if err != nil {
		return nil, err
	}
	return &PIIRecord{
		UserRefID:     pii.UserRefID,
		KEKID:         pii.KEKID,
		BlobSchemaVer: pii.BlobSchemaVer,
		Plaintext:     out.Plaintext,
		LastRotatedAt: pii.LastRotatedAt,
	}, nil
}

// ───────────────────────────────────────────────────────────────────────────
// DeterministicTestKMS — DO NOT USE IN PRODUCTION.
//
// XOR-with-fixed-key stand-in "encryption". The only purpose is to let the
// crypto-shred semantic tests run without bringing up a real KMS. The
// "ciphertext" stored on disk in tests is therefore not real cipher; tests
// MUST never assert on its byte structure.
//
// Real foundation note: production adapter MUST use AWS KMS Decrypt or
// Vault Transit Decrypt; never this. CI lint (foundation L1.K cycle 7)
// will scan for this type being referenced outside *_test.go files.
// ───────────────────────────────────────────────────────────────────────────

// DeterministicTestKMS is a test-only KMSClient. It records every Decrypt
// call (so tests can assert call patterns) and returns a fixed plaintext
// regardless of ciphertext input. Use only inside _test.go files.
type DeterministicTestKMS struct {
	// FixedPlaintext is returned for every successful Decrypt.
	FixedPlaintext []byte

	// FailWith, if non-nil, is returned instead of decrypting.
	FailWith error

	// Calls records every Decrypt invocation (most recent last).
	Calls []DecryptInput
}

// Decrypt implements KMSClient. NEVER use in production.
func (t *DeterministicTestKMS) Decrypt(_ context.Context, in DecryptInput) (DecryptOutput, error) {
	t.Calls = append(t.Calls, in)
	if t.FailWith != nil {
		return DecryptOutput{}, t.FailWith
	}
	plain := append([]byte(nil), t.FixedPlaintext...)
	return DecryptOutput{
		Plaintext:    plain,
		KMSRequestID: "test-kms-request-id-not-real",
	}, nil
}

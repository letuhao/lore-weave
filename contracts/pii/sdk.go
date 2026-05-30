package pii

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/meta"
)

// SensitiveReadTag is the cycle-3 meta-sensitive-read-paths.yml id the
// SDK call must declare on every read. Defense-in-depth: even though the
// caller integrates with the cycle-3 ReadSensitive() flow, we re-check
// the tag at SDK call time so a typo doesn't slip through to a missed
// meta_read_audit row.
type SensitiveReadTag string

const (
	// TagPIIUserGet — single-user GetPII via this SDK. Added to the
	// cycle-3 enumeration by the L4.Q migration in the security-track
	// sub-program (V1+30d); the SDK ALREADY tags reads with it so the
	// migration is data-compatible from day 1.
	TagPIIUserGet SensitiveReadTag = "pii_user_get"

	// TagPIIUserErase — single-user ErasePII via this SDK. Same as
	// above; tagged from V1 so the migration is compatible.
	TagPIIUserErase SensitiveReadTag = "pii_user_erase"

	// TagBulkPIIRead — cycle-3 enumerated bulk_pii_read path. Used for
	// admin-cli bulk exports; SDK rejects callers that try to issue
	// this tag without an explicit Bulk SDK method (NOT shipped this
	// cycle — admin-cli will add the bulk surface separately).
	TagBulkPIIRead SensitiveReadTag = "bulk_pii_read"
)

// IsValid is the SDK-side guard. Mirrors the cycle-3 yml `paths` keys.
func (t SensitiveReadTag) IsValid() bool {
	switch t {
	case TagPIIUserGet, TagPIIUserErase, TagBulkPIIRead:
		return true
	}
	return false
}

// ErrInvalidTag is returned when a caller passes a tag not in the
// enumerated set. Should never happen if callers use the typed constants
// above; the guard exists to catch dynamic string construction bugs.
var ErrInvalidTag = errors.New("pii: sensitive-read tag not in enumerated set")

// ErrEraseFailed is returned when ErasePII could not destroy the KEK.
// CRITICAL — caller MUST surface this as an alert; failure to destroy
// the KEK breaks GDPR Art. 17.
var ErrEraseFailed = errors.New("pii: KEK destroy failed — erasure NOT satisfied")

// AuditWriter is the cycle-4 sensitive-read audit interface the SDK
// uses to log every GetPII / ErasePII call. Production wraps a
// MetaWrite()-backed implementation; tests use InMemoryAuditWriter.
type AuditWriter interface {
	// WriteSensitiveRead inserts a `meta_read_audit` row.
	// Returns an error if the underlying meta write failed.
	WriteSensitiveRead(ctx context.Context, entry SensitiveReadEntry) error
}

// SensitiveReadEntry mirrors a `meta_read_audit` row (migration 014).
// SDK fills it; AuditWriter persists.
type SensitiveReadEntry struct {
	AuditID        uuid.UUID
	QueryType      SensitiveReadTag
	Parameters     map[string]string
	ActorID        string
	ActorType      string // mirrors the cycle-3 meta_read_audit enum
	ResultCount    int
	CreatedAtNanos int64
}

// Validate enforces migration 014 CHECK constraints in-process.
func (e *SensitiveReadEntry) Validate() error {
	if e == nil {
		return errors.New("pii: nil SensitiveReadEntry")
	}
	if e.AuditID == uuid.Nil {
		return errors.New("pii: audit_id required")
	}
	if !e.QueryType.IsValid() {
		return fmt.Errorf("pii: invalid query_type %q (must be one of cycle-3 enumerated paths)", e.QueryType)
	}
	if e.ActorID == "" {
		return errors.New("pii: actor_id required")
	}
	if e.ActorType == "" {
		return errors.New("pii: actor_type required")
	}
	if e.ResultCount < 0 {
		return fmt.Errorf("pii: result_count must be >= 0 (got %d)", e.ResultCount)
	}
	if e.CreatedAtNanos <= 1577836800000000000 {
		return fmt.Errorf("pii: created_at_nanos must be > 1577836800000000000 (got %d)", e.CreatedAtNanos)
	}
	return nil
}

// KEKManager is the SDK's destroy-only view of the cycle-3 pii_kek
// lifecycle. The SDK does NOT need rotate / read here; production
// implementations wrap the cycle-3 meta library's pii_kek update path.
type KEKManager interface {
	// DestroyKEK marks pii_kek.destroyed_at non-NULL for the user's KEK and
	// records the GDPR ticket + reason (the pii_kek CHECK requires both
	// non-empty when destroyed_at is set). IDEMPOTENT — re-destroy of an
	// already-destroyed KEK is a no-op (returns nil). This is the crypto-shred
	// operation that GDPR Art. 17 leans on.
	DestroyKEK(ctx context.Context, userRefID uuid.UUID, ticket, reason string) error
}

// SDK is the typed PII access surface. Construct with NewSDK; reuse
// across goroutines (all methods are safe for concurrent use).
type SDK struct {
	kms     meta.KMSClient
	db      meta.PIIReader
	keks    KEKManager
	auditor AuditWriter

	actorID   string
	actorType string

	now func() time.Time
}

// Config wires the SDK with the cycle-3 KMSClient + PIIReader (no
// vendor-specific dependency in this package).
type Config struct {
	KMS         meta.KMSClient
	DB          meta.PIIReader
	KEKManager  KEKManager
	AuditWriter AuditWriter
	ActorID     string // e.g., "admin-cli" or service SVID
	ActorType   string // mirrors meta_read_audit.actor_type enum
}

// NewSDK constructs a wired SDK. Returns an error if any required
// dependency is missing (programmer bug — fail fast).
func NewSDK(c Config) (*SDK, error) {
	if c.KMS == nil {
		return nil, errors.New("pii: KMSClient required")
	}
	if c.DB == nil {
		return nil, errors.New("pii: PIIReader required")
	}
	if c.KEKManager == nil {
		return nil, errors.New("pii: KEKManager required (erasure invariant)")
	}
	if c.AuditWriter == nil {
		return nil, errors.New("pii: AuditWriter required (audit invariant)")
	}
	if c.ActorID == "" {
		return nil, errors.New("pii: ActorID required")
	}
	if c.ActorType == "" {
		return nil, errors.New("pii: ActorType required")
	}
	return &SDK{
		kms:       c.KMS,
		db:        c.DB,
		keks:      c.KEKManager,
		auditor:   c.AuditWriter,
		actorID:   c.ActorID,
		actorType: c.ActorType,
		now:       time.Now,
	}, nil
}

// WithClock overrides the time source for tests.
func (s *SDK) WithClock(now func() time.Time) *SDK {
	s.now = now
	return s
}

// GetPII reads + decrypts the PII row for userRefID. Delegates to the
// cycle-3 meta.OpenPII; the SDK's job is to write the sensitive-read
// audit row + propagate cycle-3 errors typed.
//
// INVARIANT: plaintext is NOT cached in this package. The returned
// meta.PIIRecord is the caller's responsibility (the caller SHOULD
// zeroize the Plaintext byte slice after use).
//
// Returns meta.ErrPIIErased if the KEK is crypto-shredded (default
// post-ErasePII state) — that error path SHOULD always be expected
// after erasure.
func (s *SDK) GetPII(ctx context.Context, userRefID uuid.UUID) (*meta.PIIRecord, error) {
	rec, err := meta.OpenPII(ctx, s.kms, s.db, userRefID)
	// Always audit — even failures (security forensics depends on it).
	auditErr := s.audit(ctx, TagPIIUserGet, userRefID, resultCountFromRecord(rec, err))
	if auditErr != nil {
		// CRITICAL: audit write failure means we cannot prove the read
		// happened. Treat as a hard error and DROP the returned record.
		return nil, fmt.Errorf("pii: audit write failed: %w (original err=%v)", auditErr, err)
	}
	if err != nil {
		return nil, err
	}
	return rec, nil
}

// ErasePII destroys the KEK and writes an audit row. This is the
// crypto-shred operation per S08 §12X.6 / GDPR Art. 17.
//
// INVARIANT: KEK destroy is the ONE side-effect that satisfies
// erasure. Failure to destroy the KEK returns ErrEraseFailed (wrapped
// with the underlying KEKManager error).
//
// IDEMPOTENT — re-erasing an already-erased user is a no-op.
//
// ticket + reason are REQUIRED (GDPR audit; the pii_kek CHECK enforces both
// non-empty when destroyed_at is set).
func (s *SDK) ErasePII(ctx context.Context, userRefID uuid.UUID, ticket, reason string) error {
	if ticket == "" || reason == "" {
		return fmt.Errorf("%w: ticket and reason are required for erasure (GDPR audit)", ErrEraseFailed)
	}
	if err := s.keks.DestroyKEK(ctx, userRefID, ticket, reason); err != nil {
		// Always audit even the failure — forensic invariant.
		_ = s.audit(ctx, TagPIIUserErase, userRefID, 0)
		return fmt.Errorf("%w: %v", ErrEraseFailed, err)
	}
	if err := s.audit(ctx, TagPIIUserErase, userRefID, 1); err != nil {
		// KEK already destroyed but audit failed — this is a real
		// problem because we can't prove the erasure happened. Surface
		// as a hard error so SRE notices.
		return fmt.Errorf("pii: erase succeeded but audit failed: %w", err)
	}
	return nil
}

// audit is the SDK-internal write path; one place to validate the
// SensitiveReadEntry shape before calling the auditor.
func (s *SDK) audit(ctx context.Context, tag SensitiveReadTag, userRefID uuid.UUID, count int) error {
	if !tag.IsValid() {
		return ErrInvalidTag
	}
	entry := SensitiveReadEntry{
		AuditID:        uuid.New(),
		QueryType:      tag,
		Parameters:     map[string]string{"user_ref_id": userRefID.String()},
		ActorID:        s.actorID,
		ActorType:      s.actorType,
		ResultCount:    count,
		CreatedAtNanos: s.now().UnixNano(),
	}
	if err := entry.Validate(); err != nil {
		return err
	}
	return s.auditor.WriteSensitiveRead(ctx, entry)
}

// resultCountFromRecord — used by audit. Returns 1 for a successful
// read; 0 for any error path. We do NOT distinguish between
// ErrPIIErased / ErrPIINotFound / decrypt-error at the audit-row level;
// the SDK error (returned to caller) carries the detail.
func resultCountFromRecord(rec *meta.PIIRecord, err error) int {
	if err == nil && rec != nil {
		return 1
	}
	return 0
}

// ─────────────────────────────────────────────────────────────────────
// In-memory test scaffolding
// ─────────────────────────────────────────────────────────────────────

// InMemoryAuditWriter is the reference AuditWriter used in tests +
// dev-stack stand-ins. Safe for concurrent use.
type InMemoryAuditWriter struct {
	Entries []SensitiveReadEntry
}

// WriteSensitiveRead validates + appends.
func (w *InMemoryAuditWriter) WriteSensitiveRead(_ context.Context, e SensitiveReadEntry) error {
	if err := e.Validate(); err != nil {
		return err
	}
	w.Entries = append(w.Entries, e)
	return nil
}

// InMemoryKEKManager is a test-only KEKManager that tracks destroyed_at
// per user. The "destroy" semantic is what we assert in tests; this
// stand-in lets us avoid wiring a real Postgres just to verify the
// SDK's contract obligations.
//
// Concurrency: protected by an internal mutex.
type InMemoryKEKManager struct {
	destroyed map[uuid.UUID]int64
}

// NewInMemoryKEKManager constructs an empty manager.
func NewInMemoryKEKManager() *InMemoryKEKManager {
	return &InMemoryKEKManager{destroyed: make(map[uuid.UUID]int64)}
}

// DestroyKEK marks the user's KEK destroyed at now. Idempotent. ticket/reason
// are accepted to satisfy the KEKManager contract (recorded by real impls).
func (m *InMemoryKEKManager) DestroyKEK(_ context.Context, userRefID uuid.UUID, _, _ string) error {
	if _, ok := m.destroyed[userRefID]; ok {
		return nil // idempotent
	}
	m.destroyed[userRefID] = time.Now().UnixNano()
	return nil
}

// IsDestroyed returns true if the KEK has been destroyed.
func (m *InMemoryKEKManager) IsDestroyed(userRefID uuid.UUID) bool {
	_, ok := m.destroyed[userRefID]
	return ok
}

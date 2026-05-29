package pii

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/meta"
)

// fakePIIReader is a map-backed PIIReader for SDK tests (mirrors
// contracts/meta test pattern so we exercise the same crypto-shred
// semantics the cycle-3 lib enforces).
type fakePIIReader struct {
	pii map[uuid.UUID]meta.PIIRow
	kek map[uuid.UUID]meta.KEKRow
}

func newFakePIIReader() *fakePIIReader {
	return &fakePIIReader{
		pii: make(map[uuid.UUID]meta.PIIRow),
		kek: make(map[uuid.UUID]meta.KEKRow),
	}
}

func (f *fakePIIReader) ReadPIIRow(_ context.Context, u uuid.UUID) (meta.PIIRow, error) {
	r, ok := f.pii[u]
	if !ok {
		return meta.PIIRow{}, meta.ErrPIINotFound
	}
	return r, nil
}

func (f *fakePIIReader) ReadKEKRow(_ context.Context, k uuid.UUID) (meta.KEKRow, error) {
	r, ok := f.kek[k]
	if !ok {
		return meta.KEKRow{}, meta.ErrPIINotFound
	}
	return r, nil
}

func seedHappyUser(t *testing.T, db *fakePIIReader) (uuid.UUID, uuid.UUID) {
	t.Helper()
	uid := uuid.New()
	kekID := uuid.New()
	db.pii[uid] = meta.PIIRow{
		UserRefID:     uid,
		KEKID:         kekID,
		EncryptedBlob: []byte("ciphertext-stand-in"),
		BlobSchemaVer: 1,
		LastRotatedAt: 1700000000000000000,
	}
	db.kek[kekID] = meta.KEKRow{
		KEKID:       kekID,
		UserRefID:   uid,
		KeyMaterial: []byte("kms-encrypted"),
		KMSKeyRef:   "test-kms:key-1",
	}
	return uid, kekID
}

func wireSDK(t *testing.T) (*SDK, *fakePIIReader, *meta.DeterministicTestKMS, *InMemoryAuditWriter, *InMemoryKEKManager) {
	t.Helper()
	db := newFakePIIReader()
	kms := &meta.DeterministicTestKMS{FixedPlaintext: []byte(`{"email":"alice@example.com"}`)}
	auditor := &InMemoryAuditWriter{}
	keks := NewInMemoryKEKManager()
	sdk, err := NewSDK(Config{
		KMS: kms, DB: db, KEKManager: keks, AuditWriter: auditor,
		ActorID: "test-actor", ActorType: "service",
	})
	if err != nil {
		t.Fatalf("NewSDK: %v", err)
	}
	sdk = sdk.WithClock(func() time.Time { return time.Unix(0, 1700000000000000000) })
	return sdk, db, kms, auditor, keks
}

// ─────────────────────────────────────────────────────────────────────
// Construction
// ─────────────────────────────────────────────────────────────────────

func TestNewSDK_RejectsMissingDeps(t *testing.T) {
	kms := &meta.DeterministicTestKMS{}
	db := newFakePIIReader()
	keks := NewInMemoryKEKManager()
	auditor := &InMemoryAuditWriter{}
	cases := map[string]Config{
		"missing KMS":       {DB: db, KEKManager: keks, AuditWriter: auditor, ActorID: "a", ActorType: "s"},
		"missing DB":        {KMS: kms, KEKManager: keks, AuditWriter: auditor, ActorID: "a", ActorType: "s"},
		"missing KEKMgr":    {KMS: kms, DB: db, AuditWriter: auditor, ActorID: "a", ActorType: "s"},
		"missing Auditor":   {KMS: kms, DB: db, KEKManager: keks, ActorID: "a", ActorType: "s"},
		"missing ActorID":   {KMS: kms, DB: db, KEKManager: keks, AuditWriter: auditor, ActorType: "s"},
		"missing ActorType": {KMS: kms, DB: db, KEKManager: keks, AuditWriter: auditor, ActorID: "a"},
	}
	for name, c := range cases {
		t.Run(name, func(t *testing.T) {
			_, err := NewSDK(c)
			if err == nil {
				t.Fatalf("%s: NewSDK must reject", name)
			}
		})
	}
}

// ─────────────────────────────────────────────────────────────────────
// GetPII — happy + audit + crypto-shred semantics
// ─────────────────────────────────────────────────────────────────────

func TestGetPII_HappyPath(t *testing.T) {
	sdk, db, kms, auditor, _ := wireSDK(t)
	uid, _ := seedHappyUser(t, db)

	rec, err := sdk.GetPII(context.Background(), uid)
	if err != nil {
		t.Fatalf("GetPII: %v", err)
	}
	if string(rec.Plaintext) != `{"email":"alice@example.com"}` {
		t.Fatalf("plaintext: %s", rec.Plaintext)
	}
	// KMS was called exactly once.
	if len(kms.Calls) != 1 {
		t.Fatalf("KMS call count: %d", len(kms.Calls))
	}
	// Audit row written with TagPIIUserGet + result_count=1.
	if len(auditor.Entries) != 1 {
		t.Fatalf("audit entries: %d", len(auditor.Entries))
	}
	got := auditor.Entries[0]
	if got.QueryType != TagPIIUserGet {
		t.Fatalf("audit tag: %s", got.QueryType)
	}
	if got.ResultCount != 1 {
		t.Fatalf("audit result_count: %d", got.ResultCount)
	}
	if got.ActorID != "test-actor" {
		t.Fatalf("audit actor_id: %s", got.ActorID)
	}
	if got.Parameters["user_ref_id"] != uid.String() {
		t.Fatalf("audit param user_ref_id: %s", got.Parameters["user_ref_id"])
	}
}

func TestGetPII_AuditOnErasedUser(t *testing.T) {
	sdk, db, _, auditor, _ := wireSDK(t)
	uid, kekID := seedHappyUser(t, db)
	// Crypto-shred: mark KEK destroyed.
	tomb := int64(1700000001000000000)
	kek := db.kek[kekID]
	kek.DestroyedAt = &tomb
	db.kek[kekID] = kek

	rec, err := sdk.GetPII(context.Background(), uid)
	if !errors.Is(err, meta.ErrPIIErased) {
		t.Fatalf("expected ErrPIIErased, got %v", err)
	}
	if rec != nil {
		t.Fatal("rec must be nil on erased")
	}
	// Audit row STILL written for forensics.
	if len(auditor.Entries) != 1 {
		t.Fatalf("audit entries: %d", len(auditor.Entries))
	}
	if auditor.Entries[0].ResultCount != 0 {
		t.Fatalf("erased read must audit result_count=0, got %d", auditor.Entries[0].ResultCount)
	}
}

func TestGetPII_NeverCachesPlaintext(t *testing.T) {
	// INVARIANT: the SDK MUST NOT retain plaintext between calls. Two
	// successive GetPII calls must each hit KMS — proving no cache
	// short-circuit.
	sdk, db, kms, _, _ := wireSDK(t)
	uid, _ := seedHappyUser(t, db)
	if _, err := sdk.GetPII(context.Background(), uid); err != nil {
		t.Fatalf("first GetPII: %v", err)
	}
	if _, err := sdk.GetPII(context.Background(), uid); err != nil {
		t.Fatalf("second GetPII: %v", err)
	}
	if len(kms.Calls) != 2 {
		t.Fatalf("KMS hit count must be 2 (no cache), got %d", len(kms.Calls))
	}
}

func TestGetPII_AuditWriteFailureDropsPlaintext(t *testing.T) {
	// SECURITY: if the audit write fails, we MUST NOT return plaintext
	// (the read is not provably auditable). This is the "no audit, no
	// read" invariant the SDK enforces on top of cycle-3 OpenPII.
	db := newFakePIIReader()
	uid, _ := seedHappyUser(t, db)
	kms := &meta.DeterministicTestKMS{FixedPlaintext: []byte(`{"email":"x"}`)}
	failAuditor := failingAuditor{}
	keks := NewInMemoryKEKManager()
	sdk, err := NewSDK(Config{
		KMS: kms, DB: db, KEKManager: keks, AuditWriter: failAuditor,
		ActorID: "x", ActorType: "service",
	})
	if err != nil {
		t.Fatalf("NewSDK: %v", err)
	}
	rec, err := sdk.GetPII(context.Background(), uid)
	if err == nil {
		t.Fatal("audit failure must propagate")
	}
	if rec != nil {
		t.Fatal("plaintext MUST NOT be returned on audit failure")
	}
	if !strings.Contains(err.Error(), "audit write failed") {
		t.Fatalf("expected audit-failure error, got %v", err)
	}
}

type failingAuditor struct{}

func (failingAuditor) WriteSensitiveRead(_ context.Context, _ SensitiveReadEntry) error {
	return errors.New("audit-down")
}

// ─────────────────────────────────────────────────────────────────────
// ErasePII — actually destroys KEK + audits
// ─────────────────────────────────────────────────────────────────────

func TestErasePII_DestroysKEK(t *testing.T) {
	sdk, db, _, auditor, keks := wireSDK(t)
	uid, _ := seedHappyUser(t, db)

	if keks.IsDestroyed(uid) {
		t.Fatal("pre-erase: KEK must not be destroyed")
	}
	if err := sdk.ErasePII(context.Background(), uid); err != nil {
		t.Fatalf("ErasePII: %v", err)
	}
	if !keks.IsDestroyed(uid) {
		t.Fatal("post-erase: KEK MUST be destroyed (GDPR Art. 17 invariant)")
	}
	if len(auditor.Entries) != 1 {
		t.Fatalf("audit entries: %d", len(auditor.Entries))
	}
	got := auditor.Entries[0]
	if got.QueryType != TagPIIUserErase {
		t.Fatalf("audit tag: %s", got.QueryType)
	}
	if got.ResultCount != 1 {
		t.Fatalf("audit result_count: %d", got.ResultCount)
	}
}

func TestErasePII_Idempotent(t *testing.T) {
	sdk, db, _, _, keks := wireSDK(t)
	uid, _ := seedHappyUser(t, db)
	if err := sdk.ErasePII(context.Background(), uid); err != nil {
		t.Fatalf("first erase: %v", err)
	}
	if err := sdk.ErasePII(context.Background(), uid); err != nil {
		t.Fatalf("second erase must be idempotent, got %v", err)
	}
	if !keks.IsDestroyed(uid) {
		t.Fatal("KEK destroyed state must survive double-erase")
	}
}

type failingKEKManager struct{}

func (failingKEKManager) DestroyKEK(_ context.Context, _ uuid.UUID) error {
	return errors.New("kms-down")
}

func TestErasePII_FailureSurfacesErrEraseFailed(t *testing.T) {
	db := newFakePIIReader()
	uid, _ := seedHappyUser(t, db)
	sdk, err := NewSDK(Config{
		KMS: &meta.DeterministicTestKMS{}, DB: db,
		KEKManager: failingKEKManager{}, AuditWriter: &InMemoryAuditWriter{},
		ActorID: "x", ActorType: "service",
	})
	if err != nil {
		t.Fatalf("NewSDK: %v", err)
	}
	err = sdk.ErasePII(context.Background(), uid)
	if !errors.Is(err, ErrEraseFailed) {
		t.Fatalf("expected ErrEraseFailed wrap, got %v", err)
	}
}

func TestErasePII_AuditFailurePostDestroyReturnsHardError(t *testing.T) {
	db := newFakePIIReader()
	uid, _ := seedHappyUser(t, db)
	keks := NewInMemoryKEKManager()
	sdk, err := NewSDK(Config{
		KMS: &meta.DeterministicTestKMS{}, DB: db,
		KEKManager: keks, AuditWriter: failingAuditor{},
		ActorID: "x", ActorType: "service",
	})
	if err != nil {
		t.Fatalf("NewSDK: %v", err)
	}
	err = sdk.ErasePII(context.Background(), uid)
	if err == nil {
		t.Fatal("audit failure post-destroy MUST surface as hard error")
	}
	if !keks.IsDestroyed(uid) {
		t.Fatal("KEK was destroyed even though audit failed (correct)")
	}
}

// ─────────────────────────────────────────────────────────────────────
// SensitiveReadEntry.Validate
// ─────────────────────────────────────────────────────────────────────

func TestSensitiveReadEntry_Validate(t *testing.T) {
	base := SensitiveReadEntry{
		AuditID:        uuid.New(),
		QueryType:      TagPIIUserGet,
		ActorID:        "x",
		ActorType:      "service",
		ResultCount:    1,
		CreatedAtNanos: 1700000000000000000,
	}
	if err := base.Validate(); err != nil {
		t.Fatalf("happy: %v", err)
	}

	cases := map[string]func(*SensitiveReadEntry){
		"zero audit_id":   func(e *SensitiveReadEntry) { e.AuditID = uuid.Nil },
		"invalid tag":     func(e *SensitiveReadEntry) { e.QueryType = "bogus" },
		"empty actor_id":  func(e *SensitiveReadEntry) { e.ActorID = "" },
		"empty actor_type": func(e *SensitiveReadEntry) { e.ActorType = "" },
		"negative count":  func(e *SensitiveReadEntry) { e.ResultCount = -1 },
		"implausible ts":  func(e *SensitiveReadEntry) { e.CreatedAtNanos = 1577836800000000000 },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			e := base
			mutate(&e)
			if err := e.Validate(); err == nil {
				t.Fatalf("%s: must reject", name)
			}
		})
	}
}

func TestSensitiveReadTag_IsValid(t *testing.T) {
	for _, tag := range []SensitiveReadTag{TagPIIUserGet, TagPIIUserErase, TagBulkPIIRead} {
		if !tag.IsValid() {
			t.Errorf("%q must be valid", tag)
		}
	}
	if SensitiveReadTag("bogus").IsValid() {
		t.Fatal("bogus tag must be invalid")
	}
}

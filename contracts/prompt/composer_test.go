package prompt

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

// ── Test helpers ──────────────────────────────────────────────────────

type fakeEncoder struct {
	payload      json.RawMessage
	encodeErr    error
	providerName string
	modelRef     string
	calls        int
	lastRendered []byte
}

func (f *fakeEncoder) Encode(_ context.Context, _ PromptContext, rendered []byte) (json.RawMessage, error) {
	f.calls++
	f.lastRendered = append([]byte(nil), rendered...)
	if f.encodeErr != nil {
		return nil, f.encodeErr
	}
	if f.payload == nil {
		return json.RawMessage(`{"messages":[]}`), nil
	}
	return f.payload, nil
}
func (f *fakeEncoder) ProviderName() string {
	if f.providerName == "" {
		return "anthropic"
	}
	return f.providerName
}
func (f *fakeEncoder) ModelRef() string {
	if f.modelRef == "" {
		return "claude-test"
	}
	return f.modelRef
}

type recordingSafety struct {
	pre, post int
	preErr    error
	postErr   error
}

func (r *recordingSafety) PreAssembly(_ context.Context, _ PromptContext, _ SectionMap) error {
	r.pre++
	return r.preErr
}
func (r *recordingSafety) PostAssembly(_ context.Context, _ PromptContext, _ [32]byte, _ json.RawMessage) error {
	r.post++
	return r.postErr
}

func newComposer(t *testing.T) (*DefaultComposer, *fakeEncoder, *InMemoryAuditWriter) {
	t.Helper()
	enc := &fakeEncoder{}
	aw := &InMemoryAuditWriter{}
	idGen := func() string { return uuid.New().String() }
	now := func() int64 { return time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC).UnixNano() }
	return &DefaultComposer{
		Encoder:    enc,
		Audit:      aw,
		NewAuditID: idGen,
		Now:        now,
	}, enc, aw
}

func validSections() SectionMap {
	return SectionMap{
		SectionSystem:      []byte("you are a roleplay engine"),
		SectionInstruction: []byte("describe the scene"),
		SectionInput:       []byte("the player swings their sword"),
	}
}

func ctxWithSession() PromptContext {
	s := uuid.New()
	return PromptContext{
		RealityID:      uuid.New(),
		SessionID:      &s,
		ActorUserRefID: uuid.New(),
		Intent:         IntentSessionTurn,
	}
}

// ── Happy path ────────────────────────────────────────────────────────

func TestAssemblePrompt_HappyPath(t *testing.T) {
	c, enc, aw := newComposer(t)
	pc := ctxWithSession()
	b, err := c.AssemblePrompt(context.Background(), pc, validSections())
	if err != nil {
		t.Fatalf("AssemblePrompt err = %v; want nil", err)
	}
	if enc.calls != 1 {
		t.Errorf("Encoder.Encode called %d times; want 1", enc.calls)
	}
	if len(aw.Entries) != 1 {
		t.Fatalf("audit entries = %d; want 1", len(aw.Entries))
	}
	if got, want := len(aw.Entries[0].PromptContextHash), 32; got != want {
		t.Errorf("PromptContextHash len = %d; want %d (SHA-256)", got, want)
	}
	if b.ContextHash == ([32]byte{}) {
		t.Errorf("bundle ContextHash is zero")
	}
	if b.PromptAuditID == uuid.Nil {
		t.Errorf("bundle PromptAuditID is zero")
	}
	if b.ProviderName != "anthropic" {
		t.Errorf("ProviderName = %q; want anthropic", b.ProviderName)
	}
	// Audit entry's hash matches bundle hash.
	for i, b1 := range b.ContextHash {
		if aw.Entries[0].PromptContextHash[i] != b1 {
			t.Errorf("audit hash byte %d = %x; want %x (must match bundle ContextHash)", i, aw.Entries[0].PromptContextHash[i], b1)
			break
		}
	}
}

// ── Body-never-stored discipline ──────────────────────────────────────

func TestPromptBundle_NoBodyField(t *testing.T) {
	// Static-shape gate: PromptBundle must not have a Body-shaped field.
	// We assert by JSON marshalling the bundle and checking no "body"
	// / "rendered" / "prompt_text" key appears.
	b := PromptBundle{
		ProviderPayload:  json.RawMessage(`{"x":1}`),
		ContextHash:      [32]byte{1},
		PromptAuditID:    uuid.New(),
		EstimatedCostUSD: "0",
		TemplateID:       "tpl",
		TemplateVersion:  1,
	}
	raw, err := json.Marshal(b)
	if err != nil {
		t.Fatalf("marshal err = %v", err)
	}
	for _, banned := range []string{`"body"`, `"rendered"`, `"prompt_text"`, `"assembled"`} {
		if strings.Contains(string(raw), banned) {
			t.Errorf("PromptBundle JSON carries forbidden field %s — body-never-stored violation", banned)
		}
	}
}

func TestPromptAuditEntry_NoBodyField(t *testing.T) {
	e := PromptAuditEntry{
		AuditID:           uuid.New().String(),
		PromptContextHash: make([]byte, 32),
		TemplateID:        "tpl",
		TemplateVersion:   1,
		Intent:            string(IntentSessionTurn),
		ActorUserRefID:    uuid.New().String(),
		RealityID:         uuid.New().String(),
		CreatedAtNanos:    time.Now().UnixNano(),
	}
	raw, err := json.Marshal(e)
	if err != nil {
		t.Fatalf("marshal err = %v", err)
	}
	for _, banned := range []string{`"body"`, `"rendered"`, `"prompt_text"`, `"assembled"`} {
		if strings.Contains(string(raw), banned) {
			t.Errorf("PromptAuditEntry JSON carries forbidden field %s", banned)
		}
	}
}

// ── Q-L6H-1 (FAIL not best-effort) ─────────────────────────────────────

func TestAssemblePrompt_FailOnMissingSystem(t *testing.T) {
	c, _, aw := newComposer(t)
	pc := ctxWithSession()
	bad := SectionMap{
		SectionInstruction: []byte("describe"),
		SectionInput:       []byte("input"),
	} // no SectionSystem
	b, err := c.AssemblePrompt(context.Background(), pc, bad)
	if err == nil {
		t.Fatalf("AssemblePrompt err = nil; want FAIL on missing SectionSystem")
	}
	if !errors.Is(err, ErrComposerFailed) {
		t.Errorf("err = %v; want wraps ErrComposerFailed", err)
	}
	// Q-L6H-1: no partial bundle on failure.
	if !zeroBundle(b) {
		t.Errorf("AssemblePrompt returned non-zero bundle on failure — Q-L6H-1 violation")
	}
	// Audit must NOT have been written on early-failure path.
	if len(aw.Entries) != 0 {
		t.Errorf("audit entries = %d; want 0 (FAIL before audit)", len(aw.Entries))
	}
}

func TestAssemblePrompt_FailOnUnknownSection(t *testing.T) {
	c, _, _ := newComposer(t)
	pc := ctxWithSession()
	bad := SectionMap{
		SectionSystem: []byte("sys"),
		Section("BOGUS"): []byte("x"),
	}
	b, err := c.AssemblePrompt(context.Background(), pc, bad)
	if err == nil {
		t.Fatalf("err = nil; want FAIL on unknown section")
	}
	if !errors.Is(err, ErrComposerFailed) {
		t.Errorf("err = %v; want ErrComposerFailed", err)
	}
	if !zeroBundle(b) {
		t.Errorf("bundle not zero on FAIL")
	}
}

func TestAssemblePrompt_FailOnEmptySections(t *testing.T) {
	c, _, _ := newComposer(t)
	pc := ctxWithSession()
	_, err := c.AssemblePrompt(context.Background(), pc, SectionMap{})
	if err == nil {
		t.Fatalf("err = nil; want FAIL on empty SectionMap")
	}
	if !errors.Is(err, ErrComposerFailed) {
		t.Errorf("err = %v; want ErrComposerFailed", err)
	}
}

func TestAssemblePrompt_FailOnInvalidContext(t *testing.T) {
	c, _, _ := newComposer(t)
	pc := PromptContext{} // missing reality + actor + intent
	_, err := c.AssemblePrompt(context.Background(), pc, validSections())
	if err == nil || !errors.Is(err, ErrComposerFailed) {
		t.Fatalf("err = %v; want ErrComposerFailed", err)
	}
}

func TestAssemblePrompt_FailOnSafetyPreDenial(t *testing.T) {
	c, _, aw := newComposer(t)
	c.Safety = &recordingSafety{preErr: errors.New("jailbreak phrase detected")}
	pc := ctxWithSession()
	_, err := c.AssemblePrompt(context.Background(), pc, validSections())
	if err == nil || !errors.Is(err, ErrComposerFailed) {
		t.Fatalf("err = %v; want ErrComposerFailed", err)
	}
	// Safety pre denies BEFORE render → no audit row.
	if len(aw.Entries) != 0 {
		t.Errorf("audit entries = %d; want 0 on pre-assembly denial", len(aw.Entries))
	}
}

func TestAssemblePrompt_FailOnSafetyPostDenial(t *testing.T) {
	c, _, aw := newComposer(t)
	c.Safety = &recordingSafety{postErr: errors.New("canary leaked")}
	pc := ctxWithSession()
	_, err := c.AssemblePrompt(context.Background(), pc, validSections())
	if err == nil || !errors.Is(err, ErrComposerFailed) {
		t.Fatalf("err = %v; want ErrComposerFailed", err)
	}
	// Post-assembly denial happens BEFORE the audit write — entry count remains 0.
	if len(aw.Entries) != 0 {
		t.Errorf("audit entries = %d; want 0 on post-assembly denial", len(aw.Entries))
	}
}

func TestAssemblePrompt_FailOnEncoderError(t *testing.T) {
	c, enc, _ := newComposer(t)
	enc.encodeErr = errors.New("provider unreachable")
	pc := ctxWithSession()
	_, err := c.AssemblePrompt(context.Background(), pc, validSections())
	if err == nil || !errors.Is(err, ErrComposerFailed) {
		t.Fatalf("err = %v; want ErrComposerFailed", err)
	}
}

func TestAssemblePrompt_FailOnEmptyPayload(t *testing.T) {
	c, enc, _ := newComposer(t)
	enc.payload = json.RawMessage("")
	pc := ctxWithSession()
	_, err := c.AssemblePrompt(context.Background(), pc, validSections())
	if err == nil || !errors.Is(err, ErrComposerFailed) {
		t.Fatalf("err = %v; want ErrComposerFailed on empty payload", err)
	}
}

func TestAssemblePrompt_FailOnNilDeps(t *testing.T) {
	cases := []struct {
		name   string
		mutate func(c *DefaultComposer)
	}{
		{"no encoder", func(c *DefaultComposer) { c.Encoder = nil }},
		{"no audit", func(c *DefaultComposer) { c.Audit = nil }},
		{"no id factory", func(c *DefaultComposer) { c.NewAuditID = nil }},
		{"no clock", func(c *DefaultComposer) { c.Now = nil }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			c, _, _ := newComposer(t)
			tc.mutate(c)
			pc := ctxWithSession()
			_, err := c.AssemblePrompt(context.Background(), pc, validSections())
			if err == nil || !errors.Is(err, ErrComposerFailed) {
				t.Fatalf("err = %v; want ErrComposerFailed", err)
			}
		})
	}
}

// ── Determinism: same input → same hash ──────────────────────────────

func TestAssemblePrompt_HashDeterministic(t *testing.T) {
	c1, _, _ := newComposer(t)
	c2, _, _ := newComposer(t)
	pc := ctxWithSession()
	sec := validSections()
	b1, err := c1.AssemblePrompt(context.Background(), pc, sec)
	if err != nil {
		t.Fatalf("err = %v", err)
	}
	b2, err := c2.AssemblePrompt(context.Background(), pc, sec)
	if err != nil {
		t.Fatalf("err = %v", err)
	}
	if b1.ContextHash != b2.ContextHash {
		t.Errorf("ContextHash not deterministic: %x vs %x", b1.ContextHash, b2.ContextHash)
	}
}

// ── ResolveContext skeleton ────────────────────────────────────────────

func TestResolveContext_EmptyV1(t *testing.T) {
	c, _, _ := newComposer(t)
	pc := ctxWithSession()
	rc, err := c.ResolveContext(context.Background(), pc)
	if err != nil {
		t.Fatalf("err = %v", err)
	}
	if len(rc.AllowedEvents) != 0 || len(rc.AllowedMemories) != 0 || len(rc.RejectedRefs) != 0 {
		t.Errorf("V1 ResolvedContext should be empty; got %+v", rc)
	}
}

func TestResolveContext_FailOnInvalidContext(t *testing.T) {
	c, _, _ := newComposer(t)
	pc := PromptContext{} // invalid
	_, err := c.ResolveContext(context.Background(), pc)
	if err == nil || !errors.Is(err, ErrComposerFailed) {
		t.Fatalf("err = %v; want ErrComposerFailed", err)
	}
}

// ── Safety defaults ────────────────────────────────────────────────────

func TestDefaultSafetyHooksUsedWhenNil(t *testing.T) {
	c, _, _ := newComposer(t)
	c.Safety = nil // exercises depsReady noop fallback
	c.Consent = nil
	c.TokenBudget = nil
	pc := ctxWithSession()
	if _, err := c.AssemblePrompt(context.Background(), pc, validSections()); err != nil {
		t.Errorf("expected nil-deps to fall back to no-op safety; err = %v", err)
	}
}

func TestNoopSafetyHooks_AlwaysAllow(t *testing.T) {
	if err := (NoopSafetyHooks{}).PreAssembly(context.Background(), PromptContext{}, nil); err != nil {
		t.Errorf("Noop pre = %v; want nil", err)
	}
	if err := (NoopSafetyHooks{}).PostAssembly(context.Background(), PromptContext{}, [32]byte{}, nil); err != nil {
		t.Errorf("Noop post = %v; want nil", err)
	}
	if err := (NoopConsentGate{}).Check(context.Background(), PromptContext{}); err != nil {
		t.Errorf("Noop consent = %v; want nil", err)
	}
	if err := (NoopTokenBudgetGate{}).Check(context.Background(), PromptContext{}, []byte("x")); err != nil {
		t.Errorf("Noop budget = %v; want nil", err)
	}
}

// ── Helpers ────────────────────────────────────────────────────────────

func zeroBundle(b PromptBundle) bool {
	return len(b.ProviderPayload) == 0 &&
		b.ContextHash == [32]byte{} &&
		b.PromptAuditID == uuid.Nil &&
		b.TemplateID == "" &&
		b.TemplateVersion == 0
}

package meta

import (
	"context"
	"crypto/sha256"
	"reflect"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// TestPkColumnFor_L1A3Tables locks in the cycle 4 (L1.A-3) PK column mappings
// — meta_write_audit, meta_read_audit, admin_action_audit,
// service_to_service_audit, prompt_audit. All five use a surrogate audit_id PK.
//
// Also re-asserts the cycle 2 + 3 entries to catch a regression where adding
// audit cases knocks out a previously-handled table.
func TestPkColumnFor_L1A3Tables(t *testing.T) {
	cases := []struct {
		table string
		want  string
	}{
		// Cycle 2 baseline
		{"reality_registry", "reality_id"},
		// Cycle 3 baseline
		{"pii_registry", "user_ref_id"},
		{"pii_kek", "kek_id"},
		{"user_consent_ledger", "user_ref_id"},
		{"player_character_index", "pc_index_id"},
		// Cycle 4 new
		{"meta_write_audit", "audit_id"},
		{"meta_read_audit", "audit_id"},
		{"admin_action_audit", "audit_id"},
		{"service_to_service_audit", "audit_id"},
		{"prompt_audit", "audit_id"},
		// Fallback heuristic still works
		{"unknown_future_table", "id"},
	}
	for _, c := range cases {
		got := pkColumnFor(c.table)
		if got != c.want {
			t.Errorf("pkColumnFor(%q) = %q, want %q", c.table, got, c.want)
		}
	}
}

// TestAllowlist_L1A3AuditTables_Loaded verifies the 5 new audit tables are
// declared in events_allowlist.yaml AND that none of them emit outbox events
// (auditing the audit would infinite-loop).
func TestAllowlist_L1A3AuditTables_Loaded(t *testing.T) {
	a, err := LoadAllowlist("events_allowlist.yaml")
	if err != nil {
		t.Fatalf("LoadAllowlist: %v", err)
	}

	auditTables := []string{
		"meta_write_audit",
		"meta_read_audit",
		"admin_action_audit",
		"service_to_service_audit",
		"prompt_audit",
	}
	for _, tbl := range auditTables {
		if !a.AllowsTable(tbl) {
			t.Errorf("allowlist missing audit table %s (cycle 4 regression)", tbl)
		}
		// No INSERT/UPDATE/DELETE event emissions — audit tables MUST NOT outbox.
		for _, op := range []MetaWriteOp{OpInsert, OpUpdate, OpDelete} {
			if name, ok := a.EmitsEvent(tbl, op); ok {
				t.Errorf("audit table %s should NOT emit events; got %s on %s", tbl, name, op)
			}
		}
	}

	// Regression: cycle 2 + cycle 3 tables still present
	for _, tbl := range []string{
		"reality_registry", "session_cost_summary",
		"pii_registry", "pii_kek", "user_consent_ledger", "player_character_index",
	} {
		if !a.AllowsTable(tbl) {
			t.Errorf("regression: allowlist lost prior-cycle table %s", tbl)
		}
	}
}

// TestMetaWrite_AuditInsertWiredEveryPath verifies the same-TX audit insert
// fires on every successful MetaWrite (INSERT, UPDATE, DELETE) by counting
// SQL execs against the fake Tx.
//
// This is the cycle 4 acceptance for "MetaWrite() audit wiring activation" —
// the audit insert step ran in cycle 2 but couldn't be exercised against a
// real DB until the audit table shipped. This test pins the wiring at the
// library boundary.
func TestMetaWrite_AuditInsertWiredEveryPath(t *testing.T) {
	allow := newStaticAllowlist(
		[]string{"reality_registry"},
		// No outbox event for this test — we count audit only.
		nil,
	)

	cases := []struct {
		name      string
		intent    MetaWriteIntent
		responses []txResponse
	}{
		{
			name: "INSERT writes data + audit",
			intent: MetaWriteIntent{
				Table:     "reality_registry",
				Operation: OpInsert,
				PK:        map[string]any{"reality_id": uuid.New().String()},
				NewValues: map[string]any{"db_host": "pg-shard-0.internal", "status": "provisioning"},
				Actor:     Actor{Type: ActorService, ID: "world-service"},
			},
			responses: []txResponse{{rows: 1}, {rows: 1}},
		},
		{
			name: "UPDATE (no CAS) writes data + audit",
			intent: MetaWriteIntent{
				Table:     "reality_registry",
				Operation: OpUpdate,
				PK:        map[string]any{"reality_id": uuid.New().String()},
				NewValues: map[string]any{"status": "active"},
				Actor:     Actor{Type: ActorService, ID: "world-service"},
			},
			responses: []txResponse{{rows: 1}, {rows: 1}},
		},
		{
			name: "UPDATE (CAS hit) writes data + audit",
			intent: MetaWriteIntent{
				Table:          "reality_registry",
				Operation:      OpUpdate,
				PK:             map[string]any{"reality_id": uuid.New().String()},
				ExpectedBefore: map[string]any{"status": "provisioning"},
				NewValues:      map[string]any{"status": "active"},
				Actor:          Actor{Type: ActorService, ID: "world-service"},
			},
			responses: []txResponse{{rows: 1}, {rows: 1}},
		},
		{
			name: "DELETE writes data + audit",
			intent: MetaWriteIntent{
				Table:     "reality_registry",
				Operation: OpDelete,
				PK:        map[string]any{"reality_id": uuid.New().String()},
				Reason:    "test-cleanup",
				Actor:     Actor{Type: ActorAdmin, ID: "admin-1"},
			},
			responses: []txResponse{{rows: 1}, {rows: 1}},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cfg, _, _ := newDefaultTestCfg(allow, nil)
			prequeue := &fakeDBPrequeue{queue: [][]txResponse{tc.responses}}
			cfg.DB = prequeue

			_, err := MetaWrite(context.Background(), cfg, tc.intent)
			if err != nil {
				t.Fatalf("MetaWrite: %v", err)
			}
			tx := prequeue.lastTx
			if !tx.committed {
				t.Fatalf("TX not committed")
			}
			if len(tx.execs) < 2 {
				t.Fatalf("expected ≥2 execs (data + audit), got %d", len(tx.execs))
			}
			// Audit insert is always the LAST exec (outbox would push more, but
			// this test has no outbox event registered).
			lastExec := tx.execs[len(tx.execs)-1]
			if !strings.Contains(lastExec.Query, "INSERT INTO meta_write_audit") {
				t.Errorf("last exec should be audit insert, got: %q", lastExec.Query)
			}
		})
	}
}

// TestMetaWrite_AuditFailureRollsBackData asserts the audit insert failing
// rolls back the data write (same-TX guarantee — the audit-data invariant
// is "both or neither").
func TestMetaWrite_AuditFailureRollsBackData(t *testing.T) {
	allow := newStaticAllowlist([]string{"reality_registry"}, nil)
	cfg, _, _ := newDefaultTestCfg(allow, nil)

	prequeue := &fakeDBPrequeue{queue: [][]txResponse{{
		{rows: 1, err: nil},                                            // data INSERT ok
		{rows: 0, err: &fakeAuditError{msg: "audit table unavailable"}}, // audit insert fails
	}}}
	cfg.DB = prequeue

	_, err := MetaWrite(context.Background(), cfg, MetaWriteIntent{
		Table:     "reality_registry",
		Operation: OpInsert,
		PK:        map[string]any{"reality_id": uuid.New().String()},
		NewValues: map[string]any{"db_host": "pg-shard-0.internal", "status": "provisioning"},
		Actor:     Actor{Type: ActorService, ID: "world-service"},
	})
	if err == nil || !strings.Contains(err.Error(), "audit") {
		t.Fatalf("expected audit error, got %v", err)
	}
	if prequeue.lastTx.committed {
		t.Errorf("TX must NOT commit when audit insert fails")
	}
	if prequeue.lastTx.rollbacks == 0 {
		t.Errorf("expected rollback when audit insert fails")
	}
}

type fakeAuditError struct{ msg string }

func (e *fakeAuditError) Error() string { return e.msg }

// TestPromptAuditEntry_BodyNeverStored_TypeShape locks in the "body never
// stored" invariant at the type level by reflection: PromptAuditEntry MUST
// NOT carry any field named like a prompt body. If anyone adds one in the
// future, this test fails immediately.
//
// The set of forbidden names is broad on purpose — we'd rather false-positive
// a legitimate "Body" name than silently accept a body-bearing field.
func TestPromptAuditEntry_BodyNeverStored_TypeShape(t *testing.T) {
	forbiddenFieldNames := map[string]bool{
		"Body":           true,
		"PromptText":     true,
		"AssembledText":  true,
		"PromptBody":     true,
		"Text":           true,
		"FullPrompt":     true,
		"AssembledPrompt": true,
		"Raw":            true,
		"RawPrompt":      true,
	}
	rt := reflect.TypeOf(PromptAuditEntry{})
	for i := 0; i < rt.NumField(); i++ {
		f := rt.Field(i)
		if forbiddenFieldNames[f.Name] {
			t.Errorf("PromptAuditEntry has forbidden body field %q — L1A §3.5 invariant violation", f.Name)
		}
		// Type check: any string-typed field whose name suggests body content
		// is also suspicious. PromptContextHash is []byte and PASSES this guard.
		if f.Type.Kind() == reflect.String &&
			(strings.Contains(strings.ToLower(f.Name), "body") ||
				strings.Contains(strings.ToLower(f.Name), "prompt") && f.Name != "PromptContextHash") {
			if f.Name != "Intent" && f.Name != "TemplateID" {
				t.Errorf("PromptAuditEntry field %q (string) looks body-shaped — re-check L1A §3.5", f.Name)
			}
		}
	}
}

// TestPromptAuditEntry_Validate_HashRequired locks in the 32-byte SHA-256
// validation. A short hash (e.g., zero bytes) is rejected — protects against
// accidentally writing audit rows with no hash at all.
func TestPromptAuditEntry_Validate_HashRequired(t *testing.T) {
	good := sha256.Sum256([]byte("any assembled prompt"))
	user := uuid.New()
	reality := uuid.New()

	cases := []struct {
		name    string
		entry   PromptAuditEntry
		wantErr string
	}{
		{
			name: "valid",
			entry: PromptAuditEntry{
				PromptContextHash: good[:],
				TemplateID:        "tpl_npc_dialogue",
				TemplateVersion:   3,
				Intent:            "npc_dialogue",
				ActorUserRefID:    user,
				RealityID:         reality,
				EstimatedCostUSD:  0.0012,
			},
			wantErr: "",
		},
		{
			name: "empty hash",
			entry: PromptAuditEntry{
				PromptContextHash: nil,
				TemplateID:        "tpl_x",
				TemplateVersion:   1,
				Intent:            "x",
				ActorUserRefID:    user,
				RealityID:         reality,
			},
			wantErr: "PromptContextHash must be SHA-256",
		},
		{
			name: "short hash",
			entry: PromptAuditEntry{
				PromptContextHash: []byte{0x01, 0x02, 0x03},
				TemplateID:        "tpl_x",
				TemplateVersion:   1,
				Intent:            "x",
				ActorUserRefID:    user,
				RealityID:         reality,
			},
			wantErr: "PromptContextHash must be SHA-256",
		},
		{
			name: "missing template",
			entry: PromptAuditEntry{
				PromptContextHash: good[:],
				TemplateVersion:   1,
				Intent:            "x",
				ActorUserRefID:    user,
				RealityID:         reality,
			},
			wantErr: "TemplateID is empty",
		},
		{
			name: "zero user",
			entry: PromptAuditEntry{
				PromptContextHash: good[:],
				TemplateID:        "tpl_x",
				TemplateVersion:   1,
				Intent:            "x",
				RealityID:         reality,
			},
			wantErr: "ActorUserRefID is zero",
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			err := c.entry.Validate()
			if c.wantErr == "" {
				if err != nil {
					t.Errorf("want ok, got %v", err)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), c.wantErr) {
				t.Errorf("want error containing %q, got %v", c.wantErr, err)
			}
		})
	}
}

// TestPromptAudit_Interface_SignatureShape locks in the PromptAudit interface
// shape by reflection. The contract is:
//
//   - exactly one method, RecordAssembly
//   - takes exactly ONE parameter (a PromptAuditEntry, not a raw string)
//   - returns error
//
// If anyone adds a "RecordAssemblyWithBody(string, ...)" method, this test
// fails — preventing the body-never-stored invariant from drifting at the
// interface boundary.
func TestPromptAudit_Interface_SignatureShape(t *testing.T) {
	it := reflect.TypeOf((*PromptAudit)(nil)).Elem()
	if it.NumMethod() != 1 {
		t.Fatalf("PromptAudit interface must have exactly 1 method, got %d", it.NumMethod())
	}
	m := it.Method(0)
	if m.Name != "RecordAssembly" {
		t.Errorf("PromptAudit method name = %q, want RecordAssembly", m.Name)
	}
	// Method type: signature is `func(PromptAuditEntry) error` — 1 in, 1 out.
	mt := m.Type
	if mt.NumIn() != 1 {
		t.Errorf("RecordAssembly must take exactly 1 parameter, got %d", mt.NumIn())
	}
	// The single parameter MUST be PromptAuditEntry (not a string, not a body byte slice).
	if mt.In(0) != reflect.TypeOf(PromptAuditEntry{}) {
		t.Errorf("RecordAssembly parameter must be PromptAuditEntry, got %v", mt.In(0))
	}
	if mt.NumOut() != 1 || mt.Out(0) != reflect.TypeOf((*error)(nil)).Elem() {
		t.Errorf("RecordAssembly must return error, got %v", mt.Out(0))
	}
}

// TestScrubber_PassthroughHashStable verifies the stub Scrubber produces a
// 32-byte SHA-256 of the input and that two scrubs of the same text produce
// the same hash (forensic correlation property).
func TestScrubber_PassthroughHashStable(t *testing.T) {
	clk := newFakeClock(1_700_000_000_000_000_000)
	s := PassthroughScrubber{Version: "test-v1", Clock: clk}

	a := s.Scrub("connection refused (host=pg-shard-2.internal)")
	b := s.Scrub("connection refused (host=pg-shard-2.internal)")
	if len(a.RawHash) != 32 {
		t.Fatalf("hash must be 32 bytes, got %d", len(a.RawHash))
	}
	for i, x := range a.RawHash {
		if x != b.RawHash[i] {
			t.Fatalf("hash should be stable for identical input")
		}
	}
	if a.Version != "test-v1" {
		t.Errorf("version not propagated: %s", a.Version)
	}
	if a.ScrubbedAt.IsZero() {
		t.Errorf("ScrubbedAt should be populated")
	}
	if err := MustValidateScrubbedField(a); err != nil {
		t.Errorf("validate: %v", err)
	}

	// Empty field must pass validate (the "no error to scrub" case).
	if err := MustValidateScrubbedField(ScrubbedField{}); err != nil {
		t.Errorf("empty field should validate ok, got %v", err)
	}
	// Partial population must fail.
	if err := MustValidateScrubbedField(ScrubbedField{Scrubbed: "x"}); err == nil {
		t.Errorf("partial population must fail validate")
	}
}

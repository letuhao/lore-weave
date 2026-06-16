package meta

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// TestMetaWrite_ScrubberRedactsAuditOnly is the r1-BLOCK1 regression guard:
// when a Scrubber is configured, ONLY the meta_write_audit copy is PII-redacted;
// the persisted data write AND the outbox payload keep the original values, and
// the caller's intent maps are never mutated.
func TestMetaWrite_ScrubberRedactsAuditOnly(t *testing.T) {
	allow := newStaticAllowlist(
		[]string{"reality_registry"},
		map[string]map[MetaWriteOp]string{"reality_registry": {OpInsert: "reality.created"}},
	)
	cfg, db, out := newDefaultTestCfg(allow, nil)
	cfg.Scrubber = NewRegexScrubber(nil) // production scrubber

	newVals := map[string]any{"contact_email": "alice@example.com", "status": "provisioning"}
	_, err := MetaWrite(context.Background(), cfg, MetaWriteIntent{
		Table:          "reality_registry",
		Operation:      OpInsert,
		PK:             map[string]any{"natural_key": "pk-dave@example.com"},
		NewValues:      newVals,
		Reason:         "opened for bob@corp.example",
		RequestContext: RequestContext{RequestID: "trace for carol@evil.example", SourceService: "svc"},
		Actor:          Actor{Type: ActorService, ID: "world-service"},
	})
	if err != nil {
		t.Fatalf("MetaWrite: %v", err)
	}

	// 1. Caller's intent map untouched.
	if newVals["contact_email"] != "alice@example.com" {
		t.Errorf("caller NewValues mutated: %v", newVals["contact_email"])
	}

	// 2. Data write (exec[0]) carries the RAW email (the scrub must not touch it).
	tx := db.Txs[0]
	if !strings.Contains(argsString(tx.execs[0].Args), "alice@example.com") {
		t.Errorf("data write was scrubbed (must be raw): %v", tx.execs[0].Args)
	}

	// 3. Audit insert (exec[1]) carries the REDACTED email + reason + scrub_version.
	auditArgs := argsString(tx.execs[1].Args)
	if strings.Contains(auditArgs, "alice@example.com") {
		t.Errorf("audit insert leaked raw email: %v", tx.execs[1].Args)
	}
	if !strings.Contains(auditArgs, "[EMAIL]") {
		t.Errorf("audit insert email not redacted: %v", tx.execs[1].Args)
	}
	if !strings.Contains(auditArgs, "regex-v1") {
		t.Errorf("audit insert missing scrub_version: %v", tx.execs[1].Args)
	}
	// row_pk (review-impl #1) + request_context (WARN3) must also be redacted.
	if strings.Contains(auditArgs, "dave@example.com") {
		t.Errorf("audit leaked raw PII in row_pk: %v", tx.execs[1].Args)
	}
	if strings.Contains(auditArgs, "carol@evil.example") {
		t.Errorf("audit leaked raw PII in request_context: %v", tx.execs[1].Args)
	}

	// 4. Outbox payload keeps the RAW email (downstream projections need truth).
	if len(out.events) != 1 {
		t.Fatalf("expected 1 outbox event, got %d", len(out.events))
	}
	after := out.events[0].Payload["after"].(map[string]any)
	if after["contact_email"] != "alice@example.com" {
		t.Errorf("outbox payload was scrubbed (must be raw): %v", after["contact_email"])
	}
}

// TestMetaWrite_NoScrubberBackCompat: nil Scrubber → audit carries raw values +
// empty scrub_version (every existing caller relies on this).
func TestMetaWrite_NoScrubberBackCompat(t *testing.T) {
	allow := newStaticAllowlist([]string{"reality_registry"}, nil)
	cfg, db, _ := newDefaultTestCfg(allow, nil) // no Scrubber

	_, err := MetaWrite(context.Background(), cfg, MetaWriteIntent{
		Table:     "reality_registry",
		Operation: OpInsert,
		PK:        map[string]any{"reality_id": uuid.New().String()},
		NewValues: map[string]any{"contact_email": "alice@example.com"},
		Actor:     Actor{Type: ActorService, ID: "world-service"},
	})
	if err != nil {
		t.Fatalf("MetaWrite: %v", err)
	}
	auditArgs := argsString(db.Txs[0].execs[1].Args)
	if !strings.Contains(auditArgs, "alice@example.com") {
		t.Errorf("nil-scrubber audit should keep raw value: %v", db.Txs[0].execs[1].Args)
	}
	if strings.Contains(auditArgs, "regex-v1") {
		t.Errorf("nil-scrubber path must leave scrub_version empty (no scrub): %v", db.Txs[0].execs[1].Args)
	}
}

func argsString(args []any) string {
	var b strings.Builder
	for _, a := range args {
		switch v := a.(type) {
		case string:
			b.WriteString(v)
		case []byte:
			b.Write(v)
		default:
			b.WriteString(toStr(v))
		}
		b.WriteByte('\x1f')
	}
	return b.String()
}

func toStr(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	if b, ok := v.([]byte); ok {
		return string(b)
	}
	return ""
}

package api

// T10-D1 — a tool may declare `book_id` OPTIONAL only if it actually resolves the book from
// the envelope.
//
// `bookToolAuthAmbient`'s own comment states the pairing rule: "Use ONLY on a tool tagged
// WithAmbientBook (its book_id schema must be optional)." Read the other way round, an optional
// `book_id` in the advertised schema IS the promise of the ambient contract — the model may omit
// it inside a book studio and the book comes from X-Book-Id.
//
// MEASURED 2026-08-13 over the real wire, same envelope (X-Book-Id set), same omission:
//
//	glossary_get_entity          (WithAmbientBook) -> ok, resolved from the envelope
//	glossary_search              (WithAmbientBook) -> ok, resolved from the envelope
//	glossary_list_chapter_links                    -> "book_id must be a UUID"
//	glossary_list_entity_revisions                 -> "book_id must be a UUID"
//	glossary_get_entity_evidence                   -> "book_id must be a UUID"
//
// Those three advertised the contract without implementing it, and the refusal is wrong twice
// over: the caller followed the schema, and it sent no book_id at all rather than a malformed
// one.
//
// This guard covers the three fixed here. The wider residue — 37 other glossary tools that
// declare book_id optional without the ambient tag — is DQ-T4, a service-wide product decision
// (declare-required vs make-ambient), and `ambientResidueAllowlist` keeps it VISIBLE rather than
// letting silence read as coverage.

import (
	"sort"
	"testing"
)

// ambientBookGuarded — tools whose book_id declaration this test pins today.
var ambientBookGuarded = []string{
	"glossary_list_chapter_links",
	"glossary_list_entity_revisions",
	"glossary_get_entity_evidence",
}

func bookIDIsOptional(schema map[string]any) bool {
	props, _ := schema["properties"].(map[string]any)
	if _, has := props["book_id"]; !has {
		return false // no book_id at all — not this rule's business
	}
	req, _ := schema["required"].([]any)
	for _, r := range req {
		if s, ok := r.(string); ok && s == "book_id" {
			return false
		}
	}
	return true
}

func TestGuardedToolsDeclareBookIDRequired(t *testing.T) {
	schemas, _ := listToolsWireFull(t)
	for _, name := range ambientBookGuarded {
		schema, ok := schemas[name]
		if !ok {
			t.Fatalf("%s is not advertised at all — this guard has gone blind; re-point it "+
				"rather than deleting it", name)
		}
		if bookIDIsOptional(schema) {
			t.Errorf("%s declares book_id OPTIONAL but its handler calls the non-ambient "+
				"bookToolAuth, so an omitted book_id is refused with \"book_id must be a UUID\" "+
				"even inside a book studio. Either mark it required or give the tool "+
				"WithAmbientBook + bookToolAuthAmbient (T10-D1).", name)
		}
	}
}

func TestAmbientTaggedToolsStillDeclareBookIDOptional(t *testing.T) {
	// The other half of the same rule, and the control for the test above: a tool that DOES
	// resolve the book from the envelope must keep book_id optional, or the schema validator
	// will reject the very omission the ambient path exists to serve.
	schemas, metas := listToolsWireFull(t)
	checked := 0
	for name, meta := range metas {
		if ambient, _ := meta["ambient_book"].(bool); !ambient {
			continue
		}
		schema, ok := schemas[name]
		if !ok {
			continue
		}
		props, _ := schema["properties"].(map[string]any)
		if _, has := props["book_id"]; !has {
			continue
		}
		checked++
		if !bookIDIsOptional(schema) {
			t.Errorf("%s is tagged WithAmbientBook but declares book_id REQUIRED — the schema "+
				"validator will refuse the omission the ambient path exists to serve", name)
		}
	}
	if checked == 0 {
		t.Fatal("no WithAmbientBook tool with a book_id was found — the ambient mechanism has " +
			"moved and this control is now vacuous")
	}
}

func TestTheAmbientResidueIsStatedNotSilent(t *testing.T) {
	// Every glossary tool that still declares book_id optional WITHOUT the ambient tag. The
	// count is not asserted as "zero" — that would be a lie about the service today — but the
	// SET is pinned, so fixing one shrinks it visibly and adding one fails loudly instead of
	// disappearing into an unmeasured backlog.
	schemas, metas := listToolsWireFull(t)
	var residue []string
	for name, schema := range schemas {
		if ambient, _ := metas[name]["ambient_book"].(bool); ambient {
			continue
		}
		if bookIDIsOptional(schema) {
			residue = append(residue, name)
		}
	}
	sort.Strings(residue)
	for _, name := range ambientBookGuarded {
		for _, r := range residue {
			if r == name {
				t.Errorf("%s is fixed and must not be back in the residue", name)
			}
		}
	}
	// 🔴 THIS WAS A LOG LINE, AND IT IS NOW AN ASSERTION. Its own comment said the count "is
	// not asserted as zero — that would be a lie about the service today". DQ-T4 was answered
	// 2026-08-31 — OWNER: "(a) DECLARE book_id REQUIRED on the 37 remaining glossary tools" —
	// and built 2026-09-02, so zero is now the truth and a log line would let the next tool
	// re-open the gap silently.
	//
	// A tool that legitimately resolves the book from the envelope belongs in the OTHER half of
	// this rule: tag it WithAmbientBook and it leaves this set by construction, checked by
	// TestAmbientTaggedToolsStillDeclareBookIDOptional above.
	if len(residue) != 0 {
		t.Errorf("%d glossary tool(s) declare book_id OPTIONAL without WithAmbientBook: %v.\n"+
			"An optional book_id IS the advertised promise of the ambient contract - a model "+
			"inside a book studio may omit it - and these handlers call the NON-ambient "+
			"bookToolAuth, so the omission is refused with book_id-must-be-a-UUID. Either "+
			"declare it required (DQ-T4 ruling) or implement the contract you advertise "+
			"(WithAmbientBook + bookToolAuthAmbient).", len(residue), residue)
	}
}

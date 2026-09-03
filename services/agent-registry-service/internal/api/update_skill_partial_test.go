package api

import (
	"os"
	"strings"
	"testing"
)

// TOOLV2 LOOP #291 — "the new description and/or body", over a schema that required the body.
//
// registry_update_skill's description says: "Provide the slug and the new description and/or
// body." Measured, body_md was a REQUIRED property, so a description-only update was impossible:
//
//	{"slug": "...", "description": "..."}  ->  required: missing properties: ["body_md"]
//
// An agent fixing a typo in a description had to resend the entire SKILL.md body, and if it did
// not have the body to hand it would either fail or invent one — on a tool whose whole point is
// proposing a diff a human will read.
//
// The handler already implemented the right pattern for the OTHER field, one line away: "keep
// existing description when omitted". body_md now gets the same treatment, so a partial update
// preserves the field it did not mention rather than blanking it.
//
// Verified live after the change: a description-only update produced a pending proposal whose
// body_md was 65 chars — byte-identical to the live skill's body — and the live skill itself was
// untouched, because propose never applies.
func TestUpdateSkillBodyIsOptional(t *testing.T) {
	// Scoped to updateSkillIn: proposeSkillIn requires body_md legitimately — a NEW skill with
	// no body is not a skill — so a whole-file match would fail on the tool that is correct.
	upd := structBody(t, "updateSkillIn")
	if strings.Contains(upd, "`json:\"body_md\" jsonschema:") {
		t.Error("body_md is a required property again — a description-only update becomes " +
			"impossible, which the tool's own description promises is allowed")
	}
	if !strings.Contains(upd, `json:"body_md,omitempty"`) {
		t.Error("body_md must be omitempty so the generated schema does not require it")
	}
	// The sibling must stay required, or this fix has leaked into the wrong tool.
	if !strings.Contains(structBody(t, "proposeSkillIn"), "`json:\"body_md\"") {
		t.Error("proposeSkillIn no longer requires body_md — proposing a NEW skill with no body")
	}
}

// The point of making it optional is that omitting it PRESERVES the current body. Optional-but-
// blanking would be worse than required: a typo fix would silently destroy the skill.
func TestOmittedFieldsAreKeptNotBlanked(t *testing.T) {
	src := mustRead(t, "mcp_server.go")
	for _, want := range []string{
		"SELECT description, body_md FROM skills WHERE skill_id=$1",
		"if desc == \"\" {",
		"if body == \"\" {",
	} {
		if !strings.Contains(src, want) {
			t.Errorf("the keep-existing read is gone: missing %q", want)
		}
	}
	if !strings.Contains(src, "BodyMD: body") {
		t.Error("the proposal must carry the resolved body, not the raw (possibly empty) input")
	}
}

// The ownership gate is the reason this tool is safe to expose at all, and it must survive a
// change to the fields around it.
func TestOnlyOwnSkillsCanBeUpdated(t *testing.T) {
	src := mustRead(t, "mcp_server.go")
	if !strings.Contains(src, `tier != "user" || owner == nil || *owner != uid`) {
		t.Error("the ownership check changed shape — a system or another user's skill must not " +
			"be updatable")
	}
	if !strings.Contains(src, "System skills are read-only — clone one instead") {
		t.Error("the refusal must still name the alternative, or the agent has no next move")
	}
}

// structBody returns the source of one struct declaration, so a field assertion cannot match a
// same-named field on a DIFFERENT struct in the same file.
func structBody(t *testing.T, name string) string {
	t.Helper()
	src := mustRead(t, "mcp_server.go")
	start := strings.Index(src, "type "+name+" struct {")
	if start < 0 {
		t.Fatalf("struct %s not found", name)
	}
	end := strings.Index(src[start:], "\n}")
	if end < 0 {
		t.Fatalf("struct %s is unterminated", name)
	}
	return src[start : start+end]
}

func mustRead(t *testing.T, name string) string {
	t.Helper()
	b, err := os.ReadFile(name)
	if err != nil {
		t.Fatalf("read %s: %v", name, err)
	}
	return string(b)
}

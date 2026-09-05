package api

// A skill proposed with an EMPTY body was accepted.
//
// MEASURED 2026-08-22 by the tool deep-dive's SHIP probe (batch 38), against the live service:
//
//	registry_propose_skill(slug="loop-probe-empty", description="d", body_md="")
//	  -> {"message": "Proposed skill 'loop-probe-empty'. Awaiting the user's approval in the UI
//	      — nothing is saved until they approve.", "proposal_id": "01a02681-…"}
//
// Accepted, and a proposal row was written. A skill IS its instructions: `description` is the
// one-line menu entry and `body_md` is what the agent actually reads, so an empty skill would sit
// in the user's list looking real and contribute nothing when loaded. Nothing is applied until
// the user approves — which is what makes this latent rather than an incident, and also what
// makes it easy to approve by mistake.
//
// 🔴 THIS IS THE SAME INVARIANT AS D-EMPTY-TRANSLATION-SAVED-AS-A-VERSION, ONE BATCH EARLIER.
// That fix named the invariant — "a tool that creates a durable, author-attributed artefact must
// refuse an EMPTY one" — and recorded it as proved against every past incident of its class:
// book_steering_set, world_create, world_update, world_map_update, kg_view_edit and
// settings_update_profile all refuse correctly. registry_propose_skill was not in that list
// because it had not been probed. A class check is a SNAPSHOT of what has been measured, not a
// sweep of what exists, and this is what that distinction costs.
//
// Still not swept, and still worth probing: book_chapter_bulk_create's empty `chapters` list,
// recorded OWED in batch 26 and never exercised.
//
// WHERE THE CHECK LIVES. validateSkill, which is shared by the proposal path, the bundle importer
// and the direct skill write — one chokepoint for three callers. It is safe on the UPDATE path
// because toolUpdateSkill backfills the CURRENT body before validating, so omitting body_md to
// keep the existing one still arrives here non-empty. That ordering is asserted below, because a
// guard that broke partial updates would be a worse bug than the one it fixes.

import (
	"os"
	"strings"
	"testing"
)

func TestAnEmptySkillBodyIsRefused(t *testing.T) {
	for _, tc := range []struct{ name, body string }{
		{"empty string", ""},
		{"whitespace only", "   \n\t "},
	} {
		t.Run(tc.name, func(t *testing.T) {
			msg, ok := validateSkill(&skillInput{
				Slug: "tide-tables", Description: "Tide notes", BodyMD: tc.body,
			})
			if ok {
				t.Fatal("an empty body was accepted; a skill with no instructions looks real in " +
					"the user's list and does nothing when loaded")
			}
			if msg == "" {
				t.Fatal("the refusal must say why")
			}
		})
	}
}

func TestARealSkillStillValidates(t *testing.T) {
	// The bystander. A guard that also blocks real skills is not a fix.
	if msg, ok := validateSkill(&skillInput{
		Slug: "tide-tables", Description: "Tide notes",
		BodyMD: "The Obsidian Trench is only walkable at low tide.",
	}); !ok {
		t.Fatalf("a real skill was refused: %s", msg)
	}
}

func TestTheOtherRefusalsStillFireFirst(t *testing.T) {
	// The new check must not mask the ones already there — a bad slug with an empty body should
	// still complain about the SLUG, which is the more useful message.
	msg, ok := validateSkill(&skillInput{Slug: "Not A Slug!", Description: "d", BodyMD: ""})
	if ok {
		t.Fatal("a bad slug was accepted")
	}
	if msg != "slug must be lowercase [a-z0-9-], 2-64 chars" {
		t.Fatalf("slug validation no longer fires first: %q", msg)
	}
}

func TestAnEmptyDescriptionIsStillRefused(t *testing.T) {
	if _, ok := validateSkill(&skillInput{Slug: "tide-tables", Description: "  ", BodyMD: "x"}); ok {
		t.Fatal("an empty description was accepted")
	}
}

// The partial-update path must keep working: toolUpdateSkill backfills the current body BEFORE
// calling validateSkill, so "omit body_md to keep the current one" still reaches a non-empty body.
// Source-level because the handler needs a live pool; the ordering is the whole guarantee.
func TestTheUpdatePathBackfillsBeforeValidating(t *testing.T) {
	src, err := os.ReadFile("mcp_server.go")
	if err != nil {
		t.Fatalf("read mcp_server.go: %v", err)
	}
	body := string(src)
	start := strings.Index(body, "func (s *Server) toolUpdateSkill")
	if start < 0 {
		t.Fatal("toolUpdateSkill is gone — re-point this test")
	}
	body = body[start:]
	backfill := strings.Index(body, "body = curBody")
	// The update path does not call validateSkill directly — it hands off to doProposeSkill,
	// which validates. So the ordering that matters is backfill BEFORE that hand-off.
	validate := strings.Index(body, "doProposeSkill")
	if backfill < 0 || validate < 0 {
		t.Fatalf("update path changed shape (backfill=%d validate=%d)", backfill, validate)
	}
	if backfill > validate {
		t.Fatal("toolUpdateSkill now validates BEFORE backfilling the current body — omitting " +
			"body_md to keep the existing one would be refused by the new empty-body check")
	}
}

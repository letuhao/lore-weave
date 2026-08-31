package api

import (
	"slices"
	"strings"
	"testing"
)

// TOOLV2 LOOP #287 — the workflow surface filter offered four values, none of which any
// workflow advertises.
//
// registry_list_workflows' `surface` arg borrowed skills.go's validSurfaces, so its MCP enum was
// {chat, compose, translate, admin}. Measured against the store, published workflows advertise:
//
//	{book,editor}         5
//	{book,editor,studio}  4
//	{}                    2
//	{book}                1
//
// So every value the enum offered matched only the TWO workflows with an empty (unrestricted)
// surface list, and the ten that declare one were unreachable through the filter. The tool
// returned 2 for chat, 2 for compose and 2 for admin — three identical answers, which is what a
// filter looks like when it cannot match anything it is asked for.
//
// Skills genuinely do use chat/compose (13 on {chat}, 5 on {chat,compose}), so the skills enum is
// right and only the workflow tool was borrowing the wrong vocabulary.
//
// After the split, the filter differentiates and each count is derivable from the stored surfaces:
// book 12 (5+4+1 declaring + 2 unrestricted), editor 11 (5+4+2), studio 6 (4+2).
func TestWorkflowSurfacesAreNotSkillSurfaces(t *testing.T) {
	for _, s := range validWorkflowSurfaces {
		if slices.Contains(validSurfaces, s) {
			t.Errorf("workflow surface %q also appears in validSurfaces — the two vocabularies "+
				"are merging again; a workflow lives on book/editor/studio, a skill on "+
				"chat/compose/translate/admin", s)
		}
	}
	for _, s := range validSurfaces {
		if slices.Contains(validWorkflowSurfaces, s) {
			t.Errorf("skill surface %q leaked into validWorkflowSurfaces", s)
		}
	}
}

// The vocabulary must match what the migrations actually seed. If a fourth workflow surface is
// introduced and only the seed learns about it, the filter goes quietly blind to it again.
func TestWorkflowSurfaceVocabularyIsTheSeededOne(t *testing.T) {
	want := []string{"book", "editor", "studio"}
	if !slices.Equal(validWorkflowSurfaces, want) {
		t.Fatalf("validWorkflowSurfaces = %v, want %v (the set migrate.go seeds)",
			validWorkflowSurfaces, want)
	}
}

// The MCP enum is built from the vocabulary, not typed out beside it — a hand-written copy is how
// the original divergence survived.
func TestWorkflowSurfaceEnumIsDerivedFromTheVocabulary(t *testing.T) {
	if len(enumWorkflowSurfaces) != len(validWorkflowSurfaces) {
		t.Fatalf("enumWorkflowSurfaces has %d entries, vocabulary has %d",
			len(enumWorkflowSurfaces), len(validWorkflowSurfaces))
	}
	for i, v := range validWorkflowSurfaces {
		if enumWorkflowSurfaces[i] != any(v) {
			t.Errorf("enumWorkflowSurfaces[%d] = %v, want %q", i, enumWorkflowSurfaces[i], v)
		}
	}
}

// #292 CORRECTION — #287 fixed the FILTER and left both WRITERS.
//
// registry_propose_workflow and registry_update_workflow pinned their surfaces[] to enumSurfaces
// too, so after #287 the three workflow tools disagreed on the wire: the list tool offered
// {book, editor, studio} while the two tools that WRITE surfaces offered
// {chat, compose, translate, admin}. That is worse than the original bug — before, filter and
// writers were consistently wrong; after a half-fix, a workflow proposed with surfaces=["chat"]
// could never be found by the filter at all.
//
// So this asserts over EVERY workflow tool that touches surfaces, by name, rather than the one
// that happened to be under test.
func TestEveryWorkflowToolUsesTheWorkflowSurfaceEnum(t *testing.T) {
	src := mustRead(t, "mcp_server.go")
	for _, tool := range []string{
		"registry_list_workflows",
		"registry_propose_workflow",
		"registry_update_workflow",
	} {
		start := strings.Index(src, `Name:        "`+tool+`"`)
		if start < 0 {
			t.Fatalf("tool %s not found", tool)
		}
		end := strings.Index(src[start+1:], "registerARTool(srv")
		block := src[start:]
		if end > 0 {
			block = src[start : start+1+end]
		}
		if strings.Contains(block, "enumSurfaces") {
			t.Errorf("%s pins a surface arg to enumSurfaces (the SKILL vocabulary); workflows "+
				"live on book/editor/studio, and a writer disagreeing with the filter makes the "+
				"workflow it writes unfindable", tool)
		}
		if !strings.Contains(block, "enumWorkflowSurfaces") {
			t.Errorf("%s does not pin its surface arg to enumWorkflowSurfaces", tool)
		}
	}
}

// The skills enum must keep pointing at the skills vocabulary — this fix must not swap the
// problem to the other tool.
func TestSkillSurfaceEnumStillDerivedFromSkillVocabulary(t *testing.T) {
	if len(enumSurfaces) != len(validSurfaces) {
		t.Fatalf("enumSurfaces has %d entries, validSurfaces has %d",
			len(enumSurfaces), len(validSurfaces))
	}
	for i, v := range validSurfaces {
		if enumSurfaces[i] != any(v) {
			t.Errorf("enumSurfaces[%d] = %v, want %q", i, enumSurfaces[i], v)
		}
	}
}

// A workflow's surfaces must be validated against the WORKFLOW vocabulary.
//
// 🔴 WHAT THE EXISTING GUARDS IN THIS FILE COULD NOT SEE. They assert the LIST is right — that
// validWorkflowSurfaces equals the set migrate.go seeds, and that no skill surface leaked into
// it. Both passed while `validateWorkflow` called `invalidSurface`, the SKILL checker, which
// tests against {chat, compose, translate, admin}. The list was correct and the CALL SITE used
// a different one.
//
// The consequence was total: the published schema offers {book, editor, studio} and the
// validator demanded {chat, compose, translate, admin}, and the two share no members — so
// registry_propose_workflow could not be called with ANY surfaces value. A caller obeying the
// schema was refused by the validator; a caller obeying the validator was refused by the schema.
// Measured live 2026-09-01 by direct probe against the deployed service.
func TestValidateWorkflowUsesTheWORKFLOWSurfaceVocabulary(t *testing.T) {
	for _, s := range validWorkflowSurfaces {
		in := &workflowInput{
			Slug: "wf-surface", Title: "T", Description: "d",
			Surfaces: []string{s},
			Steps:    []workflowStepIn{{ID: "s1", Tool: "book_list", Gate: "none"}},
		}
		if msg, ok := validateWorkflow(in); !ok {
			t.Fatalf("the PUBLISHED surface %q was refused by the validator: %q — the schema and "+
				"the validator disagree, so the tool cannot be called at all", s, msg)
		}
	}
}

func TestAWorkflowMayNotDeclareASKILLSurface(t *testing.T) {
	for _, s := range validSurfaces {
		if slices.Contains(validWorkflowSurfaces, s) {
			continue // a shared member would make this case meaningless
		}
		in := &workflowInput{
			Slug: "wf-surface", Title: "T", Description: "d",
			Surfaces: []string{s},
			Steps:    []workflowStepIn{{ID: "s1", Tool: "book_list", Gate: "none"}},
		}
		if _, ok := validateWorkflow(in); ok {
			t.Errorf("the SKILL surface %q was accepted on a workflow — the filter that reads "+
				"these will never find it", s)
		}
	}
}

// The refusal must name the vocabulary it is actually enforcing, or the caller is sent to a set
// the schema does not offer. The original message hard-coded the SKILL list.
func TestTheSurfaceRefusalNamesTheWorkflowVocabulary(t *testing.T) {
	in := &workflowInput{
		Slug: "wf-surface", Title: "T", Description: "d",
		Surfaces: []string{"definitely-not-a-surface"},
		Steps:    []workflowStepIn{{ID: "s1", Tool: "book_list", Gate: "none"}},
	}
	msg, ok := validateWorkflow(in)
	if ok {
		t.Fatal("a nonsense surface was accepted")
	}
	for _, s := range validWorkflowSurfaces {
		if !strings.Contains(msg, s) {
			t.Errorf("the refusal does not offer %q: %q", s, msg)
		}
	}
	for _, s := range validSurfaces {
		if slices.Contains(validWorkflowSurfaces, s) {
			continue
		}
		if strings.Contains(msg, s) {
			t.Errorf("the refusal still offers the SKILL surface %q: %q", s, msg)
		}
	}
}

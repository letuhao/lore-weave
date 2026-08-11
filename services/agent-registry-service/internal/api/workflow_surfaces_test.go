package api

import (
	"slices"
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

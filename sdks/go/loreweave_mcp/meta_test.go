package loreweave_mcp

import (
	"strings"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestValidateToolMeta_Accepts(t *testing.T) {
	tool := &mcp.Tool{
		Name: "book_get",
		Meta: NewToolMeta(TierR, ScopeBook, nil, []string{"fetch", "lookup"}),
	}
	if err := ValidateToolMeta(tool); err != nil {
		t.Fatalf("ValidateToolMeta = %v, want nil", err)
	}
}

func TestValidateToolMeta_Rejects(t *testing.T) {
	cases := map[string]*mcp.Tool{
		"nil meta": {Name: "book_get"},
		"missing tier": {Name: "book_get", Meta: mcp.Meta{MetaKeyScope: "book"}},
		"missing scope": {Name: "book_get", Meta: mcp.Meta{MetaKeyTier: "R"}},
		"invalid tier":  {Name: "book_get", Meta: mcp.Meta{MetaKeyTier: "X", MetaKeyScope: "book"}},
		"invalid scope": {Name: "book_get", Meta: mcp.Meta{MetaKeyTier: "R", MetaKeyScope: "galaxy"}},
		"tier wrong type": {Name: "book_get", Meta: mcp.Meta{MetaKeyTier: 1, MetaKeyScope: "book"}},
	}
	for name, tool := range cases {
		t.Run(name, func(t *testing.T) {
			err := ValidateToolMeta(tool)
			if err == nil {
				t.Fatalf("ValidateToolMeta = nil, want rejection")
			}
			if !strings.Contains(err.Error(), "book_get") && name != "nil meta" {
				t.Errorf("error %q should name the tool", err)
			}
		})
	}
}

func TestValidateToolMeta_NilTool(t *testing.T) {
	if err := ValidateToolMeta(nil); err == nil {
		t.Fatal("ValidateToolMeta(nil) = nil, want error")
	}
}

func TestMustValidateToolMeta_Panics(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Error("MustValidateToolMeta should panic on invalid meta")
		}
	}()
	MustValidateToolMeta(&mcp.Tool{Name: "bad"})
}

func TestNewToolMeta_OmitsEmptyOptionals(t *testing.T) {
	m := NewToolMeta(TierW, ScopeUser, nil, nil)
	if _, ok := m[MetaKeyUndoHint]; ok {
		t.Error("undo_hint should be omitted when nil")
	}
	if _, ok := m[MetaKeySynonyms]; ok {
		t.Error("synonyms should be omitted when empty")
	}
	if m[MetaKeyTier] != "W" || m[MetaKeyScope] != "user" {
		t.Errorf("meta = %v, want tier=W scope=user", m)
	}
}

package textnorm

import "testing"

// TestNormalize_MultiLanguageFold covers the D-GLOSSARY-ST-DEDUP behavior change:
// Normalize now delegates the case/script fold to the loreweave_extraction SDK
// (NFKC + casefold + CJK traditional->simplified) on top of trim + ws-collapse.
func TestNormalize_MultiLanguageFold(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		// legacy contract preserved (ASCII): lower, trim, collapse
		{"ascii lower+trim", "  Yan Mo  ", "yan mo"},
		{"ascii collapse ws", "yan   mo", "yan mo"},
		// new: CJK traditional -> simplified fold (the headline fix)
		{"traditional folds to simplified", "張若塵", "张若尘"},
		{"simplified stable", "张若尘", "张若尘"},
		{"distinct cjk stays distinct (control)", "八王子", "八王子"},
		// new: full-width -> ascii (NFKC)
		{"fullwidth to ascii", "Ｋａｉ", "kai"},
		// new: Unicode casefold beyond ToLower
		{"sharp-s casefolds to ss", "Straße", "strasse"},
		{"empty", "   ", ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := Normalize(c.in); got != c.want {
				t.Errorf("Normalize(%q) = %q, want %q", c.in, got, c.want)
			}
		})
	}
}

// Equivalence keys: the simplified/traditional pair must collapse so the resolver
// resolves them to one entity; a distinct name must not.
func TestNormalize_StEquivalence(t *testing.T) {
	if Normalize("張若塵") != Normalize("张若尘") {
		t.Error("traditional and simplified 張若塵/张若尘 must produce the same key")
	}
	if Normalize("八王子") == Normalize("张若尘") {
		t.Error("八王子 must stay distinct from 张若尘")
	}
}

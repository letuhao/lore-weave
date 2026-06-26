package loreweave_extraction

import (
	"bufio"
	"os"
	"strings"
	"testing"
)

func TestNormalizeEntityName(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{"ascii unchanged", "Kai", "kai"},
		{"ascii upper", "KAI", "kai"},
		{"fullwidth folds to ascii", "Ｋａｉ", "kai"}, // Ｋａｉ → kai (NFKC)
		{"sharp-s casefolds to ss", "Straße", "strasse"},     // Straße → strasse
		{"composed umlaut casefolded", "Mü", "mü"},      // Mü → mü
		{"decomposed umlaut composes via NFKC", "Mü", "mü"}, // M + u + ◌̈ → mü
		{"traditional folds to simplified", "張若塵", "张若尘"}, // 張若塵 → 张若尘
		{"simplified stable", "张若尘", "张若尘"},               // 张若尘
		{"mixed components fold", "萬古神帝", "万古神帝"}, // 萬古神帝 → 万古神帝
		{"kana untouched", "カイ", "カイ"}, // カイ
		{"hangul untouched", "카이", "카이"}, // 카이
		{"empty", "", ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := NormalizeEntityName(c.in); got != c.want {
				t.Errorf("NormalizeEntityName(%q) = %q, want %q", c.in, got, c.want)
			}
		})
	}
}

// Accents fold ENCODING but NOT identity: má (a + acute) and ma stay distinct
// (no accent strip), while composed vs decomposed má DO collapse (NFKC).
func TestAccentsPreserved(t *testing.T) {
	composed := "má"   // á as one codepoint
	decomposed := "má" // a + combining acute
	plain := "ma"

	if NormalizeEntityName(composed) == NormalizeEntityName(plain) {
		t.Error("má and ma must NOT collapse (accent strip would over-merge)")
	}
	if NormalizeEntityName(composed) != NormalizeEntityName(decomposed) {
		t.Errorf("composed %q and decomposed %q má must collapse via NFKC", composed, decomposed)
	}
}

func TestStAndStableEquivalence(t *testing.T) {
	trad := "張若塵" // 張若塵
	simp := "张若尘" // 张若尘
	other := "八王子" // 八王子
	if NormalizeEntityName(trad) != NormalizeEntityName(simp) {
		t.Error("traditional and simplified must share a key")
	}
	if NormalizeEntityName(other) == NormalizeEntityName(simp) {
		t.Error("a distinct name must stay distinct")
	}
}

func TestHasHanGate(t *testing.T) {
	if HasHan("Kai") || HasHan("カイ") || HasHan("카이") {
		t.Error("HasHan must be false for non-Han text (kana/hangul are not Han)")
	}
	if !HasHan("張") || !HasHan("a張b") {
		t.Error("HasHan must be true when a Han ideograph is present")
	}
}

// TestT2SParityWithSoT guards the generated table against drift from the shared
// source of truth (sdks/data/han_t2s.tsv), which is also the Python dict's SoT.
// A stale t2s_table.go (forgot to `go generate`) fails here.
func TestT2SParityWithSoT(t *testing.T) {
	f, err := os.Open("../../data/han_t2s.tsv")
	if err != nil {
		t.Fatalf("open SoT tsv: %v", err)
	}
	defer f.Close()

	sot := map[rune]rune{}
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		if strings.HasPrefix(line, "#") || strings.TrimSpace(line) == "" {
			continue
		}
		cols := strings.Split(line, "\t")
		if len(cols) != 2 {
			t.Fatalf("bad SoT line %q", line)
		}
		tr, sr := []rune(cols[0]), []rune(cols[1])
		if len(tr) != 1 || len(sr) != 1 {
			t.Fatalf("each side must be one rune: %q", line)
		}
		sot[tr[0]] = sr[0]
	}
	if err := sc.Err(); err != nil {
		t.Fatalf("scan SoT: %v", err)
	}

	if len(sot) != len(T2S) {
		t.Fatalf("table drift: SoT has %d pairs, generated T2S has %d — run `go generate`", len(sot), len(T2S))
	}
	for k, v := range sot {
		if got, ok := T2S[k]; !ok || got != v {
			t.Errorf("table drift at 0x%04X: SoT=0x%04X generated=0x%04X (ok=%v) — run `go generate`", k, v, got, ok)
		}
	}
}

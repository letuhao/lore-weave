package shortdesc

import (
	"strings"
	"testing"
	"unicode/utf8"
)

func TestGenerate_EmptyDescriptionFallsBackToKindAndName(t *testing.T) {
	got := Generate("Kai", "", "character", 150)
	want := "character: Kai"
	if got != want {
		t.Errorf("want %q, got %q", want, got)
	}
}

func TestGenerate_EmptyKind(t *testing.T) {
	got := Generate("Kai", "", "", 150)
	if got != "Kai" {
		t.Errorf("want %q, got %q", "Kai", got)
	}
}

func TestGenerate_EmptyNameAndDescription(t *testing.T) {
	got := Generate("", "", "character", 150)
	if got != "character:" && got != "(unnamed)" && got != "character" {
		t.Errorf("unexpected: %q", got)
	}
}

func TestGenerate_ShortDescriptionReturnedVerbatim(t *testing.T) {
	desc := "A wandering swordsman of the Jianghu."
	got := Generate("Kai", desc, "character", 150)
	if got != desc {
		t.Errorf("want %q, got %q", desc, got)
	}
}

func TestGenerate_FirstSentenceWhenMultipleSentences(t *testing.T) {
	desc := "A wandering swordsman. His blade is legendary. Everyone fears him."
	got := Generate("Kai", desc, "character", 150)
	want := "A wandering swordsman."
	if got != want {
		t.Errorf("want %q, got %q", want, got)
	}
}

func TestGenerate_CJKFirstSentence(t *testing.T) {
	desc := "一位神秘的刀客。他的刀法無人能敵。"
	got := Generate("李雲", desc, "角色", 150)
	want := "一位神秘的刀客。"
	if got != want {
		t.Errorf("want %q, got %q", want, got)
	}
}

func TestGenerate_CJKEmptyDescription(t *testing.T) {
	got := Generate("李雲", "", "角色", 150)
	want := "角色: 李雲"
	if got != want {
		t.Errorf("want %q, got %q", want, got)
	}
}

func TestGenerate_TruncateAtWordBoundaryWithEllipsis(t *testing.T) {
	// One long sentence with no terminator, well over maxChars.
	desc := "A very long description that rambles on and on about various unrelated topics without ever reaching a proper sentence terminator in a timely fashion which really is unfortunate"
	got := Generate("Kai", desc, "character", 50)
	if utf8.RuneCountInString(got) > 50 {
		t.Errorf("length %d > 50: %q", utf8.RuneCountInString(got), got)
	}
	if !strings.HasSuffix(got, "…") {
		t.Errorf("expected trailing ellipsis, got %q", got)
	}
	if strings.Contains(got, "  ") {
		t.Errorf("should not have double space: %q", got)
	}
}

func TestGenerate_TruncateCJKHardCut(t *testing.T) {
	// Long CJK run with no spaces — fall back to rune boundary cut.
	desc := strings.Repeat("甲乙丙丁戊己庚辛壬癸", 30) // 300 runes
	got := Generate("李雲", desc, "角色", 40)
	if utf8.RuneCountInString(got) > 40 {
		t.Errorf("length %d > 40: %q", utf8.RuneCountInString(got), got)
	}
	if !strings.HasSuffix(got, "…") {
		t.Errorf("expected trailing ellipsis, got %q", got)
	}
}

func TestGenerate_FirstSentenceLongerThanMaxTriggersTruncate(t *testing.T) {
	// A single very long sentence — first-sentence rule doesn't apply
	// because the sentence exceeds maxChars. Must fall through to truncate.
	desc := "This is one enormous sentence with absolutely no early terminator that goes on and on and on for well beyond any reasonable character limit we might set."
	got := Generate("Kai", desc, "character", 40)
	if utf8.RuneCountInString(got) > 40 {
		t.Errorf("length %d > 40: %q", utf8.RuneCountInString(got), got)
	}
	if !strings.HasSuffix(got, "…") {
		t.Errorf("expected trailing ellipsis, got %q", got)
	}
}

func TestGenerate_MixedASCIIAndCJKTerminators(t *testing.T) {
	desc := "Hero of the story。 Also has a horse."
	got := Generate("Kai", desc, "character", 150)
	want := "Hero of the story。"
	if got != want {
		t.Errorf("want %q, got %q", want, got)
	}
}

func TestGenerate_WhitespaceOnlyDescription(t *testing.T) {
	got := Generate("Kai", "   \t\n  ", "character", 150)
	want := "character: Kai"
	if got != want {
		t.Errorf("want %q, got %q", want, got)
	}
}

func TestGenerate_ZeroMaxUsesDefault(t *testing.T) {
	desc := strings.Repeat("x ", 100) // 200 chars
	got := Generate("Kai", desc, "character", 0)
	if utf8.RuneCountInString(got) > DefaultMaxChars {
		t.Errorf("length %d > %d", utf8.RuneCountInString(got), DefaultMaxChars)
	}
}

func TestGenerate_NeverExceedsMaxChars(t *testing.T) {
	cases := []struct {
		name, desc, kind string
		max              int
	}{
		{"short", "hello", "kind", 10},
		{"exact", strings.Repeat("a", 150), "kind", 150},
		{"over", strings.Repeat("ab ", 100), "kind", 50},
		{"cjk", strings.Repeat("字", 200), "种类", 40},
		{"cjk-mixed", "Alice 李雲 " + strings.Repeat("字", 100), "character", 30},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := Generate(c.name, c.desc, c.kind, c.max)
			if n := utf8.RuneCountInString(got); n > c.max {
				t.Errorf("%s: length %d > %d: %q", c.name, n, c.max, got)
			}
		})
	}
}

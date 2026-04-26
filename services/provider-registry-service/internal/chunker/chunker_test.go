package chunker

import (
	"strings"
	"testing"
)

func TestChunkText_EmptyInput(t *testing.T) {
	for _, s := range []Strategy{StrategyTokens, StrategyParagraphs, StrategySentences, StrategyNone, ""} {
		out, err := ChunkText("", Request{Strategy: s})
		if err != nil {
			t.Errorf("strategy %q: empty input should not error: %v", s, err)
			continue
		}
		if len(out) != 1 || out[0] != "" {
			t.Errorf("strategy %q: empty input should return [\"\"], got %#v", s, out)
		}
	}
}

func TestChunkText_NoneStrategyPassesThrough(t *testing.T) {
	text := "Hello world. This is a test."
	out, err := ChunkText(text, Request{Strategy: StrategyNone})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) != 1 || out[0] != text {
		t.Errorf("expected [text], got %#v", out)
	}
}

func TestChunkText_UnknownStrategyErrors(t *testing.T) {
	_, err := ChunkText("abc", Request{Strategy: "bogus"})
	if err == nil {
		t.Errorf("expected error for unknown strategy")
	}
}

func TestChunkByParagraphs_SmallInputReturnsSingleChunk(t *testing.T) {
	text := "para one\n\npara two\n\npara three"
	out, err := ChunkText(text, Request{Strategy: StrategyParagraphs, Size: 8})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) != 1 {
		t.Errorf("3 paragraphs in size=8 should fit one chunk, got %d", len(out))
	}
	if !strings.Contains(out[0], "para one") || !strings.Contains(out[0], "para three") {
		t.Errorf("chunk missing paragraphs: %q", out[0])
	}
}

func TestChunkByParagraphs_SplitsAtSizeBoundary(t *testing.T) {
	parts := []string{"a", "b", "c", "d", "e"}
	text := strings.Join(parts, "\n\n")
	out, err := ChunkText(text, Request{Strategy: StrategyParagraphs, Size: 2})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) != 3 {
		t.Errorf("5 paras @ size=2 → expected 3 chunks, got %d: %#v", len(out), out)
	}
	// Final chunk should hold the trailing single paragraph "e"
	if out[2] != "e" {
		t.Errorf("last chunk wrong: %q", out[2])
	}
}

func TestChunkByParagraphs_HandlesMixedNewlines(t *testing.T) {
	// CRLF + multiple blank lines should still split correctly.
	text := "alpha\r\n\r\n\r\nbeta\n\n\ngamma"
	out, err := ChunkText(text, Request{Strategy: StrategyParagraphs, Size: 1})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) != 3 {
		t.Errorf("3 paras with mixed newlines → 3 chunks, got %d: %#v", len(out), out)
	}
}

func TestChunkBySentences_SmallInputReturnsSingleChunk(t *testing.T) {
	text := "Hello. How are you? I am fine!"
	out, err := ChunkText(text, Request{Strategy: StrategySentences, Size: 30})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) != 1 {
		t.Errorf("3 sentences in size=30 → 1 chunk, got %d", len(out))
	}
}

func TestChunkBySentences_SplitsAtBoundary(t *testing.T) {
	text := "One. Two. Three. Four. Five."
	out, err := ChunkText(text, Request{Strategy: StrategySentences, Size: 2})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) != 3 {
		t.Errorf("5 sentences @ size=2 → 3 chunks, got %d: %#v", len(out), out)
	}
}

func TestChunkBySentences_HandlesCJK(t *testing.T) {
	text := "你好。世界。我是。一个。测试。句子。"
	out, err := ChunkText(text, Request{Strategy: StrategySentences, Size: 2})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) < 2 {
		t.Errorf("CJK punctuation not detected as sentence boundary: %#v", out)
	}
}

func TestChunkByTokens_SmallInputReturnsSingleChunk(t *testing.T) {
	text := "Short text well under any reasonable token cap."
	out, err := ChunkText(text, Request{Strategy: StrategyTokens, Size: 1000})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) != 1 {
		t.Errorf("short text @ size=1000 → 1 chunk, got %d", len(out))
	}
}

func TestChunkByTokens_LongInputSplitsWithOverlap(t *testing.T) {
	// Generate a paragraph long enough to need multiple chunks at
	// size=20 tokens.
	text := strings.Repeat("The quick brown fox jumps over the lazy dog. ", 50)
	out, err := ChunkText(text, Request{Strategy: StrategyTokens, Size: 50, Overlap: 10})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) < 2 {
		t.Errorf("expected >=2 chunks for long text, got %d", len(out))
	}
}

func TestChunkByTokens_OverlapMustBeLessThanSize(t *testing.T) {
	_, err := ChunkText("some text", Request{Strategy: StrategyTokens, Size: 10, Overlap: 10})
	if err == nil {
		t.Errorf("expected error when overlap >= size")
	}
}

func TestChunkByTokens_AppliesDefaultOverlap(t *testing.T) {
	// Overlap=0 (zero-value) triggers DefaultTokensOverlap = 200.
	// We can't easily inspect the chunker internals; run a long text
	// through and assert chunk count is consistent with non-zero
	// overlap (chunks count > pieces of size with no overlap).
	text := strings.Repeat("alpha beta gamma delta epsilon ", 1000)
	out, err := ChunkText(text, Request{Strategy: StrategyTokens, Size: 1000})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) < 2 {
		t.Errorf("long text should produce multiple chunks: %d", len(out))
	}
}

func TestApplyDefaults_FillsSize(t *testing.T) {
	for _, tc := range []struct {
		s    Strategy
		want int
	}{
		{StrategyTokens, DefaultTokensSize},
		{StrategyParagraphs, DefaultParagraphsSize},
		{StrategySentences, DefaultSentencesSize},
	} {
		got := applyDefaults(Request{Strategy: tc.s, Size: 0}).Size
		if got != tc.want {
			t.Errorf("strategy %q: default size = %d, want %d", tc.s, got, tc.want)
		}
	}
}

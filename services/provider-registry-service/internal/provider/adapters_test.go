package provider

import (
	"net/http"
	"testing"
)

func TestResolveAdapter(t *testing.T) {
	t.Parallel()

	client := &http.Client{}
	kinds := []string{"openai", "anthropic", "ollama", "lm_studio"}
	for _, kind := range kinds {
		kind := kind
		t.Run(kind, func(t *testing.T) {
			t.Parallel()
			adapter, err := ResolveAdapter(kind, client)
			if err != nil {
				t.Fatalf("expected adapter for %s, got error: %v", kind, err)
			}
			if adapter == nil {
				t.Fatalf("adapter is nil for %s", kind)
			}
		})
	}
}

func TestResolveAdapterUnknown(t *testing.T) {
	t.Parallel()

	adapter, err := ResolveAdapter("unknown", &http.Client{})
	if err == nil {
		t.Fatal("expected error for unknown provider kind")
	}
	if adapter != nil {
		t.Fatal("adapter must be nil for unknown provider kind")
	}
}

func TestExtractMessages_ExplicitMessages(t *testing.T) {
	t.Parallel()

	msgs := extractMessages(map[string]any{
		"messages": []map[string]any{{"role": "user", "content": "hello"}},
	})
	if len(msgs) != 1 || msgs[0]["content"] != "hello" {
		t.Fatalf("unexpected messages: %v", msgs)
	}
}

func TestExtractMessages_Fallback(t *testing.T) {
	t.Parallel()

	msgs := extractMessages(map[string]any{})
	if len(msgs) != 1 || msgs[0]["role"] != "user" {
		t.Fatalf("expected fallback message, got: %v", msgs)
	}
}

func TestToFloat(t *testing.T) {
	t.Parallel()

	if toFloat(float64(3.5)) != 3.5 {
		t.Fatal("float64")
	}
	if toFloat(int(5)) != 5 {
		t.Fatal("int")
	}
	if toFloat(int64(7)) != 7 {
		t.Fatal("int64")
	}
	if toFloat(nil) != 0 {
		t.Fatal("nil")
	}
}

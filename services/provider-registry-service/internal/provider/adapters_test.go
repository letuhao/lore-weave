package provider

import (
	"context"
	"testing"
)

func TestResolveAdapter(t *testing.T) {
	t.Parallel()

	kinds := []string{"openai", "anthropic", "ollama", "lm_studio"}
	for _, kind := range kinds {
		kind := kind
		t.Run(kind, func(t *testing.T) {
			t.Parallel()
			adapter, err := ResolveAdapter(kind)
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

	adapter, err := ResolveAdapter("unknown")
	if err == nil {
		t.Fatal("expected error for unknown provider kind")
	}
	if adapter != nil {
		t.Fatal("adapter must be nil for unknown provider kind")
	}
}

func TestStaticAdapterInvokePromptFallback(t *testing.T) {
	t.Parallel()

	adapter := OpenAIAdapter()
	output, usage, err := adapter.Invoke(context.Background(), "", "", "gpt-4o-mini", map[string]any{
		"prompt": "hello world",
	})
	if err != nil {
		t.Fatalf("invoke failed: %v", err)
	}
	if output["model"] != "gpt-4o-mini" {
		t.Fatalf("unexpected model in output: %v", output["model"])
	}
	if usage.InputTokens != 2 {
		t.Fatalf("expected input tokens=2, got %d", usage.InputTokens)
	}
	if usage.OutputTokens != 10 {
		t.Fatalf("expected output tokens=10, got %d", usage.OutputTokens)
	}
}

func TestStaticAdapterInvokeInputFallbackAndMinToken(t *testing.T) {
	t.Parallel()

	adapter := AnthropicAdapter()
	_, usage, err := adapter.Invoke(context.Background(), "", "", "claude-3-5-sonnet", map[string]any{
		"input": "",
	})
	if err != nil {
		t.Fatalf("invoke failed: %v", err)
	}
	if usage.InputTokens != 1 {
		t.Fatalf("expected min input tokens=1, got %d", usage.InputTokens)
	}
	if usage.OutputTokens != 9 {
		t.Fatalf("expected output tokens=9, got %d", usage.OutputTokens)
	}
}

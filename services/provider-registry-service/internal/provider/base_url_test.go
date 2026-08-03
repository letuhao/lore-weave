package provider

import "testing"

func TestNormalizeOpenAICompatibleBase(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   string
		want string
	}{
		{"empty", "", ""},
		{"plain", "https://api.neuraldeep.ru", "https://api.neuraldeep.ru"},
		{"plain trailing slash", "https://api.neuraldeep.ru/", "https://api.neuraldeep.ru"},
		{"v1", "https://api.neuraldeep.ru/v1", "https://api.neuraldeep.ru"},
		{"v1 trailing slash", "https://api.neuraldeep.ru/v1/", "https://api.neuraldeep.ru"},
		{"nested v1", "https://openrouter.ai/api/v1", "https://openrouter.ai/api"},
		{"do not strip v10", "https://example.test/v10", "https://example.test/v10"},
		{"do not strip v1beta", "https://example.test/v1beta", "https://example.test/v1beta"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if got := normalizeOpenAICompatibleBase(tt.in); got != tt.want {
				t.Fatalf("normalizeOpenAICompatibleBase(%q) = %q; want %q", tt.in, got, tt.want)
			}
		})
	}
}

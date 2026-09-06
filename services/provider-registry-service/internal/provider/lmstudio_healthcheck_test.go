package provider

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// 🔴 THE SAME DEFECT THE OLLAMA ADAPTER WAS FIXED FOR ON 2026-09-01, LEFT LIVE ON ITS SIBLING.
//
// ollama's HealthCheck used to call Invoke with an EMPTY model name; the fix lists the endpoint's
// models and names one. That repair was never ported here, so lmStudioAdapter.HealthCheck went on
// sending `""`. This is the recurring shape in this file — a repair lands on the adapter it was
// found on and its siblings keep the defect — and it is why these assertions are written against
// the BEHAVIOUR (what reached the wire) rather than against the call.
//
// 🔴 AND ON LM STUDIO THE EMPTY NAME IS NOT THE WORST OF IT. LM Studio loads models ON DEMAND, so
// any health check that asks for a completion makes the host load one — the local target here is a
// 26B — and a probe meant to ask "are you there?" pins the GPU instead. Reachability is the whole
// question for a keyless local server, so the check must not buy a completion at all.

func newLmStudioTestAdapter() *lmStudioAdapter {
	return &lmStudioAdapter{client: &http.Client{}}
}

func lmStudioModelsHandler(t *testing.T, seen *[]string, chatModel *string) http.HandlerFunc {
	t.Helper()
	return func(w http.ResponseWriter, r *http.Request) {
		*seen = append(*seen, r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/v1/models" || r.URL.Path == "/models":
			_, _ = w.Write([]byte(`{"data":[{"id":"gemma-4-26b-qat"}]}`))
		case r.URL.Path == "/v1/chat/completions" || r.URL.Path == "/chat/completions":
			var body map[string]any
			_ = json.NewDecoder(r.Body).Decode(&body)
			if chatModel != nil {
				*chatModel, _ = body["model"].(string)
			}
			_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}],` +
				`"usage":{"prompt_tokens":1,"completion_tokens":1}}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}
}

// THE FALSIFIER, on the original instance: a keyless local LM Studio must be judged healthy
// WITHOUT a completion, so nothing can be sent with an empty model name.
func TestLmStudioHealthCheckDoesNotBuyACompletionForAKeylessLocalServer(t *testing.T) {
	var paths []string
	var chatModel string
	srv := httptest.NewServer(lmStudioModelsHandler(t, &paths, &chatModel))
	defer srv.Close()

	u, err := newLmStudioTestAdapter().HealthCheck(context.Background(), srv.URL, "")
	if err != nil {
		t.Fatalf("HealthCheck (local, keyless): %v", err)
	}
	if len(paths) == 0 {
		t.Fatal("the adapter never reached the server — every assertion below would be vacuous")
	}
	completed := false
	for _, p := range paths {
		if p == "/v1/chat/completions" || p == "/chat/completions" {
			completed = true
			t.Error("the probe asked for a COMPLETION on a keyless local server. There is no " +
				"credential to prove, and LM Studio loads a model on demand — so this pins the " +
				"GPU loading a 26B model every time something checks whether the host is up")
		}
	}
	// Belt and braces, and ONLY meaningful if a completion actually happened: an unnamed one is
	// the original defect. Guarded on `completed` because in the fixed behaviour no completion is
	// sent at all, and an empty chatModel is then the correct observation rather than a failure.
	if completed && chatModel == "" {
		t.Error("a completion was sent with an EMPTY model name — the original defect")
	}
	if u.InputTokens != 0 || u.OutputTokens != 0 {
		t.Errorf("reported usage %+v for a probe that ran no completion — a non-zero figure "+
			"here would put invented spend in the ledger", u)
	}
}

// The mirror, and the reason the completion arm is kept at all: LM Studio can sit behind a proxy
// that DOES require a key. Then reachability is not the question and only a completion
// discriminates — the finding recorded on the ollama adapter, where both listing endpoints
// answered 200 to a bogus key. It must name a real model.
func TestLmStudioHealthCheckNamesARealModelWhenItMustProveACredential(t *testing.T) {
	var paths []string
	var chatModel string
	srv := httptest.NewServer(lmStudioModelsHandler(t, &paths, &chatModel))
	defer srv.Close()

	if _, err := newLmStudioTestAdapter().HealthCheck(
		context.Background(), srv.URL, "sk-test"); err != nil {
		t.Fatalf("HealthCheck (keyed): %v", err)
	}
	if chatModel == "" {
		t.Fatal("🔴 THE ORIGINAL DEFECT: the completion was sent with an EMPTY model name. " +
			"On the ollama sibling this produced `404 model '' not found` and reported a " +
			"working provider unhealthy")
	}
	if chatModel != "gemma-4-26b-qat" {
		t.Errorf("model = %q, want the one the endpoint said it serves", chatModel)
	}
}

func TestLmStudioHealthCheckFAILSWhenTheCredentialIsRejected(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/v1/models" || r.URL.Path == "/models" {
			_, _ = w.Write([]byte(`{"data":[{"id":"gemma-4-26b-qat"}]}`))
			return
		}
		// 🔴 THE TEETH. Listing succeeds and only the completion fails, which is exactly how a
		// proxied LM Studio behaves with a bad key. A check that passed here would be the
		// guard-that-cannot-fail this fix exists to avoid.
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"error":"Unauthorized"}`))
	}))
	defer srv.Close()

	if _, err := newLmStudioTestAdapter().HealthCheck(
		context.Background(), srv.URL, "bogus"); err == nil {
		t.Fatal("HealthCheck reported HEALTHY on a credential the endpoint rejected")
	}
}

func TestLmStudioHealthCheckFAILSWhenTheEndpointServesNoModels(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[]}`))
	}))
	defer srv.Close()

	// A reachable host with nothing loaded is not a usable provider, and saying "healthy" here
	// sends the caller to a model that does not exist.
	if _, err := newLmStudioTestAdapter().HealthCheck(
		context.Background(), srv.URL, ""); err == nil {
		t.Error("reported HEALTHY for an endpoint serving no models")
	}
}

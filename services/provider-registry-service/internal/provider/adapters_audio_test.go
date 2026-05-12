package provider

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"mime/multipart"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

// stubIPLookuper — Phase 5a /review-impl MED#2 test infra. Replaces
// audioURLResolver during a test so httptest.Server (on 127.0.0.1) can
// be exercised without the SSRF guard rejecting it. Returns a "pretend
// public" IP (8.8.8.8) regardless of host, except when fakeErr is set.
type stubIPLookuper struct {
	publicIP net.IP
	fakeErr  error
	// If returnPrivateIP is non-nil, return that private IP so the
	// SSRF guard fires — used by the disallowed-IP test.
	returnPrivateIP net.IP
}

func (s *stubIPLookuper) LookupIP(_ context.Context, _, host string) ([]net.IP, error) {
	_ = host
	if s.fakeErr != nil {
		return nil, s.fakeErr
	}
	if s.returnPrivateIP != nil {
		return []net.IP{s.returnPrivateIP}, nil
	}
	return []net.IP{s.publicIP}, nil
}

// useStubResolver installs the stub for the test, restoring on Cleanup.
// Default stub returns 8.8.8.8 (public) — caller can override per test.
func useStubResolver(t *testing.T, stub audioIPLookuper) {
	t.Helper()
	orig := audioURLResolver
	audioURLResolver = stub
	t.Cleanup(func() { audioURLResolver = orig })
}

func usePublicResolver(t *testing.T) {
	useStubResolver(t, &stubIPLookuper{publicIP: net.ParseIP("8.8.8.8")})
}

// TestAdaptersAudioInitiallyUnsupported pins the Phase 5a starting-line:
// every adapter's Transcribe + Speak method MUST return ErrOperationNotSupported
// (not a wrapped error, not a different sentinel) until a real
// implementation lands. This test prevents silent partial implementations
// from leaking — the OpenAI test in openai_audio_test.go (T4+) overrides
// this assertion for the openaiAdapter once T5/T8 ship.
func TestAdaptersAudioInitiallyUnsupported(t *testing.T) {
	cases := []struct {
		name    string
		adapter Adapter
		// includeOpenAI: keep false until OpenAI Transcribe + Speak land in
		// openai_audio.go. Once they do, drop the openaiAdapter from this
		// table — its expected behavior becomes "happy path" (covered by
		// the per-method tests).
	}{
		{name: "anthropic", adapter: &anthropicAdapter{}},
		{name: "ollama", adapter: &ollamaAdapter{}},
		{name: "lmStudio", adapter: &lmStudioAdapter{}},
	}

	ctx := context.Background()
	for _, tc := range cases {
		t.Run(tc.name+"/Transcribe", func(t *testing.T) {
			_, _, err := tc.adapter.Transcribe(ctx, "https://upstream.example", "secret", "model", TranscribeInput{})
			if !errors.Is(err, ErrOperationNotSupported) {
				t.Fatalf("expected ErrOperationNotSupported, got %v", err)
			}
		})
		t.Run(tc.name+"/Speak", func(t *testing.T) {
			emit := func(AudioChunk) error { return nil }
			err := tc.adapter.Speak(ctx, "https://upstream.example", "secret", "model", SpeakInput{}, emit)
			if !errors.Is(err, ErrOperationNotSupported) {
				t.Fatalf("expected ErrOperationNotSupported, got %v", err)
			}
		})
	}
}

// ── OpenAI Transcribe (T4-T6) ─────────────────────────────────────────

// dummyAudioBytes is the synthetic audio payload returned by the audio_url
// mock server. The exact bytes don't matter for unit tests — the adapter
// just streams them into the upstream multipart upload. We use a stable
// 16-byte sequence so multipart-shape assertions can reference it.
var dummyAudioBytes = []byte("RIFF\x00\x00\x00\x00WAVE\x00\x00\x00\x00")

// audioFixtureServer returns an httptest.Server that serves dummyAudioBytes
// at the root path with a stable Content-Type. Caller closes via defer.
func audioFixtureServer(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "audio/wav")
		w.Header().Set("Content-Length", "16")
		_, _ = w.Write(dummyAudioBytes)
	}))
}

func TestOpenAIAdapter_Transcribe_HappyPath(t *testing.T) {
	usePublicResolver(t)
	audioSrv := audioFixtureServer(t)
	defer audioSrv.Close()

	var (
		gotMethod      string
		gotPath        string
		gotAuth        string
		gotModel       string
		gotLanguage    string
		gotResponseFmt string
		gotFileBytes   []byte
		gotFileName    string
		gotContentType string
	)
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		gotContentType = r.Header.Get("Content-Type")

		// Parse multipart body
		mr, err := r.MultipartReader()
		if err != nil {
			t.Errorf("MultipartReader: %v", err)
			http.Error(w, err.Error(), 500)
			return
		}
		for {
			part, perr := mr.NextPart()
			if perr == io.EOF {
				break
			}
			if perr != nil {
				t.Errorf("NextPart: %v", perr)
				return
			}
			name := part.FormName()
			body, _ := io.ReadAll(part)
			switch name {
			case "model":
				gotModel = string(body)
			case "language":
				gotLanguage = string(body)
			case "response_format":
				gotResponseFmt = string(body)
			case "file":
				gotFileBytes = body
				gotFileName = part.FileName()
			}
		}

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"text": "hello world this is a test",
			"language": "english",
			"duration": 2.345
		}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	out, _, err := a.Transcribe(
		context.Background(),
		openaiSrv.URL,
		"sk-test-key",
		"whisper-1",
		TranscribeInput{AudioURL: audioSrv.URL + "/audio.wav", Language: "en"},
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Output assertions
	if out.Text != "hello world this is a test" {
		t.Errorf("Text=%q, want %q", out.Text, "hello world this is a test")
	}
	if out.Language != "english" {
		t.Errorf("Language=%q, want %q", out.Language, "english")
	}
	if out.DurationMs != 2345 {
		t.Errorf("DurationMs=%d, want 2345", out.DurationMs)
	}

	// Wire-shape assertions
	if gotMethod != http.MethodPost {
		t.Errorf("upstream method=%s, want POST", gotMethod)
	}
	if gotPath != "/v1/audio/transcriptions" {
		t.Errorf("upstream path=%s, want /v1/audio/transcriptions", gotPath)
	}
	if gotAuth != "Bearer sk-test-key" {
		t.Errorf("Authorization=%q, want %q", gotAuth, "Bearer sk-test-key")
	}
	if !strings.HasPrefix(gotContentType, "multipart/form-data") {
		t.Errorf("upstream Content-Type=%q, want multipart/form-data prefix", gotContentType)
	}
	if gotModel != "whisper-1" {
		t.Errorf("model field=%q, want whisper-1", gotModel)
	}
	if gotLanguage != "en" {
		t.Errorf("language field=%q, want en", gotLanguage)
	}
	if gotResponseFmt != "verbose_json" {
		t.Errorf("response_format=%q, want verbose_json", gotResponseFmt)
	}
	if string(gotFileBytes) != string(dummyAudioBytes) {
		t.Errorf("file bytes mismatch: got %q, want %q", gotFileBytes, dummyAudioBytes)
	}
	if gotFileName == "" {
		t.Error("file part has empty filename")
	}
}

func TestOpenAIAdapter_Transcribe_LanguageAutoOmitsParam(t *testing.T) {
	usePublicResolver(t)
	audioSrv := audioFixtureServer(t)
	defer audioSrv.Close()

	var sawLanguageField int32 // atomic flag — was the multipart `language` part present?
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mr, err := r.MultipartReader()
		if err != nil {
			http.Error(w, err.Error(), 500)
			return
		}
		for {
			part, perr := mr.NextPart()
			if perr == io.EOF {
				break
			}
			if perr != nil {
				return
			}
			if part.FormName() == "language" {
				atomic.StoreInt32(&sawLanguageField, 1)
			}
			_, _ = io.ReadAll(part)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"text":"ok","language":"english","duration":0}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.Transcribe(
		context.Background(),
		openaiSrv.URL,
		"sk-x",
		"whisper-1",
		TranscribeInput{AudioURL: audioSrv.URL + "/x.wav", Language: "auto"},
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if atomic.LoadInt32(&sawLanguageField) == 1 {
		t.Error("language=auto should omit the multipart `language` field; saw it present")
	}
}

func TestOpenAIAdapter_Transcribe_AudioFetch404(t *testing.T) {
	usePublicResolver(t)
	missingSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.NotFound(w, r)
	}))
	defer missingSrv.Close()

	// OpenAI server should never get hit
	openaiHit := int32(0)
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&openaiHit, 1)
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.Transcribe(
		context.Background(),
		openaiSrv.URL,
		"sk-x",
		"whisper-1",
		TranscribeInput{AudioURL: missingSrv.URL + "/missing.wav", Language: "auto"},
	)
	if !errors.Is(err, ErrAudioFetchFailed) {
		t.Fatalf("expected ErrAudioFetchFailed, got %v", err)
	}
	if atomic.LoadInt32(&openaiHit) != 0 {
		t.Error("upstream OpenAI MUST NOT be called when audio fetch fails")
	}
}

func TestOpenAIAdapter_Transcribe_AudioTooLarge(t *testing.T) {
	usePublicResolver(t)
	// Server returns 26MB of bytes — should be rejected at 25MB cap
	bigSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "audio/wav")
		// Stream 26MB of zeros
		buf := make([]byte, 1024*1024) // 1MB chunk
		for i := 0; i < 26; i++ {
			_, _ = w.Write(buf)
		}
	}))
	defer bigSrv.Close()

	openaiHit := int32(0)
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&openaiHit, 1)
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.Transcribe(
		context.Background(),
		openaiSrv.URL,
		"sk-x",
		"whisper-1",
		TranscribeInput{AudioURL: bigSrv.URL + "/big.wav"},
	)
	if !errors.Is(err, ErrAudioTooLarge) {
		t.Fatalf("expected ErrAudioTooLarge, got %v", err)
	}
	if atomic.LoadInt32(&openaiHit) != 0 {
		t.Error("upstream OpenAI MUST NOT be called when audio exceeds cap")
	}
}

func TestOpenAIAdapter_Transcribe_Upstream4xxWrapped(t *testing.T) {
	usePublicResolver(t)
	audioSrv := audioFixtureServer(t)
	defer audioSrv.Close()

	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"error":{"message":"invalid api key"}}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.Transcribe(
		context.Background(),
		openaiSrv.URL,
		"sk-bad",
		"whisper-1",
		TranscribeInput{AudioURL: audioSrv.URL + "/x.wav"},
	)
	if err == nil {
		t.Fatal("expected error from 401 upstream")
	}
	// Must NOT be ErrOperationNotSupported / ErrAudioFetchFailed / ErrAudioTooLarge —
	// those are reserved for the audio-fetch-side / capability-check failures.
	if errors.Is(err, ErrOperationNotSupported) {
		t.Errorf("upstream 401 should not map to ErrOperationNotSupported")
	}
	if errors.Is(err, ErrAudioFetchFailed) {
		t.Errorf("upstream 401 should not map to ErrAudioFetchFailed")
	}
	// /review-impl MED#3: 401 should classify as ErrUpstreamPermanent
	// with StatusCode=401 so callers can map to LLM_AUTH_FAILED.
	var perm *ErrUpstreamPermanent
	if !errors.As(err, &perm) {
		t.Fatalf("expected *ErrUpstreamPermanent, got %T: %v", err, err)
	}
	if perm.StatusCode != 401 {
		t.Errorf("StatusCode=%d, want 401", perm.StatusCode)
	}
}

// /review-impl MED#3 — Phase 5a — upstream 429 classifies as
// ErrUpstreamRateLimited with Retry-After preserved.
func TestOpenAIAdapter_Transcribe_Upstream429ClassifiesAsRateLimited(t *testing.T) {
	usePublicResolver(t)
	audioSrv := audioFixtureServer(t)
	defer audioSrv.Close()

	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Retry-After", "7")
		w.WriteHeader(http.StatusTooManyRequests)
		_, _ = w.Write([]byte(`{"error":"rate limit exceeded"}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.Transcribe(
		context.Background(),
		openaiSrv.URL,
		"sk-x",
		"whisper-1",
		TranscribeInput{AudioURL: audioSrv.URL + "/x.wav"},
	)
	var rl *ErrUpstreamRateLimited
	if !errors.As(err, &rl) {
		t.Fatalf("expected *ErrUpstreamRateLimited, got %T: %v", err, err)
	}
	if rl.StatusCode != 429 {
		t.Errorf("StatusCode=%d, want 429", rl.StatusCode)
	}
	if rl.RetryAfterS == nil || *rl.RetryAfterS != 7.0 {
		t.Errorf("RetryAfterS=%v, want 7.0", rl.RetryAfterS)
	}
}

// /review-impl MED#3 — Phase 5a — upstream 502/503/504 classifies as
// ErrUpstreamTransient (caller can retry).
func TestOpenAIAdapter_Transcribe_Upstream5xxClassifiesAsTransient(t *testing.T) {
	usePublicResolver(t)
	audioSrv := audioFixtureServer(t)
	defer audioSrv.Close()

	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte("upstream blip"))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.Transcribe(
		context.Background(),
		openaiSrv.URL,
		"sk-x",
		"whisper-1",
		TranscribeInput{AudioURL: audioSrv.URL + "/x.wav"},
	)
	var trans *ErrUpstreamTransient
	if !errors.As(err, &trans) {
		t.Fatalf("expected *ErrUpstreamTransient, got %T: %v", err, err)
	}
	if trans.StatusCode != 502 {
		t.Errorf("StatusCode=%d, want 502", trans.StatusCode)
	}
}

// /review-impl MED#2 — Phase 5a — SSRF guard rejects hostnames that
// resolve to disallowed (loopback / private / link-local) IPs.
func TestOpenAIAdapter_Transcribe_SSRF_DisallowedIPRejected(t *testing.T) {
	// Stub resolver returns 169.254.169.254 (AWS IMDS — link-local).
	useStubResolver(t, &stubIPLookuper{
		returnPrivateIP: net.ParseIP("169.254.169.254"),
	})
	openaiHit := int32(0)
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&openaiHit, 1)
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	_, _, err := a.Transcribe(
		context.Background(),
		openaiSrv.URL,
		"sk-x",
		"whisper-1",
		TranscribeInput{AudioURL: "https://attacker.test/audio.wav"},
	)
	if !errors.Is(err, ErrAudioURLDisallowed) {
		t.Fatalf("expected ErrAudioURLDisallowed, got %v", err)
	}
	if atomic.LoadInt32(&openaiHit) != 0 {
		t.Error("upstream MUST NOT be called when SSRF guard rejects audio_url")
	}
}

func TestOpenAIAdapter_Transcribe_SSRF_LoopbackRejected(t *testing.T) {
	useStubResolver(t, &stubIPLookuper{
		returnPrivateIP: net.ParseIP("127.0.0.1"),
	})
	a := &openaiAdapter{client: &http.Client{}}
	_, _, err := a.Transcribe(
		context.Background(),
		"http://upstream.test",
		"sk-x",
		"whisper-1",
		TranscribeInput{AudioURL: "https://attacker.test/audio.wav"},
	)
	if !errors.Is(err, ErrAudioURLDisallowed) {
		t.Fatalf("expected ErrAudioURLDisallowed for 127.0.0.1, got %v", err)
	}
}

func TestOpenAIAdapter_Transcribe_SSRF_RFC1918Rejected(t *testing.T) {
	useStubResolver(t, &stubIPLookuper{
		returnPrivateIP: net.ParseIP("10.0.0.1"),
	})
	a := &openaiAdapter{client: &http.Client{}}
	_, _, err := a.Transcribe(
		context.Background(),
		"http://upstream.test",
		"sk-x",
		"whisper-1",
		TranscribeInput{AudioURL: "https://attacker.test/audio.wav"},
	)
	if !errors.Is(err, ErrAudioURLDisallowed) {
		t.Fatalf("expected ErrAudioURLDisallowed for 10.0.0.1, got %v", err)
	}
}

// Non-http/https schemes still rejected (defense-in-depth — before DNS).
func TestOpenAIAdapter_Transcribe_RejectsNonHTTPScheme(t *testing.T) {
	a := &openaiAdapter{client: &http.Client{}}
	_, _, err := a.Transcribe(
		context.Background(),
		"http://upstream.test",
		"sk-x",
		"whisper-1",
		TranscribeInput{AudioURL: "file:///etc/passwd"},
	)
	if !errors.Is(err, ErrAudioURLDisallowed) {
		t.Fatalf("expected ErrAudioURLDisallowed, got %v", err)
	}
}

// silence unused imports when only some helpers are referenced by certain tests
var _ = multipart.NewWriter

// ── OpenAI Speak (T7-T9) ───────────────────────────────────────────────

func TestOpenAIAdapter_Speak_HappyPath(t *testing.T) {
	// Upstream returns 12KB body. Adapter reads in 4KB chunks → 3 data
	// emits + 1 final emit (total 4 emits). Sequence_id monotonic 0..3.
	const totalSize = 12 * 1024
	payload := bytes.Repeat([]byte{0xAB}, totalSize)

	var (
		gotMethod, gotPath, gotAuth, gotContentType string
		gotBody                                     map[string]any
	)
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		gotContentType = r.Header.Get("Content-Type")
		bodyBytes, _ := io.ReadAll(r.Body)
		_ = jsonUnmarshal(bodyBytes, &gotBody)
		w.Header().Set("Content-Type", "audio/mpeg")
		_, _ = w.Write(payload)
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	var emitted []AudioChunk
	emit := func(c AudioChunk) error {
		// Defensive copy — adapter MAY reuse its read buffer between emits.
		cp := make([]byte, len(c.Data))
		copy(cp, c.Data)
		emitted = append(emitted, AudioChunk{
			SequenceID: c.SequenceID,
			Data:       cp,
			Final:      c.Final,
		})
		return nil
	}
	err := a.Speak(
		context.Background(),
		openaiSrv.URL,
		"sk-test-key",
		"tts-1",
		SpeakInput{Text: "hello", Voice: "alloy", Speed: 1.0, Format: "mp3"},
		emit,
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Wire-shape assertions
	if gotMethod != http.MethodPost {
		t.Errorf("upstream method=%s, want POST", gotMethod)
	}
	if gotPath != "/v1/audio/speech" {
		t.Errorf("upstream path=%s, want /v1/audio/speech", gotPath)
	}
	if gotAuth != "Bearer sk-test-key" {
		t.Errorf("Authorization=%q", gotAuth)
	}
	if !strings.Contains(gotContentType, "application/json") {
		t.Errorf("Content-Type=%q, want application/json", gotContentType)
	}
	if gotBody["model"] != "tts-1" {
		t.Errorf("body.model=%v, want tts-1", gotBody["model"])
	}
	if gotBody["input"] != "hello" {
		t.Errorf("body.input=%v, want hello", gotBody["input"])
	}
	if gotBody["voice"] != "alloy" {
		t.Errorf("body.voice=%v, want alloy", gotBody["voice"])
	}
	if gotBody["response_format"] != "mp3" {
		t.Errorf("body.response_format=%v, want mp3", gotBody["response_format"])
	}

	// Emit-shape assertions: ≥1 data emit + exactly 1 final emit
	if len(emitted) < 2 {
		t.Fatalf("expected ≥2 emits (data + final), got %d", len(emitted))
	}
	finalCount := 0
	totalBytes := 0
	for i, c := range emitted {
		if c.SequenceID != i {
			t.Errorf("emit[%d].SequenceID=%d, want %d (monotonic)", i, c.SequenceID, i)
		}
		if c.Final {
			finalCount++
			if i != len(emitted)-1 {
				t.Errorf("Final=true at index %d but should only be at last (%d)", i, len(emitted)-1)
			}
			if len(c.Data) != 0 {
				t.Errorf("Final emit has non-empty Data (len=%d); should be empty sentinel", len(c.Data))
			}
		} else {
			totalBytes += len(c.Data)
		}
	}
	if finalCount != 1 {
		t.Errorf("expected exactly 1 final emit, got %d", finalCount)
	}
	if totalBytes != totalSize {
		t.Errorf("total streamed bytes=%d, want %d", totalBytes, totalSize)
	}
}

func TestOpenAIAdapter_Speak_EmitErrorAborts(t *testing.T) {
	const totalSize = 12 * 1024
	payload := bytes.Repeat([]byte{0xCC}, totalSize)
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "audio/mpeg")
		_, _ = w.Write(payload)
	}))
	defer openaiSrv.Close()

	abortErr := errors.New("client gone")
	emitCount := 0
	a := &openaiAdapter{client: openaiSrv.Client()}
	err := a.Speak(
		context.Background(),
		openaiSrv.URL,
		"sk-x",
		"tts-1",
		SpeakInput{Text: "x", Voice: "alloy", Speed: 1.0, Format: "mp3"},
		func(c AudioChunk) error {
			emitCount++
			// Abort on the first chunk
			return abortErr
		},
	)
	if !errors.Is(err, abortErr) {
		t.Fatalf("expected adapter to propagate emit error, got %v", err)
	}
	if emitCount > 2 {
		t.Errorf("emit called %d times after abort; should stop after the first failing emit", emitCount)
	}
}

func TestOpenAIAdapter_Speak_Upstream4xxClassifiesAsPermanent(t *testing.T) {
	// /review-impl MED#3 — Phase 5a: Speak now uses ClassifyUpstreamHTTP
	// so 4xx-except-429 returns *ErrUpstreamPermanent. Caller maps
	// 401/403 to LLM_AUTH_FAILED, other 4xx to LLM_UPSTREAM_ERROR.
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"error":{"message":"invalid voice"}}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	err := a.Speak(
		context.Background(),
		openaiSrv.URL,
		"sk-x",
		"tts-1",
		SpeakInput{Text: "hi", Voice: "bogus", Speed: 1.0, Format: "mp3"},
		func(AudioChunk) error { return nil },
	)
	if err == nil {
		t.Fatal("expected error from 400 upstream")
	}
	if errors.Is(err, ErrOperationNotSupported) {
		t.Errorf("400 should not map to ErrOperationNotSupported")
	}
	var perm *ErrUpstreamPermanent
	if !errors.As(err, &perm) {
		t.Fatalf("expected *ErrUpstreamPermanent, got %T: %v", err, err)
	}
	if perm.StatusCode != 400 {
		t.Errorf("StatusCode=%d, want 400", perm.StatusCode)
	}
}

// /review-impl MED#3 — Phase 5a — 429 on Speak classifies as
// ErrUpstreamRateLimited (caller maps to LLM_RATE_LIMITED in SSE error).
func TestOpenAIAdapter_Speak_Upstream429ClassifiesAsRateLimited(t *testing.T) {
	openaiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Retry-After", "12")
		w.WriteHeader(http.StatusTooManyRequests)
		_, _ = w.Write([]byte(`{"error":"slow down"}`))
	}))
	defer openaiSrv.Close()

	a := &openaiAdapter{client: openaiSrv.Client()}
	err := a.Speak(
		context.Background(),
		openaiSrv.URL,
		"sk-x",
		"tts-1",
		SpeakInput{Text: "hi", Voice: "alloy", Speed: 1.0, Format: "mp3"},
		func(AudioChunk) error { return nil },
	)
	var rl *ErrUpstreamRateLimited
	if !errors.As(err, &rl) {
		t.Fatalf("expected *ErrUpstreamRateLimited, got %T: %v", err, err)
	}
	if rl.StatusCode != 429 {
		t.Errorf("StatusCode=%d, want 429", rl.StatusCode)
	}
	if rl.RetryAfterS == nil || *rl.RetryAfterS != 12.0 {
		t.Errorf("RetryAfterS=%v, want 12.0", rl.RetryAfterS)
	}
}

// jsonUnmarshal: small wrapper to keep the adapter tests free of
// json import noise. Test-only helper.
func jsonUnmarshal(b []byte, v any) error {
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.UseNumber()
	return dec.Decode(v)
}

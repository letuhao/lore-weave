package provider

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// audioFetchTimeout — Phase 5a /review-impl HIGH#1. Inner timeout for the
// gateway-side GET of audio_url. Distinct from the worker-level
// SttJobTimeout: this caps the fetch step specifically so a slow audio
// server doesn't eat the whole STT budget before the upstream call.
const audioFetchTimeout = 30 * time.Second

// audioIPLookuper abstracts the SSRF DNS check for testability. Production
// binds it to net.DefaultResolver; tests inject a stub returning a
// "pretend public" IP so httptest.Server (on 127.0.0.1) exercises the
// guard logic without forcing tests onto an external DNS server.
//
// The http.Client.Do call still uses the URL's host directly via the
// stdlib resolver — only the SSRF check is mocked.
type audioIPLookuper interface {
	LookupIP(ctx context.Context, network, host string) ([]net.IP, error)
}

// audioURLResolver is the package-level lookup abstraction. Tests
// override via setAudioURLResolverForTest with t.Cleanup-managed restore.
var audioURLResolver audioIPLookuper = net.DefaultResolver

// isDisallowedIP returns true for IPs the SSRF guard must reject:
// loopback (127.0.0.0/8, ::1), private (RFC1918 + ULA), link-local
// (169.254.0.0/16, fe80::/10), unspecified (0.0.0.0, ::), and multicast
// (rejected to prevent service-discovery probes).
//
// /review-impl MED#2 — Phase 5a.
func isDisallowedIP(ip net.IP) bool {
	return ip.IsLoopback() ||
		ip.IsPrivate() ||
		ip.IsLinkLocalUnicast() ||
		ip.IsLinkLocalMulticast() ||
		ip.IsUnspecified() ||
		ip.IsMulticast() ||
		ip.IsInterfaceLocalMulticast()
}

// openai_audio.go — Phase 5a OpenAI implementations of the audio adapter
// methods (Transcribe, Speak). The stub versions live in adapters_audio.go;
// this file overrides the OpenAI ones via Go method-set replacement
// — i.e. the stubs are removed from adapters_audio.go in T5/T8 simultaneously.
//
// Wire-shape references:
//   - Transcribe: OpenAI Whisper /v1/audio/transcriptions (multipart)
//     https://platform.openai.com/docs/api-reference/audio/createTranscription
//   - Speak:      OpenAI TTS /v1/audio/speech (JSON in, audio bytes out)
//     https://platform.openai.com/docs/api-reference/audio/createSpeech
//
// The verifySTT/verifyTTS helpers in api/server.go test these endpoints
// for credential-registration; their HTTP shape is identical to what we
// build here, but they use synthetic local audio and don't need a
// fetch-from-URL step.

// MaxAudioBytes — Phase 5a. Hard cap on Transcribe input audio size,
// matching OpenAI Whisper's documented 25MB upload limit. Audio fetched
// from AudioURL beyond this is rejected with ErrAudioTooLarge before any
// upstream provider call.
const MaxAudioBytes = 25 * 1024 * 1024

// fetchAudioURL GETs the URL with the adapter's http.Client and returns
// the body bytes, capped at MaxAudioBytes. Returns ErrAudioFetchFailed
// for non-2xx responses and transport errors; ErrAudioTooLarge if the
// body would exceed the cap; ErrAudioURLDisallowed if hostname resolves
// to a private/loopback/link-local IP range (SSRF guard).
//
// /review-impl HIGH#1 — bounds the fetch with a 30s inner timeout
// derived from caller ctx, so a slow audio server fails fast even when
// the outer ctx is unbounded.
// /review-impl MED#2 — SSRF guard via DNS pre-resolve + private-range check.
func fetchAudioURL(ctx context.Context, client *http.Client, audioURL string) ([]byte, string, error) {
	if audioURL == "" {
		return nil, "", fmt.Errorf("%w: empty audio_url", ErrAudioFetchFailed)
	}
	parsed, perr := url.Parse(audioURL)
	if perr != nil {
		return nil, "", fmt.Errorf("%w: parse url: %v", ErrAudioFetchFailed, perr)
	}
	if scheme := strings.ToLower(parsed.Scheme); scheme != "http" && scheme != "https" {
		return nil, "", fmt.Errorf("%w: scheme %q rejected (only http/https allowed)", ErrAudioURLDisallowed, scheme)
	}
	host := parsed.Hostname()
	if host == "" {
		return nil, "", fmt.Errorf("%w: missing host", ErrAudioFetchFailed)
	}

	// /review-impl HIGH#1 + MED#2 — inner timeout for fetch + DNS resolve
	fetchCtx, cancel := context.WithTimeout(ctx, audioFetchTimeout)
	defer cancel()

	// SSRF: resolve hostname BEFORE the HTTP call. If ANY resolved IP is
	// in a disallowed range, reject. Reject even when literal IP was
	// passed (parsed.Hostname returns the IP string, LookupIP recognizes
	// it and returns [ip] — same check applies).
	ips, lerr := audioURLResolver.LookupIP(fetchCtx, "ip", host)
	if lerr != nil {
		return nil, "", fmt.Errorf("%w: dns lookup: %v", ErrAudioFetchFailed, lerr)
	}
	if len(ips) == 0 {
		return nil, "", fmt.Errorf("%w: hostname %q resolves to no addresses", ErrAudioFetchFailed, host)
	}
	for _, ip := range ips {
		if isDisallowedIP(ip) {
			return nil, "", fmt.Errorf("%w: host %q resolves to disallowed IP %s", ErrAudioURLDisallowed, host, ip.String())
		}
	}

	req, err := http.NewRequestWithContext(fetchCtx, http.MethodGet, audioURL, nil)
	if err != nil {
		return nil, "", fmt.Errorf("%w: %v", ErrAudioFetchFailed, err)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, "", fmt.Errorf("%w: %v", ErrAudioFetchFailed, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, "", fmt.Errorf("%w: status %d", ErrAudioFetchFailed, resp.StatusCode)
	}
	contentType := resp.Header.Get("Content-Type")
	// Read up to MaxAudioBytes+1; if we read MaxAudioBytes+1 bytes the body
	// exceeds the cap (LimitReader returns EOF at the cap, not an error,
	// so we use cap+1 to detect overflow).
	limited := io.LimitReader(resp.Body, MaxAudioBytes+1)
	buf, rerr := io.ReadAll(limited)
	if rerr != nil {
		return nil, "", fmt.Errorf("%w: read body: %v", ErrAudioFetchFailed, rerr)
	}
	if len(buf) > MaxAudioBytes {
		return nil, "", fmt.Errorf("%w: body exceeds %d bytes", ErrAudioTooLarge, MaxAudioBytes)
	}
	return buf, contentType, nil
}

// truncateBody caps a provider response body for use in error messages.
// Used by Transcribe (and indirectly Speak, which uses LimitReader).
// /review-impl MED#3 — Phase 5a helper.
func truncateBody(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "...(truncated)"
}

// audioFilenameFromContentType picks a filename extension OpenAI Whisper
// accepts. The /v1/audio/transcriptions endpoint requires a filename
// with a recognized extension; the actual Content-Type header is
// secondary. Default to .wav since chat-service typically uploads
// webm/wav from the browser.
func audioFilenameFromContentType(ct string) string {
	ct = strings.ToLower(ct)
	switch {
	case strings.Contains(ct, "mpeg"), strings.Contains(ct, "mp3"):
		return "audio.mp3"
	case strings.Contains(ct, "ogg"):
		return "audio.ogg"
	case strings.Contains(ct, "webm"):
		return "audio.webm"
	case strings.Contains(ct, "m4a"), strings.Contains(ct, "mp4"):
		return "audio.m4a"
	case strings.Contains(ct, "flac"):
		return "audio.flac"
	default:
		return "audio.wav"
	}
}

// Transcribe — OpenAI Whisper. Phase 5a implementation.
//
// Flow: GET audio_url → multipart POST /v1/audio/transcriptions with
// `file` + `model` + `response_format=verbose_json` + (optional)
// `language` → parse JSON `{text, language, duration}`.
func (a *openaiAdapter) Transcribe(
	ctx context.Context,
	endpointBaseURL, secret, modelName string,
	input TranscribeInput,
) (TranscribeOutput, Usage, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}

	// Step 1: fetch audio bytes (gateway-side; SSRF-guarded by scheme check)
	audioBytes, contentType, err := fetchAudioURL(ctx, a.client, input.AudioURL)
	if err != nil {
		return TranscribeOutput{}, Usage{}, err
	}

	// Step 2: build multipart body
	var body bytes.Buffer
	mw := multipart.NewWriter(&body)
	if err := mw.WriteField("model", modelName); err != nil {
		return TranscribeOutput{}, Usage{}, fmt.Errorf("multipart write model: %w", err)
	}
	if err := mw.WriteField("response_format", "verbose_json"); err != nil {
		return TranscribeOutput{}, Usage{}, fmt.Errorf("multipart write response_format: %w", err)
	}
	if input.Language != "" && input.Language != "auto" {
		if err := mw.WriteField("language", input.Language); err != nil {
			return TranscribeOutput{}, Usage{}, fmt.Errorf("multipart write language: %w", err)
		}
	}
	filename := audioFilenameFromContentType(contentType)
	fw, err := mw.CreateFormFile("file", filename)
	if err != nil {
		return TranscribeOutput{}, Usage{}, fmt.Errorf("multipart CreateFormFile: %w", err)
	}
	if _, err := fw.Write(audioBytes); err != nil {
		return TranscribeOutput{}, Usage{}, fmt.Errorf("multipart write file: %w", err)
	}
	if err := mw.Close(); err != nil {
		return TranscribeOutput{}, Usage{}, fmt.Errorf("multipart close: %w", err)
	}

	// Step 3: POST to upstream
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, base+"/v1/audio/transcriptions", &body)
	if err != nil {
		return TranscribeOutput{}, Usage{}, fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", mw.FormDataContentType())
	if secret != "" {
		req.Header.Set("Authorization", "Bearer "+secret)
	}
	resp, err := a.client.Do(req)
	if err != nil {
		return TranscribeOutput{}, Usage{}, fmt.Errorf("upstream transport: %w", err)
	}
	defer resp.Body.Close()
	respBytes, _ := io.ReadAll(resp.Body)
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		// /review-impl MED#3 — typed-error classification so caller can
		// branch on retry-eligibility (429 vs 4xx vs 5xx) without parsing
		// error.Error() strings.
		bodyStr := truncateBody(string(respBytes), 4096)
		retryAfter := parseRetryAfter(resp.Header.Get("Retry-After"))
		return TranscribeOutput{}, Usage{}, ClassifyUpstreamHTTP(resp.StatusCode, bodyStr, retryAfter)
	}

	// Step 4: parse verbose_json
	var parsed struct {
		Text     string  `json:"text"`
		Language string  `json:"language"`
		Duration float64 `json:"duration"`
	}
	if err := json.Unmarshal(respBytes, &parsed); err != nil {
		return TranscribeOutput{}, Usage{}, fmt.Errorf("decode verbose_json: %w (body=%s)", err, string(respBytes))
	}
	return TranscribeOutput{
		Text:       parsed.Text,
		Language:   parsed.Language,
		DurationMs: int(parsed.Duration * 1000),
	}, Usage{}, nil
}

// speakChunkSize is the read-buffer size for streaming TTS audio bytes
// from the upstream provider's response body. 4KB matches the OpenAI
// SSE chunk size for chat-completions, keeping our backpressure profile
// uniform across operations.
const speakChunkSize = 4 * 1024

// Speak — OpenAI TTS (`/v1/audio/speech`). Phase 5a implementation.
//
// Flow: POST JSON `{model, input, voice, speed, response_format}` →
// stream upstream response body in 4KB chunks via `emit` →
// final emit with `Final=true, Data=nil`.
//
// On non-2xx upstream: read the body for diagnostics, return wrapped
// error WITHOUT emitting anything (caller's emit must be called only
// after the upstream is confirmed streaming).
//
// On `emit` error mid-stream: stop reading, close upstream connection
// (via deferred `resp.Body.Close()`), return the emit error.
func (a *openaiAdapter) Speak(
	ctx context.Context,
	endpointBaseURL, secret, modelName string,
	input SpeakInput,
	emit AudioEmitFn,
) error {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = openaiBaseURL
	}

	speed := input.Speed
	if speed <= 0 {
		speed = 1.0
	}
	format := input.Format
	if format == "" {
		format = "mp3"
	}
	voice := input.Voice
	if voice == "" {
		voice = "alloy"
	}

	body := map[string]any{
		"model":           modelName,
		"input":           input.Text,
		"voice":           voice,
		"speed":           speed,
		"response_format": format,
	}
	bodyBytes, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("marshal speak body: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, base+"/v1/audio/speech", bytes.NewReader(bodyBytes))
	if err != nil {
		return fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/octet-stream")
	if secret != "" {
		req.Header.Set("Authorization", "Bearer "+secret)
	}
	resp, err := a.client.Do(req)
	if err != nil {
		return fmt.Errorf("upstream transport: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		// /review-impl MED#3 — typed-error classification (mirrors Transcribe).
		respBytes, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		retryAfter := parseRetryAfter(resp.Header.Get("Retry-After"))
		return ClassifyUpstreamHTTP(resp.StatusCode, string(respBytes), retryAfter)
	}

	buf := make([]byte, speakChunkSize)
	seq := 0
	for {
		n, rerr := resp.Body.Read(buf)
		if n > 0 {
			chunk := AudioChunk{
				SequenceID: seq,
				Data:       buf[:n], // emit may copy; doc'd in AudioEmitFn
				Final:      false,
			}
			if eerr := emit(chunk); eerr != nil {
				return eerr
			}
			seq++
		}
		if rerr == io.EOF {
			break
		}
		if rerr != nil {
			return fmt.Errorf("upstream read: %w", rerr)
		}
	}

	// Closing sentinel
	return emit(AudioChunk{SequenceID: seq, Data: nil, Final: true})
}

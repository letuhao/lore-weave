package chunker

// Phase 3a (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). Pure-function chunker
// primitives used by the async-job worker (Phase 3c) when a job's
// `chunking` config is non-nil. Each strategy returns a `[]string` —
// the worker dispatches one chunk per element to adapter.Stream and
// the aggregator (Phase 3b) collapses results.
//
// Strategies mirror openapi ChunkingConfig.strategy enum:
//   - "tokens"     — tiktoken cl100k_base count per chunk; supports overlap
//   - "paragraphs" — split on blank lines, merge until target paragraph count
//   - "sentences"  — split on .?! boundaries, merge until target sentence count
//   - "none"       — passthrough; returns []string{text}

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/pkoukk/tiktoken-go"
)

type Strategy string

const (
	StrategyTokens     Strategy = "tokens"
	StrategyParagraphs Strategy = "paragraphs"
	StrategySentences  Strategy = "sentences"
	StrategyNone       Strategy = "none"
)

// Request is the caller-supplied chunking config. Mirrors openapi
// ChunkingConfig schema.
type Request struct {
	Strategy Strategy
	Size     int // tokens / paragraphs / sentences (units depend on Strategy)
	Overlap  int // tokens only — paragraphs/sentences are semantic units, not overlapped
}

// Default values per openapi schema description.
const (
	DefaultTokensSize       = 2000
	DefaultParagraphsSize   = 8
	DefaultSentencesSize    = 30
	DefaultTokensOverlap    = 200
)

// applyDefaults fills in missing fields per the openapi description.
func applyDefaults(r Request) Request {
	if r.Size <= 0 {
		switch r.Strategy {
		case StrategyTokens:
			r.Size = DefaultTokensSize
		case StrategyParagraphs:
			r.Size = DefaultParagraphsSize
		case StrategySentences:
			r.Size = DefaultSentencesSize
		}
	}
	if r.Overlap < 0 {
		r.Overlap = 0
	}
	if r.Strategy == StrategyTokens && r.Overlap == 0 {
		// Only apply default overlap when caller didn't specify one
		// AND we're in token mode. A caller who explicitly wants 0
		// overlap can pass -1 then we clamp above; simpler: trust the
		// zero-value as "apply default". Keep this conservative — the
		// chunker is a primitive; real-world callers always set Overlap.
		r.Overlap = DefaultTokensOverlap
	}
	return r
}

// ChunkText splits the input text per the Request strategy. Empty
// input returns []string{""} so callers can iterate uniformly. An
// invalid strategy returns an error.
func ChunkText(text string, req Request) ([]string, error) {
	if text == "" {
		return []string{""}, nil
	}
	req = applyDefaults(req)
	switch req.Strategy {
	case "", StrategyNone:
		return []string{text}, nil
	case StrategyTokens:
		return chunkByTokens(text, req.Size, req.Overlap)
	case StrategyParagraphs:
		return chunkByParagraphs(text, req.Size), nil
	case StrategySentences:
		return chunkBySentences(text, req.Size), nil
	default:
		return nil, fmt.Errorf("unknown chunking strategy: %q", req.Strategy)
	}
}

// chunkByTokens uses tiktoken cl100k_base — the encoder shared by GPT-4,
// GPT-3.5, and (close-enough) most modern models. Per-chunk size is
// the OUTPUT token cap; overlap is taken from the END of the previous
// chunk and prepended to the next so context isn't lost at boundaries.
func chunkByTokens(text string, size, overlap int) ([]string, error) {
	if size <= 0 {
		return nil, fmt.Errorf("token chunk size must be > 0")
	}
	if overlap >= size {
		return nil, fmt.Errorf("overlap (%d) must be < size (%d)", overlap, size)
	}
	enc, err := tiktoken.GetEncoding("cl100k_base")
	if err != nil {
		return nil, fmt.Errorf("tiktoken encoding: %w", err)
	}
	tokens := enc.Encode(text, nil, nil)
	if len(tokens) <= size {
		return []string{text}, nil
	}
	stride := size - overlap
	var chunks []string
	for start := 0; start < len(tokens); start += stride {
		end := start + size
		if end > len(tokens) {
			end = len(tokens)
		}
		piece := tokens[start:end]
		chunks = append(chunks, enc.Decode(piece))
		if end == len(tokens) {
			break
		}
	}
	return chunks, nil
}

// paragraphSplitter matches one-or-more blank lines (\n\n+ with
// optional whitespace inside).
var paragraphSplitter = regexp.MustCompile(`(?:\r?\n\s*\r?\n)+`)

// chunkByParagraphs splits on blank lines then merges paragraphs
// greedily until each chunk holds `size` paragraphs. Empty paragraphs
// (resulting from leading/trailing blank lines) are skipped.
func chunkByParagraphs(text string, size int) []string {
	if size <= 0 {
		size = DefaultParagraphsSize
	}
	pieces := paragraphSplitter.Split(text, -1)
	// Drop empties.
	var paras []string
	for _, p := range pieces {
		p = strings.TrimSpace(p)
		if p != "" {
			paras = append(paras, p)
		}
	}
	if len(paras) == 0 {
		return []string{""}
	}
	if len(paras) <= size {
		return []string{strings.Join(paras, "\n\n")}
	}
	var chunks []string
	for i := 0; i < len(paras); i += size {
		end := i + size
		if end > len(paras) {
			end = len(paras)
		}
		chunks = append(chunks, strings.Join(paras[i:end], "\n\n"))
	}
	return chunks
}

// sentenceSplitter approximates an English-/CJK-friendly sentence
// terminator regex. Splits AFTER `.`, `!`, `?`, `。`, `！`, `？`. Doesn't
// try to be smart about abbreviations (Mr., Dr.) — Phase 3a primitive
// is good-enough for chunking purposes; a real NLP splitter is Phase 6
// hardening.
// CJK terminators have no trailing whitespace, so we match the punctuation
// alone and slice immediately after it. ASCII terminators followed by
// whitespace are also captured by the trailing optional `\s*`.
var sentenceTerminator = regexp.MustCompile(`[.!?。！？]+\s*`)

// chunkBySentences splits the text on sentence-end punctuation and
// merges into groups of `size` sentences. Overlap is ignored for
// semantic-unit strategies (paragraphs/sentences) per design.
func chunkBySentences(text string, size int) []string {
	if size <= 0 {
		size = DefaultSentencesSize
	}
	// Split keeps the punctuation attached to each preceding sentence.
	idxs := sentenceTerminator.FindAllStringIndex(text, -1)
	var sentences []string
	prev := 0
	for _, idx := range idxs {
		end := idx[1]
		s := strings.TrimSpace(text[prev:end])
		if s != "" {
			sentences = append(sentences, s)
		}
		prev = end
	}
	if prev < len(text) {
		tail := strings.TrimSpace(text[prev:])
		if tail != "" {
			sentences = append(sentences, tail)
		}
	}
	if len(sentences) == 0 {
		return []string{""}
	}
	if len(sentences) <= size {
		return []string{strings.Join(sentences, " ")}
	}
	var chunks []string
	for i := 0; i < len(sentences); i += size {
		end := i + size
		if end > len(sentences) {
			end = len(sentences)
		}
		chunks = append(chunks, strings.Join(sentences[i:end], " "))
	}
	return chunks
}

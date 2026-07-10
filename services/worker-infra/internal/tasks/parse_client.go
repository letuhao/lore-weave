package tasks

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/loreweave/observability"
)

// parse_client.go — P1 (hierarchical extraction T1).
//
// Thin HTTP client around knowledge-service POST /internal/parse.
// The structural decomposer SDK (loreweave_parse) lives in Python in
// sdks/python/; worker-infra (Go) reaches it via this one-hop HTTP call.
//
// Spec: docs/specs/2026-05-23-p1-structural-decomposer.md §D6/§D7.
//
// IQ4 (plan §7): no retry. /internal/parse is deterministic — a 5xx
// would 5xx again. Caller should fail the import job; user retries via UI.

// Scene mirrors loreweave_parse.Scene Pydantic shape.
type Scene struct {
	SortOrder   int    `json:"sort_order"`
	Path        string `json:"path"`
	LeafText    string `json:"leaf_text"`
	ContentHash string `json:"content_hash"`
	// SourceSceneID (22-A5/SC7) — the composition outline_node.id recovered from
	// the drafted prose's `data-scene-id` heading anchor, when present. Fresh
	// pandoc/PDF imports carry no anchor, so it is absent → the index row's
	// source_scene_id stays NULL. Soft ref (no FK, crosses the service boundary).
	SourceSceneID *string `json:"source_scene_id,omitempty"`
}

// ParsedChapter mirrors loreweave_parse.Chapter (renamed to avoid clash
// with the legacy `Chapter` struct in html_to_tiptap.go, retained for
// the tiptap-conversion concern).
type ParsedChapter struct {
	SortOrder int     `json:"sort_order"`
	Title     *string `json:"title"`
	Path      string  `json:"path"`
	HTML      string  `json:"html"`
	Scenes    []Scene `json:"scenes"`
}

// Part mirrors loreweave_parse.Part.
type Part struct {
	SortOrder int             `json:"sort_order"`
	Title     *string         `json:"title"`
	Path      string          `json:"path"`
	Chapters  []ParsedChapter `json:"chapters"`
}

// StructuralTree mirrors loreweave_parse.StructuralTree.
type StructuralTree struct {
	SourceFormat     string  `json:"source_format"`
	DetectedLanguage *string `json:"detected_language"`
	WalkerPath       string  `json:"walker_path"`
	BookTitle        *string `json:"book_title"`
	Parts            []Part  `json:"parts"`
}

// parseRequest matches loreweave_parse.ParseRequest envelope.
type parseRequest struct {
	SourceFormat string         `json:"source_format"`
	Content      string         `json:"content"`
	Language     *string        `json:"language,omitempty"`
	Filename     *string        `json:"filename,omitempty"`
	Options      map[string]any `json:"options,omitempty"`
}

// ParseClient is a minimal client for POST /internal/parse.
type ParseClient struct {
	BaseURL       string
	InternalToken string
	HTTP          *http.Client
}

// NewParseClient builds a client with a 5-minute timeout (same order of
// magnitude as the pandoc call; the parse itself is sub-second but body
// transport for 50MB+ HTML over the docker network can take seconds).
func NewParseClient(baseURL, internalToken string) *ParseClient {
	return &ParseClient{
		BaseURL:       baseURL,
		InternalToken: internalToken,
		HTTP: &http.Client{
			Timeout:   5 * time.Minute,
			Transport: observability.HTTPTransport(nil),
		},
	}
}

// Call posts the source content to /internal/parse and returns the
// resulting tree. sourceFormat must be "html" or "plain".
func (c *ParseClient) Call(
	ctx context.Context,
	sourceFormat string,
	content string,
	language string,
	filename string,
) (*StructuralTree, error) {
	body := parseRequest{
		SourceFormat: sourceFormat,
		Content:      content,
	}
	if language != "" {
		body.Language = &language
	}
	if filename != "" {
		body.Filename = &filename
	}
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("parse_client marshal: %w", err)
	}

	req, err := http.NewRequestWithContext(
		ctx,
		"POST",
		c.BaseURL+"/internal/parse",
		bytes.NewReader(jsonBody),
	)
	if err != nil {
		return nil, fmt.Errorf("parse_client request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", c.InternalToken)

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, fmt.Errorf("parse_client do: %w", err)
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("parse_client read body: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf(
			"parse_client status %d: %s",
			resp.StatusCode,
			string(respBytes),
		)
	}

	var tree StructuralTree
	if err := json.Unmarshal(respBytes, &tree); err != nil {
		return nil, fmt.Errorf("parse_client unmarshal: %w", err)
	}
	return &tree, nil
}

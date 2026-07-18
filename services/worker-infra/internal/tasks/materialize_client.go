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

// MaterializeClient calls composition-service's SC6 scene decompiler
// (POST /internal/books/{book_id}/materialize-scenes, 22 B4 / 26 IX-12).
//
// 26 IX-12 — "the decompiler returns the map; the index owner writes it": composition
// mints one spec `outline_node` per parse leaf and RETURNS `mappings[]`; the import tail
// (this worker) writes `scenes.source_scene_id` from that map. Composition never writes
// book-service's DB (SCOPE-2), so the back-link write must stay on the index-owner side.
type MaterializeClient struct {
	BaseURL       string
	InternalToken string
	HTTP          *http.Client
}

func NewMaterializeClient(baseURL, internalToken string) *MaterializeClient {
	return &MaterializeClient{
		BaseURL:       baseURL,
		InternalToken: internalToken,
		HTTP: &http.Client{
			Timeout:   2 * time.Minute,
			Transport: observability.HTTPTransport(nil),
		},
	}
}

// SceneMapping is one back-link the import tail writes: the parse leaf at
// (chapter_id, sort_order) now maps to spec node outline_node_id.
type SceneMapping struct {
	ChapterID     string `json:"chapter_id"`
	SortOrder     int    `json:"sort_order"`
	OutlineNodeID string `json:"outline_node_id"`
}

type materializeRequest struct {
	OwnerUserID string `json:"owner_user_id"`
}

type materializeResponse struct {
	WorkResolved bool           `json:"work_resolved"`
	Created      int            `json:"created"`
	Matched      int            `json:"matched"`
	Mappings     []SceneMapping `json:"mappings"`
	Detail       *string        `json:"detail"`
}

// Materialize decompiles the book's imported prose into spec scenes and returns the
// back-link map. A Work-less book (never opened in the composer) is a GRACEFUL no-op —
// work_resolved=false with empty mappings, NOT an error — so the caller writes nothing
// and the leaves stay "unplanned" until the Hub's decompile CTA runs later (26 state
// model). `ownerUserID` is the book owner the import job verified; composition re-gates
// its EDIT grant and mints a scoped service bearer to read the VIEW-gated scene list.
func (c *MaterializeClient) Materialize(
	ctx context.Context, bookID, ownerUserID string,
) (*materializeResponse, error) {
	jsonBody, err := json.Marshal(materializeRequest{OwnerUserID: ownerUserID})
	if err != nil {
		return nil, fmt.Errorf("materialize marshal: %w", err)
	}
	url := fmt.Sprintf("%s/internal/books/%s/materialize-scenes", c.BaseURL, bookID)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(jsonBody))
	if err != nil {
		return nil, fmt.Errorf("materialize request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", c.InternalToken)

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, fmt.Errorf("materialize do: %w", err)
	}
	defer resp.Body.Close()
	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("materialize read body: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("materialize status %d: %s", resp.StatusCode, string(respBytes[:min(len(respBytes), 200)]))
	}
	var out materializeResponse
	if err := json.Unmarshal(respBytes, &out); err != nil {
		return nil, fmt.Errorf("materialize decode: %w", err)
	}
	return &out, nil
}

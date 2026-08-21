package tasks

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/loreweave/observability"
)

type epubV2HierarchyPayload struct {
	BookID string                `json:"book_id"`
	UserID string                `json:"user_id"`
	Nodes  []epubV2HierarchyNode `json:"nodes"`
}

type epubV2HierarchyNode struct {
	SourceKey       string  `json:"source_key"`
	ParentSourceKey *string `json:"parent_source_key,omitempty"`
	Role            string  `json:"role"`
	Title           string  `json:"title"`
	Ordinal         int     `json:"ordinal"`
	Depth           int     `json:"depth"`
	ChapterID       *string `json:"chapter_id,omitempty"`
}

type epubV2CompositionHierarchyResponse struct {
	Mappings []struct {
		SourceKey       string  `json:"source_key"`
		HierarchyNodeID string  `json:"hierarchy_node_id"`
		StructureNodeID *string `json:"structure_node_id,omitempty"`
		ChapterID       *string `json:"chapter_id,omitempty"`
	} `json:"mappings"`
}

// materializeEPUBV2Hierarchy keeps the two database ownership boundaries
// explicit: Book exposes finalized source items, Composition stores the ToC,
// and Book accepts the returned opaque mapping. A Composition outage is
// best-effort and does not invalidate already-materialized Book chapters.
func (t *ImportProcessor) materializeEPUBV2Hierarchy(ctx context.Context, payload importRequestedPayload) error {
	if t.Cfg == nil || t.Cfg.CompositionServiceURL == "" {
		return nil
	}
	var hierarchy epubV2HierarchyPayload
	if err := t.epubV2JSON(ctx, http.MethodGet, fmt.Sprintf("/internal/epub-import-jobs/%s/hierarchy", payload.JobID), nil, &hierarchy); err != nil {
		return err
	}
	if len(hierarchy.Nodes) == 0 {
		return nil
	}
	// epubimport's navigation ordinal is zero-based, while the persisted
	// cross-service hierarchy contract is one-based. Normalize at the worker
	// boundary so Composition never has to know parser-local numbering.
	for index := range hierarchy.Nodes {
		hierarchy.Nodes[index].Ordinal++
	}
	var response epubV2CompositionHierarchyResponse
	if err := t.compositionEPUBHierarchyJSON(ctx, payload.JobID, hierarchy, &response); err != nil {
		slog.Warn("epub import composition hierarchy materialization failed", "job_id", payload.JobID, "book_id", hierarchy.BookID, "error", err)
		_ = t.epubV2JSON(ctx, http.MethodPost, fmt.Sprintf("/internal/epub-import-jobs/%s/warnings", payload.JobID), map[string]string{"code": "composition_materialization_pending", "message": "Composition hierarchy materialization is pending retry.", "stage": "composition"}, nil)
		return nil
	}
	if len(response.Mappings) == 0 {
		return nil
	}
	if err := t.epubV2JSON(ctx, http.MethodPost, fmt.Sprintf("/internal/epub-import-jobs/%s/hierarchy-mappings", payload.JobID), map[string]any{"mappings": response.Mappings}, nil); err != nil {
		return err
	}
	return nil
}

func (t *ImportProcessor) compositionEPUBHierarchyJSON(ctx context.Context, jobID string, hierarchy epubV2HierarchyPayload, output any) error {
	body, err := json.Marshal(map[string]any{"import_job_id": jobID, "nodes": hierarchy.Nodes})
	if err != nil {
		return err
	}
	endpoint, err := url.Parse(strings.TrimRight(t.Cfg.CompositionServiceURL, "/") + "/internal/composition/books/" + hierarchy.BookID + "/epub-import-hierarchy")
	if err != nil {
		return err
	}
	query := endpoint.Query()
	query.Set("caller_user_id", hierarchy.UserID)
	endpoint.RawQuery = query.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint.String(), bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("X-Internal-Token", t.Cfg.InternalToken)
	req.Header.Set("Content-Type", "application/json")
	client := &http.Client{Timeout: 20 * time.Second, Transport: observability.HTTPTransport(nil)}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return fmt.Errorf("composition service status %d", resp.StatusCode)
	}
	return json.Unmarshal(data, output)
}

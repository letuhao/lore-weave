package tasks

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"path"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"

	"github.com/loreweave/epubimport"
	"github.com/loreweave/observability"
)

const epubImportPipelineVersion = "epub-v2"

type epubV2Claim struct {
	Done      bool      `json:"done"`
	Cancelled bool      `json:"cancelled"`
	ItemID    uuid.UUID `json:"item_id"`
	SourceKey string    `json:"source_key"`
	Title     string    `json:"title"`
	Ordinal   int       `json:"ordinal"`
}

// processEPUBV2 stages parser output only. Book Service remains the sole
// database writer; a later finalize command activates staged chapters.
func (t *ImportProcessor) processEPUBV2(ctx context.Context, payload importRequestedPayload) error {
	if payload.FileFormat != "epub" {
		return fmt.Errorf("epub v2 received unsupported format %q", payload.FileFormat)
	}
	obj, err := t.Minio.GetObject(ctx, t.Cfg.MinioBucket, payload.FileStorageKey, minio.GetObjectOptions{})
	if err != nil {
		return fmt.Errorf("minio get: %w", err)
	}
	defer obj.Close()
	data, err := io.ReadAll(obj)
	if err != nil {
		return fmt.Errorf("minio read: %w", err)
	}
	inspection, err := epubimport.Inspect(data, epubimport.DefaultLimits())
	if err != nil {
		return fmt.Errorf("inspect EPUB: %w", err)
	}
	nodes := make(map[string]*epubimport.NavigationNode)
	indexEPUBNavigationNodes(inspection.Structure, nodes)
	for {
		claim, err := t.claimEPUBItem(ctx, payload.JobID)
		if err != nil {
			return err
		}
		if claim.Done {
			if claim.Cancelled {
				return nil
			}
			if err := t.finalizeEPUBImport(ctx, payload.JobID); err != nil {
				return err
			}
			if err := t.seedEPUBImportLore(ctx, payload); err != nil {
				return err
			}
			if err := t.materializeEPUBV2Scenes(ctx, payload); err != nil {
				return err
			}
			return t.materializeEPUBV2Hierarchy(ctx, payload)
		}
		node := nodes[claim.SourceKey]
		if node == nil {
			if err := t.failEPUBItem(ctx, payload.JobID, claim.ItemID, "epub_content_unavailable", "source navigation item is unavailable"); err != nil {
				return err
			}
			continue
		}
		html, warnings, err := epubimport.ExtractChapter(data, *node, epubimport.DefaultLimits())
		if err != nil {
			if failErr := t.failEPUBItem(ctx, payload.JobID, claim.ItemID, "epub_extract_failed", "failed to extract chapter content"); failErr != nil {
				return failErr
			}
			continue
		}
		html, assetWarnings, err := epubimport.ResolveAndRewriteAssets(data, node.SourceHref, html, epubimport.DefaultLimits(), func(asset epubimport.ResolvedAsset) (string, error) {
			return t.storeEPUBAsset(ctx, payload.JobID, inspection.SHA256, claim.SourceKey, asset)
		})
		warnings = append(warnings, assetWarnings...)
		if err != nil {
			if failErr := t.failEPUBItem(ctx, payload.JobID, claim.ItemID, "epub_asset_resolution_failed", "failed to resolve chapter assets"); failErr != nil {
				return failErr
			}
			continue
		}
		sanitized, sanitizeWarnings, err := epubimport.SanitizeHTML(html)
		warnings = append(warnings, sanitizeWarnings...)
		if err != nil {
			if failErr := t.failEPUBItem(ctx, payload.JobID, claim.ItemID, "epub_sanitize_failed", "failed to sanitize chapter content"); failErr != nil {
				return failErr
			}
			continue
		}
		links, linkWarnings := epubimport.CollectInternalLinks(node.SourceHref, sanitized)
		warnings = append(warnings, linkWarnings...)
		lang := payload.OriginalLanguage
		if lang == "" {
			lang = "und"
		}
		tree, err := t.parseClient.CallChapter(ctx, sanitized, lang, claim.Title, claim.SourceKey)
		if err != nil || len(tree.Parts) != 1 || len(tree.Parts[0].Chapters) != 1 {
			if failErr := t.failEPUBItem(ctx, payload.JobID, claim.ItemID, "epub_parse_failed", "failed to parse chapter content"); failErr != nil {
				return failErr
			}
			continue
		}
		chapter := tree.Parts[0].Chapters[0]
		staging, err := json.Marshal(map[string]any{
			"source_key": claim.SourceKey, "title": claim.Title,
			"tiptap_json": json.RawMessage(htmlToTiptapJSON(chapter.HTML)), "scenes": chapter.Scenes, "links": links,
		})
		if err != nil {
			return fmt.Errorf("marshal staging payload: %w", err)
		}
		if err := t.stageEPUBItem(ctx, payload.JobID, claim.ItemID, staging, warnings); err != nil {
			return err
		}
	}
}

// seedEPUBImportLore delegates to Glossary, the sole owner of the ontology.
// A failed call deliberately leaves the stream delivery pending: finalization is idempotent,
// so redelivery retries this prerequisite without duplicating chapters or ontology rows.
func (t *ImportProcessor) seedEPUBImportLore(ctx context.Context, payload importRequestedPayload) error {
	if payload.TargetMode != "new_book" || t.Cfg.GlossaryServiceURL == "" {
		return nil
	}
	request := map[string]any{"system_defaults": true, "genres": payload.LoreGenres}
	encoded, err := json.Marshal(request)
	if err != nil {
		return fmt.Errorf("marshal EPUB Lore scaffold request: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(t.Cfg.GlossaryServiceURL, "/")+"/internal/books/"+payload.BookID+"/ontology/adopt-kinds?user_id="+payload.UserID, bytes.NewReader(encoded))
	if err != nil {
		return fmt.Errorf("create EPUB Lore scaffold request: %w", err)
	}
	req.Header.Set("X-Internal-Token", t.Cfg.InternalToken)
	req.Header.Set("Content-Type", "application/json")
	resp, err := (&http.Client{Timeout: 15 * time.Second, Transport: observability.HTTPTransport(nil)}).Do(req)
	if err != nil {
		return fmt.Errorf("seed EPUB Lore ontology: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return fmt.Errorf("seed EPUB Lore ontology: glossary status %d", resp.StatusCode)
	}
	slog.InfoContext(ctx, "epub import system Lore ontology scaffolded", "job_id", payload.JobID, "book_id", payload.BookID, "source_genres", len(payload.LoreGenres))
	return nil
}

func (t *ImportProcessor) materializeEPUBV2Scenes(ctx context.Context, payload importRequestedPayload) error {
	if t.materializeClient == nil {
		if t.Cfg == nil || t.Cfg.CompositionServiceURL == "" {
			return nil
		}
		t.materializeClient = NewMaterializeClient(t.Cfg.CompositionServiceURL, t.Cfg.InternalToken)
	}
	result, err := t.materializeClient.Materialize(ctx, payload.BookID, payload.UserID)
	if err != nil {
		slog.Warn("epub import composition materialization failed", "job_id", payload.JobID, "book_id", payload.BookID, "error", err)
		return nil
	}
	if !result.WorkResolved || len(result.Mappings) == 0 {
		return nil
	}
	if err := t.epubV2JSON(ctx, http.MethodPost, fmt.Sprintf("/internal/epub-import-jobs/%s/scene-mappings", payload.JobID), map[string]any{"mappings": result.Mappings}, nil); err != nil {
		return err
	}
	return nil
}

func (t *ImportProcessor) storeEPUBAsset(ctx context.Context, jobID, sourceSHA, sourceKey string, asset epubimport.ResolvedAsset) (string, error) {
	objectKey := fmt.Sprintf("imports/assets/%s/%s%s", sourceSHA, asset.SHA256, path.Ext(asset.SourcePath))
	if strings.HasPrefix(asset.SourcePath, "data:") {
		objectKey = fmt.Sprintf("imports/assets/%s/%s%s", sourceSHA, asset.SHA256, epubAssetExtension(asset.MediaType))
	}
	if _, err := t.Minio.PutObject(ctx, t.Cfg.MinioBucket, objectKey, bytes.NewReader(asset.Data), asset.SizeBytes, minio.PutObjectOptions{ContentType: asset.MediaType}); err != nil {
		return "", fmt.Errorf("store EPUB asset: %w", err)
	}
	var stored struct {
		URL string `json:"url"`
	}
	if err := t.epubV2JSON(ctx, http.MethodPost, fmt.Sprintf("/internal/epub-import-jobs/%s/assets", jobID), map[string]any{
		"source_path":       asset.SourcePath,
		"source_media_type": asset.MediaType,
		"sha256":            asset.SHA256,
		"size_bytes":        asset.SizeBytes,
		"object_key":        objectKey,
	}, &stored); err != nil {
		return "", err
	}
	if !strings.HasPrefix(stored.URL, "/media/") {
		return "", fmt.Errorf("book service returned invalid EPUB asset URL")
	}
	slog.InfoContext(ctx, "epub import asset stored", "job_id", jobID, "source_key", sourceKey, "asset_sha256", asset.SHA256, "size_bytes", asset.SizeBytes)
	return stored.URL, nil
}

func epubAssetExtension(mediaType string) string {
	switch mediaType {
	case "image/jpeg":
		return ".jpg"
	case "image/png":
		return ".png"
	case "image/gif":
		return ".gif"
	case "image/webp":
		return ".webp"
	case "image/svg+xml":
		return ".svg"
	default:
		return ".bin"
	}
}

func (t *ImportProcessor) finalizeEPUBImport(ctx context.Context, jobID string) error {
	return t.epubV2JSON(ctx, http.MethodPost, fmt.Sprintf("/internal/epub-import-jobs/%s/finalize", jobID), nil, nil)
}

func indexEPUBNavigationNodes(nodes []*epubimport.NavigationNode, index map[string]*epubimport.NavigationNode) {
	for _, node := range nodes {
		index[node.SourceKey] = node
		indexEPUBNavigationNodes(node.Children, index)
	}
}

func (t *ImportProcessor) claimEPUBItem(ctx context.Context, jobID string) (epubV2Claim, error) {
	var claim epubV2Claim
	err := t.epubV2JSON(ctx, http.MethodPost, fmt.Sprintf("/internal/epub-import-jobs/%s/claim-next", jobID), nil, &claim)
	return claim, err
}

func (t *ImportProcessor) stageEPUBItem(ctx context.Context, jobID string, itemID uuid.UUID, staging []byte, warnings []epubimport.Diagnostic) error {
	return t.epubV2JSON(ctx, http.MethodPost, fmt.Sprintf("/internal/epub-import-jobs/%s/items/%s/stage", jobID, itemID), map[string]any{"staging_payload": json.RawMessage(staging), "warnings": warnings}, nil)
}

func (t *ImportProcessor) failEPUBItem(ctx context.Context, jobID string, itemID uuid.UUID, code, message string) error {
	return t.epubV2JSON(ctx, http.MethodPost, fmt.Sprintf("/internal/epub-import-jobs/%s/items/%s/fail", jobID, itemID), map[string]string{"code": code, "message": message}, nil)
}

func (t *ImportProcessor) epubV2JSON(ctx context.Context, method, path string, input any, output any) error {
	var body io.Reader
	if input != nil {
		encoded, err := json.Marshal(input)
		if err != nil {
			return err
		}
		body = bytes.NewReader(encoded)
	}
	req, err := http.NewRequestWithContext(ctx, method, strings.TrimRight(t.Cfg.BookServiceURL, "/")+path, body)
	if err != nil {
		return err
	}
	req.Header.Set("X-Internal-Token", t.Cfg.InternalToken)
	if input != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	client := &http.Client{Timeout: 15 * time.Second, Transport: observability.HTTPTransport(nil)}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("book service status %d", resp.StatusCode)
	}
	if output != nil && len(data) > 0 {
		return json.Unmarshal(data, output)
	}
	return nil
}

package tasks

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"

	"github.com/minio/minio-go/v7"
)

// extractAndUploadImages walks a Tiptap JSON document, finds image nodes with
// data: URIs, uploads them to MinIO, and replaces the src with the MinIO URL.
// Returns the modified JSON document.
func extractAndUploadImages(
	ctx context.Context,
	tiptapJSON json.RawMessage,
	mc *minio.Client,
	bucket string,
	storagePrefix string, // e.g. "chapters/{bookID}/import-{jobID}-{idx}"
	minioExternalURL string, // optional, for constructing browser-accessible URLs
) (json.RawMessage, int) {
	var doc map[string]any
	if err := json.Unmarshal(tiptapJSON, &doc); err != nil {
		return tiptapJSON, 0
	}

	content, ok := doc["content"].([]any)
	if !ok {
		return tiptapJSON, 0
	}

	count := 0
	doc["content"] = walkNodes(ctx, content, mc, bucket, storagePrefix, &count)

	result, err := json.Marshal(doc)
	if err != nil {
		return tiptapJSON, 0
	}
	return result, count
}

func walkNodes(
	ctx context.Context,
	nodes []any,
	mc *minio.Client,
	bucket string,
	prefix string,
	count *int,
) []any {
	for i, node := range nodes {
		n, ok := node.(map[string]any)
		if !ok {
			continue
		}

		// Check if this is an image node
		if n["type"] == "image" {
			attrs, ok := n["attrs"].(map[string]any)
			if ok {
				src, _ := attrs["src"].(string)
				if strings.HasPrefix(src, "data:") {
					newURL := uploadDataURI(ctx, src, mc, bucket, prefix, *count)
					if newURL != "" {
						attrs["src"] = newURL
						n["attrs"] = attrs
						nodes[i] = n
						*count++
					}
				}
			}
		}

		// Recurse into child content
		if childContent, ok := n["content"].([]any); ok {
			n["content"] = walkNodes(ctx, childContent, mc, bucket, prefix, count)
			nodes[i] = n
		}
	}
	return nodes
}

// uploadDataURI parses a data: URI, uploads the binary to MinIO, returns the object URL.
// Format: data:image/png;base64,iVBORw0KGgo...
func uploadDataURI(
	ctx context.Context,
	dataURI string,
	mc *minio.Client,
	bucket string,
	prefix string,
	index int,
) string {
	// Parse data URI
	// data:[<mediatype>][;base64],<data>
	if !strings.HasPrefix(dataURI, "data:") {
		return ""
	}

	commaIdx := strings.Index(dataURI, ",")
	if commaIdx == -1 {
		return ""
	}

	meta := dataURI[5:commaIdx] // e.g. "image/png;base64"
	encoded := dataURI[commaIdx+1:]

	// Determine content type and encoding
	parts := strings.Split(meta, ";")
	contentType := "application/octet-stream"
	isBase64 := false
	for _, p := range parts {
		if p == "base64" {
			isBase64 = true
		} else if strings.Contains(p, "/") {
			contentType = p
		}
	}

	var data []byte
	var err error
	if isBase64 {
		data, err = base64.StdEncoding.DecodeString(encoded)
		if err != nil {
			slog.Warn("image_extractor: bad base64", "error", err)
			return ""
		}
	} else {
		data = []byte(encoded)
	}

	// Determine extension from content type
	ext := ".bin"
	switch contentType {
	case "image/png":
		ext = ".png"
	case "image/jpeg":
		ext = ".jpg"
	case "image/gif":
		ext = ".gif"
	case "image/webp":
		ext = ".webp"
	case "image/svg+xml":
		ext = ".svg"
	}

	objectKey := fmt.Sprintf("%s/img-%03d%s", prefix, index, ext)

	_, err = mc.PutObject(ctx, bucket, objectKey, bytes.NewReader(data), int64(len(data)),
		minio.PutObjectOptions{ContentType: contentType})
	if err != nil {
		slog.Error("image_extractor: minio upload failed", "key", objectKey, "error", err)
		return ""
	}

	slog.Info("image_extractor: uploaded", "key", objectKey, "size", len(data))

	// Return MinIO-accessible URL
	// Use the bucket/key path — the frontend resolves this via the existing media proxy
	return fmt.Sprintf("/media/%s/%s", bucket, objectKey)
}

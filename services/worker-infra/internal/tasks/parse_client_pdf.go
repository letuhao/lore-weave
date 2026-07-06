package tasks

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// parse_client_pdf.go — PDF book import (docs/specs/2026-07-06-pdf-book-import.md).
//
// Thin HTTP client around knowledge-service's two PDF-import endpoints:
// POST /internal/parse/pdf-peek (page count) and
// POST /internal/parse/pdf-chunk (one chunk -> one chapter + its images).
// Reuses ParseClient's HTTP client/base URL/token — a separate type would
// just duplicate that plumbing.

// pdfPeekRequest / pdfPeekResponse mirror
// app.routers.internal_parse_pdf.ParsePdfPeekRequest/Response.
type pdfPeekRequest struct {
	PdfBytesB64 string `json:"pdf_bytes_b64"`
}

type pdfPeekResponse struct {
	PageCount int `json:"page_count"`
}

// PdfPeek returns the PDF's page count, or an error if it's corrupted or
// password-protected (the knowledge-service endpoint returns 422 for
// those — surfaced here as a plain Go error; the caller fails the whole
// import job with that message, since this should have already been
// caught at the book-service pdf-peek step before the job was ever
// queued — this is the defensive re-check).
func (c *ParseClient) PdfPeek(ctx context.Context, pdfBytes []byte) (int, error) {
	body := pdfPeekRequest{PdfBytesB64: base64.StdEncoding.EncodeToString(pdfBytes)}
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return 0, fmt.Errorf("pdf_peek marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, "POST", c.BaseURL+"/internal/parse/pdf-peek", bytes.NewReader(jsonBody))
	if err != nil {
		return 0, fmt.Errorf("pdf_peek request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", c.InternalToken)

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return 0, fmt.Errorf("pdf_peek do: %w", err)
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return 0, fmt.Errorf("pdf_peek read body: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("pdf_peek status %d: %s", resp.StatusCode, string(respBytes))
	}
	var out pdfPeekResponse
	if err := json.Unmarshal(respBytes, &out); err != nil {
		return 0, fmt.Errorf("pdf_peek unmarshal: %w", err)
	}
	return out.PageCount, nil
}

// PdfChunkImage mirrors app.routers.internal_parse_pdf.ChunkImage.
type PdfChunkImage struct {
	PageNumber    int     `json:"page_number"`
	ImageBytesB64 string  `json:"image_bytes_b64"`
	Ext           string  `json:"ext"`
	Caption       *string `json:"caption"`
	ModelRef      *string `json:"model_ref"`
}

// PdfChunkResult mirrors app.routers.internal_parse_pdf.ParsePdfChunkResponse.
type PdfChunkResult struct {
	Chapter ParsedChapter   `json:"chapter"`
	Images  []PdfChunkImage `json:"images"`
}

// pdfChunkRequest mirrors app.routers.internal_parse_pdf.ParsePdfChunkRequest.
type pdfChunkRequest struct {
	BookID        string `json:"book_id"`
	PdfBytesB64   string `json:"pdf_bytes_b64"`
	PageStart     int    `json:"page_start"`
	PageEnd       int    `json:"page_end"`
	ChunkIndex    int    `json:"chunk_index"`
	CaptionImages bool   `json:"caption_images"`
	Language      string `json:"language,omitempty"`
	UserID        string `json:"user_id,omitempty"`
	ModelSource   string `json:"model_source,omitempty"`
	ModelRef      string `json:"model_ref,omitempty"`
}

// PdfChunkParams bundles CallPdfChunk's per-chunk + per-job parameters.
type PdfChunkParams struct {
	BookID        string
	PdfBytes      []byte
	PageStart     int
	PageEnd       int
	ChunkIndex    int
	CaptionImages bool
	Language      string
	UserID        string
	ModelSource   string
	ModelRef      string
}

// CallPdfChunk posts one page-range chunk to knowledge-service and
// returns the resulting chapter + its images. One call per chunk (L6) —
// the caller (ImportProcessor) loops chunks; this bounds each call's
// duration/payload to one chunk's worth of images (spec §6.1/§6.5/§6.8).
func (c *ParseClient) CallPdfChunk(ctx context.Context, p PdfChunkParams) (*PdfChunkResult, error) {
	body := pdfChunkRequest{
		BookID:        p.BookID,
		PdfBytesB64:   base64.StdEncoding.EncodeToString(p.PdfBytes),
		PageStart:     p.PageStart,
		PageEnd:       p.PageEnd,
		ChunkIndex:    p.ChunkIndex,
		CaptionImages: p.CaptionImages,
		Language:      p.Language,
		UserID:        p.UserID,
		ModelSource:   p.ModelSource,
		ModelRef:      p.ModelRef,
	}
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("pdf_chunk marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, "POST", c.BaseURL+"/internal/parse/pdf-chunk", bytes.NewReader(jsonBody))
	if err != nil {
		return nil, fmt.Errorf("pdf_chunk request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", c.InternalToken)

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, fmt.Errorf("pdf_chunk do: %w", err)
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("pdf_chunk read body: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("pdf_chunk status %d: %s", resp.StatusCode, string(respBytes))
	}
	var out PdfChunkResult
	if err := json.Unmarshal(respBytes, &out); err != nil {
		return nil, fmt.Errorf("pdf_chunk unmarshal: %w", err)
	}
	return &out, nil
}

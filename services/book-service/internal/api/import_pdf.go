package api

// import_pdf.go — PDF book import support (docs/specs/2026-07-06-pdf-book-import.md).
//
// pdfPeek backs POST /v1/books/{book_id}/import/pdf-peek: a cheap,
// synchronous page-count check the frontend calls right after file
// select, before the user configures pages_per_chunk. It rejects
// encrypted/corrupted PDFs immediately (422) rather than letting the
// wizard proceed to a chunking step for an unusable file (spec §6.2).
// The actual PDF opening happens in knowledge-service (Python/PyMuPDF —
// book-service has no PDF library); this handler just uploads + forwards.

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

const maxPdfPeekSize = 200 << 20 // 200 MB — mirrors maxImportSize

type pdfPeekReq struct {
	PdfBytesB64 string `json:"pdf_bytes_b64"`
}

type pdfPeekResp struct {
	PageCount int `json:"page_count"`
}

// pdfPeek handles POST /v1/books/{book_id}/import/pdf-peek.
func (s *Server) pdfPeek(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	// Same grant as startImport — this is part of the import flow, not a
	// public read.
	_, _, lifecycle, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book not active")
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, maxPdfPeekSize)
	if err := r.ParseMultipartForm(maxPdfPeekSize); err != nil {
		writeError(w, http.StatusRequestEntityTooLarge, "FILE_TOO_LARGE",
			fmt.Sprintf("file exceeds %d MB limit", maxPdfPeekSize>>20))
		return
	}
	f, _, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "file is required")
		return
	}
	defer f.Close()

	data, err := io.ReadAll(f)
	if err != nil {
		writeError(w, http.StatusRequestEntityTooLarge, "FILE_TOO_LARGE", "failed to read file")
		return
	}

	pageCount, err := s.pdfPeekClientCall(r.Context(), data)
	if err != nil {
		if httpErr, ok := err.(*pdfUpstreamError); ok && httpErr.status == http.StatusUnprocessableEntity {
			writeError(w, http.StatusUnprocessableEntity, "PDF_UNREADABLE", httpErr.detail)
			return
		}
		writeError(w, http.StatusBadGateway, "BOOK_PARSE_UPSTREAM_FAILURE", "failed to inspect PDF")
		return
	}

	writeJSON(w, http.StatusOK, pdfPeekResp{PageCount: pageCount})
}

// pdfUpstreamError carries the knowledge-service response status/detail
// through so pdfPeek can distinguish "PDF unreadable" (422 — a real,
// user-facing rejection) from a genuine upstream failure (502).
type pdfUpstreamError struct {
	status int
	detail string
}

func (e *pdfUpstreamError) Error() string { return e.detail }

// pdfPeekClientCall issues a single POST /internal/parse/pdf-peek.
// Mirrors parseClientCall's (parse.go) request shape/error handling.
func (s *Server) pdfPeekClientCall(ctx context.Context, data []byte) (int, error) {
	body := pdfPeekReq{PdfBytesB64: base64.StdEncoding.EncodeToString(data)}
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return 0, fmt.Errorf("marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(
		ctx, http.MethodPost, s.cfg.KnowledgeServiceURL+"/internal/parse/pdf-peek",
		bytes.NewReader(jsonBody),
	)
	if err != nil {
		return 0, fmt.Errorf("request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return 0, fmt.Errorf("do: %w", err)
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return 0, fmt.Errorf("read body: %w", err)
	}
	if resp.StatusCode == http.StatusUnprocessableEntity {
		var errBody struct {
			Detail string `json:"detail"`
		}
		_ = json.Unmarshal(respBytes, &errBody)
		return 0, &pdfUpstreamError{status: http.StatusUnprocessableEntity, detail: errBody.Detail}
	}
	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("status %d: %s", resp.StatusCode, string(respBytes))
	}
	var out pdfPeekResp
	if err := json.Unmarshal(respBytes, &out); err != nil {
		return 0, fmt.Errorf("unmarshal: %w", err)
	}
	return out.PageCount, nil
}

package api

// W10-M2 — world-map base-image upload. A worldbuilder uploads a map's base image
// (the drawing/render the pins + regions sit on). Server-side multipart upload to
// MinIO (mirrors the chapter-media upload in media.go), then records
// image_object_key + pixel dims on the map. Internal-token gated (mounted under
// /internal), owner-scoped by the ?user_id param — the trusted caller (the BFF)
// passes the authoring user. A map not owned by that user → 404 (no cross-owner
// oracle). Agents cannot upload binaries, so this is a REST route, NOT an MCP tool;
// world_map_get / world_map_list then return image_object_key + a resolved image_url.

import (
	"context"
	"errors"
	"fmt"
	"image"
	// Register the stdlib decoders so image.DecodeConfig can read pixel dims. webp is
	// NOT in the stdlib, so webp uploads store NULL dims (harmless — marker/region
	// coords are relative, so dims are advisory metadata only).
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"net/http"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/minio/minio-go/v7"
)

// uploadWorldMapImage — INTERNAL route (POST /internal/worlds/maps/{map_id}/image),
// owner-scoped by the ?user_id param (trusted caller passes the authoring user). Thin
// wrapper over uploadWorldMapImageCore.
func (s *Server) uploadWorldMapImage(w http.ResponseWriter, r *http.Request) {
	mapID, ok := parseUUIDParam(w, r, "map_id")
	if !ok {
		return
	}
	userID, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "user_id query param required")
		return
	}
	s.uploadWorldMapImageCore(w, r, mapID, userID)
}

// uploadWorldMapImageCore is the shared multipart-to-MinIO body. S7·2 R4 refactor: the
// browser gets a FIRST-PARTY public route (uploadWorldMapImagePublic) that resolves the owner
// from the JWT — NOT an injected ?user_id query param — and calls this same core. The internal
// route keeps passing ownerID from ?user_id (trusted callers). Both funnel through here so the
// upload logic (type/size gates, dims, blob overwrite, version bump) lives once.
func (s *Server) uploadWorldMapImageCore(w http.ResponseWriter, r *http.Request, mapID, userID uuid.UUID) {
	if s.minio == nil {
		writeError(w, http.StatusServiceUnavailable, "MEDIA_UNAVAILABLE", "media storage not configured")
		return
	}

	// Owner-scoped read: confirms ownership (404 for a foreign/missing map — no
	// oracle) AND grabs the current key, so a format-changing re-upload can sweep the
	// orphaned prior object after the replace below.
	var oldKey *string
	if err := s.pool.QueryRow(r.Context(),
		`SELECT image_object_key FROM world_maps WHERE id=$1 AND owner_user_id=$2`, mapID, userID).Scan(&oldKey); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "MAP_NOT_FOUND", "map not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to resolve map")
		return
	}

	if err := r.ParseMultipartForm(maxImageSize); err != nil {
		writeError(w, http.StatusBadRequest, "MEDIA_TOO_LARGE", "file exceeds size limit")
		return
	}
	f, fh, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "file is required")
		return
	}
	defer f.Close()

	contentType := fh.Header.Get("Content-Type")
	ext, allowed := allowedMediaTypes[contentType]
	if !allowed || contentType == "video/mp4" || contentType == "video/webm" {
		writeError(w, http.StatusUnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE",
			"map image must be png, jpg, gif, or webp")
		return
	}
	if fh.Size > int64(maxImageSize) {
		writeError(w, http.StatusRequestEntityTooLarge, "MEDIA_TOO_LARGE",
			fmt.Sprintf("image exceeds %d MB limit", maxImageSize/(1<<20)))
		return
	}

	// Best-effort pixel dims, then rewind so the upload reads the whole file.
	var imgW, imgH *int
	if cfg, _, derr := image.DecodeConfig(f); derr == nil {
		wv, hv := cfg.Width, cfg.Height
		imgW, imgH = &wv, &hv
	}
	if _, serr := f.Seek(0, io.SeekStart); serr != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "cannot read upload")
		return
	}

	ctx := r.Context()
	if err := s.ensureMediaBucket(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "storage init failed")
		return
	}
	// A map has ONE base image; key by map id + ext so a re-upload of the same type
	// overwrites cleanly.
	objectKey := fmt.Sprintf("worlds/maps/%s/base%s", mapID, ext)
	if _, err := s.minio.PutObject(ctx, mediaBucket, objectKey, io.LimitReader(f, int64(maxImageSize)), fh.Size,
		minio.PutObjectOptions{ContentType: contentType}); err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "upload failed")
		return
	}
	imageVersion, err := s.recordMapImage(ctx, mapID, userID, objectKey, imgW, imgH)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to record image")
		return
	}
	// A format change (png→jpg) changes the deterministic key, orphaning the prior
	// object — sweep it best-effort (never fail the upload; the row already points at
	// the new key).
	if oldKey != nil && *oldKey != "" && *oldKey != objectKey {
		_ = s.minio.RemoveObject(ctx, mediaBucket, *oldKey, minio.RemoveObjectOptions{})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"image_object_key": objectKey,
		"image_w":          imgW,
		"image_h":          imgH,
		"image_url":        s.mediaURL(objectKey),
		"image_version":    imageVersion,
	})
}

// recordMapImage writes the uploaded object key + pixel dims onto the map and bumps the
// image's OWN OCC counter (S-07 §1). It bumps `image_version` — NOT the metadata `version` —
// so an image upload and a concurrent rename never collide: a rename gates on `version`, which
// this write leaves untouched. Owner-scoped (a foreign/missing map matches 0 rows → ErrNoRows).
// Extracted so a test can exercise the exact SQL without a MinIO round-trip.
func (s *Server) recordMapImage(ctx context.Context, mapID, ownerID uuid.UUID, objectKey string, imgW, imgH *int) (int, error) {
	var imageVersion int
	err := s.pool.QueryRow(ctx,
		`UPDATE world_maps SET image_object_key=$1, image_w=$2, image_h=$3, image_version=image_version+1, updated_at=now()
		 WHERE id=$4 AND owner_user_id=$5 RETURNING image_version`,
		objectKey, imgW, imgH, mapID, ownerID).Scan(&imageVersion)
	return imageVersion, err
}

// uploadWorldMapImagePublic — S7·2 R4. The PUBLIC, JWT-resolved base-image upload
// (POST /v1/worlds/{world_id}/maps/{map_id}/image). requireWorldOwner gates the world from the
// forwarded Bearer token (the browser can call this; the internal route it wraps cannot be
// reached from a browser). Owner comes from the JWT, never a query param.
func (s *Server) uploadWorldMapImagePublic(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	mapID, ok := parseUUIDParam(w, r, "map_id")
	if !ok {
		return
	}
	ownerID, ok := s.requireWorldOwner(w, r, worldID)
	if !ok {
		return
	}
	s.uploadWorldMapImageCore(w, r, mapID, ownerID)
}

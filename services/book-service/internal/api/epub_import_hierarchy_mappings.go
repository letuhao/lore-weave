package api

import (
	"encoding/json"
	"net/http"
	"sort"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// epubImportHierarchyPayload is a read model for the worker. It contains the
// selected chapter leaves plus their ToC ancestors, so Composition can persist
// a lossless closure without querying Book Service's database itself.
type epubImportHierarchyPayload struct {
	BookID uuid.UUID                    `json:"book_id"`
	UserID uuid.UUID                    `json:"user_id"`
	Nodes  []epubImportHierarchyNodeDTO `json:"nodes"`
}

type epubImportHierarchyNodeDTO struct {
	SourceKey       string     `json:"source_key"`
	ParentSourceKey *string    `json:"parent_source_key,omitempty"`
	Role            string     `json:"role"`
	Title           string     `json:"title"`
	Ordinal         int        `json:"ordinal"`
	Depth           int        `json:"depth"`
	ChapterID       *uuid.UUID `json:"chapter_id,omitempty"`
}

type epubImportHierarchyMappingsRequest struct {
	Mappings []epubImportHierarchyMappingDTO `json:"mappings"`
}

type epubImportHierarchyMappingDTO struct {
	SourceKey       string     `json:"source_key"`
	HierarchyNodeID uuid.UUID  `json:"hierarchy_node_id"`
	StructureNodeID *uuid.UUID `json:"structure_node_id,omitempty"`
	ChapterID       *uuid.UUID `json:"chapter_id,omitempty"`
}

// getEPUBImportHierarchy exposes a finalized job's selected navigation closure
// to the worker. It is intentionally internal: the worker forwards it to
// Composition, while public clients use Book's import status/items APIs.
func (s *Server) getEPUBImportHierarchy(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	var result epubImportHierarchyPayload
	if err := s.pool.QueryRow(r.Context(), `
SELECT book_id,user_id
FROM import_jobs
WHERE id=$1 AND pipeline_version=$2 AND status IN ('completed','completed_with_warnings')
`, jobID, epubImportPipelineVersion).Scan(&result.BookID, &result.UserID); err != nil {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "finalized import job not found")
		return
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT source_key,parent_source_key,COALESCE(role,'unknown'),COALESCE(title,''),ordinal,depth,chapter_id,status
FROM import_job_items
WHERE job_id=$1
ORDER BY ordinal,source_key
`, jobID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to load import hierarchy")
		return
	}
	defer rows.Close()
	type rawNode struct {
		node     epubImportHierarchyNodeDTO
		status   string
		selected bool
	}
	all := make(map[string]rawNode)
	include := make(map[string]bool)
	for rows.Next() {
		var item rawNode
		var chapterID *uuid.UUID
		if err := rows.Scan(&item.node.SourceKey, &item.node.ParentSourceKey, &item.node.Role, &item.node.Title, &item.node.Ordinal, &item.node.Depth, &chapterID, &item.status); err != nil {
			writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to read import hierarchy")
			return
		}
		if item.status == "active" && chapterID != nil {
			item.node.ChapterID = chapterID
			item.selected = true
			include[item.node.SourceKey] = true
		}
		all[item.node.SourceKey] = item
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to read import hierarchy")
		return
	}
	// Include the ancestors of active leaves even though grouping nodes themselves
	// are skipped import items. A malformed cycle is bounded defensively.
	for sourceKey := range include {
		for steps, node := 0, all[sourceKey]; steps <= len(all) && node.node.ParentSourceKey != nil; steps++ {
			parentKey := *node.node.ParentSourceKey
			if include[parentKey] {
				break
			}
			include[parentKey] = true
			parent, found := all[parentKey]
			if !found {
				break
			}
			node = parent
		}
	}
	for sourceKey := range include {
		if item, found := all[sourceKey]; found {
			result.Nodes = append(result.Nodes, item.node)
		}
	}
	sort.Slice(result.Nodes, func(i, j int) bool {
		if result.Nodes[i].Ordinal == result.Nodes[j].Ordinal {
			return result.Nodes[i].SourceKey < result.Nodes[j].SourceKey
		}
		return result.Nodes[i].Ordinal < result.Nodes[j].Ordinal
	})
	writeJSON(w, http.StatusOK, result)
}

// applyEPUBImportHierarchyMappings is Book's only write seam for Composition's
// ToC result. The mapping's opaque IDs are not foreign keys: Composition owns
// their lifecycle. Chapters are updated only when this job created them, which
// prevents a merge/reimport from silently moving earlier user-visible chapters.
func (s *Server) applyEPUBImportHierarchyMappings(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	var in epubImportHierarchyMappingsRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || len(in.Mappings) == 0 {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "hierarchy mappings are required")
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to apply hierarchy mappings")
		return
	}
	defer tx.Rollback(r.Context())
	var bookID uuid.UUID
	if err := tx.QueryRow(r.Context(), `
SELECT book_id FROM import_jobs
WHERE id=$1 AND pipeline_version=$2 AND status IN ('completed','completed_with_warnings')
FOR UPDATE
`, jobID, epubImportPipelineVersion).Scan(&bookID); err != nil {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "finalized import job not found")
		return
	}
	mappedChapters := 0
	for _, mapping := range in.Mappings {
		if mapping.SourceKey == "" || mapping.HierarchyNodeID == uuid.Nil {
			writeError(w, http.StatusBadRequest, "INVALID_BODY", "hierarchy mapping is invalid")
			return
		}
		var expectedChapterID *uuid.UUID
		if err := tx.QueryRow(r.Context(), `
SELECT chapter_id FROM import_job_items WHERE job_id=$1 AND source_key=$2
`, jobID, mapping.SourceKey).Scan(&expectedChapterID); err != nil {
			writeError(w, http.StatusBadRequest, "INVALID_BODY", "hierarchy mapping source key is not part of the import")
			return
		}
		if !sameOptionalUUID(expectedChapterID, mapping.ChapterID) {
			writeError(w, http.StatusBadRequest, "INVALID_BODY", "hierarchy mapping chapter does not match the import item")
			return
		}
		var priorPartID *uuid.UUID
		if mapping.ChapterID != nil && mapping.StructureNodeID != nil {
			// Require immutable provenance from THIS job. The job may have linked a
			// source-key duplicate from an earlier import, but it must not remap it.
			err := tx.QueryRow(r.Context(), `
SELECT c.structure_node_id
FROM chapters c
JOIN chapter_import_provenance p ON p.chapter_id=c.id
WHERE c.id=$1 AND c.book_id=$2 AND p.import_job_id=$3
FOR UPDATE OF c
`, *mapping.ChapterID, bookID, jobID).Scan(&priorPartID)
			if err == nil {
				if _, err := tx.Exec(r.Context(), `UPDATE chapters SET structure_node_id=$2,updated_at=now() WHERE id=$1`, *mapping.ChapterID, *mapping.StructureNodeID); err != nil {
					writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to apply chapter hierarchy")
					return
				}
				mappedChapters++
			} else if err != pgx.ErrNoRows {
				writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to load chapter hierarchy")
				return
			}
		}
		if _, err := tx.Exec(r.Context(), `
INSERT INTO import_job_hierarchy_mappings(
  job_id,source_key,chapter_id,hierarchy_node_id,structure_node_id,prior_structure_node_id
) VALUES($1,$2,$3,$4,$5,$6)
ON CONFLICT (job_id,source_key) DO NOTHING
`, jobID, mapping.SourceKey, mapping.ChapterID, mapping.HierarchyNodeID, mapping.StructureNodeID, priorPartID); err != nil {
			writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to persist hierarchy mapping")
			return
		}
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to commit hierarchy mappings")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"mapped_chapters": mappedChapters})
}

func sameOptionalUUID(left, right *uuid.UUID) bool {
	if left == nil || right == nil {
		return left == nil && right == nil
	}
	return *left == *right
}

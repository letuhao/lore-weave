package api

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/epubimport"
)

// applyEPUBImportMetadata applies only fields represented by the Book model.
// Every mutation is journaled so rollback can preserve a later user edit.
func (s *Server) applyEPUBImportMetadata(ctx context.Context, tx pgx.Tx, jobID, bookID uuid.UUID, targetMode string, optionsJSON, inspectionJSON []byte) ([]string, error) {
	var inspection epubimport.Inspection
	if err := json.Unmarshal(inspectionJSON, &inspection); err != nil {
		return nil, fmt.Errorf("decode EPUB source inspection: %w", err)
	}
	var options struct {
		MetadataPolicy map[string]string `json:"metadata_policy"`
	}
	if err := json.Unmarshal(optionsJSON, &options); err != nil {
		return nil, fmt.Errorf("decode EPUB metadata policy: %w", err)
	}
	policy := func(field string) string {
		value := strings.ToLower(strings.TrimSpace(options.MetadataPolicy[field]))
		if value == "" {
			if targetMode == "new_book" {
				return "use_source"
			}
			return "keep_existing"
		}
		return value
	}

	var current struct {
		Title, Description, Language string
		Genres                       []string
	}
	if err := tx.QueryRow(ctx, `SELECT title,COALESCE(description,''),COALESCE(original_language,''),genre_tags FROM books WHERE id=$1 FOR UPDATE`, bookID).
		Scan(&current.Title, &current.Description, &current.Language, &current.Genres); err != nil {
		return nil, err
	}

	metadataApplied := make([]string, 0, 4)
	applyText := func(field, column, source, existing string) error {
		source = strings.TrimSpace(source)
		mode := policy(field)
		if source == "" || mode == "keep_existing" {
			return nil
		}
		if mode != "use_source" {
			return fmt.Errorf("unsupported metadata policy %q for %s", mode, field)
		}
		if source == existing {
			metadataApplied = append(metadataApplied, field)
			return nil
		}
		before, _ := json.Marshal(existing)
		after, _ := json.Marshal(source)
		if _, err := tx.Exec(ctx, `INSERT INTO import_job_effects(job_id,effect_type,effect_key,before_json,after_json) VALUES($1,'book_metadata',$2,$3,$4) ON CONFLICT (job_id,effect_type,effect_key) DO NOTHING`, jobID, field, before, after); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `UPDATE books SET `+column+`=$2,updated_at=now() WHERE id=$1`, bookID, source); err != nil {
			return err
		}
		metadataApplied = append(metadataApplied, field)
		return nil
	}
	if err := applyText("title", "title", inspection.Metadata.Title, current.Title); err != nil {
		return nil, err
	}
	if err := applyText("description", "description", inspection.Metadata.Description, current.Description); err != nil {
		return nil, err
	}
	language := strings.TrimSpace(inspection.Metadata.Language)
	if language != "" {
		language = importedLanguage(language)
	}
	if err := applyText("language", "original_language", language, current.Language); err != nil {
		return nil, err
	}

	if subjects := normalizeMetadataSubjects(inspection.Metadata.Subjects); len(subjects) > 0 {
		mode := policy("subjects")
		genres := append([]string(nil), current.Genres...)
		if mode == "use_source" {
			genres = subjects
		} else if mode == "merge" {
			genres = mergeMetadataSubjects(genres, subjects)
		} else if mode != "keep_existing" {
			return nil, fmt.Errorf("unsupported metadata policy %q for subjects", mode)
		}
		if !equalStringSlices(genres, current.Genres) {
			before, _ := json.Marshal(current.Genres)
			after, _ := json.Marshal(genres)
			if _, err := tx.Exec(ctx, `INSERT INTO import_job_effects(job_id,effect_type,effect_key,before_json,after_json) VALUES($1,'book_metadata','subjects',$2,$3) ON CONFLICT (job_id,effect_type,effect_key) DO NOTHING`, jobID, before, after); err != nil {
				return nil, err
			}
			if _, err := tx.Exec(ctx, `UPDATE books SET genre_tags=$2,updated_at=now() WHERE id=$1`, bookID, genres); err != nil {
				return nil, err
			}
		}
		if mode != "keep_existing" {
			metadataApplied = append(metadataApplied, "subjects")
		}
	}
	return metadataApplied, nil
}

func normalizeMetadataSubjects(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			if _, ok := seen[value]; !ok {
				seen[value] = struct{}{}
				result = append(result, value)
			}
		}
	}
	return result
}

func mergeMetadataSubjects(existing, source []string) []string {
	return normalizeMetadataSubjects(append(append([]string(nil), existing...), source...))
}

func equalStringSlices(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func (s *Server) rollbackEPUBImportMetadata(ctx context.Context, tx pgx.Tx, jobID, bookID uuid.UUID, conflicts *[]any) error {
	rows, err := tx.Query(ctx, `SELECT effect_key,before_json,after_json,applied_at FROM import_job_effects WHERE job_id=$1 AND effect_type='book_metadata' AND rolled_back_at IS NULL ORDER BY effect_key FOR UPDATE`, jobID)
	if err != nil {
		return err
	}
	type metadataEffect struct {
		field      string
		beforeJSON []byte
		afterJSON  []byte
	}
	effects := make([]metadataEffect, 0)
	for rows.Next() {
		var effect metadataEffect
		var appliedAt interface{}
		if err := rows.Scan(&effect.field, &effect.beforeJSON, &effect.afterJSON, &appliedAt); err != nil {
			return err
		}
		effects = append(effects, effect)
	}
	if err := rows.Err(); err != nil {
		return err
	}
	rows.Close()
	for _, effect := range effects {
		column := effect.field
		if effect.field == "language" {
			column = "original_language"
		}
		matchesAppliedValue := false
		if effect.field == "subjects" {
			var genres []string
			if err := tx.QueryRow(ctx, `SELECT genre_tags FROM books WHERE id=$1`, bookID).Scan(&genres); err != nil {
				return err
			}
			var expected []string
			if err := json.Unmarshal(effect.afterJSON, &expected); err != nil {
				return err
			}
			matchesAppliedValue = equalStringSlices(genres, expected)
		} else {
			var value string
			if err := tx.QueryRow(ctx, `SELECT `+column+` FROM books WHERE id=$1`, bookID).Scan(&value); err != nil {
				return err
			}
			var expected string
			if err := json.Unmarshal(effect.afterJSON, &expected); err != nil {
				return err
			}
			matchesAppliedValue = value == expected
		}
		if !matchesAppliedValue {
			*conflicts = append(*conflicts, map[string]any{"code": "rollback_conflict_user_modified_metadata", "field": effect.field})
			continue
		}
		var before any
		if err := json.Unmarshal(effect.beforeJSON, &before); err != nil {
			return err
		}
		if effect.field == "subjects" {
			var values []string
			_ = json.Unmarshal(effect.beforeJSON, &values)
			_, err = tx.Exec(ctx, `UPDATE books SET genre_tags=$2,updated_at=now() WHERE id=$1`, bookID, values)
		} else {
			_, err = tx.Exec(ctx, `UPDATE books SET `+column+`=$2,updated_at=now() WHERE id=$1`, bookID, before)
		}
		if err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `UPDATE import_job_effects SET rolled_back_at=now() WHERE job_id=$1 AND effect_type='book_metadata' AND effect_key=$2`, jobID, effect.field); err != nil {
			return err
		}
	}
	return nil
}

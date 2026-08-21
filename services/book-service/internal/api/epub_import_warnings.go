package api

import (
	"encoding/json"
	"net/http"
	"strings"
)

type epubImportJobWarningRequest struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Stage   string `json:"stage,omitempty"`
}

// recordEPUBImportJobWarning is the worker's durable seam for best-effort
// post-finalize work such as Composition materialization. It is idempotent by
// (job, code, stage), so retries cannot inflate the report.
func (s *Server) recordEPUBImportJobWarning(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	var body epubImportJobWarningRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.Code) == "" || strings.TrimSpace(body.Message) == "" {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "warning code and message are required")
		return
	}
	var jobExists bool
	if err := s.pool.QueryRow(r.Context(), `SELECT EXISTS(SELECT 1 FROM import_jobs WHERE id=$1 AND pipeline_version=$2)`, jobID, epubImportPipelineVersion).Scan(&jobExists); err != nil || !jobExists {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	warning, _ := json.Marshal(map[string]any{"code": strings.TrimSpace(body.Code), "message": strings.TrimSpace(body.Message), "stage": strings.TrimSpace(body.Stage)})
	key := strings.TrimSpace(body.Stage) + ":" + strings.TrimSpace(body.Code)
	if _, err := s.pool.Exec(r.Context(), `INSERT INTO import_job_effects(job_id,effect_type,effect_key,after_json) VALUES($1,'job_warning',$2,$3) ON CONFLICT (job_id,effect_type,effect_key) DO UPDATE SET after_json=EXCLUDED.after_json,applied_at=now()`, jobID, key, warning); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to persist import warning")
		return
	}
	stage := strings.TrimSpace(body.Stage)
	if stage == "" {
		stage = "worker"
	}
	EPUBImportWarningsTotal.WithLabelValues(stage).Inc()
	_, _ = s.pool.Exec(r.Context(), `UPDATE import_jobs SET status='completed_with_warnings',updated_at=now() WHERE id=$1 AND status='completed'`, jobID)
	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": jobID, "status": "recorded"})
}

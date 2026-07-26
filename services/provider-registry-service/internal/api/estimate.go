package api

// S5a — campaign cost-estimate pricing oracle.
//
// POST /internal/billing/estimate is a PURE pricing function: given a batch of
// (model, dimension, token-count) items it returns each item's USD cost using
// the model's registered pricing JSONB. It owns NO workload knowledge — the
// caller (campaign-service) derives token counts from chapter sizes and the
// stage→model map; this endpoint only multiplies tokens by the per-MTok price.
//
// Per-item failure (model not found / unpriced) is a SOFT per-item status, not a
// request error: a campaign estimate spanning ~6 models must not 500 because one
// model lacks pricing — the caller surfaces the unpriced items as a band caveat.
// The math reuses billing.PriceText / billing.PriceEmbedding so an estimate and
// the live reconcile guardrail can never disagree.

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/billing"
)

// modelPricer is the slice of *jobs.Repo this endpoint needs. Declared as an
// interface so estimateItems is unit-testable with a fake pricer (no DB).
// EstimateModelInfo returns pricing + provider_kind in one row (the estimate
// also surfaces a cloud/local badge — D-FACTORY-EST-PROVIDER-KIND).
type modelPricer interface {
	EstimateModelInfo(ctx context.Context, modelSource string, ownerUserID, modelRef uuid.UUID) (billing.Pricing, string, bool, error)
}

// estimateItem is one model+token request in the batch. dimension selects the
// pricing dimension: "text" (input+output, the default) or "input_only"
// (embedding — output tokens ignored, only InputPerMTok needed).
type estimateItem struct {
	Label        string `json:"label"`
	ModelSource  string `json:"model_source"`
	ModelRef     string `json:"model_ref"`
	Dimension    string `json:"dimension"`
	InputTokens  int    `json:"input_tokens"`
	OutputTokens int    `json:"output_tokens"`
}

type estimateResultItem struct {
	Label        string  `json:"label"`
	Status       string  `json:"status"` // ok | unpriced | not_found | bad_request
	EstimatedUSD float64 `json:"estimated_usd"`
	// D-FACTORY-EST-PROVIDER-KIND — the resolved provider kind + whether it runs
	// on the user's own hardware (cloud/local badge). Empty/false for a model that
	// couldn't be resolved (not_found / bad_request).
	ProviderKind string `json:"provider_kind"`
	IsLocal      bool   `json:"is_local"`
}

type estimateRequest struct {
	OwnerUserID string         `json:"owner_user_id"`
	Items       []estimateItem `json:"items"`
}

type estimateResponse struct {
	Items []estimateResultItem `json:"items"`
}

const (
	estStatusOK         = "ok"
	estStatusUnpriced   = "unpriced"
	estStatusNotFound   = "not_found"
	estStatusBadRequest = "bad_request"
)

// estimateItems prices each item against the owner's registered models. Pure +
// DB-seam-injectable: a model-not-found or unpriced model is recorded on the
// item, never returned as a top-level error (only an infra error from the pricer
// — e.g. a DB outage — propagates and fails the whole request).
func estimateItems(ctx context.Context, pricer modelPricer, owner uuid.UUID, items []estimateItem) ([]estimateResultItem, error) {
	out := make([]estimateResultItem, 0, len(items))
	for _, it := range items {
		res := estimateResultItem{Label: it.Label}
		// Validate model_source per-item so one bad source doesn't fail the whole
		// estimate (keeps the "soft per-item" invariant — only a genuine infra
		// error from the pricer propagates). ModelPricing itself hard-errors on an
		// unknown source, which would otherwise nuke the batch.
		if it.ModelSource != "user_model" && it.ModelSource != "platform_model" {
			res.Status = estStatusBadRequest
			out = append(out, res)
			continue
		}
		ref, err := uuid.Parse(it.ModelRef)
		if err != nil {
			res.Status = estStatusBadRequest
			out = append(out, res)
			continue
		}
		pricing, providerKind, found, err := pricer.EstimateModelInfo(ctx, it.ModelSource, owner, ref)
		if err != nil {
			// Infra error (bad model_source / DB failure) — fail the request so
			// the caller can 502 rather than silently under-price the estimate.
			return nil, err
		}
		if !found {
			res.Status = estStatusNotFound
			out = append(out, res)
			continue
		}
		// Model resolved → surface its kind + cloud/local flag (ok or unpriced).
		res.ProviderKind = providerKind
		res.IsLocal = billing.IsLocalKind(providerKind)
		var usd float64
		if it.Dimension == "input_only" {
			usd, err = billing.PriceEmbedding(it.InputTokens, pricing)
		} else {
			usd, err = billing.PriceText(it.InputTokens, it.OutputTokens, pricing)
		}
		if errors.Is(err, billing.ErrUnpriced) {
			res.Status = estStatusUnpriced
			out = append(out, res)
			continue
		}
		if err != nil {
			return nil, err
		}
		res.Status = estStatusOK
		res.EstimatedUSD = usd
		out = append(out, res)
	}
	return out, nil
}

// internalBillingEstimate handles POST /internal/billing/estimate.
func (s *Server) internalBillingEstimate(w http.ResponseWriter, r *http.Request) {
	var in estimateRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "ESTIMATE_VALIDATION", "invalid payload")
		return
	}
	owner, err := uuid.Parse(in.OwnerUserID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "ESTIMATE_VALIDATION", "invalid owner_user_id")
		return
	}
	items, err := estimateItems(r.Context(), s.jobsRepo, owner, in.Items)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ESTIMATE_PRICING_ERROR", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, estimateResponse{Items: items})
}

// priceVoiceRequest — C6 / SD-C6: price ONE STT/TTS invocation from the model's registered rate.
// `kind` selects the dimension: "stt" (units = audio SECONDS, priced per_second) or "tts" (units =
// CHARACTERS, priced per_kchar). Keeps the "pricing lives with the model in provider-registry" invariant
// — the voice caller (chat) resolves the $ here instead of hardcoding a rate.
type priceVoiceRequest struct {
	OwnerUserID string  `json:"owner_user_id"`
	ModelSource string  `json:"model_source"`
	ModelRef    string  `json:"model_ref"`
	Kind        string  `json:"kind"` // "stt" | "tts"
	Units       float64 `json:"units"`
}

type priceVoiceResponse struct {
	Status  string  `json:"status"` // ok | unpriced | not_found | bad_request
	CostUSD float64 `json:"cost_usd"`
	Priced  bool    `json:"priced"` // false ⇒ the model has no rate for this dimension (cost stays 0)
}

// internalBillingPriceVoice handles POST /internal/billing/price-voice.
func (s *Server) internalBillingPriceVoice(w http.ResponseWriter, r *http.Request) {
	var in priceVoiceRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "PRICE_VALIDATION", "invalid payload")
		return
	}
	owner, err := uuid.Parse(in.OwnerUserID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "PRICE_VALIDATION", "invalid owner_user_id")
		return
	}
	ref, err := uuid.Parse(in.ModelRef)
	if err != nil || (in.ModelSource != "user_model" && in.ModelSource != "platform_model") ||
		(in.Kind != "stt" && in.Kind != "tts") {
		writeJSON(w, http.StatusOK, priceVoiceResponse{Status: estStatusBadRequest})
		return
	}
	pricing, _, found, err := s.jobsRepo.EstimateModelInfo(r.Context(), in.ModelSource, owner, ref)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "PRICE_PRICING_ERROR", err.Error())
		return
	}
	if !found {
		writeJSON(w, http.StatusOK, priceVoiceResponse{Status: estStatusNotFound})
		return
	}
	var usd float64
	if in.Kind == "stt" {
		usd, err = billing.PriceSTT(in.Units, pricing)
	} else {
		usd, err = billing.PriceTTS(int(in.Units), pricing)
	}
	if errors.Is(err, billing.ErrUnpriced) {
		// The model has no rate for this dimension — a soft "unpriced", cost 0 (not an error). A $0
		// local model (Whisper/Kokoro) carries an explicit 0 rate and returns ok with cost 0 instead.
		writeJSON(w, http.StatusOK, priceVoiceResponse{Status: estStatusUnpriced})
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "PRICE_PRICING_ERROR", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, priceVoiceResponse{Status: estStatusOK, CostUSD: usd, Priced: true})
}

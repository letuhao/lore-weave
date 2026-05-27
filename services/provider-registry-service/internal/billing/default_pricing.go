package billing

// Default price table — a static, best-effort map of well-known cloud text
// models to their published per-million-token rates (design §3.2).
//
// This table is consulted ONLY at user-model registration, to pre-fill the
// editable `user_models.pricing` JSONB. It is never the live source of truth:
// a stale rate is corrected by the user in the registration form, and an
// unknown model simply leaves `pricing` empty — which fails closed (402), not
// open. Media models are intentionally absent (CLARIFY #2): they must be
// priced explicitly.

// usd is a helper for taking the address of a float literal.
func usd(v float64) *float64 { return &v }

// priceKey joins provider_kind + provider_model_name with a NUL separator
// (cannot occur in either string).
func priceKey(providerKind, modelName string) string {
	return providerKind + "\x00" + modelName
}

// textPricing builds a Pricing with only the two text dimensions set.
func textPricing(inPerMTok, outPerMTok float64) Pricing {
	return Pricing{InputPerMTok: usd(inPerMTok), OutputPerMTok: usd(outPerMTok)}
}

// defaultPriceTable — keyed by priceKey(provider_kind, provider_model_name).
// Rates are USD per 1M tokens (input, output).
var defaultPriceTable = map[string]Pricing{
	// OpenAI.
	priceKey("openai", "gpt-4o"):       textPricing(2.50, 10.00),
	priceKey("openai", "gpt-4o-mini"):  textPricing(0.15, 0.60),
	priceKey("openai", "gpt-4.1"):      textPricing(2.00, 8.00),
	priceKey("openai", "gpt-4.1-mini"): textPricing(0.40, 1.60),
	priceKey("openai", "o3"):           textPricing(2.00, 8.00),
	priceKey("openai", "o4-mini"):      textPricing(1.10, 4.40),

	// Anthropic.
	priceKey("anthropic", "claude-3-5-sonnet"): textPricing(3.00, 15.00),
	priceKey("anthropic", "claude-3-5-haiku"):  textPricing(0.80, 4.00),
	priceKey("anthropic", "claude-sonnet-4"):   textPricing(3.00, 15.00),
	priceKey("anthropic", "claude-opus-4"):     textPricing(15.00, 75.00),

	// Google Gemini (registered under a custom 'gemini' provider_kind —
	// the provider_kind CHECK was dropped in migrate v3).
	priceKey("gemini", "gemini-2.5-pro"):   textPricing(1.25, 10.00),
	priceKey("gemini", "gemini-2.5-flash"): textPricing(0.30, 2.50),
}

// DefaultPricing returns the pre-fill Pricing for a known cloud text model,
// and true. For an unknown model it returns the zero Pricing and false — the
// caller then leaves `pricing` empty so the model fails closed until priced.
func DefaultPricing(providerKind, modelName string) (Pricing, bool) {
	p, ok := defaultPriceTable[priceKey(providerKind, modelName)]
	return p, ok
}

// Package llmgw is the Go SDK for the LoreWeave unified LLM gateway.
//
// It mirrors the Python SDK (sdks/python/loreweave_llm) in shape and
// semantics — submit_job → poll → terminal → decoded result — adapted
// to idiomatic Go (sync API, context cancellation, errors.Is matching).
//
// Use one Client per process; *http.Client is goroutine-safe.
//
// Typical usage:
//
//	client, err := llmgw.NewClient(llmgw.Options{
//	    BaseURL:       cfg.LLMGatewayInternalURL,
//	    AuthMode:      llmgw.AuthInternal,
//	    InternalToken: cfg.InternalServiceToken,
//	})
//	if err != nil {
//	    log.Fatal(err)
//	}
//	size := "1024x1024"
//	result, err := client.GenerateImage(ctx, llmgw.GenerateImageRequest{
//	    Prompt:      "a sunset over mountains",
//	    ModelSource: llmgw.ModelSourceUser,
//	    ModelRef:    "0192f5ad-3c4d-7890-a000-000000000001",
//	    Size:        &size,
//	    UserID:      ownerID.String(),
//	})
//	if err != nil {
//	    if errors.Is(err, llmgw.ErrImageContentPolicy) {
//	        // surface content-policy violation to caller
//	    }
//	    return err
//	}
//	// result.Data[0].URL has the generated image URL
//
// Phase 5e-β.1 ships image_gen only; audio_gen lands in Phase 5e-β.2.
package llmgw

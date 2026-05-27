# LoreWeave extraction prompts

This directory holds the canonical prompt files for the 5 extraction
operations (entity, relation, event, fact, summarize_level). The
SDK's `get_extractor_version(op=...)` reads these files at import
time and computes a per-op SHA256 hash that gets folded into the P2
cache key — so editing any prompt invalidates only the affected op's
cached results on next extraction.

## Files

- `entity_extraction_system.md` + `entity_extraction.md`
- `relation_extraction_system.md` + `relation_extraction.md`
- `event_extraction_system.md` + `event_extraction.md`
- `fact_extraction_system.md` + `fact_extraction.md`
- `summarize_level_extraction.md` (P3, no separate system prompt)

The `_system.md` files are the upstream `messages[0].content`
(role=system); the bare-named files are the prompt-engineering
documentation/scratchpad and not always shipped over the wire.

## Dev hot-reload — `LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE=1`

In production, `get_extractor_version()` reads each prompt file
**once at module import** and caches the resulting version string for
the process lifetime. This is correct for production (prompt files
ship with the deployed image, never change between restarts) — but
it's the wrong behaviour for local dev when you're iterating on a
prompt:

1. Edit `entity_extraction_system.md`
2. Re-run extraction
3. **Cache hit** on the OLD version → no LLM call → silent stale
   results

To force the SDK to recompute the version on every call, set:

```bash
export LOREWEAVE_EXTRACTOR_VERSION_DEV_RECOMPUTE=1
```

This is honoured by both `get_extractor_version()` (global) and
`get_extractor_version(op=<name>)` (per-op). Cost is one extra
`read_bytes()` + `sha256` per call; negligible compared to LLM
latency.

**Never set this in production deploys** — it would defeat the
import-time cache and add unnecessary I/O to every extraction call
(typically thousands per book). The env var is opt-in by design so
production keeps the fast path; CI + dev set it explicitly.

## Adding a new op

If you add a new extractor (new `<op>_extraction*.md` files), also
update `_OP_PROMPTS` in `sdks/python/loreweave_extraction/_version.py`
so the per-op hashing knows which files to feed. Missing the
registration is silent: the global hash will include the new file
(via filesystem glob in `_compute_extractor_version`), but per-op
callers will raise `ValueError` for the unknown op name.

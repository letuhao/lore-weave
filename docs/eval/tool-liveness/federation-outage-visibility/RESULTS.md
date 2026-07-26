# Federation outage visibility — measured before/after (2026-07-23)

Plan: `docs/plans/2026-07-23-federation-outage-visibility.md`.
Origin: the glossary de-federation (`docs/eval/tool-liveness/glossary-unification/RESULTS.md`)
ran undetected until a live E2E happened to trip over it.

**Reproducible outage:** `docker stop infra-glossary-service-1`, wait one refresh
(`AI_GATEWAY_CATALOG_REFRESH_MS=30000`), confirm `PARTIAL` in the gateway log. Reversible.
Model: gemma-4-26b (`019ebb72-…`), scenario S00b, book `019f84e1-…`.

Checkpoints: **M0** outage/pre-fix · **M1** outage/post-fix · **M2** healthy/post-fix (the
no-false-alarm control).

---

## The headline: what the agent told the user

Same scenario, same outage, same model. This is the acceptance criterion — everything else
is instrumentation.

| | **M0 — before** | **M1 — after** |
|---|---|---|
| turn B | *"I've **loaded the glossary tools**. I can help you with: auto-enriching lore, checking lore, viewing timelines…"* | *"it looks like the **glossary service is currently unavailable**. I can't load the specific curation tools until the service is back online. Please try again in a little while!"* |
| turn C | *"I'm sorry, but I can't save 'Lâm Uyên' **because I don't have any details about her**."* | *"the **glossary service is currently unavailable**, so I don't have access to the tools needed… Once the service is back online, I'll be able to add Lâm Uyên as a 'betrayed bride'."* |

**Before, the agent invented a false explanation and blamed the user** — and advertised a
working glossary capability set assembled from the single surviving stray tool. After, it
diagnoses the outage correctly, keeps the user's intent, and promises recovery.

Thrash also dropped, because a definitive answer ends the search:

| metric | M0 | M1 |
|---|---|---|
| tool calls (turns A/B/C) | 4 / 2 / 2 | **3 / 1 / 0** |
| discovery calls | 4 | **1** |
| max consecutive discovery | 4 | **3** |

---

## Wire-level evidence

| probe | M0 (outage, pre-fix) | M1 (outage, post-fix) | M2 (healthy, post-fix) |
|---|---|---|---|
| `tool_list("glossary")` keys | `[category, count, tools]` — reads as a **complete, healthy** answer | `[…, incomplete, note, unavailable_providers]` | `[category, count, tools]` — **clean, no false alarm** |
| `tool_load("glossary_propose_entities")` | `{"not_found": [...]}` — **asserts the tool does not exist** | `{"provider_unavailable": [...], "unavailable_providers": ["glossary"], "note": "…does NOT mean the tool does not exist…"}` | loads the real schema |
| `/health/federation` | *(did not exist)* | **503** `degraded` after 3 consecutive partials | **200** `ok` |
| `/health` | `{"status":"ok"}` | `{"status":"ok"}` *(deliberate — see below)* | `{"status":"ok"}` |
| gateway log | same WARN reprinted every 30s | **1 ERROR on the transition**, 1 LOG on recovery | — |
| container health | `healthy` | `healthy` *(deliberate)* | `healthy` |

Degradation threshold, observed live (polling every 15s through a real outage):

```
HTTP 200 | degraded=False consecutive=1 unavailable=['glossary']
HTTP 200 | degraded=False consecutive=2 unavailable=['glossary']
HTTP 503 | degraded=True  consecutive=3 unavailable=['glossary']   ← threshold
HTTP 503 | degraded=True  consecutive=5 unavailable=['glossary']
…glossary restarted…
HTTP 200 | degraded=False consecutive=0 partial_since=None          ← clean recovery
```

```
ERROR [FederationService] provider 'glossary' became UNAVAILABLE — all of its tools just
      left the federated catalog; agents can no longer discover or call them
LOG   [FederationService] provider 'glossary' RECOVERED — its tools are back in the catalog
```

---

## The plan changed under measurement

**F3 as written would have caused a deadlock, and the code stopped it.** The plan said "make
the healthcheck fail on sustained PARTIAL". Checking `depends_on` first showed
`glossary-service` itself declares `ai-gateway: condition: service_healthy`
(`infra/docker-compose.yml:1044`). Failing gateway health on a partial catalog gives:
**glossary down → gateway unhealthy → glossary can never restart → the outage becomes
permanent and self-inflicted.**

So `/health` stays a pure **liveness** probe and the docker healthcheck is unchanged. The
outage signal moved to a dedicated `/health/federation` (503 when degraded) that is loud for
alerting but never load-bearing for orchestration. Both facts are recorded in the code so the
next person doesn't "fix" the healthcheck back into a deadlock.

---

## What was actually wrong

The H10 availability signal **already existed and was correct** — `partial`, per-provider
`available`, `/health/catalog`, `_meta.unavailable_providers`, and a consumer whose note says
exactly the right thing. It had **one call site**: `find_tools`. F17 retired `find_tools`
from the LLM's view, and the guarantee did not travel to the replacement discovery pair.

That is the same shape as the skill-drift and hot-set gaps: **a new path does not inherit the
old path's guarantees.** Worth checking explicitly whenever a surface is replaced.

Second-order lesson: `not_found` was an **assertion of non-existence that the gateway could
not actually make** during an outage — a down provider's tools are absent from the catalog, so
"unknown name" and "vanished with its provider" are indistinguishable. Asserting the strong
claim made the system lie, and the model then reasoned impeccably to a wrong conclusion.
**Only assert what the current state can support.**

---

## Verification

- ai-gateway: **265 tests pass** (14 suites), `tsc --noEmit` clean. 9 new.
- chat-service: **1827 pass / 24 fail**; baseline without these changes is **1822 / 29** —
  same 24 pre-existing failures, **zero regressions**, +5 new passing tests.
- Twins kept in lockstep (`find-tools.ts` ↔ `tool_discovery.py`), each side tested, including
  the `provider_unavailable` vs `unavailable` name split (`unavailable` already means a CD4
  BROKEN tool — one name, one concept).
- The `unavailable_providers` `_meta` key is now **frozen** and pinned cross-language by
  `test_provider_availability_key_is_frozen`.

<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_11_CC_cross_cutting.md
byte_range: 64394-68671
sha256: 5fe5cefc650f13c1a2023f96f79e01b83ee0a74809e22c2f3f0d87fcb62bb738
generated_by: scripts/chunk_doc.py
-->

## CC — Cross-cutting

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| CC-1 | Chat GUI extension — region sidebar, player list, NPC panel, action bar, dual stream | 🟡 | V1 | PL-1 | [03 §9.1, feature comparison doc](03_MULTIVERSE_MODEL.md) |
| CC-2 | Multi-language support per reality (display + input) | 🟡 | V1 | IF-16 | Locale per reality; reuse translation-service |
| CC-3 | In-reality cross-language translation (user types Vietnamese, NPC replies English then auto-translates) | 📦 | V2 | CC-2 | Reuse translation-service |
| CC-4 | Reality browser / map view | 📦 | V2 | PO-2 | UI detail TBD |
| CC-5 | Observability — per-reality health dashboard, event lag metrics | 🟡 | INFRA | IF-3 | Standard ops |
| CC-6 | Accessibility — WCAG 2.2 AA compliance, ARIA live batched streaming, multi-stream semantic markup + per-stream mute, color-independent signaling, 44×44 tap targets, a11y mode toggle, axe-core CI gate + SR walkthrough | ✅ | V1 | — | [A11Y_POLICY.md](../../02_governance/A11Y_POLICY.md), CC-6-D1..D7 |
| CC-7 | Author dashboard (cross-reality view of their book's play) | 📦 | V3 | WA-6 | DF3 |
| CC-8 | Macros / variables in prompts (`{{pc}}`, `{{scene}}`, `{{entity.alice}}`) | 🟡 | V1 | PL-4 | SillyTavern pattern |
| CC-9 | User preferences / settings (per-device + per-account) | 🟡 | V1 | PO-1 | Reuse existing pattern |
| CC-10 | Tier 1 — unit tests with frozen mock LLM (prompt-hash keyed fixtures, <1s, per-PR) | ✅ | V1 | — | [05_qa §2.1](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#21-tier-1--unit-tests-with-frozen-mock-llm-g1-d1), G1-D1 |
| CC-11 | Tier 2 — nightly integration on cheap real LLM (~30 scenarios, 85% pass-rate threshold) | ✅ | V1 | CC-10 | [05_qa §2.2](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#22-tier-2--nightly-integration-on-real-llm-g1-d2), G1-D2 |
| CC-12 | Tier 3 — weekly LLM-as-judge scorecard (Sonnet/GPT-4.1 rubric) | ✅ | V1 | CC-10, CC-11 | [05_qa §2.3](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#23-tier-3--weekly-llm-as-judge-evaluation-g1-d3), G1-D3 |
| CC-13 | `admin-cli regen-fixtures` + scenario library at `docs/05_qa/LLM_TEST_SCENARIOS.md` | ✅ | V1 | admin-cli, CC-10 | [05_qa §2.4–2.5](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#24-fixture-maintenance-g1-d4), G1-D4/D5 |
| CC-14 | `loadtest-service` — synthetic user simulator with script library (casual/combat/fact/jailbreak) | 📦 | V1 | — | [05_qa §3.4](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#34-synthetic-user-simulator--loadtest-service-g2-d4), G2-D4 |
| CC-15 | Tiered load-test matrix — mocked high-conc V1 / real low-conc staging / full-stack pre-prod (V1 50/$50 → V3 1000/$1000) | ✅ | V1 | CC-14 | [05_qa §3.1–3.3](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#31-tier-1--mocked-llm-high-concurrency-g2-d1), G2-D1/D2/D3 |
| CC-16 | Load-test authorization + hard budget kill-switch (admin `loadtest.execute` token, 2h max, 80% alert, 100% stop) | ✅ | V1 | admin-cli, R13 | [05_qa §3.5](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#35-authorization--kill-switch-g2-d5), G2-D5 |
| CC-17 | User "that's not right" report button on NPC responses (4 categories + free text, creates review ticket) | ✅ | V1 | NPC-6 | [05_qa §4.2](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#42-layer-2--user-thats-not-right-button-g3-d2), G3-D2 |
| CC-18 | Per-reality drift metrics dashboard (DF9 surface) with alert thresholds | 📦 | V2 | NPC-6, DF9 | [05_qa §4.3](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#43-layer-3--drift-metrics-dashboard-g3-d3), G3-D3 |
| CC-19 | Auto-remediation on drift (memory regen, persona rotation, NPC suspension on severe drift) | 📦 | V2 | NPC-6, R8-L2 | [05_qa §4.4](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#44-layer-4--auto-remediation-g3-d4), G3-D4 |
| CC-20 | Production drift → G1 fixtures feedback loop (`admin-cli promote-drift-to-fixture`) | ✅ | V1 | NPC-6, CC-13 | [05_qa §4.5](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#45-layer-5--feedback-loop-to-test-fixtures-g3-d5), G3-D5 |
| CC-21 | Canon-drift SLOs per platform tier (free <5%, paid <2%, premium <0.5%) | 📦 | PLT | CC-18, 103_PLATFORM_MODE_PLAN | [05_qa §4.6](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#46-canon-drift-slos-per-platform-tier-g3-d6), G3-D6 |


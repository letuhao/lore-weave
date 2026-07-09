# Track C brief — User-Facing, Catalog & Validation

**One-liner:** the frontend the user actually touches, the curated workflow catalog, and the live-test
validation. Builds against A's contracts (with stubs) and B's backing tools.

- **Read first:** umbrella §4.2 (mode/permission), §5 (catalog), §6b Track C · `contracts.md` (you AUTHOR against
  C3, and read C1/C6) · ALL of `scenarios/` (esp. the flagship S06 + `_TEMPLATE.md` black-box rule).
- **Owns (services · files):**
  - frontend: permission-management UI (allowlist viewer/revoke/deny + MCP-server whitelist), mode selector +
    binding UI, workflow rack, onboarding-fork (W8) / world-container (W10) / reader (W11) surfaces
  - chat-service (Py — **only** `app/services/skill_registry.py` mode→capability resolve; additive to
    `resolve_skills_to_inject()`, disjoint from A/B)
  - data authoring: the W1–W12 Workflow objects (one file each), per C3
  - `docs/eval/discoverability/`: the scenario runs
- **Deliver (parallel; final integration waits on N1/N2):**
  - **WS-3** mode→capability binding (C6) + permission-management UI + per-user MCP-server whitelist.
  - **WS-5** author the W1–W12 catalog as C3 Workflow objects — **including the flagship S06 `vision-to-book`
    workflow** and the W8/W10/W11 journeys. One workflow per session-slice; author against C3 before A's runner
    exists.
  - **WS-7** baseline + re-test the S00–S12 scenarios and flagship S06 with `gemma-4-26b-a4b-qat`; save runs to
    `docs/eval/discoverability/`. **Black-box discipline applies** (`_TEMPLATE.md`) — judge the user outcome,
    never the tool calls.
- **Consumes:** C1 (enum), C3 (steps schema — author now), C6 (binding); B's backing tools for W2/W4/W10/W11.
- **Definition of done:** a user reaches every journey by talking, no jargon required; the flagship S06 ❌→✅ with
  gemma at N3 (the whole effort's go/no-go).
- **Note:** author workflows + build UI against the frozen contracts immediately; wire to the live runner at N2,
  to real backing tools as B ships them, and run the flagship at N3.

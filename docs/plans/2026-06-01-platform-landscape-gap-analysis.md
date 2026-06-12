# Platform Landscape & Gap Analysis — LoreWeave vs the AI-platform market

- Date: 2026-06-01
- Branch: `arch-unify-chat-rag`
- Purpose: Before designing ARCH-1/ARCH-2, map what a *real* AI platform is (not just the
  visible chat/TTS/STT/image/video — those are a thin top layer) across OpenAI, Anthropic
  (Claude), Google (Gemini), and LM Studio, then honestly inventory what LoreWeave already
  has and where the real gaps are.
- Thesis under test (PO): "Chat GUI / TTS / STT / image+video gen are a tiny slice of the
  ecosystem; the real system is the backend + tools + MCP + memory/context behind it. We've
  already built most of that — we're mainly missing the chat SDK + chat GUI component + wire
  logic." **Conclusion: largely correct.** See §4–§5.
- **SCOPE CORRECTION (PO 2026-06-01):** LoreWeave is **NOT a general-purpose agentic platform.**
  It serves exactly **three verticals — classic novel · visual novel · game** (the "book → world"
  vision). Tools / MCP / agentic workflows / RAG exist **only to serve those three** — we do NOT plug
  arbitrary capabilities in. The MVP goal is to **build a *standard* SDK that lets agents interact
  with the platform + ship a curated set of *standard* domain tools/MCP**, designed so power users
  can add their own MCP/tools/workflows **later (out of MVP scope)**. MVP = establish the extensible
  standard, nothing more. Read §4/§6 through this lens — the first draft over-generalized toward an
  open marketplace; corrected below.

---

## 1. The real ecosystem layers (what's actually under the hood)

The visible surface (chat window, voice, image/video) sits on ~12 layers. The differentiation
and the moat live in the lower layers:

| # | Layer | What it is |
|---|---|---|
| L1 | **Provider / model access** | Talk to models; multi-provider routing, fallback, BYOK, self-host |
| L2 | **Multimodal I/O** | chat, completion, embeddings, TTS, STT, image-gen, video-gen |
| L3 | **Tool / function calling** | Model decides to call typed functions; execute + feed back |
| L4 | **MCP (Model Context Protocol)** | The *open interop standard* for plugging tools/data/prompts into any model |
| L5 | **Memory** | Long-term, cross-session recall (facts, preferences, episodic) |
| L6 | **Context / RAG** | Retrieval + context assembly (embeddings, knowledge graph, docs) |
| L7 | **Agent orchestration** | Bounded agentic loops; multi-agent; managed/background agents; workflows |
| L8 | **Realtime / voice** | Live voice sessions that can call tools mid-conversation |
| L9 | **Registries / marketplaces** | Agent/tool/connector registries; model registry; app stores |
| L10 | **SDKs** | Client libraries (multi-language) for app + agent builders |
| L11 | **GUI** | Chat interface, reusable/embeddable |
| L12 | **Usage / billing / governance** | Metering, quotas, cost control, sandboxes, tenancy |

---

## 2. Market state (June 2026) — the four references

### Common to ALL four (the 2026 baseline)
- **Function/tool calling** is table stakes.
- **MCP is now the universal standard.** Anthropic created it; OpenAI joined the MCP steering
  committee and supports remote MCP servers in the Responses API; Gemini SDKs have built-in MCP
  with automatic tool-calling + an MCP-server registry; **even LM Studio (local) added MCP (0.3.17)
  + OAuth for MCP (0.4.10)**. MCP is how the whole industry now plugs tools/data into models.
- **Cross-session memory** is a managed product (OpenAI memory; Claude Managed-Agents memory beta;
  Gemini **Memory Bank** + Sessions).
- **Agent orchestration** moved from "an API" to "a platform" (OpenAI Responses API + Agents SDK;
  Claude **Agent SDK** + Managed Agents + multi-agent + dynamic workflows; Gemini **Enterprise Agent
  Platform** — Vertex AI was *renamed* around agents in May 2026).

### Per-platform highlights
| Platform | Notable depth |
|---|---|
| **OpenAI** | Responses API (tools in-chain for o-series), built-in tools (web/file search, code interpreter, computer use), remote MCP + connectors (Stripe/Shopify/Twilio), Realtime voice with tools, memory. Assistants API sunsets 2026-08-26 → Responses API. |
| **Anthropic (Claude)** | **Agent SDK** (was Claude Code SDK), Managed Agents (memory beta `managed-agents-2026-04-01`, multi-agent, self-hosted sandboxes on AWS, private MCP), Skills + Plugins (bundle skills/agents/hooks/MCP), dynamic workflows (tens–hundreds of agents). MCP origin. |
| **Google (Gemini)** | **Gemini Enterprise Agent Platform** (Vertex AI retired/renamed May 2026): Agent Garden (templates), **MCP Server registry**, **Memory Bank** (long-term), Sessions, **Agent Registry** (every agent/tool/connector). Built-in MCP in SDKs. |
| **LM Studio** (local) | OpenAI- **and** Anthropic-compatible server + Python/TS SDKs; **MCP client (local+remote, OAuth)**; offline doc chat with **built-in RAG**; model management (load/unload/config), embeddings; `reasoning_effort` etc. The "local" tier now has tools+MCP+RAG. |

Sources in §7.

---

## 3. What LoreWeave actually has (verified in-repo, 2026-06-01)

Mapped to the same 12 layers. **Status: ✅ strong / 🟡 partial / ❌ missing.**

| Layer | LoreWeave | Status |
|---|---|---|
| **L1 Provider/model** | `provider-registry-service` = unified gateway: adapters for openai / anthropic / ollama / lm_studio / gemini, **BYOK** credentials (encrypted), per-model config, **self-host friendly**, custom endpoints (local OpenAI-compat). | ✅✅ (arguably > commercial: they serve only their own models; we abstract *any* provider) |
| **L2 Multimodal I/O** | One gateway, many ops: `chat`, `completion`, `embedding`, `tts`, `stt`, `image_gen`, `video_gen`, plus domain ops `entity/relation/event/fact_extraction`, `translation`, `summarize_level`. Media impl in `video-gen-service` + sibling `local-image-generator-service` (SD/SDXL/Flux/Wan/LTX…) + `local-tts-service` (kokoro/piper) + STT. | ✅✅ |
| **L3 Tool/function calling** | `knowledge-service/app/tools/` (`definitions.py` = OpenAI function schemas, `executor.py`, `routers/internal_tools.py`); chat-service `_stream_with_tools` (K21-B) **bounded** agentic loop (MAX_TOOL_ITERATIONS=5, final pass tool-free). | ✅ (works) but **closed toolset** |
| **L4 MCP** | — none — | ❌ **MISSING** (the strategic gap) |
| **L5 Memory** | `knowledge-service`: Postgres SSOT + Neo4j-derived knowledge graph; entities / facts / events / **timeline**; `store_fact` / `invalidate_fact` / `memory_search` / entity-lookup tools. **Domain memory**, not generic chat memory. | ✅✅ (differentiated vertical memory) |
| **L6 Context / RAG** | `knowledge-service/app/context/` (modes: full / no_project; formatters), embedding client, query runner; glossary-service (authored SSOT) + extraction pipeline (GraphRAG/HippoRAG-validated). | ✅✅ |
| **L7 Agent orchestration** | Single bounded tool-loop (chat-service). No multi-agent / managed / background / sub-agent / workflow engine. | 🟡 single-agent only |
| **L8 Realtime / voice** | `chat-service` voice (`voice_stream_service`, VAD, TTS/STT, `VoiceChatOverlay`). Not a realtime-tools agent. | 🟡 |
| **L9 Registries** | **Model registry** (providers + user-models + pricing). No agent/tool/connector marketplace. | 🟡 (model registry ✅; agent/tool registry ❌) |
| **L10 SDKs** | `sdks/python`, `sdks/go/llmgw` + `observability`, `sdks/rust/loreweave_llm` — but these are **LLM-gateway** SDKs (provider abstraction), **not a chat/agent SDK**. | ✅ gateway SDK / ❌ chat SDK |
| **L11 GUI** | `features/chat/` — full chat: ChatView, split session/stream contexts, streaming, **thinking blocks, tool-call indicators, branching, voice overlay, context-attach (sendToChat) + paste-to-editor**. Mature — but **not packaged as a reusable/embeddable component**, and the editor AI panel is unwired ("Coming soon"). | 🟡 exists, not reusable/wired |
| **L12 Usage/billing/governance** | `usage-billing-service` + gateway cost-estimate / per-model pricing / quota (402) / metering / max-token caps. Explicit BYOK cost control. | ✅✅ (commercial platforms hide this; ours is explicit) |

---

## 4. Gap analysis — what's actually missing

The PO thesis holds: **the deep backend is largely built.** The genuine gaps, ranked by
strategic leverage:

**(All scoped to the three verticals — classic novel / visual novel / game. We are NOT building an
open tool marketplace; we are building the *standard* that our own agents speak and that power users
can extend later.)**

1. **An agent ↔ platform SDK + a *standard* domain toolset (L3/L4/L10) — the #1 MVP gap.** Today the
   chat agent's tools are a closed, hand-wired knowledge-service set. What's missing is a **defined
   standard**: (a) one SDK surface through which *any* agent (chat, editor, assisted-creation, the
   game/world-gen pipeline) interacts with the platform's domain capabilities, and (b) a curated set
   of **standard domain tools** — `knowledge_search`, `glossary_lookup`, `translate`, `generate_image`,
   `generate_audio`, `world_gen`, chapter/scene read-write, etc. — exposed through that one surface.
   - **Use MCP as the *wire format / contract* for this standard** (it's the industry standard the
     models already speak, and it future-proofs the seam) — but scoped to **our** domain tools, not
     an open marketplace. MVP ships the standard + the core novel/VN/game tools.
   - **Extensibility is a design requirement, not a feature to ship now:** the registry/contract must
     allow power users to register their own MCP servers / tools / workflows **later** — MVP just makes
     that *possible*, it doesn't expose it.
   - (Future / out-of-MVP) exposing LoreWeave itself as an MCP *server* for external clients is a
     distribution play — design the seam to allow it, ship it later.
2. **Chat SDK + reusable/embeddable chat GUI component + wire logic (L10/L11).** The chat GUI is
   mature but page-bound; there's no chat SDK and the editor AI panel is unwired. **This is exactly
   ARCH-1.** A packaged `<Chat>` component (providers + view + context-attach + editor write-back)
   unblocks editor-chat, assisted-creation (WA-4), and future surfaces — across all three verticals.
3. **Agent orchestration depth (L7).** Single-agent only. Multi-agent / background / sub-agent
   patterns are post-MVP, but the agent + tool-standard seam should not preclude them.
4. **(Lesser, post-MVP) realtime-tools (L8), power-user tool/workflow registry surface, external
   MCP-server distribution (L9).** Design seams now; ship later.

---

## 5. Where LoreWeave is already AHEAD / differentiated

Not just "catching up" — several layers are genuinely strong or differentiated:

- **BYOK multi-provider unified gateway (L1/L2/L12).** OpenAI/Claude/Gemini each serve only their
  own models; LoreWeave abstracts *any* provider (cloud + local) behind one gateway with explicit
  pricing/metering/quota and a multi-language SDK. For a self-host / BYOK audience this is a real edge.
- **Domain memory + knowledge graph (L5/L6).** Generic platforms offer flat "memory"; LoreWeave has
  a *structured story world* (entities/facts/events/timeline + glossary SSOT), validated against
  GraphRAG/HippoRAG. This is the vertical moat.
- **A real product on top (the vertical).** Translation pipeline, glossary/wiki, reader+TTS,
  multilingual novel workflows. The references are horizontal infra; LoreWeave is infra **+** a
  domain product.
- **Explicit cost governance.** BYOK metering/quotas are first-class, not hidden.

**Reframe:** LoreWeave is **a vertical creative-content platform (classic novel · visual novel ·
game / the "book → world" pipeline)** that already owns the hard layers (provider gateway,
knowledge/memory, billing) and a domain product. It is missing the *packaging + standard* layers:
a chat/agent **SDK**, a reusable chat **component**, and a **standard domain tool/MCP contract** —
all scoped to the three verticals and **extensible later**.

---

## 6. Implications for ARCH-1 / ARCH-2 (to design next) — vertical-scoped

- **ARCH-1 = the chat/agent SDK + reusable `<Chat>` component (gap #2).** Package providers + view +
  context-attach + editor write-back so editor-chat, assisted-creation (WA-4), and the VN/game
  surfaces all consume one component. First consumer: the editor AI panel.
- **ARCH-2 = one agent + a *standard* domain tool contract (gaps #1+#3), scoped to novel/VN/game.**
  Route every AI surface through the single bounded chat-service agent (no per-surface RAG), and
  define **one tool-contract surface** for the curated domain toolset (knowledge/glossary/translate/
  image/audio/world-gen/scene-rw). **Use the MCP shape as that contract** so it's future-proof and the
  models already speak it — but ship only **our** domain tools. **Design the registry to allow
  power-user MCP/tools/workflows later; do not expose that in MVP.**
- **MVP deliverable = the *standard* (the extensible seam) + the core domain tools, not a marketplace.**
  External MCP-server distribution + power-user extension + multi-agent orchestration are explicitly
  **post-MVP**; the design must merely not preclude them.
- **Folded-in:** WA-4 (assisted creation) falls out of ARCH-1 (chat with editor-write tools). The TR-4
  output-aware block batching is **translation-specific** and tracked separately (not part of this
  agent/RAG standard).

---

## 7b. The industry has CONVERGED on a 3-layer standard stack — adopt it, don't invent

Researched (2026-06-01) whether a good-enough open standard exists to adopt instead of designing our
own. **Yes — and the "protocol wars" are over.** The majors (Anthropic, OpenAI, Google, Microsoft,
AWS, …) now govern agent standards under the **Linux Foundation "Agentic AI Foundation" (AAIF)**, and
the production-default architecture is a **complementary 3-layer stack** — each layer maps 1:1 onto a
layer we already identified:

| Our layer | Adopt this open standard | What it is | Status / governance |
|---|---|---|---|
| **Tool contract** (agent ↔ platform tools) — gap #1 / ARCH-2 | **MCP** (Model Context Protocol) | agent↔tool, client-server; the vertical tool-integration standard | Anthropic → **Linux Foundation AAIF**; ~18,000 servers, tens of M SDK downloads/mo; OpenAI/Gemini/LM Studio all speak it |
| **Chat / agent ↔ UI** (chat component + wire) — gap #2 / ARCH-1 | **AG-UI** (Agent-User Interaction Protocol) | bi-directional agent↔frontend over HTTP/SSE: streaming text, **frontend tool-calls**, **shared state-delta**, human-in-loop | CopilotKit-governed; adopted by Google/MS/AWS/Oracle + LangChain/Mastra/PydanticAI/Agno; AWS Bedrock AgentCore added it Mar 2026 |
| **Agent ↔ agent** (multi-agent — the **game-design** future) | **A2A** (Agent2Agent) | peer-to-peer agent discovery + coordination across frameworks/vendors | Google → **Linux Foundation**; 150+ orgs, in Google/MS/AWS |

(REST-native **ACP** and **AGNTCY/OASF** agent-cards exist too, but MCP+A2A+AG-UI is the production
default; we don't need ACP/AGNTCY for our scope.)

**Implementation SDKs (don't hand-roll streaming/wire):**
- Frontend chat streaming → **Vercel AI SDK** (multi-provider, React, ~20 kB) and/or **CopilotKit**
  (the AG-UI reference frontend). Our `ChatView` becomes an AG-UI client instead of a bespoke SSE parser.
- MCP server/client → official **MCP SDKs** (Python/TS) — wrap knowledge-service tools as an MCP server;
  chat-service agent becomes an MCP client.
- A2A → official A2A SDK — **design the seam now (agent cards), ship later**.

### What adopting the stack means concretely (the accepted refactor)
- **ARCH-2 → MCP.** Re-expose `knowledge-service/app/tools/` (definitions + executor) as an **internal
  MCP server**; the chat-service agent loop becomes an **MCP client**. Our domain tools
  (knowledge/glossary/translate/image/audio/world-gen/scene-rw) register as MCP tools. The gateway
  already forwards tool-calls — this standardizes the contract + makes the power-user-adds-MCP-later
  seam free. **Scope to our 3 verticals' tools; no open marketplace in MVP.**
- **ARCH-1 → AG-UI.** chat-service streams **AG-UI events** (text / tool-call / state-delta) over SSE;
  the reusable `<Chat>` component is an AG-UI client (via Vercel AI SDK / CopilotKit). This replaces
  "design our own chat SDK/wire" — we conform to the standard the models + tools already speak.
  state-delta is exactly what editor write-back / assisted-creation (WA-4) needs.
- **A2A (future, game multi-agent).** When game design needs many coordinating agents, agents expose
  **A2A agent cards** and coordinate peer-to-peer. Design ARCH so the single agent is A2A-addressable
  later; do NOT build multi-agent in MVP.

### Recommendation
**Adopt MCP + AG-UI now (they ARE ARCH-2 + ARCH-1), design the A2A seam, ship A2A later.** This trades
a one-time standardization refactor (accepted by PO for future scale, esp. game agentic AI) for: zero
bespoke protocol design, instant interop with the whole ecosystem, and a clean extension path for
power-user tools/agents. The refactor is conforming-to-a-standard, not inventing one.

---

## 7. Sources

- OpenAI: [Responses API tools/features](https://openai.com/index/new-tools-and-features-in-the-responses-api/), [MCP & Connectors](https://developers.openai.com/api/docs/guides/tools-connectors-mcp), [Realtime + MCP](https://developers.openai.com/api/docs/guides/realtime-mcp), [VentureBeat: Responses API + MCP](https://venturebeat.com/programming-development/openai-updates-its-new-responses-api-rapidly-with-mcp-support-gpt-4o-native-image-gen-and-more-enterprise-features)
- Anthropic: [MCP announcement](https://www.anthropic.com/news/model-context-protocol), [Claude Agent SDK (Python)](https://github.com/anthropics/claude-agent-sdk-python), [Managed Agents overview](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/managed-agents-overview.md), [Anthropic release notes May 2026](https://releasebot.io/updates/anthropic)
- Google: [Gemini Enterprise Agent Platform (Vertex renamed)](https://gcpstudyhub.com/blog/vertex-ai-replaced-by-gemini-enterprise-agent-platform), [I/O '26 for agent devs](https://cloud.google.com/blog/topics/developers-practitioners/io26-news-for-agent-developers-on-google-cloud), [Gemini function calling + MCP](https://ai.google.dev/gemini-api/docs/function-calling)
- LM Studio: [MCP in LM Studio (v0.3.17)](https://lmstudio.ai/blog/lmstudio-v0.3.17), [Use MCP servers](https://lmstudio.ai/docs/app/mcp), [MCP via API](https://lmstudio.ai/docs/developer/core/mcp), [2026 update: MCP OAuth + Qwen 3.6](https://www.toolmintx.in/blog/lm-studio-april-2026-update-mcp-oauth-qwen-3-6-locally-ai)
- Standards stack: [Agent interoperability protocols 2026: MCP/A2A/ACP convergence (Zylos)](https://zylos.ai/research/2026-03-26-agent-interoperability-protocols-mcp-a2a-acp-convergence), [AI agent protocol ecosystem map 2026](https://www.digitalapplied.com/blog/ai-agent-protocol-ecosystem-map-2026-mcp-a2a-acp-ucp), [Survey of agent interop protocols (arXiv 2505.02279)](https://arxiv.org/html/2505.02279v1)
- AG-UI: [AG-UI protocol (CopilotKit)](https://www.copilotkit.ai/ag-ui), [AG-UI docs](https://docs.ag-ui.com/introduction), [AG-UI GitHub](https://github.com/ag-ui-protocol/ag-ui), [CopilotKit $27M Series A on AG-UI](https://ai2.work/blog/copilotkit-raises-27m-to-make-ag-ui-the-standard-for-in-app-ai-agents)
- A2A: [Linux Foundation launches A2A](https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents), [A2A 150+ orgs, 1yr](https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year), [a2a-protocol.org](https://a2a-protocol.org/latest/)
- SDKs: [Vercel AI SDK](https://ai-sdk.dev/docs/introduction), [Anthropic vs OpenAI vs Vercel SDK 2026](https://docs.bswen.com/blog/2026-04-29-agent-sdk-comparison-anthropic-openai-vercel/)

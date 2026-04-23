# SillyTavern — Feature Comparison & LoreWeave Design Opportunities

> **Purpose**: Prior-art survey of [SillyTavern](https://github.com/SillyTavern/SillyTavern) mapped against LoreWeave's current planning. Identifies parallel design work that does not overlap with the active knowledge-service implementation.
> **Source ref**: SillyTavern release branch (Node.js, AGPL-3.0, ~26k stars).
> **Last Updated**: 2026-04-23
> **Owner**: Tech Lead + PM
> **Status**: Research — input for follow-up design docs

---

## 1. SillyTavern — What It Is

`LLM Frontend for Power Users` — a locally-installed SPA + Node.js server for character-driven roleplay chat with LLMs. AGPL-3.0, ~26k stars, 3+ years of development, originally forked from TavernAI in Feb 2023. Ships as a single monolithic app (Node `server.js` + `public/` static SPA). Install = `Start.bat` / `start.sh` / Docker / Colab / Replit.

### Tech stack

- **Backend:** Node 20+, Express-style routing in `src/endpoints/`, webpack bundled, per-user file-based data store under `data/` (one folder per user with chats, characters, presets, backups).
- **Frontend:** vanilla JS SPA in `public/` (no React). ~100+ scripts in `public/scripts/` each owning a subsystem. Handlebars templates, jQuery for DOM.
- **No DB.** File-per-entity (JSON/PNG). Per-user folder model. This is the biggest architectural difference from LoreWeave.
- **Electron variant** available via `src/electron/`.

---

## 2. Subsystems (mapped from actual source tree)

| Subsystem | Key files | What it does |
|---|---|---|
| **Character Cards** | `src/character-card-parser.js`, `src/validator/TavernCardValidator.js`, `src/png/encode.js`, `public/scripts/char-data.js` | PNG-embedded character metadata (Tavern Card v2 spec). Greeting, persona, description, example dialogues, alternate greetings, scenario. Import/export by drag-drop a PNG. |
| **CHARX / BYAF** | `src/charx.js`, `src/byaf.js`, `src/types/byaf.d.ts` | Two extra portable card formats: CHARX (zip) and BYAF ("Backup Your AI Folder"). Bundle card + lorebook + chat history. |
| **World Info / Lorebooks** | `src/endpoints/worldinfo.js`, `public/scripts/world-info.js` | Keyword-triggered context injection. Entries have keys, content, depth, probability, group weight. RAG-lite: cheap retrieval without embeddings. |
| **Personas** | `public/scripts/personas.js` | User-side personas (name, description, avatar). Separate from character. |
| **Group chats** | `src/endpoints/groups.js`, `public/scripts/group-chats.js` | Multi-character conversations with turn order and per-character muting. |
| **Presets / Prompt Manager** | `src/endpoints/presets.js`, `public/scripts/preset-manager.js`, `public/scripts/PromptManager.js`, `public/scripts/sysprompt.js`, `public/scripts/instruct-mode.js`, `public/scripts/chat-templates.js` | Reusable bundles of (model + sampler params + system prompt + prompt order + instruct format). Instruct mode = model-family-specific chat templating (Llama/Mistral/ChatML/Alpaca). |
| **Author's Note** | `public/scripts/authors-note.js` | Persistent text injected at depth-N from the bottom of context on every turn. Cheap-but-powerful consistency trick. |
| **Macros / Variables** | `public/scripts/macros.js`, `public/scripts/variables.js` | `{{user}}`, `{{char}}`, custom `{{setvar::x}}`, date/random. Live template substitution across prompts and responses. |
| **Slash commands** | `public/scripts/slash-commands.js`, `public/scripts/action-loader-slashcommands.js` | `/sys`, `/gen`, `/ask`, `/roll`, user-extensible. Full mini-scripting layer. |
| **Quick replies** | `src/endpoints/quick-replies.js` | One-click pre-filled inputs tied to slash-command scripts. |
| **Swipes** | `public/scripts/swipe-picker.js` | Regenerate N response variants, swipe between them. Keeps all variants in the chat record. |
| **Bookmarks / Branches** | `public/scripts/bookmarks.js` | Fork the chat at any message. |
| **Tool calling** | `public/scripts/tool-calling.js` | Cross-provider function calling abstraction. |
| **Reasoning** | `public/scripts/reasoning.js` | CoT / thinking-trace handling per provider (Claude extended thinking, OpenAI o-series, DeepSeek R1 style). |
| **Multi-backend LLM** | `src/endpoints/backends/chat-completions.js`, `text-completions.js`, `kobold.js` + per-provider files under `src/endpoints/` (`anthropic.js`, `openai.js`, `openrouter.js`, `google.js`, `azure.js`, `novelai.js`, `horde.js`, `minimax.js`, `volcengine.js`) | Unified chat & text completion plumbing, plus provider-specific routes for quirks. |
| **Vectors / RAG** | `src/vectors/` (8 providers: `openai-`, `cohere-`, `google-`, `ollama-`, `llamacpp-`, `nomicai-`, `vllm-`, `extras-vectors.js`), `src/endpoints/vectors.js`, `src/vectors/embedding.js` | Pluggable embedding backend behind one interface. Used for Data Bank ("chat with your docs") and character memory. |
| **Tokenizers** | `src/tokenizers/` (llama, llama3, claude, mistral, gemma, jamba, nerdstash, yi), `public/scripts/tokenizers.js` | Accurate per-family token counting for context budgeting and cost estimation. |
| **SSE streaming** | `public/scripts/sse-stream.js`, `public/scripts/custom-request.js` | Hand-rolled SSE normalizer across all providers. |
| **Secrets (BYOK)** | `src/endpoints/secrets.js`, `public/scripts/secrets.js` | Per-user encrypted API key storage. |
| **Classify** | `src/endpoints/classify.js` | Sentiment/mood classification of messages → drives expression sprite swap. |
| **Speech** | `src/endpoints/speech.js` | TTS (output) + STT (input). |
| **Image gen / caption** | `src/endpoints/stable-diffusion.js`, `caption.js`, `images.js`, `image-metadata.js` | SD/ComfyUI/A1111 integration; vision-model captioning for image inputs. |
| **Translate** | `src/endpoints/translate.js` | Auto-translate in both directions. |
| **Extensions** | `plugins.js`, `src/plugin-loader.js`, `src/endpoints/extensions.js`, `public/scripts/extensions.js` | Third-party extension framework. Extensions can register slash commands, UI panels, event handlers. |
| **Scrapers** | `public/scripts/scrapers.js` | Import characters from URLs/repos. |
| **Stats** | `src/endpoints/stats.js`, `public/scripts/stats.js` | Per-character token/cost/time stats. |
| **Backups / Recovery** | `src/endpoints/backups.js`, `recover.js`, `public/scripts/chat-backups.js`, `backups/` | Every chat is backed up automatically. |
| **Tags** | `public/scripts/tags.js` | Character folders/categories. |
| **Themes** | `src/endpoints/themes.js`, `public/scripts/power-user.js` | User-customizable UI (colors, font, chat display mode incl. Visual Novel). |
| **Moving UI** | `src/endpoints/moving-ui.js` | User-draggable repositionable panels. |

---

## 3. Architecturally Notable Choices

- **File-per-entity over DB.** Trivially portable, works offline, user-as-owner of all data. Downside: no multi-device sync, no concurrent users on one install — the opposite of LoreWeave's cloud/multi-device model.
- **Provider adapters are thin `fetch` shims, not SDKs.** Source of truth for the Vercel AI SDK protocol-style approach that [98_CHAT_SERVICE_DESIGN.md §2.1](../98_CHAT_SERVICE_DESIGN.md) calls out with LiteLLM.
- **The prompt is a first-class assembled document.** `PromptManager.js` lets the user reorder/toggle every prompt block (system, persona, world-info, author's note, history, example dialogs, jailbreak, etc.). LoreWeave's platform-mode plan ([103_PLATFORM_MODE_PLAN.md §8](../103_PLATFORM_MODE_PLAN.md)) has "per-kind prompts" but no block-composition UX yet.
- **World Info is lightweight RAG.** No embeddings — just keyword triggers with depth/probability/priority. A useful lower-cost tier alongside the Postgres-SSOT + Neo4j knowledge layer LoreWeave is building.

---

## 4. Mapping to LoreWeave

### 4.1 Active conflict zone — DO NOT overlap

Per recent commits (`K19a`–`K19e`), another agent is deep in:
- `services/knowledge-service/` (extraction, edit, merge, timeline)
- `contracts/api/knowledge/`
- The glossary ↔ knowledge anchor contract (`glossary_entity_id` FK)

Any design that touches those surfaces must wait or be pure external-schema work.

### 4.2 Safe-to-design-in-parallel areas (ranked by impact × non-overlap)

| # | Candidate parallel design job | Overlap with knowledge work? | SillyTavern patterns it imports |
|---|---|---|---|
| 1 | **Chat-service design finalization** — [98_CHAT_SERVICE_DESIGN.md](../98_CHAT_SERVICE_DESIGN.md) is still `Draft — Pending Approval`. Incorporate: swipes (regen variants), bookmarks (branch), author's note (depth-N injection), `/slash` mini-commands, macros `{{book}}/{{chapter}}/{{entity}}`, tool calling, reasoning pass-through, session stats (tokens/cost). | None — chat-service hasn't started; knowledge-service is a separate service. | PromptManager, swipes, bookmarks, authors-note, macros, slash-commands, tool-calling, reasoning, stats |
| 2 | **Prompt Preset / Instruct-Mode module (new cross-cutting)** — today prompts are scattered across translation-service, chat-service, and `system_settings`. Design one `prompt-preset` surface: preset = (model_ref + sampler params + prompt block order + instruct format) reusable in translation + chat + continuation. | None — pure composition over existing provider-registry. | Presets, PromptManager, sysprompt, instruct-mode, chat-templates |
| 3 | **Tokenizer library/service** — platform-mode tiers enforce `ai_tokens_monthly` but LoreWeave has no local token counter; today it trusts provider `usage` post-hoc. Design a small tokenizer library (or service) that supports Llama/Claude/GPT/Mistral families locally for pre-flight budget checks. | None. | `src/tokenizers/`, `public/scripts/tokenizers.js` |
| 4 | **Portable bundle format (Deferred #100)** — `100_FUTURE_FEATURE_STRUCTURED_IMPORT_EXPORT_MEDIA.md` is a marker for zip import/export. SillyTavern already ships three mature portable formats (Tavern Card v2 PNG, CHARX, BYAF). Worth lifting their schemas + validator as prior art. | None — writes a design doc only. | character-card-parser, TavernCardValidator, charx, byaf |
| 5 | **Author-voice / continuation character bibles (Phase 4)** — Phase 4 canon-safety needs "who speaks in what voice, what do they believe, what don't they know yet." SillyTavern's Character Card v2 is literally that schema. Design LoreWeave's Author Voice / POV entity derived from Character Card v2 + LoreWeave's glossary entities. | **Edge overlap** — if the author-voice object links to knowledge-service entities. Design the *external* schema only, leave the FK direction loose until knowledge agent is done. | Character Cards v2, personas, group-chat turn model |
| 6 | **Vector adapter abstraction for knowledge-service** — knowledge-service plans Neo4j + embeddings. SillyTavern's 8-provider `src/vectors/` shows a clean interface. Document the adapter contract so knowledge-service can drop in providers without churn. | **High overlap** — the other agent owns this. **Skip for now** or offer as a PR-draft-later comment. | `src/vectors/` |
| 7 | **Slash-command / quick-reply UX for editor + chat** — "/translate-chunk", "/expand-scene", "/check-canon", "/suggest-entity" as user-extensible commands across the chapter editor and chat. | None — pure UX layer over existing APIs. | slash-commands.js, quick-replies |
| 8 | **Extensions / plugin framework (post-V1 spec)** — out of scope now but a SillyTavern-style spec would unlock community contribution later. | None — design doc only. | plugin-loader.js, extensions.js |
| 9 | **Output classification + auto-labeling** — SillyTavern's `classify.js` drives sprite swap from message mood. LoreWeave analogue: auto-classify translated chunks (tone, POV, dialogue-vs-narration) for downstream QA. | None. | classify.js |

---

## 5. Recommended Next Moves

Two highest-ROI, zero-collision design jobs to pick first:

1. **Finalize `98_CHAT_SERVICE_DESIGN.md` to Approved** — it's in Draft, chat-service hasn't started, and the SillyTavern patterns (swipes, bookmarks, author's note, macros, slash commands, tool calling, reasoning) each slot cleanly into the existing architecture. This unblocks Phase 2/3 chat work.
2. **New design doc: `10X_PROMPT_PRESET_ARCHITECTURE.md`** — a cross-cutting prompt preset/instruct-mode surface reused by translation, chat, and (future) continuation. This is the single biggest SillyTavern lesson: treat the prompt as a composable, user-editable, versionable document.

---

## 6. Sources

- [SillyTavern GitHub](https://github.com/SillyTavern/SillyTavern)
- [SillyTavern `src/` tree (release)](https://github.com/SillyTavern/SillyTavern/tree/release/src)
- [SillyTavern `public/scripts/` tree (release)](https://github.com/SillyTavern/SillyTavern/tree/release/public/scripts)
- [98_CHAT_SERVICE_DESIGN.md](../98_CHAT_SERVICE_DESIGN.md)
- [103_PLATFORM_MODE_PLAN.md](../103_PLATFORM_MODE_PLAN.md)
- [100_FUTURE_FEATURE_STRUCTURED_IMPORT_EXPORT_MEDIA.md](../100_FUTURE_FEATURE_STRUCTURED_IMPORT_EXPORT_MEDIA.md)

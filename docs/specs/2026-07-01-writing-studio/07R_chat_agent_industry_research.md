# 07R — Chat-Agent Industry Research & Standard (reference)

> **Status:** research reference (not a build spec). Feeds a future "Studio Agent Standard".
> **Date:** 2026-07-02 · **Author:** research fan-out (6 web-research agents + 1 codebase inventory), synthesized.
> **Why:** Writing Studio ≈ "Cursor for novels". The chat-agent is the load-bearing part. Before scaling
> panels we capture how the industry leaders architect the chat-agent, map it to what LoreWeave already
> has (much, but fragmented), and derive the standard we should build to.

Scope axes (the user's framing): **context management** (classification + budget + indicator + auto/manual
compaction) · **tool & skill management** · **sub-agent deployment** · **background jobs** · **loading
context from other data providers** · **web search** · plus streaming/UX, plan/act, HITL gates.

---

## Part 1 — Per-tool findings (concrete mechanisms + sources)

### Claude Code (Anthropic CLI)
- **Context budget/indicator:** live %-used; auto-compact threshold `effectiveWindow − 13K` (~167K on 200K), by late-2025 triggers earlier (~64–75%). ([hyperdev](https://hyperdev.matsuoka.com/p/how-claude-code-got-better-by-protecting), [ClaudeLog](https://claudelog.com/faqs/what-is-claude-code-auto-compact/))
- **3-tier compaction:** (a) **microcompact** — *no model call*, drops stale tool results; (b) **full compact** — model summarizes into `<summary>` (keeps state/next-steps/decisions, drops pre-summary blocks); (c) **session-memory compact** — uses pre-extracted notes. API: `compact_20260112` beta, `trigger` default 150K, `pause_after_compaction` keeps last N verbatim. ([oldeucryptoboi](https://oldeucryptoboi.com/blog/context-compaction-deep-dive/), [platform.claude.com/compaction](https://platform.claude.com/docs/en/build-with-claude/compaction))
- **Manual:** `/compact [hint]`, `/clear`. **Memory:** `CLAUDE.md` (project/user/enterprise) auto-injected; `@import`; `#` writes a quick note.
- **Tools/skills:** built-ins + MCP; **MCP Tool Search (Jan 2026)** loads defs on-demand (~85% token cut). Permission `allow/ask/deny`; Shift+Tab cycles default→acceptEdits→plan. **Skills** = `SKILL.md` (`allowed-tools`, `context: fork`); commands+skills merged as `/slash`. **Hooks** = deterministic pre/post shell.
- **Sub-agents:** Task tool = separate Claude, own context/prompt/tools; **only final message returns**; built-ins Explore(Haiku)/Plan/General; concurrent; **flat hierarchy**.
- **Background:** detached bash + `run_in_background` agents; notify on completion.
- **External context:** MCP (stdio/SSE/HTTP) tools+resources; `@`-mentions; **agentic grep/read, NO standing repo index**. **Web:** native `web_search_20250305` with built-in citations + `allowed/blocked_domains`; `WebFetch`.
- **UX:** Plan mode, **TodoWrite** live checklist, output styles, native diff/apply, git-based undo.

### Cursor (AI IDE)
- **Context tiers:** always-included (system, `alwaysApply` rules, current file) · conditional (selection, @-targets, glob rules, open tabs) · on-demand `@Codebase`/`@Docs`/`@Web`/`@Git`. **Memories:** a sidecar model *suggests* memories; user approves; saved as auto-rules. **Rules:** `.cursor/rules/*.mdc` (4 modes; keep <200 words — taxed every request). ([datalakehousehub](https://datalakehousehub.com/blog/2026-03-context-management-cursor/), [cursor.com/docs/rules](https://cursor.com/docs/rules))
- **Codebase RAG (the differentiator):** on open, chunk → embed (custom model) → vector DB; **source discarded, paths encrypted**; usable ~80% indexed, re-sync 5 min; semantic + Instant Grep = +12.5% vs grep. ([cursor.com/docs/codebase-indexing](https://cursor.com/docs/context/codebase-indexing))
- **Tools:** MCP, approval-by-default, per-server allowlists, auto-review classifier. Commands + Skills (SKILL.md parity).
- **Sub-agents:** Explore subagent; **Cursor 2.0** multi-agent parallel; **2.5 subagent *trees*** (child spawns child).
- **Background:** **Cloud Agents** in isolated Ubuntu VMs, parallel; **Feb 2026 "Computer Use"** = desktop+browser to visually verify. ([cursor.com/docs/cloud-agent](https://cursor.com/docs/cloud-agent))
- **Web:** `@Web` + agent web-search, cited. **UX:** Plan Mode → editable `plan.md`; **checkpoints** (auto pre-change snapshot, one-click restore; manual edits NOT tracked); Instant-Apply diff.

### Google Antigravity (agent-first IDE, launched 2025-11-20)
- **Paradigm:** **Manager Surface** (mission-control) separate from Editor view — spawn/observe/orchestrate many async agents; human reviews **Artifacts** + leaves **Google-Docs-style comments** mid-run. Modes: **Planning** (max thinking, no destructive) vs **Fast**. Results → **Inbox**. ([developers.googleblog](https://developers.googleblog.com/build-with-google-antigravity-our-new-agentic-development-platform/), [arjankc](https://www.arjankc.com.np/blog/google-antigravity-agent-manager-explained/))
- **Context:** **Knowledge Items** (distilled facts extracted by a **Knowledge Subagent** at conversation end, persist indefinitely) + `AGENTS.md` + rolling summaries (~800K char cap) + `.agents/workflows/` + Skills (`SKILL.md`).
- **Tools:** Skills auto-activate (`npx skills add`); exec policies (terminal auto-exec, artifact-review "Agent Decides", JS policy) + allow/deny lists. **Sub-agents:** parallel agents (one per workspace) + Browser Subagent + Knowledge Subagent.
- **Background/artifacts:** long-running agents in bg → Inbox; **Artifact typology** = task lists/plans (pre) · diffs (mid) · **Walkthroughs** + **Visual Evidence (screenshots + MP4 browser recordings)** (post). **Verify-at-a-glance via artifacts, not logs.** MCP via `~/.gemini/config/mcp_config.json`; first-class browser control.

### Amazon Kiro (spec-driven agentic IDE, v0.5 2025-10-31)
- **Paradigm:** **spec = unit of work** — 3 files `requirements.md` (EARS: `WHEN … THE SYSTEM SHALL …`) → `design.md` → `tasks.md` (numbered checklist). **Approval gates between phases**; Quick-Plan skips gates; **dependency engine groups tasks into concurrent "waves"**. ([kiro.dev/docs/specs](https://kiro.dev/docs/specs/))
- **Context:** **steering files** `.kiro/steering/` (`product/tech/structure.md`, default always-on) with inclusion modes `always`/`fileMatch`(+glob)/`manual`(#name)/`auto`; `#[[file:path:10-25]]` pins a line range; `AGENTS.md`. ([kiro.dev/docs/steering](https://kiro.dev/docs/steering/))
- **Tools/trust:** **Autopilot** (end-to-end, retroactive View/Revert/Interrupt) vs **Supervised** (per-file/per-hunk accept/reject). **Agent hooks** (`.kiro/hooks/`) event-driven bg automations (PostFileSave, userTriggered, pre/post tool-invoke → agent prompt or shell). MCP local + **Remote (Streamable HTTP)**, one-click install (v0.5).
- **Verify:** spec-as-contract (EARS traceable to tasks→code); gate-before-code.

### GitHub Copilot (agent mode + coding agent)
- **Two surfaces:** **agent mode** (sync, in-IDE) vs **coding agent** (async, cloud, GitHub-Actions ephemeral env).
- **Context:** merged instruction stack (personal → `.github/instructions/*.md` `applyTo` globs → `copilot-instructions.md` → `AGENTS.md` → org); reads `CLAUDE.md`/`GEMINI.md`; **prompt files `.prompt.md` are on-demand, not auto-injected**; Copilot **Memory** (preview) + **Spaces** (grounding).
- **Tools:** `.github/agents/*.agent.md` (instructions+tools+model); **auto-apply edits, gate only terminal commands**; MCP (GitHub + Playwright MCP default in coding agent).
- **Background (standout):** assign issue → 👀 → **opens branch + draft PR simultaneously** → task checklist in PR body → pushes commits per item; **59-min cap**, one repo/branch/PR. **PR = the HITL gate** (never merges). ([github.blog/assigning-and-completing-issues](https://github.blog/ai-and-ml/github-copilot/assigning-and-completing-issues-with-coding-agent-in-github-copilot/), [docs/about-coding-agent](https://docs.github.com/copilot/concepts/agents/coding-agent/about-coding-agent))
- **Web:** github.com = model-native/Bing; VS Code = "Web Search for Copilot" **MCP** extension.

### Zed AI (local, editor-native, multi-threaded)
- **Context:** @-mention files/dirs/symbols/**prior threads**/diagnostics/branch-diffs/URLs; `.rules`/`AGENTS.md`; **auto-compaction** near threshold → "**Context Compacted**" entry (`agent.auto_compact`); "**New From Summary**". Each thread its own window.
- **Tools:** **Profiles** = Ask (read-only) / Write (all) / Minimal (none) / custom (`agent.profiles`) + per-tool allow/deny/confirm.
- **Parallel:** concurrent independent threads; **git-worktree isolation** (`create_worktree` hook); **heterogeneous agents per thread via ACP** (Claude Code/Codex mixable); Terminal Threads.
- **External:** "**context servers = MCP**". **Web:** URL-fetch native + search via MCP.
- **HITL:** **Restore Checkpoint** per message (even mid-edit; caveat: destructive, no redo); **Review Changes** `ctrl-shift-r` per-hunk accept/reject; **Follow mode**; editable/replayable messages; persistent threads.

### Aider (open-source, git-native)
- **Repository Map (signature):** tree-sitter AST → symbols+signatures; **PageRank over dependency graph** ranks symbols (×10 chat-mentioned, ×50 files-in-chat); **`--map-tokens` budget (default 1K)**, re-ranks against chat state. ([aider.chat/repomap](https://aider.chat/2023/10/22/repomap.html))
- **Edit formats:** whole / diff / **udiff** (line-numbers omitted, "act like writing data for a program" → 3× fewer lazy stubs, 20%→61% refactor bench). **Architect/Editor:** strong reasoner proposes prose, cheap editor emits diffs.
- **External:** `/web` (Playwright/httpx scrape) + `/run`; **no native MCP**. Git-native: auto-commit per edit, dirty-commit separates human vs AI, `/undo`.

### Continue.dev (open-source, config-driven)
- **`config.yaml`:** `models` with **roles** (chat/edit/**apply**/embed/rerank/autocomplete/summarize); **rules** (`.continue/rules`, globs); **prompts** (`/`-invokable).
- **Modes:** **Chat** (no tools) / **Plan** (read-only tools) / **Agent** (all tools, "Ask First" per-tool gate). **MCP only in Agent mode** (stdio/SSE/streamable-http).
- **@-providers (16+):** `@codebase` (tree-sitter chunk → LanceDB embed + SQLite FTS; **nRetrieve 25 → rerank → nFinal 5**), `@docs` (crawl+embed a doc site), `@repo-map`, **`@web`**, `@url`, `@git`…

### Windsurf (Cascade) & Cline — brief (folded from cross-cutting)
- **Windsurf Cascade:** "**Memories**" (auto-captured + user rules), Cascade flows, MCP.
- **Cline:** **pioneered MCP-in-IDE**; "**memory bank**" = markdown files re-read each session; explicit **Plan/Act** toggle; per-tool approval.
- Both reinforce the convergent patterns below (memory-as-files, plan/act separation, MCP-native).

---

## Part 2 — Cross-cutting industry patterns (Anthropic/OpenAI/Google/MCP)

1. **Compaction** = summarize near-limit → fresh window seeded with summary (keep state/decisions/next-steps + recent files verbatim; drop stale tool outputs). Anthropic productized primitives:
   - **Context editing** `clear_tool_uses_20250919` (default trigger 100K, `keep`=3, `exclude_tools` e.g. web_search) — "safest, lightest-touch compaction"; `clear_thinking_20251015`.
   - **Memory tool** `memory_20250818` (agent writes NOTES outside window, pulls back on demand). Memory + context-editing = **+39%** on internal agentic-search eval. ([anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), [context-editing docs](https://platform.claude.com/docs/en/build-with-claude/context-editing))
2. **Token budget:** live %-used + tiered warnings (~70/85%); typed buckets **system · pinned/memory · files · conversation · tool-results** (tool-results biggest → evicted first); reserve **~10–15% output headroom**; `count_tokens` previews post-clearing impact.
3. **Tools/skills at scale:** static loading = up to **72% context bloat**; accuracy collapses (RAG-MCP 43%→14%). Fix = **Tool Search / progressive disclosure** (Anthropic GA Feb 2026, ~85% cut) + **`SKILL.md` 3-tier** (L1 metadata ~1.7K total for 17 skills / L2 body on-relevance / L3 scripts run-without-reading). **MCP 3 primitives:** **Tools** (model-controlled) · **Resources** (app-controlled data = "load context from other providers") · **Prompts** (user-controlled = slash commands). Skills=procedure, MCP=access. ([agent skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills), [MCP prompts](https://modelcontextprotocol.io/specification/2025-06-18/server/prompts))
4. **Sub-agents:** child has own window; **only ~1–2K distilled final message returns**; parallel fan-out for independent work; helps when subtasks large+independent, hurts when short/interdependent.
5. **Background/async:** **checkpoint-and-resume** (LangGraph/Temporal/ADK); **human-resumable suspension** (stop truly, persist state, resume — "30 seconds or 3 days"); short-term (thread checkpoint) vs long-term (cross-session) memory.
6. **HITL/trust:** **reversibility → autonomy** (undoable = auto-allow; state-mutating = gate); permission modes (default/acceptEdits/plan); **plan-then-act**; **3-checkpoint gating** (plan-review → findings-review → diff-before-push); checkpoints/undo + verification artifacts.

**Table-stakes** (ship or you're behind): live token meter + tiered warnings + typed buckets + output headroom; auto-compaction + steerable manual compact; tool-result eviction (keep-N + exclusions); MCP interop; per-session tool enable/disable; sub-agent distilled-return; HITL gates keyed to reversibility.
**Differentiators:** memory/notes tool wired **pre-eviction** (the +39% lever for long stateful docs); tool-search/progressive-disclosure over a big catalog; `SKILL.md` procedural skills; durable background agents with human-resumable suspension.

---

## Part 3 — The standard, per axis (converged)

| Axis | The standard mechanism |
|---|---|
| **Context budget** | live %-used meter, tiered warnings 70/85%, typed buckets (system·pinned·files·conversation·tool-results), reserve 10–15% output |
| **Compaction** | microcompact (drop stale tool-results, no model call) → full compact (`<summary>` keeps state+recent-files verbatim) → manual `/compact`+`/clear`; use Anthropic context-editing + memory tool |
| **Memory** | small always-on rules (CLAUDE.md/steering/rules) + auto-suggested/curated memories + a memory *tool* for durable notes |
| **Tools at scale** | progressive disclosure / tool-search (not static load); per-session enable/disable; Tier gating by reversibility |
| **Skills** | `SKILL.md` 3-tier (metadata → body → scripts); skills=procedure, MCP=access |
| **External context** | MCP tools + **resources** + **prompts**; @-mention providers; RAG index of the corpus |
| **Sub-agents** | isolated window, distilled return, parallel fan-out for independent work |
| **Background** | durable checkpoint-and-resume + human-resumable suspension + completion notify |
| **Web search** | first-class tool, inline citations, domain allow/deny |
| **HITL** | reversibility→autonomy; permission modes; plan-then-act; diff/checkpoint review; verification artifacts |

---

## Part 4 — LoreWeave gap map (have / fragmented / missing)

| Axis | ✅ Have (solid) | 🟡 Fragmented | 🔴 Missing |
|---|---|---|---|
| Context mgmt | working_memory charter (goal/phases/state, pinned+tail), memory-mode indicator (no_project/static/degraded), knowledge-project binding | `composeMode` only signals presence; `ContextBar` is next-message-only | **token/% meter, tiered warnings, compaction (auto+manual), typed buckets, output headroom** |
| Tool/skill | **rack curation** (enabled_tools/skills, cap 8/4), **`find_tools`** (= Tool Search), Tier-A/S/W/G gating, skill_registry (4 skills, surface-aware) | no per-skill config; no in-session catalog refresh; no approval for server-side MCP tools | MCP **resources & prompts** (only tools today); skill↔tool affinity |
| HITL gates | **propose_edit / confirm_action / batch-confirm** cards, Tier gating, **activity+undo strip** | — | permission *modes* (Ask/Write/Minimal), chat plan-mode |
| Sub-agent | — | — | **none** (single agent) |
| Background | **SharedWorker hub** keeps turn alive across dock float/close (windowingEnabled) | — | **durable server-side suspend/resume**; turn dies on browser close; no "run in bg → notify" |
| External context | knowledge-service RAG/KG per turn, glossary/book tools, one-off attachments | multi-source is manual; no attach suggestions | web-search not surfaced; MCP resources; dynamic vector-recall |
| Web search | BYOK wired at provider-registry | — | UI enable + BYOK cred + inline citations |
| Streaming/UX | **AG-UI SSE**, agent-surface state machine, thinking block, model picker, format toggles, **full-stack voice**, usage/timing | usage hidden; no format-obeyed feedback | live token countdown; model-capability hints |

**Key files:** `frontend/src/features/chat/{hooks/useContextRack.ts, components/AgentContextRack.tsx, workers/chatStateHub.ts, hooks/agUiEvents.ts}`, `services/chat-service/app/services/{working_memory.py, tool_surface.py, tool_discovery.py, skill_registry.py, frontend_tools.py, agent_surface.py, stream_events.py}`, `frontend/src/features/studio/panels/ComposePanel.tsx`.

---

## Part 5 — Where LoreWeave is AT or AHEAD of the pack (build on these)

1. **knowledge-service (KG + semantic RAG + authored SSOT) = Cursor's codebase index, but for a novel** — Cursor must embed a repo; we already have a two-layer KG + working_memory. **Biggest differentiator.**
2. **Tool curation rack + `find_tools` + Tier gating** = exactly the "Tool Search / progressive disclosure" pattern Anthropic GA'd early 2026. We already have it.
3. **Quality Report / promise-coverage engines** = the novel analog of Antigravity's **verification artifacts** / Kiro's EARS spec (arc-conformance, motif, promise coverage) — proof-of-work for prose.
4. **Durable job infra exists on the BACKEND** (campaign saga, outbox, resume_state, WFQ) — chat just doesn't use it yet. "Durable background agent" is **plumbing to reuse, not net-new build.**
5. **Frontend-tool contract + Lane A/B/C** (just standardized + test-locked) = the agent→GUI HITL spine many tools lack.

---

## Part 6 — Recommended standard for the Studio chat-agent (3 priority tiers)

**🥇 Table-stakes to close (clearest gaps):**
1. Context **meter + tiered warnings** (70/85%) + **typed buckets** + 10–15% output headroom. (FE already emits usage events — surface as a meter.)
2. **Compaction:** reuse Anthropic **context-editing (`clear_tool_uses`) + memory tool** (we're on Claude/BYOK) → auto microcompact tool-results + a **manual "Compact" button** + "New from summary". *Gap #1.*
3. **Web search** surfaced as a BYOK tool with citations + domain gate (see memory `web-search-is-a-tool-not-llm-spend`).

**🥈 Bring up to standard:**
4. Context rack → **persistent pinned context** (pin bible/character/scene to *every* turn, not just the next message).
5. **MCP resources + prompts** first-class (we only have tools): resources = the correct "load context from other providers"; prompts = reusable slash-commands.
6. **Permission modes** for chat (Ask/Write/Compose), wired to the existing `composeMode`.

**🥉 Differentiators (novel-specific — where we win):**
7. **Story-bible-as-steering** (Kiro steering / Cursor rules for fiction): per-book bible file, inclusion modes (always/scene-match/manual) → auto-inject the right context.
8. **Memory tool wired PRE-eviction** to preserve canon/plot (the +39% lever for long stateful documents).
9. **Critic/continuity sub-agent** (fan-out): mach-truyện / character-consistency checker runs in parallel, returns a distilled verdict — reuse the existing "idle judges" constellation.
10. **Durable background revision runs** reusing the campaign-saga infra → "revise 12 chapters in the background, notify on done" (a Copilot-coding-agent for prose); verification artifact = the **Quality Report**.

---

## Part 7 — Open questions for discussion (next)

- **Paradigm depth:** stay chat-in-dock (Cursor-like) or invest early in an Antigravity-style "agent manager / Inbox" for background authoring runs?
- **Compaction ownership:** rely on Anthropic server-side context-editing/memory (BYOK-Claude only) vs a provider-agnostic compaction in chat-service (works for local lm_studio models too)? Trade-off: leverage vs portability.
- **Story-bible-as-steering vs working_memory charter:** unify, or keep charter (task state) separate from bible (world state)?
- **Sub-agent scope:** which authoring tasks justify a sub-agent (critic, continuity, research) vs staying single-agent?
- **Priority order:** confirm 🥇1–3 first; or pull a differentiator (e.g. #8 memory-for-canon) forward because it compounds with the KG we already have?

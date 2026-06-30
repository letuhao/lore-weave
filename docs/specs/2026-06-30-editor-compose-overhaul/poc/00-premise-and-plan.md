# POC — "Can we write a long novel with our tools + Gemma-4 26B QAT?"

> **Goal:** drive the PO's real story idea through the actual composition journey (Idea → Structure →
> Draft) + glossary + KG, using **Gemma-4 26B QAT** (local lm_studio, BYOK), and produce **10–20
> chapters**. Capture every input/output to find what's ✅ wired / 🟡 hidden / 🔴 missing — the
> concrete backlog for the overhaul.

## The story idea (POC input — verbatim intent)
- **Theme:** dark cultivation (xianxia), heavy drama + plot twists.
- **MC:** an **ugly young woman**, **hated by everyone including her parents**, with **bad cultivation
  potential**.
- **Inciting incident:** in a near-death experience she obtains a **succubus's ancient grimoire** and
  decides to learn it.
- **Arc:** she improves herself, aiming to one day reach **perfection**.
- **Focus:** cultivation + combat. Romance is **optional/secondary**.
- **Output language:** **Vietnamese** (Tiếng Việt) — prose generated in Vietnamese via Gemma-4 26B QAT.

## POC method
1. **Resolve env** — stack up? Gemma-4 26B QAT reachable (lm_studio)? Resolve its `user_model_id` for
   the test account (`claude-test@loreweave.dev`, `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`).
2. **Build a POC harness** (script) that walks the journey against the REAL services and **logs every
   request/response** to `poc/io/`:
   - create Book + chapters (Planner needs existing chapters — the §11.4 gotcha)
   - Idea → premise (chat brainstorm, optional)
   - Structure → Planner decompose (premise + structure_template → scenes)
   - Draft → Compose per scene (Gemma)
   - Glossary extract + KG build
3. **Smoke first** (1 chapter end-to-end), then **scale to 10–20**.
4. **Score each step** ✅/🟡/🔴 and write findings to `poc/02-findings.md`.

## Success criteria
- A coherent multi-chapter story scaffold (outline + drafted scenes) exists.
- Glossary entities + KG graph populate from the prose.
- We can name the exact missing pieces that block a non-writer from doing this in the GUI.

## Status
- [ ] env resolved
- [ ] harness built
- [ ] smoke (1 chapter)
- [ ] scaled (10–20)
- [ ] findings written

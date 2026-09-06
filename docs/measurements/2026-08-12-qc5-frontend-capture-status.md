# QC-5 end-to-end frontend capture — status, 2026-08-12

**Two of four artefacts captured. The drafting run itself has NOT been executed, so this
does not close `D-QC5-FULL-FLOW-CAPTURE`.**

Recorded because the environment work is the expensive half and it is now done and
reproducible — the next session starts at the drafting run rather than at a cold stack.

## The environment, stood up and driven

Everything below is the **isolated stack** (`infra/iso.sh`, ports +20000). The shared stack
no longer serves this branch's code.

| | |
|---|---|
| Services | postgres · redis · neo4j · minio · rabbitmq · pandoc · book · glossary · knowledge · worker-infra · composition · composition-worker · ai-gateway · provider-registry · usage-billing · auth · api-gateway-bff · frontend · agent-registry · jobs |
| Databases cloned | auth · book · glossary · knowledge · composition · provider_registry |
| Frontend | `http://localhost:25174` — real UI, real nginx build |
| Login | real form login as the book's owning user |
| Model resolved | **Gemma-4 26B-A4B QAT (200K)**, shown in the editor — provider-registry → LM Studio, so the LLM path is wired end to end |

**Getting a login needed one deliberate write.** The acceptance user's password is not in the
repo (`docs/dev/LOCAL_TEST_ENV.md` is git-ignored and absent), so a known password was
written into the **isolated clone's** auth database, using the service's own hashing
parameters (`authpwd`: argon2id, t=3, m=64MiB, p=4, 32-byte key, `argon2id$` + raw-std-b64 of
salt‖hash). The shared stack was not touched. This is only acceptable *because* the database
is a throwaway clone — on shared data it would be tampering with someone's account.

## Artefacts

| # | Artefact | Status |
|---|---|---|
| 1 | the plan artifact | ✅ **captured** — Plan Centre, 13 chapters with per-chapter status |
| 2 | the drafted chapters | ❌ not produced — the drafting run was not executed |
| 3 | the critic's per-chapter scores | ❌ not produced — depends on (2) |
| 4 | the glossary delta | ◐ **before** captured (`46` live / `43` named); **after** pending (2) |

### 1 — the plan artifact

<!-- doc-language-gate: ok -- the UI's own labels ARE the captured artefact -->
The book's plan, as the real Plan Centre renders it: two arcs (`Arc mở đầu` 1 beat, and an
11-beat arc), 13 chapters, 35 scenes. Per-chapter status in this clone:

```
 1  ĐANG VIẾT (writing, 102 words)
 3, 4, 5  HOÀN THÀNH (complete)
 2, 6, 7, 8, 9, 10, 11, 12, 13  CHƯA BẮT ĐẦU (not started)
```

<!-- doc-language-gate: end -->

**The three chapters QC-5 names are 11–13** — the trap sequence — and all three are
**not started** in this clone, so the drafting run is a genuine generation, not a re-read of
existing text. Chapter 11 expands to three scenes, the first of which is the beat the
previously-analysed draft came from.

### 4 — the glossary delta, before

```
live entities (deleted_at IS NULL)   46
of those, named                      43
KG mirror at baseline                43 mirrored, 0 missing
```

## What remains

<!-- doc-language-gate: ok -- UI control names, quoted verbatim so the next session can find them -->
Drive the drafting of chapters 11–13 through the studio and capture the drafted text plus
the critic's per-chapter scores, then re-measure the glossary. The editor is reachable and
the model resolves; the remaining unknown is which studio surface starts a plan-driven
draft — the AI actions on the editor toolbar are `Viết lại` / `Mở rộng` / `Miêu tả` /
`Tiếp tục từ con trỏ` (rewrite / expand / describe / continue-from-cursor), and the
plan-driven drafting appears to live behind the agent-run surface (`Đường ray Tiến trình`,
`Các lượt chạy Agent tự động`) rather than a single button.
<!-- doc-language-gate: end -->

⚠️ **LM Studio is shared with the other branch's stack.** A nine-scene generation run will
occupy that queue for a while; worth a word to whoever is on the other branch before
starting.

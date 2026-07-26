# S3·motif — real-model agent eval + live-smoke (composition tool unification)

**Date:** 2026-07-25 · **Branch:** `feat/frontend-tools-mcp-migration`

## What shipped

The 8 per-op motif write tools consolidated into **3 unified op-tools** (grouped by tier+scope):

| Unified tool | Tier/Scope | Supersedes |
|---|---|---|
| `composition_motif_edit(op=create\|patch\|archive\|restore)` | A/user | motif_create, motif_patch, motif_archive, motif_restore |
| `composition_motif_link_edit(op=create\|delete)` | A/user | motif_link_create, motif_link_delete |
| `composition_motif_bind_edit(op=bind\|unbind)` | A/book | motif_bind, motif_unbind |

The 8 legacy tools are `visibility=legacy` + `superseded_by` (still callable, hidden from
`tool_list` default). `adopt` (W/user), `mine` (W/book), and all reads stay separate (different
tier / non-CRUD). Delegates to the SAME handlers, zero logic moved.

## Live-smoke (direct MCP, $0)

- `motif_edit` create→patch→archive→restore round-trip, all `isError=false`. **The patch changed
  ONLY `summary` and KEPT `name`** — partial-patch semantics survive the op-wrapper (the
  `model_fields_set` risk, unit- + live-proven).
- `motif_link_edit` create→delete on two owned motifs, `isError=false`.
- `op=create` missing name → clean `isError` ("requires code and name"), not a silent no-op.
- Legacy `composition_motif_archive` still callable.
- **Discovery shrink:** `tool_list` default `composition_motif*` **15 → 10 visible** (8 legacy
  hidden / 0 shown); `include_deprecated=true` → 18 (8 legacy back).

## Real-model agent eval — PASS

Gemma-4 26B (local, provider-registry→lm_studio, $0), the 8 legacy motif tools HIDDEN, given a
3-step task ("create motif → change ONLY its summary → archive it"):

| Turn | Model tool call | Result |
|---|---|---|
| 0 | `composition_motif_edit {op:create, code, name:'The Reluctant Mentor', kind:trope}` | motif `019f986f…` v1 |
| 1 | `composition_motif_edit {op:patch, motif_id, expected_version:1, summary:'A jaded veteran…'}` | v1→v2 |
| 2 | `composition_motif_edit {op:archive, motif_id}` | archived |
| 3 | *(no call)* | confirms done |

**Only `composition_motif_edit` (×3), ops `[create, patch, archive]`, zero legacy tools.** The
model threaded `expected_version:1` into the patch unprompted and issued a **partial patch**.

### DB verification (`loreweave_composition.motif` `019f986f…`)
```
name    = The Reluctant Mentor          # create — KEPT through the partial patch
kind    = trope                         # create — KEPT
summary = A jaded veteran is pulled back in.   # patch — the only changed field
version = 2                             # create→v1, patch→v2
status  = archived                      # archive
```

## Conclusion

`composition_motif_edit` (and its link/bind siblings) is a **verified drop-in replacement**: a
real local model discovered and drove the unified tool through a full lifecycle with the legacy
tools invisible, and — the motif-specific risk — its partial patch did not clobber unset fields.

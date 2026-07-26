"""Phase-1 chaining for BOOK/PROJECT-scoped creators (the composition + planforge families).

`user_fixture.authored_user_args` chains the USER-scoped writes (motif, glossary_user,
registry). This is its book-scoped twin: the composition and planforge tools that mint an
id a later tool consumes, but whose scope is `book`/`project`, so they run in PHASE 1
against the throwaway fixture book — not phase 2.

The lever that makes this cheap:
  * `composition_create_work` mints the COMPOSITION `project_id` (distinct from the kg
    project the fixture already holds — composition has its own `composition_work` table;
    a kg project_id fails these tools with "not found or not accessible").
  * `plan_propose_spec` in the default `rules` mode runs SYNCHRONOUSLY ($0, no LLM) and
    returns a real `run_id` immediately — so the whole `run_id` consumer cluster is
    reachable without spending on an async plan job.
  * `composition_outline_node_create` (kind `beat` — `scene`/`chapter` need a chapter_id,
    `act` fails the kind check) and `composition_canon_rule_create` each return `{id,
    version}`, which their update/delete twins consume.

Everything here writes only under the throwaway book; `teardown_composition` deletes those
rows (leaking a row per sweep is the trap this module is careful to avoid).
"""
from __future__ import annotations

from typing import Any

from . import config, oracle

# Creators FIRST, then read/update consumers, then DELETES last (a delete before its
# sibling read/update silently starves them). A tool not listed keeps catalog order and
# falls back to fill_args.
PROJECT_SWEEP_ORDER: tuple[str, ...] = (
    "composition_create_work",           # mints the composition project_id
    "plan_propose_spec",                 # mints run_id (sync, rules mode)
    "composition_outline_node_create",   # mints node_id + version
    "composition_canon_rule_create",     # mints rule_id + version
    "composition_arc_create",            # mints arc_id (structure_node) + version
    "book_steering_set",                 # mints a steering rule (name) for _delete
    # run_id consumers (plan_* linters/checkpoint read the seeded run)
    "plan_apply_revision",
    "plan_handoff_autofix",
    "plan_interpret_feedback",
    "plan_validate",
    "plan_self_check",
    "plan_review_checkpoint",
    "plan_compile",
    # node consumers (read/update BEFORE the node is deleted)
    "composition_get_outline_node",
    "composition_outline_node_update",
    "composition_outline_node_move",
    "composition_motif_suggest_for_chapter",
    # rule consumer
    "composition_canon_rule_update",
    # arc consumers (read/update/move/… BEFORE delete; restore un-archives after delete)
    "composition_arc_get",
    "composition_arc_update",
    "composition_arc_move",
    "composition_arc_assign_chapters",
    "composition_arc_template_drift",
    "composition_arc_extract_template",
    "composition_arc_delete",
    "composition_arc_restore",
    # book-scoped glossary/book chains
    "book_list_revisions",               # surfaces the fixture chapter's revision_id
    "book_chapter_restore_revision",     # ← consumes it
    "book_scene_list",                   # surfaces a scene_id (if the chapter parsed scenes)
    "book_scene_get",                    # ← reads it
    "book_steering_delete",              # ← deletes the rule steering_set created
    "glossary_propose_new_entity",       # creates a draft entity in the inbox
    "glossary_book_patch",               # edits an adopted kind row
    "glossary_book_delete",              # mints a delete token for an adopted kind
    "glossary_book_revert",              # mints a revert token to the parent standard
    "glossary_ontology_upsert",          # creates a book kind
    "glossary_ontology_delete",          # ← mints a delete token for it
    # authoring-run consumers of the seeded run (get/gate/create/start/… before close)
    "composition_authoring_run_get",
    "composition_authoring_run_gate",
    "composition_authoring_run_create",
    "composition_authoring_run_start",
    "composition_authoring_run_resume",
    "composition_authoring_run_pause",
    "composition_authoring_run_accept_unit",
    "composition_authoring_run_reject_unit",
    "composition_authoring_run_close",   # ← transitions draft→closed, so LAST
    # kg build chain (on the seeded kg project; embeddings run LOCAL on bge-m3 = $0).
    # ORDER is load-bearing: set-model probes the dim, benchmark + build_graph need it set.
    # Without this ordering the alphabetical fallback runs build_graph (b) before set-model (p).
    "kg_project_set_embedding_model",
    "kg_run_benchmark",
    "kg_build_graph",
    # kg node-chain (reuse the 2 seeded KG nodes + a listed template); propose_edge mints the
    # triage_id/signature the triage_* consume; list_templates surfaces the adopt source.
    "kg_list_templates",
    "kg_entity_edge_timeline",
    "kg_propose_edge",
    "kg_triage_place_edge",
    "kg_triage_resolve",
    "kg_adopt_template",
    # composition scene/outline + motif chains (reuse the 2nd seeded project's nodes + motif)
    "composition_scene_link_create",
    "composition_scene_link_delete",
    "composition_outline_node_restore",
    "composition_motif_bind",
    "composition_motif_unbind",
    # memory: remember mints a fact_id that forget consumes
    "memory_remember",
    "memory_forget",
    # deletes LAST — they destroy the id their siblings above need
    "composition_canon_rule_delete",
    "composition_outline_node_delete",
)


def _id(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


def authored_project_args(tool: str, ids: dict, state: dict) -> dict | None:
    """`ids` holds the fixture (book_id, kg project_id, chapter_id…); `state` holds the
    RESULT of every earlier successful call this phase, so a consumer can read the id its
    creator minted. Returns None ⇒ fall back to fill_args (the ~170 tools not in a chain).
    """
    book = ids.get("book_id")
    work = state.get("composition_create_work") or {}
    cproj = _id(work, "project_id")  # the COMPOSITION project, not the kg one
    run_id = _id(state.get("plan_propose_spec") or {}, "run_id")
    node = state.get("composition_outline_node_create") or {}
    node_id, node_ver = _id(node, "id", "node_id"), node.get("version")
    rule = state.get("composition_canon_rule_create") or {}
    rule_id, rule_ver = _id(rule, "id", "rule_id"), rule.get("version")
    arc = state.get("composition_arc_create") or {}
    arc_id, arc_ver = _id(arc, "id", "node_id", "structure_node_id"), arc.get("version")
    arun = ids.get("authoring_run_id")

    entity_id = ids.get("entity_id")
    chapter_id = ids.get("chapter_id")
    match tool:
        # ── cheap semantic fixes: a required-only call is a no-op ("no fields to update");
        #    supply one optional field on purpose so the write actually exercises ─────────
        case "book_update_meta":
            return {"book_id": book, "description": "TLE sweep touched this"} if book else None
        case "book_chapter_update_meta":
            return {"book_id": book, "chapter_id": chapter_id, "title": "TLE chapter v2"} \
                if (book and chapter_id) else None
        case "glossary_entity_set_attributes":
            # "attributes or scope_label must be provided"; attributes are keyed by the
            # entity kind's DECLARED codes (which the fixture entity has none of), so use the
            # free-form scope_label instead.
            return {"book_id": book, "entity_id": entity_id,
                    "scope_label": "TLE swept"} if (book and entity_id) else None
        case "glossary_propose_new_kind":
            # Tier W: mints a confirm_token for a NEW book kind. `code` is the code being
            # MINTED (not a lookup), so authored, not fill_args-refused.
            return {"book_id": book, "code": "tle_probe_kind", "name": "TLE Probe Kind"} \
                if book else None
        case "glossary_propose_new_attribute":
            # a NEW attribute (code+name) on an EXISTING kind — the fixture adopts
            # character/location/item, so kind_code='character' is a live kind.
            return {"book_id": book, "kind_code": "character",
                    "code": "tle_probe_attr", "name": "TLE Probe Attr"} if book else None
        case "book_chapter_restore_revision":
            # the fixture chapter carries a seed revision; book_list_revisions (ordered
            # before this) surfaces its id.
            revs = (state.get("book_list_revisions") or {}).get("revisions") or []
            rid = revs[0].get("revision_id") if revs else None
            return {"book_id": book, "chapter_id": chapter_id, "revision_id": rid} \
                if (book and chapter_id and rid) else None
        # ── glossary array-payload tools (item shapes mapped from the Go structs) ──
        case "glossary_ontology_upsert":
            # Tier A, writes immediately. Omit base_version ⇒ CREATE a book kind.
            return {"scope": "book", "book_id": book,
                    "items": [{"level": "kind", "code": "tle_upsert_kind",
                               "name": "TLE Upsert Kind"}]} if book else None
        case "glossary_ontology_delete":
            # Tier W: mints a confirm_token (we never redeem it). Targets the kind
            # glossary_ontology_upsert created (ordered before this).
            return {"scope": "book", "book_id": book,
                    "items": [{"level": "kind", "code": "tle_upsert_kind"}]} if book else None
        case "glossary_propose_aliases":
            # Tier A draft. Needs an existing entity; the fixture seeds 'Aldric Vane'.
            return {"book_id": book, "language_code": "en",
                    "items": [{"entity_id": entity_id, "aliases": ["Aldric", "Vane"]}]} \
                if (book and entity_id) else None
        case "glossary_propose_translation":
            return {"book_id": book, "language_code": "vi",
                    "items": [{"entity_id": entity_id, "value": "Aldric Vane"}]} \
                if (book and entity_id) else None
        case "glossary_propose_kinds":
            # Tier W: mints a confirm_token for a batch of kinds.
            return {"book_id": book,
                    "kinds": [{"code": "tle_kinds_kind", "name": "TLE Kinds Kind"}]} if book else None
        case "glossary_propose_batch":
            # Tier W: mints an execute_plan token. create_kinds is self-contained; every
            # attribute needs a non-empty description (extraction instruction) — none here.
            return {"book_id": book, "goal": "probe",
                    "ops": [{"type": "create_kinds",
                             "params": {"kinds": [{"code": "tle_batch_kind",
                                                   "name": "TLE Batch Kind"}]},
                             "rationale": "probe"}]} if book else None
        # ── the lower-yield buildable handful (author payloads / reuse fixture state) ──
        case "book_chapter_bulk_create":
            return {"book_id": book,
                    "chapters": [{"title": "TLE Bulk Chapter", "content": "TLE body"}]} \
                if book else None
        case "glossary_book_set_kind_genres":
            return {"book_id": book, "kind_code": "character", "add": ["universal"]} if book else None
        case "glossary_propose_reassign_kind":
            # Tier W: mint a token to reassign the fixture entity to a different live kind.
            return {"book_id": book, "entity_id": entity_id, "kind_code": "location"} \
                if (book and entity_id) else None
        case "glossary_propose_merge":
            # Tier W: mint a merge token. Fixture seeds ≥2 entities (Aldric winner, Mira loser).
            loser = ids.get("entity_id2")
            return {"book_id": book, "winner_id": entity_id, "loser_ids": [loser]} \
                if (book and entity_id and loser) else None
        case "composition_authoring_run_revert_all":
            arun = ids.get("authoring_run_id")
            return {"args": {"book_id": book, "run_id": arun}} if (book and arun) else None
        case "memory_remember":
            # scope=project — a fact on the kg project; mints a fact_id the forget consumes.
            # fact_type enum: decision|preference|milestone|negation.
            proj = ids.get("project_id")
            return {"fact_text": "TLE probe fact", "fact_type": "preference",
                    "project_id": proj} if proj else None
        case "memory_forget":
            fid = _id(state.get("memory_remember") or {}, "fact_id", "id")
            return {"fact_id": fid} if fid else None
        case "composition_authoring_run_get" | "composition_authoring_run_gate" \
                | "composition_authoring_run_close":
            # the seeded authoring_runs row (see seed_authoring_run). get reads it, gate
            # mints a token, close transitions draft→closed (ordered LAST so it doesn't
            # close the run before gate/get run). These wrap args in the composition `args`
            # envelope (like the other composition_* tools).
            arun = ids.get("authoring_run_id")
            return {"args": {"book_id": book, "run_id": arun}} if (book and arun) else None
        case "composition_get_outline_node":
            node = state.get("composition_outline_node_create") or {}
            nid = _id(node, "id", "node_id")
            return {"project_id": cproj, "node_id": nid} if (cproj and nid) else None
        case "composition_create_work":
            return {"book_id": book} if book else None
        case "plan_propose_spec":
            # rules mode (no model_ref) is synchronous + free; a minimal outline is enough
            # to mint the run row that the run_id consumers operate on.
            return {"book_id": book,
                    "source_markdown": "# Arc One\n\nA hero answers the call and sets out."} \
                if book else None
        case "composition_outline_node_create":
            # kind enum is now {chapter, scene} (was beat); a `chapter` node needs a
            # chapter_id (the fixture chapter).
            return {"args": {"project_id": cproj, "kind": "chapter",
                             "chapter_id": chapter_id, "title": "TLE node"}} \
                if (cproj and chapter_id) else None
        case "composition_canon_rule_create":
            return {"args": {"project_id": cproj, "text": "TLE canon rule: the sky is green."}} \
                if cproj else None
        # ── run_id consumers ────────────────────────────────────────────────────
        case "plan_apply_revision":
            return {"book_id": book, "run_id": run_id} if run_id else None
        case "plan_handoff_autofix":
            return {"book_id": book, "run_id": run_id} if run_id else None
        case "plan_interpret_feedback":
            return {"book_id": book, "run_id": run_id, "user_message": "tighten the pacing"} \
                if run_id else None
        # ── outline node consumers ──────────────────────────────────────────────
        case "composition_outline_node_update":
            if not (cproj and node_id):
                return None
            a = {"project_id": cproj, "node_id": node_id, "title": "TLE node v2"}
            if node_ver is not None:
                a["expected_version"] = node_ver
            return {"args": a}
        case "composition_motif_suggest_for_chapter":
            return {"project_id": cproj, "node_id": node_id} if (cproj and node_id) else None
        # ── canon rule consumers ────────────────────────────────────────────────
        case "composition_canon_rule_update":
            if not (cproj and rule_id):
                return None
            a = {"project_id": cproj, "rule_id": rule_id, "text": "TLE canon rule v2."}
            if rule_ver is not None:
                a["expected_version"] = rule_ver
            return {"args": a}
        case "composition_canon_rule_delete":
            return {"project_id": cproj, "rule_id": rule_id} if (cproj and rule_id) else None
        case "composition_outline_node_delete":
            return {"project_id": cproj, "node_id": node_id} if (cproj and node_id) else None
        case "composition_outline_node_move":
            # reuse the created node; root move (no new parent) is a no-op that still executes.
            return {"args": {"project_id": cproj, "node_id": node_id,
                             "new_parent_id": None, "after_id": None}} \
                if (cproj and node_id) else None
        # ── plan_* linters/checkpoint (reuse the seeded rules-mode run_id) ──────────
        case "plan_validate":
            return {"book_id": book, "run_id": run_id} if run_id else None
        case "plan_self_check":
            return {"book_id": book, "run_id": run_id} if run_id else None
        case "plan_review_checkpoint":
            # approved=False = hold (least state-restrictive), still exercises the write.
            return {"book_id": book, "run_id": run_id, "approved": False} if run_id else None
        case "plan_compile":
            # run_pipeline=False ⇒ deterministic (no LLM). arc_id is a SPEC arc string
            # (rules-mode seeds "arc_1"); a mismatch returns a structured error (still executes).
            return {"book_id": book, "run_id": run_id, "arc_id": "arc_1", "run_pipeline": False} \
                if run_id else None
        # ── arc family (reuse composition_arc_create's arc_id) ──────────────────────
        case "composition_arc_create":
            return {"args": {"book_id": book}} if book else None
        case "composition_arc_get":
            return {"node_id": arc_id} if arc_id else None
        case "composition_arc_update":
            if not arc_id:
                return None
            a = {"node_id": arc_id, "title": "TLE arc v2"}
            if arc_ver is not None:
                a["expected_version"] = arc_ver
            return {"args": a}
        case "composition_arc_move":
            return {"args": {"node_id": arc_id, "new_parent_arc_id": None, "after_id": None}} \
                if arc_id else None
        case "composition_arc_assign_chapters":
            # empty chapter list ⇒ assigns nothing but still executes the write path.
            return {"args": {"book_id": book, "structure_node_id": arc_id, "chapter_node_ids": []}} \
                if (book and arc_id) else None
        case "composition_arc_template_drift":
            # an arc without provenance returns {"available": false} (early) → executes.
            return {"node_id": arc_id} if arc_id else None
        case "composition_arc_extract_template":
            return {"args": {"node_id": arc_id, "code": "tle_arc_tmpl",
                             "name": "TLE Arc Template"}} if arc_id else None
        case "composition_arc_delete":
            return {"node_id": arc_id} if arc_id else None
        case "composition_arc_restore":
            return {"node_id": arc_id} if arc_id else None
        # ── authoring-run family (reuse the seeded authoring_run_id) ────────────────
        case "composition_authoring_run_create":
            return {"args": {"book_id": book, "plan_run_id": run_id, "budget_usd": 1,
                             "pause_after_each_unit": True, "scope": [],
                             "tool_allowlist": [], "level": 3}} if (book and run_id) else None
        case "composition_authoring_run_start" | "composition_authoring_run_resume":
            # each MINTS a confirm_token only (real drafting runs on confirm, never here).
            return {"args": {"book_id": book, "run_id": arun}} if (book and arun) else None
        case "composition_authoring_run_pause":
            # a draft run raises TransitionConflict → CAUGHT → {"success": false} dict → executes.
            return {"args": {"book_id": book, "run_id": arun}} if (book and arun) else None
        case "composition_authoring_run_accept_unit" | "composition_authoring_run_reject_unit":
            # no unit at index 0 → LookupError CAUGHT → {"success": false} dict → executes.
            return {"args": {"book_id": book, "run_id": arun, "unit_index": 0}} \
                if (book and arun) else None
        # ── book steering (set mints a rule name; delete consumes it) ───────────────
        case "book_steering_set":
            return {"book_id": book, "name": "tle-rule", "body": "TLE steering probe"} \
                if book else None
        case "book_steering_delete":
            return {"book_id": book, "name": "tle-rule"} if book else None
        case "book_scene_get":
            # prefer the directly-seeded scene (seed_db_fixtures); else a parsed one.
            sid = ids.get("scene_id")
            if not sid:
                scenes = (state.get("book_scene_list") or {}).get("scenes") or []
                sid = (scenes[0].get("scene_id") or scenes[0].get("id")) if scenes else None
            return {"book_id": book, "scene_id": sid} if (book and sid) else None
        # ── glossary book-standard writes (target the fixture's adopted kinds) ──────
        case "glossary_propose_new_entity":
            return {"book_id": book, "kind": "character", "name": "TLE probe entity"} \
                if book else None
        case "glossary_book_patch":
            return {"book_id": book, "level": "kind", "code": "character",
                    "name": "Character (TLE)"} if book else None
        case "glossary_book_delete":
            return {"book_id": book, "level": "kind", "code": "item"} if book else None
        case "glossary_book_revert":
            return {"book_id": book, "level": "kind", "code": "character"} if book else None
        # ── kg build chain (seeded kg project; local bge-m3 embeddings = $0) ────────
        case "kg_project_set_embedding_model":
            # probes the vector dim with ONE real (local) embedding call; set-on-unset only.
            kg = ids.get("project_id")
            return {"embedding_model": config.EMBEDDING_MODEL_REF, "project_id": kg} if kg else None
        case "kg_run_benchmark":
            # embeddings-only golden benchmark (local) — needs the model set above.
            kg = ids.get("project_id")
            return {"project_id": kg} if kg else None
        case "kg_build_graph":
            # MINTS a confirm_token only (extraction runs on confirm, never here) — needs
            # the embedding model set; llm_model is not validated at mint time.
            kg = ids.get("project_id")
            return {"llm_model": config.MODEL_REF, "scope": "glossary_sync", "project_id": kg} \
                if kg else None
        case "kg_world_query":
            # an EMPTY seeded world returns {nodes:[],edges:[]} → executes.
            wid = ids.get("world_id")
            return {"world_id": wid} if wid else None
        # ── translation-version tools (reuse the seeded job + completed version) ─────
        case "jobs_get":
            # user-scoped R, swept in phase 1 too — a synthetic job_id → not-found dict.
            return {"service": "composition", "job_id": "00000000-0000-4000-8000-000000000001"}
        case "translation_job_status":
            jid = ids.get("translation_job_id")
            return {"job_id": jid} if jid else None
        case "translation_job_control":
            jid = ids.get("translation_job_id")
            return {"job_id": jid, "action": "pause"} if jid else None
        case "translation_set_active_version":
            vid = ids.get("translation_version_id")
            return {"book_id": book, "chapter_id": chapter_id, "version_id": vid} \
                if (book and chapter_id and vid) else None
        case "translation_save_edited_version":
            vid = ids.get("translation_version_id")
            return {"book_id": book, "chapter_id": chapter_id, "edited_from_version_id": vid,
                    "target_language": "en", "translated_body": "TLE edited"} \
                if (book and chapter_id and vid) else None
        case "translation_patch_block":
            vid = ids.get("translation_version_id")
            return {"book_id": book, "chapter_id": chapter_id, "base_version_id": vid,
                    "target_language": "en", "block_index": 0,
                    "block": {"type": "paragraph", "content": []}} \
                if (book and chapter_id and vid) else None
        # ── kg node-chain (reuse the 2 seeded KG nodes + kg_list_templates) ──────────
        case "kg_create_node":
            # Tier-A, idempotent. Authored args bypass the fill_args project_id auto-inject,
            # so pass it explicitly.
            kg = ids.get("project_id")
            return {"name": "TLE probe node", "kind": "character", "project_id": kg} if kg else None
        case "kg_entity_edge_timeline":
            na = ids.get("kg_node_a")
            return {"entity_id": na, "edge_type": "tle_rel"} if na else None
        case "kg_propose_edge":
            na, nb, kg = ids.get("kg_node_a"), ids.get("kg_node_b"), ids.get("project_id")
            return {"source_entity_id": na, "target_entity_id": nb,
                    "edge_type": "tle_rel", "project_id": kg} if (na and nb and kg) else None
        case "kg_triage_place_edge":
            tid = _id(state.get("kg_propose_edge") or {}, "triage_id", "id")
            kg = ids.get("project_id")
            return {"triage_id": tid, "project_id": kg} if (tid and kg) else None
        case "kg_triage_resolve":
            sig = _id(state.get("kg_propose_edge") or {}, "signature")
            kg = ids.get("project_id")
            # already-placed ⇒ structured refusal (still executes); dismiss is least-destructive.
            return {"signature": sig, "action": "dismiss", "project_id": kg} if (sig and kg) else None
        case "kg_adopt_template":
            tmpls = state.get("kg_list_templates")
            first = (tmpls[0] if isinstance(tmpls, list) and tmpls
                     else (tmpls or {}).get("templates", [{}])[0] if isinstance(tmpls, dict) else {})
            sid = (first or {}).get("schema_id") or (first or {}).get("id")
            kg = ids.get("project_id")
            return {"source_schema_id": sid, "project_id": kg} if (sid and kg) else None
        # ── composition scene/outline chains (reuse the 2nd project + its nodes) ─────
        case "composition_scene_link_create":
            cp, na, nb = ids.get("cproj2"), ids.get("node_a"), ids.get("node_b")
            return {"args": {"project_id": cp, "from_node_id": na, "to_node_id": nb,
                             "kind": "setup_payoff"}} if (cp and na and nb) else None
        case "composition_scene_link_delete":
            cp = ids.get("cproj2")
            lid = _id(state.get("composition_scene_link_create") or {}, "id", "link_id")
            return {"project_id": cp, "link_id": lid} if (cp and lid) else None
        case "composition_outline_node_restore":
            cp, arch = ids.get("cproj2"), ids.get("node_archived")
            return {"project_id": cp, "node_id": arch} if (cp and arch) else None
        # ── composition motif bind/unbind (reuse the 2nd project's node + a motif) ───
        case "composition_motif_bind":
            cp, na, ma = ids.get("cproj2"), ids.get("node_a"), ids.get("motif_a")
            return {"args": {"project_id": cp, "node_id": na, "motif_id": ma,
                             "role_bindings": {}}} if (cp and na and ma) else None
        case "composition_motif_unbind":
            cp, na = ids.get("cproj2"), ids.get("node_a")
            return {"project_id": cp, "node_id": na} if (cp and na) else None
        case "book_chapter_save_draft":
            # `body` is the chapter's PROSE, as plain text (M0a, 2026-07-13). It used to be
            # declared json.RawMessage — i.e. []byte — so the schema advertised an array of
            # INTEGERS and the tool was uncallable with real content by anyone, including this
            # probe. That is why this tool sat at `executes: null / SWEEP-INCONCLUSIVE` and was
            # written off as a fixture problem ("needs a chapter_drafts row at a matching
            # base_version"). It was not the fixture; the contract was impossible.
            dv = ids.get("draft_version")
            return {"book_id": book, "chapter_id": chapter_id, "base_version": dv,
                    "body": "The probe wrote this paragraph.",
                    "commit_message": "tool-liveness probe"} \
                if (book and chapter_id and dv is not None) else None
        case _:
            return None  # not in a chain → fill_args


def seed_authoring_run(ids: dict) -> None:
    """Seed a throwaway authoring_runs row so its get/gate/close consumers are reachable at
    $0. authoring_run_create is Tier-W + a paid confirm (`budget_usd`), so nothing minted a
    run for the sweep. But the row only needs a `plan_run_id`, which plan_propose_spec mints
    synchronously in rules mode (free). Mint one, INSERT the run in `draft`, stash its id.
    (Book-scoped, so teardown_composition cleans it with the rest.)"""
    import uuid

    from .mcp_direct import MCPDirect

    book = ids.get("book_id")
    if not book:
        return
    try:
        plan = MCPDirect().call(
            "plan_propose_spec",
            {"book_id": book, "source_markdown": "# Arc One\n\nA hero sets out."})
        plan_run_id = plan.get("run_id")
        if not plan_run_id:
            return
        run_id = str(uuid.uuid4())
        oracle.db_query(
            config.DOMAIN_DB["composition"],
            "INSERT INTO authoring_runs(run_id, created_by, book_id, plan_run_id, level, status) "
            f"VALUES ('{run_id}','{config.USER_ID}','{book}','{plan_run_id}',3,'draft')")  # level ∈ {3,4}
        ids["authoring_run_id"] = run_id
    except Exception as e:  # non-fatal — the 3 consumers just stay null
        print(f"  (no authoring-run seed: {type(e).__name__}: {e})")


# DB names outside DOMAIN_DB the $0 seeds touch directly.
_TRANSLATION_DB = "loreweave_translation"


def seed_db_fixtures(ids: dict) -> None:
    """Seed rows NO $0 MCP creator can mint but which a consuming tool needs, so the tool
    reaches `executes` on a throwaway target it OWNS (never real data). Everything here is a
    plain INSERT under the fixture book/user — cleaned by `teardown_db_fixtures`. Unlocks:
    kg_world_query (a world), book_scene_get (a derived scene), and the 5 translation-version
    tools (a completed translation of the fixture chapter). These need *state*, not spend —
    the rows model exactly what a user would have, seeded directly because the creator is a
    real (paid/async) job we don't run.
    """
    import uuid

    book, chapter, user = ids.get("book_id"), ids.get("chapter_id"), config.USER_ID
    if not (book and chapter):
        return
    # ── a world owned by the user (book DB) — kg_world_query on an EMPTY world returns
    #    {nodes:[],edges:[]} → executes (a foreign/missing world raises → null). ────────────
    try:
        wid = str(uuid.uuid4())
        # the worlds PK is `id` (kg_world_query's `world_id` arg maps to it).
        oracle.db_query(config.DOMAIN_DB["book"],
                        "INSERT INTO worlds(id, owner_user_id, name) "
                        f"VALUES ('{wid}','{user}','TLE World')")
        ids["world_id"] = wid
    except Exception as e:
        print(f"  (no world seed: {type(e).__name__}: {e})")
    # ── a derived scene on the fixture chapter (book DB) for book_scene_get ────────────────
    try:
        sid = str(uuid.uuid4())
        oracle.db_query(config.DOMAIN_DB["book"],
                        "INSERT INTO scenes(id, book_id, chapter_id, sort_order, path, "
                        "leaf_text, content_hash, lifecycle_state) "
                        f"VALUES ('{sid}','{book}','{chapter}',0,'root','TLE scene text',"
                        "'tlehash','active')")
        ids["scene_id"] = sid
    except Exception as e:
        print(f"  (no scene seed: {type(e).__name__}: {e})")
    # ── a completed translation of the fixture chapter (translation DB) for the 5 version
    #    tools (job_status/job_control/set_active_version/save_edited_version/patch_block) ──
    try:
        jid, vid = str(uuid.uuid4()), str(uuid.uuid4())
        oracle.db_query(_TRANSLATION_DB,
                        "INSERT INTO translation_jobs(job_id, book_id, owner_user_id, "
                        "target_language, model_source, model_ref, system_prompt, "
                        "user_prompt_tpl, chapter_ids, status) "
                        f"VALUES ('{jid}','{book}','{user}','en','user_model','{config.MODEL_REF}',"
                        f"'sys','tpl',ARRAY['{chapter}']::uuid[],'running')")
        oracle.db_query(_TRANSLATION_DB,
                        "INSERT INTO chapter_translations(id, job_id, chapter_id, book_id, "
                        "owner_user_id, target_language, status, version_num, "
                        "translated_body_format, translated_body_json, translated_body, authored_by) "
                        f"VALUES ('{vid}','{jid}','{chapter}','{book}','{user}','en','completed',1,"
                        "'json','[{\"type\":\"paragraph\",\"content\":[]}]'::jsonb,'TLE','llm')")
        ids["translation_job_id"] = jid
        ids["translation_version_id"] = vid
    except Exception as e:
        print(f"  (no translation seed: {type(e).__name__}: {e})")


def seed_chain_extras(ids: dict) -> None:
    """Mint the 2nd-of-a-pair targets the sweep's one-call-per-tool shape can't make inline:
    2 KG nodes (for kg_propose_edge / entity_edge_timeline / triage), and a 2nd composition
    project holding 2 outline nodes + an archived node + a motif (for scene_link / motif_bind /
    outline_node_restore). Everything is book/project-scoped under the fixture book → cleaned by
    the runtime composition/kg teardown. Failures are non-fatal (the consumers just stay null)."""
    from .mcp_direct import MCPDirect

    d = MCPDirect()
    book, chapter, kg = ids.get("book_id"), ids.get("chapter_id"), ids.get("project_id")
    # ── 2 KG nodes (kg_create_node is idempotent Tier-A; returns entity_id) ────────────────
    if kg:
        try:
            a = d.call("kg_create_node", {"name": "TLE Node A", "kind": "character", "project_id": kg})
            b = d.call("kg_create_node", {"name": "TLE Node B", "kind": "character", "project_id": kg})
            ids["kg_node_a"] = a.get("entity_id") or a.get("id")
            ids["kg_node_b"] = b.get("entity_id") or b.get("id")
        except Exception as e:
            print(f"  (no kg-node seed: {type(e).__name__}: {e})")
    # ── a 2nd composition project with 2 nodes + an archived node + a motif ────────────────
    if book and chapter:
        try:
            w = d.call("composition_create_work", {"book_id": book})
            cp = w.get("project_id")
            ids["cproj2"] = cp

            def _node(title: str):
                r = d.call("composition_outline_node_create", {"args": {
                    "project_id": cp, "kind": "chapter", "chapter_id": chapter, "title": title}})
                return r.get("id") or r.get("node_id")

            ids["node_a"] = _node("TLE Node A")
            ids["node_b"] = _node("TLE Node B")
            arch = _node("TLE Archived")
            d.call("composition_outline_node_delete", {"project_id": cp, "node_id": arch})
            ids["node_archived"] = arch  # deleted ⇒ outline_node_restore has something to restore
        except Exception as e:
            print(f"  (no composition-extras seed: {type(e).__name__}: {e})")
        try:
            m = d.call("composition_motif_create", {"args": {"code": "tle-bind", "name": "TLE Bind Motif"}})
            ids["motif_a"] = m.get("id") or m.get("motif_id")
        except Exception as e:
            print(f"  (no motif seed: {type(e).__name__}: {e})")
        # book_chapter_save_draft needs base_version == the current chapter_drafts.draft_version.
        try:
            dv = oracle.db_query(config.DOMAIN_DB["book"],
                                 f"SELECT draft_version FROM chapter_drafts WHERE chapter_id='{chapter}'")
            ids["draft_version"] = int(dv.strip()) if dv and dv.strip().lstrip("-").isdigit() else 0
        except Exception:
            ids["draft_version"] = 0


def teardown_db_fixtures(ids: dict) -> dict:
    """Delete every row seed_db_fixtures created (the world isn't book-CASCADEd; translation
    rows live in a different DB) — 'destroy what I created', both ways."""
    out: dict = {}
    wid = ids.get("world_id")
    if wid:
        try:
            oracle.db_query(config.DOMAIN_DB["book"], f"DELETE FROM worlds WHERE id='{wid}'")
            out["world"] = "ok"
        except Exception as e:
            out["world"] = f"FAILED: {e}"
    jid = ids.get("translation_job_id")
    if jid:
        # child (chapter_translations) before parent (translation_jobs); both key on job_id.
        for tbl in ("chapter_translations", "translation_jobs"):
            try:
                oracle.db_query(_TRANSLATION_DB, f"DELETE FROM {tbl} WHERE job_id='{jid}'")
            except Exception as e:
                out[tbl] = f"FAILED: {e}"
        out.setdefault("translation", "ok")
    # the seeded motif is USER-scoped (book_id NULL) → NOT cleaned by the book-scoped
    # composition teardown; delete it by its owner+code so it doesn't accumulate per run.
    try:
        oracle.db_query(config.DOMAIN_DB["composition"],
                        f"DELETE FROM motif WHERE owner_user_id='{config.USER_ID}' AND code='tle-bind'")
        out["motif"] = "ok"
    except Exception as e:
        out["motif"] = f"FAILED: {e}"
    return out  # scenes are book-scoped → CASCADE-deleted with the book by fx.teardown()


def teardown_composition(book_id: str) -> dict:
    """Delete EVERY composition row under the throwaway book, and verify none survive.

    A hardcoded table list is the wrong tool here: the sweep calls Tier-W tools that write
    rows I did not anticipate (the first version listed 5 tables and leaked a `generation_job`
    row per run — the exact trap this cleanup exists to prevent). So discover every
    book-scoped table at runtime from information_schema, and delete from all of them.

    Order-agnostic by RETRY: an FK-child row can block a parent delete, so pass over the
    tables a few times — once a child is gone, the next pass clears its parent. Converges
    without hardcoding dependency order. Scoped strictly to the created book id.
    """
    if not book_id or config.KEEP_FIXTURES:
        return {"kept": True}
    bid = str(book_id).replace("'", "''")
    db = config.DOMAIN_DB["composition"]
    try:
        tables = [r[0] for r in oracle.db_query(
            db, "SELECT table_name FROM information_schema.columns "
                "WHERE column_name='book_id' AND table_schema='public'")]
    except Exception as e:
        return {"discover": f"FAILED ({type(e).__name__})"}
    for _ in range(3):  # FK depth in composition is shallow; 3 passes clears it
        for table in tables:
            try:
                oracle.db_query(db, f"DELETE FROM {table} WHERE book_id='{bid}'")
            except Exception:  # FK-blocked this pass — a later pass clears it
                pass
    # Verify completeness — a surviving row is a leak, and silence would hide it.
    leaked = {}
    for table in tables:
        try:
            n = int(oracle.scalar(db, f"SELECT count(*) FROM {table} WHERE book_id='{bid}'") or 0)
            if n:
                leaked[table] = n
        except Exception:
            pass
    return {"tables": len(tables), "leaked": leaked} if leaked else {"tables": len(tables), "clean": True}

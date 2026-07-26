"""A throwaway USER, so the 25 user-scoped Tier-A writes can finally be exercised.

`_meta.scope` unlocked the 58 book/project-scoped writes: they can only touch the throwaway
book we hand them. The 25 `user`/`none`-scoped writes have no such handle — they mutate
*the caller*. `settings_update_profile` rewrites the profile; `glossary_user_create` adds a
user-tier kind; `registry_propose_skill` files a proposal. Against the real test account
that is vandalism, so they were never called.

That is precisely where the bug lived. `settings_update_profile` carried the same
`json.RawMessage` output-schema break as `settings_get_profile` and failed 100% of calls —
found by *reasoning from the root cause*, because nothing could call it. This module is how
we stop needing to be lucky.

The fixture is a REAL registered user (the MCP internal-token envelope carries
`X-User-Id`, but the downstream services resolve a real row — an invented UUID fails at
auth-service). Teardown deletes only rows keyed to the id we created.
"""
from __future__ import annotations

import uuid

import httpx

from . import config, oracle

_PASSWORD = "TleSweep@2026"

# Where a throwaway user's rows actually land — enumerated from
# information_schema, not guessed. Each entry is (db, table, owner column). Deletion is
# scoped to the created user id; never a broader predicate.
#
# Ordered so children die before parents (proposals before skills/workflows;
# user_default_models + user_models before provider_credentials — FK child first).
_OWNED_ROWS: tuple[tuple[str, str, str], ...] = (
    ("knowledge", "knowledge_projects", "user_id"),
    ("glossary", "user_kinds", "owner_user_id"),
    ("glossary", "user_attributes", "owner_user_id"),
    ("glossary", "user_genres", "owner_user_id"),
    ("agent_registry", "skill_proposals", "owner_user_id"),
    ("agent_registry", "workflow_proposals", "owner_user_id"),
    ("agent_registry", "skills", "owner_user_id"),
    ("agent_registry", "workflows", "owner_user_id"),
    ("composition", "motif", "owner_user_id"),
    ("provider_registry", "user_default_models", "owner_user_id"),
    ("provider_registry", "user_models", "owner_user_id"),
    ("provider_registry", "provider_credentials", "owner_user_id"),
)


class UserFixture:
    """A registered throwaway user. Build, sweep as them, tear down."""

    def __init__(self) -> None:
        self.run_id = uuid.uuid4().hex[:8]
        self.email = f"tle-sweep-{self.run_id}@loreweave.test"
        self.user_id: str | None = None
        # Seeded so the 6 credential-gated tools are reachable (see _seed_provider_model).
        self.credential_id: str | None = None
        self.user_model_id: str | None = None
        # Seeded so the registry read/edit tools are reachable (see _seed_registry).
        self.skill_slug: str | None = None
        self.workflow_slug: str | None = None

    def build(self) -> "UserFixture":
        r = httpx.post(
            f"{config.GATEWAY}/v1/auth/register",
            json={"email": self.email, "password": _PASSWORD, "display_name": "TLE Sweep"},
            timeout=20,
        )
        r.raise_for_status()
        self.user_id = r.json()["user_id"]
        self._seed_provider_model()
        self._seed_registry()
        self._seed_motif_pair()
        return self

    def _seed_motif_pair(self) -> None:
        """Two user-tier motifs so composition_motif_link_create/_delete reach: a link needs
        BOTH endpoints to be the caller's own motifs, and the sweep's one motif_create can mint
        only one. book_id NULL ⇒ user-tier (no shared-book gate). Cleaned by _OWNED_ROWS (motif)."""
        self.motif_link_a = str(uuid.uuid4())
        self.motif_link_b = str(uuid.uuid4())
        db = config.DOMAIN_DB["composition"]
        for mid, code in ((self.motif_link_a, "tle-linkA"), (self.motif_link_b, "tle-linkB")):
            oracle.db_query(db,
                "INSERT INTO motif(id, owner_user_id, code, name) "
                f"VALUES ('{mid}','{self.user_id}','{code}','TLE {code}')")

    def _seed_registry(self) -> None:
        """Seed one PUBLISHED skill + workflow so the registry read/edit tools are reachable.

        `registry_get_skill` / `_update_skill` / `_set_skill_enabled` / `registry_get_workflow`
        operate on an APPROVED (`skills`/`workflows`) row by slug — a *proposal*
        (`registry_propose_skill`, which the throwaway user CAN call) is not retrievable that
        way, so nothing ever reached these four. Seeding a published row (a real state — the
        `status` column defaults `published`) directly is the same buildable-fixture move as
        the keyless credential above; the rows are torn down by `_OWNED_ROWS`.
        """
        self.skill_slug = f"tle-skill-{self.run_id}"
        self.workflow_slug = f"tle-wf-seed-{self.run_id}"
        db = config.DOMAIN_DB["agent_registry"]
        oracle.db_query(db,
            "INSERT INTO skills(owner_user_id, tier, slug, description, status) "
            f"VALUES ('{self.user_id}','user','{self.skill_slug}','TLE seeded skill','published')")
        oracle.db_query(db,
            "INSERT INTO workflows(owner_user_id, tier, slug) "
            f"VALUES ('{self.user_id}','user','{self.workflow_slug}')")

    def _seed_provider_model(self) -> None:
        """Seed a KEYLESS provider credential + one model row for the throwaway user.

        The 6 credential-gated tools (`settings_provider_inventory` and the five
        `settings_model_*` writes) all require a `provider_credential_id` or a
        `user_model_id`. A model in the agent loop cannot MINT a credential — that needs a
        secret entered in the Settings UI, and OD-S1 forbids a secret being an LLM-visible
        tool arg. So nothing in the tool surface can create one, and the tools were never
        reachable by the sweep. That is not "the tool is broken" and not "unreachable by
        design" — it is missing *fixture* state, which is buildable (CLAUDE.md's
        anti-laziness rule). The credential is keyless (secret_ciphertext NULL) — a real
        production state (a provider added but no key yet); every one of these 6 tools is a
        METADATA op that never reads the secret, so a keyless row exercises them faithfully.
        """
        self.credential_id = str(uuid.uuid4())
        self.user_model_id = str(uuid.uuid4())
        db = config.DOMAIN_DB["provider_registry"]
        oracle.db_query(db,
            "INSERT INTO provider_credentials"
            "(provider_credential_id, owner_user_id, provider_kind, display_name, status) "
            f"VALUES ('{self.credential_id}','{self.user_id}','lm_studio',"
            "'TLE Sweep (keyless)','active')")
        oracle.db_query(db,
            "INSERT INTO user_models"
            "(user_model_id, owner_user_id, provider_credential_id, provider_kind, "
            " provider_model_name, capability_flags) "
            f"VALUES ('{self.user_model_id}','{self.user_id}','{self.credential_id}',"
            "'lm_studio','tle-sweep-model','{\"embedding\": true}'::jsonb)")

    def headers(self) -> dict:
        assert self.user_id, "build() first"
        return {
            "X-Internal-Token": config.INTERNAL_TOKEN,
            "X-User-Id": self.user_id,
            "X-Session-Id": f"tle-user-sweep-{self.run_id}",
        }

    def teardown(self) -> dict:
        """Delete every row keyed to the user we created, then the user itself.

        Best-effort per table: a table that does not exist in this deployment must not
        abort the rest of the cleanup, or one schema drift leaks every other row.
        """
        if not self.user_id or config.KEEP_FIXTURES:
            return {"kept": True, "user_id": self.user_id}
        uid = self.user_id.replace("'", "''")
        deleted: dict[str, str] = {}
        for db, table, col in _OWNED_ROWS:
            try:
                oracle.db_query(config.DOMAIN_DB[db], f"DELETE FROM {table} WHERE {col}='{uid}'")
                deleted[table] = "ok"
            except Exception as e:  # table absent in this deployment, or no perms
                deleted[table] = f"skip ({type(e).__name__})"
        try:
            oracle.db_query(config.DOMAIN_DB["auth"], f"DELETE FROM users WHERE id='{uid}'")
            deleted["users"] = "ok"
        except Exception as e:
            deleted["users"] = f"FAILED ({e})"
        return {"user_id": self.user_id, **deleted}


# ── Authored args for the user-scoped writes ────────────────────────────────────
#
# These cannot be filled from a fixture the way `book_id` can — they are free-form or
# reference rows the throwaway user does not have. Authoring them is the only way to
# exercise the tool at all. A tool absent from this map stays `executes: null`, which
# blocks nothing.
#
# `settings_update_profile` is the one that matters most: its `required` is EMPTY, so a
# required-args-only call returns "no fields to update" and proves nothing. It needs an
# optional field supplied on purpose. That is the tool whose twin was broken.
# Tools that must run in this order: a later one consumes what an earlier one created.
# Anything not listed keeps catalog order.
USER_SWEEP_ORDER: tuple[str, ...] = (
    "settings_update_profile",
    "kg_project_create",
    "kg_view_upsert",           # needs the project above
    "kg_view_delete",           # needs the view above
    "glossary_user_create",     # mints a kind `code` + `base_version`
    "glossary_user_patch",      # ← consumes them
    "glossary_user_delete",     # ← soft-delete (reversible)
    "glossary_user_restore",    # ← undo, leaving the world as we found it
    # credential-gated: all reference the seeded credential / model (see _seed_provider_model).
    "settings_provider_inventory",  # R — lists the seeded credential's (empty) inventory
    "settings_model_register",      # A — registers a 2nd model against the seeded credential
    "settings_model_update",        # A — edits the seeded model
    "settings_model_set_favorite",  # A — flips is_favorite on the seeded model
    "settings_model_set_active",    # A — flips is_active on the seeded model
    "settings_model_delete",        # W — mints a delete token (writes nothing; never redeemed)
    # motif chain: create mints a motif_id (+ version) the rest consume; archive LAST since
    # it changes state the reads/patch above depend on.
    "composition_motif_create",
    "composition_motif_get",
    "composition_motif_link_list",
    "composition_motif_patch",
    "composition_motif_adopt",
    "composition_motif_link_create",   # links the 2 seeded motifs → mints link.id
    "composition_motif_link_delete",   # ← consumes it
    "composition_motif_archive",
    "registry_propose_skill",
    "registry_propose_workflow",
    # registry read/edit against the seeded published skill/workflow (see _seed_registry)
    "registry_get_skill",
    "registry_update_skill",
    "registry_set_skill_enabled",
    "registry_get_workflow",
    "registry_update_workflow",
    # jobs facade: a missing/foreign job returns a structured not-found dict (NOT a raise),
    # so a synthetic job_id reaches `executes` without seeding a real job.
    "jobs_get",
    "jobs_cancel",
    "jobs_pause",
)

# A syntactically-valid job_id the caller never created — jobs_* resolve it to a
# not-found *dict* (executes:True), never touching real data.
_FAKE_JOB_ID = "00000000-0000-4000-8000-000000000001"


def authored_user_args(tool: str, fx: UserFixture, state: dict) -> dict | None:
    """`state` holds the RESULT of every earlier successful call in this sweep.

    Chaining is the only way to reach `glossary_user_patch` / `_delete` / `_restore`: they
    need a `code` + `base_version` that only `glossary_user_create` can mint. A fixture
    cannot invent a row the tool itself is supposed to make.
    """
    kind = state.get("glossary_user_create") or {}
    motif = state.get("composition_motif_create") or {}
    motif_id = motif.get("id") or motif.get("motif_id")
    motif_ver = motif.get("version")
    match tool:
        case "settings_update_profile":
            # required=[] — a required-only call is a no-op ("no fields to update") and
            # proves nothing. Supply an optional field on purpose. THIS is the tool whose
            # twin (settings_get_profile) was broken; it must actually be exercised.
            return {"display_name": f"TLE Sweep {fx.run_id}"}
        case "kg_project_create":
            return {"name": f"TLE-user-sweep-{fx.run_id}", "project_type": "general"}
        case "kg_view_upsert":
            proj = (state.get("kg_project_create") or {}).get("project_id")
            if not proj:
                return None
            return {"project_id": proj, "code": f"tle_{fx.run_id}", "name": "TLE view"}
        case "kg_view_delete":
            proj = (state.get("kg_project_create") or {}).get("project_id")
            if not proj or "kg_view_upsert" not in state:
                return None
            return {"project_id": proj, "code": f"tle_{fx.run_id}"}
        case "glossary_user_create":
            # `level` is enum ['genre','kind','attribute'] — a user-tier custom kind.
            return {"level": "kind", "name": f"TLE Kind {fx.run_id}"}
        case "glossary_user_patch":
            if not kind.get("code"):
                return None
            args = {"level": "kind", "code": kind["code"], "description": "patched by TLE sweep"}
            if kind.get("base_version"):
                args["base_version"] = kind["base_version"]  # 409 on drift, per the tool
            return args
        case "glossary_user_delete":
            return {"level": "kind", "code": kind["code"]} if kind.get("code") else None
        case "glossary_user_restore":
            # soft-delete is reversible — restore, so the throwaway user's kinds are the
            # same before and after. (They are deleted with the user anyway; leaving the
            # world as we found it is the habit, not the necessity.)
            return {"level": "kind", "code": kind["code"]} if kind.get("code") else None
        case "settings_model_set_default":
            # `capability` is a closed set the schema does not declare — the tool told us:
            # "unsupported capability (want one of: rerank, embedding, chat...)". Omitting
            # `model_ref` CLEARS the default, which the throwaway user does not have.
            return {"capability": "embedding"}
        # ── credential-gated: use the seeded credential / model ──────────────────
        case "settings_provider_inventory":
            return {"provider_credential_id": fx.credential_id} if fx.credential_id else None
        case "settings_model_register":
            if not fx.credential_id:
                return None
            # context_length is optional in the SCHEMA but REQUIRED by the tool for
            # ollama/lm_studio providers (which the seeded credential is). Supplying it is
            # honest — a real caller registering an lm_studio model must provide it too.
            return {"provider_credential_id": fx.credential_id,
                    "provider_model_name": f"tle-sweep-registered-{fx.run_id}",
                    "context_length": 8192}
        case "settings_model_update":
            return {"user_model_id": fx.user_model_id, "alias": f"TLE renamed {fx.run_id}"} \
                if fx.user_model_id else None
        case "settings_model_set_favorite":
            return {"user_model_id": fx.user_model_id, "value": True} if fx.user_model_id else None
        case "settings_model_set_active":
            return {"user_model_id": fx.user_model_id, "value": True} if fx.user_model_id else None
        case "settings_model_delete":
            # Tier W: mints a confirm_token + preview, writes NOTHING. We never redeem it, so
            # the seeded model survives to be cleaned up by teardown.
            return {"user_model_id": fx.user_model_id} if fx.user_model_id else None
        # ── motif chain: create mints the motif_id (+ version) the rest consume ───
        case "composition_motif_create":
            # args.required = [code, name]; both author-supplied (a motif `code` is the NEW
            # code being minted, not a lookup — which is why fill_args, blind to intent,
            # refused it).
            return {"args": {"code": f"tle-motif-{fx.run_id}", "name": f"TLE Motif {fx.run_id}"}}
        case "composition_motif_get" | "composition_motif_link_list":
            return {"motif_id": motif_id} if motif_id else None
        case "composition_motif_patch":
            if not motif_id:
                return None
            a = {"motif_id": motif_id, "summary": "patched by TLE sweep"}
            if motif_ver is not None:
                a["expected_version"] = motif_ver  # required; 409 on drift
            return {"args": a}
        case "composition_motif_adopt":
            return {"args": {"motif_id": motif_id}} if motif_id else None  # W: mints a token
        case "composition_motif_archive":
            return {"motif_id": motif_id} if motif_id else None
        # ── registry read/edit: use the seeded published skill / workflow ────────
        case "registry_get_skill":
            return {"slug": fx.skill_slug} if fx.skill_slug else None
        case "registry_update_skill":
            return {"slug": fx.skill_slug, "body_md": "# TLE\nupdated by the sweep"} \
                if fx.skill_slug else None
        case "registry_set_skill_enabled":
            return {"slug": fx.skill_slug, "enabled": True} if fx.skill_slug else None
        case "registry_get_workflow":
            return {"slug": fx.workflow_slug} if fx.workflow_slug else None
        case "registry_update_workflow":
            return {"slug": fx.workflow_slug, "title": "TLE workflow v2",
                    "description": "Updated by the TLE capability sweep.",
                    "steps": [{"id": "step-one", "tool": "book_list", "gate": "none"}]} \
                if fx.workflow_slug else None
        case "registry_propose_skill":
            return {
                "slug": f"tle-sweep-{fx.run_id}",
                "description": "Throwaway skill proposed by the TLE capability sweep.",
                "body_md": "# TLE sweep\nThis proposal is deleted with its owner.",
            }
        case "registry_propose_workflow":
            # `book_list` is a PROVEN tool, so the CD4 ship gate admits this step without a
            # warning. An unproven tool would still be admitted (warn only); a
            # proven-broken one would be REJECTED — which is the gate working.
            return {
                "slug": f"tle-wf-{fx.run_id}",
                "title": "TLE sweep workflow",
                "description": "Throwaway workflow proposed by the TLE capability sweep.",
                "surfaces": ["chat"],
                "steps": [{"id": "step-one", "tool": "book_list", "gate": "none"}],
            }
        case "composition_motif_link_create":
            # link the 2 seeded user-tier motifs (book_id omitted ⇒ user graph); mints link.id.
            a, b = getattr(fx, "motif_link_a", None), getattr(fx, "motif_link_b", None)
            return {"args": {"from_motif_id": a, "to_motif_id": b, "kind": "variant_of"}} \
                if (a and b) else None
        case "composition_motif_link_delete":
            lid = (state.get("composition_motif_link_create") or {}).get("id") \
                or (state.get("composition_motif_link_create") or {}).get("link_id")
            return {"link_id": lid} if lid else None
        case "jobs_get":
            return {"service": "composition", "job_id": _FAKE_JOB_ID}
        case "jobs_cancel":
            return {"service": "translation", "job_id": _FAKE_JOB_ID}
        case "jobs_pause":
            return {"service": "knowledge", "job_id": _FAKE_JOB_ID}
        case _:
            return None  # needs state we do not have (a motif, a job, a credential)

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
# Ordered so children die before parents (proposals before skills/workflows).
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
)


class UserFixture:
    """A registered throwaway user. Build, sweep as them, tear down."""

    def __init__(self) -> None:
        self.run_id = uuid.uuid4().hex[:8]
        self.email = f"tle-sweep-{self.run_id}@loreweave.test"
        self.user_id: str | None = None

    def build(self) -> "UserFixture":
        r = httpx.post(
            f"{config.GATEWAY}/v1/auth/register",
            json={"email": self.email, "password": _PASSWORD, "display_name": "TLE Sweep"},
            timeout=20,
        )
        r.raise_for_status()
        self.user_id = r.json()["user_id"]
        return self

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
    "registry_propose_skill",
    "registry_propose_workflow",
)


def authored_user_args(tool: str, fx: UserFixture, state: dict) -> dict | None:
    """`state` holds the RESULT of every earlier successful call in this sweep.

    Chaining is the only way to reach `glossary_user_patch` / `_delete` / `_restore`: they
    need a `code` + `base_version` that only `glossary_user_create` can mint. A fixture
    cannot invent a row the tool itself is supposed to make.
    """
    kind = state.get("glossary_user_create") or {}
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
        case _:
            return None  # needs state we do not have (a motif, a job, a credential)

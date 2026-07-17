"""Canon rules + templates router (§5).

Reuses the M2 CanonRulesRepo (If-Match → 412, soft-archive on DELETE). CR4: a
`from_order > until_order` window is a typo — validated at the router (400),
never persisted. GET /templates lists built-in + the user's structure templates.
Access is the E0 book grant (25 PM-8): VIEW for reads, EDIT for writes, gated
BEFORE any repo call; by-id routes resolve the rule's scope first and gate on
ITS book.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.db.models import RuleScope
from app.db.pool import get_pool
from app.db.repositories import VersionMismatchError
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.structure_templates import (
    DuplicateStructureTemplateName,
    StructureTemplatesRepo,
    StructureTemplateVersionConflict,
)
from app.db.repositories.works import WorksRepo
from app.deps import (get_canon_rules_repo, get_grant_client_dep,
                      get_structure_templates_repo, get_works_repo)
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError

router = APIRouter(prefix="/v1/composition")


class CanonRuleCreate(BaseModel):
    text: str
    scope: RuleScope = "world"
    entity_id: UUID | None = None
    from_order: int | None = None
    until_order: int | None = None
    kind: str | None = None


class CanonRulePatch(BaseModel):
    text: str | None = None
    scope: RuleScope | None = None
    entity_id: UUID | None = None
    from_order: int | None = None
    until_order: int | None = None
    kind: str | None = None
    active: bool | None = None


def _validate_window(from_order: int | None, until_order: int | None) -> None:
    """CR4: reject an inverted reveal window (author typo) → 400."""
    if from_order is not None and until_order is not None and from_order > until_order:
        raise HTTPException(status_code=400, detail={
            "code": "CANON_WINDOW_INVERTED", "from_order": from_order, "until_order": until_order})


def _parse_if_match(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.strip().strip('"'))
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    """E0-4c book-grant chokepoint → HTTP (mirrors works._gate_book). none→404
    (no oracle), under-tier→403."""
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="work not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


async def _require_work(
    works: WorksRepo, grant: GrantClient, user_id: UUID, project_id: UUID,
    need: GrantLevel,
) -> None:
    """Resolve the Work by project (un-user-scoped — 25 PM-9) and gate the
    caller's E0 grant on its book (PM-8: access is decided HERE, never in the
    repos)."""
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    await _gate_book(grant, work.book_id, user_id, need)


async def _rule_project_id(rule_id: UUID) -> UUID:
    """PM-8 scope-bootstrap for the by-id routes (`/canon-rules/{rule_id}` has no
    project in the path): the ids-only `project_id` of a rule, un-scoped —
    mirrors works.scope_meta's anti-oracle read (ids or 404, never row content).
    The grant is then gated on THAT project's book, so the gate can never check
    a different book than the row mutated."""
    row = await get_pool().fetchrow(
        "SELECT project_id FROM canon_rule WHERE id = $1", rule_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="canon rule not found")
    return row["project_id"]


@router.get("/works/{project_id}/canon-rules")
async def list_canon_rules(
    project_id: UUID,
    active_only: bool = False,
    include_archived: bool = False,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """List canon rules for management. `active_only` = enforceable only (the
    critic's set). `include_archived` (BE-11b) also returns soft-archived rows so
    the UI can list them under a section and Restore one (mutually exclusive with
    active_only, which is already a NOT-archived subset)."""
    await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    rules = await (canon.list_active(project_id) if active_only
                   else canon.list_all(project_id, include_archived=include_archived))
    return {"rules": [r.model_dump(mode="json") for r in rules]}


@router.post("/works/{project_id}/canon-rules", status_code=201)
async def create_canon_rule(
    project_id: UUID,
    body: CanonRuleCreate,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    _validate_window(body.from_order, body.until_order)
    rule = await canon.create(project_id, body.text, scope=body.scope,
                              entity_id=body.entity_id, from_order=body.from_order,
                              until_order=body.until_order, kind=body.kind,
                              created_by=user_id)
    return rule.model_dump(mode="json")


@router.patch("/canon-rules/{rule_id}")
async def patch_canon_rule(
    rule_id: UUID,
    body: CanonRulePatch,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    # By-id route: resolve the rule's scope from the ROW ITSELF, gate on ITS book.
    project_id = await _rule_project_id(rule_id)
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    patch = body.model_dump(exclude_unset=True)
    # CR4 on the EFFECTIVE window after the patch — need the current row when the
    # patch sets only one bound.
    if "from_order" in patch or "until_order" in patch:
        current = await canon.get(project_id, rule_id)
        if current is None:
            raise HTTPException(status_code=404, detail="canon rule not found")
        fo = patch.get("from_order", current.from_order)
        uo = patch.get("until_order", current.until_order)
        _validate_window(fo, uo)
    try:
        rule = await canon.update(project_id, rule_id, patch,
                                  expected_version=_parse_if_match(if_match))
    except VersionMismatchError as exc:
        raise HTTPException(status_code=412, detail={"code": "CANON_VERSION_CONFLICT",
                                                     "current": exc.current.model_dump(mode="json")})
    if rule is None:
        raise HTTPException(status_code=404, detail="canon rule not found")
    return rule.model_dump(mode="json")


@router.delete("/canon-rules/{rule_id}", status_code=200)
async def delete_canon_rule(
    rule_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    # By-id route: resolve the rule's scope from the ROW ITSELF, gate on ITS book.
    project_id = await _rule_project_id(rule_id)
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    rule = await canon.archive(project_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="canon rule not found")
    return rule.model_dump(mode="json")


@router.post("/canon-rules/{rule_id}/restore", status_code=200)
async def restore_canon_rule(
    rule_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """BE-11 — un-archive a soft-deleted canon rule: the UNDO the DELETE already promises.

    `list_all` filters `NOT is_archived`, so an archived rule is unlistable — but
    `DELETE /canon-rules/{rule_id}` returns the archived row (id included), so the FE holds
    the id and renders "Rule deleted · Undo" → here. Reachability is that toast, not an
    archive browser.

    EDIT gate (restore mutates), resolved from the ROW's project — the by-id routes carry
    no project in the path, so the gate can never check a different book than the row
    mutated. No If-Match: an archived row has no concurrent editor to race.
    """
    project_id = await _rule_project_id(rule_id)
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    rule = await canon.restore(project_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="canon rule not found or not archived")
    return rule.model_dump(mode="json")


@router.get("/templates")
async def list_templates(
    include_archived: bool = False,
    user_id: UUID = Depends(get_current_user),
    templates: StructureTemplatesRepo = Depends(get_structure_templates_repo),
) -> dict[str, Any]:
    rows = await templates.list_for_user(user_id, include_archived=include_archived)
    return {"templates": [t.model_dump(mode="json") for t in rows]}


# ── S-01 · custom structure-template authoring (per-USER; no book/project scope) ──


class StructureTemplateCreate(BaseModel):
    name: str
    kind: str = "generic"  # free-text label (S-01 CV-1), NOT an enum
    beats: list[dict[str, Any]] = []


class StructureTemplateUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    beats: list[dict[str, Any]] | None = None


class StructureTemplateClone(BaseModel):
    name: str | None = None  # default "<src> (copy)"


def _dup_409(exc: DuplicateStructureTemplateName) -> HTTPException:
    return HTTPException(status_code=409, detail=f"you already have a structure named '{exc}'")


@router.post("/templates", status_code=201)
async def create_template(
    body: StructureTemplateCreate,
    user_id: UUID = Depends(get_current_user),
    templates: StructureTemplatesRepo = Depends(get_structure_templates_repo),
) -> dict[str, Any]:
    try:
        t = await templates.create(user_id, name=body.name, kind=body.kind, beats=body.beats)
    except DuplicateStructureTemplateName as e:
        raise _dup_409(e)
    return t.model_dump(mode="json")


@router.post("/templates/{template_id}/clone", status_code=201)
async def clone_template(
    template_id: UUID,
    body: StructureTemplateClone,
    user_id: UUID = Depends(get_current_user),
    templates: StructureTemplatesRepo = Depends(get_structure_templates_repo),
) -> dict[str, Any]:
    """Slice-B entry point: copy a built-in (or any visible template) into the user's own tier."""
    try:
        t = await templates.clone_builtin(user_id, template_id, name=body.name)
    except LookupError:
        raise HTTPException(status_code=404, detail="structure template not found")
    except DuplicateStructureTemplateName as e:
        raise _dup_409(e)
    return t.model_dump(mode="json")


@router.patch("/templates/{template_id}")
async def patch_template(
    template_id: UUID,
    body: StructureTemplateUpdate,
    user_id: UUID = Depends(get_current_user),
    templates: StructureTemplatesRepo = Depends(get_structure_templates_repo),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    if if_match is None:
        raise HTTPException(status_code=428, detail="If-Match (version) required")
    try:
        expected = int(if_match.strip('"'))
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")
    patch = body.model_dump(exclude_unset=True)
    try:
        t = await templates.update(user_id, template_id, expected, **patch)
    except StructureTemplateVersionConflict:
        raise HTTPException(status_code=412, detail="structure template was modified; reload")
    except DuplicateStructureTemplateName as e:
        raise _dup_409(e)
    if t is None:
        # Not the user's own row (a built-in write, or another user's, or gone). Built-ins are
        # read-only to users — clone first (S-01 §3).
        raise HTTPException(status_code=404, detail="no editable structure template with that id")
    return t.model_dump(mode="json")


@router.delete("/templates/{template_id}", status_code=204)
async def archive_template(
    template_id: UUID,
    user_id: UUID = Depends(get_current_user),
    templates: StructureTemplatesRepo = Depends(get_structure_templates_repo),
) -> None:
    t = await templates.archive(user_id, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="no active structure template with that id")


@router.post("/templates/{template_id}/restore")
async def restore_template(
    template_id: UUID,
    user_id: UUID = Depends(get_current_user),
    templates: StructureTemplatesRepo = Depends(get_structure_templates_repo),
) -> dict[str, Any]:
    t = await templates.restore(user_id, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="no archived structure template with that id")
    return t.model_dump(mode="json")

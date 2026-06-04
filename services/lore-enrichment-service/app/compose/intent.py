"""Mode-B intent resolver (Compose slice 4).

ONE LLM call: given a free-text intent + the book's entity list (names+kinds) + the
book profile, propose a target (existing|new + canonical_name + entity_kind),
dimensions, technique, and a short rationale. Strict-JSON, tolerantly parsed.

NO job is created here (F5): the resolver is the first half of a 2-step flow. The FE
shows the resolved target, lets the author EDIT/CONFIRM, then submits a normal
/compose — so a mis-resolved target is never silently enriched.

Book-aware (de-bias C1): the prompt instructs the model to fit the book's
worldview/language, and the LLM seam is resolved by model_ref (NO model name).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.db.book_profile import NEUTRAL_PROFILE, BookProfile
from app.gaps.model import is_zh
from app.generation.generate import CompleteFn
from app.strategies.base import StrategyContext

logger = logging.getLogger("lore_enrichment.compose.intent")

#: The resolver only ever proposes canon-safe techniques (no recook/compose_draft —
#: those are author-driven modes, not an intent guess). Default = fabrication
#: (canon-grounded invention) unless the model explicitly asks for retrieval.
_ALLOWED_TECHNIQUES = {"retrieval", "fabrication"}
_DEFAULT_TECHNIQUE = "fabrication"


class IntentResolutionError(RuntimeError):
    """The resolver could not produce a usable target from the model output."""


@dataclass(frozen=True)
class ResolvedIntent:
    target_mode: str  # "existing" | "new"
    canonical_name: str
    entity_kind: str
    dimensions: list[str]
    technique: str
    rationale: str

    def as_dict(self) -> dict:
        return {
            "target": {
                "mode": self.target_mode,
                "canonical_name": self.canonical_name,
                "entity_kind": self.entity_kind,
            },
            "dimensions": self.dimensions,
            "technique": self.technique,
            "rationale": self.rationale,
        }


def build_intent_prompt(intent_text: str, entities: list[dict], profile: BookProfile) -> str:
    """Build the resolver prompt: the intent + the book's entities + the JSON schema.
    Bilingual by profile.language; worldview interpolated. entities = [{name, kind}]."""
    entity_lines = "\n".join(f"- {e.get('name', '')} [{e.get('kind', '')}]" for e in entities[:200])
    worldview = (profile.worldview or "").strip()
    schema = (
        '{"target":{"mode":"existing|new","canonical_name":"…","entity_kind":"…"},'
        '"dimensions":["…"],"technique":"retrieval|fabrication","rationale":"…"}'
    )
    if is_zh(profile.language):
        wv = f"本书世界观：{worldview}\n" if worldview else ""
        return (
            f"{wv}作者意图：{intent_text}\n\n"
            f"已有实体（名称 [类型]）：\n{entity_lines or '（无）'}\n\n"
            "请判断该意图指向哪个实体：若是上表中的已有实体，mode=existing 并使用其确切"
            "名称与类型；否则 mode=new 并拟定一个贴合世界观的名称与类型（character/"
            "location/item/faction/event/generic 之一）。给出建议补全的维度、技术"
            "（retrieval 有据可循 / fabrication 据设定创作）与简短理由。\n"
            f"仅输出一个 JSON 对象：{schema}"
        )
    wv = f"Book worldview: {worldview}\n" if worldview else ""
    return (
        f"{wv}Author intent: {intent_text}\n\n"
        f"Existing entities (name [kind]):\n{entity_lines or '(none)'}\n\n"
        "Decide which entity this intent targets: if it matches an existing entity above, "
        "set mode=existing and use its EXACT name and kind; otherwise mode=new and propose a "
        "worldview-fitting name and kind (one of character/location/item/faction/event/generic). "
        "Suggest the dimensions to fill, the technique (retrieval = grounded, fabrication = "
        "canon-grounded invention), and a short rationale.\n"
        f"Output ONLY one JSON object: {schema}"
    )


def _extract_json(text: str) -> dict:
    """Tolerantly pull the first JSON object out of the model text (handles ```json
    fences / surrounding prose). Raises IntentResolutionError on no parseable object."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise IntentResolutionError("no JSON object in resolver output")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise IntentResolutionError(f"resolver output is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise IntentResolutionError("resolver JSON is not an object")
    return data


async def resolve_intent(
    *,
    complete: CompleteFn,
    intent_text: str,
    entities: list[dict],
    profile: BookProfile = NEUTRAL_PROFILE,
    user_id: str,
    project_id: str,
    model_ref: str,
) -> ResolvedIntent:
    """Resolve a free-text intent into a proposed target+dims+technique (one LLM call)."""
    prompt = build_intent_prompt(intent_text, entities, profile)
    ctx = StrategyContext(user_id=user_id, project_id=project_id, model_ref=model_ref, profile=profile)
    raw = await complete(prompt, ctx)
    data = _extract_json(raw)

    target = data.get("target") if isinstance(data.get("target"), dict) else {}
    mode = target.get("mode") if target.get("mode") in ("existing", "new") else "new"
    name = str(target.get("canonical_name") or "").strip()
    kind = str(target.get("entity_kind") or "generic").strip() or "generic"
    dims = [d for d in (data.get("dimensions") or []) if isinstance(d, str) and d.strip()]
    tech = data.get("technique") if data.get("technique") in _ALLOWED_TECHNIQUES else _DEFAULT_TECHNIQUE
    rationale = str(data.get("rationale") or "").strip()
    if not name:
        raise IntentResolutionError("resolver did not return a canonical_name")
    return ResolvedIntent(
        target_mode=mode, canonical_name=name, entity_kind=kind,
        dimensions=dims, technique=tech, rationale=rationale,
    )

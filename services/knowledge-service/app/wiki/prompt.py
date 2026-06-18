"""Wiki generation — the constrained-Markdown prompt builder (wiki-llm M3 / §C2).

Pure: turns the per-entity context (M2 brief + cite-labelled sources) and the
book's de-bias profile (M1) into the chat `messages` the LLM answers. The LLM is
the ONLY component that emits free text, and it emits a SMALL fixed Markdown
subset the M0 parser understands — never JSON/TipTap.

The cite labels are OURS: every source is handed to the LLM pre-labelled
``[P1]``/``[G1]``/``[K1]``; the model echoes a label inline after each claim it
supports, and a label it invents (not in the sources) is dropped at parse. The
prompt enforces: cite every non-trivial claim · use ONLY provided labels ·
synthesise (don't copy source phrasing) · write prose, NOT an attribute dump
(risk #14) · `>` blockquote ONLY for enriched/non-canon material. The BookProfile
shapes language / voice / era / anachronism so the article isn't biased toward
the hardcoded 封神 universe.
"""

from __future__ import annotations

from app.clients.book_profile_client import BookProfile
from app.wiki.context import ContextSource, EntityBrief

#: The fixed system contract (format + grounding rules). Profile/voice clauses
#: are appended per-call; the entity + sources go in the user message.
_SYSTEM_BASE = """\
You are an encyclopaedia editor writing ONE wiki article about a single entity \
from a work of fiction, grounded ONLY in the sources provided.

OUTPUT FORMAT — constrained Markdown, nothing else:
- Open with a LEAD paragraph (no heading) that says who/what the subject is.
- Then 2–4 thematic sections, each a `## Section Title` followed by prose. Add a \
section ONLY when the sources support it — do NOT pad with empty or speculative \
sections.
- Use `- ` for bullet lists where a list is genuinely clearer than prose.
- Use `> ` blockquote ONLY for explicitly non-canonical / speculative / variant \
("enriched") material. Canon prose is never blockquoted.
- No top-level `#` title, no tables, no images, no front-matter.

GROUNDING — this is the most important rule:
- You are given SOURCES, each pre-labelled like [P1], [G1], [K1].
- After EVERY non-trivial claim, cite the supporting source inline, e.g. \
"She was raised in the southern marches [P2]." Place the label right after the \
clause it supports.
- Use ONLY the labels you were given. NEVER invent a label or cite a source you \
were not handed.
- If a claim is not supported by any source, DO NOT make it. Omit it entirely.
- Synthesise in your OWN words; do NOT copy sentences verbatim from the sources.

DO NOT restate raw attribute lists or an "infobox" of fields — write flowing, \
readable prose. Be concise and faithful; never embellish beyond the sources."""


def _profile_clauses(profile: BookProfile) -> str:
    """Per-book style guidance derived from the de-bias profile. Each clause is
    emitted only when the profile sets it, so a neutral profile adds nothing
    (the article stays a generic worldbuilder, never the hardcoded 封神 voice)."""
    lines: list[str] = []
    if profile.language and profile.language != "auto":
        lines.append(f"- Write the article in this language: {profile.language}.")
    else:
        lines.append("- Write in the same language as the source passages.")
    if profile.worldview.strip():
        lines.append(f"- World/setting context: {profile.worldview.strip()}.")
    if profile.voice and profile.voice.strip():
        lines.append(f"- Narrative voice/tone to match: {profile.voice.strip()}.")
    if profile.era_policy and profile.era_policy.strip():
        lines.append(f"- Era constraint: {profile.era_policy.strip()}.")
    if profile.anachronism_markers:
        terms = ", ".join(t for t, _r in profile.anachronism_markers)
        lines.append(
            f"- Avoid anachronistic terms that don't fit the setting: {terms}."
        )
    return "STYLE:\n" + "\n".join(lines)


_KIND_LABEL = {"glossary": "glossary", "kg": "knowledge-graph", "passage": "passage"}


def _render_sources(items: list[ContextSource]) -> str:
    """The labelled source block the LLM cites against. Each line is
    ``[cite_id] (kind) full-text`` — the FULL text (not the stored snippet)."""
    if not items:
        return "(no sources were retrieved for this entity)"
    out: list[str] = []
    for it in items:
        kind = _KIND_LABEL.get(it.source.kind, it.source.kind)
        text = it.text.strip().replace("\n", " ")
        out.append(f"[{it.source.cite_id}] ({kind}) {text}")
    return "\n".join(out)


def _render_brief(brief: EntityBrief) -> str:
    parts = [f"SUBJECT: {brief.name}"]
    if brief.kind:
        parts.append(f"TYPE: {brief.kind}")
    if brief.aliases:
        parts.append("ALSO KNOWN AS: " + ", ".join(brief.aliases))
    return "\n".join(parts)


def _render_exemplars(exemplars: list[tuple[str, str]]) -> str:
    """D-WIKI-M8-FEWSHOT — render gold AI-draft→human-edit pairs as a STYLE lesson in
    the system message. Framed explicitly so the model learns the editorial style
    (tone, structure, what humans trim/fix) WITHOUT copying the example content or
    treating their text as live sources to cite."""
    blocks: list[str] = [
        "EXAMPLES OF HUMAN EDITS TO PRIOR AI ARTICLES (learn the editorial STYLE — "
        "what humans tighten, cut, or reword; do NOT copy this content and do NOT cite "
        "from these examples):"
    ]
    for i, (ai_text, human_text) in enumerate(exemplars, start=1):
        ai = ai_text.strip()
        human = human_text.strip()
        if not ai or not human:
            continue
        blocks.append(
            f"Example {i}:\n--- AI DRAFT ---\n{ai}\n--- HUMAN-EDITED ---\n{human}"
        )
    # /review-impl F4: if EVERY pair was blank, `blocks` holds only the header —
    # don't emit a dangling "EXAMPLES…" header with no examples under it.
    if len(blocks) == 1:
        return ""
    return "\n\n".join(blocks)


def build_messages(
    *,
    brief: EntityBrief,
    profile: BookProfile,
    items: list[ContextSource],
    corrective: str | None = None,
    exemplars: list[tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build the `messages` list for the generation LLM call.

    `corrective` (optional) appends a short note to the system prompt on a RETRY
    attempt — e.g. "your previous draft left claims uncited" — to nudge the model
    toward grounding without rebuilding the whole prompt. `exemplars` (optional,
    D-WIKI-M8-FEWSHOT) adds gold AI→human edit pairs as a style lesson in the system
    message — kept OUT of the user turn so it never pollutes the cite-discipline."""
    system = _SYSTEM_BASE + "\n\n" + _profile_clauses(profile)
    if exemplars:
        rendered = _render_exemplars(exemplars)
        if rendered:
            system += "\n\n" + rendered
    if corrective:
        system += "\n\nNOTE ON YOUR PREVIOUS ATTEMPT:\n" + corrective.strip()
    user = (
        _render_brief(brief)
        + "\n\nSOURCES (cite these by their [label]):\n"
        + _render_sources(items)
        + "\n\nWrite the wiki article now, citing every non-trivial claim."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

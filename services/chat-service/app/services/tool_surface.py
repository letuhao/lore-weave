"""Session-scoped tool surface assembly — whitelist-with-escape (story 04).

When ``enabled_tools`` is non-empty (curated mode), the turn advertises
ALWAYS_ON_CORE ∪ pins ∪ session ``activated_tools``; ``find_tools`` unions
matches into the per-turn active set AND persists to ``activated_tools``.
Empty pins preserve legacy hot-set + auto-discovery behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.tool_discovery import hot_tool_names, surface_hot_domains

ACTIVATED_TOOLS_CAP = 64


@dataclass
class SessionToolPins:
    """Resolved session pin state for a chat turn (fresh or resume)."""

    effective_enabled: list[str]
    effective_skills: list[str]
    curated_mode: bool
    activation_state: dict


def resolve_session_tool_pins(
    session_row,
    *,
    enabled_tools_override: list[str] | None = None,
    enabled_skills_override: list[str] | None = None,
) -> SessionToolPins:
    session_enabled = list(session_row.get("enabled_tools") or []) if session_row else []
    session_skills = list(session_row.get("enabled_skills") or []) if session_row else []
    session_activated = list(session_row.get("activated_tools") or []) if session_row else []
    effective_enabled = (
        enabled_tools_override if enabled_tools_override is not None else session_enabled
    )
    effective_skills = (
        enabled_skills_override if enabled_skills_override is not None else session_skills
    )
    return SessionToolPins(
        effective_enabled=effective_enabled,
        effective_skills=effective_skills,
        curated_mode=is_curated(effective_enabled),
        activation_state={"activated_tools": list(session_activated), "dirty": False},
    )


def discovery_seed_for_surface(
    catalog: list[dict],
    *,
    pins: SessionToolPins,
    editor: bool,
    book_scoped: bool,
    studio: bool = False,
) -> set[str]:
    """Discovery active-set seed: hot set (auto) or pins ∪ activated (curated)."""
    hot_domains = surface_hot_domains(editor=editor, book_scoped=book_scoped, studio=studio)
    raw_hot_seed = hot_tool_names(catalog, hot_domains)
    eff_pins = pins.effective_enabled
    if pins.curated_mode:
        # In curated mode the hot set only enters via this union; the studio surface's
        # hot domains (glossary+composition) ride the same seam (M-E live-caught).
        glossary_in_skills = (
            "glossary" in pins.effective_skills
            or (not pins.effective_skills and (book_scoped or studio))
        )
        eff_pins = effective_enabled_tools(
            pins.effective_enabled,
            glossary_skill=glossary_in_skills,
            catalog=catalog,
            hot_domains=hot_domains,
        )
    return assemble_initial_active_names(
        curated=pins.curated_mode,
        enabled_tools=eff_pins,
        activated_tools=pins.activation_state["activated_tools"],
        hot_seed_names=raw_hot_seed,
    )


def is_curated(enabled_tools: list[str] | None) -> bool:
    return bool(enabled_tools)


def effective_enabled_tools(
    enabled_tools: list[str],
    *,
    glossary_skill: bool,
    catalog: list[dict],
    hot_domains: set[str],
) -> list[str]:
    """When glossary skill is active in curated mode, auto-union glossary hot tools."""
    if not glossary_skill or not enabled_tools:
        return list(enabled_tools)
    hot = hot_tool_names(catalog, hot_domains)
    return list(dict.fromkeys([*enabled_tools, *sorted(hot)]))


def assemble_initial_active_names(
    *,
    curated: bool,
    enabled_tools: list[str],
    activated_tools: list[str],
    hot_seed_names: set[str],
) -> set[str]:
    if not curated:
        return set(hot_seed_names)
    return set(enabled_tools) | set(activated_tools)


def merge_activated_tools(current: list[str], matched: set[str]) -> list[str]:
    merged = list(dict.fromkeys([*current, *sorted(matched)]))
    if len(merged) > ACTIVATED_TOOLS_CAP:
        merged = merged[-ACTIVATED_TOOLS_CAP:]
    return merged

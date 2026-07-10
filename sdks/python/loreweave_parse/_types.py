"""Pydantic types for the structural decomposer (T1 of the hierarchical extraction ADR).

These mirror the StructuralTree schema locked in
docs/specs/2026-05-23-p1-structural-decomposer.md D8 + the
POST /internal/parse contract (D6).

Invariants (asserted by Pydantic + the round-trip tests):
- len(tree.parts) >= 1
- every part has >= 1 chapter
- every chapter has >= 1 scene
- path strings are deterministic from sort_orders
- re-parsing identical input produces identical paths + content_hashes
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SourceFormat = Literal["html", "plain", "tiptap"]  # 26 IX-6: tiptap = re-parse of the pinned draft
WalkerPath = Literal["headings", "fallback_single"]  # M2 dropped "nav" for P1


class Scene(BaseModel):
    sort_order: int = Field(ge=1)
    path: str  # e.g. "book/part-1/chapter-3/scene-2"
    leaf_text: str
    content_hash: str  # sha256(leaf_text) hex — P2 task-ID seed
    # 26 IX-5/IX-6: the opening heading's `data-scene-id` (ProseMirror `attrs.sceneId`)
    # carried through by the tiptap walker; the re-parser sets `scenes.source_scene_id`
    # from it (evidence rule 1). None for anchorless leaves and every non-tiptap format.
    anchor_scene_id: str | None = None


class Chapter(BaseModel):
    sort_order: int = Field(ge=1)
    title: str | None = None
    path: str  # e.g. "book/part-1/chapter-3"
    html: str  # post-pandoc HTML slice for this chapter; consumed by htmlToTiptapJSON
    scenes: list[Scene] = Field(min_length=1)


class Part(BaseModel):
    sort_order: int = Field(ge=1)
    title: str | None = None
    path: str  # e.g. "book/part-1"
    chapters: list[Chapter] = Field(min_length=1)


class StructuralTree(BaseModel):
    source_format: SourceFormat
    detected_language: str | None = None  # populated only when input language was "auto"/null
    walker_path: WalkerPath
    book_title: str | None = None
    parts: list[Part] = Field(min_length=1)


class ParseOptions(BaseModel):
    """Optional knobs on parse(). All defaulted; spec D6."""

    scene_break_on_hr: bool = True
    max_leaf_chars: int | None = None  # P1: not enforced (P2 concern)


class ParseRequest(BaseModel):
    """Request body for POST /internal/parse (D6)."""

    source_format: SourceFormat
    content: str
    language: str | None = None  # null/"auto" runs detector
    filename: str | None = None
    options: ParseOptions = Field(default_factory=ParseOptions)


__all__ = [
    "Chapter",
    "ParseOptions",
    "ParseRequest",
    "Part",
    "Scene",
    "SourceFormat",
    "StructuralTree",
    "WalkerPath",
]

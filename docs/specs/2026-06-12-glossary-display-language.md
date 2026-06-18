# Glossary Display Language QoL

**Date:** 2026-06-12  
**Track:** enhancement (isolated handoff)

## Problem

Glossary list and entity detail always show original-language text. Users who batch-translate glossary entries must open each entity to see translations.

## Solution

Per-book display language preference (server-synced via `/v1/me/preferences`). Header picker on Glossary tab. List and detail resolve translated text when available; fallback to original.

## Acceptance criteria

1. Glossary tab header has a language picker (original + supported target langs).
2. Preference persists per book across devices (prefs JSONB).
3. Entity list shows resolved `display_name` when `display_language` differs from original.
4. Search matches translated names when display language is active.
5. Entity editor header and attribute view show resolved values; original shown as secondary when viewing a translation.
6. Reload preserves picker selection.

## Out of scope

Wiki, entity-names decoration, unknown/merge panels, MCP tools.

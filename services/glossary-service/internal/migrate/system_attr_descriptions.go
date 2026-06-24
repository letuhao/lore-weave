package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpSystemAttrDescriptions — chain step 0035 (F1, D-GLOSSARY-SYSTEM-ATTR-DESCRIPTIONS).
// Spec: docs/specs/2026-06-22-F1-system-attr-descriptions.md
//
// Seeds an extraction-ready `description` onto every System-tier attribute. The
// extraction LLM reads `book_attributes.description` as the PER-ATTRIBUTE instruction
// (extraction_prompt.py); books clone the System tier at adopt time, so an empty
// System description is the platform-wide root cause of guidance-less extraction.
//
// Mechanics (no schema change — verified in the spec):
//   - `content_hash` already includes `description` (md5(code|name|description|
//     field_type|is_required|options)). Editing a description MUST recompute the
//     hash or G5 Sync goes blind to the change. We recompute it here with the EXACT
//     inline md5 the seed uses (migrate.go SeedGenreKindAttr, line ~1923) — which is
//     byte-identical to the Go attrContentHash helper — so the new hash matches what
//     a fresh seed-with-description would have produced (parity across tiers).
//   - Adopt copies `sa.description` + `sa.content_hash` into the book row, so NEW
//     books get descriptions at adopt; EXISTING books detect the hash drift via G5
//     Sync and pull the description through `sync_apply take_theirs` (decision:
//     sync-only, NO backfill).
//
// Non-clobbering: the empty-description guard means an
// admin-authored description is never overwritten, and a re-run updates 0 rows
// (idempotent). All seeded System attributes live under the `universal` genre, so
// matching by (kind_code, attr_code) hits exactly one row per attribute.
//
// DML-only (UPDATE) — no DDL — but still routed through execGuarded for the shared
// migration advisory lock. `name`/`term` (the display keys) carry no extraction
// value and are intentionally omitted.
func UpSystemAttrDescriptions(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "system-attr-descriptions", systemAttrDescriptionsSQL)
}

const systemAttrDescriptionsSQL = `
UPDATE system_attributes sa
SET description = v.descr,
    content_hash = md5(
      sa.code || '|' || sa.name || '|' || COALESCE(v.descr, '') || '|' ||
      sa.field_type || '|' || (sa.is_required)::text || '|' ||
      COALESCE(array_to_string(sa.options, ','), '')
    )
FROM (VALUES
  -- character
  ('character', 'aliases', 'Other names, titles, epithets, or nicknames the character is known by.'),
  ('character', 'gender', 'The character''s gender or how the text presents it.'),
  ('character', 'role', 'The character''s narrative role (protagonist, antagonist, mentor, foil, …).'),
  ('character', 'occupation', 'The character''s job, profession, or primary activity in the story.'),
  ('character', 'social_class', 'The character''s social standing or rank (noble, commoner, outcast, …).'),
  ('character', 'affiliation', 'The faction, house, organization, or side the character belongs to.'),
  ('character', 'appearance', 'Physical appearance: build, face, clothing, and any distinguishing or supernatural features described in the text.'),
  ('character', 'personality', 'Temperament, core traits, virtues and flaws as shown through actions and speech.'),
  ('character', 'emotional_wound', 'The past hurt, loss, or trauma that drives the character''s behavior.'),
  ('character', 'love_language', 'How the character expresses or receives affection (if relevant to the story).'),
  ('character', 'relationships', 'Key relationships to other characters and how they connect.'),
  ('character', 'description', 'A concise overview of who the character is and their significance in the story.'),
  -- event
  ('event', 'type', 'The kind of event (battle, betrayal, wedding, death, revelation, …).'),
  ('event', 'date_in_story', 'When the event occurs in the story''s timeline (in-world date or chapter).'),
  ('event', 'location', 'Where the event takes place.'),
  ('event', 'participants', 'The characters or groups involved in the event.'),
  ('event', 'emotional_impact', 'The emotional weight or fallout the event carries for those involved.'),
  ('event', 'outcome', 'What results or changes because of the event.'),
  ('event', 'description', 'What happens in the event, concisely.'),
  -- item
  ('item', 'aliases', 'Other names or titles the item is known by.'),
  ('item', 'type', 'The kind of item (weapon, artifact, relic, document, tool, …).'),
  ('item', 'owner', 'Who currently holds or is associated with the item.'),
  ('item', 'symbolic_meaning', 'What the item represents thematically or symbolically in the story.'),
  ('item', 'description', 'What the item is, its properties, and its role.'),
  -- location
  ('location', 'aliases', 'Other names the place is known by.'),
  ('location', 'type', 'The kind of place (city, castle, region, realm, building, …).'),
  ('location', 'parent_location', 'The larger place this one belongs to (region, country, world).'),
  ('location', 'atmosphere', 'The mood, tone, or sensory feel of the place as the text describes it.'),
  ('location', 'significance', 'Why the place matters to the story or its characters.'),
  ('location', 'description', 'What the place is and its notable features.'),
  -- organization
  ('organization', 'aliases', 'Other names the organization is known by.'),
  ('organization', 'type', 'The kind of organization (guild, house, cult, government, army, …).'),
  ('organization', 'leader', 'Who leads or heads the organization.'),
  ('organization', 'headquarters', 'The organization''s base, seat, or primary location.'),
  ('organization', 'members', 'Notable members or the makeup of the organization.'),
  ('organization', 'description', 'What the organization is, its purpose, and its role in the story.'),
  -- plot_arc
  ('plot_arc', 'arc_type', 'The kind of arc (redemption, revenge, coming-of-age, mystery, …).'),
  ('plot_arc', 'parties', 'The characters or groups the arc centers on.'),
  ('plot_arc', 'trigger', 'The event or condition that sets the arc in motion.'),
  ('plot_arc', 'stakes', 'What is at risk or to be gained in the arc.'),
  ('plot_arc', 'chapters_span', 'The chapter range the arc covers.'),
  ('plot_arc', 'emotional_beats', 'The key emotional turning points along the arc.'),
  ('plot_arc', 'resolution', 'How the arc concludes or is left.'),
  ('plot_arc', 'description', 'A concise summary of the arc.'),
  -- power_system
  ('power_system', 'aliases', 'Other names the power/system is known by.'),
  ('power_system', 'type', 'The kind of power system (magic, cultivation, technology, psionics, …).'),
  ('power_system', 'rank', 'The tier, rank, or level scheme within the system.'),
  ('power_system', 'user', 'Who wields or has access to this power.'),
  ('power_system', 'effects', 'What the power does and its capabilities or limits.'),
  ('power_system', 'description', 'How the power system works, concisely.'),
  -- relationship
  ('relationship', 'parties', 'The characters or groups in the relationship.'),
  ('relationship', 'relationship_type', 'The kind of relationship (rivals, lovers, family, allies, …).'),
  ('relationship', 'status', 'The current state of the relationship (estranged, growing, broken, …).'),
  ('relationship', 'tropes', 'Romance/relationship tropes that characterize it (if any).'),
  ('relationship', 'dynamic', 'How the parties interact and the push-pull between them.'),
  ('relationship', 'key_conflict', 'The central tension or obstacle in the relationship.'),
  ('relationship', 'turning_points', 'Moments that shift the relationship.'),
  ('relationship', 'resolution', 'How the relationship resolves or is left.'),
  ('relationship', 'description', 'A concise summary of the relationship.'),
  -- social_setting
  ('social_setting', 'era', 'The time period or era of the setting.'),
  ('social_setting', 'location', 'The place or region the social setting covers.'),
  ('social_setting', 'class_hierarchy', 'The social classes or hierarchy and how they relate.'),
  ('social_setting', 'rules_norms', 'The customs, laws, and social norms that govern behavior.'),
  ('social_setting', 'romance_obstacles', 'Social barriers to romance the setting imposes (if relevant).'),
  ('social_setting', 'significance', 'Why this social setting matters to the story.'),
  ('social_setting', 'description', 'A concise overview of the social setting.'),
  -- species
  ('species', 'aliases', 'Other names the species or race is known by.'),
  ('species', 'traits', 'Defining physical or innate traits of the species.'),
  ('species', 'abilities', 'Special abilities or powers the species possesses.'),
  ('species', 'habitat', 'Where the species lives.'),
  ('species', 'culture', 'The species'' culture, customs, or social organization.'),
  ('species', 'description', 'What the species is, concisely.'),
  -- terminology
  ('terminology', 'category', 'The category the term belongs to (magic, politics, technology, …).'),
  ('terminology', 'definition', 'What the term means in this story''s world.'),
  ('terminology', 'usage_note', 'How and when the term is used, and any nuance.'),
  -- trope
  ('trope', 'category', 'The category of trope (character, plot, romance, setting, …).'),
  ('trope', 'definition', 'What the trope is.'),
  ('trope', 'how_manifested', 'How this trope shows up in the story specifically.'),
  ('trope', 'subverted', 'Whether and how the story subverts or plays against the trope.'),
  ('trope', 'related_characters', 'Characters who embody or are involved with the trope.'),
  ('trope', 'usage_note', 'Notes on how the trope functions in the story.')
) AS v(kind_code, attr_code, descr)
JOIN system_kinds sk ON sk.code = v.kind_code
WHERE sa.kind_id = sk.kind_id
  AND sa.code = v.attr_code
  AND COALESCE(TRIM(sa.description), '') = '';
`

package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/domain"
)

// techniqueKindSplitSQL — chain step 0056. Splits `technique` out of `power_system` at the
// System tier, and REWRITES both definitions.
//
// The defect: `power_system` reads to a model as "a graded scheme of power" — the thing a
// story establishes when it names 練氣/築基/金丹 or 大羅金仙 and lets characters move along
// it. The kind's own description (written 2026-08-01, the day descriptions were added at all)
// said the opposite in as many words: "a SINGLE technique belongs here; the name says system
// but one art is enough." Name and definition were arguing, and the model was left to pick.
//
// It picked badly in both directions, measurably: the two-stage shape filed 崑崙之妙術 under
// `terminology` and 哮天犬 under `item`; the batched shape put four swords and a mirror INTO
// `power_system`. Those look like opposite errors and are the same one — no kind meant "a
// single art", so arts scattered to whichever neighbour was nearest.
//
// Evidence for the other half, which matters because it corrects a claim this project made
// about its own numbers: chapters 88-92 of 封神演義 contain ZERO occurrences of 境界, 修為,
// 品階, 等級, 階級, 層次, 果位, 金仙, 大羅, 天仙 or 太乙. That text has no ranked ladder. Its
// power vocabulary is individual arts (縱地行之術, 陰符之術, 崑崙之妙術, 八九變化) and
// attainment labels (煉氣士, 得道白猿, 真人). So `power_system = 0` on that run was not a
// coverage gap to explain — under the corrected definition it is the right answer, and the
// earlier reading of it as a miss was an inference about a corpus nobody had looked at.
//
// Tenancy: System tier only (admin-managed, read-only to users; CLAUDE.md › User Boundaries).
// Books that already adopted the catalogue keep their book-tier copies untouched — they gain
// `technique` by re-running adopt, which is idempotent and inserts only codes they lack.
//
// The `power_system` UPDATE deliberately overwrites a non-empty description, unlike the
// initial description seed which only filled NULLs. The whole point is that the existing text
// is WRONG; leaving it because it is present would preserve the defect.
const techniqueKindSplitSQL = `
-- The kind row only. Its ATTRIBUTES and its genre link are not written here: Seed() and
-- SeedGenreKindAttr() both derive from domain.DefaultKinds in Go and run on every startup,
-- per-code idempotent, so a newly declared kind picks both up without a second copy of the
-- data in SQL that could drift from the Go one.
INSERT INTO system_kinds (code, name, description, icon, color, sort_order, is_default, is_hidden)
VALUES (
  'technique', 'Technique / Art',
  'A single named ART, SPELL, FORMATION, MARTIAL MOVE or magical METHOD that someone performs, casts or has mastered. One art is a whole entity here; it does not need a system behind it. NOT the ladder such arts might be ranked on (power_system), NOT the weapon or talisman used to perform it (item), NOT a doctrine nobody performs (terminology).',
  '🌀', '#8b5cf6', 7, true, false
)
ON CONFLICT (code) DO UPDATE
  SET description = EXCLUDED.description
  WHERE system_kinds.description IS NULL OR system_kinds.description = '';

UPDATE system_kinds SET
  name = 'Power System (Tier Ladder)',
  description = 'The GRADED SCHEME a world measures power by, or one named TIER within it. Extract this only where the text establishes an ORDERING that characters move along; the mark of it is that two tiers can be compared. NOT a single art someone performs, however impressive (that is technique), NOT the object used (item), NOT a bare honorific with no ladder behind it (terminology). A story with no ranked ladder has NO entities of this kind.'
WHERE code = 'power_system';

-- Retire the three attributes that only made sense while power_system meant "an art":
-- what SORT of method it is, WHO performs it, and what it DOES when used. A tier is not
-- performed by anyone. They live on the technique kind now, and the ladder gets tiers,
-- entry_requirement and capabilities from the Go seed pass instead.
--
-- SOFT, via deprecated_at -- the same mechanism an admin delete uses (G-C8). A hard DELETE
-- would be the wrong tool twice over: these rows are referenced by adopt provenance, and a
-- mistake here would be unrecoverable, where a deprecation is one UPDATE from undone.
-- Book-tier copies are untouched either way, so no author loses a field they authored.
UPDATE system_attributes a
SET deprecated_at = now()
FROM system_kinds k
WHERE a.kind_id = k.kind_id
  AND k.code = 'power_system'
  AND a.code IN ('type', 'user', 'effects')
  AND a.deprecated_at IS NULL;

-- The vi labels. power_system was seeded as a phrase meaning "system of power", which
-- carries the same ambiguity: it names the scheme, while the rows filed under it were arts.
UPDATE system_kinds k
SET name_i18n = k.name_i18n || jsonb_build_object('vi', v.vi)
FROM (VALUES
  ('power_system', 'Cảnh giới / Hệ thống cấp bậc'), -- doc-language-gate: ok -- an i18n label; the vi text IS the payload
  ('technique',    'Công pháp / Thuật')             -- doc-language-gate: ok -- an i18n label; the vi text IS the payload
) AS v(code, vi)
WHERE k.code = v.code;
`

// splitKinds are the two kinds whose ATTRIBUTES this step must reconcile in Go rather than
// SQL: the new one has none yet, and the rewritten one gained three.
var splitKinds = map[string]bool{"power_system": true, "technique": true}

// UpTechniqueKindSplit seeds the `technique` kind row and rewrites `power_system` to mean
// the tier ladder its name already implied. Idempotent; chain step 0056.
func UpTechniqueKindSplit(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "technique-kind-split", techniqueKindSplitSQL)
}

// UpTechniqueKindAttrs reconciles the two split kinds' ATTRIBUTES. Chain step 0057.
//
// It is a SEPARATE ledger entry rather than a second half of 0056, and that is not tidiness:
// 0056 had already been applied when this work was written, so appending to it would have
// been dead code on every database that ran the first version — silently, since the chain
// reports a step it has already recorded as done. **A ledger entry is immutable once
// applied.** (Caught by looking at the table rather than at the migration.)
//
// The work cannot ride SeedGenreKindAttr either: that step is ledgered too, so it has long
// since run everywhere and will never see a kind declared afterwards. Its insert loop is
// mirrored here, scoped to the two kinds and reading the same domain.DefaultKinds, so the
// two paths cannot describe different attributes for the same code.
func UpTechniqueKindAttrs(ctx context.Context, pool *pgxpool.Pool) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("technique-split attrs tx: %w", err)
	}
	defer tx.Rollback(ctx)

	for _, k := range domain.DefaultKinds {
		if !splitKinds[k.Code] {
			continue
		}
		var kindID string
		if err := tx.QueryRow(ctx,
			`SELECT kind_id FROM system_kinds WHERE code=$1`, k.Code).Scan(&kindID); err != nil {
			return fmt.Errorf("technique-split resolve kind %s: %w", k.Code, err)
		}
		for _, a := range k.Attrs {
			var opts []string
			if len(a.Options) > 0 {
				opts = a.Options
			}
			// DO UPDATE, not DO NOTHING: `power_system.rank` already exists and its label
			// ("Rank / Tier") described the ART's grade, not a position in a ladder. Leaving
			// the old row would ship a kind whose own fields still argue with its definition,
			// which is the defect this whole step exists to end. Only these two kinds are in
			// scope, and both are being deliberately redefined.
			if _, err := tx.Exec(ctx, `
				INSERT INTO system_attributes
				  (kind_id, genre_id, code, name, description, field_type, is_required, sort_order, options, content_hash)
				SELECT $1, g.genre_id, $2, $3, $4, $5, $6::boolean, $7, $8::text[],
				       md5($2||'|'||$3||'|'||coalesce($4,'')||'|'||$5||'|'||($6::boolean)::text||'|'||coalesce(array_to_string($8::text[],','),''))
				FROM system_genres g WHERE g.code = 'universal'
				ON CONFLICT (kind_id, genre_id, code) DO UPDATE
				   SET name = EXCLUDED.name, description = EXCLUDED.description,
				       field_type = EXCLUDED.field_type, is_required = EXCLUDED.is_required,
				       sort_order = EXCLUDED.sort_order, options = EXCLUDED.options,
				       content_hash = EXCLUDED.content_hash, deprecated_at = NULL`,
				kindID, a.Code, a.Name, a.Description, a.FieldType, a.IsRequired, a.SortOrder, opts,
			); err != nil {
				return fmt.Errorf("technique-split attr %s.%s: %w", k.Code, a.Code, err)
			}
		}
	}
	return tx.Commit(ctx)
}

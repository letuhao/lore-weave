package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpStDedupAppMaintained — chain step 0040 (D-GLOSSARY-ST-DEDUP M3a).
//
// Converts glossary_entities.normalized_name from a GENERATED-STORED column to a
// plain, APP-MAINTAINED column. The generated expression was
//
//	lower(btrim(regexp_replace(normalize(coalesce(cached_name,''),NFC),'\s+',' ','g')))
//
// i.e. NFC + lower only — it could NOT fold CJK simplified/traditional, full-width,
// or Unicode-casefold variants (Postgres has no native casefold or t2s), so
// 張若塵 and 张若尘 got distinct dedup keys. We now compute the key in Go via the
// shared loreweave_extraction SDK (NFKC + casefold + Han t2s fold) — the SAME fold
// the resolver (textnorm.Normalize) and the knowledge-service use — and write it
// from the app at every name-write path (refreshEntityDedupKey). This makes the
// DB dedup-key backstop agree with the resolver by construction (one fold impl).
//
// DROP EXPRESSION (Postgres ≥13) converts the column to plain WHILE PRESERVING the
// current values — so this step is non-destructive: existing rows keep their old
// NFC+lower key until the M3b remediation backfills the new fold and merges the
// existing simplified/traditional duplicate groups. The partial unique index
// uq_entity_dedup stays valid (it indexes the column regardless of generated-ness).
//
// Idempotent: the DROP is guarded on attgenerated so a re-run (or a fresh DB whose
// column is already plain) no-ops. A DEFAULT '' is set so a freshly-inserted entity
// row (created before its name EAV lands) carries '' — excluded by the partial
// index — until refreshEntityDedupKey fills it.
func UpStDedupAppMaintained(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "st-dedup-app-maintained", `
		DO $$
		BEGIN
		  IF EXISTS (
		    SELECT 1 FROM pg_attribute
		    WHERE attrelid = 'glossary_entities'::regclass
		      AND attname  = 'normalized_name'
		      AND attgenerated = 's'      -- 's' = STORED generated
		      AND NOT attisdropped
		  ) THEN
		    ALTER TABLE glossary_entities ALTER COLUMN normalized_name DROP EXPRESSION;
		  END IF;
		END $$;

		ALTER TABLE glossary_entities ALTER COLUMN normalized_name SET DEFAULT '';
		UPDATE glossary_entities SET normalized_name = '' WHERE normalized_name IS NULL;`)
}

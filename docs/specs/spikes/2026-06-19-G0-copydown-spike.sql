-- =====================================================================
-- G0 SPIKE — genre·kind·attribute standards→sovereign-instance model
-- Spec: docs/specs/2026-06-19-genre-kind-attribute-tiering.md
--
-- HYPOTHESIS TO PROVE (the cleanest form of the design):
--   1. Standards (System/User) hold DEFINITIONS ONLY, keyed by (kind, genre, code),
--      with PLAIN per-tier FKs — no polymorphic (kind×genre×tier) reference anywhere.
--   2. ADOPT = copy-down: a Book is scaffolded from standards by resolving
--      System→User by code (User shadows System) and INSERT...SELECT into the
--      book tier. Instantiation, not duplication.
--   3. Multi-genre keep-both-namespaced is FREE: same attr code in two genres =
--      two distinct book rows (no special merge logic, no namespacing column).
--   4. The entity FORM read is BOOK-LOCAL SINGLE-TIER: it touches only book_*
--      tables — never system_* or user_*. Proven by EXPLAIN.
--   5. Every entity reference (kind, attribute-value) is a plain in-book FK.
--
-- Throwaway DB. Uses plpgsql ASSERT — any failed invariant aborts loudly.
-- =====================================================================

\set ON_ERROR_STOP on
SET client_min_messages = NOTICE;

DROP SCHEMA IF EXISTS spike CASCADE;
CREATE SCHEMA spike;
SET search_path = spike;

-- ─────────────────────────────────────────────────────────────────────
-- STANDARDS LAYER — definitions only. No entities live here.
-- ─────────────────────────────────────────────────────────────────────

-- System tier (admin/seed only)
CREATE TABLE system_genres (
  id   bigserial PRIMARY KEY,
  code text NOT NULL UNIQUE,
  name text NOT NULL
);
CREATE TABLE system_kinds (
  id   bigserial PRIMARY KEY,
  code text NOT NULL UNIQUE,
  name text NOT NULL
);
CREATE TABLE system_kind_genres (              -- which genres a system kind supports
  system_kind_id  bigint NOT NULL REFERENCES system_kinds(id),
  system_genre_id bigint NOT NULL REFERENCES system_genres(id),
  PRIMARY KEY (system_kind_id, system_genre_id)
);
CREATE TABLE system_attributes (
  id              bigserial PRIMARY KEY,
  system_kind_id  bigint NOT NULL REFERENCES system_kinds(id),   -- plain FK, same tier
  system_genre_id bigint NOT NULL REFERENCES system_genres(id),  -- plain FK, same tier
  code        text NOT NULL,
  name        text NOT NULL,
  description text,
  field_type  text NOT NULL,
  is_required boolean NOT NULL DEFAULT false,
  sort_order  int NOT NULL DEFAULT 0,
  UNIQUE (system_kind_id, system_genre_id, code)   -- real scoped UNIQUE, not UNIQUE(code)
);

-- User tier (owner_user_id). Same shape + owner. Standards, still no entities.
CREATE TABLE user_genres (
  id bigserial PRIMARY KEY, owner_user_id uuid NOT NULL,
  code text NOT NULL, name text NOT NULL,
  UNIQUE (owner_user_id, code)
);
CREATE TABLE user_kinds (
  id bigserial PRIMARY KEY, owner_user_id uuid NOT NULL,
  code text NOT NULL, name text NOT NULL,
  UNIQUE (owner_user_id, code)
);
CREATE TABLE user_attributes (
  id bigserial PRIMARY KEY, owner_user_id uuid NOT NULL,
  -- a user attribute attaches onto a (kind, genre) identified BY CODE so it can
  -- ride on top of a system kind/genre; resolved to ids at adopt time.
  kind_code  text NOT NULL,
  genre_code text NOT NULL,
  code text NOT NULL, name text NOT NULL, description text,
  field_type text NOT NULL, is_required boolean NOT NULL DEFAULT false,
  sort_order int NOT NULL DEFAULT 0,
  UNIQUE (owner_user_id, kind_code, genre_code, code)
);

-- ─────────────────────────────────────────────────────────────────────
-- BOOK LAYER — the sovereign instance. Owns its ontology + all entities.
-- Every column below is a PLAIN FK to a sibling book_* row. No polymorphism.
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE book_genres (
  id bigserial PRIMARY KEY, book_id uuid NOT NULL,
  code text NOT NULL, name text NOT NULL,
  source_ref text,                              -- 'system:xianxia' | 'user:<id>:foo' | NULL(book-native)
  deprecated_at timestamptz,
  UNIQUE (book_id, code)
);
CREATE TABLE book_kinds (
  id bigserial PRIMARY KEY, book_id uuid NOT NULL,
  code text NOT NULL, name text NOT NULL,
  source_ref text, deprecated_at timestamptz,
  UNIQUE (book_id, code)
);
CREATE TABLE book_kind_genres (
  book_id uuid NOT NULL,
  book_kind_id  bigint NOT NULL REFERENCES book_kinds(id),
  book_genre_id bigint NOT NULL REFERENCES book_genres(id),
  PRIMARY KEY (book_kind_id, book_genre_id)
);
CREATE TABLE book_attributes (
  id bigserial PRIMARY KEY, book_id uuid NOT NULL,
  book_kind_id  bigint NOT NULL REFERENCES book_kinds(id),    -- plain FK, same tier
  book_genre_id bigint NOT NULL REFERENCES book_genres(id),   -- plain FK, same tier
  code text NOT NULL, name text NOT NULL, description text,
  field_type text NOT NULL, is_required boolean NOT NULL DEFAULT false,
  sort_order int NOT NULL DEFAULT 0,
  source_ref text, deprecated_at timestamptz,
  UNIQUE (book_id, book_kind_id, book_genre_id, code)         -- keep-both lands here naturally
);
CREATE TABLE book_active_genres (
  book_id uuid NOT NULL,
  book_genre_id bigint NOT NULL REFERENCES book_genres(id),
  PRIMARY KEY (book_id, book_genre_id)
);

-- Entities — live ONLY here. kind = plain FK to book_kinds.
CREATE TABLE glossary_entities (
  id bigserial PRIMARY KEY, book_id uuid NOT NULL,
  book_kind_id bigint NOT NULL REFERENCES book_kinds(id),     -- book-local plain FK
  name text NOT NULL
);
CREATE TABLE entity_genres (                  -- per-entity genre override (D2)
  entity_id bigint NOT NULL REFERENCES glossary_entities(id),
  book_genre_id bigint NOT NULL REFERENCES book_genres(id),
  PRIMARY KEY (entity_id, book_genre_id)
);
CREATE TABLE entity_attribute_values (
  entity_id bigint NOT NULL REFERENCES glossary_entities(id),
  book_attribute_id bigint NOT NULL REFERENCES book_attributes(id),  -- book-local plain FK
  value text,
  PRIMARY KEY (entity_id, book_attribute_id)
);

-- ─────────────────────────────────────────────────────────────────────
-- SEED standards
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO system_genres(code,name) VALUES
  ('universal','Universal'), ('xianxia','Xianxia'), ('romance','Romance');
INSERT INTO system_kinds(code,name) VALUES ('character','Character');

INSERT INTO system_kind_genres(system_kind_id, system_genre_id)
SELECT k.id, g.id FROM system_kinds k, system_genres g
WHERE k.code='character' AND g.code IN ('universal','xianxia','romance');

-- character × universal
INSERT INTO system_attributes(system_kind_id,system_genre_id,code,name,description,field_type,is_required,sort_order)
SELECT k.id,g.id,v.code,v.name,v.descr,v.ft,v.req,v.so
FROM system_kinds k, system_genres g,
  (VALUES ('name','Name','Display name','text',true,1),
          ('description','Description','Freeform','textarea',false,2)) AS v(code,name,descr,ft,req,so)
WHERE k.code='character' AND g.code='universal';

-- character × xianxia  (note: defines `rank` = cultivation tier)
INSERT INTO system_attributes(system_kind_id,system_genre_id,code,name,description,field_type,is_required,sort_order)
SELECT k.id,g.id,v.code,v.name,v.descr,v.ft,v.req,v.so
FROM system_kinds k, system_genres g,
  (VALUES ('cultivation_realm','Cultivation Realm','Tier on the ladder','select',false,1),
          ('rank','Rank','Sect cultivation rank','select',false,2)) AS v(code,name,descr,ft,req,so)
WHERE k.code='character' AND g.code='xianxia';

-- character × romance  (note: also defines `rank` = social standing → conflict;
--                       and love_language which the USER tier will override)
INSERT INTO system_attributes(system_kind_id,system_genre_id,code,name,description,field_type,is_required,sort_order)
SELECT k.id,g.id,v.code,v.name,v.descr,v.ft,v.req,v.so
FROM system_kinds k, system_genres g,
  (VALUES ('love_language','Love Language','How affection is shown','text',false,1),
          ('rank','Rank','Social standing','text',false,2)) AS v(code,name,descr,ft,req,so)
WHERE k.code='character' AND g.code='romance';

-- User tier: one attribute that OVERRIDES system love_language (same kind/genre/code),
-- plus one net-new user attribute (dao_heart on character×xianxia).
\set uid '11111111-1111-1111-1111-111111111111'
INSERT INTO user_attributes(owner_user_id,kind_code,genre_code,code,name,description,field_type,is_required,sort_order) VALUES
  (:'uid','character','romance','love_language','Love Language','User-tuned options','select',false,1),
  (:'uid','character','xianxia','dao_heart','Dao Heart','Core conviction','textarea',false,3);

-- ─────────────────────────────────────────────────────────────────────
-- ADOPT / COPY-DOWN — scaffold a book from standards.
-- Resolve System→User by code (User shadows System), copy into book tier.
-- This is the ONLY moment cross-tier resolution happens.
-- ─────────────────────────────────────────────────────────────────────
\set bid '22222222-2222-2222-2222-222222222222'

-- 1) genres (book adopts universal+xianxia+romance from system)
INSERT INTO book_genres(book_id,code,name,source_ref)
SELECT :'bid', code, name, 'system:'||code FROM system_genres;

-- 2) kinds
INSERT INTO book_kinds(book_id,code,name,source_ref)
SELECT :'bid', code, name, 'system:'||code FROM system_kinds;

-- 3) kind↔genre links (remap system ids → book ids by code)
INSERT INTO book_kind_genres(book_id,book_kind_id,book_genre_id)
SELECT :'bid', bk.id, bg.id
FROM system_kind_genres skg
JOIN system_kinds  sk ON sk.id = skg.system_kind_id
JOIN system_genres sg ON sg.id = skg.system_genre_id
JOIN book_kinds  bk ON bk.book_id=:'bid' AND bk.code = sk.code
JOIN book_genres bg ON bg.book_id=:'bid' AND bg.code = sg.code;

-- 4) attributes — the resolve. Build the (kind_code,genre_code,attr_code) set
--    from System ∪ User, where USER SHADOWS SYSTEM by that key, then map to book ids.
WITH resolved AS (
  -- system rows whose (kind,genre,code) is NOT overridden by a user row
  SELECT sk.code AS kind_code, sg.code AS genre_code, sa.code,
         sa.name, sa.description, sa.field_type, sa.is_required, sa.sort_order,
         'system:'||sk.code||'/'||sg.code||'/'||sa.code AS source_ref
  FROM system_attributes sa
  JOIN system_kinds sk ON sk.id=sa.system_kind_id
  JOIN system_genres sg ON sg.id=sa.system_genre_id
  WHERE NOT EXISTS (
    SELECT 1 FROM user_attributes ua
    WHERE ua.owner_user_id=:'uid' AND ua.kind_code=sk.code
      AND ua.genre_code=sg.code AND ua.code=sa.code)
  UNION ALL
  -- all user rows for this owner (overrides + net-new)
  SELECT ua.kind_code, ua.genre_code, ua.code,
         ua.name, ua.description, ua.field_type, ua.is_required, ua.sort_order,
         'user:'||:'uid'||'/'||ua.kind_code||'/'||ua.genre_code||'/'||ua.code
  FROM user_attributes ua WHERE ua.owner_user_id=:'uid'
)
INSERT INTO book_attributes(book_id,book_kind_id,book_genre_id,code,name,description,field_type,is_required,sort_order,source_ref)
SELECT :'bid', bk.id, bg.id, r.code, r.name, r.description, r.field_type, r.is_required, r.sort_order, r.source_ref
FROM resolved r
JOIN book_kinds  bk ON bk.book_id=:'bid' AND bk.code=r.kind_code
JOIN book_genres bg ON bg.book_id=:'bid' AND bg.code=r.genre_code;

-- 5) book activates universal+xianxia+romance
INSERT INTO book_active_genres(book_id,book_genre_id)
SELECT :'bid', id FROM book_genres WHERE book_id=:'bid' AND code IN ('universal','xianxia','romance');

-- ─────────────────────────────────────────────────────────────────────
-- CREATE an entity. Plain book-local FKs only.
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO glossary_entities(book_id,book_kind_id,name)
SELECT :'bid', id, 'Diệp Phàm' FROM book_kinds WHERE book_id=:'bid' AND code='character';

-- ═════════════════════════════════════════════════════════════════════
-- THE ENTITY-FORM READ — book-local, single-tier. Touches ONLY book_* tables.
-- Active genres = entity override if any, else book defaults. (Here: book default.)
-- ═════════════════════════════════════════════════════════════════════
\echo '\n=== ENTITY FORM (book-local single-tier read) ==='
SELECT bg.code AS genre,
       ba.code AS attr_code,
       -- keep-both display name: namespace ONLY on a real same-code clash across genres
       CASE WHEN cnt.n > 1 THEN ba.code||'·'||bg.code ELSE ba.code END AS display,
       ba.field_type, ba.source_ref
FROM glossary_entities e
JOIN book_kinds  bk ON bk.id = e.book_kind_id
JOIN book_active_genres bag ON bag.book_id = e.book_id
JOIN book_genres bg ON bg.id = bag.book_genre_id
JOIN book_kind_genres bkg ON bkg.book_kind_id = bk.id AND bkg.book_genre_id = bg.id
JOIN book_attributes ba ON ba.book_kind_id = bk.id AND ba.book_genre_id = bg.id
LEFT JOIN LATERAL (
  SELECT count(*) n FROM book_attributes x
  WHERE x.book_id=ba.book_id AND x.book_kind_id=ba.book_kind_id AND x.code=ba.code
) cnt ON true
WHERE e.name='Diệp Phàm' AND ba.deprecated_at IS NULL
ORDER BY bg.code, ba.sort_order;

-- ═════════════════════════════════════════════════════════════════════
-- ASSERTIONS — fail loudly if the model doesn't hold.
-- ═════════════════════════════════════════════════════════════════════
DO $$
DECLARE
  bid constant uuid := '22222222-2222-2222-2222-222222222222';  -- psql :vars do not expand inside a dollar-quoted block
  n int;
  ll_src text;
BEGIN
  -- (A) love_language resolved to EXACTLY ONE book row, sourced from USER (override won)
  SELECT count(*), min(ba.source_ref) INTO n, ll_src
  FROM book_attributes ba JOIN book_genres bg ON bg.id=ba.book_genre_id
  WHERE ba.book_id=bid AND ba.code='love_language' AND bg.code='romance';
  ASSERT n = 1, format('love_language should resolve to 1 row, got %s', n);
  ASSERT ll_src LIKE 'user:%', format('love_language should be user-sourced, got %s', ll_src);

  -- (B) keep-both: `rank` exists as TWO book rows (xianxia + romance), both kept
  SELECT count(*) INTO n FROM book_attributes WHERE book_id=bid AND code='rank';
  ASSERT n = 2, format('rank should be kept-both = 2 rows, got %s', n);

  -- (C) net-new user attr dao_heart copied down
  SELECT count(*) INTO n FROM book_attributes WHERE book_id=bid AND code='dao_heart';
  ASSERT n = 1, format('dao_heart should be copied down, got %s', n);

  -- (D) total resolved attrs = universal(2) + xianxia(cultivation_realm,rank,dao_heart=3)
  --     + romance(love_language,rank=2) = 7
  SELECT count(*) INTO n FROM book_attributes WHERE book_id=bid;
  ASSERT n = 7, format('book should have 7 resolved attrs, got %s', n);

  -- (E) SOVEREIGNTY: deprecating a SYSTEM attribute must NOT touch the book copy.
  DELETE FROM system_attributes WHERE code='cultivation_realm';  -- simulate upstream removal
  SELECT count(*) INTO n FROM book_attributes WHERE book_id=bid AND code='cultivation_realm';
  ASSERT n = 1, 'book copy must survive upstream system removal (frozen/sovereign)';

  RAISE NOTICE 'ALL ASSERTIONS PASSED ✓ (love_language override won, rank kept-both, dao_heart copied, 7 total, sovereign survives upstream delete)';
END $$;

-- ═════════════════════════════════════════════════════════════════════
-- PROOF (4): the entity-form read plan touches ONLY book_* tables.
-- Grep the EXPLAIN output below for any system_/user_ scan — there must be none.
-- ═════════════════════════════════════════════════════════════════════
\echo '\n=== EXPLAIN of entity-form read (must reference only book_* + entity tables) ==='
EXPLAIN (COSTS OFF)
SELECT bg.code, ba.code, ba.field_type
FROM glossary_entities e
JOIN book_kinds bk ON bk.id = e.book_kind_id
JOIN book_active_genres bag ON bag.book_id = e.book_id
JOIN book_genres bg ON bg.id = bag.book_genre_id
JOIN book_kind_genres bkg ON bkg.book_kind_id = bk.id AND bkg.book_genre_id = bg.id
JOIN book_attributes ba ON ba.book_kind_id = bk.id AND ba.book_genre_id = bg.id
WHERE e.book_id=:'bid';

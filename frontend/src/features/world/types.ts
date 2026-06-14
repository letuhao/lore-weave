// C21 — World container (prose-less worldbuilding). A "world" groups books and
// auto-provisions a hidden bible book + a sort_order-0 bible chapter (C20). The
// FE never surfaces the book/manuscript mechanic — it presents "a world" whose
// lore (glossary entities) anchors to the bible chapter.

/** Mirrors book-service `worldResponse` (C20 + the C21 Step-A follow-up that
 *  exposes the bible handle). `bible_book_id` / `bible_chapter_id` are the
 *  FE-reachable anchor for lore authoring; null only for legacy worlds with no
 *  provisioned bible (the workspace then shows a degraded "anchor unavailable"
 *  state rather than mis-anchoring). */
export interface World {
  world_id: string;
  owner_user_id: string;
  name: string;
  description: string | null;
  book_count: number;
  /** The world's hidden bible book — the glossary book lore is authored in. */
  bible_book_id: string | null;
  /** The bible book's sort_order-0 hidden chapter — the NOT-NULL anchor every
   *  authored glossary entity links to (chapter_entity_links.chapter_id). */
  bible_chapter_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface WorldListResponse {
  items: World[];
  total: number;
}

export interface CreateWorldPayload {
  name: string;
  description?: string;
}

/** A glossary entity kind (reused from glossary-service /v1/glossary/kinds). The
 *  world lore form picks a kind, then authors an entity of that kind. */
export interface WorldKind {
  kind_id: string;
  code: string;
  name: string;
  icon?: string | null;
  color?: string | null;
}

/** The minimal glossary-entity shape the world lore path needs back (the entity
 *  id, so the second step can chapter-link it to the bible chapter). */
export interface AuthoredEntity {
  entity_id: string;
}

/** chapter_entity_links row returned by the glossary chapter-link endpoint. The
 *  `chapter_id` MUST equal the world's `bible_chapter_id` — the test + smoke
 *  assert exactly that (anchor correctness). */
export interface ChapterLink {
  link_id: string;
  entity_id: string;
  chapter_id: string;
  relevance: string;
}

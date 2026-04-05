/**
 * Canonical seed defaults for system entity kinds and their attributes.
 * Mirrors Go domain.DefaultKinds — used to detect modifications and revert.
 */

export type SeedAttr = { name: string; fieldType: string; isRequired: boolean };
export type SeedKind = { name: string; icon: string; color: string; attrs: Record<string, SeedAttr> };

export const SEED_KINDS: Record<string, SeedKind> = {
  character: {
    name: 'Character', icon: '👤', color: '#6366f1',
    attrs: {
      name: { name: 'Name', fieldType: 'text', isRequired: true },
      aliases: { name: 'Aliases', fieldType: 'tags', isRequired: false },
      gender: { name: 'Gender', fieldType: 'text', isRequired: false },
      role: { name: 'Role', fieldType: 'text', isRequired: false },
      occupation: { name: 'Occupation', fieldType: 'text', isRequired: false },
      social_class: { name: 'Social Class', fieldType: 'text', isRequired: false },
      affiliation: { name: 'Affiliation', fieldType: 'text', isRequired: false },
      appearance: { name: 'Appearance', fieldType: 'textarea', isRequired: false },
      personality: { name: 'Personality', fieldType: 'textarea', isRequired: false },
      emotional_wound: { name: 'Emotional Wound', fieldType: 'textarea', isRequired: false },
      love_language: { name: 'Love Language', fieldType: 'text', isRequired: false },
      relationships: { name: 'Relationships', fieldType: 'textarea', isRequired: false },
      description: { name: 'Description', fieldType: 'textarea', isRequired: false },
    },
  },
  location: {
    name: 'Location', icon: '📍', color: '#f59e0b',
    attrs: {
      name: { name: 'Name', fieldType: 'text', isRequired: true },
      aliases: { name: 'Aliases', fieldType: 'tags', isRequired: false },
      type: { name: 'Type', fieldType: 'text', isRequired: false },
      parent_location: { name: 'Parent Location', fieldType: 'text', isRequired: false },
      atmosphere: { name: 'Atmosphere', fieldType: 'textarea', isRequired: false },
      significance: { name: 'Significance', fieldType: 'textarea', isRequired: false },
      description: { name: 'Description', fieldType: 'textarea', isRequired: false },
    },
  },
  item: {
    name: 'Item / Prop', icon: '🎁', color: '#ef4444',
    attrs: {
      name: { name: 'Name', fieldType: 'text', isRequired: true },
      aliases: { name: 'Aliases', fieldType: 'tags', isRequired: false },
      type: { name: 'Type', fieldType: 'text', isRequired: false },
      owner: { name: 'Owner', fieldType: 'text', isRequired: false },
      symbolic_meaning: { name: 'Symbolic Meaning', fieldType: 'textarea', isRequired: false },
      description: { name: 'Description', fieldType: 'textarea', isRequired: false },
    },
  },
  event: {
    name: 'Event', icon: '📅', color: '#10b981',
    attrs: {
      name: { name: 'Name', fieldType: 'text', isRequired: true },
      type: { name: 'Type', fieldType: 'text', isRequired: false },
      date_in_story: { name: 'Date in Story', fieldType: 'text', isRequired: false },
      location: { name: 'Location', fieldType: 'text', isRequired: false },
      participants: { name: 'Participants', fieldType: 'tags', isRequired: false },
      emotional_impact: { name: 'Emotional Impact', fieldType: 'textarea', isRequired: false },
      outcome: { name: 'Outcome', fieldType: 'textarea', isRequired: false },
      description: { name: 'Description', fieldType: 'textarea', isRequired: false },
    },
  },
  terminology: {
    name: 'Terminology', icon: '📖', color: '#f97316',
    attrs: {
      term: { name: 'Term', fieldType: 'text', isRequired: true },
      category: { name: 'Category', fieldType: 'text', isRequired: false },
      definition: { name: 'Definition', fieldType: 'textarea', isRequired: true },
      usage_note: { name: 'Usage Note', fieldType: 'textarea', isRequired: false },
    },
  },
  power_system: {
    name: 'Power System', icon: '✨', color: '#a855f7',
    attrs: {
      name: { name: 'Name', fieldType: 'text', isRequired: true },
      aliases: { name: 'Aliases', fieldType: 'tags', isRequired: false },
      type: { name: 'Type', fieldType: 'text', isRequired: false },
      rank: { name: 'Rank / Tier', fieldType: 'text', isRequired: false },
      user: { name: 'User', fieldType: 'text', isRequired: false },
      effects: { name: 'Effects', fieldType: 'textarea', isRequired: false },
      description: { name: 'Description', fieldType: 'textarea', isRequired: false },
    },
  },
  organization: {
    name: 'Organization', icon: '🏛', color: '#0ea5e9',
    attrs: {
      name: { name: 'Name', fieldType: 'text', isRequired: true },
      aliases: { name: 'Aliases', fieldType: 'tags', isRequired: false },
      type: { name: 'Type', fieldType: 'text', isRequired: false },
      leader: { name: 'Leader', fieldType: 'text', isRequired: false },
      headquarters: { name: 'Headquarters', fieldType: 'text', isRequired: false },
      members: { name: 'Members', fieldType: 'tags', isRequired: false },
      description: { name: 'Description', fieldType: 'textarea', isRequired: false },
    },
  },
  species: {
    name: 'Species / Race', icon: '🧬', color: '#ec4899',
    attrs: {
      name: { name: 'Name', fieldType: 'text', isRequired: true },
      aliases: { name: 'Aliases', fieldType: 'tags', isRequired: false },
      traits: { name: 'Traits', fieldType: 'textarea', isRequired: false },
      abilities: { name: 'Abilities', fieldType: 'textarea', isRequired: false },
      habitat: { name: 'Habitat', fieldType: 'text', isRequired: false },
      culture: { name: 'Culture', fieldType: 'textarea', isRequired: false },
      description: { name: 'Description', fieldType: 'textarea', isRequired: false },
    },
  },
  relationship: {
    name: 'Relationship', icon: '💕', color: '#e879f9',
    attrs: {
      name: { name: 'Name', fieldType: 'text', isRequired: true },
      parties: { name: 'Parties', fieldType: 'tags', isRequired: false },
      relationship_type: { name: 'Relationship Type', fieldType: 'text', isRequired: false },
      status: { name: 'Status', fieldType: 'text', isRequired: false },
      tropes: { name: 'Tropes', fieldType: 'tags', isRequired: false },
      dynamic: { name: 'Dynamic', fieldType: 'textarea', isRequired: false },
      key_conflict: { name: 'Key Conflict', fieldType: 'textarea', isRequired: false },
      turning_points: { name: 'Turning Points', fieldType: 'textarea', isRequired: false },
      resolution: { name: 'Resolution', fieldType: 'textarea', isRequired: false },
      description: { name: 'Description', fieldType: 'textarea', isRequired: false },
    },
  },
  plot_arc: {
    name: 'Plot Arc', icon: '📈', color: '#f43f5e',
    attrs: {
      name: { name: 'Name', fieldType: 'text', isRequired: true },
      arc_type: { name: 'Arc Type', fieldType: 'text', isRequired: false },
      parties: { name: 'Parties', fieldType: 'tags', isRequired: false },
      trigger: { name: 'Trigger', fieldType: 'textarea', isRequired: false },
      stakes: { name: 'Stakes', fieldType: 'textarea', isRequired: false },
      chapters_span: { name: 'Chapters Span', fieldType: 'text', isRequired: false },
      emotional_beats: { name: 'Emotional Beats', fieldType: 'textarea', isRequired: false },
      resolution: { name: 'Resolution', fieldType: 'textarea', isRequired: false },
      description: { name: 'Description', fieldType: 'textarea', isRequired: false },
    },
  },
  trope: {
    name: 'Trope', icon: '🎭', color: '#7c3aed',
    attrs: {
      name: { name: 'Name', fieldType: 'text', isRequired: true },
      category: { name: 'Category', fieldType: 'text', isRequired: false },
      definition: { name: 'Definition', fieldType: 'textarea', isRequired: true },
      how_manifested: { name: 'How Manifested', fieldType: 'textarea', isRequired: false },
      subverted: { name: 'Subverted?', fieldType: 'textarea', isRequired: false },
      related_characters: { name: 'Related Characters', fieldType: 'tags', isRequired: false },
      usage_note: { name: 'Usage Note', fieldType: 'textarea', isRequired: false },
    },
  },
  social_setting: {
    name: 'Social Setting', icon: '🏫', color: '#0891b2',
    attrs: {
      name: { name: 'Name', fieldType: 'text', isRequired: true },
      era: { name: 'Era', fieldType: 'text', isRequired: false },
      location: { name: 'Location', fieldType: 'text', isRequired: false },
      class_hierarchy: { name: 'Class Hierarchy', fieldType: 'textarea', isRequired: false },
      rules_norms: { name: 'Rules & Norms', fieldType: 'textarea', isRequired: false },
      romance_obstacles: { name: 'Romance Obstacles', fieldType: 'textarea', isRequired: false },
      significance: { name: 'Significance', fieldType: 'textarea', isRequired: false },
      description: { name: 'Description', fieldType: 'textarea', isRequired: false },
    },
  },
};

/** Count how many fields on a system kind differ from seed defaults. */
export function countKindModifications(kind: { code: string; name: string; icon: string; color: string; default_attributes: Array<{ code: string; name: string; field_type: string; is_required: boolean; is_system: boolean }> }): number {
  const seed = SEED_KINDS[kind.code];
  if (!seed) return 0;
  let count = 0;
  if (kind.name !== seed.name) count++;
  if (kind.icon !== seed.icon) count++;
  if (kind.color !== seed.color) count++;
  for (const attr of kind.default_attributes) {
    if (!attr.is_system) continue;
    const seedAttr = seed.attrs[attr.code];
    if (!seedAttr) continue;
    if (attr.name !== seedAttr.name) count++;
  }
  return count;
}

/** Check if a single attribute is modified from seed. */
export function isAttrModified(kindCode: string, attr: { code: string; name: string; is_system: boolean }): boolean {
  if (!attr.is_system) return false;
  const seed = SEED_KINDS[kindCode];
  if (!seed) return false;
  const seedAttr = seed.attrs[attr.code];
  if (!seedAttr) return false;
  return attr.name !== seedAttr.name;
}

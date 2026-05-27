// Placeholder item definitions. Session E+ fetches from backend; for
// V0 demo this static table is enough. Per spec §9 pattern #6
// (data-driven design).

export interface ItemDef {
  id: string;
  name: string;
  rarity: 'common' | 'rare' | 'epic';
  iconKey: string;
}

export const ITEMS: Record<string, ItemDef> = {
  'wood-sword': { id: 'wood-sword', name: 'Wooden Sword', rarity: 'common', iconKey: 'icon-sword' },
  'iron-shield': { id: 'iron-shield', name: 'Iron Shield', rarity: 'common', iconKey: 'icon-shield' },
};

// Game-domain TS types shared between React and Phaser layers.

export type PlayerId = string;
export type CharacterId = string;
export type ZoneId = string;

export interface Vitals {
  hp: number;
  maxHp: number;
  mp: number;
  maxMp: number;
}

export interface CharacterSummary {
  id: CharacterId;
  name: string;
  level: number;
  vitals: Vitals;
}

export interface ItemRef {
  id: string;
  qty: number;
}

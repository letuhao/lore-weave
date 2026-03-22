import { useState, useReducer, useMemo, useCallback, useRef, useEffect } from "react";
import { Search, Plus, ChevronDown, ChevronRight, GripVertical, X, Check, Edit3, Trash2, Copy, MoreHorizontal, Link2, Unlink, BookOpen, Globe, FileText, AlertTriangle, Star, Eye, EyeOff, Filter, Tag } from "lucide-react";

// ═══════════════════════════════════════════════════════════
// DATA & TYPES
// ═══════════════════════════════════════════════════════════

const LANGUAGES = [
  { code: "zh", name: "Chinese", native: "中文", flag: "🇨🇳" },
  { code: "en", name: "English", native: "English", flag: "🇬🇧" },
  { code: "ja", name: "Japanese", native: "日本語", flag: "🇯🇵" },
  { code: "ko", name: "Korean", native: "한국어", flag: "🇰🇷" },
  { code: "vi", name: "Vietnamese", native: "Tiếng Việt", flag: "🇻🇳" },
  { code: "th", name: "Thai", native: "ไทย", flag: "🇹🇭" },
  { code: "es", name: "Spanish", native: "Español", flag: "🇪🇸" },
  { code: "fr", name: "French", native: "Français", flag: "🇫🇷" },
];

const ENTITY_KINDS = [
  { id: "character", code: "character", name: "Character", icon: "👤", color: "#6366f1", defaultAttributes: ["name","aliases","gender","role","affiliation","appearance","personality","description"] },
  { id: "location", code: "location", name: "Location", icon: "📍", color: "#f59e0b", defaultAttributes: ["name","aliases","type","parent_location","description","significance"] },
  { id: "item", code: "item", name: "Item", icon: "⚔️", color: "#ef4444", defaultAttributes: ["name","aliases","type","rarity","owner","abilities","description"] },
  { id: "power_system", code: "power_system", name: "Power System", icon: "✨", color: "#a855f7", defaultAttributes: ["name","aliases","type","rank","user","effects","description"] },
  { id: "organization", code: "organization", name: "Organization", icon: "🏛", color: "#0ea5e9", defaultAttributes: ["name","aliases","type","leader","headquarters","members","description"] },
  { id: "event", code: "event", name: "Event", icon: "📅", color: "#10b981", defaultAttributes: ["name","type","date_in_story","location","participants","outcome","description"] },
  { id: "terminology", code: "terminology", name: "Terminology", icon: "📖", color: "#f97316", defaultAttributes: ["term","category","definition","usage_note"] },
  { id: "species", code: "species", name: "Species", icon: "🧬", color: "#ec4899", defaultAttributes: ["name","aliases","traits","abilities","habitat","culture","description"] },
];

const ATTR_DEFS = {
  name: { code: "name", name: "Name", fieldType: "text", isRequired: true },
  term: { code: "term", name: "Term", fieldType: "text", isRequired: true },
  aliases: { code: "aliases", name: "Aliases", fieldType: "tags" },
  gender: { code: "gender", name: "Gender", fieldType: "select", options: ["Male","Female","Non-binary","Other","Unknown"] },
  role: { code: "role", name: "Role", fieldType: "select", options: ["Protagonist","Antagonist","Supporting","Minor","Mentioned"] },
  affiliation: { code: "affiliation", name: "Affiliation", fieldType: "text" },
  cultivation_level: { code: "cultivation_level", name: "Power Level", fieldType: "text" },
  appearance: { code: "appearance", name: "Appearance", fieldType: "textarea" },
  personality: { code: "personality", name: "Personality", fieldType: "textarea" },
  relationships: { code: "relationships", name: "Relationships", fieldType: "textarea" },
  description: { code: "description", name: "Description", fieldType: "textarea" },
  significance: { code: "significance", name: "Significance", fieldType: "textarea" },
  type: { code: "type", name: "Type", fieldType: "select", options: ["City","Region","Building","Realm","Dimension","Landmark","Weapon","Armor","Tool","Consumable","Treasure","Martial Art","Spell","Skill","Passive","Bloodline","Sect","Kingdom","Company","Guild","Family","Battle","Ceremony","Disaster","Discovery","Cultural","Technical","Magical","Political","Other"] },
  parent_location: { code: "parent_location", name: "Parent Location", fieldType: "text" },
  rarity: { code: "rarity", name: "Rarity", fieldType: "select", options: ["Common","Uncommon","Rare","Legendary","Unique"] },
  owner: { code: "owner", name: "Owner", fieldType: "text" },
  abilities: { code: "abilities", name: "Abilities", fieldType: "textarea" },
  rank: { code: "rank", name: "Rank / Tier", fieldType: "text" },
  user: { code: "user", name: "Known Users", fieldType: "text" },
  effects: { code: "effects", name: "Effects", fieldType: "textarea" },
  requirements: { code: "requirements", name: "Requirements", fieldType: "textarea" },
  leader: { code: "leader", name: "Leader", fieldType: "text" },
  headquarters: { code: "headquarters", name: "Headquarters", fieldType: "text" },
  members: { code: "members", name: "Notable Members", fieldType: "textarea" },
  purpose: { code: "purpose", name: "Purpose / Goal", fieldType: "textarea" },
  date_in_story: { code: "date_in_story", name: "Date (In-Story)", fieldType: "text" },
  location: { code: "location", name: "Location", fieldType: "text" },
  participants: { code: "participants", name: "Participants", fieldType: "textarea" },
  outcome: { code: "outcome", name: "Outcome", fieldType: "textarea" },
  category: { code: "category", name: "Category", fieldType: "select", options: ["Cultural","Technical","Magical","Political","Religious","Other"] },
  definition: { code: "definition", name: "Definition", fieldType: "textarea", isRequired: true },
  usage_note: { code: "usage_note", name: "Usage Notes", fieldType: "textarea" },
  traits: { code: "traits", name: "Physical Traits", fieldType: "textarea" },
  habitat: { code: "habitat", name: "Habitat", fieldType: "text" },
  culture: { code: "culture", name: "Culture", fieldType: "textarea" },
};

const CHAPTERS = Array.from({ length: 20 }, (_, i) => ({
  id: `ch${i + 1}`,
  index: i,
  title: `Chapter ${i + 1}`,
}));

let _id = 100;
const uid = () => `id_${++_id}`;

const makeSampleEntities = () => [
  {
    id: "e1", bookId: "b1", kindId: "character",
    kind: ENTITY_KINDS[0],
    chapterLinks: [
      { id: "cl1", chapterId: "ch1", chapterTitle: "Chapter 1", chapterIndex: 0, relevance: "major", note: "First introduced" },
      { id: "cl2", chapterId: "ch3", chapterTitle: "Chapter 3", chapterIndex: 2, relevance: "appears" },
      { id: "cl3", chapterId: "ch7", chapterTitle: "Chapter 7", chapterIndex: 6, relevance: "major", note: "Major battle scene" },
    ],
    attributeValues: [
      { id: "av1", attributeDefinitionId: "name", originalLanguage: "zh", originalValue: "林默",
        translations: [
          { id: "t1", languageCode: "en", value: "Lin Mo", confidence: "verified", updatedAt: "2025-01-15" },
          { id: "t2", languageCode: "ja", value: "リン・モー", confidence: "draft", updatedAt: "2025-01-16" },
          { id: "t3", languageCode: "ko", value: "린모", confidence: "machine", updatedAt: "2025-01-17" },
        ],
        evidences: [
          { id: "ev1", location: { chapterIndex: 0, chapterId: "ch1", chapterTitle: "Chapter 1", blockOrLine: "Line 34" }, type: "quote", originalLanguage: "zh", originalText: "少年名叫林默，是云山派的外门弟子。", translations: [{ id: "et1", languageCode: "en", value: "The young man was named Lin Mo, an outer disciple of the Cloud Mountain Sect.", confidence: "verified", updatedAt: "2025-01-15" }], createdAt: "2025-01-10" },
        ]
      },
      { id: "av2", attributeDefinitionId: "gender", originalLanguage: "en", originalValue: "Male", translations: [], evidences: [] },
      { id: "av3", attributeDefinitionId: "role", originalLanguage: "en", originalValue: "Protagonist", translations: [], evidences: [] },
      { id: "av4", attributeDefinitionId: "affiliation", originalLanguage: "zh", originalValue: "云山派",
        translations: [{ id: "t4", languageCode: "en", value: "Cloud Mountain Sect", confidence: "verified", updatedAt: "2025-01-15" }],
        evidences: []
      },
      { id: "av5", attributeDefinitionId: "description", originalLanguage: "en", originalValue: "A talented but low-ranking disciple who discovers a hidden cultivation technique.", translations: [], evidences: [] },
    ],
    status: "active", tags: ["protagonist", "cultivator"], createdAt: "2025-01-10", updatedAt: "2025-01-20",
  },
  {
    id: "e2", bookId: "b1", kindId: "location",
    kind: ENTITY_KINDS[1],
    chapterLinks: [
      { id: "cl4", chapterId: "ch1", chapterTitle: "Chapter 1", chapterIndex: 0, relevance: "major" },
      { id: "cl5", chapterId: "ch2", chapterTitle: "Chapter 2", chapterIndex: 1, relevance: "appears" },
    ],
    attributeValues: [
      { id: "av6", attributeDefinitionId: "name", originalLanguage: "zh", originalValue: "云山",
        translations: [{ id: "t5", languageCode: "en", value: "Cloud Mountain", confidence: "verified", updatedAt: "2025-01-15" }],
        evidences: []
      },
      { id: "av7", attributeDefinitionId: "description", originalLanguage: "en", originalValue: "A mist-shrouded mountain range home to one of the five great sects.", translations: [], evidences: [] },
    ],
    status: "active", tags: ["setting", "sect-territory"], createdAt: "2025-01-10", updatedAt: "2025-01-18",
  },
  {
    id: "e3", bookId: "b1", kindId: "item",
    kind: ENTITY_KINDS[2],
    chapterLinks: [
      { id: "cl6", chapterId: "ch5", chapterTitle: "Chapter 5", chapterIndex: 4, relevance: "major", note: "Discovered in the cave" },
    ],
    attributeValues: [
      { id: "av8", attributeDefinitionId: "name", originalLanguage: "zh", originalValue: "破天剑",
        translations: [{ id: "t6", languageCode: "en", value: "Heaven-Splitting Sword", confidence: "draft", updatedAt: "2025-01-20" }],
        evidences: []
      },
      { id: "av9", attributeDefinitionId: "rarity", originalLanguage: "en", originalValue: "Legendary", translations: [], evidences: [] },
    ],
    status: "active", tags: ["weapon", "legendary"], createdAt: "2025-01-12", updatedAt: "2025-01-20",
  },
  {
    id: "e4", bookId: "b1", kindId: "terminology",
    kind: ENTITY_KINDS[6],
    chapterLinks: [],
    attributeValues: [
      { id: "av10", attributeDefinitionId: "term", originalLanguage: "zh", originalValue: "气",
        translations: [{ id: "t7", languageCode: "en", value: "Qi", confidence: "verified", updatedAt: "2025-01-10" }],
        evidences: []
      },
      { id: "av11", attributeDefinitionId: "definition", originalLanguage: "en", originalValue: "The fundamental life energy that cultivators harness to gain supernatural abilities.", translations: [], evidences: [] },
    ],
    status: "draft", tags: ["cultivation", "core-concept"], createdAt: "2025-01-08", updatedAt: "2025-01-08",
  },
  {
    id: "e5", bookId: "b1", kindId: "organization",
    kind: ENTITY_KINDS[4],
    chapterLinks: [
      { id: "cl7", chapterId: "ch1", chapterTitle: "Chapter 1", chapterIndex: 0, relevance: "major" },
      { id: "cl8", chapterId: "ch3", chapterTitle: "Chapter 3", chapterIndex: 2, relevance: "appears" },
      { id: "cl9", chapterId: "ch8", chapterTitle: "Chapter 8", chapterIndex: 7, relevance: "mentioned" },
    ],
    attributeValues: [
      { id: "av12", attributeDefinitionId: "name", originalLanguage: "zh", originalValue: "云山派",
        translations: [{ id: "t8", languageCode: "en", value: "Cloud Mountain Sect", confidence: "verified", updatedAt: "2025-01-10" }],
        evidences: []
      },
      { id: "av13", attributeDefinitionId: "leader", originalLanguage: "zh", originalValue: "白云真人",
        translations: [{ id: "t9", languageCode: "en", value: "Master Baiyun", confidence: "draft", updatedAt: "2025-01-15" }],
        evidences: []
      },
    ],
    status: "active", tags: ["sect", "ally"], createdAt: "2025-01-10", updatedAt: "2025-01-15",
  },
];

// ═══════════════════════════════════════════════════════════
// REDUCER
// ═══════════════════════════════════════════════════════════

const initialState = {
  entities: makeSampleEntities(),
  filters: { chapterIds: "all", kindCodes: [], status: "all", searchQuery: "", tags: [] },
  selectedEntityId: null,
  detailOpen: false,
  createModalOpen: false,
  toast: null,
};

function reducer(state, action) {
  switch (action.type) {
    case "SET_FILTER": return { ...state, filters: { ...state.filters, ...action.payload } };
    case "SELECT_ENTITY": return { ...state, selectedEntityId: action.id, detailOpen: true };
    case "CLOSE_DETAIL": return { ...state, detailOpen: false };
    case "OPEN_CREATE": return { ...state, createModalOpen: true };
    case "CLOSE_CREATE": return { ...state, createModalOpen: false };
    case "CREATE_ENTITY": {
      const kind = ENTITY_KINDS.find(k => k.id === action.kindId);
      const attrs = (kind?.defaultAttributes || []).map(code => ({
        id: uid(), attributeDefinitionId: code, originalLanguage: "zh", originalValue: "",
        translations: [], evidences: [],
      }));
      const entity = {
        id: uid(), bookId: "b1", kindId: action.kindId, kind,
        chapterLinks: [], attributeValues: attrs,
        status: "draft", tags: [], createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
      };
      return { ...state, entities: [...state.entities, entity], selectedEntityId: entity.id, detailOpen: true, createModalOpen: false };
    }
    case "DELETE_ENTITY":
      return { ...state, entities: state.entities.filter(e => e.id !== action.id), selectedEntityId: null, detailOpen: false };
    case "UPDATE_ENTITY":
      return { ...state, entities: state.entities.map(e => e.id === action.id ? { ...e, ...action.changes, updatedAt: new Date().toISOString() } : e) };
    case "LINK_CHAPTER": {
      return { ...state, entities: state.entities.map(e => {
        if (e.id !== action.entityId) return e;
        if (e.chapterLinks.some(cl => cl.chapterId === action.link.chapterId)) return e;
        return { ...e, chapterLinks: [...e.chapterLinks, action.link].sort((a, b) => (a.chapterIndex || 0) - (b.chapterIndex || 0)), updatedAt: new Date().toISOString() };
      })};
    }
    case "UNLINK_CHAPTER":
      return { ...state, entities: state.entities.map(e => e.id !== action.entityId ? e : { ...e, chapterLinks: e.chapterLinks.filter(cl => cl.id !== action.linkId), updatedAt: new Date().toISOString() }) };
    case "UPDATE_ATTR_VALUE":
      return { ...state, entities: state.entities.map(e => {
        if (e.id !== action.entityId) return e;
        return { ...e, attributeValues: e.attributeValues.map(av => av.id === action.attrValueId ? { ...av, ...action.changes } : av), updatedAt: new Date().toISOString() };
      })};
    case "ADD_TRANSLATION":
      return { ...state, entities: state.entities.map(e => {
        if (e.id !== action.entityId) return e;
        return { ...e, attributeValues: e.attributeValues.map(av => av.id === action.attrValueId ? { ...av, translations: [...av.translations, action.translation] } : av), updatedAt: new Date().toISOString() };
      })};
    case "REMOVE_TRANSLATION":
      return { ...state, entities: state.entities.map(e => {
        if (e.id !== action.entityId) return e;
        return { ...e, attributeValues: e.attributeValues.map(av => av.id === action.attrValueId ? { ...av, translations: av.translations.filter(t => t.id !== action.translationId) } : av), updatedAt: new Date().toISOString() };
      })};
    case "ADD_EVIDENCE":
      return { ...state, entities: state.entities.map(e => {
        if (e.id !== action.entityId) return e;
        return { ...e, attributeValues: e.attributeValues.map(av => av.id === action.attrValueId ? { ...av, evidences: [...av.evidences, action.evidence] } : av), updatedAt: new Date().toISOString() };
      })};
    case "REMOVE_EVIDENCE":
      return { ...state, entities: state.entities.map(e => {
        if (e.id !== action.entityId) return e;
        return { ...e, attributeValues: e.attributeValues.map(av => av.id === action.attrValueId ? { ...av, evidences: av.evidences.filter(ev => ev.id !== action.evidenceId) } : av), updatedAt: new Date().toISOString() };
      })};
    case "SHOW_TOAST": return { ...state, toast: action.message };
    case "HIDE_TOAST": return { ...state, toast: null };
    default: return state;
  }
}

// ═══════════════════════════════════════════════════════════
// UTILITY COMPONENTS
// ═══════════════════════════════════════════════════════════

const langInfo = (code) => LANGUAGES.find(l => l.code === code) || { code, name: code, native: code, flag: "🌐" };

function Badge({ children, color, small, onClick, className = "" }) {
  return (
    <span onClick={onClick} className={className} style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: small ? "1px 6px" : "2px 10px",
      borderRadius: 999, fontSize: small ? 10 : 11, fontWeight: 600,
      background: color ? `${color}18` : "var(--surface-2)",
      color: color || "var(--text-2)",
      border: `1px solid ${color ? `${color}30` : "var(--border)"}`,
      cursor: onClick ? "pointer" : "default",
      transition: "all 0.15s",
      letterSpacing: "0.02em",
    }}>{children}</span>
  );
}

function ConfidenceDot({ confidence }) {
  const colors = { verified: "#10b981", draft: "#f59e0b", machine: "#94a3b8" };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 10, color: colors[confidence] || "#94a3b8" }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: colors[confidence] || "#94a3b8" }} />
      {confidence}
    </span>
  );
}

function IconBtn({ icon: Icon, onClick, title, danger, size = 14, disabled }) {
  return (
    <button onClick={onClick} title={title} disabled={disabled} style={{
      background: "none", border: "none", cursor: disabled ? "not-allowed" : "pointer", padding: 4, borderRadius: 4,
      color: danger ? "#ef4444" : "var(--text-3)", opacity: disabled ? 0.3 : 0.7,
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      transition: "all 0.15s",
    }}
    onMouseEnter={e => { if (!disabled) e.currentTarget.style.opacity = "1"; e.currentTarget.style.background = danger ? "#fef2f2" : "var(--surface-2)"; }}
    onMouseLeave={e => { e.currentTarget.style.opacity = disabled ? "0.3" : "0.7"; e.currentTarget.style.background = "none"; }}
    ><Icon size={size} /></button>
  );
}

function Dropdown({ value, onChange, options, placeholder, style }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={{
      padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)",
      background: "var(--surface-1)", color: "var(--text-1)", fontSize: 12,
      outline: "none", cursor: "pointer", ...style,
    }}>
      {placeholder && <option value="">{placeholder}</option>}
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

function Toast({ message, onClose }) {
  useEffect(() => { const t = setTimeout(onClose, 3500); return () => clearTimeout(t); }, [onClose]);
  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24, zIndex: 9999,
      background: "var(--text-1)", color: "var(--surface-0)", padding: "10px 18px",
      borderRadius: 10, fontSize: 13, fontWeight: 500, boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
      display: "flex", alignItems: "center", gap: 8, animation: "slideUp 0.3s ease",
    }}>
      <Check size={14} /> {message}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// FILTERS BAR
// ═══════════════════════════════════════════════════════════

function FiltersBar({ filters, dispatch, entityCount, unlinkCount }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{ background: "var(--surface-1)", borderRadius: 12, border: "1px solid var(--border)", padding: "12px 16px", marginBottom: 16 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 180 }}>
          <BookOpen size={14} style={{ color: "var(--text-3)" }} />
          <select value={filters.chapterIds === "all" ? "all" : filters.chapterIds === "unlinked" ? "unlinked" : "custom"}
            onChange={e => {
              const v = e.target.value;
              if (v === "all" || v === "unlinked") dispatch({ type: "SET_FILTER", payload: { chapterIds: v } });
              else dispatch({ type: "SET_FILTER", payload: { chapterIds: [] } });
            }}
            style={{ padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-0)", fontSize: 12, color: "var(--text-1)" }}>
            <option value="all">All Chapters</option>
            <option value="unlinked">Unlinked Only</option>
            <option value="custom">Select Chapters…</option>
          </select>
          {Array.isArray(filters.chapterIds) && (
            <select multiple value={filters.chapterIds}
              onChange={e => dispatch({ type: "SET_FILTER", payload: { chapterIds: Array.from(e.target.selectedOptions, o => o.value) } })}
              style={{ padding: 4, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-0)", fontSize: 11, maxHeight: 80, minWidth: 120, color: "var(--text-1)" }}>
              {CHAPTERS.map(ch => <option key={ch.id} value={ch.id}>{ch.title}</option>)}
            </select>
          )}
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {["all", "active", "inactive", "draft"].map(s => (
            <button key={s} onClick={() => dispatch({ type: "SET_FILTER", payload: { status: s } })}
              style={{
                padding: "4px 10px", borderRadius: 6, fontSize: 11, fontWeight: 500, cursor: "pointer", textTransform: "capitalize",
                border: filters.status === s ? "1px solid var(--accent)" : "1px solid var(--border)",
                background: filters.status === s ? "var(--accent-bg)" : "var(--surface-0)",
                color: filters.status === s ? "var(--accent)" : "var(--text-2)",
              }}>{s}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {ENTITY_KINDS.map(k => {
            const active = filters.kindCodes.includes(k.code);
            return (
              <button key={k.code} onClick={() => {
                const next = active ? filters.kindCodes.filter(c => c !== k.code) : [...filters.kindCodes, k.code];
                dispatch({ type: "SET_FILTER", payload: { kindCodes: next } });
              }} style={{
                padding: "3px 8px", borderRadius: 6, fontSize: 11, cursor: "pointer",
                border: active ? `1px solid ${k.color}` : "1px solid var(--border)",
                background: active ? `${k.color}15` : "var(--surface-0)",
                color: active ? k.color : "var(--text-3)",
                display: "flex", alignItems: "center", gap: 3,
              }}><span>{k.icon}</span> {k.name}</button>
            );
          })}
        </div>
        <div style={{ flex: 1, minWidth: 160 }}>
          <div style={{ position: "relative" }}>
            <Search size={13} style={{ position: "absolute", left: 8, top: 7, color: "var(--text-3)" }} />
            <input value={filters.searchQuery} onChange={e => dispatch({ type: "SET_FILTER", payload: { searchQuery: e.target.value } })}
              placeholder="Search glossary…"
              style={{ width: "100%", padding: "5px 8px 5px 28px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-0)", fontSize: 12, color: "var(--text-1)", outline: "none" }} />
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8, fontSize: 11, color: "var(--text-3)" }}>
        <span>{entityCount} entries</span>
        {unlinkCount > 0 && <Badge color="#f59e0b" small><AlertTriangle size={10} /> {unlinkCount} unlinked</Badge>}
        {Array.isArray(filters.chapterIds) && filters.chapterIds.map(cid => {
          const ch = CHAPTERS.find(c => c.id === cid);
          return ch ? <Badge key={cid} small onClick={() => dispatch({ type: "SET_FILTER", payload: { chapterIds: filters.chapterIds.filter(id => id !== cid) } })} className="cursor-pointer">{ch.title} <X size={8} /></Badge> : null;
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// ENTITY CARD
// ═══════════════════════════════════════════════════════════

function EntityCard({ entity, isSelected, onSelect }) {
  const nameAttr = entity.attributeValues.find(av => av.attributeDefinitionId === "name" || av.attributeDefinitionId === "term");
  const name = nameAttr?.originalValue || "(untitled)";
  const enTrans = nameAttr?.translations?.find(t => t.languageCode === "en");
  const totalTranslations = new Set(entity.attributeValues.flatMap(av => av.translations.map(t => t.languageCode))).size;
  const totalEvidences = entity.attributeValues.reduce((sum, av) => sum + av.evidences.length, 0);

  return (
    <div onClick={() => onSelect(entity.id)} style={{
      display: "flex", borderRadius: 10, border: isSelected ? `2px solid ${entity.kind.color}` : "1px solid var(--border)",
      background: isSelected ? `${entity.kind.color}08` : "var(--surface-1)",
      cursor: "pointer", overflow: "hidden", transition: "all 0.2s",
      marginBottom: 6,
    }}
    onMouseEnter={e => { if (!isSelected) e.currentTarget.style.borderColor = entity.kind.color + "60"; }}
    onMouseLeave={e => { if (!isSelected) e.currentTarget.style.borderColor = "var(--border)"; }}
    >
      <div style={{ width: 4, background: entity.kind.color, flexShrink: 0 }} />
      <div style={{ padding: "10px 14px", flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
            <span style={{ fontSize: 15, fontWeight: 700, color: "var(--text-1)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {name}
            </span>
            {enTrans && <span style={{ fontSize: 12, color: "var(--text-3)", whiteSpace: "nowrap" }}>({enTrans.value})</span>}
          </div>
          <Badge color={entity.status === "active" ? "#10b981" : entity.status === "draft" ? "#f59e0b" : "#94a3b8"} small>
            {entity.status}
          </Badge>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginBottom: 4 }}>
          <Badge color={entity.kind.color} small>{entity.kind.icon} {entity.kind.name}</Badge>
          {entity.chapterLinks.length === 0 ? (
            <span style={{ fontSize: 10, color: "#f59e0b", display: "flex", alignItems: "center", gap: 3 }}>
              <AlertTriangle size={10} /> No chapters linked
            </span>
          ) : (
            <span style={{ fontSize: 10, color: "var(--text-3)", display: "flex", gap: 3, flexWrap: "wrap" }}>
              📖 {entity.chapterLinks.slice(0, 4).map(cl => <span key={cl.id} style={{ background: "var(--surface-2)", padding: "0 4px", borderRadius: 3 }}>Ch.{cl.chapterIndex + 1}</span>)}
              {entity.chapterLinks.length > 4 && <span>+{entity.chapterLinks.length - 4}</span>}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 10, color: "var(--text-3)" }}>
          {totalTranslations > 0 && <span>🌐 {totalTranslations} lang{totalTranslations > 1 ? "s" : ""}</span>}
          {totalEvidences > 0 && <span>📎 {totalEvidences} evidence{totalEvidences > 1 ? "s" : ""}</span>}
          {entity.tags.map(t => <Badge key={t} small><Tag size={8} /> {t}</Badge>)}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// CHAPTER LINK EDITOR
// ═══════════════════════════════════════════════════════════

function ChapterLinkEditor({ entity, dispatch }) {
  const [adding, setAdding] = useState(false);
  const [newChId, setNewChId] = useState("");
  const [newRelevance, setNewRelevance] = useState("appears");
  const [newNote, setNewNote] = useState("");

  const linkedIds = new Set(entity.chapterLinks.map(cl => cl.chapterId));
  const available = CHAPTERS.filter(ch => !linkedIds.has(ch.id));

  const handleLink = () => {
    if (!newChId) return;
    const ch = CHAPTERS.find(c => c.id === newChId);
    dispatch({ type: "LINK_CHAPTER", entityId: entity.id, link: {
      id: uid(), chapterId: newChId, chapterTitle: ch.title, chapterIndex: ch.index,
      relevance: newRelevance, note: newNote || undefined, addedAt: new Date().toISOString(),
    }});
    setNewChId(""); setNewNote(""); setAdding(false);
    dispatch({ type: "SHOW_TOAST", message: `Linked to ${ch.title}` });
  };

  const relevanceColors = { major: "#6366f1", appears: "#10b981", mentioned: "#94a3b8" };
  const relevanceIcons = { major: "★", appears: "●", mentioned: "○" };

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          <Link2 size={11} style={{ marginRight: 4, verticalAlign: "middle" }} />Linked Chapters
        </span>
        <button onClick={() => setAdding(!adding)} style={{
          background: "none", border: "1px solid var(--border)", borderRadius: 6, padding: "2px 8px",
          fontSize: 11, color: "var(--accent)", cursor: "pointer", display: "flex", alignItems: "center", gap: 3,
        }}><Plus size={11} /> Link</button>
      </div>

      {entity.chapterLinks.length === 0 && !adding && (
        <div style={{ padding: "12px 16px", borderRadius: 8, background: "#fef3c710", border: "1px dashed #f59e0b40", textAlign: "center", fontSize: 12, color: "var(--text-3)" }}>
          <AlertTriangle size={14} style={{ color: "#f59e0b", marginBottom: 4 }} /><br />
          No chapters linked yet. Link this entity to chapters where it appears.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {entity.chapterLinks.map(cl => (
          <div key={cl.id} style={{
            display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
            borderRadius: 8, background: "var(--surface-0)", border: "1px solid var(--border)",
          }}>
            <span style={{ fontSize: 13 }}>📖</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-1)", flex: 1 }}>{cl.chapterTitle}</span>
            <select value={cl.relevance} onChange={e => {
              dispatch({ type: "UPDATE_ENTITY", id: entity.id, changes: {
                chapterLinks: entity.chapterLinks.map(c => c.id === cl.id ? { ...c, relevance: e.target.value } : c)
              }});
            }} style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, border: `1px solid ${relevanceColors[cl.relevance]}40`, background: `${relevanceColors[cl.relevance]}10`, color: relevanceColors[cl.relevance], cursor: "pointer" }}>
              <option value="major">★ major</option>
              <option value="appears">● appears</option>
              <option value="mentioned">○ mentioned</option>
            </select>
            {cl.note && <span style={{ fontSize: 10, color: "var(--text-3)", fontStyle: "italic", maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>"{cl.note}"</span>}
            <IconBtn icon={X} size={12} onClick={() => dispatch({ type: "UNLINK_CHAPTER", entityId: entity.id, linkId: cl.id })} danger title="Unlink chapter" />
          </div>
        ))}
      </div>

      {adding && (
        <div style={{ marginTop: 8, padding: 12, borderRadius: 8, background: "var(--surface-0)", border: "1px solid var(--accent-border)" }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <Dropdown value={newChId} onChange={setNewChId} placeholder="Select chapter…"
              options={available.map(ch => ({ value: ch.id, label: ch.title }))} style={{ flex: 1, minWidth: 140 }} />
            <div style={{ display: "flex", gap: 3 }}>
              {["appears", "major", "mentioned"].map(r => (
                <button key={r} onClick={() => setNewRelevance(r)} style={{
                  padding: "3px 8px", borderRadius: 4, fontSize: 10, cursor: "pointer",
                  border: newRelevance === r ? `1px solid ${relevanceColors[r]}` : "1px solid var(--border)",
                  background: newRelevance === r ? `${relevanceColors[r]}15` : "transparent",
                  color: newRelevance === r ? relevanceColors[r] : "var(--text-3)",
                }}>{relevanceIcons[r]} {r}</button>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}>
            <input value={newNote} onChange={e => setNewNote(e.target.value)} placeholder="Note (optional)…"
              style={{ flex: 1, padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-1)", fontSize: 11, color: "var(--text-1)" }} />
            <button onClick={handleLink} disabled={!newChId} style={{
              padding: "5px 14px", borderRadius: 6, border: "none", background: newChId ? "var(--accent)" : "var(--surface-2)",
              color: newChId ? "#fff" : "var(--text-3)", fontSize: 11, fontWeight: 600, cursor: newChId ? "pointer" : "not-allowed",
            }}>Link</button>
            <button onClick={() => setAdding(false)} style={{ padding: "5px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "none", fontSize: 11, color: "var(--text-3)", cursor: "pointer" }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// TRANSLATION LIST
// ═══════════════════════════════════════════════════════════

function TranslationList({ translations, existingLangs, entityId, attrValueId, dispatch }) {
  const [adding, setAdding] = useState(false);
  const [lang, setLang] = useState("");
  const [val, setVal] = useState("");
  const [conf, setConf] = useState("draft");

  const availLangs = LANGUAGES.filter(l => !existingLangs.includes(l.code));

  const handleAdd = () => {
    if (!lang || !val) return;
    dispatch({ type: "ADD_TRANSLATION", entityId, attrValueId, translation: {
      id: uid(), languageCode: lang, value: val, confidence: conf, updatedAt: new Date().toISOString(),
    }});
    setLang(""); setVal(""); setAdding(false);
  };

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Translations</span>
        <button onClick={() => setAdding(!adding)} style={{ background: "none", border: "none", fontSize: 10, color: "var(--accent)", cursor: "pointer", display: "flex", alignItems: "center", gap: 2 }}>
          <Plus size={10} /> Add
        </button>
      </div>
      {translations.length === 0 && !adding && (
        <div style={{ fontSize: 11, color: "var(--text-3)", fontStyle: "italic", padding: "4px 0" }}>No translations yet</div>
      )}
      {translations.map(t => {
        const li = langInfo(t.languageCode);
        return (
          <div key={t.id} style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px", borderRadius: 6, background: "var(--surface-0)", marginBottom: 3, border: "1px solid var(--border)" }}>
            <span style={{ fontSize: 12 }}>{li.flag}</span>
            <span style={{ fontSize: 10, color: "var(--text-3)", minWidth: 20 }}>{t.languageCode}</span>
            <span style={{ flex: 1, fontSize: 12, color: "var(--text-1)", fontWeight: 500 }}>{t.value}</span>
            <ConfidenceDot confidence={t.confidence} />
            <IconBtn icon={X} size={10} danger onClick={() => dispatch({ type: "REMOVE_TRANSLATION", entityId, attrValueId, translationId: t.id })} />
          </div>
        );
      })}
      {adding && (
        <div style={{ padding: 8, borderRadius: 6, background: "var(--surface-0)", border: "1px solid var(--accent-border)", marginTop: 4 }}>
          <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
            <Dropdown value={lang} onChange={setLang} placeholder="Language…"
              options={availLangs.map(l => ({ value: l.code, label: `${l.flag} ${l.name}` }))} style={{ minWidth: 120 }} />
            <div style={{ display: "flex", gap: 3 }}>
              {["draft", "machine", "verified"].map(c => (
                <button key={c} onClick={() => setConf(c)} style={{
                  padding: "2px 6px", borderRadius: 4, fontSize: 9, cursor: "pointer",
                  border: conf === c ? "1px solid var(--accent)" : "1px solid var(--border)",
                  background: conf === c ? "var(--accent-bg)" : "transparent",
                  color: conf === c ? "var(--accent)" : "var(--text-3)",
                }}>{c}</button>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <input value={val} onChange={e => setVal(e.target.value)} placeholder="Translated value…"
              style={{ flex: 1, padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)", fontSize: 12, background: "var(--surface-1)", color: "var(--text-1)" }}
              onKeyDown={e => e.key === "Enter" && handleAdd()} />
            <button onClick={handleAdd} disabled={!lang || !val} style={{
              padding: "5px 12px", borderRadius: 6, border: "none", fontSize: 11, fontWeight: 600, cursor: lang && val ? "pointer" : "not-allowed",
              background: lang && val ? "var(--accent)" : "var(--surface-2)", color: lang && val ? "#fff" : "var(--text-3)",
            }}>Add</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// EVIDENCE LIST
// ═══════════════════════════════════════════════════════════

function EvidenceList({ evidences, entityId, attrValueId, dispatch }) {
  const [adding, setAdding] = useState(false);
  const [evChapter, setEvChapter] = useState("");
  const [evBlock, setEvBlock] = useState("");
  const [evType, setEvType] = useState("quote");
  const [evLang, setEvLang] = useState("zh");
  const [evText, setEvText] = useState("");

  const handleAdd = () => {
    if (!evChapter || !evText) return;
    const ch = CHAPTERS.find(c => c.id === evChapter);
    dispatch({ type: "ADD_EVIDENCE", entityId, attrValueId, evidence: {
      id: uid(), location: { chapterIndex: ch.index, chapterId: ch.id, chapterTitle: ch.title, blockOrLine: evBlock },
      type: evType, originalLanguage: evLang, originalText: evText, translations: [], createdAt: new Date().toISOString(),
    }});
    setEvChapter(""); setEvBlock(""); setEvText(""); setAdding(false);
  };

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Evidences</span>
        <button onClick={() => setAdding(!adding)} style={{ background: "none", border: "none", fontSize: 10, color: "var(--accent)", cursor: "pointer", display: "flex", alignItems: "center", gap: 2 }}>
          <Plus size={10} /> Add
        </button>
      </div>
      {evidences.map(ev => (
        <div key={ev.id} style={{ padding: "8px 10px", borderRadius: 8, background: "var(--surface-0)", border: "1px solid var(--border)", marginBottom: 4, borderLeft: "3px solid var(--accent)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <span style={{ fontSize: 11, color: "var(--accent)", fontWeight: 600 }}>📍 {ev.location.chapterTitle}, {ev.location.blockOrLine}</span>
            <Badge small color={ev.type === "quote" ? "#6366f1" : ev.type === "summary" ? "#10b981" : "#94a3b8"}>{ev.type}</Badge>
            <span style={{ flex: 1 }} />
            <IconBtn icon={X} size={10} danger onClick={() => dispatch({ type: "REMOVE_EVIDENCE", entityId, attrValueId, evidenceId: ev.id })} />
          </div>
          <div style={{ fontSize: 12, color: "var(--text-1)", padding: "4px 0", fontStyle: ev.type === "quote" ? "italic" : "normal", lineHeight: 1.5 }}>
            {ev.type === "quote" ? `"${ev.originalText}"` : ev.originalText}
          </div>
          <div style={{ fontSize: 10, color: "var(--text-3)" }}>
            {langInfo(ev.originalLanguage).flag} {ev.originalLanguage}
            {ev.translations.length > 0 && <> · 🌐 {ev.translations.map(t => t.languageCode).join(", ")}</>}
          </div>
        </div>
      ))}
      {adding && (
        <div style={{ padding: 10, borderRadius: 8, background: "var(--surface-0)", border: "1px solid var(--accent-border)", marginTop: 4 }}>
          <div style={{ display: "flex", gap: 6, marginBottom: 6, flexWrap: "wrap" }}>
            <Dropdown value={evChapter} onChange={setEvChapter} placeholder="Chapter…"
              options={CHAPTERS.map(ch => ({ value: ch.id, label: ch.title }))} style={{ minWidth: 130 }} />
            <input value={evBlock} onChange={e => setEvBlock(e.target.value)} placeholder="Line / Block…"
              style={{ width: 100, padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)", fontSize: 11, background: "var(--surface-1)", color: "var(--text-1)" }} />
            <div style={{ display: "flex", gap: 3 }}>
              {["quote", "summary", "reference"].map(t => (
                <button key={t} onClick={() => setEvType(t)} style={{
                  padding: "3px 8px", borderRadius: 4, fontSize: 10, cursor: "pointer",
                  border: evType === t ? "1px solid var(--accent)" : "1px solid var(--border)",
                  background: evType === t ? "var(--accent-bg)" : "transparent",
                  color: evType === t ? "var(--accent)" : "var(--text-3)",
                }}>{t}</button>
              ))}
            </div>
            <Dropdown value={evLang} onChange={setEvLang}
              options={LANGUAGES.map(l => ({ value: l.code, label: `${l.flag} ${l.code}` }))} style={{ minWidth: 80 }} />
          </div>
          <textarea value={evText} onChange={e => setEvText(e.target.value)} placeholder="Quote or summary text…" rows={2}
            style={{ width: "100%", padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)", fontSize: 12, background: "var(--surface-1)", resize: "vertical", color: "var(--text-1)", fontFamily: "inherit" }} />
          <div style={{ display: "flex", gap: 6, marginTop: 6, justifyContent: "flex-end" }}>
            <button onClick={() => setAdding(false)} style={{ padding: "5px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "none", fontSize: 11, cursor: "pointer", color: "var(--text-3)" }}>Cancel</button>
            <button onClick={handleAdd} disabled={!evChapter || !evText} style={{
              padding: "5px 14px", borderRadius: 6, border: "none", fontSize: 11, fontWeight: 600, cursor: evChapter && evText ? "pointer" : "not-allowed",
              background: evChapter && evText ? "var(--accent)" : "var(--surface-2)", color: evChapter && evText ? "#fff" : "var(--text-3)",
            }}>Save Evidence</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// ATTRIBUTE ROW
// ═══════════════════════════════════════════════════════════

function AttributeRow({ attrValue, entityId, dispatch }) {
  const [expanded, setExpanded] = useState(false);
  const def = ATTR_DEFS[attrValue.attributeDefinitionId] || { code: attrValue.attributeDefinitionId, name: attrValue.attributeDefinitionId, fieldType: "text" };
  const li = langInfo(attrValue.originalLanguage);
  const existingLangs = [attrValue.originalLanguage, ...attrValue.translations.map(t => t.languageCode)];

  const renderInput = () => {
    const common = { fontSize: 13, color: "var(--text-1)", background: "var(--surface-0)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px", width: "100%", fontFamily: "inherit" };
    if (def.fieldType === "textarea") {
      return <textarea value={attrValue.originalValue} onChange={e => dispatch({ type: "UPDATE_ATTR_VALUE", entityId, attrValueId: attrValue.id, changes: { originalValue: e.target.value } })} rows={2} style={{ ...common, resize: "vertical" }} />;
    }
    if (def.fieldType === "select" && def.options) {
      return <Dropdown value={attrValue.originalValue} onChange={v => dispatch({ type: "UPDATE_ATTR_VALUE", entityId, attrValueId: attrValue.id, changes: { originalValue: v } })} options={def.options.map(o => ({ value: o, label: o }))} placeholder={`Select ${def.name}…`} style={common} />;
    }
    if (def.fieldType === "tags") {
      return <input value={attrValue.originalValue} onChange={e => dispatch({ type: "UPDATE_ATTR_VALUE", entityId, attrValueId: attrValue.id, changes: { originalValue: e.target.value } })} placeholder="Comma-separated tags…" style={common} />;
    }
    return <input value={attrValue.originalValue} onChange={e => dispatch({ type: "UPDATE_ATTR_VALUE", entityId, attrValueId: attrValue.id, changes: { originalValue: e.target.value } })} style={common} />;
  };

  return (
    <div style={{ borderRadius: 8, border: "1px solid var(--border)", marginBottom: 6, background: "var(--surface-1)", overflow: "hidden" }}>
      <div onClick={() => setExpanded(!expanded)} style={{
        display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", cursor: "pointer",
        background: expanded ? "var(--surface-0)" : "transparent",
      }}>
        {expanded ? <ChevronDown size={13} style={{ color: "var(--text-3)" }} /> : <ChevronRight size={13} style={{ color: "var(--text-3)" }} />}
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-1)" }}>{def.name}</span>
        <span style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "monospace" }}>({def.code})</span>
        {def.isRequired && <span style={{ fontSize: 9, color: "#ef4444" }}>required</span>}
        <span style={{ flex: 1 }} />
        {!expanded && attrValue.originalValue && (
          <span style={{ fontSize: 12, color: "var(--text-2)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {li.flag} {attrValue.originalValue}
          </span>
        )}
        {!expanded && attrValue.translations.length > 0 && <Badge small>🌐 +{attrValue.translations.length}</Badge>}
        {!expanded && attrValue.evidences.length > 0 && <Badge small>📎 +{attrValue.evidences.length}</Badge>}
      </div>
      {expanded && (
        <div style={{ padding: "8px 12px 12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 10, color: "var(--text-3)" }}>Original language:</span>
            <Dropdown value={attrValue.originalLanguage}
              onChange={v => dispatch({ type: "UPDATE_ATTR_VALUE", entityId, attrValueId: attrValue.id, changes: { originalLanguage: v } })}
              options={LANGUAGES.map(l => ({ value: l.code, label: `${l.flag} ${l.name} (${l.code})` }))} />
          </div>
          {renderInput()}
          <TranslationList translations={attrValue.translations} existingLangs={existingLangs} entityId={entityId} attrValueId={attrValue.id} dispatch={dispatch} />
          <EvidenceList evidences={attrValue.evidences} entityId={entityId} attrValueId={attrValue.id} dispatch={dispatch} />
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// ENTITY DETAIL PANEL
// ═══════════════════════════════════════════════════════════

function EntityDetailPanel({ entity, dispatch, onClose }) {
  if (!entity) return null;

  return (
    <div style={{
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      background: "var(--surface-1)", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 20 }}>{entity.kind.icon}</span>
            <span style={{ fontSize: 16, fontWeight: 700, color: "var(--text-1)" }}>
              {entity.attributeValues.find(av => av.attributeDefinitionId === "name" || av.attributeDefinitionId === "term")?.originalValue || "(untitled)"}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <select value={entity.status} onChange={e => dispatch({ type: "UPDATE_ENTITY", id: entity.id, changes: { status: e.target.value } })}
              style={{ fontSize: 11, padding: "3px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-0)", color: "var(--text-1)" }}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="draft">Draft</option>
            </select>
            <IconBtn icon={Trash2} danger title="Delete entity" onClick={() => {
              if (confirm("Delete this entity?")) dispatch({ type: "DELETE_ENTITY", id: entity.id });
            }} />
            <IconBtn icon={X} onClick={onClose} title="Close" />
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <Badge color={entity.kind.color}>{entity.kind.name}</Badge>
          <span style={{ fontSize: 10, color: "var(--text-3)" }}>Created {new Date(entity.createdAt).toLocaleDateString()}</span>
        </div>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>
        <ChapterLinkEditor entity={entity} dispatch={dispatch} />

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            <FileText size={11} style={{ marginRight: 4, verticalAlign: "middle" }} />Attributes
          </span>
        </div>
        {entity.attributeValues.map(av => (
          <AttributeRow key={av.id} attrValue={av} entityId={entity.id} dispatch={dispatch} />
        ))}

        {/* Tags */}
        <div style={{ marginTop: 16 }}>
          <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Tags</span>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
            {entity.tags.map(t => <Badge key={t} small><Tag size={8} /> {t}</Badge>)}
            {entity.tags.length === 0 && <span style={{ fontSize: 11, color: "var(--text-3)", fontStyle: "italic" }}>No tags</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// CREATE ENTITY MODAL
// ═══════════════════════════════════════════════════════════

function CreateEntityModal({ dispatch, onClose }) {
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center",
      background: "rgba(0,0,0,0.4)", backdropFilter: "blur(4px)",
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: "var(--surface-1)", borderRadius: 16, padding: 24, width: 420, maxWidth: "90vw",
        boxShadow: "0 24px 64px rgba(0,0,0,0.2)",
      }}>
        <h3 style={{ margin: "0 0 16px", fontSize: 16, fontWeight: 700, color: "var(--text-1)" }}>New Glossary Entity</h3>
        <p style={{ fontSize: 12, color: "var(--text-3)", margin: "0 0 16px" }}>Choose an entity kind to get started.</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
          {ENTITY_KINDS.map(k => (
            <button key={k.id} onClick={() => dispatch({ type: "CREATE_ENTITY", kindId: k.id })}
              style={{
                padding: "12px 14px", borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface-0)",
                cursor: "pointer", textAlign: "left", display: "flex", alignItems: "center", gap: 10,
                transition: "all 0.15s",
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = k.color; e.currentTarget.style.background = `${k.color}08`; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.background = "var(--surface-0)"; }}
            >
              <span style={{ fontSize: 22 }}>{k.icon}</span>
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>{k.name}</span>
            </button>
          ))}
        </div>
        <button onClick={onClose} style={{ marginTop: 16, width: "100%", padding: "8px 0", borderRadius: 8, border: "1px solid var(--border)", background: "none", fontSize: 12, color: "var(--text-3)", cursor: "pointer" }}>Cancel</button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════

export default function GlossaryManager() {
  const [state, dispatch] = useReducer(reducer, initialState);

  const filtered = useMemo(() => {
    let list = state.entities;
    const f = state.filters;
    if (f.status !== "all") list = list.filter(e => e.status === f.status);
    if (f.kindCodes.length > 0) list = list.filter(e => f.kindCodes.includes(e.kindId));
    if (f.chapterIds === "unlinked") list = list.filter(e => e.chapterLinks.length === 0);
    else if (Array.isArray(f.chapterIds) && f.chapterIds.length > 0) {
      const set = new Set(f.chapterIds);
      list = list.filter(e => e.chapterLinks.some(cl => set.has(cl.chapterId)));
    }
    if (f.searchQuery) {
      const q = f.searchQuery.toLowerCase();
      list = list.filter(e =>
        e.attributeValues.some(av =>
          av.originalValue.toLowerCase().includes(q) ||
          av.translations.some(t => t.value.toLowerCase().includes(q))
        ) || e.tags.some(t => t.toLowerCase().includes(q))
      );
    }
    return list;
  }, [state.entities, state.filters]);

  const selectedEntity = state.entities.find(e => e.id === state.selectedEntityId);
  const unlinkCount = state.entities.filter(e => e.chapterLinks.length === 0).length;

  return (
    <div style={{
      "--surface-0": "#ffffff", "--surface-1": "#f8f9fb", "--surface-2": "#eef0f4",
      "--text-1": "#1a1d26", "--text-2": "#4a5068", "--text-3": "#8b90a0",
      "--border": "#e2e5ec", "--accent": "#6366f1", "--accent-bg": "#eef2ff", "--accent-border": "#c7d2fe",
      fontFamily: "'DM Sans', 'Segoe UI', system-ui, sans-serif",
      height: "100vh", display: "flex", flexDirection: "column", background: "var(--surface-0)", color: "var(--text-1)",
    }}>
      {/* Top bar */}
      <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0, background: "var(--surface-1)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>📚</span>
          <span style={{ fontSize: 16, fontWeight: 800, color: "var(--text-1)", letterSpacing: "-0.02em" }}>Glossary & Lore</span>
          <span style={{ fontSize: 11, color: "var(--text-3)", background: "var(--surface-2)", padding: "2px 8px", borderRadius: 4 }}>{state.entities.length} entities</span>
        </div>
        <button onClick={() => dispatch({ type: "OPEN_CREATE" })} style={{
          display: "flex", alignItems: "center", gap: 6, padding: "7px 16px", borderRadius: 8,
          border: "none", background: "var(--accent)", color: "#fff", fontSize: 12, fontWeight: 600,
          cursor: "pointer", boxShadow: "0 2px 8px rgba(99,102,241,0.3)",
        }}><Plus size={14} /> New Entity</button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* List side */}
        <div style={{ flex: state.detailOpen ? "0 0 50%" : "1", overflow: "auto", padding: 16, transition: "flex 0.3s" }}>
          <FiltersBar filters={state.filters} dispatch={dispatch} entityCount={filtered.length} unlinkCount={unlinkCount} />
          {filtered.length === 0 ? (
            <div style={{ textAlign: "center", padding: "48px 0", color: "var(--text-3)" }}>
              <Globe size={32} style={{ marginBottom: 8, opacity: 0.4 }} />
              <div style={{ fontSize: 13 }}>No entities match your filters</div>
            </div>
          ) : (
            filtered.map(e => (
              <EntityCard key={e.id} entity={e} isSelected={state.selectedEntityId === e.id} onSelect={id => dispatch({ type: "SELECT_ENTITY", id })} />
            ))
          )}
        </div>

        {/* Detail side */}
        {state.detailOpen && (
          <div style={{ flex: "0 0 50%", borderLeft: "1px solid var(--border)", overflow: "hidden" }}>
            <EntityDetailPanel entity={selectedEntity} dispatch={dispatch} onClose={() => dispatch({ type: "CLOSE_DETAIL" })} />
          </div>
        )}
      </div>

      {state.createModalOpen && <CreateEntityModal dispatch={dispatch} onClose={() => dispatch({ type: "CLOSE_CREATE" })} />}
      {state.toast && <Toast message={state.toast} onClose={() => dispatch({ type: "HIDE_TOAST" })} />}

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;0,9..40,800;1,9..40,400&display=swap');
        * { box-sizing: border-box; margin: 0; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        input:focus, textarea:focus, select:focus { outline: none; border-color: var(--accent) !important; box-shadow: 0 0 0 2px var(--accent-bg); }
        @keyframes slideUp { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
      `}</style>
    </div>
  );
}

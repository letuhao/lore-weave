package domain

// EntityKind describes a category of glossary entity (e.g. Character, Location).
type EntityKind struct {
	KindID      string    `json:"kind_id"`
	Code        string    `json:"code"`
	Name        string    `json:"name"`
	Description *string   `json:"description"`
	Icon        string    `json:"icon"`
	Color       string    `json:"color"`
	IsDefault   bool      `json:"is_default"`
	IsHidden    bool      `json:"is_hidden"`
	SortOrder   int       `json:"sort_order"`
	GenreTags   []string  `json:"genre_tags"`
	EntityCount int       `json:"entity_count"`
	Attributes  []AttrDef `json:"default_attributes"`
}

// AttrDef describes one attribute field within a kind.
type AttrDef struct {
	AttrDefID   string   `json:"attr_def_id"`
	Code        string   `json:"code"`
	Name        string   `json:"name"`
	Description *string  `json:"description"`
	FieldType   string   `json:"field_type"`
	IsRequired  bool     `json:"is_required"`
	IsSystem    bool     `json:"is_system"`
	IsActive    bool     `json:"is_active"`
	SortOrder   int      `json:"sort_order"`
	Options     []string `json:"options,omitempty"`
	GenreTags   []string `json:"genre_tags"`
}

// SeedKind is the static definition used to seed entity_kinds + attribute_definitions.
type SeedKind struct {
	Code      string
	Name      string
	Icon      string
	Color     string
	SortOrder int
	GenreTags []string
	Attrs     []SeedAttr
}

// SeedAttr is a single attribute definition within a SeedKind.
type SeedAttr struct {
	Code       string
	Name       string
	FieldType  string // text | textarea | select | number | date | tags | url | boolean
	IsRequired bool
	SortOrder  int
	Options    []string
}

// DefaultKinds is the canonical ordered list of 12 system kinds used for seed and tests.
var DefaultKinds = []SeedKind{
	// ── Group A: Universal ────────────────────────────────────────────────────
	{
		Code: "character", Name: "Character", Icon: "👤", Color: "#6366f1",
		SortOrder: 1, GenreTags: []string{"universal"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", FieldType: "tags", SortOrder: 2},
			{Code: "gender", Name: "Gender", FieldType: "text", SortOrder: 3},
			{Code: "role", Name: "Role", FieldType: "text", SortOrder: 4},
			{Code: "occupation", Name: "Occupation", FieldType: "text", SortOrder: 5},
			{Code: "social_class", Name: "Social Class", FieldType: "text", SortOrder: 6},
			{Code: "affiliation", Name: "Affiliation", FieldType: "text", SortOrder: 7},
			{Code: "appearance", Name: "Appearance", FieldType: "textarea", SortOrder: 8},
			{Code: "personality", Name: "Personality", FieldType: "textarea", SortOrder: 9},
			{Code: "emotional_wound", Name: "Emotional Wound", FieldType: "textarea", SortOrder: 10},
			{Code: "love_language", Name: "Love Language", FieldType: "text", SortOrder: 11},
			{Code: "relationships", Name: "Relationships", FieldType: "textarea", SortOrder: 12},
			{Code: "description", Name: "Description", FieldType: "textarea", SortOrder: 13},
		},
	},
	{
		Code: "location", Name: "Location", Icon: "📍", Color: "#f59e0b",
		SortOrder: 2, GenreTags: []string{"universal"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", FieldType: "tags", SortOrder: 2},
			{Code: "type", Name: "Type", FieldType: "text", SortOrder: 3},
			{Code: "parent_location", Name: "Parent Location", FieldType: "text", SortOrder: 4},
			{Code: "atmosphere", Name: "Atmosphere", FieldType: "textarea", SortOrder: 5},
			{Code: "significance", Name: "Significance", FieldType: "textarea", SortOrder: 6},
			{Code: "description", Name: "Description", FieldType: "textarea", SortOrder: 7},
		},
	},
	{
		Code: "item", Name: "Item / Prop", Icon: "🎁", Color: "#ef4444",
		SortOrder: 3, GenreTags: []string{"universal"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", FieldType: "tags", SortOrder: 2},
			{Code: "type", Name: "Type", FieldType: "text", SortOrder: 3},
			{Code: "owner", Name: "Owner", FieldType: "text", SortOrder: 4},
			{Code: "symbolic_meaning", Name: "Symbolic Meaning", FieldType: "textarea", SortOrder: 5},
			{Code: "description", Name: "Description", FieldType: "textarea", SortOrder: 6},
		},
	},
	{
		Code: "event", Name: "Event", Icon: "📅", Color: "#10b981",
		SortOrder: 4, GenreTags: []string{"universal"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "type", Name: "Type", FieldType: "text", SortOrder: 2},
			{Code: "date_in_story", Name: "Date in Story", FieldType: "text", SortOrder: 3},
			{Code: "location", Name: "Location", FieldType: "text", SortOrder: 4},
			{Code: "participants", Name: "Participants", FieldType: "tags", SortOrder: 5},
			{Code: "emotional_impact", Name: "Emotional Impact", FieldType: "textarea", SortOrder: 6},
			{Code: "outcome", Name: "Outcome", FieldType: "textarea", SortOrder: 7},
			{Code: "description", Name: "Description", FieldType: "textarea", SortOrder: 8},
		},
	},
	{
		Code: "terminology", Name: "Terminology", Icon: "📖", Color: "#f97316",
		SortOrder: 5, GenreTags: []string{"universal"},
		Attrs: []SeedAttr{
			{Code: "term", Name: "Term", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "category", Name: "Category", FieldType: "text", SortOrder: 2},
			{Code: "definition", Name: "Definition", FieldType: "textarea", IsRequired: true, SortOrder: 3},
			{Code: "usage_note", Name: "Usage Note", FieldType: "textarea", SortOrder: 4},
		},
	},
	// ── Group B: Fantasy ─────────────────────────────────────────────────────
	{
		Code: "power_system", Name: "Power System", Icon: "✨", Color: "#a855f7",
		SortOrder: 6, GenreTags: []string{"fantasy"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", FieldType: "tags", SortOrder: 2},
			{Code: "type", Name: "Type", FieldType: "text", SortOrder: 3},
			{Code: "rank", Name: "Rank / Tier", FieldType: "text", SortOrder: 4},
			{Code: "user", Name: "User", FieldType: "text", SortOrder: 5},
			{Code: "effects", Name: "Effects", FieldType: "textarea", SortOrder: 6},
			{Code: "description", Name: "Description", FieldType: "textarea", SortOrder: 7},
		},
	},
	{
		Code: "organization", Name: "Organization", Icon: "🏛", Color: "#0ea5e9",
		SortOrder: 7, GenreTags: []string{"fantasy", "drama"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", FieldType: "tags", SortOrder: 2},
			{Code: "type", Name: "Type", FieldType: "text", SortOrder: 3},
			{Code: "leader", Name: "Leader", FieldType: "text", SortOrder: 4},
			{Code: "headquarters", Name: "Headquarters", FieldType: "text", SortOrder: 5},
			{Code: "members", Name: "Members", FieldType: "tags", SortOrder: 6},
			{Code: "description", Name: "Description", FieldType: "textarea", SortOrder: 7},
		},
	},
	{
		Code: "species", Name: "Species / Race", Icon: "🧬", Color: "#ec4899",
		SortOrder: 8, GenreTags: []string{"fantasy"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", FieldType: "tags", SortOrder: 2},
			{Code: "traits", Name: "Traits", FieldType: "textarea", SortOrder: 3},
			{Code: "abilities", Name: "Abilities", FieldType: "textarea", SortOrder: 4},
			{Code: "habitat", Name: "Habitat", FieldType: "text", SortOrder: 5},
			{Code: "culture", Name: "Culture", FieldType: "textarea", SortOrder: 6},
			{Code: "description", Name: "Description", FieldType: "textarea", SortOrder: 7},
		},
	},
	// ── Group C: Romance / Drama ──────────────────────────────────────────────
	{
		Code: "relationship", Name: "Relationship", Icon: "💕", Color: "#e879f9",
		SortOrder: 9, GenreTags: []string{"romance", "drama"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "parties", Name: "Parties", FieldType: "tags", SortOrder: 2},
			{Code: "relationship_type", Name: "Relationship Type", FieldType: "text", SortOrder: 3},
			{Code: "status", Name: "Status", FieldType: "text", SortOrder: 4},
			{Code: "tropes", Name: "Tropes", FieldType: "tags", SortOrder: 5},
			{Code: "dynamic", Name: "Dynamic", FieldType: "textarea", SortOrder: 6},
			{Code: "key_conflict", Name: "Key Conflict", FieldType: "textarea", SortOrder: 7},
			{Code: "turning_points", Name: "Turning Points", FieldType: "textarea", SortOrder: 8},
			{Code: "resolution", Name: "Resolution", FieldType: "textarea", SortOrder: 9},
			{Code: "description", Name: "Description", FieldType: "textarea", SortOrder: 10},
		},
	},
	{
		Code: "plot_arc", Name: "Plot Arc", Icon: "📈", Color: "#f43f5e",
		SortOrder: 10, GenreTags: []string{"romance", "drama"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "arc_type", Name: "Arc Type", FieldType: "text", SortOrder: 2},
			{Code: "parties", Name: "Parties", FieldType: "tags", SortOrder: 3},
			{Code: "trigger", Name: "Trigger", FieldType: "textarea", SortOrder: 4},
			{Code: "stakes", Name: "Stakes", FieldType: "textarea", SortOrder: 5},
			{Code: "chapters_span", Name: "Chapters Span", FieldType: "text", SortOrder: 6},
			{Code: "emotional_beats", Name: "Emotional Beats", FieldType: "textarea", SortOrder: 7},
			{Code: "resolution", Name: "Resolution", FieldType: "textarea", SortOrder: 8},
			{Code: "description", Name: "Description", FieldType: "textarea", SortOrder: 9},
		},
	},
	{
		Code: "trope", Name: "Trope", Icon: "🎭", Color: "#7c3aed",
		SortOrder: 11, GenreTags: []string{"romance", "drama"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "category", Name: "Category", FieldType: "text", SortOrder: 2},
			{Code: "definition", Name: "Definition", FieldType: "textarea", IsRequired: true, SortOrder: 3},
			{Code: "how_manifested", Name: "How Manifested", FieldType: "textarea", SortOrder: 4},
			{Code: "subverted", Name: "Subverted?", FieldType: "textarea", SortOrder: 5},
			{Code: "related_characters", Name: "Related Characters", FieldType: "tags", SortOrder: 6},
			{Code: "usage_note", Name: "Usage Note", FieldType: "textarea", SortOrder: 7},
		},
	},
	{
		Code: "social_setting", Name: "Social Setting", Icon: "🏫", Color: "#0891b2",
		SortOrder: 12, GenreTags: []string{"romance", "drama", "historical"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "era", Name: "Era", FieldType: "text", SortOrder: 2},
			{Code: "location", Name: "Location", FieldType: "text", SortOrder: 3},
			{Code: "class_hierarchy", Name: "Class Hierarchy", FieldType: "textarea", SortOrder: 4},
			{Code: "rules_norms", Name: "Rules & Norms", FieldType: "textarea", SortOrder: 5},
			{Code: "romance_obstacles", Name: "Romance Obstacles", FieldType: "textarea", SortOrder: 6},
			{Code: "significance", Name: "Significance", FieldType: "textarea", SortOrder: 7},
			{Code: "description", Name: "Description", FieldType: "textarea", SortOrder: 8},
		},
	},
}

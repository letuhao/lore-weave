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
	AttrDefID       string   `json:"attr_def_id"`
	Code            string   `json:"code"`
	Name            string   `json:"name"`
	Description     *string  `json:"description"`
	FieldType       string   `json:"field_type"`
	IsRequired      bool     `json:"is_required"`
	IsSystem        bool     `json:"is_system"`
	IsActive        bool     `json:"is_active"`
	SortOrder       int      `json:"sort_order"`
	Options         []string `json:"options,omitempty"`
	GenreTags       []string `json:"genre_tags"`
	AutoFillPrompt  *string  `json:"auto_fill_prompt"`
	TranslationHint *string  `json:"translation_hint"`
}

// SeedKind is the static definition used to seed system_kinds + system_kind_attributes.
type SeedKind struct {
	Code string
	Name string
	// Description is what the EXTRACTION PROMPT shows the model about this kind, and it
	// is the only thing distinguishing one bare identifier from another. It was absent
	// from this struct entirely until 2026-08-01 — the concept arrived later (the work
	// kinds seeded in migrate.go do carry one) and the original twelve were never
	// revisited, so every book adopted a catalogue whose kinds had NO definitions.
	//
	// Measured consequence: the model was handed the word `power_system` and nothing
	// else, and filed 崑崙之妙術 ("the wondrous art of Kunlun") under `terminology`
	// while filing 哮天犬 (a divine hound) under `item` — because `power_system` reads
	// as "a system of power", which a single technique does not resemble. The shipped
	// batched shape misfiled in the opposite direction, putting four swords and a mirror
	// INTO power_system. Both were guessing from an identifier.
	//
	// Write these CONTRASTIVELY — say what the kind is AND what it is not, naming the
	// neighbour it is most often confused with. "A body of people acting together; it
	// survives the loss of its building" discriminates; "an organization" does not.
	Description string
	Icon        string
	Color       string
	SortOrder   int
	GenreTags   []string
	Attrs       []SeedAttr
}

// SeedAttr is a single attribute definition within a SeedKind.
type SeedAttr struct {
	Code string
	Name string
	// Description is rendered into the extraction prompt directly after the attribute's
	// code and type — `- role (text): <description>`. Without it the model sees a bare
	// identifier and guesses, which is the same rot as SeedKind.Description one level
	// down: this struct never had the field either, so all 93 seeded attributes carried
	// none and every extraction prompt this platform has ever sent was a list of naked
	// codes. Say what the value IS and, where a neighbour competes for it, what it is not.
	Description string
	FieldType   string // text | textarea | select | number | date | tags | url | boolean
	IsRequired  bool
	SortOrder   int
	Options     []string
}

// DefaultKinds is the canonical ordered list of 12 system kinds used for seed and tests.
var DefaultKinds = []SeedKind{
	// ── Group A: Universal ────────────────────────────────────────────────────
	{
		Code: "character", Name: "Character",
		Description: "An individual PERSON, god, immortal or named being who acts, speaks, or is addressed. NOT a group of people (that is organization), and NOT a kind of being (that is species).", Icon: "👤", Color: "#6366f1",
		SortOrder: 1, GenreTags: []string{"universal"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", Description: "The character's canonical name, exactly as written in the source.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", Description: "Every other name, title or epithet the text uses for this same person.", FieldType: "tags", SortOrder: 2},
			{Code: "gender", Name: "Gender", Description: "As the text presents it; leave empty rather than inferring.", FieldType: "text", SortOrder: 3},
			{Code: "role", Name: "Role", Description: "Their function in the story — protagonist, antagonist, mentor, foil.", FieldType: "text", SortOrder: 4},
			{Code: "occupation", Name: "Occupation", Description: "What they do: their office, trade, or station.", FieldType: "text", SortOrder: 5},
			{Code: "social_class", Name: "Social Class", Description: "Their rank or standing in the world's hierarchy.", FieldType: "text", SortOrder: 6},
			{Code: "affiliation", Name: "Affiliation", Description: "The organization, sect, house or faction they belong to.", FieldType: "text", SortOrder: 7},
			{Code: "appearance", Name: "Appearance", Description: "Physical description as the text gives it, not as you imagine it.", FieldType: "textarea", SortOrder: 8},
			{Code: "personality", Name: "Personality", Description: "Disposition and temperament, evidenced by how they act and speak.", FieldType: "textarea", SortOrder: 9},
			{Code: "emotional_wound", Name: "Emotional Wound", Description: "The unresolved hurt or loss that drives them.", FieldType: "textarea", SortOrder: 10},
			{Code: "love_language", Name: "Love Language", Description: "How they express and receive affection, when the text shows it.", FieldType: "text", SortOrder: 11},
			{Code: "relationships", Name: "Relationships", Description: "Named ties to other characters and what each tie is.", FieldType: "textarea", SortOrder: 12},
			{Code: "description", Name: "Description", Description: "A short summary of who this person is and why they matter here.", FieldType: "textarea", SortOrder: 13},
		},
	},
	{
		Code: "location", Name: "Location",
		Description: "A PLACE one can travel to or stand in — a mountain, cave, hall, palace, pass, city, river. NOT the body of people seated there: a sect's cave is a location, the sect is an organization.", Icon: "📍", Color: "#f59e0b",
		SortOrder: 2, GenreTags: []string{"universal"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", Description: "The place's canonical name, exactly as written in the source.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", Description: "Other names the text uses for this same place.", FieldType: "tags", SortOrder: 2},
			{Code: "type", Name: "Type", Description: "What kind of place — mountain, cave, hall, palace, pass, city, river.", FieldType: "text", SortOrder: 3},
			{Code: "parent_location", Name: "Parent Location", Description: "The larger place that contains it, if the text names one.", FieldType: "text", SortOrder: 4},
			{Code: "atmosphere", Name: "Atmosphere", Description: "How the place feels: its mood, weather, light, sound.", FieldType: "textarea", SortOrder: 5},
			{Code: "significance", Name: "Significance", Description: "Why it matters to the story — what happens here.", FieldType: "textarea", SortOrder: 6},
			{Code: "description", Name: "Description", Description: "A short summary of the place itself.", FieldType: "textarea", SortOrder: 7},
		},
	},
	{
		Code: "item", Name: "Item / Prop",
		Description: "A physical OBJECT — a weapon, treasure, talisman, garment, vehicle. NOT a living creature or mount, even one someone owns (that is species), and NOT the technique performed with it (that is power_system).", Icon: "🎁", Color: "#ef4444",
		SortOrder: 3, GenreTags: []string{"universal"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", Description: "The object's canonical name, exactly as written in the source.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", Description: "Other names the text uses for this same object.", FieldType: "tags", SortOrder: 2},
			{Code: "type", Name: "Type", Description: "What kind of object — weapon, treasure, talisman, garment, vehicle.", FieldType: "text", SortOrder: 3},
			{Code: "owner", Name: "Owner", Description: "Who possesses or wields it.", FieldType: "text", SortOrder: 4},
			{Code: "symbolic_meaning", Name: "Symbolic Meaning", Description: "What it stands for beyond its physical use, if anything.", FieldType: "textarea", SortOrder: 5},
			{Code: "description", Name: "Description", Description: "What the object is, what it does, and what it looks like.", FieldType: "textarea", SortOrder: 6},
		},
	},
	{
		Code: "event", Name: "Event",
		Description: "Something that HAPPENS — a battle, an execution, a flight, an investiture, a betrayal, a prophecy fulfilled. The text will usually not name it, so give it a short label of your own.", Icon: "📅", Color: "#10b981",
		SortOrder: 4, GenreTags: []string{"universal"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", Description: "A short label for what happened. The text will usually not name it — write one.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "type", Name: "Type", Description: "What kind of happening — battle, execution, journey, betrayal, investiture.", FieldType: "text", SortOrder: 2},
			{Code: "date_in_story", Name: "Date in Story", Description: "When it happens in the story's own time, however the text marks it.", FieldType: "text", SortOrder: 3},
			{Code: "location", Name: "Location", Description: "Where it happens.", FieldType: "text", SortOrder: 4},
			{Code: "participants", Name: "Participants", Description: "The named characters or groups involved.", FieldType: "tags", SortOrder: 5},
			{Code: "emotional_impact", Name: "Emotional Impact", Description: "What it costs or changes for those involved.", FieldType: "textarea", SortOrder: 6},
			{Code: "outcome", Name: "Outcome", Description: "How it ends and what follows from it.", FieldType: "textarea", SortOrder: 7},
			{Code: "description", Name: "Description", Description: "What happened, in a sentence or two.", FieldType: "textarea", SortOrder: 8},
		},
	},
	{
		Code: "terminology", Name: "Terminology",
		Description: "An abstract TERM, doctrine, rank, title or concept with no physical form and no practitioner. NOT a technique someone performs (that is power_system), NOT an object (item), NOT a group of people (organization).", Icon: "📖", Color: "#f97316",
		SortOrder: 5, GenreTags: []string{"universal"},
		Attrs: []SeedAttr{
			{Code: "term", Name: "Term", Description: "The term exactly as the text writes it.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "category", Name: "Category", Description: "What sort of term — a doctrine, a rank, a title, a unit, a concept.", FieldType: "text", SortOrder: 2},
			{Code: "definition", Name: "Definition", Description: "What it means in this world, in the world's own logic.", FieldType: "textarea", IsRequired: true, SortOrder: 3},
			{Code: "usage_note", Name: "Usage Note", Description: "Who uses it, when, and any nuance a reader would miss.", FieldType: "textarea", SortOrder: 4},
		},
	},
	// ── Group B: Fantasy ─────────────────────────────────────────────────────
	{
		Code: "power_system", Name: "Power System",
		Description: "A named TECHNIQUE, ART, SPELL, FORMATION or magical METHOD — something a practitioner performs, casts or cultivates. A SINGLE technique belongs here; the name says system but one art is enough. NOT the object used to perform it (item), and NOT an abstract term nobody performs (terminology).", Icon: "✨", Color: "#a855f7",
		SortOrder: 6, GenreTags: []string{"fantasy"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", Description: "The technique or art's name as the text writes it.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", Description: "Other names the text uses for the same technique.", FieldType: "tags", SortOrder: 2},
			{Code: "type", Name: "Type", Description: "What sort of method — a spell, a formation, an escape art, a cultivation path.", FieldType: "text", SortOrder: 3},
			{Code: "rank", Name: "Rank / Tier", Description: "Its level, tier or grade, if the world ranks such things.", FieldType: "text", SortOrder: 4},
			{Code: "user", Name: "User", Description: "Who performs or has mastered it.", FieldType: "text", SortOrder: 5},
			{Code: "effects", Name: "Effects", Description: "What it does when used, and at what cost.", FieldType: "textarea", SortOrder: 6},
			{Code: "description", Name: "Description", Description: "How the technique works, in the world's own terms.", FieldType: "textarea", SortOrder: 7},
		},
	},
	{
		Code: "organization", Name: "Organization",
		Description: "A body of PEOPLE acting together — a sect, dynasty, army, clan, court, office. It survives the loss of its building. NOT the place it occupies (location), and NOT a doctrine it teaches (terminology).", Icon: "🏛", Color: "#0ea5e9",
		SortOrder: 7, GenreTags: []string{"fantasy", "drama"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", Description: "The group's name exactly as the text writes it.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", Description: "Other names the text uses for the same group.", FieldType: "tags", SortOrder: 2},
			{Code: "type", Name: "Type", Description: "What sort of body — sect, dynasty, army, clan, court, office.", FieldType: "text", SortOrder: 3},
			{Code: "leader", Name: "Leader", Description: "Who heads it.", FieldType: "text", SortOrder: 4},
			{Code: "headquarters", Name: "Headquarters", Description: "The place it is seated — a location, not the group itself.", FieldType: "text", SortOrder: 5},
			{Code: "members", Name: "Members", Description: "Named individuals belonging to it.", FieldType: "tags", SortOrder: 6},
			{Code: "description", Name: "Description", Description: "What the group is, what it wants, and how it is organised.", FieldType: "textarea", SortOrder: 7},
		},
	},
	{
		Code: "species", Name: "Species / Race",
		Description: "A kind of LIVING BEING, or a named individual creature — including divine mounts, beasts and animal companions. NOT an object (item), even when someone owns or rides it.", Icon: "🧬", Color: "#ec4899",
		SortOrder: 8, GenreTags: []string{"fantasy"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", Description: "The creature or kind's name as the text writes it.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "aliases", Name: "Aliases", Description: "Other names the text uses for the same creature or kind.", FieldType: "tags", SortOrder: 2},
			{Code: "traits", Name: "Traits", Description: "Distinguishing physical or behavioural characteristics.", FieldType: "textarea", SortOrder: 3},
			{Code: "abilities", Name: "Abilities", Description: "What it can do that ordinary beings cannot.", FieldType: "textarea", SortOrder: 4},
			{Code: "habitat", Name: "Habitat", Description: "Where it lives.", FieldType: "text", SortOrder: 5},
			{Code: "culture", Name: "Culture", Description: "Its customs and social order, if it has any.", FieldType: "textarea", SortOrder: 6},
			{Code: "description", Name: "Description", Description: "What this being is.", FieldType: "textarea", SortOrder: 7},
		},
	},
	// ── Group C: Romance / Drama ──────────────────────────────────────────────
	{
		Code: "relationship", Name: "Relationship",
		Description: "A standing TIE between two named parties — master and disciple, sworn brothers, a marriage, a feud. NOT either party, and NOT the single event that created it.", Icon: "💕", Color: "#e879f9",
		SortOrder: 9, GenreTags: []string{"romance", "drama"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", Description: "A short label for the tie, e.g. A and B as master and disciple.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "parties", Name: "Parties", Description: "The two (or more) named parties bound by it.", FieldType: "tags", SortOrder: 2},
			{Code: "relationship_type", Name: "Relationship Type", Description: "What kind of tie — kinship, marriage, discipleship, rivalry, feud.", FieldType: "text", SortOrder: 3},
			{Code: "status", Name: "Status", Description: "Where it stands now — intact, strained, broken, secret.", FieldType: "text", SortOrder: 4},
			{Code: "tropes", Name: "Tropes", Description: "Recognisable relationship patterns it follows.", FieldType: "tags", SortOrder: 5},
			{Code: "dynamic", Name: "Dynamic", Description: "How the parties actually behave toward each other.", FieldType: "textarea", SortOrder: 6},
			{Code: "key_conflict", Name: "Key Conflict", Description: "The tension at the centre of it.", FieldType: "textarea", SortOrder: 7},
			{Code: "turning_points", Name: "Turning Points", Description: "The moments that changed it.", FieldType: "textarea", SortOrder: 8},
			{Code: "resolution", Name: "Resolution", Description: "How it ends, if it does.", FieldType: "textarea", SortOrder: 9},
			{Code: "description", Name: "Description", Description: "What binds these parties and why it matters.", FieldType: "textarea", SortOrder: 10},
		},
	},
	{
		Code: "plot_arc", Name: "Plot Arc",
		Description: "A multi-chapter STORYLINE with a beginning and an end. Larger than one event; a sequence of them.", Icon: "📈", Color: "#f43f5e",
		SortOrder: 10, GenreTags: []string{"romance", "drama"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", Description: "A short label for the storyline.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "arc_type", Name: "Arc Type", Description: "What sort of arc — revenge, ascent, redemption, war, courtship.", FieldType: "text", SortOrder: 2},
			{Code: "parties", Name: "Parties", Description: "The characters or groups it belongs to.", FieldType: "tags", SortOrder: 3},
			{Code: "trigger", Name: "Trigger", Description: "The event that starts it.", FieldType: "textarea", SortOrder: 4},
			{Code: "stakes", Name: "Stakes", Description: "What stands to be won or lost.", FieldType: "textarea", SortOrder: 5},
			{Code: "chapters_span", Name: "Chapters Span", Description: "Roughly which chapters it runs across.", FieldType: "text", SortOrder: 6},
			{Code: "emotional_beats", Name: "Emotional Beats", Description: "The turns the arc moves through.", FieldType: "textarea", SortOrder: 7},
			{Code: "resolution", Name: "Resolution", Description: "How it concludes.", FieldType: "textarea", SortOrder: 8},
			{Code: "description", Name: "Description", Description: "What this storyline is about.", FieldType: "textarea", SortOrder: 9},
		},
	},
	{
		Code: "trope", Name: "Trope",
		Description: "A recurring narrative DEVICE or convention the story uses. A property of the telling, not a thing inside the world.", Icon: "🎭", Color: "#7c3aed",
		SortOrder: 11, GenreTags: []string{"romance", "drama"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", Description: "The device's usual name.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "category", Name: "Category", Description: "What sort of device — structural, character, romantic, thematic.", FieldType: "text", SortOrder: 2},
			{Code: "definition", Name: "Definition", Description: "What the device is, in general.", FieldType: "textarea", IsRequired: true, SortOrder: 3},
			{Code: "how_manifested", Name: "How Manifested", Description: "How THIS story uses it, concretely.", FieldType: "textarea", SortOrder: 4},
			{Code: "subverted", Name: "Subverted?", Description: "Whether the story inverts or defies it, and how.", FieldType: "textarea", SortOrder: 5},
			{Code: "related_characters", Name: "Related Characters", Description: "Characters the device attaches to.", FieldType: "tags", SortOrder: 6},
			{Code: "usage_note", Name: "Usage Note", Description: "Anything about its use here worth recording.", FieldType: "textarea", SortOrder: 7},
		},
	},
	{
		Code: "social_setting", Name: "Social Setting",
		Description: "A social STRUCTURE or custom of the world — a caste order, a rite, an economy, a law. NOT a place (location) and NOT the body enforcing it (organization).", Icon: "🏫", Color: "#0891b2",
		SortOrder: 12, GenreTags: []string{"romance", "drama", "historical"},
		Attrs: []SeedAttr{
			{Code: "name", Name: "Name", Description: "A short label for the structure or custom.", FieldType: "text", IsRequired: true, SortOrder: 1},
			{Code: "era", Name: "Era", Description: "The period it belongs to, however the text marks time.", FieldType: "text", SortOrder: 2},
			{Code: "location", Name: "Location", Description: "Where it applies.", FieldType: "text", SortOrder: 3},
			{Code: "class_hierarchy", Name: "Class Hierarchy", Description: "How rank is ordered under it.", FieldType: "textarea", SortOrder: 4},
			{Code: "rules_norms", Name: "Rules & Norms", Description: "What it requires or forbids.", FieldType: "textarea", SortOrder: 5},
			{Code: "romance_obstacles", Name: "Romance Obstacles", Description: "Barriers it places between people.", FieldType: "textarea", SortOrder: 6},
			{Code: "significance", Name: "Significance", Description: "Why it matters to the story.", FieldType: "textarea", SortOrder: 7},
			{Code: "description", Name: "Description", Description: "What this social structure is.", FieldType: "textarea", SortOrder: 8},
		},
	},
}

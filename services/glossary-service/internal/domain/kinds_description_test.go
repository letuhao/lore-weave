package domain

import (
	"strings"
	"testing"
)

// The extraction prompt renders a kind as `## <code>\n<description>` and an attribute as
// `- <code> (<type>): <description>`. A missing description reaches the model as a naked
// identifier, and the model guesses from the English word.
//
// It guessed badly, measurably: handed the bare token `power_system`, it filed
// 崑崙之妙術 ("the wondrous art of Kunlun") under `terminology` and 哮天犬 (a divine
// hound) under `item` — because "power_system" reads as *a system of power*, which a single
// technique does not resemble. The shipped 3-batch shape misfiled in the opposite direction,
// putting four swords and a mirror INTO power_system. Both were guessing.
//
// Neither `SeedKind` nor `SeedAttr` had a Description field at all until 2026-08-01: the
// concept arrived later (the work kinds in migrate.go carry one) and the original twelve
// were never revisited. These tests are the mechanism that stops it drifting back — adding
// a kind or an attribute without a definition now fails the build, rather than silently
// shipping another naked identifier.

func TestEverySeededKindHasADescription(t *testing.T) {
	for _, k := range DefaultKinds {
		if strings.TrimSpace(k.Description) == "" {
			t.Errorf("kind %q has no Description — the extraction prompt would show the "+
				"model only the bare identifier %q", k.Code, k.Code)
		}
	}
}

func TestEverySeededAttributeHasADescription(t *testing.T) {
	for _, k := range DefaultKinds {
		for _, a := range k.Attrs {
			if strings.TrimSpace(a.Description) == "" {
				t.Errorf("attribute %s.%s has no Description — the prompt would render "+
					"`- %s (%s)` and nothing else", k.Code, a.Code, a.Code, a.FieldType)
			}
		}
	}
}

// A description that merely restates the code teaches the model nothing. `power_system:
// "A power system"` is the failure this catches — it is present, so the test above passes,
// and it carries no information the identifier did not already carry.
func TestADescriptionSaysMoreThanTheCodeDoes(t *testing.T) {
	for _, k := range DefaultKinds {
		bare := strings.ReplaceAll(k.Code, "_", " ")
		if strings.EqualFold(strings.Trim(k.Description, ". "), bare) ||
			strings.EqualFold(strings.Trim(k.Description, ". "), "a "+bare) ||
			strings.EqualFold(strings.Trim(k.Description, ". "), "an "+bare) {
			t.Errorf("kind %q description just restates the code: %q", k.Code, k.Description)
		}
		if len(k.Description) < 40 {
			t.Errorf("kind %q description is %d chars — too short to discriminate it from "+
				"its neighbours: %q", k.Code, len(k.Description), k.Description)
		}
	}
}

// The kinds that actually collide in practice must say what they are NOT. A definition
// written in isolation ("a body of people") does not stop the model filing a sect's cave
// as the sect; a contrastive one ("...it survives the loss of its building") does.
func TestTheConfusableKindsAreDefinedContrastively(t *testing.T) {
	// Each of these was measured misfiling into the others on a real corpus.
	confusable := map[string]bool{
		"power_system": true, "terminology": true, "item": true,
		"species": true, "organization": true, "location": true,
		// `technique` was split out of `power_system` on 2026-08-02 (below). The two are
		// now the closest pair in the catalogue, so both must name the other.
		"technique": true,
	}
	for _, k := range DefaultKinds {
		if !confusable[k.Code] {
			continue
		}
		if !strings.Contains(k.Description, "NOT") {
			t.Errorf("kind %q is one of the confusable set and its description never says "+
				"what it is NOT: %q", k.Code, k.Description)
		}
	}
}

// A kind's NAME is part of its prompt. `power_system` first shipped with no description at
// all, and its first description made the disagreement explicit — it read "a SINGLE technique
// belongs here; the name says system but one art is enough", which asks the model to file an
// individual art under a token that reads as a graded scheme. The model has been trained on
// corpora where 境界/築基/大羅金仙 are what "power system" names; a lone spell is not that.
//
// Measured on chapters 88-92 of 封神演義: ZERO occurrences of 境界, 修為, 品階, 等級,
// 階級, 層次, 果位, 金仙, 大羅, 天仙 or 太乙 — the text has no ranked ladder anywhere. It
// does have individual arts (縱地行之術, 陰符之術, 崑崙之妙術, 八九變化). So the extraction's
// `power_system = 0` was never evidence of a defect; there was nothing of that kind to find,
// and reading the zero as a miss was an unfounded inference about an unexamined corpus.
//
// The kinds were split accordingly. This test is the mechanism that stops them merging back.
func TestPowerSystemMeansTheLadderAndTechniqueMeansTheArt(t *testing.T) {
	byCode := map[string]SeedKind{}
	for _, k := range DefaultKinds {
		byCode[k.Code] = k
	}
	ps, ok := byCode["power_system"]
	if !ok {
		t.Fatal("power_system is gone — if that is deliberate, delete this test with it")
	}
	tech, ok := byCode["technique"]
	if !ok {
		t.Fatal("technique is gone; individual arts have nowhere to go but power_system, " +
			"which is the conflation this split fixed")
	}
	// The ladder kind must be about ORDERING, and must refuse the single art.
	if !strings.Contains(ps.Description, "TIER") && !strings.Contains(ps.Description, "GRADED") {
		t.Errorf("power_system no longer describes a graded/tiered scheme: %q", ps.Description)
	}
	if !strings.Contains(ps.Description, "technique") {
		t.Errorf("power_system must send single arts to `technique` by name: %q", ps.Description)
	}
	if strings.Contains(ps.Description, "SINGLE technique belongs here") {
		t.Errorf("power_system is back to claiming one art is enough — the exact wording that "+
			"contradicted its own name: %q", ps.Description)
	}
	// ...and the art kind must accept one art standing alone.
	if !strings.Contains(tech.Description, "power_system") {
		t.Errorf("technique must name power_system as its neighbour: %q", tech.Description)
	}
	// A story with no ladder must be allowed to report none, or the model fills the kind
	// with whatever is nearest — which is how four swords and a mirror got in.
	if !strings.Contains(ps.Description, "NO entities of this kind") {
		t.Errorf("power_system must license an EMPTY result for a story with no ladder: %q",
			ps.Description)
	}
}

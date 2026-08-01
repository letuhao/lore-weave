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

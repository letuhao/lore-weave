package api

import (
	"strings"
)

// parseSkillMarkdown parses a minimal SKILL.md: YAML-ish frontmatter delimited by
// `---` lines (name + description required, optional surfaces list) + a markdown
// body. We keep a tiny hand-parser rather than a YAML dep — the format is
// controlled (we also render it, roundtrip-stable) and this avoids executable
// surface. Returns (input, message, ok).
func parseSkillMarkdown(md string) (*skillInput, string, bool) {
	md = strings.ReplaceAll(md, "\r\n", "\n")
	if !strings.HasPrefix(strings.TrimLeft(md, "\n"), "---") {
		return nil, "SKILL.md must start with a --- frontmatter block", false
	}
	md = strings.TrimLeft(md, "\n")
	rest := strings.TrimPrefix(md, "---\n")
	end := strings.Index(rest, "\n---")
	if end < 0 {
		return nil, "unterminated frontmatter (missing closing ---)", false
	}
	front := rest[:end]
	body := rest[end+len("\n---"):]
	body = strings.TrimPrefix(body, "\n")
	body = strings.TrimLeft(body, "\n")

	in := &skillInput{Surfaces: []string{}}
	for _, line := range strings.Split(front, "\n") {
		line = strings.TrimRight(line, " \t")
		if line == "" || strings.HasPrefix(strings.TrimSpace(line), "#") {
			continue
		}
		idx := strings.Index(line, ":")
		if idx < 0 {
			continue
		}
		key := strings.TrimSpace(line[:idx])
		val := strings.TrimSpace(line[idx+1:])
		val = strings.Trim(val, `"'`)
		switch key {
		case "name":
			in.Slug = val
		case "description":
			in.Description = val
		case "surfaces":
			in.Surfaces = parseInlineList(val)
		}
	}
	in.BodyMD = body
	if in.Slug == "" {
		return nil, "frontmatter missing 'name'", false
	}
	if in.Description == "" {
		return nil, "frontmatter missing 'description'", false
	}
	return in, "", true
}

// parseInlineList handles `[a, b, c]` or `a, b, c`.
func parseInlineList(v string) []string {
	v = strings.TrimSpace(v)
	v = strings.TrimPrefix(v, "[")
	v = strings.TrimSuffix(v, "]")
	out := []string{}
	for _, p := range strings.Split(v, ",") {
		p = strings.TrimSpace(strings.Trim(p, `"'`))
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func renderSkillMarkdown(sk *skillRow) string {
	var b strings.Builder
	b.WriteString("---\n")
	b.WriteString("name: " + sk.Slug + "\n")
	b.WriteString("description: " + sk.Description + "\n")
	if len(sk.Surfaces) > 0 {
		b.WriteString("surfaces: [" + strings.Join(sk.Surfaces, ", ") + "]\n")
	}
	b.WriteString("---\n\n")
	b.WriteString(sk.BodyMD)
	if !strings.HasSuffix(sk.BodyMD, "\n") {
		b.WriteString("\n")
	}
	return b.String()
}

// l1MetadataLine renders the always-in-prompt L1 line for a skill (progressive
// disclosure), mirroring chat-service skill_registry's metadata block.
func l1MetadataLine(slug, description string) string {
	return "· " + slug + " — " + description
}

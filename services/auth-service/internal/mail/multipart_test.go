package mail

import (
	"strings"
	"testing"
)

func sample() Content {
	return Content{
		Subject:     "Reset your LoreWeave password",
		Preheader:   "expires in one hour",
		Heading:     "Reset your password",
		Intro:       "Someone asked to reset the password.",
		ActionURL:   "https://loreweave.test/reset?token=abc123",
		ActionLabel: "Choose a new password",
		TokenLabel:  "Or paste this code:",
		Token:       "abc123",
		ExpiryNote:  "Expires in one hour.",
		IgnoreNote:  "Ignore if this wasn't you.",
	}
}

// A message must carry BOTH parts. HTML-only scores worse with spam filters and
// is unreadable in text-only clients; text-only loses the whole design.
func TestMultipartCarriesBothParts(t *testing.T) {
	c := sample()
	html, err := c.RenderHTML()
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	msg, err := buildMultipart("LoreWeave <no-reply@lw.test>", "u@example.com", c.Subject, c.RenderText(), html)
	if err != nil {
		t.Fatalf("build: %v", err)
	}
	if !strings.Contains(msg, "multipart/alternative") {
		t.Error("not multipart/alternative")
	}
	iText := strings.Index(msg, "text/plain")
	iHTML := strings.Index(msg, "text/html")
	if iText < 0 || iHTML < 0 {
		t.Fatal("a part is missing")
	}
	// RFC 2046 5.1.4: least-rich FIRST. Reversed, clients that render the last
	// understood part would show the plain-text fallback instead of the design.
	if iText > iHTML {
		t.Error("text/plain must precede text/html")
	}
	if !strings.Contains(msg, "abc123") {
		t.Error("token missing from the message")
	}
}

// The boundary must not collide with body content, or the message truncates at
// whatever line happens to match.
func TestBoundaryIsUnique(t *testing.T) {
	seen := map[string]bool{}
	for i := 0; i < 200; i++ {
		b, err := randomBoundary()
		if err != nil {
			t.Fatalf("boundary: %v", err)
		}
		if seen[b] {
			t.Fatal("duplicate boundary")
		}
		seen[b] = true
	}
}

// A raw 8-bit Subject header is invalid and gets mangled or dropped by relays --
// which is exactly what a Vietnamese or Japanese subject line is.
func TestNonASCIISubjectIsEncoded(t *testing.T) {
	msg, err := buildMultipart("a@b.co", "u@example.com", "Xac minh email cua ban — 日本語", "text", "<p>html</p>")
	if err != nil {
		t.Fatalf("build: %v", err)
	}
	line := ""
	for _, l := range strings.Split(msg, "\r\n") {
		if strings.HasPrefix(l, "Subject:") {
			line = l
			break
		}
	}
	if !strings.Contains(line, "=?UTF-8?") {
		t.Errorf("subject not RFC 2047 encoded: %q", line)
	}
	if strings.Contains(line, "日本語") {
		t.Errorf("raw 8-bit bytes left in the Subject header: %q", line)
	}
}

// html/template escapes interpolated fields; a token or name carrying markup
// must not become live HTML in someone's inbox.
func TestHTMLIsEscaped(t *testing.T) {
	c := sample()
	c.Token = `<script>alert(1)</script>`
	html, err := c.RenderHTML()
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	if strings.Contains(html, "<script>alert(1)</script>") {
		t.Error("unescaped markup reached the HTML body")
	}
	if !strings.Contains(html, "&lt;script&gt;") {
		t.Error("expected the markup to be escaped")
	}
}

// Header injection: a newline in the subject would let a caller append
// arbitrary headers (Bcc, Content-Type) to the message.
func TestSubjectCannotInjectHeaders(t *testing.T) {
	msg, err := buildMultipart("a@b.co", "u@example.com", "Hi\r\nBcc: attacker@evil.test", "t", "<p>h</p>")
	if err != nil {
		t.Fatalf("build: %v", err)
	}
	// The property is "no NEW header line", not "the string Bcc: is absent".
	// After the newlines are stripped, `Bcc:` survives as ordinary text inside
	// the subject value, which is harmless — a substring assertion would fail on
	// correct code. Check the header block line by line instead.
	headers, _, _ := strings.Cut(msg, "\r\n\r\n")
	for _, line := range strings.Split(headers, "\r\n") {
		name, _, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		switch strings.ToLower(strings.TrimSpace(name)) {
		case "bcc", "cc", "content-type":
			if strings.EqualFold(strings.TrimSpace(name), "content-type") && strings.Contains(line, "multipart/alternative") {
				continue // the legitimate one this function writes
			}
			t.Errorf("subject injected a header line: %q", line)
		}
	}
}

// The text part is written as its own message, not tag-stripped HTML.
func TestTextPartIsReadable(t *testing.T) {
	txt := sample().RenderText()
	if strings.Contains(txt, "<") || strings.Contains(txt, "style=") {
		t.Error("markup leaked into the text/plain part")
	}
	for _, want := range []string{"Reset your password", "abc123", "Expires in one hour."} {
		if !strings.Contains(txt, want) {
			t.Errorf("text part missing %q", want)
		}
	}
}

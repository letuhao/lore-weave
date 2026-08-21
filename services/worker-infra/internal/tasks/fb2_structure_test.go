package tasks

import (
	"encoding/base64"
	"os"
	"strings"
	"testing"
)

const fb2Fixture = `<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">
  <description>
    <title-info>
      <genre>sf_fantasy</genre><author><first-name>Test</first-name><last-name>Author</last-name></author>
      <book-title>Fixture Book</book-title><annotation><p>A concise description.</p></annotation>
      <keywords>fixture, import</keywords><coverpage><image l:href="#cover"/></coverpage><lang>ru</lang>
    </title-info>
    <document-info><author><nickname>Converter</nickname></author><program-used>fixture</program-used><id>fixture-id</id><version>1.0</version></document-info>
    <publish-info><book-name>Fixture Print</book-name><isbn>9780000000000</isbn></publish-info>
  </description>
  <body>
    <section><title><p>Part One</p></title>
      <section><title><p>Chapter One</p></title><p>First <strong>bold</strong> line.</p><image l:href="#cover"/></section>
      <section><title><p>Chapter Two</p></title><poem><stanza><v>A verse.</v></stanza></poem></section>
    </section>
  </body>
  <binary id="cover" content-type="image/png">%s</binary>
</FictionBook>`

func TestExtractFB2DocumentPreservesStructureAndMetadata(t *testing.T) {
	data := []byte(strings.ReplaceAll(fb2Fixture, "%s", base64.StdEncoding.EncodeToString([]byte("not-a-real-png"))))
	doc, err := extractFB2Document(data)
	if err != nil {
		t.Fatalf("extractFB2Document() error = %v", err)
	}
	if doc.Title != "Fixture Book" || doc.Language != "ru" || doc.Summary != "A concise description." {
		t.Fatalf("metadata = %#v", doc)
	}
	if len(doc.Genres) != 1 || doc.Genres[0] != "sf_fantasy" || doc.Cover == nil {
		t.Fatalf("genre/cover = %#v", doc)
	}
	for _, want := range []string{"<title>Fixture Book</title>", "<h1>Part One</h1>", "<h2>Chapter One</h2>", "<strong>bold</strong>", "<blockquote>", "data:image/png;base64,"} {
		if !strings.Contains(doc.HTML, want) {
			t.Errorf("HTML missing %q: %s", want, doc.HTML)
		}
	}
	titleInfo := doc.Metadata["title_info"].(map[string]any)
	if titleInfo["keywords"] != "fixture, import" {
		t.Fatalf("keywords = %v", titleInfo["keywords"])
	}
}

// Optional manual compatibility smoke. It keeps real user-provided books out
// of the repository while allowing a local source file to exercise the same
// parser and limits used in production.
func TestExtractFB2Document_LocalSmoke(t *testing.T) {
	path := os.Getenv("FB2_LOCAL_SMOKE_PATH")
	if path == "" {
		t.Skip("set FB2_LOCAL_SMOKE_PATH to run a local FB2 compatibility smoke")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read local FB2 fixture: %v", err)
	}
	doc, err := extractFB2Document(data)
	if err != nil {
		t.Fatalf("extract local FB2: %v", err)
	}
	if doc.Title == "" || doc.Sections == 0 {
		t.Fatalf("local FB2 yielded no title or sections")
	}
	t.Logf("local FB2 parsed: sections=%d images=%d has_cover=%t", doc.Sections, doc.Images, doc.Cover != nil)
}

func TestExtractFB2DocumentRejectsUnsafeOrInvalidInput(t *testing.T) {
	cases := []string{
		`<FictionBook xmlns="wrong"><description><title-info><book-title>x</book-title></title-info></description><body><section/></body></FictionBook>`,
		`<!DOCTYPE FictionBook [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"/>`,
		`<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><description><title-info><book-title>x</book-title></title-info></description><body><section>`,
	}
	for _, input := range cases {
		if _, err := extractFB2Document([]byte(input)); err == nil {
			t.Errorf("extractFB2Document(%q) succeeded", input)
		}
	}
}

func TestExtractFB2DocumentRejectsOversizedImage(t *testing.T) {
	encoded := base64.StdEncoding.EncodeToString(make([]byte, maxFB2SingleImageSize+1))
	input := strings.ReplaceAll(fb2Fixture, "%s", encoded)
	if _, err := extractFB2Document([]byte(input)); err == nil || !strings.Contains(err.Error(), "embedded image limit") {
		t.Fatalf("error = %v", err)
	}
}

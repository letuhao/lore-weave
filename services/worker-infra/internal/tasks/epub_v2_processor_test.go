package tasks

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"

	"github.com/loreweave/epubimport"
	"github.com/loreweave/worker-infra/internal/config"
)

func TestProcessEPUBV2RedeliveryDoesNotDuplicateStagingOrParsing(t *testing.T) {
	archive := testEPUBArchive(t)
	inspection, err := epubimport.Inspect(archive, epubimport.DefaultLimits())
	if err != nil || len(inspection.Structure) != 1 {
		t.Fatalf("inspect fixture: inspection=%#v err=%v", inspection, err)
	}
	sourceKey := inspection.Structure[0].SourceKey
	itemID := uuid.New()
	claims := 0
	stageCalls := 0
	finalizeCalls := 0
	loreCalls := 0
	var staged map[string]any
	book := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasSuffix(r.URL.Path, "/claim-next"):
			claims++
			if claims == 1 {
				_ = json.NewEncoder(w).Encode(epubV2Claim{ItemID: itemID, SourceKey: sourceKey, Title: "Chapter one"})
				return
			}
			_ = json.NewEncoder(w).Encode(epubV2Claim{Done: true})
		case strings.Contains(r.URL.Path, "/items/") && strings.HasSuffix(r.URL.Path, "/stage"):
			stageCalls++
			if err := json.NewDecoder(r.Body).Decode(&staged); err != nil {
				t.Fatalf("decode stage request: %v", err)
			}
		case strings.HasSuffix(r.URL.Path, "/finalize"):
			finalizeCalls++
			w.WriteHeader(http.StatusNoContent)
		default:
			t.Fatalf("unexpected Book Service path: %s", r.URL.Path)
		}
	}))
	defer book.Close()
	glossary := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		loreCalls++
		if r.Method != http.MethodPost || r.URL.Path != "/internal/books/book-1/ontology/adopt-kinds" || r.URL.Query().Get("user_id") != "user-1" {
			t.Fatalf("unexpected Glossary request: %s %s", r.Method, r.URL.String())
		}
		if r.Header.Get("X-Internal-Token") != "test" {
			t.Fatalf("missing internal token")
		}
		var body struct {
			SystemDefaults bool     `json:"system_defaults"`
			Genres         []string `json:"genres"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || !body.SystemDefaults || len(body.Genres) != 1 || body.Genres[0] != "fantasy" {
			t.Fatalf("Lore scaffold body=%#v err=%v", body, err)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer glossary.Close()

	parserCalls := 0
	parser := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		parserCalls++
		if r.URL.Path != "/internal/parse/chapter" {
			t.Fatalf("parser path = %s", r.URL.Path)
		}
		var request parseRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatalf("decode parser request: %v", err)
		}
		if request.Options["preserve_chapter_boundary"] != true || request.Options["extract_scenes_only"] != true {
			t.Fatalf("parser options = %#v", request.Options)
		}
		_ = json.NewEncoder(w).Encode(StructuralTree{Parts: []Part{{Chapters: []ParsedChapter{{HTML: "<p>parsed chapter</p>"}}}}})
	}))
	defer parser.Close()

	objectGets := 0
	objectStore := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Has("location") && r.URL.Path == "/books/" {
			w.Header().Set("Content-Type", "application/xml")
			_, _ = w.Write([]byte(`<LocationConstraint>us-east-1</LocationConstraint>`))
			return
		}
		if r.Method != http.MethodGet || r.URL.Path != "/books/source.epub" {
			t.Fatalf("object request = %s %s", r.Method, r.URL.Path)
		}
		objectGets++
		if objectGets == 1 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Last-Modified", "Mon, 2 Jan 2006 15:04:05 GMT")
		_, _ = w.Write(archive)
	}))
	defer objectStore.Close()
	minioClient, err := minio.New(strings.TrimPrefix(objectStore.URL, "http://"), &minio.Options{Creds: credentials.NewStaticV4("key", "secret", ""), Secure: false})
	if err != nil {
		t.Fatalf("create MinIO client: %v", err)
	}

	processor := &ImportProcessor{
		Cfg:   &config.Config{MinioBucket: "books", BookServiceURL: book.URL, GlossaryServiceURL: glossary.URL, KnowledgeServiceURL: parser.URL, InternalToken: "test"},
		Minio: minioClient, parseClient: NewParseClient(parser.URL, "test"),
	}
	importPayload := importRequestedPayload{JobID: "job-1", BookID: "book-1", UserID: "user-1", FileFormat: "epub", FileStorageKey: "source.epub", OriginalLanguage: "en", TargetMode: "new_book", LoreGenres: []string{"fantasy"}}
	if err := processor.processEPUBV2(context.Background(), importPayload); err != nil {
		t.Fatalf("processEPUBV2 must recover from a transient MinIO failure: %v", err)
	}
	if err := processor.processEPUBV2(context.Background(), importPayload); err != nil {
		t.Fatalf("redelivered processEPUBV2: %v", err)
	}
	if parserCalls != 1 || claims != 3 || stageCalls != 1 || finalizeCalls != 2 || loreCalls != 2 || objectGets != 3 {
		t.Fatalf("parser/claim/stage/finalize/lore/object calls=%d/%d/%d/%d/%d/%d, want 1/3/1/2/2/3", parserCalls, claims, stageCalls, finalizeCalls, loreCalls, objectGets)
	}
	payload, ok := staged["staging_payload"].(map[string]any)
	if !ok || payload["source_key"] != sourceKey {
		t.Fatalf("stage payload = %#v", staged)
	}
}

// EPUB import may call the deterministic chapter parser, but it must never
// invoke a provider/model gateway as an implicit follow-up action.
func TestEPUBV2PipelineHasNoProviderGatewayDependency(t *testing.T) {
	source, err := os.ReadFile("epub_v2_processor.go")
	if err != nil {
		t.Fatalf("read EPUB processor: %v", err)
	}
	for _, forbidden := range []string{"provider-registry", "ai-gateway", "llm.Client", "OpenAI"} {
		if bytes.Contains(source, []byte(forbidden)) {
			t.Fatalf("EPUB import must not call a provider gateway; found %q", forbidden)
		}
	}
}

func testEPUBArchive(t *testing.T) []byte {
	t.Helper()
	files := map[string]string{
		"mimetype": "application/epub+zip", "META-INF/container.xml": `<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>`,
		"book.opf":      `<package><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>`,
		"chapter.xhtml": `<html><body><p>source chapter</p></body></html>`,
	}
	var output bytes.Buffer
	writer := zip.NewWriter(&output)
	for name, body := range files {
		entry, err := writer.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := entry.Write([]byte(body)); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return output.Bytes()
}

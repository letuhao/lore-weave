package epubimport

import (
	"archive/zip"
	"bytes"
	"fmt"
	"strings"
	"testing"
)

// BenchmarkInspectReferenceEPUBs measures the two release-reference shapes
// without committing source books. The generated bodies are deterministic and
// deliberately incompressible enough to exercise archive byte accounting.
func BenchmarkInspectReferenceEPUBs(b *testing.B) {
	for _, shape := range []struct {
		name, chapters string
		count, bytes   int
	}{
		{name: "50_chapters_10_MiB", count: 50, bytes: 10 << 20},
		{name: "500_chapters_100_MiB", count: 500, bytes: 100 << 20},
	} {
		b.Run(shape.name, func(b *testing.B) {
			data := buildReferenceEPUB(b, shape.count, shape.bytes)
			b.ReportMetric(float64(len(data)), "compressed_bytes")
			b.SetBytes(int64(shape.bytes))
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				if _, err := Inspect(data, DefaultLimits()); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}

func buildReferenceEPUB(tb testing.TB, chapters, totalBytes int) []byte {
	tb.Helper()
	var body, opf, spine strings.Builder
	body.WriteString(`<package><manifest>`)
	perChapter := totalBytes / chapters
	for i := 0; i < chapters; i++ {
		name := fmt.Sprintf("chapter-%03d.xhtml", i)
		body.WriteString(fmt.Sprintf(`<item id="c%d" href="%s" media-type="application/xhtml+xml"/>`, i, name))
		opf.WriteString(fmt.Sprintf(`<itemref idref="c%d"/>`, i))
		spine.WriteString(name + "\x00")
	}
	body.WriteString(`</manifest><spine>` + opf.String() + `</spine></package>`)
	files := map[string][]byte{
		"mimetype":               []byte(epubMIME),
		"META-INF/container.xml": []byte(`<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>`),
		"book.opf":               []byte(body.String()),
	}
	seed := uint32(0x9e3779b9)
	for _, name := range strings.Split(strings.TrimSuffix(spine.String(), "\x00"), "\x00") {
		content := make([]byte, perChapter)
		for i := range content {
			seed = seed*1664525 + 1013904223
			content[i] = byte(32 + seed%95)
		}
		chapter := append([]byte(`<html><body><p>`), content...)
		files[name] = append(chapter, []byte(`</p></body></html>`)...)
	}
	var output bytes.Buffer
	writer := zip.NewWriter(&output)
	for name, content := range files {
		entry, err := writer.Create(name)
		if err != nil {
			tb.Fatal(err)
		}
		if _, err := entry.Write(content); err != nil {
			tb.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		tb.Fatal(err)
	}
	return output.Bytes()
}

package epubimport

import (
	"archive/zip"
	"bytes"
	"encoding/base64"
	"fmt"
	"net/url"
	"path"
	"strings"

	"golang.org/x/net/html"
)

// ResolveAndRewriteAssets resolves local image references in one content
// fragment, validates their bytes, and replaces them through storeAsset. It
// intentionally handles no external URLs, CSS, fonts, audio, or video.
func ResolveAndRewriteAssets(epub []byte, contentHref, rawHTML string, limits Limits, storeAsset AssetURLResolver) (string, []Diagnostic, error) {
	if storeAsset == nil {
		return "", nil, fmt.Errorf("asset URL resolver is required")
	}
	archive, err := openEPUBAssetArchive(epub, limits.Normalize())
	if err != nil {
		return "", nil, err
	}
	contentPath, err := canonicalArchivePath(contentHref)
	if err != nil {
		return "", nil, err
	}
	doc, err := html.Parse(strings.NewReader(rawHTML))
	if err != nil {
		return "", nil, &Error{Code: CodeInvalidNavigation, Message: "chapter HTML is invalid"}
	}
	resolver := assetRewriter{
		archive:    archive,
		base:       path.Dir(contentPath),
		limits:     limits.Normalize(),
		storeAsset: storeAsset,
		urls:       make(map[string]string),
	}
	resolver.walk(doc)
	var output bytes.Buffer
	if err := html.Render(&output, doc); err != nil {
		return "", resolver.diagnostics, &Error{Code: CodeInvalidNavigation, Message: "chapter HTML cannot be serialized"}
	}
	return output.String(), resolver.diagnostics, nil
}

// ExtractCover reads the already inspected cover candidate from a retained
// EPUB source. Callers own destination storage and must decide when the
// user-approved cover policy permits applying it to a book.
func ExtractCover(epub []byte, candidate CoverCandidate, limits Limits) (ResolvedAsset, error) {
	archive, err := openEPUBAssetArchive(epub, limits.Normalize())
	if err != nil {
		return ResolvedAsset{}, err
	}
	sourcePath, err := canonicalArchivePath(candidate.SourcePath)
	if err != nil {
		return ResolvedAsset{}, err
	}
	file, ok := archive.files[sourcePath]
	if !ok {
		return ResolvedAsset{}, &Error{Code: CodeContentUnavailable, Message: "EPUB cover resource is unavailable"}
	}
	manifest, ok := archive.manifestAsset(sourcePath)
	if !ok {
		return ResolvedAsset{}, &Error{Code: CodeUnsupportedResource, Message: "EPUB cover is not declared in the manifest"}
	}
	data, err := archive.read(file)
	if err != nil || int64(len(data)) > limits.Normalize().MaxSingleEntrySize {
		return ResolvedAsset{}, &Error{Code: CodeUnsupportedResource, Message: "EPUB cover exceeds the configured size limit"}
	}
	mediaType, ok := validateImageBytes(data, manifest.MediaType)
	if !ok {
		return ResolvedAsset{}, &Error{Code: CodeUnsupportedResource, Message: "EPUB cover MIME type is invalid"}
	}
	return ResolvedAsset{SourcePath: sourcePath, MediaType: mediaType, SHA256: hash(data), SizeBytes: int64(len(data)), Data: data}, nil
}

func openEPUBAssetArchive(epub []byte, limits Limits) (*archive, error) {
	inspection, err := Inspect(epub, limits)
	if err != nil {
		return nil, err
	}
	_ = inspection // Inspect establishes the same archive validation contract as worker processing.
	zr, err := zipReader(epub)
	if err != nil {
		return nil, err
	}
	ar, err := openArchive(zr, limits)
	if err != nil {
		return nil, err
	}
	if err := ar.loadPackage(); err != nil {
		return nil, err
	}
	return ar, nil
}

// zipReader is kept narrow to make ResolveAndRewriteAssets share Inspect's
// archive constraints without exporting the archive representation.
func zipReader(data []byte) (*zip.Reader, error) {
	if len(data) < 4 || !bytes.Equal(data[:4], []byte("PK\x03\x04")) {
		return nil, &Error{Code: CodeInvalidArchive, Message: "EPUB must contain a ZIP local-file signature"}
	}
	reader, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, &Error{Code: CodeInvalidArchive, Message: "EPUB ZIP directory is unreadable"}
	}
	return reader, nil
}

type assetRewriter struct {
	archive     *archive
	base        string
	limits      Limits
	storeAsset  AssetURLResolver
	urls        map[string]string
	diagnostics []Diagnostic
}

func (r *assetRewriter) walk(node *html.Node) {
	for child := node.FirstChild; child != nil; child = child.NextSibling {
		r.walk(child)
	}
	if node.Type != html.ElementNode {
		return
	}
	switch strings.ToLower(node.Data) {
	case "img":
		r.rewriteAttribute(node, "src")
		r.rewriteSrcset(node)
	case "image":
		// SVG <image href> is parsed as an ordinary element by x/net/html.
		r.rewriteAttribute(node, "href")
		r.rewriteAttribute(node, "xlink:href")
	case "object":
		r.rewriteObject(node)
	}
}

func (r *assetRewriter) rewriteObject(node *html.Node) {
	data := nodeAttribute(node, "data")
	if data == "" {
		return
	}
	asset, urlValue, ok := r.resolve(data)
	if !ok {
		r.removeAttribute(node, "data")
		return
	}
	if !isImageMediaType(nodeAttribute(node, "type")) && !isImageMediaType(asset.MediaType) {
		r.diagnostics = append(r.diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "non-image EPUB object removed"})
		r.removeAttribute(node, "data")
		return
	}
	// Object can embed executable browser content. A validated image becomes an
	// image node before sanitization, preserving its safe semantic intent.
	node.Data = "img"
	node.Attr = []html.Attribute{{Key: "src", Val: urlValue}}
}

func (r *assetRewriter) rewriteAttribute(node *html.Node, key string) {
	for index := range node.Attr {
		if !strings.EqualFold(node.Attr[index].Key, key) {
			continue
		}
		_, rewritten, ok := r.resolve(node.Attr[index].Val)
		if !ok {
			node.Attr = append(node.Attr[:index], node.Attr[index+1:]...)
			return
		}
		node.Attr[index].Val = rewritten
		return
	}
}

func (r *assetRewriter) rewriteSrcset(node *html.Node) {
	for index := range node.Attr {
		if !strings.EqualFold(node.Attr[index].Key, "srcset") {
			continue
		}
		parts := strings.Split(node.Attr[index].Val, ",")
		rewritten := make([]string, 0, len(parts))
		for _, part := range parts {
			fields := strings.Fields(strings.TrimSpace(part))
			if len(fields) == 0 {
				continue
			}
			_, value, ok := r.resolve(fields[0])
			if !ok {
				continue
			}
			fields[0] = value
			rewritten = append(rewritten, strings.Join(fields, " "))
		}
		if len(rewritten) == 0 {
			node.Attr = append(node.Attr[:index], node.Attr[index+1:]...)
			return
		}
		node.Attr[index].Val = strings.Join(rewritten, ", ")
		return
	}
}

func (r *assetRewriter) resolve(raw string) (ResolvedAsset, string, bool) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return ResolvedAsset{}, "", false
	}
	if strings.HasPrefix(strings.ToLower(value), "data:") {
		asset, err := parseImageDataURI(value, r.limits)
		if err != nil {
			r.diagnostics = append(r.diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "invalid embedded EPUB image removed"})
			return ResolvedAsset{}, "", false
		}
		return r.store(asset)
	}
	parsed, err := url.Parse(value)
	if err != nil || parsed.IsAbs() || strings.HasPrefix(value, "//") || strings.HasPrefix(parsed.Path, "/") {
		r.diagnostics = append(r.diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "external EPUB image removed"})
		return ResolvedAsset{}, "", false
	}
	assetPath, err := r.archive.resolveFrom(r.base, parsed.EscapedPath())
	if err != nil {
		r.diagnostics = append(r.diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "unsafe EPUB image path removed"})
		return ResolvedAsset{}, "", false
	}
	file, ok := r.archive.files[assetPath]
	if !ok {
		r.diagnostics = append(r.diagnostics, Diagnostic{Code: CodeContentUnavailable, Message: "EPUB image resource is missing"})
		return ResolvedAsset{}, "", false
	}
	manifest, ok := r.archive.manifestAsset(assetPath)
	if !ok {
		r.diagnostics = append(r.diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "EPUB image is not declared in the manifest"})
		return ResolvedAsset{}, "", false
	}
	data, err := r.archive.read(file)
	if err != nil || int64(len(data)) > r.limits.MaxSingleEntrySize {
		r.diagnostics = append(r.diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "EPUB image exceeds the configured size limit"})
		return ResolvedAsset{}, "", false
	}
	mediaType, ok := validateImageBytes(data, manifest.MediaType)
	if !ok {
		r.diagnostics = append(r.diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "EPUB image MIME type is invalid"})
		return ResolvedAsset{}, "", false
	}
	return r.store(ResolvedAsset{SourcePath: assetPath, MediaType: mediaType, SHA256: hash(data), SizeBytes: int64(len(data)), Data: data})
}

func (r *assetRewriter) store(asset ResolvedAsset) (ResolvedAsset, string, bool) {
	cacheKey := asset.SourcePath + ":" + asset.SHA256
	if existing, ok := r.urls[cacheKey]; ok {
		return asset, existing, true
	}
	value, err := r.storeAsset(asset)
	if err != nil || strings.TrimSpace(value) == "" {
		r.diagnostics = append(r.diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "EPUB image could not be stored"})
		return ResolvedAsset{}, "", false
	}
	r.urls[cacheKey] = value
	return asset, value, true
}

func (r *assetRewriter) removeAttribute(node *html.Node, key string) {
	for index := range node.Attr {
		if strings.EqualFold(node.Attr[index].Key, key) {
			node.Attr = append(node.Attr[:index], node.Attr[index+1:]...)
			return
		}
	}
}

func (a *archive) manifestAsset(assetPath string) (opfManifestItem, bool) {
	for _, item := range a.pkg.Manifest.Items {
		resolved, err := a.resolve(item.Href)
		if err == nil && resolved == assetPath {
			return item, true
		}
	}
	return opfManifestItem{}, false
}

func parseImageDataURI(raw string, limits Limits) (ResolvedAsset, error) {
	comma := strings.IndexByte(raw, ',')
	if comma < 0 {
		return ResolvedAsset{}, fmt.Errorf("data URI payload is missing")
	}
	meta := strings.TrimPrefix(strings.ToLower(raw[:comma]), "data:")
	if !strings.HasPrefix(meta, "image/") || !strings.Contains(meta, ";base64") {
		return ResolvedAsset{}, fmt.Errorf("data URI is not a base64 image")
	}
	decoded, err := base64.StdEncoding.DecodeString(raw[comma+1:])
	if err != nil || int64(len(decoded)) > limits.MaxSingleEntrySize {
		return ResolvedAsset{}, fmt.Errorf("data URI is invalid or exceeds the configured limit")
	}
	declared := strings.TrimSpace(strings.Split(meta, ";")[0])
	mediaType, ok := validateImageBytes(decoded, declared)
	if !ok {
		return ResolvedAsset{}, fmt.Errorf("data URI image MIME type is invalid")
	}
	digest := hash(decoded)
	return ResolvedAsset{SourcePath: "data:" + digest, MediaType: mediaType, SHA256: digest, SizeBytes: int64(len(decoded)), Data: decoded}, nil
}

func validateImageBytes(data []byte, declared string) (string, bool) {
	mediaType := ""
	switch {
	case len(data) >= 8 && bytes.Equal(data[:8], []byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'}):
		mediaType = "image/png"
	case len(data) >= 3 && bytes.Equal(data[:3], []byte{0xff, 0xd8, 0xff}):
		mediaType = "image/jpeg"
	case len(data) >= 6 && (bytes.Equal(data[:6], []byte("GIF87a")) || bytes.Equal(data[:6], []byte("GIF89a"))):
		mediaType = "image/gif"
	case len(data) >= 12 && bytes.Equal(data[:4], []byte("RIFF")) && bytes.Equal(data[8:12], []byte("WEBP")):
		mediaType = "image/webp"
	case looksLikeSafeSVG(data):
		mediaType = "image/svg+xml"
	default:
		return "", false
	}
	declared = strings.ToLower(strings.TrimSpace(declared))
	return mediaType, declared == "" || declared == mediaType
}

func looksLikeSafeSVG(data []byte) bool {
	if len(data) == 0 || len(data) > 5<<20 {
		return false
	}
	value := strings.ToLower(strings.TrimSpace(string(data)))
	if !strings.Contains(value, "<svg") {
		return false
	}
	for _, forbidden := range []string{"<script", "<foreignobject", "javascript:", "http://", "https://", "//"} {
		if strings.Contains(value, forbidden) {
			return false
		}
	}
	return true
}

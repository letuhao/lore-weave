package epubimport

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/xml"
	"io"
	"net/url"
	"path"
	"sort"
	"strings"
)

const epubMIME = "application/epub+zip"

type archive struct {
	files map[string]*zip.File
	base  string
	pkg   opfPackage
	limit Limits
}

// Inspect validates an EPUB archive, reads package-level metadata, and
// normalizes its navigation without extracting chapter bodies into memory.
func Inspect(data []byte, limits Limits) (*Inspection, error) {
	limit := limits.Normalize()
	if int64(len(data)) > limit.MaxCompressedSize {
		return nil, archiveLimit("compressed source exceeds configured limit")
	}
	if len(data) < 4 || !bytes.Equal(data[:4], []byte("PK\x03\x04")) {
		return nil, &Error{Code: CodeInvalidArchive, Message: "EPUB must contain a ZIP local-file signature"}
	}
	zr, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, &Error{Code: CodeInvalidArchive, Message: "EPUB ZIP directory is unreadable"}
	}
	ar, err := openArchive(zr, limit)
	if err != nil {
		return nil, err
	}
	if _, ok := ar.files["META-INF/encryption.xml"]; ok {
		return nil, &Error{Code: CodeDRMUnsupported, Message: "encrypted EPUBs are not supported"}
	}
	mimetype, ok := ar.files["mimetype"]
	if !ok {
		return nil, &Error{Code: CodeInvalidMIME, Message: "EPUB mimetype entry is missing"}
	}
	mimetypeBytes, err := ar.read(mimetype)
	if err != nil {
		return nil, err
	}
	if strings.TrimSpace(string(mimetypeBytes)) != epubMIME {
		return nil, &Error{Code: CodeInvalidMIME, Message: "EPUB mimetype is not application/epub+zip"}
	}
	if err := ar.loadPackage(); err != nil {
		return nil, err
	}

	if len(ar.contentDocuments()) > limit.MaxContentDocuments {
		return nil, archiveLimit("content document count exceeds configured limit")
	}
	assets, err := ar.assets()
	if err != nil {
		return nil, err
	}
	metadata := ar.pkg.Metadata.metadata()
	metadata.EPUBVersion = strings.TrimSpace(ar.pkg.Version)
	inspection := &Inspection{
		SHA256:           hash(data),
		CompressedSize:   int64(len(data)),
		UncompressedSize: ar.uncompressedSize(),
		Metadata:         metadata,
		Assets:           assets,
		Warnings:         []Diagnostic{},
	}
	inspection.Cover = ar.cover()
	structure, source, warnings, err := ar.navigation(inspection.SHA256)
	if err != nil {
		return nil, err
	}
	inspection.NavigationSource = source
	inspection.Structure = structure
	inspection.Warnings = append(inspection.Warnings, warnings...)
	return inspection, nil
}

func openArchive(zr *zip.Reader, limit Limits) (*archive, error) {
	if len(zr.File) > limit.MaxZipEntries {
		return nil, archiveLimit("ZIP entry count exceeds configured limit")
	}
	files := make(map[string]*zip.File, len(zr.File))
	var total int64
	for _, file := range zr.File {
		name, err := canonicalArchivePath(file.Name)
		if err != nil {
			return nil, err
		}
		if _, exists := files[name]; exists {
			return nil, &Error{Code: CodeInvalidArchivePath, Message: "EPUB ZIP contains colliding normalized paths"}
		}
		if int64(file.UncompressedSize64) > limit.MaxSingleEntrySize {
			return nil, archiveLimit("ZIP entry exceeds configured size limit")
		}
		total += int64(file.UncompressedSize64)
		if total > limit.MaxUncompressedSize {
			return nil, archiveLimit("EPUB uncompressed size exceeds configured limit")
		}
		if file.CompressedSize64 > 0 && float64(file.UncompressedSize64)/float64(file.CompressedSize64) > limit.MaxCompressionRatio {
			return nil, archiveLimit("ZIP entry compression ratio exceeds configured limit")
		}
		files[name] = file
	}
	return &archive{files: files, limit: limit}, nil
}

func (a *archive) loadPackage() error {
	container, ok := a.files["META-INF/container.xml"]
	if !ok {
		return &Error{Code: CodeContainerMissing, Message: "META-INF/container.xml is missing"}
	}
	data, err := a.read(container)
	if err != nil {
		return err
	}
	var parsed containerDocument
	if err := xml.Unmarshal(data, &parsed); err != nil || len(parsed.Rootfiles) == 0 {
		return &Error{Code: CodeContainerMissing, Message: "META-INF/container.xml has no package document"}
	}
	opfPath, err := canonicalArchivePath(parsed.Rootfiles[0].FullPath)
	if err != nil {
		return &Error{Code: CodeInvalidOPF, Message: "package document path is invalid"}
	}
	opf, ok := a.files[opfPath]
	if !ok {
		return &Error{Code: CodeInvalidOPF, Message: "package document is missing"}
	}
	opfBytes, err := a.read(opf)
	if err != nil {
		return err
	}
	if err := xml.Unmarshal(opfBytes, &a.pkg); err != nil {
		return &Error{Code: CodeInvalidOPF, Message: "package document is invalid XML"}
	}
	if len(a.pkg.Manifest.Items) == 0 {
		return &Error{Code: CodeInvalidOPF, Message: "package document has no manifest"}
	}
	a.base = path.Dir(opfPath)
	return nil
}

func (a *archive) read(file *zip.File) ([]byte, error) {
	if int64(file.UncompressedSize64) > a.limit.MaxSingleEntrySize {
		return nil, archiveLimit("ZIP entry exceeds configured size limit")
	}
	r, err := file.Open()
	if err != nil {
		return nil, &Error{Code: CodeInvalidArchive, Message: "EPUB ZIP entry cannot be opened"}
	}
	defer r.Close()
	return io.ReadAll(io.LimitReader(r, a.limit.MaxSingleEntrySize+1))
}

func (a *archive) uncompressedSize() int64 {
	var total int64
	for _, file := range a.files {
		total += int64(file.UncompressedSize64)
	}
	return total
}

func (a *archive) manifestByID() map[string]opfManifestItem {
	items := make(map[string]opfManifestItem, len(a.pkg.Manifest.Items))
	for _, item := range a.pkg.Manifest.Items {
		items[item.ID] = item
	}
	return items
}

func (a *archive) contentDocuments() []string {
	paths := make([]string, 0)
	for _, item := range a.pkg.Manifest.Items {
		if !isContentDocument(item) {
			continue
		}
		if itemPath, err := a.resolve(item.Href); err == nil {
			paths = append(paths, itemPath)
		}
	}
	sort.Strings(paths)
	return paths
}

func (a *archive) assets() ([]Asset, error) {
	assets := make([]Asset, 0)
	for _, item := range a.pkg.Manifest.Items {
		if isContentDocument(item) || isNavigationDocument(item) || isNCX(item) {
			continue
		}
		assetPath, err := a.resolve(item.Href)
		if err != nil {
			continue
		}
		if file, ok := a.files[assetPath]; ok {
			assets = append(assets, Asset{SourcePath: assetPath, MediaType: item.MediaType, SizeBytes: int64(file.UncompressedSize64)})
		}
	}
	if len(assets) > a.limit.MaxAssets {
		return nil, archiveLimit("asset count exceeds configured limit")
	}
	return assets, nil
}

func (a *archive) cover() *CoverCandidate {
	for _, item := range a.pkg.Manifest.Items {
		if hasProperty(item.Properties, "cover-image") {
			return a.coverFor(item, "epub3-cover-image")
		}
	}
	for _, meta := range a.pkg.Metadata.Meta {
		if strings.EqualFold(strings.TrimSpace(meta.Name), "cover") {
			if item, ok := a.manifestByID()[strings.TrimSpace(meta.Content)]; ok {
				return a.coverFor(item, "epub2-meta-cover")
			}
		}
	}
	for _, ref := range a.pkg.Guide.References {
		if strings.EqualFold(strings.TrimSpace(ref.Type), "cover") {
			if itemPath, err := a.resolve(splitHref(ref.Href).path); err == nil {
				if file, ok := a.files[itemPath]; ok {
					return &CoverCandidate{SourcePath: itemPath, MediaType: mediaTypeForPath(itemPath), SizeBytes: int64(file.UncompressedSize64), SourceMethod: "guide-cover"}
				}
			}
		}
	}
	for _, item := range a.pkg.Manifest.Items {
		name := strings.ToLower(path.Base(item.Href))
		if strings.Contains(name, "cover") && isImageMediaType(item.MediaType) {
			return a.coverFor(item, "filename-fallback")
		}
	}
	return nil
}

func (a *archive) coverFor(item opfManifestItem, sourceMethod string) *CoverCandidate {
	itemPath, err := a.resolve(item.Href)
	if err != nil {
		return nil
	}
	file, ok := a.files[itemPath]
	if !ok || !isImageMediaType(item.MediaType) {
		return nil
	}
	return &CoverCandidate{SourcePath: itemPath, MediaType: item.MediaType, SizeBytes: int64(file.UncompressedSize64), SourceMethod: sourceMethod}
}

func (a *archive) resolve(href string) (string, error) {
	h := splitHref(href)
	if h.path == "" {
		return "", &Error{Code: CodeInvalidArchivePath, Message: "EPUB reference path is empty"}
	}
	decoded, err := url.PathUnescape(h.path)
	if err != nil {
		return "", &Error{Code: CodeInvalidArchivePath, Message: "EPUB reference path is malformed"}
	}
	if strings.HasPrefix(decoded, "/") || strings.Contains(decoded, "\\") {
		return "", &Error{Code: CodeInvalidArchivePath, Message: "EPUB reference path is unsafe"}
	}
	return canonicalArchivePath(path.Join(a.base, decoded))
}

func canonicalArchivePath(raw string) (string, error) {
	if raw == "" || strings.HasPrefix(raw, "/") || strings.HasPrefix(raw, "\\") || strings.Contains(raw, "\\") {
		return "", &Error{Code: CodeInvalidArchivePath, Message: "EPUB archive path is unsafe"}
	}
	clean := path.Clean(raw)
	if clean == "." || clean == ".." || strings.HasPrefix(clean, "../") {
		return "", &Error{Code: CodeInvalidArchivePath, Message: "EPUB archive path escapes its root"}
	}
	return clean, nil
}

func archiveLimit(message string) error {
	return &Error{Code: CodeArchiveLimit, Message: message}
}

func hash(data []byte) string {
	digest := sha256.Sum256(data)
	return hex.EncodeToString(digest[:])
}

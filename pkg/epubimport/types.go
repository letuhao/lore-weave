// Package epubimport provides deterministic, bounded EPUB inspection and
// chapter-range normalization shared by Book Service and worker-infra.
package epubimport

import (
	"fmt"
	"strconv"
)

// ErrorCode is stable across the public preview API, worker checkpoints, and
// import reports. It is intentionally free of source text.
type ErrorCode string

const (
	CodeInvalidArchive      ErrorCode = "epub_invalid_archive"
	CodeInvalidMIME         ErrorCode = "epub_mimetype_invalid"
	CodeContainerMissing    ErrorCode = "epub_container_missing"
	CodeInvalidOPF          ErrorCode = "epub_opf_invalid"
	CodeDRMUnsupported      ErrorCode = "epub_drm_unsupported"
	CodeInvalidArchivePath  ErrorCode = "epub_archive_path_invalid"
	CodeArchiveLimit        ErrorCode = "epub_archive_limit_exceeded"
	CodeInvalidNavigation   ErrorCode = "epub_navigation_invalid"
	CodeContentUnavailable  ErrorCode = "epub_content_unavailable"
	CodeNavigationMissing   ErrorCode = "navigation_missing_spine_fallback"
	CodeAnchorMissing       ErrorCode = "navigation_anchor_missing"
	CodeRangeAmbiguous      ErrorCode = "navigation_range_ambiguous"
	CodeUnsupportedResource ErrorCode = "unsupported_resource"
)

// Error carries a safe, machine-readable rejection reason. Message must never
// include manuscript content or archive bytes.
type Error struct {
	Code    ErrorCode
	Message string
}

func (e *Error) Error() string {
	return fmt.Sprintf("%s: %s", e.Code, e.Message)
}

// Diagnostic is a non-fatal inspection or extraction finding.
type Diagnostic struct {
	Code      ErrorCode `json:"code"`
	Message   string    `json:"message"`
	SourceKey string    `json:"source_key,omitempty"`
}

// Limits bound archive work before an EPUB is inspected or extracted.
// Zero fields are replaced with DefaultLimits by Normalize.
type Limits struct {
	MaxCompressedSize   int64
	MaxUncompressedSize int64
	MaxZipEntries       int
	MaxSingleEntrySize  int64
	MaxCompressionRatio float64
	MaxContentDocuments int
	MaxNavigationNodes  int
	MaxAssets           int
	MaxChapterHTMLSize  int64
}

// DefaultLimits are conservative deployment defaults. Services may lower
// these values, but must not allow user input to raise them.
func DefaultLimits() Limits {
	return Limits{
		MaxCompressedSize:   200 << 20,
		MaxUncompressedSize: 2 << 30,
		MaxZipEntries:       20000,
		MaxSingleEntrySize:  100 << 20,
		MaxCompressionRatio: 100,
		MaxContentDocuments: 5000,
		MaxNavigationNodes:  10000,
		MaxAssets:           10000,
		MaxChapterHTMLSize:  20 << 20,
	}
}

// Normalize supplies defaults for unset limits and returns an independent
// value so callers can safely reuse a shared deployment configuration.
func (l Limits) Normalize() Limits {
	d := DefaultLimits()
	if l.MaxCompressedSize > 0 {
		d.MaxCompressedSize = l.MaxCompressedSize
	}
	if l.MaxUncompressedSize > 0 {
		d.MaxUncompressedSize = l.MaxUncompressedSize
	}
	if l.MaxZipEntries > 0 {
		d.MaxZipEntries = l.MaxZipEntries
	}
	if l.MaxSingleEntrySize > 0 {
		d.MaxSingleEntrySize = l.MaxSingleEntrySize
	}
	if l.MaxCompressionRatio > 0 {
		d.MaxCompressionRatio = l.MaxCompressionRatio
	}
	if l.MaxContentDocuments > 0 {
		d.MaxContentDocuments = l.MaxContentDocuments
	}
	if l.MaxNavigationNodes > 0 {
		d.MaxNavigationNodes = l.MaxNavigationNodes
	}
	if l.MaxAssets > 0 {
		d.MaxAssets = l.MaxAssets
	}
	if l.MaxChapterHTMLSize > 0 {
		d.MaxChapterHTMLSize = l.MaxChapterHTMLSize
	}
	return d
}

// LimitsFromEnv reads deployment ceilings without letting a malformed setting
// disable a safety limit. Supported variables use the EPUB_IMPORT_ prefix and
// accept base-10 integer bytes/counts; EPUB_IMPORT_MAX_COMPRESSION_RATIO may
// be decimal.
func LimitsFromEnv(lookup func(string) string) Limits {
	limits := DefaultLimits()
	setInt64 := func(name string, target *int64) {
		if raw := lookup(name); raw != "" {
			if value, err := strconv.ParseInt(raw, 10, 64); err == nil && value > 0 {
				*target = value
			}
		}
	}
	setInt := func(name string, target *int) {
		if raw := lookup(name); raw != "" {
			if value, err := strconv.Atoi(raw); err == nil && value > 0 {
				*target = value
			}
		}
	}
	setInt64("EPUB_IMPORT_MAX_COMPRESSED_SIZE", &limits.MaxCompressedSize)
	setInt64("EPUB_IMPORT_MAX_UNCOMPRESSED_SIZE", &limits.MaxUncompressedSize)
	setInt("EPUB_IMPORT_MAX_ZIP_ENTRIES", &limits.MaxZipEntries)
	setInt64("EPUB_IMPORT_MAX_SINGLE_ENTRY_SIZE", &limits.MaxSingleEntrySize)
	if raw := lookup("EPUB_IMPORT_MAX_COMPRESSION_RATIO"); raw != "" {
		if value, err := strconv.ParseFloat(raw, 64); err == nil && value > 0 {
			limits.MaxCompressionRatio = value
		}
	}
	setInt("EPUB_IMPORT_MAX_CONTENT_DOCUMENTS", &limits.MaxContentDocuments)
	setInt("EPUB_IMPORT_MAX_NAVIGATION_NODES", &limits.MaxNavigationNodes)
	setInt("EPUB_IMPORT_MAX_ASSETS", &limits.MaxAssets)
	setInt64("EPUB_IMPORT_MAX_CHAPTER_HTML_SIZE", &limits.MaxChapterHTMLSize)
	return limits
}

type NavigationSource string

const (
	NavigationEPUB3Nav NavigationSource = "epub3-nav"
	NavigationEPUB2NCX NavigationSource = "epub2-ncx"
	NavigationSpine    NavigationSource = "spine-fallback"
)

type Role string

const (
	RoleVolume      Role = "volume"
	RolePart        Role = "part"
	RoleChapter     Role = "chapter"
	RoleSection     Role = "section"
	RoleFrontmatter Role = "frontmatter"
	RoleBackmatter  Role = "backmatter"
	RoleAppendix    Role = "appendix"
	RoleUnknown     Role = "unknown"
)

type ContentRange struct {
	Href        string `json:"href"`
	StartAnchor string `json:"start_anchor,omitempty"`
	EndAnchor   string `json:"end_anchor,omitempty"`
}

// NavigationNode preserves the full source navigation tree. Only a selected
// leaf is a default chapter candidate; parent nodes remain hierarchy.
type NavigationNode struct {
	SourceKey       string            `json:"source_key"`
	SourceHref      string            `json:"source_href,omitempty"`
	SourceFragment  string            `json:"source_fragment,omitempty"`
	ParentSourceKey string            `json:"parent_source_key,omitempty"`
	Ordinal         int               `json:"ordinal"`
	Depth           int               `json:"depth"`
	Role            Role              `json:"role"`
	Title           string            `json:"title"`
	Linear          bool              `json:"linear"`
	Selected        bool              `json:"selected"`
	ContentRanges   []ContentRange    `json:"content_ranges,omitempty"`
	Warnings        []Diagnostic      `json:"warnings,omitempty"`
	Children        []*NavigationNode `json:"children,omitempty"`
}

type Metadata struct {
	Title           string   `json:"title,omitempty"`
	Creators        []string `json:"creators,omitempty"`
	Language        string   `json:"language,omitempty"`
	Description     string   `json:"description,omitempty"`
	Publisher       string   `json:"publisher,omitempty"`
	Subjects        []string `json:"subjects,omitempty"`
	Identifiers     []string `json:"identifiers,omitempty"`
	PublicationDate string   `json:"publication_date,omitempty"`
	ModifiedDate    string   `json:"modified_date,omitempty"`
	Rights          string   `json:"rights,omitempty"`
	Series          string   `json:"series,omitempty"`
	SeriesIndex     string   `json:"series_index,omitempty"`
	EPUBVersion     string   `json:"epub_version,omitempty"`
}

type CoverCandidate struct {
	SourcePath   string `json:"source_path"`
	MediaType    string `json:"media_type"`
	SizeBytes    int64  `json:"size_bytes"`
	SourceMethod string `json:"source_method"`
}

type Asset struct {
	SourcePath string `json:"source_path"`
	MediaType  string `json:"media_type"`
	SizeBytes  int64  `json:"size_bytes"`
}

// ResolvedAsset is an image extracted from an EPUB content document. Data is
// deliberately transient: callers must store it in object storage and retain
// only the returned URL and provenance metadata.
type ResolvedAsset struct {
	SourcePath string `json:"source_path"`
	MediaType  string `json:"media_type"`
	SHA256     string `json:"sha256"`
	SizeBytes  int64  `json:"size_bytes"`
	Data       []byte `json:"-"`
}

// AssetURLResolver persists a validated asset and returns the browser-safe URL
// that replaces its EPUB-local reference. The resolver owns storage policy;
// this package never accesses a network or object store.
type AssetURLResolver func(ResolvedAsset) (string, error)

// Inspection contains no extracted manuscript HTML. It is safe to persist as
// the preview payload and use to initialize import items.
type Inspection struct {
	SHA256           string            `json:"sha256"`
	CompressedSize   int64             `json:"compressed_size"`
	UncompressedSize int64             `json:"uncompressed_size"`
	Metadata         Metadata          `json:"metadata"`
	Cover            *CoverCandidate   `json:"cover,omitempty"`
	NavigationSource NavigationSource  `json:"navigation_source"`
	Structure        []*NavigationNode `json:"structure"`
	Assets           []Asset           `json:"assets"`
	Warnings         []Diagnostic      `json:"warnings"`
}

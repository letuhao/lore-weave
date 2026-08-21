package epubimport

import (
	"net/url"
	"path"
	"strings"
)

type containerDocument struct {
	Rootfiles []struct {
		FullPath string `xml:"full-path,attr"`
	} `xml:"rootfiles>rootfile"`
}

type opfPackage struct {
	Version  string      `xml:"version,attr"`
	Metadata opfMetadata `xml:"metadata"`
	Manifest struct {
		Items []opfManifestItem `xml:"item"`
	} `xml:"manifest"`
	Spine struct {
		TOC      string        `xml:"toc,attr"`
		Itemrefs []opfSpineRef `xml:"itemref"`
	} `xml:"spine"`
	Guide struct {
		References []opfGuideReference `xml:"reference"`
	} `xml:"guide"`
}

type opfMetadata struct {
	Titles       []string `xml:"title"`
	Creators     []string `xml:"creator"`
	Languages    []string `xml:"language"`
	Descriptions []string `xml:"description"`
	Publishers   []string `xml:"publisher"`
	Subjects     []string `xml:"subject"`
	Identifiers  []string `xml:"identifier"`
	Dates        []string `xml:"date"`
	Rights       []string `xml:"rights"`
	Meta         []struct {
		Name     string `xml:"name,attr"`
		Content  string `xml:"content,attr"`
		Property string `xml:"property,attr"`
		Value    string `xml:",chardata"`
	} `xml:"meta"`
}

type opfManifestItem struct {
	ID         string `xml:"id,attr"`
	Href       string `xml:"href,attr"`
	MediaType  string `xml:"media-type,attr"`
	Properties string `xml:"properties,attr"`
}

type opfSpineRef struct {
	IDRef  string `xml:"idref,attr"`
	Linear string `xml:"linear,attr"`
}

type opfGuideReference struct {
	Type string `xml:"type,attr"`
	Href string `xml:"href,attr"`
}

func (m opfMetadata) metadata() Metadata {
	result := Metadata{
		Title:       firstNonEmpty(m.Titles),
		Creators:    nonEmpty(m.Creators),
		Language:    firstNonEmpty(m.Languages),
		Description: firstNonEmpty(m.Descriptions),
		Publisher:   firstNonEmpty(m.Publishers),
		Subjects:    nonEmpty(m.Subjects),
		Identifiers: nonEmpty(m.Identifiers),
		Rights:      firstNonEmpty(m.Rights),
	}
	for _, date := range m.Dates {
		if strings.TrimSpace(date) != "" {
			result.PublicationDate = strings.TrimSpace(date)
			break
		}
	}
	for _, meta := range m.Meta {
		property := strings.ToLower(strings.TrimSpace(meta.Property))
		value := strings.TrimSpace(meta.Content)
		if value == "" {
			value = strings.TrimSpace(meta.Value)
		}
		switch property {
		case "dcterms:modified":
			result.ModifiedDate = value
		case "belongs-to-collection", "calibre:series":
			result.Series = value
		case "group-position", "calibre:series_index":
			result.SeriesIndex = value
		}
	}
	return result
}

func firstNonEmpty(values []string) string {
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			return value
		}
	}
	return ""
}

func nonEmpty(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			result = append(result, value)
		}
	}
	return result
}

func isContentDocument(item opfManifestItem) bool {
	mediaType := strings.ToLower(strings.TrimSpace(item.MediaType))
	href := strings.ToLower(splitHref(item.Href).path)
	return mediaType == "application/xhtml+xml" || mediaType == "text/html" || strings.HasSuffix(href, ".xhtml") || strings.HasSuffix(href, ".html") || strings.HasSuffix(href, ".htm")
}

func isNavigationDocument(item opfManifestItem) bool {
	return hasProperty(item.Properties, "nav")
}

func isNCX(item opfManifestItem) bool {
	return strings.Contains(strings.ToLower(item.MediaType), "ncx") || strings.HasSuffix(strings.ToLower(splitHref(item.Href).path), ".ncx")
}

func hasProperty(properties, wanted string) bool {
	for _, property := range strings.Fields(strings.ToLower(properties)) {
		if property == wanted {
			return true
		}
	}
	return false
}

func isImageMediaType(mediaType string) bool {
	return strings.HasPrefix(strings.ToLower(strings.TrimSpace(mediaType)), "image/")
}

func mediaTypeForPath(value string) string {
	switch strings.ToLower(path.Ext(value)) {
	case ".jpg", ".jpeg":
		return "image/jpeg"
	case ".png":
		return "image/png"
	case ".gif":
		return "image/gif"
	case ".webp":
		return "image/webp"
	case ".svg":
		return "image/svg+xml"
	default:
		return "application/octet-stream"
	}
}

type hrefParts struct {
	path     string
	fragment string
}

func splitHref(raw string) hrefParts {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil {
		return hrefParts{path: raw}
	}
	return hrefParts{path: parsed.EscapedPath(), fragment: parsed.Fragment}
}

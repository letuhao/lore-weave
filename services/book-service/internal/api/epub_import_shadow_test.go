package api

import (
	"testing"

	"github.com/loreweave/epubimport"
)

func TestBuildEPUBShadowComparisonRecordsStructuralDelta(t *testing.T) {
	inspection := epubimport.Inspection{
		NavigationSource: epubimport.NavigationEPUB3Nav,
		Structure: []*epubimport.NavigationNode{
			{SourceHref: "text.xhtml", Linear: true, Selected: false, Children: []*epubimport.NavigationNode{
				{SourceHref: "text.xhtml", Linear: true, Selected: true},
				{SourceHref: "text.xhtml", Linear: true, Selected: true},
			}},
		},
	}
	comparison := buildEPUBShadowComparison(inspection)
	if comparison.LegacyChapterCount != 1 || comparison.V2ChapterCount != 2 || comparison.Delta != 1 {
		t.Fatalf("comparison = %+v, want legacy=1 v2=2 delta=1", comparison)
	}
	if len(comparison.Differences) != 1 || comparison.Differences[0] != "logical_navigation_count_differs_from_document_projection" {
		t.Fatalf("differences = %#v", comparison.Differences)
	}
}

func TestBuildEPUBShadowComparisonMarksSpineFallback(t *testing.T) {
	comparison := buildEPUBShadowComparison(epubimport.Inspection{NavigationSource: epubimport.NavigationSpine})
	if len(comparison.Differences) != 1 || comparison.Differences[0] != "navigation_fallback_used" {
		t.Fatalf("spine differences = %#v", comparison.Differences)
	}
}

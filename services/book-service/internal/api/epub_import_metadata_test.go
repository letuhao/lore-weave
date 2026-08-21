package api

import "testing"

func TestMergeMetadataSubjectsIsStableAndDeduplicated(t *testing.T) {
	got := mergeMetadataSubjects([]string{"fantasy", "  ", "history"}, []string{"history", "romance", "fantasy"})
	want := []string{"fantasy", "history", "romance"}
	if !equalStringSlices(got, want) {
		t.Fatalf("merged subjects = %#v, want %#v", got, want)
	}
}

func TestNormalizeMetadataSubjectsDropsEmptyAndDuplicates(t *testing.T) {
	got := normalizeMetadataSubjects([]string{"", " fantasy ", "fantasy", "history"})
	want := []string{"fantasy", "history"}
	if !equalStringSlices(got, want) {
		t.Fatalf("normalized subjects = %#v, want %#v", got, want)
	}
}

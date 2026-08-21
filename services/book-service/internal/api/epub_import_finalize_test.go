package api

import "testing"

func TestCanFinalizeEPUBImportWaitsForProcessingItem(t *testing.T) {
	if canFinalizeEPUBImport(0, 1, 0) {
		t.Fatal("finalize accepted an item that is still processing")
	}
	if canFinalizeEPUBImport(1, 0, 0) || canFinalizeEPUBImport(0, 0, 1) {
		t.Fatal("finalize accepted unfinished item state")
	}
	if !canFinalizeEPUBImport(0, 0, 0) {
		t.Fatal("finalize rejected a fully ready import")
	}
}

func TestShouldApplyEPUBImportCoverKeepsExistingBookByDefault(t *testing.T) {
	if shouldApplyEPUBImportCover("existing_book", []byte(`{}`)) {
		t.Fatal("existing book cover must be preserved without an explicit policy")
	}
	if !shouldApplyEPUBImportCover("existing_book", []byte(`{"metadata_policy":{"cover":"use_source"}}`)) {
		t.Fatal("explicit source cover policy was ignored")
	}
	if !shouldApplyEPUBImportCover("new_book", []byte(`{}`)) {
		t.Fatal("new book should receive its EPUB cover by default")
	}
	if shouldApplyEPUBImportCover("new_book", []byte(`{"metadata_policy":{"cover":"skip"}}`)) {
		t.Fatal("new book skip policy was ignored")
	}
}

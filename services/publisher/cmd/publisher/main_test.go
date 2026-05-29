package main

import "testing"

// TestBannerIsNonEmpty — sanity check that the build links against the
// constants module (catches accidental package-level break).
func TestBannerIsNonEmpty(t *testing.T) {
	if banner == "" {
		t.Fatal("banner empty — package break?")
	}
}

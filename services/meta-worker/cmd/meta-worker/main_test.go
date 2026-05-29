package main

import "testing"

func TestBannerIsNonEmpty(t *testing.T) {
	if banner == "" {
		t.Fatal("banner empty — package break?")
	}
}

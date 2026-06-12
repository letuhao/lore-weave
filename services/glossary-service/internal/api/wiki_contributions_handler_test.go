package api

import "testing"

func TestWikiContributionVisible(t *testing.T) {
	cases := []struct {
		name   string
		isSelf bool
		status string
		vis    string
		want   bool
	}{
		{"self sees own draft in private book", true, "draft", "", true},
		{"self sees own published in private book", true, "published", "private", true},
		{"other sees published in public-wiki book", false, "published", "public", true},
		{"anonymous sees published in public-wiki book", false, "published", "public", true},
		{"other does NOT see published in private-wiki book", false, "published", "private", false},
		{"other does NOT see draft even if wiki public", false, "draft", "public", false},
		{"other does NOT see published when visibility unknown", false, "published", "", false},
	}
	for _, c := range cases {
		if got := wikiContributionVisible(c.isSelf, c.status, c.vis); got != c.want {
			t.Errorf("%s: wikiContributionVisible(%v,%q,%q)=%v want %v",
				c.name, c.isSelf, c.status, c.vis, got, c.want)
		}
	}
}

package api

import "testing"

func TestStructureActivityCopy(t *testing.T) {
	tests := []struct {
		name, action, previous, title, wantTitle, wantBody string
	}{
		{"rename", string(structureActivityRenamed), "Глава 1", "Пролог", "Chapter renamed", `Chapter "Глава 1" renamed to "Пролог"`},
		{"rename from empty", string(structureActivityRenamed), "", "Пролог", "Chapter renamed", `Chapter renamed to "Пролог"`},
		{"trash", string(structureActivityTrashed), "", "Глава 1", "Chapter moved to trash", `Chapter "Глава 1" moved to trash`},
		{"restore", string(structureActivityRestored), "", "Глава 1", "Chapter restored", `Chapter "Глава 1" restored`},
		{"delete", string(structureActivityDeleted), "", "Глава 1", "Chapter deleted", `Chapter "Глава 1" permanently deleted`},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotTitle, gotBody := structureActivityCopy(structureActivityAction(tt.action), tt.previous, tt.title)
			if gotTitle != tt.wantTitle || gotBody != tt.wantBody {
				t.Fatalf("copy = (%q, %q), want (%q, %q)", gotTitle, gotBody, tt.wantTitle, tt.wantBody)
			}
		})
	}
}

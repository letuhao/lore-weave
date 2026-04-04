package domain

// GenreGroup represents a user-defined genre for a book's glossary.
type GenreGroup struct {
	ID          string `json:"id"`
	BookID      string `json:"book_id"`
	Name        string `json:"name"`
	Color       string `json:"color"`
	Description string `json:"description"`
	SortOrder   int    `json:"sort_order"`
	CreatedAt   string `json:"created_at"`
}

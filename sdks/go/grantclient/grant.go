package grantclient

// GrantLevel is the ordered permission a user holds on a book.
// E0 (collaboration-permissions): none < view < edit < manage < owner.
//
// The wire strings match book-service's GrantLevel.String() exactly so a
// value round-trips losslessly across the /access boundary.
type GrantLevel int

const (
	GrantNone   GrantLevel = 0
	GrantView   GrantLevel = 1
	GrantEdit   GrantLevel = 2
	GrantManage GrantLevel = 3
	GrantOwner  GrantLevel = 4
)

func (g GrantLevel) String() string {
	switch g {
	case GrantOwner:
		return "owner"
	case GrantManage:
		return "manage"
	case GrantEdit:
		return "edit"
	case GrantView:
		return "view"
	default:
		return "none"
	}
}

// AtLeast reports whether the held grant satisfies the required level. This is
// the single comparison that gates every permission decision (resolved >= need).
func (g GrantLevel) AtLeast(need GrantLevel) bool {
	return g >= need
}

// ParseGrantLevel maps a wire string back to a GrantLevel. Any unknown/empty
// value (including "owner" mis-sent as a role, or a future level this client
// doesn't recognize) maps to GrantNone — default-deny, never silently grant.
func ParseGrantLevel(s string) GrantLevel {
	switch s {
	case "owner":
		return GrantOwner
	case "manage":
		return GrantManage
	case "edit":
		return GrantEdit
	case "view":
		return GrantView
	default:
		return GrantNone
	}
}

/** Password rules shared with auth-service/internal/api/util.go. */
export const PASSWORD_MIN_LENGTH = 8;

export function passwordMeetsPolicy(password: string): boolean {
  // Go's len(string) counts UTF-8 bytes, so use TextEncoder rather than JS
  // UTF-16 code-unit length for parity with auth-service.
  if (new TextEncoder().encode(password).length < PASSWORD_MIN_LENGTH) return false;
  return /\p{L}/u.test(password) && /\p{Nd}/u.test(password);
}

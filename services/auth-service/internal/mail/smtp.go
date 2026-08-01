package mail

import (
	"crypto/rand"
	"crypto/tls"
	"encoding/hex"
	"fmt"
	"mime"
	"net/smtp"
	"strings"
)

// SendPlain sends a text/plain email. For Mailhog and similar dev relays, user/password may be empty.
func SendPlain(host string, port int, user, password, fromHeader, to, subject, body string) error {
	if host == "" {
		return fmt.Errorf("smtp: empty host")
	}
	if to == "" {
		return fmt.Errorf("smtp: empty recipient")
	}
	from := envelopeAddress(fromHeader)
	if from == "" {
		return fmt.Errorf("smtp: invalid From address")
	}
	addr := fmt.Sprintf("%s:%d", host, port)
	var auth smtp.Auth
	if user != "" {
		auth = smtp.PlainAuth("", user, password, host)
	}
	msg := buildRFC822(fromHeader, to, subject, body)
	return smtp.SendMail(addr, auth, from, []string{to}, []byte(msg))
}

// TLSMode selects how the connection to the relay is secured.
type TLSMode string

const (
	// TLSAuto = plain connect, then STARTTLS if the server advertises it. This is
	// what `smtp.SendMail` does and what port 587 relays expect (Gmail, SES,
	// Resend, Postmark). Also the mode that works with a local Mailhog, which
	// advertises nothing.
	TLSAuto TLSMode = "auto"
	// TLSImplicit = the connection is TLS from byte zero (port 465, "SMTPS").
	// `smtp.SendMail` CANNOT do this — it always dials plaintext first — so a
	// 465-only relay fails with a protocol error that reads like a network
	// problem. This mode is the reason the sender below is hand-rolled.
	TLSImplicit TLSMode = "implicit"
)

// Send delivers a multipart/alternative message (plain text + HTML).
//
// HTML-only mail scores worse with spam filters and is unreadable in text-only
// clients, so both parts always travel together; `multipart/alternative` lets
// the client pick. Ordering is mandated by RFC 2046: least-rich part FIRST, so
// a client that renders the last part it understands lands on the HTML.
func Send(host string, port int, user, password, fromHeader, to, subject, textBody, htmlBody string, mode TLSMode) error {
	if host == "" {
		return fmt.Errorf("smtp: empty host")
	}
	if to == "" {
		return fmt.Errorf("smtp: empty recipient")
	}
	from := envelopeAddress(fromHeader)
	if from == "" {
		return fmt.Errorf("smtp: invalid From address")
	}
	msg, err := buildMultipart(fromHeader, to, subject, textBody, htmlBody)
	if err != nil {
		return err
	}
	addr := fmt.Sprintf("%s:%d", host, port)

	var auth smtp.Auth
	if user != "" {
		auth = smtp.PlainAuth("", user, password, host)
	}

	if mode != TLSImplicit {
		// STARTTLS path — smtp.SendMail upgrades automatically when offered.
		return smtp.SendMail(addr, auth, from, []string{to}, []byte(msg))
	}

	// Implicit TLS (465): dial wrapped, then speak SMTP inside the tunnel.
	conn, err := tls.Dial("tcp", addr, &tls.Config{ServerName: host, MinVersion: tls.VersionTLS12})
	if err != nil {
		return fmt.Errorf("smtp: tls dial: %w", err)
	}
	c, err := smtp.NewClient(conn, host)
	if err != nil {
		_ = conn.Close()
		return fmt.Errorf("smtp: client: %w", err)
	}
	defer func() { _ = c.Quit() }()
	if auth != nil {
		if err := c.Auth(auth); err != nil {
			return fmt.Errorf("smtp: auth: %w", err)
		}
	}
	if err := c.Mail(from); err != nil {
		return fmt.Errorf("smtp: MAIL FROM: %w", err)
	}
	if err := c.Rcpt(to); err != nil {
		return fmt.Errorf("smtp: RCPT TO: %w", err)
	}
	wc, err := c.Data()
	if err != nil {
		return fmt.Errorf("smtp: DATA: %w", err)
	}
	if _, err := wc.Write([]byte(msg)); err != nil {
		_ = wc.Close()
		return fmt.Errorf("smtp: write: %w", err)
	}
	return wc.Close()
}

// randomBoundary returns a MIME boundary that cannot collide with body content.
func randomBoundary() (string, error) {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return "lw_" + hex.EncodeToString(b), nil
}

func buildMultipart(from, to, subject, textBody, htmlBody string) (string, error) {
	boundary, err := randomBoundary()
	if err != nil {
		return "", err
	}
	subject = strings.ReplaceAll(subject, "\r", "")
	subject = strings.ReplaceAll(subject, "\n", " ")

	var b strings.Builder
	fmt.Fprintf(&b, "From: %s\r\n", from)
	fmt.Fprintf(&b, "To: %s\r\n", to)
	// RFC 2047 encoding, so a non-ASCII subject ("Xác minh…") is not mangled or
	// silently dropped by the relay. A raw 8-bit Subject header is invalid.
	fmt.Fprintf(&b, "Subject: %s\r\n", mime.QEncoding.Encode("UTF-8", subject))
	b.WriteString("MIME-Version: 1.0\r\n")
	// Transactional mail must not land in a promotions bundle or trip
	// list-unsubscribe expectations; Auto-Submitted also stops well-behaved
	// autoresponders from replying to a no-reply address.
	b.WriteString("Auto-Submitted: auto-generated\r\n")
	fmt.Fprintf(&b, "Content-Type: multipart/alternative; boundary=\"%s\"\r\n", boundary)
	b.WriteString("\r\n")

	// Least-rich part first (RFC 2046 §5.1.4).
	fmt.Fprintf(&b, "--%s\r\n", boundary)
	b.WriteString("Content-Type: text/plain; charset=UTF-8\r\n")
	b.WriteString("Content-Transfer-Encoding: 8bit\r\n\r\n")
	b.WriteString(normalizeCRLF(textBody))
	b.WriteString("\r\n")

	fmt.Fprintf(&b, "--%s\r\n", boundary)
	b.WriteString("Content-Type: text/html; charset=UTF-8\r\n")
	b.WriteString("Content-Transfer-Encoding: 8bit\r\n\r\n")
	b.WriteString(normalizeCRLF(htmlBody))
	b.WriteString("\r\n")

	fmt.Fprintf(&b, "--%s--\r\n", boundary)
	return b.String(), nil
}

// normalizeCRLF makes line endings SMTP-legal without doubling existing CRLFs.
func normalizeCRLF(s string) string {
	s = strings.ReplaceAll(s, "\r\n", "\n")
	return strings.ReplaceAll(s, "\n", "\r\n")
}

func envelopeAddress(fromHeader string) string {
	fromHeader = strings.TrimSpace(fromHeader)
	start := strings.LastIndex(fromHeader, "<")
	end := strings.LastIndex(fromHeader, ">")
	if start >= 0 && end > start {
		return strings.TrimSpace(fromHeader[start+1 : end])
	}
	return fromHeader
}

func buildRFC822(from, to, subject, body string) string {
	subject = strings.ReplaceAll(subject, "\r", "")
	subject = strings.ReplaceAll(subject, "\n", " ")
	b := strings.Builder{}
	fmt.Fprintf(&b, "From: %s\r\n", from)
	fmt.Fprintf(&b, "To: %s\r\n", to)
	fmt.Fprintf(&b, "Subject: %s\r\n", subject)
	b.WriteString("MIME-Version: 1.0\r\n")
	b.WriteString("Content-Type: text/plain; charset=UTF-8\r\n")
	b.WriteString("\r\n")
	b.WriteString(strings.ReplaceAll(body, "\n", "\r\n"))
	if !strings.HasSuffix(body, "\n") {
		b.WriteString("\r\n")
	}
	return b.String()
}

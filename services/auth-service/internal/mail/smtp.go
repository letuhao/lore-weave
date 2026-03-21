package mail

import (
	"fmt"
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

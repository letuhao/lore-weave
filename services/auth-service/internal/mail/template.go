package mail

import (
	"bytes"
	"fmt"
	"html/template"
	"strings"
)

// HTML mail templates.
//
// Email HTML is not web HTML, and the constraints below are why this looks like
// 2005 markup on purpose:
//
//   - TABLES, not flex/grid. Outlook renders through Word's engine; flexbox and
//     grid simply do not exist there.
//   - INLINE styles. Gmail strips <style> blocks in several clients, so anything
//     that must survive is on the element.
//   - NO external assets. Remote CSS never loads, and remote images are blocked
//     by default — a logo <img> shows as a broken box for most recipients. The
//     wordmark here is text.
//   - A PREHEADER. The hidden first line becomes the inbox preview snippet; with
//     no preheader clients scrape the first visible text, which is usually the
//     wordmark repeated.
//   - Both parts always. `text/plain` is not a courtesy — spam filters score
//     HTML-only mail worse, and it is the accessible fallback.
//
// The dark-mode block is best-effort: Apple Mail and iOS honour it, Gmail
// largely does not. The light palette must therefore stand on its own.

const layoutHTML = `<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light dark" />
<title>{{.Subject}}</title>
<style>
  @media (prefers-color-scheme: dark) {
    .lw-body { background: #0f1115 !important; }
    .lw-card { background: #171a21 !important; border-color: #2a2f3a !important; }
    .lw-text { color: #d8dbe2 !important; }
    .lw-muted { color: #8b93a3 !important; }
    .lw-token { background: #0f1115 !important; color: #e6e9ef !important; border-color: #2a2f3a !important; }
  }
  @media only screen and (max-width: 620px) {
    .lw-card { width: 100% !important; }
    .lw-pad { padding: 24px !important; }
  }
</style>
</head>
<body class="lw-body" style="margin:0;padding:0;background:#eef0f4;">
<!-- preheader: inbox preview text, hidden in the body -->
<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;">{{.Preheader}}</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="lw-body" style="background:#eef0f4;">
  <tr>
    <td align="center" style="padding:32px 12px;">

      <table role="presentation" class="lw-card" width="600" cellpadding="0" cellspacing="0" border="0"
             style="width:600px;max-width:600px;background:#ffffff;border:1px solid #dfe3ea;border-radius:12px;overflow:hidden;">

        <tr>
          <td style="background:#1b1f27;padding:22px 32px;">
            <span style="font-family:Georgia,'Times New Roman',serif;font-size:20px;font-weight:700;color:#ffffff;letter-spacing:.3px;">LoreWeave</span>
            <span style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#8b93a3;padding-left:10px;">{{.Kicker}}</span>
          </td>
        </tr>

        <tr>
          <td class="lw-pad" style="padding:34px 32px 8px 32px;">
            <h1 class="lw-text" style="margin:0 0 12px 0;font-family:Georgia,'Times New Roman',serif;font-size:23px;line-height:1.3;color:#1b1f27;font-weight:700;">{{.Heading}}</h1>
            <p class="lw-text" style="margin:0 0 22px 0;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#3c424e;">{{.Intro}}</p>

            <!-- CTA: bulletproof-ish button (padding on the <a>, not a bg image) -->
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 22px 0;">
              <tr>
                <td align="center" bgcolor="#4f46e5" style="border-radius:8px;">
                  <a href="{{.ActionURL}}" target="_blank"
                     style="display:inline-block;padding:13px 30px;font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:8px;">{{.ActionLabel}}</a>
                </td>
              </tr>
            </table>

            <p class="lw-muted" style="margin:0 0 8px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#6b7280;">{{.TokenLabel}}</p>
            <div class="lw-token" style="font-family:Consolas,Monaco,'Courier New',monospace;font-size:14px;letter-spacing:.5px;color:#1b1f27;background:#f5f6f9;border:1px solid #dfe3ea;border-radius:8px;padding:14px 16px;word-break:break-all;margin:0 0 22px 0;">{{.Token}}</div>

            <p class="lw-muted" style="margin:0 0 6px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.6;color:#6b7280;">{{.ExpiryNote}}</p>
            <p class="lw-muted" style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.6;color:#6b7280;">{{.IgnoreNote}}</p>
          </td>
        </tr>

        <tr>
          <td class="lw-pad" style="padding:24px 32px 30px 32px;">
            <div style="height:1px;background:#e6e9ef;line-height:1px;font-size:0;">&nbsp;</div>
            <p class="lw-muted" style="margin:16px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.6;color:#9aa1ae;">
              If the button doesn't work, copy this link into your browser:<br />
              <span style="color:#6b7280;word-break:break-all;">{{.ActionURL}}</span>
            </p>
          </td>
        </tr>

      </table>

      <p style="margin:18px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9aa1ae;">
        LoreWeave · this message was sent automatically, please don't reply
      </p>

    </td>
  </tr>
</table>
</body>
</html>`

var layoutTmpl = template.Must(template.New("mail").Parse(layoutHTML))

// Content is the per-message copy the layout renders.
type Content struct {
	Subject     string
	Preheader   string
	Kicker      string
	Heading     string
	Intro       string
	ActionURL   string
	ActionLabel string
	TokenLabel  string
	Token       string
	ExpiryNote  string
	IgnoreNote  string
}

// RenderHTML produces the HTML part. `html/template` escapes every field, so a
// hostile display name or a token containing markup cannot inject into the mail.
func (c Content) RenderHTML() (string, error) {
	var buf bytes.Buffer
	if err := layoutTmpl.Execute(&buf, c); err != nil {
		return "", err
	}
	return buf.String(), nil
}

// RenderText produces the plain-text part.
//
// This is NOT a stripped-tags version of the HTML: a text/plain part built by
// regexing markup reads like debris. It is written as its own message so the
// fallback is worth receiving.
func (c Content) RenderText() string {
	var b strings.Builder
	fmt.Fprintf(&b, "%s\n\n", c.Heading)
	fmt.Fprintf(&b, "%s\n\n", c.Intro)
	fmt.Fprintf(&b, "%s\n\n    %s\n\n", c.TokenLabel, c.Token)
	if c.ActionURL != "" {
		fmt.Fprintf(&b, "%s:\n%s\n\n", c.ActionLabel, c.ActionURL)
	}
	fmt.Fprintf(&b, "%s\n%s\n\n", c.ExpiryNote, c.IgnoreNote)
	b.WriteString("--\nLoreWeave · this message was sent automatically, please don't reply\n")
	return b.String()
}

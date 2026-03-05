"""Send the deals PDF report via email."""
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

try:
    import keyring as _keyring
except ImportError:
    _keyring = None

_KEYRING_SERVICE = "food-chaser"
_KEYRING_USER    = "smtp"


_RECIPIENTS = "jgawry@gmail.com, kgawry@gmail.com"

_PLAIN = (
    "Hello, this is your friendly neighborhood deals reporter.\n\n"
    "With great discounts come great opportunities!\n\n"
    "Please find attached the current deals report.\n\n"
    "Happy saving,\nFood Chaser"
)


def _html_body(date_str: str, category: str | None) -> str:
    scope = f"category: <strong>{category}</strong>" if category else "all categories"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:system-ui,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:10px;overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,.08);">

        <!-- Header -->
        <tr>
          <td style="background:#e63946;padding:28px 36px;">
            <h1 style="margin:0;color:#ffffff;font-size:26px;letter-spacing:-.5px;">
              🛒 Food Chaser
            </h1>
            <p style="margin:6px 0 0;color:rgba(255,255,255,.85);font-size:13px;">
              Deals Report &middot; {date_str}
            </p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:32px 36px;">
            <p style="margin:0 0 16px;font-size:16px;color:#222;">
              Hello there! 👋
            </p>
            <p style="margin:0 0 16px;font-size:15px;color:#444;line-height:1.6;">
              This is your friendly neighborhood deals reporter.
              With great discounts come great opportunities!
            </p>
            <p style="margin:0 0 24px;font-size:15px;color:#444;line-height:1.6;">
              Please find attached the current deals report
              ({scope}).
            </p>

            <!-- Highlight box -->
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#fff5f5;border-left:4px solid #e63946;
                           border-radius:4px;padding:14px 18px;">
                  <p style="margin:0;font-size:14px;color:#e63946;font-weight:700;">
                    Tip of the day
                  </p>
                  <p style="margin:6px 0 0;font-size:14px;color:#555;line-height:1.5;">
                    Check the <strong>Kupon</strong> category for app-exclusive
                    1+1 and 2+2 gratis deals — activate them in the Lidl Plus app
                    before you shop!
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f9f9f9;padding:18px 36px;border-top:1px solid #eeeeee;">
            <p style="margin:0;font-size:12px;color:#999;line-height:1.6;">
              Happy saving! &mdash; <strong style="color:#e63946;">Food Chaser</strong><br>
              This is an automated report. Do not reply to this email.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_deals_email(pdf_bytes: bytes, category: str = None) -> None:
    """
    Send *pdf_bytes* as an email attachment.

    Required env vars:
      SMTP_HOST  – default smtp.gmail.com
      SMTP_PORT  – default 465  (SSL)
      SMTP_USER  – sender address / Gmail account
      SMTP_PASS  – Gmail App Password (not your regular password)
    """
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")

    # Prefer credential vault over .env
    if not password and _keyring is not None:
        password = _keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER) or ""

    if not user or not password:
        raise RuntimeError(
            "SMTP credentials not found. Run `python store_credentials.py` "
            "or set SMTP_USER / SMTP_PASS in .env"
        )

    date_str = datetime.now().strftime("%d %b %Y")
    subject = f"Food Chaser Report: {date_str}"
    filename = f"deals-{category or 'all'}.pdf"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = _RECIPIENTS
    # Plain text fallback
    msg.set_content(_PLAIN)
    # HTML alternative
    msg.add_alternative(_html_body(date_str, category), subtype="html")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)

    with smtplib.SMTP_SSL(host, port) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)

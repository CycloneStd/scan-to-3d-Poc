import json
import smtplib
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import get_settings


def send_security_email(to_email: str, subject: str, body: str, html_body: str | None = None) -> None:
    settings = get_settings()
    from_email = settings.email_from_email or settings.smtp_from_email
    from_name = settings.email_from_name or settings.smtp_from_name
    if not from_email:
        raise RuntimeError("WEBXR_EMAIL_FROM_EMAIL is not configured")

    if settings.email_provider == "resend":
        if not settings.resend_api_key:
            raise RuntimeError("WEBXR_RESEND_API_KEY is not configured")
        payload = {
            "from": f"{from_name} <{from_email}>",
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        if html_body:
            payload["html"] = html_body
        request = Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                response.read()
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Resend rejected the email ({error.code}): {detail}") from error
        except URLError as error:
            raise RuntimeError(f"Could not reach the Resend API: {error.reason}") from error
        return

    if not settings.smtp_host:
        raise RuntimeError("WEBXR_SMTP_HOST is not configured")

    message = EmailMessage()
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.ehlo()
        if settings.smtp_starttls:
            smtp.starttls()
            smtp.ehlo()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value() if settings.smtp_password else "")
        smtp.send_message(message)

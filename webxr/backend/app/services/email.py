import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import get_settings


def send_security_email(to_email: str, subject: str, body: str, html_body: str | None = None) -> str | None:
    settings = get_settings()
    from_email = settings.email_from_email
    from_name = settings.email_from_name or "Cyclone Scan"
    if not from_email:
        raise RuntimeError("WEBXR_EMAIL_FROM_EMAIL is not configured")

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
            "User-Agent": "scan3d-backend/1.0 (Resend API client)",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
            return result.get("id")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend rejected the email ({error.code}): {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach the Resend API: {error.reason}") from error

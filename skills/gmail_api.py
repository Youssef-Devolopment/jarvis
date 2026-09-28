"""Gmail via Google API (OAuth)."""
from __future__ import annotations
import base64
import os
from email.mime.text import MIMEText
from pathlib import Path
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_CREDS = Path(__file__).resolve().parent.parent / "credentials.json"
_TOKEN = Path(__file__).resolve().parent.parent / "token.json"


def _service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        return None
    scopes = ["https://www.googleapis.com/auth/gmail.modify"]
    creds = None
    if _TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _CREDS.exists():
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(_CREDS), scopes)
            creds = flow.run_local_server(port=0)
        _TOKEN.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


@register("gmail_unread", [
    r"^(?:check|read|what(?:'s| is)\s+in)\s+(?:my\s+)?(?:gmail|inbox|emails?)[\?\.\!]?$",
    r"^unread\s+emails[\?\.\!]?$",
], "Check unread emails")
def s_gmail_unread(text, m):
    svc = _service()
    if not svc:
        return "Gmail not configured. Add credentials.json to project root."
    try:
        results = svc.users().messages().list(
            userId="me", q="is:unread", maxResults=5).execute()
        messages = results.get("messages", [])
        if not messages:
            return "No unread emails."
        lines = [f"You have {len(messages)} unread emails:"]
        for msg in messages[:3]:
            detail = svc.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From"]).execute()
            headers = detail.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "")
            lines.append(f"From {sender[:40]}: {subject[:60]}")
        return " ".join(lines)
    except Exception as exc:
        return f"Gmail failed: {str(exc)[:80]}"


@register("gmail_send", [
    r"^(?:send|compose)\s+(?:an?\s+)?email\s+(?:to\s+)?(?P<to>\S+@\S+)\s+"
    r"(?:saying|about|:)\s+(?P<subj>.+?)[\?\.\!]?$",
], "Send email")
def s_gmail_send(text, m):
    svc = _service()
    if not svc:
        return "Gmail not configured."
    try:
        to = m.group("to")
        subject = m.group("subj")[:60]
        message = MIMEText(subject)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email sent to {to}."
    except Exception as exc:
        return f"Email failed: {str(exc)[:80]}"

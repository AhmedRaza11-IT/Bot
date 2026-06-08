"""
email_reader.py
═══════════════════════════════════════════════════════════════════
Auto Email Verification — Gmail IMAP OTP Reader
═══════════════════════════════════════════════════════════════════
• Connects to Gmail via IMAP SSL (port 993)
• Authenticates with Gmail App Password (no OAuth required)
• Polls inbox for BLS verification emails
• Extracts OTP codes (4–8 digits) via multi-pattern regex
• Also extracts verification links for click-through auth
• Returns OTP/link within a configurable timeout
• Falls back to GUI manual-entry dialog if polling times out
"""

import email
import imaplib
import re
import time
import tkinter as tk
from tkinter import simpledialog
from email.header import decode_header
from typing import Optional

# ── Gmail IMAP Configuration ──────────────────────────────────────────────
GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993

# ── OTP extraction patterns (ordered by specificity) ──────────────────────
_OTP_PATTERNS = [
    r'OTP[\s:–-]+(\d{4,8})',
    r'verification[\s\w]*code[\s:–-]+(\d{4,8})',
    r'Your code[\s:–-]+(\d{4,8})',
    r'PIN[\s:–-]+(\d{4,8})',
    r'passcode[\s:–-]+(\d{4,8})',
    r'\b(\d{6})\b',      # most OTPs are 6-digit — match standalone
    r'\b(\d{4})\b',      # 4-digit fallback
    r'\b(\d{8})\b',      # 8-digit fallback
]

# ── Verification link patterns ────────────────────────────────────────────
_LINK_PATTERNS = [
    r'https?://[^\s"<>]+verify[^\s"<>]*',
    r'https?://[^\s"<>]+confirm[^\s"<>]*',
    r'https?://[^\s"<>]+activate[^\s"<>]*',
    r'https?://[^\s"<>]+validate[^\s"<>]*',
    r'href=["\']?(https?://[^\s"\'<>]+token[^\s"\'<>]*)["\']?',
]

# ── BLS-specific email sender filters ────────────────────────────────────
BLS_SENDER_HINTS = [
    "italyvisa",
    "bls",
    "noreply",
    "no-reply",
    "donotreply",
]


def _decode_subject(msg) -> str:
    """Safely decode an email subject (handles encoded headers)."""
    raw = decode_header(msg.get("Subject", ""))[0]
    data, charset = raw
    if isinstance(data, bytes):
        return data.decode(charset or "utf-8", errors="ignore")
    return str(data)


def _get_body(msg) -> str:
    """Extract the plain-text + HTML body from a Message object."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode("utf-8", errors="ignore") + "\n"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="ignore")
    return body


def _extract_otp(body: str) -> Optional[str]:
    """Try each OTP pattern in order, return first match or None."""
    for pattern in _OTP_PATTERNS:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_link(body: str) -> Optional[str]:
    """Try each link pattern, return first verification URL or None."""
    for pattern in _LINK_PATTERNS:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            return m.group(1) if m.lastindex else m.group(0)
    return None


def _is_bls_email(sender: str, subject: str) -> bool:
    """Heuristic: is this email likely from BLS Italy?"""
    text = (sender + " " + subject).lower()
    return any(hint in text for hint in BLS_SENDER_HINTS)


class EmailReader:
    """
    Reads Gmail inbox for BLS Italy verification emails and
    extracts OTP codes or verification links.

    Usage:
        reader = EmailReader("your@gmail.com", "app_password_here")
        result = reader.wait_for_otp(timeout=120)
        if result:
            print("OTP:", result)
    """

    def __init__(self, gmail_address: str, app_password: str, log_fn=None):
        self.address     = gmail_address.strip()
        self.app_password = app_password.strip().replace(" ", "")
        self._log        = log_fn or print

    def _connect(self) -> imaplib.IMAP4_SSL:
        """Connect and authenticate to Gmail IMAP."""
        mail = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
        mail.login(self.address, self.app_password)
        return mail

    def wait_for_otp(
        self,
        timeout: int = 120,
        poll_interval: int = 5,
        sender_filter: Optional[str] = None,
    ) -> Optional[str]:
        """
        Poll Gmail inbox until an OTP email arrives or timeout is reached.

        Args:
            timeout       : Max seconds to wait (default 120)
            poll_interval : Seconds between inbox checks (default 5)
            sender_filter : Optional exact sender email to filter by

        Returns:
            OTP code string, or None on timeout
        """
        self._log(f"📧 Waiting for OTP email (timeout: {timeout}s)...")

        try:
            mail = self._connect()
        except Exception as e:
            self._log(f"❌ Gmail IMAP connection failed: {e}")
            return self._manual_fallback("IMAP connection failed. Enter OTP manually:")

        mail.select("inbox")
        start = time.time()

        while time.time() - start < timeout:
            try:
                # Search for UNSEEN emails
                criteria = "(UNSEEN)"
                if sender_filter:
                    criteria = f'(UNSEEN FROM "{sender_filter}")'

                _, msg_ids = mail.search(None, criteria)
                ids = msg_ids[0].split()

                for mid in reversed(ids):   # newest first
                    _, data = mail.fetch(mid, "(RFC822)")
                    for part in data:
                        if not isinstance(part, tuple):
                            continue
                        msg     = email.message_from_bytes(part[1])
                        sender  = msg.get("From", "")
                        subject = _decode_subject(msg)

                        # Skip if clearly not a BLS email
                        if not _is_bls_email(sender, subject):
                            continue

                        body = _get_body(msg)
                        otp  = _extract_otp(body)
                        if otp:
                            self._log(f"✅ OTP found: {otp}  (Subject: {subject})")
                            mail.store(mid, "+FLAGS", "\\Seen")
                            mail.logout()
                            return otp

                        # Try verification link as fallback
                        link = _extract_link(body)
                        if link:
                            self._log(f"🔗 Verification link found: {link[:80]}...")
                            mail.store(mid, "+FLAGS", "\\Seen")
                            mail.logout()
                            return link   # caller handles link vs OTP

            except Exception as e:
                self._log(f"⚠️ Email poll error: {e}")

            elapsed = int(time.time() - start)
            self._log(f"📧 No OTP yet... waiting ({elapsed}/{timeout}s)")
            time.sleep(poll_interval)

        try:
            mail.logout()
        except Exception:
            pass

        self._log("⏰ OTP polling timed out.")
        return self._manual_fallback("OTP email not received. Enter OTP manually:")

    def _manual_fallback(self, prompt: str) -> Optional[str]:
        """
        Show a Tkinter input dialog for manual OTP entry when automation fails.
        Must be called from the main thread or via after() for safety.
        """
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            result = simpledialog.askstring(
                "Manual OTP Required",
                prompt,
                parent=root
            )
            root.destroy()
            return result.strip() if result else None
        except Exception:
            # Console fallback if Tkinter isn't available in context
            return input(f"\n[MANUAL] {prompt} ").strip() or None

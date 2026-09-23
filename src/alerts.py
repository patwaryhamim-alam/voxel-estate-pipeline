"""
EMAIL ALERTS
============
Sends email notifications for pipeline errors.

RECIPIENT: Admin only (EMAIL_ADMIN from .env).
Client never receives error alerts.

FIX 6 (Privacy hygiene):
    - Traceback is TRUNCATED in emails (first 3 + last 2 frames)
    - Prevents leaking full library internals to email
    - No secrets, no .env values in body

USAGE:
    from alerts import send_error_alert
    send_error_alert(
        subject="Pipeline Failed",
        body="Gemini rate limit hit",
        context="client_001",
        exc_info=sys.exc_info(),
    )
"""

import os
import smtplib
import traceback
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

load_dotenv()


# ============================================================
# CONFIG
# ============================================================
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL
MAX_TRACEBACK_FRAMES = 5


def _get_email_config():
    """
    Read email credentials from environment.
    Admin only — no client emails for errors.
    """
    return {
        "sender": os.getenv("EMAIL_SENDER"),
        "password": os.getenv("EMAIL_PASSWORD"),
        "admin": (os.getenv("EMAIL_ADMIN") or os.getenv("EMAIL_RECIPIENT") or "").strip(),
    }


# ============================================================
# TRACEBACK TRIMMER (Fix 6)
# ============================================================
def _trimmed_traceback(exc_info) -> str:
    """
    Return a shortened traceback string.

    Keeps: exception type + message, first 3 frames, last 2 frames.
    Removes: intermediate frames (usually library internals).
    """
    if not exc_info:
        return ""

    exc_type, exc_value, exc_tb = exc_info
    frames = traceback.extract_tb(exc_tb)
    total = len(frames)

    if total <= MAX_TRACEBACK_FRAMES:
        # Short enough — keep full
        return "".join(traceback.format_exception(*exc_info))

    head_n = 3
    tail_n = MAX_TRACEBACK_FRAMES - head_n
    kept = frames[:head_n] + frames[-tail_n:]

    lines = [
        f"Traceback (trimmed — {total} total frames, showing first {head_n} + last {tail_n}):",
        "",
    ]
    lines.append("".join(traceback.format_list(kept)))
    lines.append(f"[... {total - MAX_TRACEBACK_FRAMES} intermediate frames omitted ...]")
    lines.append("")
    lines.append("".join(traceback.format_exception_only(exc_type, exc_value)))

    return "\n".join(lines)


# ============================================================
# PUBLIC: send_error_alert()
# ============================================================
def send_error_alert(subject, body, context="", exc_info=None):
    """
    Send an error alert email to admin only.

    Args:
        subject:  Email subject
        body:     Email body (what went wrong)
        context:  Which client/pipeline
        exc_info: Optional — sys.exc_info() for trimmed traceback

    Returns:
        (success: bool, message: str)
    """
    config = _get_email_config()

    if not all([config["sender"], config["password"], config["admin"]]):
        return False, "Email config incomplete (.env missing EMAIL_* variables)"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    body_parts = [
        "PIPELINE ERROR ALERT",
        "=" * 50,
        "",
        f"Time:     {timestamp}",
        f"Context:  {context or 'N/A'}",
        "",
        "Problem:",
        "-" * 50,
        body,
    ]

    if exc_info:
        tb = _trimmed_traceback(exc_info)
        if tb:
            body_parts.extend([
                "",
                "Traceback (trimmed):",
                "-" * 50,
                tb,
            ])

    full_body = "\n".join(body_parts)

    msg = MIMEMultipart()
    msg["From"] = config["sender"]
    msg["To"] = config["admin"]
    msg["Subject"] = f"[Voxel Estate] {subject}"
    msg.attach(MIMEText(full_body, "plain"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(config["sender"], config["password"])
            smtp.send_message(msg)
        return True, f"Alert sent to {config['admin']}"
    except Exception as e:
        return False, f"Failed to send alert: {str(e)[:200]}"


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ALERTS TEST — Fix 6 (Trimmed Traceback)")
    print("=" * 60)

    # Test 1: Simple alert (no traceback)
    print("\n[1] Simple alert...")
    ok, msg = send_error_alert(
        subject="Test Error Alert",
        body="This is a test error message.",
        context="test_run",
    )
    print(f"   {'OK' if ok else 'FAIL'}: {msg}")

    # Test 2: Deep exception (check trimming)
    print("\n[2] Deep exception test (check trimmed traceback)...")
    try:
        def level_5(): return 1 / 0
        def level_4(): return level_5()
        def level_3(): return level_4()
        def level_2(): return level_3()
        def level_1(): return level_2()
        level_1()
    except Exception:
        import sys
        tb = _trimmed_traceback(sys.exc_info())
        print("   Trimmed traceback:")
        for line in tb.split("\n")[:15]:
            print(f"      {line}")

    print("\n✅ Alerts test complete")
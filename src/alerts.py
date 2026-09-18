"""
EMAIL ALERTS
============
Sends email notifications for pipeline errors.

USAGE:
    from alerts import send_error_alert
    send_error_alert(
        subject="Pipeline Failed",
        body="Gemini rate limit hit",
        context="client_001",
    )

CONFIGURATION (.env):
    EMAIL_SENDER=your@gmail.com
    EMAIL_PASSWORD=16char_app_password
    EMAIL_RECIPIENT=where_to_send@gmail.com
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


def _get_email_config():
    """Read email credentials from environment."""
    return {
        "sender": os.getenv("EMAIL_SENDER"),
        "password": os.getenv("EMAIL_PASSWORD"),
        "recipient": os.getenv("EMAIL_RECIPIENT"),
    }


# ============================================================
# PUBLIC: send_error_alert()
# ============================================================
def send_error_alert(subject, body, context="", exc_info=None):
    """
    Send an error alert email.

    Args:
        subject:  Email subject (short, e.g., "Pipeline Failed")
        body:     Email body (what went wrong)
        context:  Which client/pipeline (e.g., "client_001")
        exc_info: Optional — pass sys.exc_info() for full traceback

    Returns:
        (success: bool, message: str)
    """
    config = _get_email_config()

    # Verify config
    if not all([config["sender"], config["password"], config["recipient"]]):
        return False, "Email config incomplete (.env missing EMAIL_* variables)"

    # Build email body
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    body_parts = [
        "🚨 PIPELINE ERROR ALERT",
        "=" * 50,
        "",
        f"Time:     {timestamp}",
        f"Context:  {context or 'N/A'}",
        "",
        "Problem:",
        "-" * 50,
        body,
    ]

    # Add traceback if provided
    if exc_info:
        tb = "".join(traceback.format_exception(*exc_info))
        body_parts.extend([
            "",
            "Traceback:",
            "-" * 50,
            tb,
        ])

    full_body = "\n".join(body_parts)

    # Create message
    msg = MIMEMultipart()
    msg["From"] = config["sender"]
    msg["To"] = config["recipient"]
    msg["Subject"] = f"[Voxel Estate] {subject}"
    msg.attach(MIMEText(full_body, "plain"))

    # Send
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(config["sender"], config["password"])
            smtp.send_message(msg)
        return True, f"Alert sent to {config['recipient']}"
    except Exception as e:
        return False, f"Failed to send alert: {str(e)[:200]}"


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("Testing error alert...")
    success, message = send_error_alert(
        subject="Test Error Alert",
        body="This is a test error message from the alerts module.",
        context="test_run",
    )
    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
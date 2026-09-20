"""
RUN SUMMARY REPORTER
====================
Tracks pipeline stats during a run and sends summary email + log.

USAGE:
    from run_summary import RunSummary, send_summary_email
    
    summary = RunSummary(client_id="client_001")
    summary.set_input_rows(10)
    summary.set_dropped_rows(2)
    summary.set_ai_stats(requests=1, cached=0, classified=10, fallback=0)
    summary.set_sheet_stats(pushed=8, skipped=2)
    summary.finish()
    
    send_summary_email(summary)
"""

import os
import smtplib
from datetime import datetime
from pathlib import Path
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

load_dotenv()

try:
    from logger import get_logger
    log = get_logger(__name__)
except ImportError:
    import logging
    log = logging.getLogger(__name__)


# ============================================================
# RUN SUMMARY CLASS
# ============================================================
class RunSummary:
    """Tracks stats for one pipeline run."""

    def __init__(self, client_id: str = "unknown", run_type: str = "manual"):
        self.client_id = client_id
        self.run_type = run_type
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None

        # Rows
        self.input_rows = 0
        self.dropped_rows = 0
        self.valid_rows = 0

        # AI
        self.ai_requests = 0
        self.ai_cached = 0
        self.ai_classified = 0
        self.ai_fallback = 0

        # Sheet
        self.sheet_pushed = 0
        self.sheet_skipped = 0

        # Status
        self.status = "unknown"  # "success" | "error" | "partial"
        self.error_message = ""

    # --------------------------------------------------------
    # Setters
    # --------------------------------------------------------
    def set_input_rows(self, n: int):
        self.input_rows = n

    def set_dropped_rows(self, n: int):
        self.dropped_rows = n
        self.valid_rows = self.input_rows - self.dropped_rows

    def set_ai_stats(self, requests: int = 0, cached: int = 0,
                     classified: int = 0, fallback: int = 0):
        self.ai_requests = requests
        self.ai_cached = cached
        self.ai_classified = classified
        self.ai_fallback = fallback

    def set_sheet_stats(self, pushed: int = 0, skipped: int = 0):
        self.sheet_pushed = pushed
        self.sheet_skipped = skipped

    def set_error(self, message: str):
        self.status = "error"
        self.error_message = message

    def set_success(self):
        self.status = "success"

    def set_partial(self):
        self.status = "partial"

    def finish(self):
        self.end_time = datetime.now()

    # --------------------------------------------------------
    # Properties
    # --------------------------------------------------------
    @property
    def duration_seconds(self) -> float:
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    # --------------------------------------------------------
    # Formatting
    # --------------------------------------------------------
    def to_text(self) -> str:
        """Human-readable summary."""
        status_icon = {
            "success": "✅",
            "error": "❌",
            "partial": "⚠️",
            "unknown": "❓",
        }.get(self.status, "❓")

        lines = [
            "=" * 60,
            f"RUN SUMMARY — {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            "",
            f"Client:       {self.client_id}",
            f"Run Type:     {self.run_type}",
            f"Duration:     {self.duration_seconds:.1f} seconds",
            "",
            "ROWS:",
            f"  Input:        {self.input_rows}",
            f"  Dropped:      {self.dropped_rows}",
            f"  Valid:        {self.valid_rows}",
            "",
            "AI:",
            f"  Requests:     {self.ai_requests}",
            f"  Cached:       {self.ai_cached}",
            f"  Classified:   {self.ai_classified}",
            f"  Fallback:     {self.ai_fallback}",
            "",
            "SHEET:",
            f"  Pushed:       {self.sheet_pushed}",
            f"  Skipped:      {self.sheet_skipped} (duplicates)",
            "",
            f"STATUS: {status_icon} {self.status.upper()}",
        ]

        if self.error_message:
            lines.append("")
            lines.append("ERROR:")
            lines.append(f"  {self.error_message[:500]}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_html(self) -> str:
        """HTML version for email."""
        status_color = {
            "success": "#10B981",
            "error": "#EF4444",
            "partial": "#F59E0B",
            "unknown": "#6B7280",
        }.get(self.status, "#6B7280")

        status_icon = {
            "success": "✅",
            "error": "❌",
            "partial": "⚠️",
            "unknown": "❓",
        }.get(self.status, "❓")

        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                     background: #0A0A0A; color: #E5E7EB; padding: 20px; margin: 0;">
            <div style="max-width: 600px; margin: 0 auto; background: #111827;
                        border-radius: 12px; overflow: hidden; border: 1px solid #1F2937;">

                <div style="background: linear-gradient(135deg, #10B981 0%, #059669 100%);
                            padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0; font-size: 20px;">
                        ⚡ Voxel Estate — Run Summary
                    </h1>
                </div>

                <div style="padding: 24px;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="color: #9CA3AF; padding: 6px 0;">Client</td>
                            <td style="color: #FFFFFF; text-align: right; font-weight: 600;">
                                {self.client_id}
                            </td>
                        </tr>
                        <tr>
                            <td style="color: #9CA3AF; padding: 6px 0;">Time</td>
                            <td style="color: #FFFFFF; text-align: right;">
                                {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}
                            </td>
                        </tr>
                        <tr>
                            <td style="color: #9CA3AF; padding: 6px 0;">Duration</td>
                            <td style="color: #FFFFFF; text-align: right;">
                                {self.duration_seconds:.1f} seconds
                            </td>
                        </tr>
                    </table>

                    <hr style="border: none; border-top: 1px solid #1F2937; margin: 20px 0;">

                    <h3 style="color: #10B981; font-size: 13px; text-transform: uppercase;
                               letter-spacing: 1px; margin: 20px 0 12px 0;">
                        Rows Processed
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="color: #9CA3AF; padding: 4px 0;">Input</td>
                            <td style="color: #FFFFFF; text-align: right;">{self.input_rows}</td>
                        </tr>
                        <tr>
                            <td style="color: #9CA3AF; padding: 4px 0;">Dropped (invalid)</td>
                            <td style="color: #EF4444; text-align: right;">{self.dropped_rows}</td>
                        </tr>
                        <tr>
                            <td style="color: #9CA3AF; padding: 4px 0;">Valid</td>
                            <td style="color: #10B981; text-align: right; font-weight: 600;">
                                {self.valid_rows}
                            </td>
                        </tr>
                    </table>

                    <h3 style="color: #10B981; font-size: 13px; text-transform: uppercase;
                               letter-spacing: 1px; margin: 20px 0 12px 0;">
                        AI Classification
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="color: #9CA3AF; padding: 4px 0;">API Requests</td>
                            <td style="color: #FFFFFF; text-align: right;">{self.ai_requests}</td>
                        </tr>
                        <tr>
                            <td style="color: #9CA3AF; padding: 4px 0;">Cache Hits</td>
                            <td style="color: #10B981; text-align: right;">{self.ai_cached}</td>
                        </tr>
                        <tr>
                            <td style="color: #9CA3AF; padding: 4px 0;">AI Classified</td>
                            <td style="color: #FFFFFF; text-align: right;">{self.ai_classified}</td>
                        </tr>
                        <tr>
                            <td style="color: #9CA3AF; padding: 4px 0;">Fallback Used</td>
                            <td style="color: #F59E0B; text-align: right;">{self.ai_fallback}</td>
                        </tr>
                    </table>

                    <h3 style="color: #10B981; font-size: 13px; text-transform: uppercase;
                               letter-spacing: 1px; margin: 20px 0 12px 0;">
                        Sheet Delivery
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="color: #9CA3AF; padding: 4px 0;">Pushed</td>
                            <td style="color: #10B981; text-align: right; font-weight: 600;">
                                {self.sheet_pushed}
                            </td>
                        </tr>
                        <tr>
                            <td style="color: #9CA3AF; padding: 4px 0;">Skipped (duplicates)</td>
                            <td style="color: #6B7280; text-align: right;">{self.sheet_skipped}</td>
                        </tr>
                    </table>

                    <div style="background: {status_color}22; border-left: 3px solid {status_color};
                                padding: 12px 16px; border-radius: 8px; margin-top: 24px;">
                        <div style="color: {status_color}; font-weight: 600; font-size: 14px;">
                            {status_icon} Status: {self.status.upper()}
                        </div>
                    </div>

                    {"" if not self.error_message else f'''
                    <div style="background: #EF444422; border-left: 3px solid #EF4444;
                                padding: 12px 16px; border-radius: 8px; margin-top: 12px;">
                        <div style="color: #FCA5A5; font-weight: 600; font-size: 12px;
                                    text-transform: uppercase; margin-bottom: 6px;">Error</div>
                        <div style="color: #FCA5A5; font-family: monospace; font-size: 12px;
                                    word-break: break-all;">
                            {self.error_message[:500]}
                        </div>
                    </div>
                    '''}

                    <div style="text-align: center; margin-top: 30px; padding-top: 20px;
                                border-top: 1px solid #1F2937; color: #6B7280; font-size: 11px;">
                        Voxel Estate — Automated Motivated Seller Intelligence<br>
                        <a href="https://voxelestate.netlify.app"
                           style="color: #10B981; text-decoration: none;">
                            voxelestate.netlify.app
                        </a>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return html


# ============================================================
# EMAIL SENDER
# ============================================================
def send_summary_email(summary: RunSummary) -> tuple:
    """
    Send run summary email via Gmail SMTP.

    Returns:
        (success: bool, message: str)
    """
    sender = os.getenv("EMAIL_SENDER")
    password = os.getenv("EMAIL_PASSWORD")
    recipient = os.getenv("EMAIL_RECIPIENT")

    if not all([sender, password, recipient]):
        log.warning("Email credentials not configured — skipping summary email")
        return False, "Email config incomplete"

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = sender
        msg["To"] = recipient

        status_icon = {
            "success": "✅",
            "error": "❌",
            "partial": "⚠️",
        }.get(summary.status, "❓")

        msg["Subject"] = (
            f"{status_icon} Run Summary — {summary.client_id} "
            f"({summary.sheet_pushed} leads)"
        )

        # Plain text + HTML
        msg.attach(MIMEText(summary.to_text(), "plain"))
        msg.attach(MIMEText(summary.to_html(), "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)

        log.info(f"Run summary email sent to {recipient}")
        return True, f"Sent to {recipient}"

    except Exception as e:
        log.warning(f"Failed to send summary email: {e}")
        return False, f"Send failed: {str(e)[:100]}"


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("RUN SUMMARY TEST")
    print("=" * 60)

    summary = RunSummary(client_id="client_001", run_type="manual")
    summary.set_input_rows(100)
    summary.set_dropped_rows(5)
    summary.set_ai_stats(requests=7, cached=0, classified=95, fallback=0)
    summary.set_sheet_stats(pushed=95, skipped=0)
    summary.set_success()
    summary.finish()

    print(summary.to_text())

    print("\n[2] Sending test email...")
    ok, msg = send_summary_email(summary)
    print(f"   {msg}")

    if ok:
        print("   ✅ Check your Gmail inbox!")
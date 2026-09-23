"""
RUN SUMMARY REPORTER
====================
Tracks pipeline stats and sends summary email via Gmail SMTP.

RECIPIENT LOGIC:
    All emails go to admin only (EMAIL_ADMIN).
    Future: client emails can be added via _get_recipients().

FIX 6 (Privacy hygiene):
    - Error messages truncated to 300 chars in email
    - No stack traces in summary emails
    - No PII in any field (already enforced by pipeline)

FIX 1 (Partial-run tracking):
    - Tracks files_partial / files_fully_done / leads_pending
    - to_text() shows "PARTIAL RUN" block when applicable
    - Status can be "partial" (some files done, some pending)

USAGE:
    from run_summary import RunSummary, send_summary_email
    
    summary = RunSummary(client_id="client_001")
    summary.set_input_rows(10)
    summary.set_dropped_rows(2)
    summary.set_sheet_stats(pushed=8, skipped=2)
    summary.set_partial_info(files_partial=0, files_done=1, leads_pending=0)
    summary.finish()
    send_summary_email(summary)
"""

import os
import smtplib
from datetime import datetime
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
# CONFIG
# ============================================================
MAX_ERROR_MSG_LEN = 300


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

        self.input_rows = 0
        self.dropped_rows = 0
        self.valid_rows = 0

        self.ai_requests = 0
        self.ai_cached = 0
        self.ai_classified = 0
        self.ai_fallback = 0

        self.sheet_pushed = 0
        self.sheet_skipped = 0

        # Fix 1: partial-run tracking
        self.files_partial = 0
        self.files_fully_done = 0
        self.leads_pending = 0

        self.status = "unknown"
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

    def set_partial_info(self, files_partial: int = 0,
                         files_done: int = 0,
                         leads_pending: int = 0):
        """Fix 1: track partial-run info."""
        self.files_partial = files_partial
        self.files_fully_done = files_done
        self.leads_pending = leads_pending

    def set_error(self, message: str):
        """Set error message (truncated for email)."""
        self.status = "error"
        self.error_message = str(message)[:MAX_ERROR_MSG_LEN]

    def set_success(self):
        self.status = "success"

    def set_partial(self):
        self.status = "partial"

    def finish(self):
        self.end_time = datetime.now()

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    # --------------------------------------------------------
    # Text output
    # --------------------------------------------------------
    def to_text(self) -> str:
        status_icon = {
            "success": "[OK]",
            "error": "[ERR]",
            "partial": "[WARN]",
            "unknown": "[?]",
        }.get(self.status, "[?]")

        lines = [
            "=" * 60,
            f"RUN SUMMARY - {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
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
        ]

        # Fix 1: partial-run info block
        if self.leads_pending > 0 or self.files_partial > 0:
            lines.extend([
                "",
                "PARTIAL RUN:",
                f"  Files done:    {self.files_fully_done}",
                f"  Files partial: {self.files_partial} (stay in inbox)",
                f"  Leads pending: {self.leads_pending} (retry next run)",
            ])

        lines.extend([
            "",
            f"STATUS: {status_icon} {self.status.upper()}",
        ])

        if self.error_message:
            lines.append("")
            lines.append("ERROR:")
            lines.append(f"  {self.error_message}")
            lines.append("")
            lines.append("  (Full error logged to logs/errors_*.log)")

        lines.append("=" * 60)
        return "\n".join(lines)

    # --------------------------------------------------------
    # HTML output
    # --------------------------------------------------------
    def to_html(self) -> str:
        status_color = {
            "success": "#10B981",
            "error": "#EF4444",
            "partial": "#F59E0B",
            "unknown": "#6B7280",
        }.get(self.status, "#6B7280")

        status_icon = {
            "success": "OK",
            "error": "ERROR",
            "partial": "PARTIAL",
            "unknown": "UNKNOWN",
        }.get(self.status, "UNKNOWN")

        error_block = ""
        if self.error_message:
            error_block = f"""
                    <div style="background: #EF444422; border-left: 3px solid #EF4444;
                                padding: 12px 16px; border-radius: 8px; margin-top: 12px;">
                        <div style="color: #FCA5A5; font-weight: 600; font-size: 12px;
                                    text-transform: uppercase; margin-bottom: 6px;">Error</div>
                        <div style="color: #FCA5A5; font-family: monospace; font-size: 12px;
                                    word-break: break-all;">
                            {self.error_message}
                        </div>
                        <div style="color: #9CA3AF; font-size: 11px; margin-top: 8px;">
                            Full error in logs/errors_*.log
                        </div>
                    </div>
            """

        partial_block = ""
        if self.leads_pending > 0 or self.files_partial > 0:
            partial_block = f"""
                    <div style="background: #F59E0B22; border-left: 3px solid #F59E0B;
                                padding: 12px 16px; border-radius: 8px; margin-top: 12px;">
                        <div style="color: #FCD34D; font-weight: 600; font-size: 12px;
                                    text-transform: uppercase; margin-bottom: 6px;">
                            Partial Run
                        </div>
                        <div style="color: #FCD34D; font-size: 12px;">
                            Files done: {self.files_fully_done} |
                            Files partial: {self.files_partial} |
                            Leads pending: {self.leads_pending}
                        </div>
                        <div style="color: #9CA3AF; font-size: 11px; margin-top: 6px;">
                            Pending leads will retry on next run (cache + inbox file kept).
                        </div>
                    </div>
            """

        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                     background: #0A0A0A; color: #E5E7EB; padding: 20px; margin: 0;">
            <div style="max-width: 600px; margin: 0 auto; background: #111827;
                        border-radius: 12px; overflow: hidden; border: 1px solid #1F2937;">

                <div style="background: linear-gradient(135deg, #10B981 0%, #059669 100%);
                            padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0; font-size: 20px;">
                        Voxel Estate - Run Summary
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
                            Status: {status_icon}
                        </div>
                    </div>
                    {partial_block}
                    {error_block}
                    <div style="text-align: center; margin-top: 30px; padding-top: 20px;
                                border-top: 1px solid #1F2937; color: #6B7280; font-size: 11px;">
                        Voxel Estate - Automated Motivated Seller Intelligence<br>
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
# RECIPIENT LOGIC
# ============================================================
def _get_recipients(summary: RunSummary) -> list:
    """
    All emails go to admin only.
    Future: add client email for success-only forwarding.
    """
    admin = (os.getenv("EMAIL_ADMIN") or os.getenv("EMAIL_RECIPIENT") or "").strip()
    return [admin] if admin else []


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

    if not all([sender, password]):
        log.warning("Email credentials not configured — skipping summary email")
        return False, "Email config incomplete"

    recipients = _get_recipients(summary)
    if not recipients:
        log.warning("No email recipients configured — skipping")
        return False, "No recipients"

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)

        status_tag = {
            "success": "[OK]",
            "error": "[ERR]",
            "partial": "[PARTIAL]",
        }.get(summary.status, "[?]")

        msg["Subject"] = (
            f"{status_tag} Run Summary - {summary.client_id} "
            f"({summary.sheet_pushed} leads)"
        )

        msg.attach(MIMEText(summary.to_text(), "plain"))
        msg.attach(MIMEText(summary.to_html(), "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)

        log.info(f"Run summary email sent to {recipients}")
        return True, f"Sent to {', '.join(recipients)}"

    except Exception as e:
        log.warning(f"Failed to send summary email: {e}")
        return False, f"Send failed: {str(e)[:100]}"


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("RUN SUMMARY TEST — Fix 1 + Fix 6")
    print("=" * 60)

    # Test 1: Success run
    summary = RunSummary(client_id="client_001", run_type="manual")
    summary.set_input_rows(100)
    summary.set_dropped_rows(5)
    summary.set_ai_stats(requests=7, cached=0, classified=95, fallback=0)
    summary.set_sheet_stats(pushed=95, skipped=0)
    summary.set_partial_info(files_partial=0, files_done=1, leads_pending=0)
    summary.set_success()
    summary.finish()

    print("\n[1] Success run output:")
    print(summary.to_text())

    # Test 2: Partial run
    print("\n[2] Partial run output:")
    partial = RunSummary(client_id="client_001", run_type="manual")
    partial.set_input_rows(800)
    partial.set_dropped_rows(50)
    partial.set_ai_stats(requests=20, cached=350, classified=412, fallback=0)
    partial.set_sheet_stats(pushed=412, skipped=0)
    partial.set_partial_info(files_partial=1, files_done=0, leads_pending=388)
    partial.set_partial()
    partial.finish()
    print(partial.to_text())

    # Test 3: Error truncation
    print("\n[3] Error message truncation:")
    summary2 = RunSummary(client_id="client_002")
    long_error = "X" * 1000
    summary2.set_error(long_error)
    print(f"   Input error length: {len(long_error)}")
    print(f"   Stored error length: {len(summary2.error_message)}")
    print(f"   Expected max: {MAX_ERROR_MSG_LEN}")
    assert len(summary2.error_message) == MAX_ERROR_MSG_LEN, "Truncation failed!"
    print("   OK — error truncated correctly")

    print("\n✅ Run summary test complete")
    print("   (Skipping email send to avoid spamming inbox)")
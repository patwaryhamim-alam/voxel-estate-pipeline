"""
INVOICE HTML GENERATOR
======================
Converts invoice markdown to styled HTML for fast PDF export.

USAGE:
    python scripts/generate_invoice_html.py docs/invoice_VE-2026-0001.md
"""

import re
import sys
from pathlib import Path


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Invoice</title>
<style>
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    max-width: 800px;
    margin: 40px auto;
    padding: 20px;
    color: #1F2937;
    line-height: 1.6;
  }
  img { max-width: 250px; height: auto; display: block; margin: 0 auto 20px; }
  h1 {
    text-align: center;
    color: #1F2937;
    border-bottom: 3px solid #10B981;
    padding-bottom: 10px;
    letter-spacing: 2px;
    margin-top: 10px;
  }
  h2 {
    color: #10B981;
    border-bottom: 2px solid #10B981;
    padding-bottom: 5px;
    margin-top: 30px;
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 15px 0;
  }
  th, td {
    border: 1px solid #E5E7EB;
    padding: 10px 12px;
    text-align: left;
    font-size: 14px;
    vertical-align: top;
  }
  th {
    background: #10B981;
    color: white;
    font-weight: 600;
  }
  strong { color: #1F2937; font-weight: 600; }
  hr { border: none; border-top: 1px solid #E5E7EB; margin: 25px 0; }
  em { color: #6B7280; font-size: 13px; display: block; text-align: center; margin-top: 30px; }
  p { margin: 10px 0; }
  ul { margin: 10px 0; padding-left: 20px; }
  li { margin: 4px 0; }
</style>
</head>
<body>
{content}
</body>
</html>
"""


def md_to_html(md_text):
    """Simple markdown to HTML converter for our specific invoice format."""
    lines = md_text.split("\n")
    html_lines = []
    in_table = False
    table_buffer = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Image
        img_match = re.search(r'<img[^>]*src="([^"]+)"[^>]*>', line)
        if img_match:
            src = img_match.group(1)
            html_lines.append(f'<img src="{src}" alt="Logo" />')
            i += 1
            continue

        # HTML tags (p, div) — pass through
        if stripped.startswith("<p") or stripped.startswith("</p") or stripped.startswith("<div"):
            html_lines.append(line)
            i += 1
            continue

        # Heading 1
        if stripped.startswith("# "):
            html_lines.append(f"<h1>{stripped[2:]}</h1>")
            i += 1
            continue

        # Heading 2
        if stripped.startswith("## "):
            html_lines.append(f"<h2>{stripped[3:]}</h2>")
            i += 1
            continue

        # Horizontal rule
        if stripped == "---":
            html_lines.append("<hr />")
            i += 1
            continue

        # Table detection
        if stripped.startswith("|") and stripped.endswith("|"):
            table_buffer.append(stripped)
            i += 1
            continue
        else:
            # Flush table if we were in one
            if table_buffer:
                html_lines.append(render_table(table_buffer))
                table_buffer = []

        # Empty line
        if stripped == "":
            i += 1
            continue

        # Bold paragraph like "**Voxel Estate**"
        if stripped.startswith("**") and stripped.endswith("**"):
            content = stripped[2:-2]
            html_lines.append(f"<p><strong>{content}</strong></p>")
            i += 1
            continue

        # List items "- xxx" or "* xxx"
        if stripped.startswith("- ") or stripped.startswith("* "):
            list_items = []
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                item = lines[i].strip()[2:]
                # Inline markdown cleanup
                item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
                list_items.append(f"<li>{item}</li>")
                i += 1
            html_lines.append(f"<ul>{''.join(list_items)}</ul>")
            continue

        # Regular paragraph — clean inline markdown
        cleaned = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
        html_lines.append(f"<p>{cleaned}</p>")
        i += 1

    # Flush any remaining table
    if table_buffer:
        html_lines.append(render_table(table_buffer))

    return "\n".join(html_lines)


def render_table(table_lines):
    """Convert markdown table lines to HTML table."""
    if len(table_lines) < 2:
        return ""

    # First line = header
    header_cells = [c.strip() for c in table_lines[0].strip("|").split("|")]

    # Second line = separator (|----|----|)
    # Data starts from line 2
    data_lines = table_lines[2:] if len(table_lines) > 2 else []

    html = ["<table>"]
    html.append("<thead><tr>")
    for cell in header_cells:
        cell_clean = re.sub(r"\*\*(.+?)\*\*", r"\1", cell)
        html.append(f"<th>{cell_clean}</th>")
    html.append("</tr></thead>")
    html.append("<tbody>")

    for line in data_lines:
        cells = [c.strip() for c in line.strip("|").split("|")]
        html.append("<tr>")
        for cell in cells:
            # Handle <br> tags
            cell = cell.replace("<br>", "<br />")
            # Handle bold
            cell = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", cell)
            html.append(f"<td>{cell}</td>")
        html.append("</tr>")

    html.append("</tbody></table>")
    return "\n".join(html)


def generate_html(md_path):
    md_path = Path(md_path)
    if not md_path.exists():
        print(f"❌ File not found: {md_path}")
        sys.exit(1)

    md_content = md_path.read_text(encoding="utf-8")
    html_content = md_to_html(md_content)
    full_html = HTML_TEMPLATE.replace("{content}", html_content)

    html_path = md_path.with_suffix(".html")
    html_path.write_text(full_html, encoding="utf-8")

    print(f"✅ HTML generated: {html_path}")
    print(f"\n📄 Next steps:")
    print(f"   1. Open in browser:  start {html_path}")
    print(f"   2. Press Ctrl + P")
    print(f"   3. Choose 'Save as PDF'")
    print(f"   4. Enable 'Background graphics' in More Settings")
    print(f"   5. Save to: {md_path.parent}")
    return html_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("USAGE: python scripts/generate_invoice_html.py <markdown_file>")
        print("EXAMPLE: python scripts/generate_invoice_html.py docs/invoice_VE-2026-0001.md")
        sys.exit(1)

    generate_html(sys.argv[1])
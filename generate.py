#!/usr/bin/env python3
"""
Sefer Engine — Generate PDF from structured JSON content.

Usage:
    python generate.py [content_json] [output_pdf]

Defaults:
    content_json = content/test_pages.json
    output_pdf = output/shefa_shlomo_test.pdf
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from engine.renderer import generate_pdf


def main():
    # Defaults
    content_json = "content/test_pages.json"
    output_pdf = "output/shefa_shlomo_test.pdf"
    output_html = "output/shefa_shlomo_test.html"

    # CLI args
    if len(sys.argv) > 1:
        content_json = sys.argv[1]
    if len(sys.argv) > 2:
        output_pdf = sys.argv[2]

    # Resolve paths relative to script location
    base = Path(__file__).parent
    content_path = base / content_json
    pdf_path = base / output_pdf
    html_path = base / output_html

    print(f"Sefer Engine — Generating PDF")
    print(f"  Content: {content_path}")
    print(f"  Output:  {pdf_path}")
    print()

    generate_pdf(
        json_path=str(content_path),
        output_pdf=str(pdf_path),
        output_html=str(html_path),
    )

    print("\nDone!")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Sefer Engine — Generate a book PDF from content JSON.

Usage:
  python generate.py                          # uses default sample content
  python generate.py path/to/content.json     # uses custom content
  python generate.py content.json output.pdf  # custom input + output
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from sefer_engine.loader import load_from_json
from sefer_engine.paginator import Paginator, PageConfig
from sefer_engine.renderer import render_to_pdf


def main():
    # Parse args
    content_path = sys.argv[1] if len(sys.argv) > 1 else "sample_content/shefa_shlomo.json"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "output/sefer.pdf"

    # Ensure output dir exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading content from: {content_path}")
    book = load_from_json(content_path)
    print(f"  Title: {book.title}")
    print(f"  Sections: {len(book.sections)}")

    # Configure page layout
    config = PageConfig(
        page_height_mm=240,
        page_width_mm=170,
        margin_top_mm=15,
        margin_bottom_mm=15,
        margin_inner_mm=18,
        margin_outer_mm=15,
    )

    # Run pagination algorithm
    print("\nRunning pagination algorithm...")
    paginator = Paginator(config)
    pages = paginator.paginate(book)

    print(f"  Generated {len(pages)} pages")
    for p in pages:
        bz_type = p.bottom_zone.layout_type if p.bottom_zone else "none"
        sections = ", ".join(p.section_numbers) if p.section_numbers else "(carry-over)"
        print(f"  Page {p.page_number}: sections [{sections}] | bottom: {bz_type} | "
              f"main: {p.main_text_height_mm:.0f}mm")

    # Render to PDF
    print(f"\nRendering to PDF: {output_path}")
    html_path, pdf_path = render_to_pdf(pages, output_path, title=book.title)
    print(f"  HTML saved: {html_path}")
    print(f"  PDF saved:  {pdf_path}")
    print("\nDone!")


if __name__ == "__main__":
    main()

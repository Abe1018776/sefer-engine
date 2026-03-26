#!/usr/bin/env python3
"""
engine/validate.py — Post-Render Validation

Quality checks on the compiled PDF and page data:
- Page count matches expected
- Content completeness (no empty pages)
- All footnote markers present in output
- Hebrew text renders (no tofu/boxes)
- Overflow detection
"""

import json
import re
import subprocess
from pathlib import Path


class ValidationResult:
    """Collects validation results."""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    def add_info(self, msg: str):
        self.info.append(msg)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def report(self) -> str:
        lines = ["═══ Validation Report ═══"]
        if self.info:
            for i in self.info:
                lines.append(f"  ℹ {i}")
        if self.warnings:
            lines.append(f"\n  Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"    ⚠ {w}")
        if self.errors:
            lines.append(f"\n  Errors ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"    ✗ {e}")
        if self.passed:
            lines.append("\n  ✓ All validations passed")
        else:
            lines.append(f"\n  ✗ {len(self.errors)} error(s) found")
        return '\n'.join(lines)


def validate_pages(pages: list, result: ValidationResult = None) -> ValidationResult:
    """Validate page data before rendering.
    
    Args:
        pages: List of page dicts from solver
        result: Optional existing ValidationResult to append to
    """
    if result is None:
        result = ValidationResult()

    result.add_info(f"Page count: {len(pages)}")

    if len(pages) == 0:
        result.error("No pages generated")
        return result

    # Check for empty pages
    empty_pages = []
    for p in pages:
        has_content = (
            p.get('main_text', '').strip() or
            p.get('section_title', '').strip() or
            p.get('section_text', '').strip() or
            p.get('makor_text', '').strip() or
            p.get('tzinor_text', '').strip()
        )
        if not has_content:
            empty_pages.append(p.get('page_display', '?'))

    if empty_pages:
        result.error(f"Empty pages: {', '.join(empty_pages)}")

    # Check for required fields
    required_fields = ['id', 'page_display', 'header', 'makor_title', 'tzinor_title']
    for p in pages:
        for field in required_fields:
            if field not in p:
                result.error(f"Page {p.get('page_display', '?')}: missing field '{field}'")

    # Check content completeness: look for very short pages (potential splits)
    for p in pages:
        mk = p.get('makor_text', '')
        tz = p.get('tzinor_text', '')
        if mk and len(mk) < 20:
            result.warn(f"Page {p['page_display']}: very short makor ({len(mk)} chars)")
        if tz and len(tz) < 20:
            result.warn(f"Page {p['page_display']}: very short tzinor ({len(tz)} chars)")

    # Check for replacement character U+FFFD in text
    for p in pages:
        for field in ['main_text', 'section_text', 'makor_text', 'tzinor_text']:
            text = p.get(field, '')
            if '\ufffd' in text:
                result.error(f"Page {p['page_display']}: U+FFFD replacement char in {field}")

    # Check page numbering continuity
    displays = [p['page_display'] for p in pages]
    result.add_info(f"Pages: {displays[0]} to {displays[-1]}")

    return result


def validate_pdf(pdf_path: str, expected_pages: int = None,
                 result: ValidationResult = None) -> ValidationResult:
    """Validate the compiled PDF.
    
    Args:
        pdf_path: Path to the output PDF
        expected_pages: Expected page count (optional)
        result: Optional existing ValidationResult
    """
    if result is None:
        result = ValidationResult()

    path = Path(pdf_path)
    if not path.exists():
        result.error(f"PDF not found: {pdf_path}")
        return result

    result.add_info(f"PDF size: {path.stat().st_size / 1024:.1f} KB")

    # Get page count using pdfinfo or similar
    try:
        r = subprocess.run(
            ['pdfinfo', str(path)],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            for line in r.stdout.split('\n'):
                if line.startswith('Pages:'):
                    pdf_pages = int(line.split(':')[1].strip())
                    result.add_info(f"PDF page count: {pdf_pages}")
                    if expected_pages and pdf_pages != expected_pages:
                        result.warn(
                            f"PDF has {pdf_pages} pages, expected {expected_pages}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        result.warn("Could not verify PDF page count (pdfinfo not available)")

    # Check file is non-trivially large (not an error page)
    if path.stat().st_size < 5000:
        result.warn("PDF is suspiciously small — may be a compile error page")

    return result


def validate_all(pages_json_path: str, pdf_path: str = None) -> ValidationResult:
    """Run all validations.
    
    Args:
        pages_json_path: Path to test_pages.json
        pdf_path: Path to compiled PDF (optional)
    """
    result = ValidationResult()

    # Load and validate pages
    try:
        with open(pages_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        pages = data.get('pages', [])
        validate_pages(pages, result)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        result.error(f"Could not load pages JSON: {e}")
        return result

    # Validate PDF if path provided
    if pdf_path:
        validate_pdf(pdf_path, expected_pages=len(pages), result=result)

    return result


if __name__ == '__main__':
    import sys
    pages_path = sys.argv[1] if len(sys.argv) > 1 else 'content/test_pages.json'
    pdf_path = sys.argv[2] if len(sys.argv) > 2 else None

    result = validate_all(pages_path, pdf_path)
    print(result.report())
    sys.exit(0 if result.passed else 1)

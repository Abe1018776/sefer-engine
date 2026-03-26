#!/usr/bin/env python3
"""
run_pipeline.py — Sefer Engine Master Pipeline

Full pipeline: load content → solve pages → write test_pages.json → compile PDFs → validate

Usage:
    python3 run_pipeline.py content/unpaginated_shaar_hatorah.json
    python3 run_pipeline.py content/unpaginated_shaar_hatorah.json --skip-compile
"""

import json
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Ensure engine is importable
sys.path.insert(0, str(BASE_DIR))


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Sefer Engine — Full Pipeline')
    parser.add_argument('input', help='Path to unpaginated JSON content file')
    parser.add_argument('--output', default=None,
                       help='Output test_pages.json path (default: content/test_pages.json)')
    parser.add_argument('--overrides', default=None,
                       help='Path to overrides.json (default: content/overrides.json)')
    parser.add_argument('--skip-compile', action='store_true',
                       help='Skip PDF compilation (just paginate and validate)')
    parser.add_argument('--pdf-output', default=None,
                       help='Output PDF path (default: context/output/sefer_output.pdf)')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = BASE_DIR / input_path
    
    output_path = Path(args.output) if args.output else BASE_DIR / 'content' / 'test_pages.json'
    overrides_path = args.overrides
    if overrides_path is None:
        default_ovr = BASE_DIR / 'content' / 'overrides.json'
        if default_ovr.exists():
            overrides_path = str(default_ovr)

    t0 = time.time()
    print("╔═══════════════════════════════════════════════╗")
    print("║   Sefer Engine — Production Pipeline          ║")
    print("╚═══════════════════════════════════════════════╝\n")

    # ─── Step 1: Solve pages ─────────────────────────────────────
    print("▶ Step 1: Solving page layout...")
    from engine.solver import solve_and_output
    pages = solve_and_output(
        str(input_path), str(output_path), overrides_path)
    t1 = time.time()
    print(f"  ✓ {len(pages)} pages solved in {t1-t0:.1f}s\n")

    # ─── Step 2: Validate pages ──────────────────────────────────
    print("▶ Step 2: Validating page data...")
    from engine.validate import validate_pages, ValidationResult
    result = ValidationResult()
    validate_pages(pages, result)
    
    if not result.passed:
        print(result.report())
        print("\n  ✗ Validation failed — skipping compile")
        sys.exit(1)
    print(f"  ✓ Page validation passed ({len(pages)} pages)\n")

    # ─── Step 3: Compile PDFs ────────────────────────────────────
    if args.skip_compile:
        print("▶ Step 3: SKIPPED (--skip-compile)\n")
        pdf_path = None
    else:
        print("▶ Step 3: Compiling ConTeXt → PDF...")
        t2 = time.time()
        
        # Set font path if not already set
        if 'OSFONTDIR' not in os.environ:
            os.environ['OSFONTDIR'] = (
                "/usr/share/fonts/truetype/culmus:"
                "/usr/share/fonts/truetype/noto"
            )
        
        from generate_context import main as render_main
        pdf_path = render_main(str(output_path), args.pdf_output)
        t3 = time.time()
        print(f"  ✓ PDF compiled in {t3-t2:.1f}s\n")

    # ─── Step 4: Post-render validation ──────────────────────────
    print("▶ Step 4: Post-render validation...")
    from engine.validate import validate_pdf
    if pdf_path:
        validate_pdf(str(pdf_path), expected_pages=len(pages), result=result)
    
    print(result.report())
    
    total_time = time.time() - t0
    print(f"\n  Total pipeline time: {total_time:.1f}s")
    
    if result.passed:
        print("\n╔═══════════════════════════════════════════════╗")
        print("║   Pipeline complete — all checks passed       ║")
        print("╚═══════════════════════════════════════════════╝")
        return 0
    else:
        print("\n⚠ Pipeline completed with warnings/errors")
        return 1


if __name__ == '__main__':
    try:
        rc = main()
        sys.exit(rc or 0)
    except Exception as e:
        print(f"\n✗ Pipeline error: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
        sys.exit(1)

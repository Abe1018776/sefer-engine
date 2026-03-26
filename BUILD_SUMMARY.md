# Build Summary — Measurement + Solver + Overrides

## Files Created

### engine/measure.py (315 lines)
Font measurement engine using fontTools. Loads Frank Ruehl CLM font metrics with
Noto Serif Hebrew fallback. Provides:
- `TextMeasurer` class with real glyph-width-based line counting
- `count_lines()`, `measure_height()`, `split_at_height()` methods
- Factory functions: `create_column_measurer()` (10pt/67.75mm), 
  `create_body_measurer()` (12pt/139mm), `create_fullwidth_column_measurer()` (10pt/139mm)

### engine/solver.py (465 lines)
Coupled page solver replacing character-count-based paginator:
- Uses TextMeasurer for all height calculations
- Supports dual-column (L-shape), single-column, and zero-body pages
- Enforces footnote-anchor coupling, widow/orphan prevention
- Computes badness scores (slack + imbalance + penalties)
- `solve_and_output()` convenience function for pipeline use
- Hebrew numeral conversion built-in

### engine/overrides.py (82 lines)
Manual override system:
- Reads overrides.json with page-specific and global settings
- Supports: force_break_before, extra_leading_pt, keep_with_next
- Global: min_body_lines, min_column_lines, max_column_imbalance_ratio

### engine/validate.py (198 lines)
Post-render validation:
- Page count and content completeness checks
- Empty page detection, U+FFFD (tofu) detection
- PDF existence and size verification via pdfinfo
- `validate_all()` combines page + PDF validation

### content/overrides.json
Default override configuration with global settings.

### run_pipeline.py (122 lines)
Master pipeline script: solve → validate → compile → post-validate
Usage: `python3 run_pipeline.py content/unpaginated_shaar_hatorah.json`

## Files Modified

### generate_context.py
Added single-column mode support:
- `detect_column_mode()` function: returns 'dual', 'makor_only', 'tzinor_only', 'none'
- `gen_measure_tex()`: measures at full width for single-column pages
- `gen_final_tex()`: renders makor/tzinor as full-width \tfx paragraph when alone
- `main()` now accepts command-line arguments for JSON input and PDF output
- `parse_measurements()` handles non-numeric fields (mode string)

## Pipeline Output
- 10 pages solved from unpaginated_shaar_hatorah.json
  - 4 dual-column pages (א-ד) with L-shape layout
  - 5 single-column pages (ה-ט) with makor-only at full width
  - 1 section-title-only page (י)
- All pages compiled successfully
- Output: context/output/sefer_output.pdf (219.6 KB, 10 pages)
- All validations passed

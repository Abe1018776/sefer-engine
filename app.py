#!/usr/bin/env python3
"""
Sefer Engine — Flask Web Application

A web interface for the Hebrew book typesetting engine.
Accepts structured content (JSON or DOCX) and produces
L-shape dual-column layouts in PDF.

Usage:
    python app.py
"""

import json
import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    abort,
    redirect,
    url_for,
)

from sefer_engine.loader import load_from_json
from sefer_engine.paginator import Paginator, PageConfig, BookContent, Section, SourceEntry, StoryEntry
from sefer_engine.renderer import render_book, render_to_pdf, render_to_html

# Try to import the proper DOCX loader
try:
    from sefer_engine.docx_loader import load_from_docx as _load_docx
    HAS_DOCX_LOADER = True
except ImportError:
    HAS_DOCX_LOADER = False

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB max upload

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Store job metadata in memory (in production, use a database)
jobs = {}


def parse_config_from_form(form):
    """Extract PageConfig from form data, using defaults for missing/blank fields."""
    def _f(key, default):
        v = form.get(key, "")
        return float(v) if v not in ("", None) else default

    return PageConfig(
        page_width_mm=_f("page_width", 170),
        page_height_mm=_f("page_height", 240),
        margin_top_mm=_f("margin_top", 15),
        margin_bottom_mm=_f("margin_bottom", 15),
        margin_inner_mm=_f("margin_inner", 18),
        margin_outer_mm=_f("margin_outer", 15),
    )


def parse_config_from_json(data):
    """Extract PageConfig from JSON API request."""
    config_data = data.get("config", {})
    return PageConfig(
        page_width_mm=float(config_data.get("page_width", 170)),
        page_height_mm=float(config_data.get("page_height", 240)),
        margin_top_mm=float(config_data.get("margin_top", 15)),
        margin_bottom_mm=float(config_data.get("margin_bottom", 15)),
        margin_inner_mm=float(config_data.get("margin_inner", 18)),
        margin_outer_mm=float(config_data.get("margin_outer", 15)),
    )


def load_content_from_json_data(data):
    """Load BookContent from a JSON dict (same structure as the JSON files)."""
    meta = data.get("metadata", {})
    book = BookContent(
        title=meta.get("title", ""),
        subtitle=meta.get("subtitle", ""),
        author=meta.get("author", ""),
    )
    for sec_data in data.get("sections", []):
        sources = [
            SourceEntry(marker=s["marker"], ref=s.get("ref", ""), text=s["text"])
            for s in sec_data.get("sources", [])
        ]
        stories = [
            StoryEntry(marker=s["marker"], text=s["text"])
            for s in sec_data.get("stories", [])
        ]
        section = Section(
            id=sec_data["id"],
            number=sec_data["number"],
            title=sec_data["title"],
            main_text=sec_data["main_text"],
            sources=sources,
            stories=stories,
            continuation=sec_data.get("continuation", ""),
        )
        book.sections.append(section)
    return book


def load_content_from_docx(file_path):
    """Load BookContent from a DOCX file using the proper Hebrew parser."""
    if HAS_DOCX_LOADER:
        return _load_docx(file_path)

    # Fallback: basic parsing if docx_loader not available
    try:
        from docx import Document
    except ImportError:
        raise ImportError(
            "python-docx is not installed. "
            "Install it with: pip install python-docx"
        )

    doc = Document(file_path)
    book = BookContent(title="", subtitle="", author="")
    current_section = None
    section_counter = 0

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if para.style.name.startswith("Heading"):
            if current_section is not None:
                book.sections.append(current_section)
            section_counter += 1
            current_section = Section(
                id=str(section_counter),
                number=str(section_counter),
                title=text,
                main_text="",
            )
        elif current_section is not None:
            if current_section.main_text:
                current_section.main_text += "\n" + text
            else:
                current_section.main_text = text
        else:
            if not book.title:
                book.title = text
            elif not book.subtitle:
                book.subtitle = text

    if current_section is not None:
        book.sections.append(current_section)
    if not book.title and book.sections:
        book.title = book.sections[0].title
    return book


def run_generation(book, config, job_id):
    """Run the full generation pipeline and return paths."""
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = str(job_dir / "sefer.pdf")

    paginator = Paginator(config)
    pages = paginator.paginate(book)

    html_path, pdf_path = render_to_pdf(pages, pdf_path, title=book.title)

    return {
        "html_path": html_path,
        "pdf_path": pdf_path,
        "page_count": len(pages),
        "title": book.title,
        "section_count": len(book.sections),
    }


# ── Routes ──


@app.route("/")
def index():
    """Landing page with upload form and configuration options."""
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """Accept a DOCX or JSON file upload, generate PDF, redirect to preview."""
    if "file" not in request.files:
        return render_template("index.html", error="לא נבחר קובץ"), 400

    file = request.files["file"]
    if file.filename == "":
        return render_template("index.html", error="לא נבחר קובץ"), 400

    filename = file.filename.lower()
    job_id = str(uuid.uuid4())

    try:
        config = parse_config_from_form(request.form)

        if filename.endswith(".json"):
            raw = file.read().decode("utf-8")
            data = json.loads(raw)
            book = load_content_from_json_data(data)
        elif filename.endswith(".docx"):
            # Save to temp file for python-docx
            tmp_dir = tempfile.mkdtemp()
            tmp_path = os.path.join(tmp_dir, "upload.docx")
            file.save(tmp_path)
            try:
                book = load_content_from_docx(tmp_path)
            finally:
                os.unlink(tmp_path)
                os.rmdir(tmp_dir)
        else:
            return render_template(
                "index.html",
                error="סוג קובץ לא נתמך. אנא העלה קובץ JSON או DOCX."
            ), 400

        if not book.sections:
            return render_template(
                "index.html",
                error="הקובץ אינו מכיל פרקים. אנא בדוק את מבנה הקובץ."
            ), 400

        result = run_generation(book, config, job_id)
        jobs[job_id] = result

        return redirect(url_for("preview", job_id=job_id))

    except json.JSONDecodeError:
        return render_template(
            "index.html",
            error="שגיאה בקריאת קובץ JSON. אנא ודא שהקובץ תקין."
        ), 400
    except ImportError as e:
        return render_template(
            "index.html",
            error=f"חסרה חבילה נדרשת: {e}"
        ), 500
    except Exception as e:
        traceback.print_exc()
        return render_template(
            "index.html",
            error=f"שגיאה ביצירת הספר: {e}"
        ), 500


@app.route("/generate", methods=["POST"])
def generate():
    """Generate PDF from previously uploaded content or direct JSON POST."""
    job_id = str(uuid.uuid4())

    try:
        if request.is_json:
            data = request.get_json()
            config = parse_config_from_json(data)
            book = load_content_from_json_data(data.get("content", data))
        else:
            return jsonify({"error": "Content-Type must be application/json"}), 400

        if not book.sections:
            return jsonify({"error": "No sections found in content"}), 400

        result = run_generation(book, config, job_id)
        jobs[job_id] = result

        return jsonify({
            "job_id": job_id,
            "title": result["title"],
            "page_count": result["page_count"],
            "section_count": result["section_count"],
            "preview_url": url_for("preview", job_id=job_id, _external=True),
            "download_url": url_for("download", job_id=job_id, _external=True),
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/preview/<job_id>")
def preview(job_id):
    """Show HTML preview of generated pages."""
    job = jobs.get(job_id)
    if not job:
        # Check if the files exist on disk even if not in memory
        html_path = OUTPUT_DIR / job_id / "sefer.html"
        if not html_path.exists():
            abort(404)
        job = {
            "html_path": str(html_path),
            "pdf_path": str(OUTPUT_DIR / job_id / "sefer.pdf"),
            "title": "ספר",
            "page_count": 0,
            "section_count": 0,
        }

    return render_template(
        "preview.html",
        job_id=job_id,
        title=job["title"],
        page_count=job["page_count"],
        section_count=job["section_count"],
    )


@app.route("/preview/<job_id>/content")
def preview_content(job_id):
    """Serve the generated HTML for iframe embedding."""
    job = jobs.get(job_id)
    html_path = None

    if job:
        html_path = job.get("html_path")
    else:
        candidate = OUTPUT_DIR / job_id / "sefer.html"
        if candidate.exists():
            html_path = str(candidate)

    if not html_path or not Path(html_path).exists():
        abort(404)

    return send_file(html_path, mimetype="text/html")


@app.route("/download/<job_id>")
def download(job_id):
    """Download generated PDF."""
    job = jobs.get(job_id)
    pdf_path = None

    if job:
        pdf_path = job.get("pdf_path")
    else:
        candidate = OUTPUT_DIR / job_id / "sefer.pdf"
        if candidate.exists():
            pdf_path = str(candidate)

    if not pdf_path or not Path(pdf_path).exists():
        abort(404)

    title = job["title"] if job else "sefer"
    download_name = f"{title}.pdf" if title else "sefer.pdf"

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name,
    )


@app.route("/sample")
def sample():
    """Generate a PDF from the bundled sample content."""
    sample_path = Path(__file__).parent / "sample_content" / "shefa_shlomo.json"
    if not sample_path.exists():
        return render_template("index.html", error="קובץ לדוגמה לא נמצא"), 404

    job_id = str(uuid.uuid4())
    try:
        book = load_from_json(str(sample_path))
        config = PageConfig()
        result = run_generation(book, config, job_id)
        jobs[job_id] = result
        return redirect(url_for("preview", job_id=job_id))
    except Exception as e:
        traceback.print_exc()
        return render_template("index.html", error=f"שגיאה: {e}"), 500


@app.route("/api/generate", methods=["GET", "POST"])
def api_generate():
    """API endpoint: accept JSON content, return PDF file directly.

    GET  - pass ?file=<path-to-json> or ?content=<json-string>
    POST - pass JSON body with content (and optional config)

    Append ?format=json to receive metadata instead of the PDF binary.
    """
    try:
        if request.method == "GET":
            file_param = request.args.get("file")
            content_param = request.args.get("content")

            if file_param:
                book = load_from_json(file_param)
            elif content_param:
                data = json.loads(content_param)
                book = load_content_from_json_data(data)
            else:
                return jsonify({
                    "error": "יש לספק פרמטר content (JSON) או file (נתיב לקובץ)",
                }), 400
            config = PageConfig()

        else:  # POST
            if not request.is_json:
                return jsonify({
                    "error": "Content-Type חייב להיות application/json",
                }), 400
            data = request.get_json()
            config = parse_config_from_json(data)
            content = data.get("content", data)
            book = load_content_from_json_data(content)

        if not book.sections:
            return jsonify({"error": "לא נמצאו פרקים בתוכן"}), 400

        job_id = str(uuid.uuid4())
        result = run_generation(book, config, job_id)
        jobs[job_id] = result

        return_format = request.args.get("format", "pdf")

        if return_format == "json":
            return jsonify({
                "job_id": job_id,
                "title": result["title"],
                "page_count": result["page_count"],
                "section_count": result["section_count"],
                "preview_url": url_for("preview", job_id=job_id, _external=True),
                "download_url": url_for("download", job_id=job_id, _external=True),
            })

        title = result.get("title") or "sefer"
        return send_file(
            result["pdf_path"],
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{title}.pdf",
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/status/<job_id>")
def job_status(job_id):
    """Check job generation status."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "עבודה לא נמצאה"}), 404

    resp = {
        "job_id": job_id,
        "status": job.get("status", "done"),
        "title": job.get("title", ""),
        "page_count": job.get("page_count", 0),
        "section_count": job.get("section_count", 0),
        "error": job.get("error"),
        "preview_url": url_for("preview", job_id=job_id),
        "download_url": url_for("download", job_id=job_id),
    }
    return jsonify(resp)


# ── Error handlers ───────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if request.accept_mimetypes.best == "application/json":
        return jsonify({"error": "הדף לא נמצא"}), 404
    return render_template("index.html", error="404 — הדף המבוקש לא נמצא"), 404


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "הקובץ גדול מדי. הגבלה: 50MB"}), 413


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "שגיאת שרת פנימית"}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("  Sefer Engine - Web Interface")
    print("  http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=5000)

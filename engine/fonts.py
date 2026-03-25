"""Font management for Hebrew sefer typesetting."""

import subprocess


def find_font_path(pattern: str) -> str | None:
    """Find a font file path matching the given pattern using fc-match."""
    try:
        result = subprocess.run(
            ["fc-match", "--format=%{file}", pattern],
            capture_output=True, text=True, check=True,
        )
        path = result.stdout.strip()
        return path if path else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_font_faces_css() -> str:
    """Generate @font-face CSS declarations for Hebrew fonts."""
    serif_regular = find_font_path("Noto Serif Hebrew:style=Regular")
    serif_bold = find_font_path("Noto Serif Hebrew:style=Bold")

    if not serif_regular:
        serif_regular = find_font_path("Noto Serif Hebrew")
    if not serif_bold:
        serif_bold = serif_regular

    faces = []
    if serif_regular:
        faces.append(f"""@font-face {{
  font-family: 'SeferSerif';
  src: url('file://{serif_regular}') format('truetype');
  font-weight: normal;
  font-style: normal;
}}""")
    if serif_bold:
        faces.append(f"""@font-face {{
  font-family: 'SeferSerif';
  src: url('file://{serif_bold}') format('truetype');
  font-weight: bold;
  font-style: normal;
}}""")

    return "\n\n".join(faces)

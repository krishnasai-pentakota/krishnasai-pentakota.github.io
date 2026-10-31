"""Print the built resume page to an A4 PDF in static/docs/.

Run after `python build.py`, then commit the PDF with the content change:

    python tools/make_resume_pdf.py

The file name must match `resume_pdf` in content/profile.yaml.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DIST_RESUME = ROOT / "dist" / "resume.html"


def main() -> int:
    import re
    profile = (ROOT / "content" / "profile.yaml").read_text(encoding="utf-8")
    m = re.search(r"^resume_pdf:\s*(\S+)", profile, re.M)
    if not m:
        print("profile.yaml has no resume_pdf set; nothing to do.")
        return 0
    target = ROOT / "static" / m.group(1)
    if not DIST_RESUME.is_file():
        print("dist/resume.html is missing: run `python build.py` first.")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(DIST_RESUME.as_uri(), wait_until="load")
        page.emulate_media(media="print")
        page.pdf(path=str(target), format="A4", print_background=True,
                 margin={"top": "14mm", "bottom": "14mm", "left": "14mm", "right": "14mm"})
        browser.close()
    print(f"wrote {target.relative_to(ROOT)} ({target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

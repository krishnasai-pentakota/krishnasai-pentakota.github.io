"""Open every built page at phone, small-phone and desktop width and report:
  - pages wider than the screen (the page would wobble sideways on a phone)
  - JavaScript errors

Run after `python build.py`:
    pip install playwright
    playwright install chromium          # once
    python tools/check_layout.py         # serves dist/ itself on a free port

Why this exists: on 16 Oct 2026 the Factory and FDE Lab pages were 80 px too wide on
phones. A screen-reader label inside a shelf tile was absolutely positioned against the
whole rows area, so the shelf's scroll box didn't clip it. Fix: `position: relative` on
`.shelf-track`. The pytest checks read HTML; only a real browser can see layout bugs.
"""
import asyncio
import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.async_api import async_playwright

DIST = Path(__file__).resolve().parent.parent / "dist"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # no line per request
        pass


class QuietServer(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):  # the browser moving on mid-download is normal
        pass


def serve(folder: Path) -> str:
    handler = functools.partial(QuietHandler, directory=str(folder))
    server = QuietServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/"


async def main() -> int:
    if not (DIST / "index.html").exists():
        print("dist/ is empty: run `python build.py` first.")
        return 1
    base = serve(DIST)
    pages = sorted(p.relative_to(DIST).as_posix() for p in DIST.rglob("*.html") if "static" not in p.parts)
    problems: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        sizes = {
            "phone 390": {"viewport": {"width": 390, "height": 844}},
            "Pixel 7": pw.devices["Pixel 7"],
            "desktop 1440": {"viewport": {"width": 1440, "height": 900}},
        }
        for label, options in sizes.items():
            context = await browser.new_context(**options)
            await context.add_init_script("sessionStorage.setItem('introSeen', '1')")  # skip the intro
            page = await context.new_page()
            page.on("pageerror", lambda e, label=label: problems.append(f"{label}: JS error: {e}"))
            for path in pages:
                await page.goto(base + path, wait_until="load")
                width, layout, screen = await page.evaluate(
                    "[document.documentElement.scrollWidth, innerWidth, visualViewport.width]"
                )
                if width > screen + 1 or layout > screen + 1:
                    problems.append(f"{label}: {path} is {max(width, layout)} px wide on a {screen:.0f} px screen")
            await context.close()
        await browser.close()
    print(f"Checked {len(pages)} pages at {len(sizes)} widths.")
    for p in problems:
        print("  ✗", p)
    print("All clear." if not problems else f"{len(problems)} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

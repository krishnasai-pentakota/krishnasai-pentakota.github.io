"""Build the portfolio site.

    python build.py            validate content, then build into dist/
    python build.py --check    validate only (fast; run it while editing)
    python build.py --out X    build into folder X instead of dist/

Pipeline:  content/*.yaml -> load + validate (Pydantic) -> render (Jinja) -> dist/
           styles/site.css -> Tailwind (standalone binary, no Node) -> dist/static/css/site.css
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from time import perf_counter

from portfolio.loader import ContentError, load_site
from portfolio.render import render_site

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the portfolio site.")
    parser.add_argument("--check", action="store_true", help="validate content only")
    parser.add_argument("--out", type=Path, default=ROOT / "dist", help="output folder")
    args = parser.parse_args(argv)

    started = perf_counter()
    try:
        site = load_site(ROOT / "content", ROOT / "static")
    except ContentError as e:
        print(f"[FAIL] Content check found {len(e.problems)} problem(s):")
        for problem in e.problems:
            print(f"  - {problem}")
        print("Fix these and run again. Nothing was built.")
        return 1

    kinds = {}
    for p in site.projects:
        kinds[p.kind] = kinds.get(p.kind, 0) + 1
    summary = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
    print(f"[ok] Content valid: {len(site.projects)} projects ({summary}), "
          f"{len(site.verified_testimonials)} verified testimonials")
    if args.check:
        return 0

    written = render_site(site, ROOT / "templates", ROOT / "static", ROOT / "styles" / "site.css", args.out)
    ms = (perf_counter() - started) * 1000
    print(f"[ok] Built {len(written)} files into {args.out} in {ms:.0f} ms")
    print(f"     Open {args.out / 'index.html'} in your browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

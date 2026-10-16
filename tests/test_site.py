"""Integration tests: the real content loads, and the built site is clean.

These are the checks you'd otherwise do by eye before every deploy."""

import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import pytest

from build import main
from portfolio.loader import ContentError, load_site

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("site") / "dist"
    assert main(["--out", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def site():
    return load_site(ROOT / "content", ROOT / "static")


class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for key in ("href", "src"):
            if a.get(key) is not None:
                self.refs.append(a[key])


def parse(html: str) -> LinkCollector:
    c = LinkCollector()
    c.feed(html)
    return c


def all_pages(built: Path) -> list[Path]:
    """Every page we generate. The Studio demos are files we copy in as they are."""
    return sorted(p for p in built.rglob("*.html") if "demos" not in p.parts)


def read(built: Path, rel: str) -> str:
    return (built / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------- content

def test_real_content_is_valid(site):
    assert site.profile.name
    assert [r.id for r in site.roles] == ["factory", "hire", "client", "lab", "studio"]
    for r in site.roles:
        assert len([p for p in site.projects if p.featured and p.kind == r.id]) <= 1


def test_broken_content_reports_every_problem(tmp_path):
    (tmp_path / "projects").mkdir()
    (tmp_path / "profile.yaml").write_text("name: Only a name\n", encoding="utf-8")
    (tmp_path / "projects" / "bad.yaml").write_text("title: x\nkind: spaceship\n", encoding="utf-8")
    with pytest.raises(ContentError) as caught:
        load_site(tmp_path, ROOT / "static")
    problems = "\n".join(caught.value.problems)
    assert "profile.yaml" in problems and "roles.yaml" in problems and "projects/bad.yaml" in problems
    assert len(caught.value.problems) > 3  # all problems at once, not just the first


# ---------------------------------------------------------------- every page

def test_no_dead_links_on_any_page(built):
    """Crawl every page like a link checker: each relative link must land on a
    file in the build, and each #anchor on an element with that id."""
    parsed = {page: parse(page.read_text(encoding="utf-8")) for page in all_pages(built)}
    checked = 0
    for page, links in parsed.items():
        where = page.relative_to(built).as_posix()
        for ref in links.refs:
            assert ref not in ("", "#"), f"{where}: a button or link goes nowhere"
            if re.match(r"^(https://|mailto:|tel:|data:)", ref):
                continue
            assert not ref.startswith("/"), f"{where}: {ref} is root-absolute; breaks on GitHub Pages project sites"
            path, _, anchor = ref.partition("#")
            target = (page.parent / path).resolve() if path else page.resolve()
            assert target.is_file(), f"{where}: {ref} points at a file that isn't in the build"
            if anchor and target.suffix == ".html":
                ids = parsed[next(p for p in parsed if p.resolve() == target)].ids
                assert anchor in ids, f"{where}: {ref} has no element with id '{anchor}'"
            checked += 1
    assert checked > 200  # the crawl really ran across the pages


def test_no_python_leftovers_on_any_page(built):
    for page in all_pages(built):
        html = page.read_text(encoding="utf-8")
        for leftover in (">None<", "None</", "Undefined", "{{", "{%"):
            assert leftover not in html, f"{page.name} contains '{leftover}'"


def test_js_only_controls_ship_hidden(built):
    """A visitor without JavaScript never sees a button that does nothing."""
    for page in all_pages(built):
        html = page.read_text(encoding="utf-8")
        for tag in re.findall(r"<button[^>]*(?:data-quick-look=|data-print|data-copy-letter|data-replay-intro)[^>]*>", html):
            assert " hidden" in tag, f"{page.name}: JS-only control not hidden by default: {tag}"


def test_scripts_are_safe(built):
    for page in all_pages(built):
        html = page.read_text(encoding="utf-8")
        root = "../" * len(page.relative_to(built).parent.parts)
        assert f'<script src="{root}static/js/site.js" defer></script>' in html, page.name
        # Only the opening screen loads a module (the intro), and it can fail safely.
        if page.name != "index.html" or page.parent != built:
            assert 'type="module"' not in html, f"{page.name}: module scripts don't run from file://"
    for js in ("site.js", "intro.js"):
        code = (built / "static" / "js" / js).read_text(encoding="utf-8")
        assert not re.search(r"\.(innerHTML|outerHTML)\s*\+?=", code), f"{js}: build DOM with textContent, never innerHTML"


# ---------------------------------------------------------------- the opening screen

def test_picker_shows_the_five_roles(built, site):
    html = read(built, "index.html")
    tiles = re.findall(r'<a class="picker-tile" href="([a-z]+\.html)"', html)
    assert tiles == [r.page for r in site.roles]
    for r in site.roles:
        assert (built / r.page).is_file()


def test_intro_has_every_way_out(built):
    """The intro must never trap anyone: reduced motion skips it, it plays once per
    session, a timer rescues a page whose script never starts, and there's a Skip button."""
    html = read(built, "index.html")
    assert "prefers-reduced-motion: reduce" in html and "sessionStorage" in html
    assert re.search(r"setTimeout\(function \(\) \{\s*if \(!d\.classList\.contains\(\"intro-running\"\)\)", html)
    assert re.search(r'<button type="button" class="intro-skip"[^>]*>Skip intro</button>', html)
    intro = (built / "static" / "js" / "intro.js").read_text(encoding="utf-8")
    assert ".catch(" in intro and "finish()" in intro          # any failure hands the page back
    assert "renderer.dispose()" in intro                       # GPU memory is released afterwards


# ---------------------------------------------------------------- role pages

def test_role_pages_show_every_project(built, site):
    for r in site.roles:
        if r.id == "hire":
            continue
        html = read(built, r.page)
        for p in site.in_role(r.id):
            assert f'id="{p.id}"' in html, f"{r.page} is missing {p.id}"
        bill = site.billboard(r.id)
        if bill:
            assert f">{bill.title}</h1>" in unescape(html), f"{r.page}: banner isn't {bill.id}"


def test_quick_look_has_a_template_for_every_trigger(built, site):
    for r in site.roles:
        html = read(built, r.page)
        triggers = set(re.findall(r'data-quick-look="([a-z0-9-]+)"', html))
        templates = set(re.findall(r'<template id="ql-([a-z0-9-]+)">', html))
        assert triggers <= templates, f"{r.page}: quick look without a template: {triggers - templates}"


def test_a_page_for_each_project_that_earns_one(built, site):
    expected = {p.page for p in site.projects if p.has_page}
    actual = {p.relative_to(built).as_posix() for p in (built / "work").glob("*.html")}
    assert actual == expected


def test_public_code_and_dashboards_are_one_click_away(built, site):
    for p in site.projects:
        if p.has_page:
            html = read(built, p.page)
            for link in (p.live_link, p.code_link):
                if link:
                    assert f'href="{link.url}"' in html, f"{p.page} doesn't link {link.url}"


# ---------------------------------------------------------------- privacy decisions

def test_factory_pages_dont_name_the_employer(built, site):
    """Decided 16 Oct 2026: the Factory pages say 'a ribbon manufacturer'.
    The employer's name stays on the resume and LinkedIn only."""
    pages = ["factory.html"] + [p.page for p in site.projects if p.kind == "factory" and p.has_page]
    for rel in pages:
        text = re.sub(r"<[^>]+>", " ", read(built, rel))
        for name in ("MISO", "Miso", "Ribest", "YAMA", "Yama"):
            assert name not in text, f"{rel} names the employer ('{name}')"


def test_studio_demo_is_anonymised(built):
    demo = read(built, "static/demos/festival-slideshow.html")
    assert "Demo · sample names and amounts" in demo
    visible = re.sub(r"data:[a-z/+0-9.-]+;base64,[A-Za-z0-9+/=]+", "", demo)
    for name in ("MISO", "Ribest", "YAMA", "JCC"):
        assert name not in visible, f"the demo still shows '{name}'"


# ---------------------------------------------------------------- Hire me

def test_resume_page_is_complete_and_printable(built, site):
    html = read(built, "resume.html")
    assert site.profile.name in html
    assert "[" not in re.sub(r"<[^>]+>", "", html), "a [placeholder] reached the resume"
    assert re.search(r"<button[^>]*data-print[^>]*hidden", html)
    css = read(built, "static/css/site.css")
    assert "@page" in css and "size:A4" in css.replace(" ", "")


def test_cover_letter_fills_in_locally(built):
    html = read(built, "cover-letter.html")
    assert re.search(r"<form[^>]*data-letter-form[^>]*hidden", html)   # appears only when the script can fill it
    assert "<form" in html and "action=" not in html                   # nothing is ever submitted anywhere
    assert {"role", "company", "why"} <= set(re.findall(r'data-fill="([a-z]+)"', html))


def test_hire_page_links_the_profiles(built, site):
    html = read(built, "hire.html")
    if site.profile.email:
        assert f'href="mailto:{site.profile.email}"' in html
    if site.profile.github:
        assert f'href="{site.profile.github}"' in html


# ---------------------------------------------------------------- build hygiene

def test_tailwind_compiled_not_shipped_raw(built):
    css = read(built, "static/css/site.css")
    assert '@import "tailwindcss"' not in css, "raw Tailwind source shipped instead of compiled CSS"
    assert "--color-lime" in css  # design tokens made it through
    assert "max-w-" in css  # a utility used in the templates was generated
    assert len(css) < 60_000, "CSS unexpectedly large; is Tailwind scanning too much?"


def test_noindex_follows_profile(built, site):
    for page in all_pages(built):
        assert ('name="robots"' in page.read_text(encoding="utf-8")) == site.profile.noindex, page.name


def test_rebuild_is_clean(tmp_path):
    out = tmp_path / "dist"
    assert main(["--out", str(out)]) == 0
    (out / "stale.txt").write_text("left over from an old build", encoding="utf-8")
    assert main(["--out", str(out)]) == 0
    assert not (out / "stale.txt").exists()


def test_refuses_to_wipe_a_folder_it_did_not_create(tmp_path):
    precious = tmp_path / "my-work"
    precious.mkdir()
    (precious / "notes.txt").write_text("important", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--out", str(precious)])
    assert (precious / "notes.txt").exists()

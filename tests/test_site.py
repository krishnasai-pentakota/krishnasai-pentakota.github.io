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
            path = path.split("?", 1)[0]  # site.css?v=… : the ?v= part is a version stamp, not a file
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
        for tag in re.findall(r"<button[^>]*(?:data-quick-look=|data-print|data-copy-letter)[^>]*>", html):
            assert " hidden" in tag, f"{page.name}: JS-only control not hidden by default: {tag}"


def test_scripts_are_safe(built):
    for page in all_pages(built):
        html = page.read_text(encoding="utf-8")
        root = "../" * len(page.relative_to(built).parent.parts)
        assert re.search(rf'<script src="{re.escape(root)}static/js/site\.js\?v=[0-9a-f]{{10}}" defer></script>', html), page.name
        assert 'type="module"' not in html, f"{page.name}: module scripts don't run from file://"
    for js in ("site.js", "opening.js"):
        code = (built / "static" / "js" / js).read_text(encoding="utf-8")
        assert not re.search(r"\.(innerHTML|outerHTML)\s*\+?=", code), f"{js}: build DOM with textContent, never innerHTML"


# ---------------------------------------------------------------- the opening screen

def test_picker_shows_the_five_roles(built, site):
    html = read(built, "index.html")
    tiles = re.findall(r'<a class="picker-tile" href="([a-z]+\.html)"', html)
    assert tiles == [r.page for r in site.roles]
    for r in site.roles:
        assert (built / r.page).is_file()


def test_no_ribbon_intro_or_3d_libraries(built):
    """Decision, 16 Oct: the ribbon intro is gone for good, with Three.js and GSAP."""
    html = read(built, "index.html")
    for leftover in ("gsap", "three", "Replay intro", "data-intro-canvas"):
        assert leftover not in html, f"index.html still has the old ribbon intro: '{leftover}'"
    for gone in ("js/intro.js", "vendor/three-lite.module.js", "vendor/gsap.min.js"):
        assert not (built / "static" / gone).exists(), f"{gone} should no longer ship"


def test_intro_film_has_every_way_out(built):
    """The film must never trap anyone or waste their data."""
    html = read(built, "index.html")
    # Decided before paint: not with reduced motion, once per session, not on Data Saver,
    # and a 3 s rescue if the script never starts.
    assert "prefers-reduced-motion: reduce" in html and 'sessionStorage.getItem("ks-intro")' in html
    assert "saveData" in html
    assert re.search(r'if \(!d\.classList\.contains\("intro-playing"\)\) d\.classList\.remove\("intro-pending"\);\s*\}, 3000\)', html)
    # Plays muted and inline (the only way browsers allow autoplay), downloads nothing unless it plays.
    video = re.search(r"<video[^>]*data-intro-video[^>]*>", html).group(0)
    for attr in ("muted", "playsinline", 'preload="none"'):
        assert attr in video, f"intro video needs {attr}"
    assert '<button type="button" class="intro-button" data-intro-skip>Skip intro</button>' in html
    js = (built / "static" / "js" / "opening.js").read_text(encoding="utf-8")
    assert "playing.catch(finish)" in js            # autoplay blocked -> straight to the roles
    assert '"ended", finish' in js                  # film over -> roles
    assert "addEventListener(\"error\", finish)" in js  # no playable format -> roles
    assert "if (!started) finish(); }, 4000)" in js  # slow connection -> roles
    assert 'e.key === "Escape"' in js


def test_intro_film_files_are_small_and_clean(built):
    media = built / "static" / "media"
    for name, limit_kb in (("intro.webm", 1500), ("intro.mp4", 1800), ("intro-poster.webp", 80)):
        f = media / name
        assert f.is_file(), f"missing {name}"
        assert f.stat().st_size < limit_kb * 1024, f"{name} is {f.stat().st_size // 1024} KB, over {limit_kb} KB"


def test_role_tiles_are_flat_with_one_icon_and_credited_photos(built, site):
    """Decision, 16 Oct: no 3D cubes. Each tile is a photo with its icon shown once."""
    html = read(built, "index.html")
    assert "cube" not in html, "the 3D cubes are gone; no cube markup should remain"
    tiles = re.findall(r'<a class="picker-tile".*?</a>', html, flags=re.S)
    assert len(tiles) == 5
    for r, tile in zip(site.roles, tiles):
        assert tile.count("<svg") == 1, f"{r.id}: its icon must appear exactly once"
        assert r.photos, f"{r.id} has no photo"
        for ph in r.photos:
            assert f'static/{ph.src}"' in tile and (built / "static" / ph.src).is_file(), ph.src
        assert ("tile-photo--fade" in tile) == (len(r.photos) == 2), r.id
    assert len(site.role("client").photos) == 2  # a hospital and a restaurant, cross-fading
    credits = unescape(re.search(r'<p class="picker-credits">(.*?)</p>', html, flags=re.S).group(1))
    assert "made with AI" in credits  # the intro film says what it is
    for ph in site.role_photos:
        assert ph.credit in credits and str(ph.link) in credits, f"{ph.src}: photographer not credited"


def test_assets_carry_one_version_stamp(built):
    """Every page asks for the same fingerprinted CSS and JS, so a new page can never
    be paired with an old cached stylesheet (that once showed each icon three times)."""
    stamps = set()
    for page in all_pages(built):
        html = page.read_text(encoding="utf-8")
        found = re.findall(r'static/(?:css/site\.css|js/site\.js)\?v=([0-9a-f]{10})"', html)
        assert len(found) == 2, f"{page.name}: CSS and JS links need ?v= stamps"
        stamps.update(found)
    assert len(stamps) == 1, f"pages disagree on the asset version: {stamps}"


def test_version_stamp_changes_when_styles_change(tmp_path):
    from portfolio.render import asset_version
    css = tmp_path / "site.css"
    css.write_text("a { color: red }")
    before = asset_version(css)
    css.write_text("a { color: blue }")
    assert asset_version(css) != before


def test_star_pointer_everywhere(built):
    css = (built / "static" / "css" / "site.css").read_text(encoding="utf-8")
    for name in ("cursor-star.png", "cursor-star-link.png"):
        assert f"../img/{name}" in css, f"site.css doesn't use {name}"
        assert (built / "static" / "img" / name).is_file(), f"missing static/img/{name}"
    assert "cursor:pointer" not in css.replace(" ", ""), "every clickable thing should show the star, not the plain hand"
    js = (built / "static" / "js" / "site.js").read_text(encoding="utf-8")
    assert "reduceMotion.matches) return;" in js[js.index("function initStarTrail"):]  # no trail for reduced motion


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

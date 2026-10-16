"""Unit tests for the content rules. Each test is one rule from models.py,
proven in both directions: good input passes, bad input is refused."""

from datetime import date

import pytest
from pydantic import ValidationError

from portfolio.models import CaseStudy, Job, Link, Media, Profile, Project, Resume, Role, Shot, Site, Testimonial

ROLE_IDS = ["factory", "hire", "client", "lab", "studio"]


def project(**overrides):
    """A minimal valid project; each test changes one thing."""
    data = {
        "id": "demo-project",
        "title": "Demo project",
        "kind": "factory",
        "status": "prototype",
        "summary": "A small project used only by the tests.",
    }
    data.update(overrides)
    return Project.model_validate(data)


def profile(**overrides):
    data = {
        "name": "Test Person",
        "short_name": "Test",
        "monogram": "TP",
        "headline": "Engineer",
        "tagline": "Builds things.",
        "summary": "A person used by the tests.",
    }
    data.update(overrides)
    return Profile.model_validate(data)


def roles(ids=ROLE_IDS):
    return [Role(id=r, name=r.title(), tagline="A role used by the tests", intro="An intro used only by the tests.",
                 icon="loom", color="#C6F36B") for r in ids]


def site(projects, **kw):
    return Site(profile=profile(), roles=roles(), projects=projects, **kw)


# ---------------------------------------------------------------- one project

def test_minimal_project_is_valid():
    assert project().status.label == "Prototype"


@pytest.mark.parametrize("bad", ["#", "", "/relative/path", "http://not-https.com", "javascript:alert(1)"])
def test_links_must_be_real_https(bad):
    with pytest.raises(ValidationError):
        Link(label="Repo", url=bad)


def test_unknown_field_is_a_typo_error():
    with pytest.raises(ValidationError, match="sumary"):
        project(sumary="typo")


def test_file_name_must_be_a_slug():
    with pytest.raises(ValidationError, match="lowercase-with-dashes"):
        project(id="My Project")


def test_kind_must_be_a_role_with_projects():
    for kind in ("factory", "client", "lab", "studio"):
        assert project(kind=kind).kind == kind
    for bad in ("hire", "engineering", "creative"):  # hire is the career page; old names are gone
        with pytest.raises(ValidationError):
            project(kind=bad)


def test_concept_cannot_show_results():
    metric = {"value": "90%", "label": "less manual work", "evidence": "Measured after launch"}
    with pytest.raises(ValidationError, match="cannot show results"):
        project(status="concept", metrics=[metric])


def test_concept_can_state_a_goal():
    assert project(status="concept", goal="Cut manual work by 90%").goal


def test_metric_needs_evidence():
    with pytest.raises(ValidationError):
        project(metrics=[{"value": "96", "label": "tests", "evidence": ""}])


def test_shipped_work_needs_link_or_proof_note():
    with pytest.raises(ValidationError, match="public link or a proof_note"):
        project(status="implemented")
    assert project(status="implemented", proof_note="Runs on the office network.")
    assert project(status="implemented", links=[{"label": "Repo", "url": "https://github.com/x/y"}])


@pytest.mark.parametrize("kind", ["client", "studio"])
def test_delivered_client_work_needs_my_role(kind):
    with pytest.raises(ValidationError, match="my_role"):
        project(kind=kind, status="delivered", proof_note="Handed over.")
    assert project(kind=kind, status="delivered", proof_note="Handed over.", my_role="Design and build")


def test_also_in_cannot_repeat_its_own_role():
    with pytest.raises(ValidationError, match="repeats its own role"):
        project(kind="factory", also_in=["factory"])
    assert project(kind="factory", also_in=["lab"]).roles == ["factory", "lab"]


def test_media_and_screenshots_need_alt_and_relative_paths():
    with pytest.raises(ValidationError, match="alt text"):
        Media(poster="img/poster.jpg")
    with pytest.raises(ValidationError, match="inside static"):
        Media(poster="/img/poster.jpg", alt="Poster")
    with pytest.raises(ValidationError):
        Shot(src="img/a.webp", alt="short")            # alt text must say what the screen shows
    with pytest.raises(ValidationError, match="inside static"):
        Shot(src="../secret.png", alt="A screenshot of the dashboard")
    for field in ("cover", "demo"):
        with pytest.raises(ValidationError, match="inside static"):
            project(**{field: "https://example.com/x.png"})


def test_highlights_are_short_and_few():
    assert len(project(highlights=["Return notes", "Wastage notes with reason codes"]).highlights) == 2
    with pytest.raises(ValidationError):
        project(highlights=["x" * 111])  # one bullet too long
    with pytest.raises(ValidationError):
        project(highlights=[f"point {i}" for i in range(7)])  # too many bullets


def test_a_page_only_when_there_is_more_to_say():
    assert project().page is None  # summary only: the tile says it all
    assert project(highlights=["Return notes", "Wastage notes"]).page == "work/demo-project.html"
    assert project(screenshots=[{"src": "img/a.webp", "alt": "The overview screen"}]).has_page
    assert project(status="concept").has_more is False
    assert project(my_role="Design and build").has_more is True


def test_links_by_type_and_the_tile_picture():
    p = project(links=[{"label": "Repo", "url": "https://github.com/x/y", "type": "code"},
                       {"label": "Open it", "url": "https://x.github.io/y/", "type": "live"}],
                screenshots=[{"src": "img/a.webp", "alt": "The overview screen"}])
    assert p.code_link.label == "Repo" and p.live_link.label == "Open it"
    assert p.thumb == "img/a.webp"                         # no cover: the first screenshot
    assert project(cover="img/c.webp", screenshots=p.screenshots).thumb == "img/c.webp"
    assert project().live_link is None and project().thumb is None


def test_new_this_week():
    p = project(updated=date(2026, 10, 15))
    assert p.is_new(date(2026, 10, 16)) and not p.is_new(date(2026, 11, 1))
    assert not project().is_new(date(2026, 10, 16))


def test_flow_needs_at_least_three_steps():
    with pytest.raises(ValidationError, match="at least 3"):
        project(flow=["Excel", "Dashboard"])
    assert len(project(flow=["Excel", "Validate", "Dashboard"]).flow) == 3


# ---------------------------------------------------------------- writing and people

def test_verified_testimonial_needs_a_source():
    with pytest.raises(ValidationError, match="source"):
        Testimonial(id="t1", quote="Great work, very reliable.", name="A Client", verified=True)


def test_profile_links_point_at_the_right_sites():
    with pytest.raises(ValidationError, match="github.com"):
        profile(github="https://gitlab.com/someone")
    with pytest.raises(ValidationError, match="email"):
        profile(email="not-an-email")
    assert profile(github="https://github.com/someone").github.host == "github.com"


@pytest.mark.parametrize("leftover", ["[one line on what you built]", "[PHONE]", "TODO: add numbers", "Results TBD"])
def test_prose_refuses_placeholders(leftover):
    with pytest.raises(ValidationError, match="placeholder"):
        CaseStudy(problem="A real problem that needs at least forty characters here.", steps=["Did one thing", leftover])
    with pytest.raises(ValidationError, match="placeholder"):
        Job(role="Analyst", org="TCS", start="Feb 2022", bullets=[leftover])


def test_job_dates_read_like_a_resume():
    assert Job(role="Analyst", org="TCS", start="Feb 2022", end="Dec 2023").end == "Dec 2023"
    for bad in ("2022-02", "February 2022", "feb 2022"):
        with pytest.raises(ValidationError, match="Aug 2026"):
            Job(role="Analyst", org="TCS", start=bad)


def test_phone_shape():
    assert profile(phone="+91 98765 43210").phone
    with pytest.raises(ValidationError, match="digits"):
        profile(phone="call me")


# ---------------------------------------------------------------- the whole site

def test_roles_must_be_exactly_the_five():
    with pytest.raises(ValidationError, match="five roles"):
        Site(profile=profile(), roles=roles(ROLE_IDS[:4]), projects=[])
    with pytest.raises(ValidationError):
        Role(id="sales", name="Sales", tagline="Not one of the five", intro="An intro used only by the tests.",
             icon="loom", color="#C6F36B")
    with pytest.raises(ValidationError):
        Role.model_validate({**roles()[0].model_dump(), "color": "lime"})   # colours are hex, e.g. #C6F36B
    assert [r.page for r in site([]).roles] == [f"{r}.html" for r in ROLE_IDS]


def test_one_banner_per_role():
    with pytest.raises(ValidationError, match="one project per role gets the banner"):
        site([project(id="a", featured=True), project(id="b", featured=True)])
    assert site([project(id="a", featured=True), project(id="b", kind="client", featured=True)])


def test_banner_falls_back_sensibly():
    s = site([project(id="a", order=1), project(id="b", order=2, cover="img/b.webp")])
    assert s.billboard("factory").id == "b"                # nothing featured: the first with a picture
    s = site([project(id="a", order=1), project(id="b", order=2, featured=True)])
    assert s.billboard("factory").id == "b"                # featured always wins
    assert s.billboard("studio") is None                   # an empty role has no banner


def test_role_rows_include_also_in_projects():
    s = site([project(id="a", order=2), project(id="b", order=1, also_in=["lab"]), project(id="c", kind="lab")])
    assert [p.id for p in s.in_role("factory")] == ["b", "a"]
    assert [p.id for p in s.in_role("lab")] == ["b", "c"]
    assert s.billboard("lab").id == "c"                    # banners come from a role's own projects


def test_recently_updated_and_last_updated():
    s = site([project(id="a", updated=date(2026, 10, 1)), project(id="b", updated=date(2026, 10, 15)), project(id="c")])
    assert [p.id for p in s.recently_updated()] == ["b", "a"]
    assert s.last_updated == date(2026, 10, 15)


def test_testimonial_must_reference_a_real_project():
    t = Testimonial(id="t1", quote="Great work, very reliable.", name="A Client", project="ghost")
    with pytest.raises(ValidationError, match="unknown project"):
        site([project()], testimonials=[t])


def test_resume_projects_must_exist():
    resume = Resume(summary="x" * 90, experience=[Job(role="Analyst", org="TCS", start="Feb 2022")], projects=["ghost"])
    with pytest.raises(ValidationError, match="unknown project 'ghost'"):
        site([project()], resume=resume)

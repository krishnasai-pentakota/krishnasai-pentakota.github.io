"""Content models: the contract every content file must meet before the site is built.

Read this file the way you read a PostgreSQL schema with CHECK constraints and
foreign keys. A bad row (here: a bad YAML file) is rejected at the door, with a
reason, before anything downstream (templates, HTML) ever sees it.

  - Field types and Field(...) limits  -> column types + CHECK constraints
  - @field_validator                   -> a CHECK on one column
  - @model_validator on Project        -> a CHECK across columns of one row
  - @model_validator on Site           -> table-level rules (unique ids, foreign keys)
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)
PHONE = re.compile(r"^\+?[\d\s-]{8,18}$")
MONTH_YEAR = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}$")
# Template leftovers: "[PHONE]", "[one line on what you built]", "TODO", "TBD".
PLACEHOLDER = re.compile(r"\[[^\]]{2,}\]|\b(TODO|TBD|XXX)\b")


class Strict(BaseModel):
    """Base for every content model.

    extra="forbid" turns a typo like `sumary:` into an error instead of a field
    that silently disappears. str_strip_whitespace removes stray spaces that
    YAML folding sometimes leaves behind.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _strings(value):
    """Yield every string inside a value, however deeply nested."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


class Prose(Strict):
    """Base for long-form writing (case studies, the resume).

    One validator here covers every text field in every subclass: it walks the
    whole model and refuses template leftovers. Write the rule once, inherit it
    everywhere — the same idea as a CHECK constraint on a domain type."""

    @model_validator(mode="after")
    def no_placeholders(self):
        for text in _strings(self.model_dump(mode="json")):
            hit = PLACEHOLDER.search(text)
            if hit:
                raise ValueError(f"placeholder left in the text: '{hit.group(0)}'. Fill it in or delete the line")
        return self


def _https_only(url: HttpUrl | None) -> HttpUrl | None:
    if url is not None and url.scheme != "https":
        raise ValueError("use an https:// link")
    return url


def _relative_asset(path: str | None) -> str | None:
    """Asset paths are relative to static/ so the site also works under
    username.github.io/<repo>/ (a root-absolute '/img/x.jpg' would break there)."""
    if path is None:
        return None
    if path.startswith(("/", "\\")) or "://" in path or ".." in path.split("/"):
        raise ValueError("must be a path inside static/, like 'img/poster.jpg'")
    return path


# ---------------------------------------------------------------- small parts


class Status(str, Enum):
    IMPLEMENTED = "implemented"  # built and in real use
    DELIVERED = "delivered"  # handed over to a client
    IN_PROGRESS = "in_progress"  # being built now
    PROTOTYPE = "prototype"  # works, not yet in real use
    CONCEPT = "concept"  # designed or planned; nothing to show yet

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").capitalize()

    @property
    def shipped(self) -> bool:
        return self in (Status.IMPLEMENTED, Status.DELIVERED)

    @property
    def can_have_results(self) -> bool:
        return self in (Status.IMPLEMENTED, Status.DELIVERED, Status.PROTOTYPE)


class Link(Strict):
    label: str = Field(min_length=1, max_length=40)
    url: HttpUrl  # rejects "", "#" and relative paths by itself
    # What the link opens. "live" becomes the big "Open live dashboard" button.
    type: Literal["live", "code", "video", "doc"] = "doc"

    _https = field_validator("url")(_https_only)


class Shot(Strict):
    """A screenshot: the KPI snapshot people see before they click anything."""

    src: str  # image under static/, e.g. img/sales/overview.webp
    alt: str = Field(min_length=10)  # what the screenshot shows, for screen readers
    caption: str | None = Field(default=None, max_length=90)

    _path = field_validator("src")(_relative_asset)


class Metric(Strict):
    """A number shown on the site. `evidence` says where the number can be
    checked. It is never rendered; it is there so every number has a source
    you can open in an interview."""

    value: str = Field(min_length=1, max_length=16)
    label: str = Field(min_length=3, max_length=60)
    evidence: str = Field(min_length=10)


class Media(Strict):
    poster: str | None = None  # image under static/, e.g. img/sri-veda.jpg
    preview: str | None = None  # short muted clip under static/
    video_url: HttpUrl | None = None  # full video on YouTube or Vimeo
    duration: str | None = Field(default=None, pattern=r"^\d{1,2}:\d{2}$")
    alt: str | None = None

    _paths = field_validator("poster", "preview")(_relative_asset)
    _https = field_validator("video_url")(_https_only)

    @model_validator(mode="after")
    def poster_needs_alt(self) -> Media:
        if self.poster and not self.alt:
            raise ValueError("a poster image needs alt text describing it")
        return self


# ---------------------------------------------------------------- one file each


# The five roles on the opening screen. "hire" is the career page and holds no
# projects; every project belongs to one of the other four.
RoleId = Literal["factory", "hire", "client", "lab", "studio"]
Kind = Literal["factory", "client", "lab", "studio"]
Icon = Literal["loom", "badge", "briefcase", "flask", "clapper"]

# A short bullet: one concrete thing the work does. Annotated attaches the
# limit to each item, so a list of 4 short bullets passes and one long one fails.
Highlight = Annotated[str, Field(min_length=3, max_length=110)]
FlowStep = Annotated[str, Field(min_length=3, max_length=48)]


class Decision(Prose):
    choice: str = Field(min_length=3, max_length=80)  # what you chose
    why: str = Field(min_length=20, max_length=400)  # the reason, in one or two sentences


class CaseStudy(Prose):
    """The long version of a project, shown on its own page."""

    problem: str = Field(min_length=40)
    steps: list[str] = Field(min_length=2, max_length=8)  # what you did, in order
    decisions: list[Decision] = Field(default=[], max_length=6)
    outcome: str | None = None
    next: str | None = None


class Project(Strict):
    id: str  # taken from the file name by the loader
    title: str = Field(min_length=3, max_length=80)
    kind: Kind  # which role it lives under
    also_in: list[Kind] = []  # extra roles it also appears in (like one title in two Netflix rows)
    status: Status
    summary: str = Field(min_length=20, max_length=300)
    why: str | None = Field(default=None, min_length=20, max_length=260)  # why it matters, in one breath
    my_role: str | None = None  # what YOU did
    client: str | None = None
    period: str | None = None
    updated: date | None = None  # YAML reads 2026-10-16 as a real date
    goal: str | None = None  # a target, shown as "Goal:", never as a result
    highlights: list[Highlight] = Field(default=[], max_length=6)
    stack: list[str] = []
    tags: list[str] = []
    metrics: list[Metric] = []
    cover: str | None = None  # 16:9 image under static/ for tiles and the banner
    screenshots: list[Shot] = Field(default=[], max_length=8)
    links: list[Link] = []
    demo: str | None = None  # a live demo page under static/, e.g. demos/festival-slideshow.html
    proof_note: str | None = None  # why there is no public link
    media: Media | None = None
    flow: list[FlowStep] = Field(default=[], max_length=7)  # how data moves, drawn as a pipeline
    case_study: CaseStudy | None = None
    featured: bool = False  # the big banner at the top of its role page
    order: int = 100  # lower shows first

    _assets = field_validator("demo", "cover")(_relative_asset)

    @property
    def has_page(self) -> bool:
        """A project earns its own page only when there's more to say than the
        card already says. Thin pages look worse than no page."""
        return bool(self.case_study or self.highlights or self.metrics or self.screenshots)

    @property
    def page(self) -> str | None:
        return f"work/{self.id}.html" if self.has_page else None

    @property
    def has_more(self) -> bool:
        """Is there anything for the quick-look panel beyond the card itself?"""
        return bool(self.highlights or self.metrics or self.my_role or self.goal or self.why
                    or self.links or self.proof_note or self.has_page)

    @property
    def roles(self) -> list[str]:
        return [self.kind, *[k for k in self.also_in if k != self.kind]]

    @property
    def live_link(self) -> Link | None:
        return next((l for l in self.links if l.type == "live"), None)

    @property
    def code_link(self) -> Link | None:
        return next((l for l in self.links if l.type == "code"), None)

    @property
    def thumb(self) -> str | None:
        """The picture used on tiles and banners: the cover, else the first screenshot."""
        return self.cover or (self.screenshots[0].src if self.screenshots else None)

    def is_new(self, today: date, days: int = 7) -> bool:
        return self.updated is not None and (today - self.updated).days <= days

    @field_validator("id")
    @classmethod
    def id_is_slug(cls, v: str) -> str:
        if not SLUG.match(v):
            raise ValueError("file name must be lowercase-with-dashes, e.g. weaving-audit.yaml")
        return v

    @model_validator(mode="after")
    def honest_status(self) -> Project:
        # Results only exist for work that exists.
        if self.metrics and not self.status.can_have_results:
            raise ValueError(
                f"status '{self.status.value}' cannot show results (metrics); "
                "use 'goal' for a target, or change the status"
            )
        # Shipped work must be checkable, or say why it can't be.
        if self.status.shipped and not (self.links or self.proof_note):
            raise ValueError("shipped work needs a public link or a proof_note saying where it runs")
        # Client and studio work must say what you did.
        if self.kind in ("client", "studio") and self.status.shipped and not self.my_role:
            raise ValueError("delivered client work needs 'my_role' (what you did)")
        if self.kind in self.also_in:
            raise ValueError(f"also_in repeats its own role '{self.kind}'")
        # A pipeline needs at least a start, a middle and an end.
        if self.flow and len(self.flow) < 3:
            raise ValueError("a flow needs at least 3 steps, or leave it out")
        return self


class Testimonial(Strict):
    id: str
    quote: str = Field(min_length=20, max_length=400)
    name: str
    role: str | None = None
    project: str | None = None  # a project id
    verified: bool = False
    source: str | None = None  # e.g. "WhatsApp message, 2 Nov 2026, screenshot saved"
    source_url: HttpUrl | None = None

    @model_validator(mode="after")
    def verified_needs_source(self) -> Testimonial:
        if self.verified and not (self.source or self.source_url):
            raise ValueError("a verified testimonial needs a 'source'")
        return self


class Profile(Strict):
    name: str
    short_name: str
    monogram: str = Field(min_length=1, max_length=3)
    headline: str
    tagline: str
    summary: str
    location: str | None = None
    availability: str | None = None
    email: str | None = None
    phone: str | None = None  # shown on the resume page only
    github: HttpUrl | None = None
    linkedin: HttpUrl | None = None
    resume_pdf: str | None = None
    site_url: HttpUrl | None = None  # set after the first deploy (used for share previews)
    noindex: bool = True  # True keeps the site out of Google search results

    _paths = field_validator("resume_pdf")(_relative_asset)
    _https = field_validator("github", "linkedin", "site_url")(_https_only)

    @field_validator("email")
    @classmethod
    def email_shape(cls, v: str | None) -> str | None:
        if v is not None and not EMAIL.match(v):
            raise ValueError("doesn't look like an email address")
        return v

    @field_validator("phone")
    @classmethod
    def phone_shape(cls, v: str | None) -> str | None:
        if v is not None and not PHONE.match(v):
            raise ValueError("use digits, spaces and an optional leading +, e.g. +91 98765 43210")
        return v

    @field_validator("github")
    @classmethod
    def on_github(cls, v: HttpUrl | None) -> HttpUrl | None:
        if v is not None and v.host not in ("github.com", "www.github.com"):
            raise ValueError("must be a github.com link")
        return v

    @field_validator("linkedin")
    @classmethod
    def on_linkedin(cls, v: HttpUrl | None) -> HttpUrl | None:
        if v is not None and not (v.host or "").endswith("linkedin.com"):
            raise ValueError("must be a linkedin.com link")
        return v


# ---------------------------------------------------------------- resume


class Job(Prose):
    role: str
    org: str
    place: str | None = None
    start: str
    end: str = "Present"
    bullets: list[str] = Field(default=[], max_length=8)

    @field_validator("start", "end")
    @classmethod
    def month_year(cls, v: str) -> str:
        if v != "Present" and not MONTH_YEAR.match(v):
            raise ValueError("write dates like 'Aug 2026' (or 'Present' for the end date)")
        return v


class Education(Prose):
    degree: str
    school: str
    years: str = Field(pattern=r"^\d{4}( – \d{4})?$")  # "2017 – 2021" (en dash)


class SkillGroup(Prose):
    group: str
    items: list[str] = Field(min_length=1)


class Resume(Prose):
    summary: str = Field(min_length=80, max_length=900)
    experience: list[Job] = Field(min_length=1)
    skills: list[SkillGroup] = []
    education: list[Education] = []
    projects: list[str] = []  # project ids, shown as "Selected projects"


# ---------------------------------------------------------------- the five roles


class Role(Strict):
    """One tile on the opening screen, and the page behind it."""

    id: RoleId
    name: str = Field(min_length=2, max_length=16)  # short: it sits under a tile
    tagline: str = Field(min_length=10, max_length=60)
    intro: str = Field(min_length=20, max_length=320)
    icon: Icon
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    # The photo on the front of the role's cube, and who took it.
    photo: str | None = None  # image under static/, e.g. img/roles/factory.webp
    photo_credit: str | None = Field(default=None, max_length=40)  # photographer's name
    photo_link: HttpUrl | None = None  # the photo's page, e.g. on Unsplash

    _path = field_validator("photo")(_relative_asset)
    _https = field_validator("photo_link")(_https_only)

    @model_validator(mode="after")
    def _photos_are_credited(self) -> Role:
        if self.photo and not (self.photo_credit and self.photo_link):
            raise ValueError("a role photo needs photo_credit and photo_link (whose photo it is, and where it came from)")
        return self

    @property
    def page(self) -> str:
        return f"{self.id}.html"


# ---------------------------------------------------------------- the whole site


class Site(BaseModel):
    """Everything the templates receive. Table-level rules live here."""

    profile: Profile
    roles: list[Role]
    projects: list[Project]
    testimonials: list[Testimonial] = []
    resume: Resume | None = None
    today: date = Field(default_factory=date.today)  # "new this week" is measured from here

    @model_validator(mode="after")
    def site_rules(self) -> Site:
        role_ids = [r.id for r in self.roles]
        if sorted(role_ids) != sorted(["factory", "hire", "client", "lab", "studio"]):
            raise ValueError(f"roles.yaml must list each of the five roles once (got {role_ids})")
        for kind in {k for p in self.projects for k in p.roles}:
            banners = [p.id for p in self.projects if p.featured and p.kind == kind]
            if len(banners) > 1:
                raise ValueError(f"role '{kind}' has {len(banners)} featured projects ({', '.join(banners)}); "
                                 "one project per role gets the banner")
        ids = {p.id for p in self.projects}
        for t in self.testimonials:  # like a foreign key
            if t.project and t.project not in ids:
                raise ValueError(f"testimonial '{t.id}' points to unknown project '{t.project}'")
        if self.resume:
            for pid in self.resume.projects:
                if pid not in ids:
                    raise ValueError(f"resume.yaml lists unknown project '{pid}'")
        return self

    # Helpers the templates call. Keeping sorting/filtering here, not in
    # Jinja, keeps the templates dumb and this logic testable.
    def _sorted(self, items: list[Project]) -> list[Project]:
        return sorted(items, key=lambda p: (p.order, p.title))

    def role(self, rid: str) -> Role:
        return next(r for r in self.roles if r.id == rid)

    def in_role(self, rid: str) -> list[Project]:
        """Every project shown on a role page, its own and the also_in ones."""
        return self._sorted([p for p in self.projects if rid in p.roles])

    def billboard(self, rid: str) -> Project | None:
        """The banner project: the featured one, else the first with a screenshot, else the first."""
        own = self._sorted([p for p in self.projects if p.kind == rid])
        return (next((p for p in own if p.featured), None)
                or next((p for p in own if p.thumb), None)
                or (own[0] if own else None))

    def recently_updated(self, limit: int = 6) -> list[Project]:
        dated = [p for p in self.projects if p.updated]
        return sorted(dated, key=lambda p: (p.updated, -p.order), reverse=True)[:limit]

    @property
    def last_updated(self) -> date | None:
        return max((p.updated for p in self.projects if p.updated), default=None)

    @property
    def verified_testimonials(self) -> list[Testimonial]:
        return [t for t in self.testimonials if t.verified]

    @property
    def pages(self) -> list[Project]:
        """Projects with their own page, grouped by their home role, in role order."""
        return [p for r in self.roles for p in self._sorted([q for q in self.projects if q.kind == r.id])
                if p.has_page]

    def project(self, pid: str) -> Project:
        return next(p for p in self.projects if p.id == pid)

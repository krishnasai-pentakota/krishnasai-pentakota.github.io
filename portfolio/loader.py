"""Load content/*.yaml into validated models.

Two design choices worth knowing for interviews:

1. Collect ALL problems, then fail once. Stopping at the first error makes you
   fix-run-fix-run ten times. This is the same idea as a data-quality report
   that lists every bad row instead of crashing on row 1.
2. Always open files with encoding="utf-8". Windows defaults to cp1252, which
   chokes on characters like the rupee sign or Telugu text.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from .models import Profile, Project, Resume, Role, Site, Testimonial

M = TypeVar("M", bound=BaseModel)


class ContentError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"{len(problems)} content problem(s)")


def _describe(err: ValidationError, where: str) -> list[str]:
    """Turn Pydantic's error list into one readable line per problem."""
    lines = []
    for e in err.errors():
        field = ".".join(str(part) for part in e["loc"]) or "(file)"
        msg = e["msg"].removeprefix("Value error, ")
        lines.append(f"{where}: {field}: {msg}")
    return lines


def _load_one(path: Path, model: type[M], problems: list[str], *, id_from_name: bool = False) -> M | None:
    rel = path.as_posix().split("content/", 1)[-1]
    if not path.is_file():
        problems.append(f"{rel}: file is missing")
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        problems.append(f"{rel}: not valid YAML ({e})")
        return None
    if not isinstance(data, dict):
        problems.append(f"{rel}: expected 'key: value' pairs at the top level")
        return None
    if id_from_name:
        if "id" in data and data["id"] != path.stem:
            problems.append(f"{rel}: id '{data['id']}' must match the file name '{path.stem}'")
            return None
        data["id"] = path.stem
    try:
        return model.model_validate(data)
    except ValidationError as e:
        problems.extend(_describe(e, rel))
        return None


def check_assets(site: Site, static_dir: Path) -> list[str]:
    """Every local file the content points at must exist under static/."""
    problems = []
    wanted: list[tuple[str, str]] = []
    if site.profile.resume_pdf:
        wanted.append(("profile.yaml: resume_pdf", site.profile.resume_pdf))
    for p in site.projects:
        where = f"projects/{p.id}.yaml"
        if p.media:
            for field in ("poster", "preview"):
                value = getattr(p.media, field)
                if value:
                    wanted.append((f"{where}: media.{field}", value))
        for i, shot in enumerate(p.screenshots):
            wanted.append((f"{where}: screenshots.{i}.src", shot.src))
        for field in ("demo", "cover"):
            if getattr(p, field):
                wanted.append((f"{where}: {field}", getattr(p, field)))
    for where, rel in wanted:
        if not (static_dir / rel).is_file():
            problems.append(f"{where}: file not found at static/{rel}")
    return problems


def _load_roles(path: Path, problems: list[str]) -> list[Role]:
    """roles.yaml is a list (one entry per tile), so it gets its own small loader."""
    if not path.is_file():
        problems.append("roles.yaml: file is missing")
        return []
    try:
        items = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        problems.append(f"roles.yaml: not valid YAML ({e})")
        return []
    if not isinstance(items, list):
        problems.append("roles.yaml: expected a list of roles (each starting with '- id:')")
        return []
    roles = []
    for i, item in enumerate(items):
        try:
            roles.append(Role.model_validate(item))
        except ValidationError as e:
            problems.extend(_describe(e, f"roles.yaml: item {i + 1}"))
    return roles


def load_site(content_dir: Path, static_dir: Path) -> Site:
    problems: list[str] = []

    profile = _load_one(content_dir / "profile.yaml", Profile, problems)
    roles = _load_roles(content_dir / "roles.yaml", problems)
    projects = [
        _load_one(p, Project, problems, id_from_name=True)
        for p in sorted((content_dir / "projects").glob("*.yaml"))
    ]
    testimonials = [
        _load_one(p, Testimonial, problems, id_from_name=True)
        for p in sorted((content_dir / "testimonials").glob("*.yaml"))
    ]
    resume_file = content_dir / "resume.yaml"  # optional: no file, no resume page
    resume = _load_one(resume_file, Resume, problems) if resume_file.exists() else None
    if problems:  # don't build a Site out of half-valid parts
        raise ContentError(problems)

    try:
        site = Site(profile=profile, roles=roles, projects=projects, testimonials=testimonials, resume=resume)
    except ValidationError as e:
        raise ContentError(_describe(e, "site")) from None

    problems = check_assets(site, static_dir)
    if problems:
        raise ContentError(problems)
    return site

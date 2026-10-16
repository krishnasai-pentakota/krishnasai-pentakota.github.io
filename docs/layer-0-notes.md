# Layer 0 notes — the build pipeline

Read this once with the code open beside it. Each block below matches one file.

## The shape

```
content/*.yaml ──► loader.py ──► models.py ──► render.py ──► dist/
   (source)        (extract)     (validate)    (load)        (target)
```

It's an ETL job. The "rows" are your project files, the "schema" is
`models.py`, and the "warehouse" is a folder of HTML. Same habits as your weaving
pipeline: validate before loading, reject bad rows with a reason, make reruns safe.

## Block 1 — `models.py`: the contract

- **`class Strict(BaseModel)` with `extra="forbid"`**: any key the model doesn't know is an
  error. Without it, `sumary:` would load fine and the summary would silently be missing.
- **`Status` enum**: five allowed values, nothing else. `label`, `shipped` and
  `can_have_results` are properties, so the rules live in one place and templates
  just ask `p.status.shipped`.
- **`HttpUrl`**: refuses `""`, `"#"` and relative paths on its own. `_https_only` adds
  "must be https".
- **`@field_validator`**: a check on one field (slug format, github.com host).
- **`@model_validator(mode="after")` on `Project`**: a check across fields of one file,
  e.g. "concept + metrics = not allowed". `mode="after"` means it runs once every
  field is already parsed and typed.
- **`@model_validator` on `Site`**: rules across files: at most 3 featured, and a
  testimonial must point to a real project (a foreign key).
- **`ClassVar[int]`**: marks `MAX_FEATURED` as a constant. Without `ClassVar`,
  Pydantic would treat it as a field anyone could override from YAML.

## Block 2 — `loader.py`: collect every error, then fail once

`_load_one` never raises. It appends readable lines to `problems` and returns
`None`. `load_site` raises `ContentError` once, at the end, with the full list.
That's the difference between fixing 5 problems in one run and running the build 5 times.

Always `read_text(encoding="utf-8")`: on Windows the default is cp1252, which
breaks on ₹ or Telugu text.

## Block 3 — `render.py`: safe, strict, repeatable

- **`StrictUndefined`**: `{{ profile.nmae }}` stops the build. Jinja's default prints
  an empty string and you'd ship a blank heading.
- **`autoescape`**: `<` and `&` in your content become safe HTML. Content can never
  inject a script.
- **`_clean` + the marker file**: each build deletes the previous `dist/` so no stale
  files survive. That's an idempotent build: same input, same output. It only
  deletes folders that carry `.built-by-portfolio`, so a wrong `--out` can't wipe your work.

## Block 4 — templates

- `base.html` is the frame (head, nav, footer). `index.html` *extends* it and fills the blocks.
- `_macros.html` holds `card()` and `section()`. Change the card once and every card changes.
- `section()` renders nothing when its list is empty. That's how empty sections disappear.
- Paths like `static/css/site.css` have no leading `/`, so the site works under
  `username.github.io/<repo>/`.

## Block 5 — tests

- `test_models.py`: one test per rule, proving both directions (good passes, bad fails).
- `test_site.py`: builds the real site into a temp folder and parses the HTML. It checks
  that no link is dead, every `#anchor` has a matching id, there are no leftover
  `None`/`{{` strings, the rebuild removes stale files, and the build refuses to wipe a
  folder it didn't create.

## Two real bugs the pipeline caught while I wrote your content

1. `role: Sole engineer: audit, ...` → **not valid YAML**. A `: ` inside an unquoted
   value starts a new key. Fix: wrap the value in quotes.
2. `period: 2026` → **"Input should be a valid string"**. YAML reads a bare `2026` as a
   number. Fix: `"2026"`. (Same trap: `version: 1.10` becomes the number 1.1.)

Both would have shipped silently with a hand-edited JS config object.

## Exercises (15 minutes)

1. In `content/profile.yaml` set `github: "#"` and run `python build.py --check`. Read the
   error, then set it back to `null`.
2. In `fde-slip-reader.yaml` add:
   ```yaml
   metrics:
     - value: "95%"
       label: fields read correctly
       evidence: eval run
   ```
   Run the check. Why is it refused? What would you change, and when?
3. Add a rule yourself: in `Project.honest_status`, refuse a `lab` project whose
   `period` is missing. Add a test for it in `test_models.py`. Run `python -m pytest`.

## Interview questions this layer prepares you for

- *Why validate content with Pydantic instead of a JavaScript config object?*
- *What's the difference between a field validator and a model validator?*
- *What does "idempotent build" mean, and how does this one achieve it?*
- *Why collect all validation errors instead of failing on the first?*

<details><summary>Short answers</summary>

1. A JS object fails at runtime in the visitor's browser, or not at all (blank text). Pydantic
   fails at build time on your machine, with the file and field named, before anything ships.
2. A field validator checks one value in isolation. A model validator sees the whole
   object, so it can enforce rules between fields (status vs metrics).
3. Running it twice with the same input gives the same output. Here: `dist/` is
   deleted and fully regenerated every run, so nothing stale survives.
4. Feedback cost. One run shows every problem, the same way a data-quality report lists
   all bad rows instead of crashing on the first.

</details>

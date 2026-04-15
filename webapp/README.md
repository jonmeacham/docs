# Schedule Planner Webapp

Static web app for schedule-planning queries, compatible with GitHub Pages.

## What It Supports

You can filter by any combination of:

- schedule slot period (`A1`-`B8`)
- semester/full-year compatibility
- graduation credit requirement
- course name from a searchable list

Results show all compatible offerings from the machine-readable master schedule, with teacher/section details and matched graduation requirements from the catalog.

## Data Sources

The app reads:

- `./data/master_schedule_cells.json`
- `./data/course_catalog.json`

These webapp-local data files are generated from canonical datasets using:

```bash
uv run "scripts/build_webapp_data.py"
```

## Semester Filter Rules

- `Semester 1 only`: semester-1 offerings only (excludes full-year offerings)
- `Semester 2 only`: semester-2 offerings only (excludes full-year offerings)
- `Full year only`: full-year offerings only

## GitHub Pages

If this repository is published on GitHub Pages, the app is available at:

- `/webapp/`

No build step is required.

## Local Use (from `webapp` directory)

Because the app now uses local `./data/*` paths, it can be served directly from this folder:

```bash
cd webapp
uv run python -m http.server 4173
```

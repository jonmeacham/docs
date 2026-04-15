# LHS 10th Grade Schedule Planning Toolkit

This repository contains source planning artifacts, machine-readable datasets, extractors, and a GitHub Pages-compatible webapp for exploring schedule options.

## Repository Contents

- Source documents (master schedule, catalog, planning references)
- Machine-readable datasets:
  - `machine_readable_master_schedule_xlsx/`
  - `machine_readable_course_catalog/`
- Reusable extractors and data build scripts in `scripts/`
- Static planner app in `webapp/`
- End-to-end webapp tests in `tests/`

## Quick Start

From repo root:

```bash
npm install
python3 "scripts/build_webapp_data.py"
npm run test:webapp
```

Run locally:

```bash
python3 -m http.server 4173
```

Then open:

- `http://localhost:4173/` (redirects to `webapp/`)

## Data Pipeline

Canonical source extraction:

```bash
python3 "scripts/extract_master_schedule_xlsx.py" \
  --xlsx "26-27 Printable Master Schedule.xlsx" \
  --output-dir "machine_readable_master_schedule_xlsx"
```

```bash
python3 "scripts/extract_course_catalog_md.py" \
  --source "LHS COURSE DESCRIPTIONS 26-27.md" \
  --output-dir "machine_readable_course_catalog"
```

Build webapp-local deployment data:

```bash
python3 "scripts/build_webapp_data.py"
# or
npm run build:webapp-data
```

For step-by-step regeneration and validation guidance, see `REGENERATE_DATASETS.md`.

## Webapp

The static app lives in `webapp/` and reads local deployment data from:

- `webapp/data/master_schedule_cells.json`
- `webapp/data/course_catalog.json`

GitHub Pages can serve the repository root directly; `index.html` redirects to `webapp/`.

## Testing

- Run all Playwright tests: `npm test`
- Run webapp-focused suite: `npm run test:webapp`

## Notes

- `private/` is gitignored for student-specific planning details.
- XLSX-based extraction is the preferred source of truth for semester ordering and slot accuracy.

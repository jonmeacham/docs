# Regenerate Machine-Readable Datasets

Use this guide when new versions of the master schedule or course catalog are published.

## Canonical Sources

- Master schedule source: `*.xlsx` (preferred over PDF)
- Course catalog source: `*.md` (course descriptions)

## Commands

From repo root:

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

```bash
python3 "scripts/build_webapp_data.py"
```

## Validation Checklist

After each run, check:

- `machine_readable_master_schedule_xlsx/validation_report.md`
  - spot checks pass
  - section counts look reasonable
- `machine_readable_course_catalog/validation_report.md`
  - low missing counts for graduation requirement / course length
  - expected course count range for current school year

## Cross-Reference Fields Guaranteed

The course catalog extractor keeps these fields for schedule joins:

- `course_name`
- `description`
- `graduation_requirement_details`
- `course_length_text` + normalized semester count
- `prerequisites` + `recommended_prerequisites`
- `grade_requirements`
- `normalized_course_name` + `cross_reference_aliases`

The master schedule extractor keeps:

- teacher-period cells with ordered `lines`
- semester mapping (`semester_1`, `semester_2`) for two-line cells
- section and teacher identifiers for filtering and joins

For GitHub Pages deployment, the webapp consumes:

- `webapp/data/master_schedule_cells.json`
- `webapp/data/course_catalog.json`

These are generated from the canonical datasets by `scripts/build_webapp_data.py`.

## Legacy Fallback

If XLSX is unavailable, a PDF OCR fallback exists:

```bash
python3 "scripts/extract_master_schedule.py"
```

This path is less reliable and should only be used when spreadsheet source is missing.

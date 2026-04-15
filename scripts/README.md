# Data Extractors

This folder contains reusable extractors for generating machine-readable planning datasets from district artifacts.

## Extractors

| Script | Input Artifact | Primary Output Dir | Status |
|---|---|---|---|
| `extract_master_schedule_xlsx.py` | `26-27 Printable Master Schedule.xlsx` | `machine_readable_master_schedule_xlsx` | Recommended |
| `extract_course_catalog_md.py` | `LHS COURSE DESCRIPTIONS 26-27.md` | `machine_readable_course_catalog` | Recommended |
| `build_webapp_data.py` | generated schedule/catalog datasets | `webapp/data` | Recommended for deployment |
| `extract_master_schedule.py` | `26-27 Printable Master Schedule - TENTATIVE MASTER SCHEDULE.pdf` | `machine_readable_master_schedule` | Legacy (OCR fallback) |

## Usage

Run from repository root (`/Users/jon/repo/docs`):

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

Legacy OCR fallback (only if XLSX is unavailable):

```bash
python3 "scripts/extract_master_schedule.py" \
  --pdf "26-27 Printable Master Schedule - TENTATIVE MASTER SCHEDULE.pdf" \
  --output-dir "machine_readable_master_schedule"
```

## Reuse For New School Years

1. Drop the new source files in repo root.
2. Run each extractor with the new file path via CLI flags.
3. Review the generated `validation_report.md` in each output directory.
4. If validation looks good, use the JSON/CSV outputs as the cross-reference source.

## Data Contracts

### Master Schedule (`machine_readable_master_schedule_xlsx`)

- `master_schedule_cells.json`:
  - one record per populated teacher-period cell
  - `lines[0]` = semester 1 line when `schedule_hint == "semester_pair"`
  - `lines[1]` = semester 2 line when `schedule_hint == "semester_pair"`
- `master_schedule_lines.csv`:
  - flattened line-level table for query/join workflows
  - includes `semester_hint` (`semester_1`, `semester_2`, `full_year`, etc.)

### Course Catalog (`machine_readable_course_catalog`)

- `course_catalog.json`:
  - canonical course objects with:
    - `course_name`
    - `description`
    - `graduation_requirement_details`
    - `course_length_text`, `course_length_normalized`, `course_length_semesters`
    - `prerequisites`, `recommended_prerequisites`
    - `grade_requirements`
    - cross-reference helpers (`normalized_course_name`, `cross_reference_aliases`)
- `course_catalog.csv`: flattened course table
- `course_prerequisites.csv`: one prerequisite row per statement

## Notes

- The XLSX master schedule extractor is preferred because it preserves semester ordering directly from cell line order.
- Catalog parsing depends on the current markdown structure (bold course titles + metadata lines). If formatting changes, update parsing rules in `extract_course_catalog_md.py`.

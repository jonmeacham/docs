.PHONY: dataset webapp test

MASTER_SCHEDULE_XLSX := 26-27 Printable Master Schedule.xlsx
COURSE_CATALOG_MD := LHS COURSE DESCRIPTIONS 26-27.md

dataset:
	uv run scripts/extract_master_schedule_xlsx.py --xlsx "$(MASTER_SCHEDULE_XLSX)" --output-dir machine_readable_master_schedule_xlsx
	uv run scripts/extract_course_catalog_md.py --source "$(COURSE_CATALOG_MD)" --output-dir machine_readable_course_catalog
	uv run scripts/build_webapp_data.py

webapp: dataset
	npm run test:webapp
	@echo "Webapp is prepared for commit and GitHub Pages deploy (data rebuilt, tests passed)."

test:
	npm test -- --workers=4

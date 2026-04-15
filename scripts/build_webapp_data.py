#!/usr/bin/env python3
"""Build webapp-local data files for GitHub Pages deployment."""

from __future__ import annotations

import json
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def build_master_schedule(source: dict) -> dict:
    slim_cells = []
    for cell in source.get("cells", []):
        slim_cells.append(
            {
                "source_row": cell.get("source_row"),
                "section": cell.get("section"),
                "teacher_name": cell.get("teacher_name"),
                "room": cell.get("room"),
                "period": cell.get("period"),
                "schedule_hint": cell.get("schedule_hint"),
                "lines": [
                    {
                        "line_index": line.get("line_index"),
                        "semester_hint": line.get("semester_hint"),
                        "text": line.get("text"),
                    }
                    for line in cell.get("lines", [])
                ],
            }
        )
    return {
        "source_workbook": source.get("source_workbook"),
        "updated_date_text": source.get("updated_date_text"),
        "periods": source.get("periods", []),
        "cells": slim_cells,
    }


def build_course_catalog(source: dict) -> dict:
    slim_courses = []
    for course in source.get("courses", []):
        slim_courses.append(
            {
                "course_name": course.get("course_name"),
                "section_name": course.get("section_name"),
                "graduation_requirement_list": course.get("graduation_requirement_list", []),
                "description": course.get("description"),
                "prerequisites": course.get("prerequisites", []),
                "recommended_prerequisites": course.get("recommended_prerequisites", []),
                "course_length_text": course.get("course_length_text"),
                "grade_requirements": course.get("grade_requirements"),
                "normalized_course_name": course.get("normalized_course_name"),
                "cross_reference_aliases": course.get("cross_reference_aliases", []),
                "audition_tryout_required": course.get("audition_tryout_required", False),
                "audition_tryout_evidence": course.get("audition_tryout_evidence", []),
            }
        )
    return {
        "source_markdown": source.get("source_markdown"),
        "course_count": len(slim_courses),
        "courses": slim_courses,
    }


def main() -> None:
    root = Path.cwd()
    master_source = read_json(
        root / "machine_readable_master_schedule_xlsx" / "master_schedule_cells.json"
    )
    catalog_source = read_json(
        root / "machine_readable_course_catalog" / "course_catalog.json"
    )

    write_json(
        root / "webapp" / "data" / "master_schedule_cells.json",
        build_master_schedule(master_source),
    )
    write_json(
        root / "webapp" / "data" / "course_catalog.json",
        build_course_catalog(catalog_source),
    )


if __name__ == "__main__":
    main()

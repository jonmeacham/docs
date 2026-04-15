#!/usr/bin/env -S uv run python
"""Extract a machine-readable master schedule from the XLSX source workbook.

Designed for yearly reuse:
- pass the new workbook path via `--xlsx`
- pass a target dataset directory via `--output-dir`
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET


PERIOD_COLUMNS = {
    "C": "A1",
    "D": "A2",
    "E": "A3",
    "F": "A4",
    "G": "B5",
    "H": "B6",
    "I": "B7",
    "J": "B8",
}

SECTION_HEADERS = {
    "CTE / FINANCIAL LIT",
    "ENGLISH",
    "FINE ARTS",
    "MATH",
    "PE / HEALTH",
    "SCIENCE",
    "SOCIAL STUDIES",
    "WORLD LANGUAGES",
    "GENERAL EDUCATION/INTERACTIVE VIDEO CLASSES (IVC)",
    "SPED",
    "UVU DIGITAL EDUCATION-UVU LIVE INTERACTIVE- UVU LIVESTREAM- UVU ONLINE",
    "SEMINARY",
}

SPOT_CHECKS = [
    {
        "teacher_prefix": "Anderson, M",
        "period": "A2",
        "must_contain": ["Mixed Media Sculpture", "Ceramics Sculpture"],
        "description": "Anderson A2 has the sculpture pair",
    },
    {
        "teacher_prefix": "Haws, Z",
        "period": "A3",
        "must_contain": ["Illustration/Character Design", "Illustration/Character Design"],
        "description": "Haws A3 has Illustration/Character Design both semesters",
    },
    {
        "teacher_prefix": "Slager, B",
        "period": "A2",
        "must_contain": ["Photo 1", "Photo 2"],
        "description": "Slager A2 is Photo 1 / Photo 2",
    },
    {
        "teacher_prefix": "Madsen, E",
        "period": "A2",
        "must_contain": ["Fitness", "Fitness"],
        "description": "Madsen A2 is Fitness both semesters",
    },
    {
        "teacher_prefix": "Olson, M",
        "period": "B6",
        "must_contain": ["Spanish 2"],
        "description": "Olson B6 includes Spanish 2",
    },
]


@dataclass
class WorkbookData:
    sheet_name: str
    shared_strings: list[str]
    cells: dict[str, str]
    merge_map: dict[str, str]
    max_row: int


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def col_to_num(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n


def num_to_col(num: int) -> str:
    chars = []
    while num:
        num, rem = divmod(num - 1, 26)
        chars.append(chr(65 + rem))
    return "".join(reversed(chars))


def split_ref(ref: str) -> tuple[str, int]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    if not match:
        raise ValueError(f"Bad cell ref: {ref}")
    return match.group(1), int(match.group(2))


def iter_range(range_ref: str) -> list[str]:
    start_ref, end_ref = range_ref.split(":")
    start_col, start_row = split_ref(start_ref)
    end_col, end_row = split_ref(end_ref)
    refs = []
    for row in range(start_row, end_row + 1):
        for col_num in range(col_to_num(start_col), col_to_num(end_col) + 1):
            refs.append(f"{num_to_col(col_num)}{row}")
    return refs


def xlsx_serial_to_date(serial: str) -> str:
    if not serial.isdigit():
        return serial
    # Excel's day 1 is 1899-12-31 with a fake 1900 leap day.
    from datetime import date, timedelta

    base = date(1899, 12, 30)
    return str(base + timedelta(days=int(serial)))


def load_workbook(path: Path) -> WorkbookData:
    with ZipFile(path) as zf:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        ns_main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        ns_rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        sheet = workbook.find(f"{ns_main}sheets")[0]
        sheet_name = sheet.attrib["name"]
        target = rel_map[sheet.attrib[f"{ns_rel}id"]]
        sheet_xml = ET.fromstring(zf.read(f"xl/{target}"))

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root:
                shared_strings.append("".join(t.text or "" for t in si.iter(f"{ns_main}t")))

        cells: dict[str, str] = {}
        max_row = 0
        for row in sheet_xml.find(f"{ns_main}sheetData"):
            max_row = max(max_row, int(row.attrib["r"]))
            for cell in row:
                ref = cell.attrib["r"]
                cell_type = cell.attrib.get("t")
                value = ""
                value_node = cell.find(f"{ns_main}v")
                if value_node is not None and value_node.text is not None:
                    value = value_node.text
                    if cell_type == "s":
                        value = shared_strings[int(value)]
                inline = cell.find(f"{ns_main}is")
                if inline is not None:
                    value = "".join(t.text or "" for t in inline.iter(f"{ns_main}t"))
                cells[ref] = value

        merge_map: dict[str, str] = {}
        merge_cells = sheet_xml.find(f"{ns_main}mergeCells")
        if merge_cells is not None:
            for merged in merge_cells:
                merged_ref = merged.attrib["ref"]
                refs = iter_range(merged_ref)
                origin = refs[0]
                for ref in refs:
                    merge_map[ref] = origin

        return WorkbookData(
            sheet_name=sheet_name,
            shared_strings=shared_strings,
            cells=cells,
            merge_map=merge_map,
            max_row=max_row,
        )


def get_cell_value(book: WorkbookData, ref: str) -> str:
    origin = book.merge_map.get(ref, ref)
    return book.cells.get(origin, "")


def clean_cell_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [normalize_ws(line) for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def parse_teacher(text: str) -> tuple[str, str | None]:
    text = normalize_ws(text)
    match = re.match(r"^(.*?)(?:\s*\(([^)]*)\))?$", text)
    if not match:
        return text, None
    name = normalize_ws(match.group(1))
    room = normalize_ws(match.group(2) or "") or None
    return name, room


def normalize_for_match(text: str) -> str:
    text = text.upper()
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"[^A-Z0-9/()+&'\-]+", " ", text)
    return normalize_ws(text)


def build_cells(book: WorkbookData, source_name: str) -> list[dict]:
    cells: list[dict] = []
    current_section: str | None = None

    for row_num in range(1, book.max_row + 1):
        label = clean_cell_text(get_cell_value(book, f"A{row_num}"))
        label_norm = normalize_for_match(label)
        if label_norm in {normalize_for_match(s) for s in SECTION_HEADERS}:
            current_section = next(s for s in SECTION_HEADERS if normalize_for_match(s) == label_norm)
            continue

        if current_section is None:
            continue

        period_values = {
            period: clean_cell_text(get_cell_value(book, f"{col}{row_num}"))
            for col, period in PERIOD_COLUMNS.items()
        }
        has_period_data = any(period_values.values())
        if not has_period_data:
            continue

        teacher_display = label
        if not teacher_display and current_section == "SEMINARY":
            teacher_display = "Seminary"
        if not teacher_display:
            continue

        label_origin = book.merge_map.get(f"A{row_num}", f"A{row_num}")
        _, teacher_row = split_ref(label_origin)
        teacher_name, room = parse_teacher(teacher_display)

        for period, cell_text in period_values.items():
            lines = [line for line in cell_text.split("\n") if line]
            if not lines:
                continue

            if len(lines) == 1:
                schedule_hint = "full_year"
            elif len(lines) == 2:
                schedule_hint = "semester_pair"
            else:
                schedule_hint = "ambiguous"

            cells.append(
                {
                    "source_workbook": source_name,
                    "sheet_name": book.sheet_name,
                    "source_row": row_num,
                    "teacher_row": teacher_row,
                    "section": current_section,
                    "teacher_display": teacher_display,
                    "teacher_name": teacher_name,
                    "room": room,
                    "period": period,
                    "schedule_hint": schedule_hint,
                    "line_count": len(lines),
                    "lines": [
                        {
                            "line_index": idx + 1,
                            "semester_hint": (
                                "full_year"
                                if schedule_hint == "full_year"
                                else f"semester_{idx + 1}"
                                if schedule_hint == "semester_pair"
                                else f"line_{idx + 1}"
                            ),
                            "text": line,
                        }
                        for idx, line in enumerate(lines)
                    ],
                }
            )
    return cells


def build_line_rows(cells: list[dict]) -> list[dict]:
    rows = []
    for cell in cells:
        for line in cell["lines"]:
            rows.append(
                {
                    "sheet_name": cell["sheet_name"],
                    "source_row": cell["source_row"],
                    "teacher_row": cell["teacher_row"],
                    "section": cell["section"] or "",
                    "teacher_name": cell["teacher_name"],
                    "room": cell["room"] or "",
                    "period": cell["period"],
                    "cell_schedule_hint": cell["schedule_hint"],
                    "line_index": line["line_index"],
                    "semester_hint": line["semester_hint"],
                    "course_text": line["text"],
                }
            )
    return rows


def passes_check(found_lines: list[str], expected_lines: list[str]) -> bool:
    normalized = [normalize_for_match(line) for line in found_lines]
    for expected in expected_lines:
        expected_norm = normalize_for_match(expected)
        if not any(
            expected_norm in line
            or difflib.SequenceMatcher(None, expected_norm, line).ratio() >= 0.75
            for line in normalized
        ):
            return False
    return True


def validate(cells: list[dict], workbook_name: str) -> tuple[dict, str]:
    teacher_rows = {(cell["section"], cell["teacher_display"], cell["teacher_row"]) for cell in cells}
    section_counts: dict[str, int] = {}
    for section, teacher, row in teacher_rows:
        key = section or "UNKNOWN"
        section_counts[key] = section_counts.get(key, 0) + 1

    hints = {"full_year": 0, "semester_pair": 0, "ambiguous": 0}
    for cell in cells:
        hints[cell["schedule_hint"]] += 1

    spot_results = []
    for check in SPOT_CHECKS:
        cell = next(
            (
                item
                for item in cells
                if item["teacher_name"].startswith(check["teacher_prefix"]) and item["period"] == check["period"]
            ),
            None,
        )
        found_lines = [line["text"] for line in cell["lines"]] if cell else []
        spot_results.append(
            {
                "description": check["description"],
                "teacher_prefix": check["teacher_prefix"],
                "period": check["period"],
                "passed": bool(cell) and passes_check(found_lines, check["must_contain"]),
                "found_lines": found_lines,
            }
        )

    summary = {
        "source_workbook": workbook_name,
        "teacher_row_count": len(teacher_rows),
        "cell_count": len(cells),
        "section_teacher_counts": section_counts,
        "schedule_hint_counts": hints,
        "spot_check_pass_count": sum(1 for result in spot_results if result["passed"]),
        "spot_check_total": len(spot_results),
    }

    spot_lines = []
    for result in spot_results:
        status = "PASS" if result["passed"] else "FAIL"
        found = "; ".join(result["found_lines"]) if result["found_lines"] else "no cell found"
        spot_lines.append(
            f"- {status}: {result['description']} (`{result['teacher_prefix']}` `{result['period']}`) -> {found}"
        )

    counts_lines = "\n".join(
        f"- `{section}`: {count} teacher rows" for section, count in sorted(section_counts.items())
    )
    hint_lines = "\n".join(
        f"- `{hint}`: {count} cells" for hint, count in sorted(hints.items())
    )

    report = (
        "# Master Schedule Validation\n\n"
        "## Summary\n"
        f"- Source workbook: `{workbook_name}`\n"
        f"- Teacher rows parsed: {summary['teacher_row_count']}\n"
        f"- Period cells parsed: {summary['cell_count']}\n"
        f"- Spot checks passed: {summary['spot_check_pass_count']} / {summary['spot_check_total']}\n\n"
        "## Teacher Rows By Section\n"
        f"{counts_lines}\n\n"
        "## Cell Types\n"
        f"{hint_lines}\n\n"
        "## Spot Checks\n"
        f"{chr(10).join(spot_lines)}\n"
    )
    return summary, report


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--xlsx",
        default="26-27 Printable Master Schedule.xlsx",
        help="Path to the master schedule workbook.",
    )
    parser.add_argument(
        "--output-dir",
        default="machine_readable_master_schedule_xlsx",
        help="Directory for generated artifacts.",
    )
    args = parser.parse_args()

    root = Path.cwd()
    xlsx_path = (root / args.xlsx).resolve()
    output_dir = (root / args.output_dir).resolve()

    book = load_workbook(xlsx_path)
    cells = build_cells(book, xlsx_path.name)
    lines = build_line_rows(cells)
    summary, report = validate(cells, xlsx_path.name)

    metadata = {
        "source_workbook": xlsx_path.name,
        "sheet_name": book.sheet_name,
        "updated_date_text": xlsx_serial_to_date(get_cell_value(book, "J1")),
        "periods": list(PERIOD_COLUMNS.values()),
        "cells": cells,
        "validation_summary": summary,
    }
    write_json(output_dir / "master_schedule_cells.json", metadata)
    write_csv(output_dir / "master_schedule_lines.csv", lines)
    (output_dir / "validation_report.md").write_text(report)
    (output_dir / "README.md").write_text(
        "# Machine-Readable Master Schedule\n\n"
        f"These artifacts were generated from `{xlsx_path.name}`.\n\n"
        "- `master_schedule_cells.json`: cell-oriented schedule data with ordered line lists per period cell.\n"
        "- `master_schedule_lines.csv`: one record per cell line, with semester hints.\n"
        "- `validation_report.md`: spot checks and section counts.\n"
    )


if __name__ == "__main__":
    main()

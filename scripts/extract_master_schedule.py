#!/usr/bin/env -S uv run python
"""Build a machine-readable version of the Lehi High master schedule PDF.

The output intentionally preserves each schedule cell as an ordered list of lines.
For semester cells, line 1 corresponds to Semester 1 and line 2 to Semester 2.
For full-year cells, a single line is stored.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import statistics
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PERIODS = ["A1", "A2", "A3", "A4", "B5", "B6", "B7", "B8"]
RENDER_WIDTH = 3300
RENDER_HEIGHT = 2550

# These ratios were calibrated from a 2200px-wide rendered page and then stored
# as proportions so they can be reused if the render size changes.
PERIOD_BOUNDARY_RATIOS = [
    328 / 2200,
    495 / 2200,
    705 / 2200,
    915 / 2200,
    1124 / 2200,
    1333 / 2200,
    1542 / 2200,
    1751 / 2200,
    2060 / 2200,
]
TEACHER_BOUNDARY_RATIO = PERIOD_BOUNDARY_RATIOS[0]
SECTION_DETECTION_RATIO = 340 / 2200

SECTION_HEADERS = [
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
]

PAGE_SECTION_RANGES = {
    1: [
        (0, 1320, "CTE / FINANCIAL LIT"),
        (1320, 9999, "ENGLISH"),
    ],
    2: [
        (0, 620, "ENGLISH"),
        (620, 1260, "FINE ARTS"),
        (1260, 9999, "MATH"),
    ],
    3: [
        (0, 280, "MATH"),
        (280, 1320, "PE / HEALTH"),
        (1320, 9999, "SCIENCE"),
    ],
    4: [
        (0, 620, "SCIENCE"),
        (620, 1010, "SOCIAL STUDIES"),
        (1010, 1330, "WORLD LANGUAGES"),
        (1330, 9999, "GENERAL EDUCATION/INTERACTIVE VIDEO CLASSES (IVC)"),
    ],
    5: [
        (0, 720, "SPED"),
        (720, 1020, "UVU DIGITAL EDUCATION-UVU LIVE INTERACTIVE- UVU LIVESTREAM- UVU ONLINE"),
        (1020, 9999, "SEMINARY"),
    ],
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
        "must_contain": ["Illustration/Character Design"],
        "description": "Haws A3 has Illustration/Character Design",
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
        "must_contain": ["Fitness"],
        "description": "Madsen A2 includes Fitness",
    },
    {
        "teacher_prefix": "Olson, M",
        "period": "B6",
        "must_contain": ["Spanish 2"],
        "description": "Olson B6 includes Spanish 2",
    },
]


@dataclass
class Word:
    page: int
    left: int
    top: int
    width: int
    height: int
    conf: float
    text: str

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2


@dataclass
class Event:
    kind: str
    top: int
    bottom: int
    text: str
    section: str | None = None


def run(command: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_for_match(text: str) -> str:
    text = text.upper()
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"[^A-Z0-9/()+-]+", " ", text)
    return normalize_whitespace(text)


def clean_text(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("|", " ")
    text = text.replace("ﬁ", "fi")
    text = text.replace("ﬂ", "fl")
    return normalize_whitespace(text)


def canonical_section(line_text: str) -> str | None:
    normalized = normalize_for_match(line_text)
    for header in SECTION_HEADERS:
        header_norm = normalize_for_match(header)
        if normalized == header_norm or normalized in header_norm or header_norm in normalized:
            return header
    return None


def looks_like_teacher_line(line_text: str) -> bool:
    text = clean_text(line_text)
    if not text:
        return False
    if canonical_section(text):
        return False
    if text.startswith(("Staff ", "New Hire")):
        return True
    if "," in text:
        return True
    if "(" in text and ")" in text and any(char.isalpha() for char in text):
        return True
    return False


def parse_teacher(text: str) -> tuple[str, str | None]:
    text = clean_text(text)
    match = re.match(r"^(.*?)(?:\s*\(([^)]*)\))?$", text)
    if not match:
        return text, None
    name = clean_text(match.group(1))
    room = clean_text(match.group(2) or "") or None
    return name, room


def render_pages(pdf_path: Path, render_dir: Path) -> list[Path]:
    render_dir.mkdir(parents=True, exist_ok=True)
    swift_script = textwrap.dedent(
        f"""
        import Foundation
        import PDFKit
        import AppKit

        func save(_ image: NSImage, path: String) {{
            guard let tiff = image.tiffRepresentation,
                  let rep = NSBitmapImageRep(data: tiff),
                  let data = rep.representation(using: .png, properties: [:]) else {{ return }}
            try? data.write(to: URL(fileURLWithPath: path))
        }}

        let pdfURL = URL(fileURLWithPath: "{pdf_path}")
        guard let doc = PDFDocument(url: pdfURL) else {{
            fputs("Failed to open PDF\\n", stderr)
            exit(1)
        }}

        let outputDir = URL(fileURLWithPath: "{render_dir}")
        for pageIndex in 0..<doc.pageCount {{
            guard let page = doc.page(at: pageIndex) else {{ continue }}
            let image = page.thumbnail(of: NSSize(width: {RENDER_WIDTH}, height: {RENDER_HEIGHT}), for: .mediaBox)
            let url = outputDir.appendingPathComponent("page_\\(pageIndex + 1).png")
            save(image, path: url.path)
        }}
        """
    )
    subprocess.run(["swift", "-"], input=swift_script, text=True, check=True)
    return sorted(render_dir.glob("page_*.png"))


def ocr_tsv(image_path: Path) -> str:
    return run(["tesseract", str(image_path), "stdout", "--psm", "6", "tsv"])


def parse_tsv(tsv_text: str, page_num: int) -> list[Word]:
    rows = list(csv.DictReader(tsv_text.splitlines(), delimiter="\t"))
    words: list[Word] = []
    for row in rows:
        if row.get("level") != "5":
            continue
        text = clean_text(row.get("text", ""))
        if not text:
            continue
        try:
            conf = float(row.get("conf", "-1"))
        except ValueError:
            conf = -1
        if conf < 0:
            continue
        words.append(
            Word(
                page=page_num,
                left=int(row["left"]),
                top=int(row["top"]),
                width=int(row["width"]),
                height=int(row["height"]),
                conf=conf,
                text=text,
            )
        )
    return words


def build_first_column_lines(words: list[Word], page_width: int) -> list[dict]:
    teacher_boundary = page_width * TEACHER_BOUNDARY_RATIO
    first_col_words = [w for w in words if w.center_x < teacher_boundary]
    buckets: dict[tuple[int, int], list[Word]] = {}
    # Tesseract line ids are not kept above, so cluster visually by top position.
    for word in sorted(first_col_words, key=lambda w: (w.top, w.left)):
        matched_key = None
        for key in buckets:
            ref_top = key[1]
            if abs(word.top - ref_top) <= 10:
                matched_key = key
                break
        if matched_key is None:
            matched_key = (len(buckets) + 1, word.top)
            buckets[matched_key] = []
        buckets[matched_key].append(word)

    lines: list[dict] = []
    for _, line_words in sorted(buckets.items(), key=lambda item: item[0][1]):
        line_words.sort(key=lambda w: w.left)
        text = clean_text(" ".join(word.text for word in line_words))
        if not text:
            continue
        lines.append(
            {
                "text": text,
                "left": min(w.left for w in line_words),
                "right": max(w.left + w.width for w in line_words),
                "top": min(w.top for w in line_words),
                "bottom": max(w.top + w.height for w in line_words),
            }
        )
    return lines


def build_page_lines(words: list[Word]) -> list[dict]:
    if not words:
        return []
    buckets: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.top, w.left)):
        placed = False
        for bucket in buckets:
            ref_top = statistics.mean(w.top for w in bucket)
            if abs(word.top - ref_top) <= 8:
                bucket.append(word)
                placed = True
                break
        if not placed:
            buckets.append([word])

    lines: list[dict] = []
    for bucket in buckets:
        bucket.sort(key=lambda w: w.left)
        text = clean_text(" ".join(word.text for word in bucket))
        if not text:
            continue
        lines.append(
            {
                "text": text,
                "left": min(w.left for w in bucket),
                "right": max(w.left + w.width for w in bucket),
                "top": min(w.top for w in bucket),
                "bottom": max(w.top + w.height for w in bucket),
            }
        )
    return lines


def build_events(first_col_lines: list[dict], page_lines: list[dict], page_width: int) -> list[Event]:
    section_x_limit = page_width * SECTION_DETECTION_RATIO
    events: list[Event] = []
    current_section: str | None = None
    for line in page_lines:
        text = line["text"]
        if line["left"] <= section_x_limit:
            section = canonical_section(text)
            if section:
                current_section = section
                events.append(
                    Event(
                        kind="section",
                        top=line["top"],
                        bottom=line["bottom"],
                        text=section,
                        section=section,
                    )
                )
    for line in first_col_lines:
        text = line["text"]
        inferred_section = current_section
        for event in events:
            if event.kind == "section" and event.top <= line["top"]:
                inferred_section = event.section
        if looks_like_teacher_line(text):
            events.append(
                Event(
                    kind="teacher",
                    top=line["top"],
                    bottom=line["bottom"],
                    text=text,
                    section=inferred_section,
                )
            )
    return sorted(events, key=lambda e: (e.top, 0 if e.kind == "section" else 1))


def section_for_page(page_num: int, top: int, detected_section: str | None) -> str | None:
    ranges = PAGE_SECTION_RANGES.get(page_num)
    if ranges:
        for start, end, section in ranges:
            if start <= top < end:
                return section
    return detected_section


def group_words_into_lines(words: list[Word]) -> list[dict]:
    if not words:
        return []
    words = sorted(words, key=lambda w: (w.center_y, w.left))
    clusters: list[list[Word]] = []
    for word in words:
        placed = False
        for cluster in clusters:
            cluster_y = statistics.mean(w.center_y for w in cluster)
            if abs(word.center_y - cluster_y) <= 18:
                cluster.append(word)
                placed = True
                break
        if not placed:
            clusters.append([word])

    lines: list[dict] = []
    for cluster in sorted(clusters, key=lambda c: statistics.mean(w.center_y for w in c)):
        cluster.sort(key=lambda w: w.left)
        text = clean_text(" ".join(word.text for word in cluster))
        if not text:
            continue
        lines.append(
            {
                "text": text,
                "top": min(w.top for w in cluster),
                "bottom": max(w.top + w.height for w in cluster),
                "avg_conf": round(statistics.mean(w.conf for w in cluster), 2),
            }
        )
    return lines


def extract_cells(words: list[Word], page_num: int, page_width: int) -> list[dict]:
    boundaries = [page_width * ratio for ratio in PERIOD_BOUNDARY_RATIOS]
    first_col_lines = build_first_column_lines(words, page_width)
    page_lines = build_page_lines(words)
    events = build_events(first_col_lines, page_lines, page_width)
    cells: list[dict] = []

    for index, event in enumerate(events):
        if event.kind != "teacher":
            continue

        prev_teacher_top = None
        for past in reversed(events[:index]):
            if past.kind == "teacher":
                prev_teacher_top = past.top
                break

        next_top = None
        for future in events[index + 1 :]:
            if future.top > event.top and future.kind in {"teacher", "section"}:
                next_top = future.top
                break

        if prev_teacher_top is None:
            band_top = event.top - 12
        else:
            band_top = int((prev_teacher_top + event.top) / 2)

        if next_top is None:
            band_bottom = event.bottom + 40
        else:
            band_bottom = int((event.top + next_top) / 2)

        teacher_name, room = parse_teacher(event.text)
        section = section_for_page(page_num, event.top, event.section)

        for period, left, right in zip(PERIODS, boundaries[:-1], boundaries[1:]):
            cell_words = [
                w
                for w in words
                if left <= w.center_x < right and band_top <= w.center_y <= band_bottom
            ]
            cell_lines = group_words_into_lines(cell_words)
            cells.append(
                {
                    "page": page_num,
                    "section": section,
                    "teacher_display": event.text,
                    "teacher_name": teacher_name,
                    "room": room,
                    "period": period,
                    "band_top": band_top,
                    "band_bottom": band_bottom,
                    "line_count": len(cell_lines),
                    "schedule_hint": (
                        "empty"
                        if not cell_lines
                        else "full_year"
                        if len(cell_lines) == 1
                        else "semester_pair"
                        if len(cell_lines) == 2
                        else "ambiguous"
                    ),
                    "lines": cell_lines,
                }
            )
    return cells


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n")


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_line_rows(cells: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for cell in cells:
        if not cell["lines"]:
            continue
        for index, line in enumerate(cell["lines"], start=1):
            rows.append(
                {
                    "page": cell["page"],
                    "section": cell["section"] or "",
                    "teacher_name": cell["teacher_name"],
                    "room": cell["room"] or "",
                    "period": cell["period"],
                    "cell_schedule_hint": cell["schedule_hint"],
                    "line_index": index,
                    "semester_hint": (
                        "full_year"
                        if cell["schedule_hint"] == "full_year"
                        else f"semester_{index}"
                        if cell["schedule_hint"] == "semester_pair"
                        else f"line_{index}"
                    ),
                    "course_text": line["text"],
                    "ocr_avg_conf": line["avg_conf"],
                }
            )
    return rows


def validate(cells: list[dict]) -> tuple[dict, str]:
    teacher_period_pairs = {(c["page"], c["teacher_display"], c["period"]) for c in cells}
    unique_teacher_rows = {(c["page"], c["teacher_display"]) for c in cells}
    anomalies = [
        c
        for c in cells
        if c["schedule_hint"] == "ambiguous" or c["section"] is None
    ]

    spot_results = []
    for check in SPOT_CHECKS:
        matches = [
            c
            for c in cells
            if c["teacher_name"].startswith(check["teacher_prefix"]) and c["period"] == check["period"]
        ]
        passed = False
        found_lines: list[str] = []
        if matches:
            found_lines = [line["text"] for line in matches[0]["lines"]]
            normalized_found = [normalize_for_match(line) for line in found_lines]
            for expected in check["must_contain"]:
                expected_norm = normalize_for_match(expected)
                if not any(
                    expected_norm in candidate
                    or difflib.SequenceMatcher(None, expected_norm, candidate).ratio() >= 0.6
                    for candidate in normalized_found
                ):
                    break
            else:
                passed = True
        spot_results.append(
            {
                "description": check["description"],
                "passed": passed,
                "teacher_prefix": check["teacher_prefix"],
                "period": check["period"],
                "found_lines": found_lines,
            }
        )

    page_section_counts: dict[str, int] = {}
    for page, teacher in unique_teacher_rows:
        section = next(
            c["section"] or "UNKNOWN"
            for c in cells
            if c["page"] == page and c["teacher_display"] == teacher
        )
        key = f"page_{page}:{section}"
        page_section_counts[key] = page_section_counts.get(key, 0) + 1

    summary = {
        "teacher_row_count": len(unique_teacher_rows),
        "cell_count": len(cells),
        "non_empty_cell_count": sum(1 for c in cells if c["line_count"] > 0),
        "ambiguous_or_unsectioned_cells": len(anomalies),
        "spot_check_pass_count": sum(1 for result in spot_results if result["passed"]),
        "spot_check_total": len(spot_results),
        "page_section_teacher_counts": page_section_counts,
    }

    anomaly_lines = []
    for cell in anomalies[:25]:
        anomaly_lines.append(
            f"- page {cell['page']} `{cell['section'] or 'UNKNOWN'}` `{cell['teacher_name']}` `{cell['period']}` -> "
            f"{cell['schedule_hint']} / {cell['line_count']} lines"
        )
    if not anomaly_lines:
        anomaly_lines.append("- none")

    spot_lines = []
    for result in spot_results:
        status = "PASS" if result["passed"] else "FAIL"
        found = "; ".join(result["found_lines"]) if result["found_lines"] else "no cell found"
        spot_lines.append(
            f"- {status}: {result['description']} (`{result['teacher_prefix']}` `{result['period']}`) -> {found}"
        )

    counts_lines = "\n".join(
        f"- `{key}`: {count} teacher rows" for key, count in sorted(page_section_counts.items())
    )
    report = textwrap.dedent(
        f"""\
        # Master Schedule Validation

        ## Summary
        - Teacher rows parsed: {summary['teacher_row_count']}
        - Period cells parsed: {summary['cell_count']}
        - Non-empty cells: {summary['non_empty_cell_count']}
        - Ambiguous or missing-section cells: {summary['ambiguous_or_unsectioned_cells']}
        - Spot checks passed: {summary['spot_check_pass_count']} / {summary['spot_check_total']}

        ## Teacher Rows By Page And Section
        {counts_lines}

        ## Spot Checks
        {'\n'.join(spot_lines)}

        ## Notable Anomalies
        {'\n'.join(anomaly_lines)}
        """
    ).strip() + "\n"
    return summary, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf",
        default="26-27 Printable Master Schedule - TENTATIVE MASTER SCHEDULE.pdf",
        help="Path to the master schedule PDF.",
    )
    parser.add_argument(
        "--output-dir",
        default="machine_readable_master_schedule",
        help="Directory where JSON/CSV/report outputs will be written.",
    )
    args = parser.parse_args()

    repo_root = Path.cwd()
    pdf_path = (repo_root / args.pdf).resolve()
    output_dir = (repo_root / args.output_dir).resolve()
    render_dir = output_dir / "rendered"
    tsv_dir = output_dir / "ocr_tsv"

    png_paths = render_pages(pdf_path, render_dir)
    all_cells: list[dict] = []

    for page_num, png_path in enumerate(png_paths, start=1):
        tsv_dir.mkdir(parents=True, exist_ok=True)
        tsv_text = ocr_tsv(png_path)
        (tsv_dir / f"page_{page_num}.tsv").write_text(tsv_text)
        words = parse_tsv(tsv_text, page_num)
        all_cells.extend(extract_cells(words, page_num, page_width=RENDER_WIDTH))

    line_rows = build_line_rows(all_cells)
    summary, report = validate(all_cells)

    write_json(
        output_dir / "master_schedule_cells.json",
        {
            "source_pdf": str(pdf_path.name),
            "page_count": len(png_paths),
            "periods": PERIODS,
            "cells": all_cells,
            "validation_summary": summary,
        },
    )
    write_csv(output_dir / "master_schedule_lines.csv", line_rows)
    (output_dir / "validation_report.md").write_text(report)


if __name__ == "__main__":
    main()

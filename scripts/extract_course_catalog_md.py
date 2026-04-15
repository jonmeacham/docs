#!/usr/bin/env python3
"""Extract a machine-readable course catalog from markdown source.

Designed for yearly reuse:
- pass the new markdown path via `--source`
- pass a target dataset directory via `--output-dir`
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path


METADATA_PREFIXES = (
    "Graduation Requirement",
    "Graduation Requirements",
    "Course Length",
    "Grade:",
    "Grades:",
    "Grade ",
    "Prerequisite",
    "Prerequisites",
    "Recommended",
    "CTE PATHWAY",
    "CTE Pathway",
    "Opportunity Scholarship",
    "Concurrent Enrollment",
    "Fee:",
    "Optional fee:",
    "College-Level French Skills & Exam Prep",
)

NON_COURSE_TITLE_PREFIXES = (
    "there is a tuition charge",
    "dance clothes required",
    "required dual enrollment",
    "parent signed math opt out form required",
    "facilitators manage the room",
    "any additional ",
)


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_md_text(text: str) -> str:
    text = text.replace("\\!", "!")
    text = text.replace("\\-", "-")
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = text.replace("**", "")
    text = text.replace("*", "")
    return normalize_ws(text)


def normalize_key(text: str) -> str:
    text = clean_md_text(text).lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def normalized_title(title: str) -> str:
    text = clean_md_text(title).lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return normalize_ws(text)


def title_aliases(title: str) -> list[str]:
    base = normalized_title(title)
    aliases = {base}
    aliases.add(base.replace(" ce", ""))
    aliases.add(base.replace(" ap ", " "))
    aliases.add(base.replace(" and ", " "))
    aliases.add(base.replace(" 1", "").replace(" 2", "").replace(" 3", "").replace(" 4", ""))
    cleaned = {normalize_ws(alias) for alias in aliases if alias and normalize_ws(alias)}
    return sorted(cleaned)


def parse_course_length(text: str) -> tuple[str | None, int | None]:
    t = clean_md_text(text).lower()
    if "full year" in t or "year-long" in t:
        return "full_year", 2
    if "semester" in t:
        return "semester", 1
    return clean_md_text(text) or None, None


def split_requirements(value: str) -> list[str]:
    clean = clean_md_text(value)
    if not clean:
        return []
    parts = re.split(r",| or | and ", clean, flags=re.IGNORECASE)
    return [normalize_ws(part) for part in parts if normalize_ws(part)]


@dataclass
class CourseRecord:
    course_id: str
    course_name: str
    section_name: str | None
    section_slug: str | None
    source_line_start: int
    source_line_end: int
    graduation_requirement_details: str | None
    graduation_requirement_list: list[str]
    course_length_text: str | None
    course_length_normalized: str | None
    course_length_semesters: int | None
    grade_requirements: str | None
    prerequisites: list[str]
    recommended_prerequisites: list[str]
    metadata: dict[str, str]
    description: str
    audition_tryout_required: bool
    audition_tryout_evidence: list[str]
    normalized_course_name: str
    cross_reference_aliases: list[str]

    def as_dict(self) -> dict:
        return {
            "course_id": self.course_id,
            "course_name": self.course_name,
            "section_name": self.section_name,
            "section_slug": self.section_slug,
            "source_line_start": self.source_line_start,
            "source_line_end": self.source_line_end,
            "graduation_requirement_details": self.graduation_requirement_details,
            "graduation_requirement_list": self.graduation_requirement_list,
            "course_length_text": self.course_length_text,
            "course_length_normalized": self.course_length_normalized,
            "course_length_semesters": self.course_length_semesters,
            "grade_requirements": self.grade_requirements,
            "prerequisites": self.prerequisites,
            "recommended_prerequisites": self.recommended_prerequisites,
            "metadata": self.metadata,
            "description": self.description,
            "audition_tryout_required": self.audition_tryout_required,
            "audition_tryout_evidence": self.audition_tryout_evidence,
            "normalized_course_name": self.normalized_course_name,
            "cross_reference_aliases": self.cross_reference_aliases,
        }


def parse_section_heading(line: str) -> str | None:
    raw = line.strip()
    if not (raw.startswith("|") and raw.endswith("|")):
        return None
    value = normalize_ws(raw.strip("|").strip())
    if not value or value == ":---:":
        return None
    if "COURSE DESCRIPTIONS" in value:
        return None
    if len(value) < 3:
        return None
    return clean_md_text(value).upper()


def extract_bold_title(line: str) -> str | None:
    raw = line.strip()
    if "**" not in raw:
        return None
    match = re.fullmatch(r"(?:\[\s*)?\*\*(.+?)\*\*(?:\]\([^)]+\))?\s*", raw)
    if not match:
        return None
    title = clean_md_text(match.group(1))
    if not title:
        return None
    title_norm = title.lower()
    if title_norm.startswith(NON_COURSE_TITLE_PREFIXES):
        return None
    return title


def looks_like_metadata(line: str) -> bool:
    clean = clean_md_text(line)
    if not clean:
        return False
    if clean.startswith("- ") or clean.startswith("* "):
        return True
    return any(clean.startswith(prefix) for prefix in METADATA_PREFIXES)


def build_records(lines: list[str]) -> list[CourseRecord]:
    records: list[CourseRecord] = []
    current_section: str | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        section = parse_section_heading(line)
        if section:
            current_section = section
            i += 1
            continue

        title = extract_bold_title(line)
        if not title:
            i += 1
            continue

        # Avoid table-of-contents links and non-course callouts.
        if i < 28:
            i += 1
            continue

        start_line = i + 1
        j = i + 1
        block_lines: list[str] = []
        while j < len(lines):
            next_line = lines[j]
            if parse_section_heading(next_line):
                break
            next_title = extract_bold_title(next_line)
            if next_title:
                break
            block_lines.append(next_line.rstrip())
            j += 1

        metadata: dict[str, str] = {}
        description_lines: list[str] = []
        prereqs: list[str] = []
        rec_prereqs: list[str] = []
        active_list_key: str | None = None

        for raw in block_lines:
            clean = clean_md_text(raw)
            if not clean:
                active_list_key = None
                continue

            if clean.startswith("- ") or raw.strip().startswith("* "):
                bullet = clean.lstrip("-").strip()
                if active_list_key == "prerequisite":
                    prereqs.append(bullet)
                elif active_list_key == "recommended":
                    rec_prereqs.append(bullet)
                else:
                    description_lines.append(clean)
                continue

            if ":" in clean and looks_like_metadata(clean):
                key, value = clean.split(":", 1)
                key_norm = normalize_key(key)
                value = value.strip()
                if key_norm in metadata and value:
                    metadata[key_norm] = f"{metadata[key_norm]} | {value}"
                else:
                    metadata[key_norm] = value

                key_l = key.lower()
                if "prereq" in key_l:
                    active_list_key = "recommended" if "recommend" in key_l else "prerequisite"
                    if value:
                        if active_list_key == "recommended":
                            rec_prereqs.append(value)
                        else:
                            prereqs.append(value)
                else:
                    active_list_key = None
                continue

            if looks_like_metadata(clean):
                # metadata-style line without ":" (e.g., standalone notes)
                metadata_key = normalize_key(clean[:32])
                metadata[metadata_key] = clean
                active_list_key = None
                continue

            description_lines.append(clean)

        graduation = (
            metadata.get("graduation_requirement")
            or metadata.get("graduation_requirements")
            or None
        )
        length_text = metadata.get("course_length")
        # Exclude bold callouts and informational notes that are not courses.
        if not graduation and not length_text:
            i = j
            continue
        length_norm, semesters = parse_course_length(length_text or "")
        grades = metadata.get("grades") or metadata.get("grade") or metadata.get("grade_10_12") or None

        dedup_prereqs = []
        seen = set()
        for item in prereqs:
            item_clean = clean_md_text(item)
            if item_clean and item_clean not in seen:
                seen.add(item_clean)
                dedup_prereqs.append(item_clean)

        dedup_rec = []
        seen_rec = set()
        for item in rec_prereqs:
            item_clean = clean_md_text(item)
            if item_clean and item_clean not in seen_rec:
                seen_rec.add(item_clean)
                dedup_rec.append(item_clean)

        section_slug = normalize_key(current_section or "") or None
        cid = normalize_key(title)
        if not cid:
            cid = f"course_{len(records)+1:04d}"

        record = CourseRecord(
            course_id=cid,
            course_name=title,
            section_name=current_section,
            section_slug=section_slug,
            source_line_start=start_line,
            source_line_end=j,
            graduation_requirement_details=graduation,
            graduation_requirement_list=split_requirements(graduation or ""),
            course_length_text=length_text,
            course_length_normalized=length_norm,
            course_length_semesters=semesters,
            grade_requirements=grades,
            prerequisites=dedup_prereqs,
            recommended_prerequisites=dedup_rec,
            metadata=metadata,
            description=normalize_ws(" ".join(description_lines)),
            audition_tryout_required=False,
            audition_tryout_evidence=[],
            normalized_course_name=normalized_title(title),
            cross_reference_aliases=title_aliases(title),
        )

        audition_pool = " ".join(
            [
                record.course_name,
                record.description,
                " ".join(record.prerequisites),
                " ".join(record.recommended_prerequisites),
            ]
        ).lower()
        evidence = []
        if "audition" in audition_pool:
            evidence.append("audition")
        if "tryout" in audition_pool or "try-out" in audition_pool:
            evidence.append("tryout")
        record.audition_tryout_required = bool(evidence)
        record.audition_tryout_evidence = evidence

        records.append(record)
        i = j

    return records


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def validate(records: list[CourseRecord], source_name: str) -> tuple[dict, str]:
    missing_graduation = [r.course_name for r in records if not r.graduation_requirement_details]
    missing_length = [r.course_name for r in records if not r.course_length_text]
    missing_grade = [r.course_name for r in records if not r.grade_requirements]
    missing_description = [r.course_name for r in records if not r.description]
    with_prereq = [r.course_name for r in records if r.prerequisites or r.recommended_prerequisites]
    with_audition = [r.course_name for r in records if r.audition_tryout_required]

    sections: dict[str, int] = {}
    for record in records:
        key = record.section_name or "UNKNOWN"
        sections[key] = sections.get(key, 0) + 1

    summary = {
        "source_markdown": source_name,
        "course_count": len(records),
        "sections": sections,
        "courses_with_prerequisites": len(with_prereq),
        "courses_with_audition_tryout": len(with_audition),
        "missing_graduation_requirement_count": len(missing_graduation),
        "missing_course_length_count": len(missing_length),
        "missing_grade_requirements_count": len(missing_grade),
        "missing_description_count": len(missing_description),
    }

    report = (
        "# Course Catalog Validation\n\n"
        "## Summary\n"
        f"- Source markdown: `{source_name}`\n"
        f"- Parsed courses: {len(records)}\n"
        f"- Courses with prerequisites/recommended prerequisites: {len(with_prereq)}\n"
        f"- Courses with audition/tryout requirement: {len(with_audition)}\n"
        f"- Missing graduation requirement: {len(missing_graduation)}\n"
        f"- Missing course length: {len(missing_length)}\n"
        f"- Missing grade requirements: {len(missing_grade)}\n"
        f"- Missing description: {len(missing_description)}\n\n"
        "## Courses By Section\n"
        + "\n".join(f"- `{section}`: {count}" for section, count in sorted(sections.items()))
        + "\n\n## Missing Core Cross-Reference Fields (sample)\n"
        + f"- Graduation requirement: {', '.join(missing_graduation[:12]) or 'none'}\n"
        + f"- Course length: {', '.join(missing_length[:12]) or 'none'}\n"
        + f"- Grade requirements: {', '.join(missing_grade[:12]) or 'none'}\n"
    )
    return summary, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default="LHS COURSE DESCRIPTIONS 26-27.md",
        help="Path to source markdown catalog.",
    )
    parser.add_argument(
        "--output-dir",
        default="machine_readable_course_catalog",
        help="Output directory for generated artifacts.",
    )
    args = parser.parse_args()

    root = Path.cwd()
    source_path = (root / args.source).resolve()
    output_dir = (root / args.output_dir).resolve()

    lines = source_path.read_text().splitlines()
    records = build_records(lines)
    summary, report = validate(records, source_path.name)

    json_payload = {
        "source_markdown": source_path.name,
        "course_count": len(records),
        "courses": [r.as_dict() for r in records],
        "validation_summary": summary,
    }
    write_json(output_dir / "course_catalog.json", json_payload)

    flat_rows = []
    for r in records:
        flat_rows.append(
            {
                "course_id": r.course_id,
                "course_name": r.course_name,
                "section_name": r.section_name or "",
                "source_line_start": r.source_line_start,
                "source_line_end": r.source_line_end,
                "graduation_requirement_details": r.graduation_requirement_details or "",
                "course_length_text": r.course_length_text or "",
                "course_length_normalized": r.course_length_normalized or "",
                "course_length_semesters": r.course_length_semesters or "",
                "grade_requirements": r.grade_requirements or "",
                "prerequisites": " | ".join(r.prerequisites),
                "recommended_prerequisites": " | ".join(r.recommended_prerequisites),
                "normalized_course_name": r.normalized_course_name,
                "cross_reference_aliases": " | ".join(r.cross_reference_aliases),
                "description": r.description,
                "audition_tryout_required": r.audition_tryout_required,
                "audition_tryout_evidence": " | ".join(r.audition_tryout_evidence),
            }
        )
    write_csv(output_dir / "course_catalog.csv", flat_rows)

    prereq_rows = []
    for r in records:
        for prereq in r.prerequisites:
            prereq_rows.append(
                {
                    "course_id": r.course_id,
                    "course_name": r.course_name,
                    "prerequisite_type": "required",
                    "prerequisite_text": prereq,
                }
            )
        for prereq in r.recommended_prerequisites:
            prereq_rows.append(
                {
                    "course_id": r.course_id,
                    "course_name": r.course_name,
                    "prerequisite_type": "recommended",
                    "prerequisite_text": prereq,
                }
            )
    write_csv(output_dir / "course_prerequisites.csv", prereq_rows)

    (output_dir / "validation_report.md").write_text(report)
    (output_dir / "README.md").write_text(
        "# Machine-Readable Course Catalog\n\n"
        f"Generated from `{source_path.name}`.\n\n"
        "- `course_catalog.json`: rich course records with metadata and full descriptions.\n"
        "- `course_catalog.csv`: flattened course table for analysis/cross-reference.\n"
        "- `course_prerequisites.csv`: one row per prerequisite statement.\n"
        "- `validation_report.md`: extraction quality summary.\n"
    )


if __name__ == "__main__":
    main()

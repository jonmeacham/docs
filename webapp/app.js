"use strict";

const DATA_PATHS = {
  masterSchedule: "./data/master_schedule_cells.json",
  catalog: "./data/course_catalog.json",
};

const PERIODS = ["A1", "A2", "A3", "A4", "B5", "B6", "B7", "B8"];
const MOBILE_BREAKPOINT = 760;

const state = {
  offerings: [],
  requirementOptions: [],
  courseOptions: [],
};

function toIdFragment(value) {
  const normalized = normalizeText(value).replace(/\s+/g, "-");
  return normalized || "item";
}

function setResultsSummary(message) {
  const summaryEl = document.getElementById("summary");
  summaryEl.textContent = message;
}

function announceResultsStatus(message) {
  const statusEl = document.getElementById("results-status");
  statusEl.textContent = message;
}

function formatTermFilter(term) {
  if (term === "semester_1") return "Semester 1 only";
  if (term === "semester_2") return "Semester 2 only";
  if (term === "full_year") return "Full year only";
  return "";
}

function setActiveFiltersSummary(filters) {
  const parts = [];
  if (filters.course) {
    parts.push(`Course: "${document.getElementById("course").value.trim()}"`);
  }
  if (filters.period) {
    parts.push(`Period: ${filters.period}`);
  }
  if (filters.term) {
    parts.push(`Slot: ${formatTermFilter(filters.term)}`);
  }
  if (filters.requirements.length > 0) {
    parts.push(`Requirements: ${filters.requirements.join(", ")}`);
  }
  if (filters.includeAudition) {
    parts.push("Includes audition/tryout courses");
  }

  const activeEl = document.getElementById("active-filters");
  activeEl.textContent = parts.length > 0 ? `Active filters: ${parts.join(" | ")}` : "Active filters: none";
  const badgeEl = document.getElementById("active-filter-count");
  const activeCount =
    (filters.course ? 1 : 0) +
    (filters.period ? 1 : 0) +
    (filters.term ? 1 : 0) +
    filters.requirements.length +
    (filters.includeAudition ? 1 : 0);
  badgeEl.textContent = String(activeCount);
}

function normalizeText(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function dedupe(values) {
  return [...new Set(values.filter(Boolean))];
}

function canonicalRequirement(requirement) {
  const raw = String(requirement || "").trim();
  if (!raw) return "";
  const norm = normalizeText(raw);
  if (!norm) return "";
  if (norm.includes("language art")) return "Language Arts";
  if (/\bart(s)?\b/.test(norm)) return "Art";
  return raw;
}

function buildAliasIndex(courses) {
  const index = new Map();
  for (const course of courses) {
    const allAliases = dedupe([
      course.normalized_course_name,
      ...(course.cross_reference_aliases || []),
      course.course_name,
    ]);
    for (const alias of allAliases) {
      const key = normalizeText(alias);
      if (!key) continue;
      if (!index.has(key)) {
        index.set(key, []);
      }
      index.get(key).push(course);
    }
  }
  return index;
}

function resolveCatalogMatches(courseName, aliasIndex, catalogCourses) {
  const key = normalizeText(courseName);
  if (!key) return [];

  const exact = aliasIndex.get(key);
  if (exact && exact.length > 0) {
    return exact;
  }

  const fuzzy = [];
  for (const course of catalogCourses) {
    const normalized = normalizeText(course.normalized_course_name || course.course_name);
    if (!normalized) continue;
    if (normalized.includes(key) || key.includes(normalized)) {
      fuzzy.push(course);
    }
  }
  return fuzzy;
}

function buildOfferings(masterCells, catalogCourses) {
  const aliasIndex = buildAliasIndex(catalogCourses);
  const offerings = [];

  for (const cell of masterCells) {
    for (const line of cell.lines) {
      const matchedCourses = resolveCatalogMatches(line.text, aliasIndex, catalogCourses);
      const graduationRequirements = dedupe(
        matchedCourses.flatMap((course) => course.graduation_requirement_list || [])
      );
      const graduationRequirementsNorm = graduationRequirements.map(normalizeText);
      const canonicalRequirements = dedupe(graduationRequirements.map(canonicalRequirement));
      const canonicalRequirementsNorm = canonicalRequirements.map(normalizeText);
      const auditionRequired =
        matchedCourses.some((course) => course.audition_tryout_required) ||
        /\baudition\b|\btry-?out\b/i.test(line.text);
      offerings.push({
        courseName: line.text,
        courseNameNorm: normalizeText(line.text),
        period: cell.period,
        semesterHint: line.semester_hint,
        scheduleHint: cell.schedule_hint,
        section: cell.section,
        teacher: cell.teacher_name,
        room: cell.room || "",
        sourceRow: cell.source_row,
        matchedCatalogCourses: matchedCourses.map((course) => course.course_name),
        matchedCatalogDetails: matchedCourses.map((course) => ({
          courseName: course.course_name,
          sectionName: course.section_name || "",
          description: course.description || "",
          prerequisites: course.prerequisites || [],
          recommendedPrerequisites: course.recommended_prerequisites || [],
          courseLength: course.course_length_text || "",
          grades: course.grade_requirements || "",
          auditionTryoutRequired: Boolean(course.audition_tryout_required),
          auditionTryoutEvidence: course.audition_tryout_evidence || [],
        })),
        graduationRequirements,
        graduationRequirementsNorm,
        canonicalRequirements,
        canonicalRequirementsNorm,
        auditionRequired,
      });
    }
  }
  return offerings;
}

function getCompatibleByTerm(offering, selectedTerm) {
  if (!selectedTerm) return true;
  if (selectedTerm === "full_year") {
    return offering.scheduleHint === "full_year";
  }
  if (selectedTerm === "semester_1") {
    return offering.semesterHint === "semester_1";
  }
  if (selectedTerm === "semester_2") {
    return offering.semesterHint === "semester_2";
  }
  return true;
}

function createDetailContent(detailContainer, offering) {
  const details = offering.matchedCatalogDetails;
  if (!details || details.length === 0) {
    const empty = document.createElement("div");
    empty.className = "detail-item";
    empty.innerHTML = "<p><span class='label'>Catalog match:</span> No detailed course record found for this line item.</p>";
    detailContainer.appendChild(empty);
    return;
  }
  for (const detail of details) {
    const block = document.createElement("div");
    block.className = "detail-item";
    const prereqText = detail.prerequisites.length ? detail.prerequisites.join("; ") : "None listed";
    const recPrereqText = detail.recommendedPrerequisites.length
      ? detail.recommendedPrerequisites.join("; ")
      : "None listed";
    block.innerHTML = `
      <h4>${detail.courseName}</h4>
      <p><span class="label">Section:</span> ${detail.sectionName || "Unspecified"} • <span class="label">Length:</span> ${detail.courseLength || "Unspecified"} • <span class="label">Grades:</span> ${detail.grades || "Unspecified"}</p>
      <p><span class="label">Prerequisites:</span> ${prereqText}</p>
      <p><span class="label">Recommended:</span> ${recPrereqText}</p>
      <p><span class="label">Description:</span> ${detail.description || "No description available."}</p>
    `;
    detailContainer.appendChild(block);
  }
}

function addToggleHandlers(toggleBtn, detailEl, offering) {
  const toggle = (keyboardTriggered = false) => {
    const expanded = toggleBtn.getAttribute("aria-expanded") === "true";
    toggleBtn.setAttribute("aria-expanded", String(!expanded));
    toggleBtn.textContent = expanded ? "Show details" : "Hide details";
    toggleBtn.setAttribute("aria-label", `${expanded ? "Show" : "Hide"} details for ${offering.courseName} in ${offering.period}`);
    detailEl.hidden = expanded;
    if (!expanded && keyboardTriggered) {
      detailEl.focus({ preventScroll: false });
    }
  };
  let keyboardToggleFired = false;
  toggleBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    if (keyboardToggleFired) {
      keyboardToggleFired = false;
      return;
    }
    toggle(false);
  });
  toggleBtn.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    keyboardToggleFired = true;
    toggle(true);
  });
}

function renderDesktopResults(resultsEl, filtered) {
  const wrap = document.createElement("div");
  wrap.className = "results-table-wrap";
  const table = document.createElement("table");
  table.className = "results-table";
  table.innerHTML =
    "<thead><tr><th></th><th>Period</th><th>Term</th><th>Course</th><th>Teacher</th><th>Graduation Requirement</th></tr></thead>";
  const tbody = document.createElement("tbody");
  for (const [index, offering] of filtered.entries()) {
    const itemId = `${toIdFragment(offering.courseName)}-${offering.period}-${offering.sourceRow}-${index}`;
    const detailPanelId = `detail-panel-${itemId}`;
    const row = document.createElement("tr");
    const toggleCell = document.createElement("td");
    toggleCell.setAttribute("data-col", "toggle");
    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "row-toggle";
    toggleBtn.setAttribute("aria-expanded", "false");
    toggleBtn.setAttribute("aria-controls", detailPanelId);
    toggleBtn.setAttribute("aria-label", `Show details for ${offering.courseName} in ${offering.period}`);
    toggleBtn.textContent = "Show details";
    toggleCell.appendChild(toggleBtn);
    row.appendChild(toggleCell);

    const periodCell = document.createElement("td");
    periodCell.setAttribute("data-col", "period");
    periodCell.textContent = offering.period;
    row.appendChild(periodCell);
    const termCell = document.createElement("td");
    termCell.setAttribute("data-col", "term");
    termCell.textContent = offering.semesterHint.replace("_", " ");
    row.appendChild(termCell);
    const courseCell = document.createElement("td");
    courseCell.setAttribute("data-col", "course");
    courseCell.textContent = offering.courseName;
    row.appendChild(courseCell);
    const teacherCell = document.createElement("td");
    teacherCell.setAttribute("data-col", "teacher");
    teacherCell.textContent = `${offering.teacher}${offering.room ? ` (${offering.room})` : ""}`;
    row.appendChild(teacherCell);
    const reqCell = document.createElement("td");
    reqCell.setAttribute("data-col", "requirement");
    reqCell.textContent = offering.graduationRequirements.length
      ? offering.graduationRequirements.join(", ")
      : "No catalog match";
    row.appendChild(reqCell);

    const detailRow = document.createElement("tr");
    detailRow.className = "detail-row";
    detailRow.hidden = true;
    const detailTd = document.createElement("td");
    detailTd.colSpan = 6;
    const detailContent = document.createElement("div");
    detailContent.className = "detail-content";
    detailContent.id = detailPanelId;
    detailContent.setAttribute("role", "region");
    detailContent.setAttribute("aria-label", `Details for ${offering.courseName} in ${offering.period}`);
    detailContent.tabIndex = -1;
    createDetailContent(detailContent, offering);
    detailTd.appendChild(detailContent);
    detailRow.appendChild(detailTd);
    addToggleHandlers(toggleBtn, detailRow, offering);

    row.addEventListener("click", (event) => {
      if (event.target.closest("button,a,input,select,textarea")) return;
      toggleBtn.click();
    });
    tbody.appendChild(row);
    tbody.appendChild(detailRow);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  resultsEl.appendChild(wrap);
}

function renderMobileResults(resultsEl, filtered) {
  const list = document.createElement("div");
  list.className = "results-cards";
  for (const [index, offering] of filtered.entries()) {
    const itemId = `${toIdFragment(offering.courseName)}-${offering.period}-${offering.sourceRow}-${index}`;
    const detailPanelId = `card-detail-${itemId}`;
    const card = document.createElement("article");
    card.className = "result-card";

    const top = document.createElement("div");
    top.className = "result-card-top";
    top.innerHTML = `<p class="result-course">${offering.courseName}</p><p class="result-meta">${offering.period} • ${offering.semesterHint.replace("_", " ")}</p>`;
    card.appendChild(top);

    const teacher = document.createElement("p");
    teacher.className = "result-teacher";
    teacher.textContent = `${offering.teacher}${offering.room ? ` (${offering.room})` : ""}`;
    card.appendChild(teacher);

    const req = document.createElement("p");
    req.className = "result-req";
    req.textContent = offering.graduationRequirements.length
      ? offering.graduationRequirements.join(", ")
      : "No catalog match";
    card.appendChild(req);

    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "card-toggle";
    toggleBtn.setAttribute("aria-expanded", "false");
    toggleBtn.setAttribute("aria-controls", detailPanelId);
    toggleBtn.setAttribute("aria-label", `Show details for ${offering.courseName} in ${offering.period}`);
    toggleBtn.textContent = "Show details";
    card.appendChild(toggleBtn);

    const detail = document.createElement("div");
    detail.className = "card-detail";
    detail.id = detailPanelId;
    detail.hidden = true;
    detail.tabIndex = -1;
    detail.setAttribute("role", "region");
    detail.setAttribute("aria-label", `Details for ${offering.courseName} in ${offering.period}`);
    const detailContent = document.createElement("div");
    detailContent.className = "detail-content";
    createDetailContent(detailContent, offering);
    detail.appendChild(detailContent);
    addToggleHandlers(toggleBtn, detail, offering);
    card.appendChild(detail);
    list.appendChild(card);
  }
  resultsEl.appendChild(list);
}

function renderResults(filtered) {
  const resultsEl = document.getElementById("results");
  resultsEl.innerHTML = "";
  const countText = `${filtered.length} matching course option${filtered.length === 1 ? "" : "s"}`;
  setResultsSummary(countText);
  announceResultsStatus(countText);
  if (filtered.length === 0) {
    const div = document.createElement("div");
    div.className = "empty";
    div.textContent = "No compatible options found for the current filter combination. Try clearing one filter.";
    resultsEl.appendChild(div);
    announceResultsStatus("No compatible course options found.");
    return;
  }
  if (window.innerWidth <= MOBILE_BREAKPOINT) {
    renderMobileResults(resultsEl, filtered);
    return;
  }
  renderDesktopResults(resultsEl, filtered);
}

function currentFilters() {
  const selectedRequirements = getSelectedRequirements();
  return {
    period: document.getElementById("period").value,
    term: document.getElementById("term").value,
    requirements: selectedRequirements,
    course: normalizeText(document.getElementById("course").value),
    includeAudition: document.getElementById("exclude-audition").checked,
  };
}

function getSelectedRequirements() {
  const selectedFromChecks = [...document.querySelectorAll('#requirements-mobile-list input[type="checkbox"]:checked')].map(
    (input) => input.value
  );
  if (selectedFromChecks.length > 0) {
    return selectedFromChecks;
  }
  const requirementSelect = document.getElementById("requirements");
  return [...requirementSelect.selectedOptions].map((option) => option.value);
}

function setRequirementsSelection(values) {
  const chosen = new Set(values);
  for (const option of document.getElementById("requirements").options) {
    option.selected = chosen.has(option.value);
  }
  for (const check of document.querySelectorAll('#requirements-mobile-list input[type="checkbox"]')) {
    check.checked = chosen.has(check.value);
  }
}

function applyFilters() {
  const filters = currentFilters();
  setActiveFiltersSummary(filters);

  const filtered = state.offerings.filter((offering) => {
    if (filters.period && offering.period !== filters.period) return false;
    if (!getCompatibleByTerm(offering, filters.term)) return false;
    if (filters.course) {
      if (!offering.courseNameNorm) return false;
      if (
        !offering.courseNameNorm.includes(filters.course)
      ) {
        return false;
      }
    }
    if (filters.requirements.length > 0) {
      const selectedNorm = filters.requirements.map(normalizeText);
      const reqMatches = selectedNorm.some((selected) =>
        offering.canonicalRequirementsNorm.some((req) => req === selected || req.includes(selected))
      );
      if (!reqMatches) {
        return false;
      }
    }
    if (!filters.includeAudition && offering.auditionRequired) {
      return false;
    }
    return true;
  });

  filtered.sort((a, b) => {
    const c = a.courseName.localeCompare(b.courseName);
    if (c !== 0) return c;
    const p = PERIODS.indexOf(a.period) - PERIODS.indexOf(b.period);
    if (p !== 0) return p;
    return a.teacher.localeCompare(b.teacher);
  });

  renderResults(filtered);
}

function fillInputs() {
  const periodSelect = document.getElementById("period");
  for (const period of PERIODS) {
    const option = document.createElement("option");
    option.value = period;
    option.textContent = period;
    periodSelect.appendChild(option);
  }

  const reqSelect = document.getElementById("requirements");
  const reqMobile = document.getElementById("requirements-mobile-list");
  for (const req of state.requirementOptions) {
    const option = document.createElement("option");
    option.value = req;
    option.textContent = req;
    reqSelect.appendChild(option);

    const item = document.createElement("label");
    item.className = "mobile-requirement-item";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = req;
    item.appendChild(box);
    item.append(` ${req}`);
    reqMobile.appendChild(item);
  }

  const courseDataList = document.getElementById("course-options");
  for (const courseName of state.courseOptions) {
    const option = document.createElement("option");
    option.value = courseName;
    courseDataList.appendChild(option);
  }
}

function wireEvents() {
  ["period", "term", "requirements", "exclude-audition"].forEach((id) => {
    document.getElementById(id).addEventListener("input", applyFilters);
    document.getElementById(id).addEventListener("change", applyFilters);
  });
  document.getElementById("course").addEventListener("change", applyFilters);
  document.getElementById("requirements").addEventListener("change", () => {
    setRequirementsSelection(getSelectedRequirements());
  });
  document.getElementById("requirements-mobile-list").addEventListener("change", () => {
    setRequirementsSelection(getSelectedRequirements());
    applyFilters();
  });

  document.getElementById("clear-btn").addEventListener("click", () => {
    document.getElementById("period").value = "";
    document.getElementById("term").value = "";
    document.getElementById("exclude-audition").checked = false;
    setRequirementsSelection([]);
    document.getElementById("course").value = "";
    applyFilters();
    announceResultsStatus("All filters cleared. Showing all compatible course options.");
  });

  const openFilters = () => {
    if (window.innerWidth > MOBILE_BREAKPOINT) {
      return;
    }
    document.body.classList.add("filters-open");
    document.getElementById("open-filters-btn").setAttribute("aria-expanded", "true");
    document.getElementById("filters-backdrop").hidden = false;
  };
  const closeFilters = () => {
    document.body.classList.remove("filters-open");
    document.getElementById("open-filters-btn").setAttribute("aria-expanded", "false");
    document.getElementById("filters-backdrop").hidden = true;
  };
  document.getElementById("open-filters-btn").addEventListener("click", openFilters);
  document.getElementById("close-filters-btn").addEventListener("click", closeFilters);
  document.getElementById("apply-filters-btn").addEventListener("click", () => {
    applyFilters();
    closeFilters();
  });
  document.getElementById("filters-backdrop").addEventListener("click", closeFilters);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeFilters();
    }
  });

  document.getElementById("filters-form").addEventListener("submit", (event) => {
    event.preventDefault();
  });

  let searchTimer;
  document.getElementById("course").addEventListener("input", () => {
    if (window.innerWidth > MOBILE_BREAKPOINT) {
      applyFilters();
      return;
    }
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilters, 130);
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > MOBILE_BREAKPOINT) {
      closeFilters();
    }
    applyFilters();
  });
}

async function loadData() {
  const [masterResp, catalogResp] = await Promise.all([
    fetch(DATA_PATHS.masterSchedule),
    fetch(DATA_PATHS.catalog),
  ]);
  if (!masterResp.ok || !catalogResp.ok) {
    throw new Error("Failed to load one or more dataset files.");
  }
  const master = await masterResp.json();
  const catalog = await catalogResp.json();

  state.offerings = buildOfferings(master.cells, catalog.courses);
  state.requirementOptions = dedupe(
    catalog.courses
      .flatMap((course) => course.graduation_requirement_list || [])
      .map(canonicalRequirement)
  ).sort((a, b) => a.localeCompare(b));
  state.courseOptions = dedupe(state.offerings.map((offering) => offering.courseName)).sort((a, b) =>
    a.localeCompare(b)
  );
}

async function init() {
  try {
    await loadData();
    fillInputs();
    wireEvents();
    applyFilters();
  } catch (error) {
    const resultsEl = document.getElementById("results");
    setResultsSummary("Error loading datasets");
    announceResultsStatus("Error loading datasets.");
    resultsEl.innerHTML =
      "<div class='empty'>Unable to load course data. Confirm the site is served from this repository root and data files are present in webapp/data.</div>";
  }
}

init();

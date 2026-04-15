"use strict";

const STORAGE_KEYS = {
  current: "lhs.builder.current",
  saves: "lhs.builder.saves",
  completed: "lhs.builder.completed",
};

const PERIOD_ROWS = [
  { day: "A Day", period: "A1" },
  { day: "A Day", period: "A2" },
  { day: "A Day", period: "A3" },
  { day: "A Day", period: "A4" },
  { day: "B Day", period: "B5" },
  { day: "B Day", period: "B6" },
  { day: "B Day", period: "B7" },
  { day: "B Day", period: "B8" },
];

const DATA_PATHS = {
  masterSchedule: "./data/master_schedule_cells.json",
  catalog: "./data/course_catalog.json",
};

const AUTOSAVE_DEBOUNCE_MS = 450;

let autosaveTimer;

function nowIso() {
  return new Date().toISOString();
}

function formatDateTime(isoText) {
  if (!isoText) return "never";
  const date = new Date(isoText);
  return date.toLocaleString();
}

function blankSlot(period) {
  return {
    period,
    fullYear: false,
    semester1: "",
    semester2: "",
    teacher: "",
    notes: "",
  };
}

function blankDraft() {
  return {
    savedAt: "",
    completedAt: "",
    student: {
      name: "",
      grade: "10th Grade (2026-27)",
      counselor: "",
      studentId: "",
    },
    slots: Object.fromEntries(PERIOD_ROWS.map((row) => [row.period, blankSlot(row.period)])),
    requirements: {
      requiredClasses: "",
      electivePriorities: "",
      notes: "",
    },
  };
}

const state = {
  draft: blankDraft(),
  checkpoints: [],
  courseOptions: [],
};

function parseJsonSafe(text, fallback) {
  try {
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

function readStorage(key, fallback) {
  const raw = localStorage.getItem(key);
  if (!raw) return fallback;
  return parseJsonSafe(raw, fallback);
}

function writeStorage(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function ensureSlots(draft) {
  const next = structuredClone(draft);
  next.slots ||= {};
  for (const row of PERIOD_ROWS) {
    next.slots[row.period] = {
      ...blankSlot(row.period),
      ...(next.slots[row.period] || {}),
      period: row.period,
    };
  }
  next.student ||= blankDraft().student;
  next.requirements ||= blankDraft().requirements;
  return next;
}

function setSaveStatus(message) {
  document.getElementById("save-status").textContent = message;
}

function setCompletionStatus(completedAt) {
  const el = document.getElementById("completion-status");
  if (completedAt) {
    el.textContent = `Complete (${formatDateTime(completedAt)})`;
  } else {
    el.textContent = "Draft";
  }
}

function setValidationStatus(text, isError = false) {
  const el = document.getElementById("validation-status");
  el.textContent = text;
  el.classList.toggle("validation-error", isError);
  el.classList.toggle("validation-ok", !isError && Boolean(text));
}

function syncStudentFieldsFromState() {
  document.getElementById("student-name").value = state.draft.student.name || "";
  document.getElementById("student-grade").value = state.draft.student.grade || "";
  document.getElementById("student-counselor").value = state.draft.student.counselor || "";
  document.getElementById("student-id").value = state.draft.student.studentId || "";
  document.getElementById("required-classes").value = state.draft.requirements.requiredClasses || "";
  document.getElementById("elective-priorities").value = state.draft.requirements.electivePriorities || "";
  document.getElementById("schedule-notes").value = state.draft.requirements.notes || "";
}

function setSlotInputStates(period) {
  const slot = state.draft.slots[period];
  const sem2 = document.querySelector(`[data-period="${period}"][data-field="semester2"]`);
  sem2.disabled = slot.fullYear;
  if (slot.fullYear) {
    sem2.value = "";
  }
}

function syncSlotRowsFromState() {
  for (const row of PERIOD_ROWS) {
    const slot = state.draft.slots[row.period];
    const fullYearInput = document.querySelector(`[data-period="${row.period}"][data-field="fullYear"]`);
    const sem1Input = document.querySelector(`[data-period="${row.period}"][data-field="semester1"]`);
    const sem2Input = document.querySelector(`[data-period="${row.period}"][data-field="semester2"]`);
    const teacherInput = document.querySelector(`[data-period="${row.period}"][data-field="teacher"]`);
    const notesInput = document.querySelector(`[data-period="${row.period}"][data-field="notes"]`);
    fullYearInput.checked = Boolean(slot.fullYear);
    sem1Input.value = slot.semester1 || "";
    sem2Input.value = slot.semester2 || "";
    teacherInput.value = slot.teacher || "";
    notesInput.value = slot.notes || "";
    setSlotInputStates(row.period);
  }
}

function renderCheckpointOptions() {
  const select = document.getElementById("checkpoint-select");
  select.innerHTML = "";
  if (!state.checkpoints.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No saved checkpoints";
    select.appendChild(option);
    return;
  }
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = "Select a checkpoint...";
  select.appendChild(blank);
  for (const checkpoint of state.checkpoints) {
    const option = document.createElement("option");
    option.value = checkpoint.id;
    option.textContent = `${checkpoint.name} (${formatDateTime(checkpoint.savedAt)})`;
    select.appendChild(option);
  }
}

function hydrateFormFromState() {
  syncStudentFieldsFromState();
  syncSlotRowsFromState();
  renderPrintSummary();
  setCompletionStatus(state.draft.completedAt);
}

function buildScheduleRows() {
  const tbody = document.getElementById("schedule-rows");
  tbody.innerHTML = "";
  for (const row of PERIOD_ROWS) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.day}</td>
      <td>${row.period}</td>
      <td class="slot-full-year">
        <input type="checkbox" data-period="${row.period}" data-field="fullYear" aria-label="${row.period} full year" />
      </td>
      <td><input class="slot-input" list="course-options" data-period="${row.period}" data-field="semester1" /></td>
      <td><input class="slot-input" list="course-options" data-period="${row.period}" data-field="semester2" /></td>
      <td><input class="slot-input" data-period="${row.period}" data-field="teacher" /></td>
      <td><input class="slot-input" data-period="${row.period}" data-field="notes" /></td>
    `;
    tbody.appendChild(tr);
  }
}

function captureFormIntoState() {
  state.draft.student = {
    name: document.getElementById("student-name").value.trim(),
    grade: document.getElementById("student-grade").value.trim(),
    counselor: document.getElementById("student-counselor").value.trim(),
    studentId: document.getElementById("student-id").value.trim(),
  };
  state.draft.requirements = {
    requiredClasses: document.getElementById("required-classes").value.trim(),
    electivePriorities: document.getElementById("elective-priorities").value.trim(),
    notes: document.getElementById("schedule-notes").value.trim(),
  };
  for (const row of PERIOD_ROWS) {
    const slot = state.draft.slots[row.period];
    slot.fullYear = document.querySelector(`[data-period="${row.period}"][data-field="fullYear"]`).checked;
    slot.semester1 = document.querySelector(`[data-period="${row.period}"][data-field="semester1"]`).value.trim();
    slot.semester2 = document.querySelector(`[data-period="${row.period}"][data-field="semester2"]`).value.trim();
    slot.teacher = document.querySelector(`[data-period="${row.period}"][data-field="teacher"]`).value.trim();
    slot.notes = document.querySelector(`[data-period="${row.period}"][data-field="notes"]`).value.trim();
    if (slot.fullYear) {
      slot.semester2 = "";
    }
  }
}

function saveCurrentDraft({ autosave = false } = {}) {
  captureFormIntoState();
  state.draft.savedAt = nowIso();
  writeStorage(STORAGE_KEYS.current, state.draft);
  renderPrintSummary();
  setSaveStatus(`${autosave ? "Autosaved" : "Saved"} ${formatDateTime(state.draft.savedAt)}`);
}

function queueAutosave() {
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(() => saveCurrentDraft({ autosave: true }), AUTOSAVE_DEBOUNCE_MS);
}

function validateForCompletion() {
  const missing = [];
  captureFormIntoState();
  if (!state.draft.student.name) missing.push("Student name");
  if (!state.draft.student.grade) missing.push("Grade / year");
  for (const row of PERIOD_ROWS) {
    const slot = state.draft.slots[row.period];
    if (!slot.semester1) {
      missing.push(`${row.period} Semester 1 course`);
      continue;
    }
    if (!slot.fullYear && !slot.semester2) {
      missing.push(`${row.period} Semester 2 course`);
    }
  }
  return missing;
}

function markComplete() {
  const missing = validateForCompletion();
  if (missing.length > 0) {
    setValidationStatus(`Complete schedule first. Missing: ${missing.slice(0, 6).join(", ")}`, true);
    return;
  }
  state.draft.completedAt = nowIso();
  state.draft.savedAt = nowIso();
  writeStorage(STORAGE_KEYS.current, state.draft);
  writeStorage(STORAGE_KEYS.completed, state.draft);
  setCompletionStatus(state.draft.completedAt);
  setSaveStatus(`Saved ${formatDateTime(state.draft.savedAt)}`);
  setValidationStatus("Schedule marked complete and saved for export.");
  renderPrintSummary();
}

function saveCheckpoint() {
  saveCurrentDraft();
  const manualName = document.getElementById("checkpoint-name").value.trim();
  const checkpoint = {
    id: crypto.randomUUID(),
    name: manualName || `Checkpoint ${state.checkpoints.length + 1}`,
    savedAt: nowIso(),
    data: structuredClone(state.draft),
  };
  state.checkpoints = [checkpoint, ...state.checkpoints].slice(0, 25);
  writeStorage(STORAGE_KEYS.saves, state.checkpoints);
  renderCheckpointOptions();
  document.getElementById("checkpoint-name").value = "";
  setValidationStatus(`Saved checkpoint "${checkpoint.name}".`);
}

function restoreCheckpoint() {
  const id = document.getElementById("checkpoint-select").value;
  if (!id) {
    setValidationStatus("Select a checkpoint to restore.", true);
    return;
  }
  const checkpoint = state.checkpoints.find((item) => item.id === id);
  if (!checkpoint) {
    setValidationStatus("Selected checkpoint was not found.", true);
    return;
  }
  state.draft = ensureSlots(structuredClone(checkpoint.data));
  hydrateFormFromState();
  saveCurrentDraft();
  setValidationStatus(`Restored checkpoint "${checkpoint.name}".`);
}

function renderPrintSummary() {
  const summary = document.getElementById("print-summary");
  const student = state.draft.student;
  const req = state.draft.requirements;
  const rowsHtml = PERIOD_ROWS.map((row) => {
    const slot = state.draft.slots[row.period];
    const sem2 = slot.fullYear ? "Full Year" : slot.semester2 || "";
    return `
      <tr>
        <td>${row.day}</td>
        <td>${row.period}</td>
        <td>${slot.semester1 || ""}</td>
        <td>${sem2}</td>
        <td>${slot.teacher || ""}</td>
        <td>${slot.notes || ""}</td>
      </tr>
    `;
  }).join("");
  summary.innerHTML = `
    <h1>Lehi High Schedule Builder Summary</h1>
    <p class="print-meta"><strong>Student:</strong> ${student.name || ""} &nbsp; <strong>Grade:</strong> ${
      student.grade || ""
    } &nbsp; <strong>Counselor:</strong> ${student.counselor || ""}</p>
    <p class="print-meta"><strong>Student ID:</strong> ${student.studentId || ""} &nbsp; <strong>Saved:</strong> ${formatDateTime(
      state.draft.savedAt
    )} &nbsp; <strong>Completed:</strong> ${state.draft.completedAt ? formatDateTime(state.draft.completedAt) : "Not marked complete"}</p>
    <table>
      <thead>
        <tr><th>Day</th><th>Period</th><th>Semester 1</th><th>Semester 2 / Full Year</th><th>Teacher</th><th>Notes</th></tr>
      </thead>
      <tbody>${rowsHtml}</tbody>
    </table>
    <h2>Required Classes</h2>
    <p>${(req.requiredClasses || "").replace(/\n/g, "<br/>")}</p>
    <h2>Elective Priorities</h2>
    <p>${(req.electivePriorities || "").replace(/\n/g, "<br/>")}</p>
    <h2>Additional Notes</h2>
    <p>${(req.notes || "").replace(/\n/g, "<br/>")}</p>
  `;
}

function wireEvents() {
  document.getElementById("builder-main").addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.matches('[data-field="fullYear"]')) {
      const period = target.getAttribute("data-period");
      if (period) {
        state.draft.slots[period].fullYear = target.checked;
        setSlotInputStates(period);
      }
    }
    queueAutosave();
  });
  document.getElementById("builder-main").addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.matches('[data-field="fullYear"]')) {
      const period = target.getAttribute("data-period");
      if (period) setSlotInputStates(period);
    }
    queueAutosave();
  });

  document.getElementById("save-checkpoint-btn").addEventListener("click", saveCheckpoint);
  document.getElementById("restore-checkpoint-btn").addEventListener("click", restoreCheckpoint);
  document.getElementById("mark-complete-btn").addEventListener("click", markComplete);
  document.getElementById("export-pdf-btn").addEventListener("click", () => {
    saveCurrentDraft();
    window.print();
  });
}

async function loadCourseSuggestions() {
  try {
    const [masterResp, catalogResp] = await Promise.all([
      fetch(DATA_PATHS.masterSchedule),
      fetch(DATA_PATHS.catalog),
    ]);
    if (!masterResp.ok || !catalogResp.ok) return;
    const master = await masterResp.json();
    const catalog = await catalogResp.json();
    const namesFromMaster = (master.cells || [])
      .flatMap((cell) => (cell.lines || []).map((line) => (line.text || "").trim()))
      .filter(Boolean);
    const namesFromCatalog = (catalog.courses || []).map((course) => (course.course_name || "").trim()).filter(Boolean);
    state.courseOptions = [...new Set([...namesFromCatalog, ...namesFromMaster])].sort((a, b) => a.localeCompare(b));
  } catch {
    state.courseOptions = [];
  }
}

function renderCourseDatalist() {
  const datalist = document.getElementById("course-options");
  datalist.innerHTML = "";
  for (const course of state.courseOptions) {
    const option = document.createElement("option");
    option.value = course;
    datalist.appendChild(option);
  }
}

function loadDraftFromStorage() {
  const fromCurrent = readStorage(STORAGE_KEYS.current, null);
  const fromCompleted = readStorage(STORAGE_KEYS.completed, null);
  state.draft = ensureSlots(fromCurrent || fromCompleted || blankDraft());
  state.checkpoints = readStorage(STORAGE_KEYS.saves, []);
  if (!Array.isArray(state.checkpoints)) {
    state.checkpoints = [];
  }
}

async function init() {
  buildScheduleRows();
  loadDraftFromStorage();
  await loadCourseSuggestions();
  renderCourseDatalist();
  hydrateFormFromState();
  renderCheckpointOptions();
  wireEvents();
  if (state.draft.savedAt) {
    setSaveStatus(`Saved ${formatDateTime(state.draft.savedAt)}`);
  }
}

init();

const state = {
  runs: [],
  selectedRun: null,
  sources: [],
  selectedSource: null,
  records: [],
  offset: 0,
  limit: 50,
  query: "",
  totalRecords: 0,
  hasMore: false,
  selectedRecordIndex: null,
  selectedRecord: null,
};

const elements = {
  runList: document.getElementById("runList"),
  sourceList: document.getElementById("sourceList"),
  runCount: document.getElementById("runCount"),
  sourceCount: document.getElementById("sourceCount"),
  overviewPanel: document.getElementById("overviewPanel"),
  recordsBody: document.getElementById("recordsBody"),
  detailBody: document.getElementById("detailBody"),
  detailHint: document.getElementById("detailHint"),
  searchInput: document.getElementById("searchInput"),
  pageSizeSelect: document.getElementById("pageSizeSelect"),
  prevPageButton: document.getElementById("prevPageButton"),
  nextPageButton: document.getElementById("nextPageButton"),
  pageLabel: document.getElementById("pageLabel"),
  refreshButton: document.getElementById("refreshButton"),
  emptyStateTemplate: document.getElementById("emptyStateTemplate"),
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(value || 0);
}

function statusClass(status) {
  if (!status) {
    return "status-unknown";
  }
  return `status-${status}`;
}

function statusLabel(status) {
  if (status === "in_progress_or_interrupted") {
    return "streaming/partial";
  }
  return status || "unknown";
}

async function api(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function renderRuns() {
  elements.runList.innerHTML = "";
  elements.runCount.textContent = `${state.runs.length} found`;

  for (const run of state.runs) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "list-item";
    if (run.name === state.selectedRun) {
      item.classList.add("active");
    }

    item.innerHTML = `
      <p class="list-item-title">${escapeHtml(run.name)}</p>
      <p class="list-item-sub">${formatNumber(run.source_count)} sources</p>
    `;

    item.addEventListener("click", async () => {
      if (state.selectedRun === run.name) {
        return;
      }
      state.selectedRun = run.name;
      state.offset = 0;
      state.selectedSource = null;
      state.selectedRecord = null;
      state.selectedRecordIndex = null;
      renderRuns();
      await loadSources();
    });

    elements.runList.append(item);
  }
}

function sourceSubtitle(source) {
  const parts = [];
  parts.push(`${formatNumber(source.record_count)} records`);
  if (source.latest_jsonl) {
    parts.push(source.latest_jsonl.replace(".jsonl", ""));
  }
  return parts.join(" • ");
}

function renderSources() {
  elements.sourceList.innerHTML = "";
  elements.sourceCount.textContent = `${state.sources.length} found`;

  for (const source of state.sources) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "list-item";
    if (source.name === state.selectedSource) {
      item.classList.add("active");
    }

    item.innerHTML = `
      <div class="section-head">
        <p class="list-item-title">${escapeHtml(source.name)}</p>
        <span class="status-chip ${statusClass(source.status)}">${escapeHtml(statusLabel(source.status))}</span>
      </div>
      <p class="list-item-sub">${escapeHtml(sourceSubtitle(source))}</p>
    `;

    item.addEventListener("click", async () => {
      if (state.selectedSource === source.name) {
        return;
      }
      state.selectedSource = source.name;
      state.offset = 0;
      state.selectedRecord = null;
      state.selectedRecordIndex = null;
      renderSources();
      await loadRecords();
    });

    elements.sourceList.append(item);
  }
}

function renderOverview() {
  const source = state.sources.find((item) => item.name === state.selectedSource);
  if (!source) {
    elements.overviewPanel.innerHTML = `
      <div class="empty-state">
        <h3>Select a source</h3>
        <p>Choose a run and source to inspect records.</p>
      </div>
    `;
    return;
  }

  const latestJsonl = source.latest_jsonl || "-";
  const latestMeta = source.latest_meta || "missing";
  const notes = Array.isArray(source.notes) ? source.notes : [];

  let notice = "";
  if (!source.latest_meta && source.latest_jsonl) {
    notice = `
      <div class="notice">
        Metadata is currently missing for this source. This is handled gracefully: the viewer uses JSONL line count as live progress.
        This commonly happens while a long source (for example pentester_land) is still running or if a run was interrupted.
      </div>
    `;
  } else if (notes.length > 0) {
    notice = `
      <div class="notice">
        ${notes.map((note) => `<div>${escapeHtml(note)}</div>`).join("")}
      </div>
    `;
  }

  elements.overviewPanel.innerHTML = `
    <div class="section-head">
      <div>
        <h2>${escapeHtml(state.selectedRun)} / ${escapeHtml(source.name)}</h2>
        <p class="subtitle">Latest snapshot: ${escapeHtml(latestJsonl)}${
          source.latest_meta ? ` with metadata ${escapeHtml(latestMeta)}` : ""
        }</p>
      </div>
      <span class="status-chip ${statusClass(source.status)}">${escapeHtml(statusLabel(source.status))}</span>
    </div>

    <div class="overview-grid">
      <article class="metric">
        <p class="label">Records</p>
        <p class="value">${formatNumber(source.record_count)}</p>
      </article>
      <article class="metric">
        <p class="label">JSONL Observed</p>
        <p class="value">${formatNumber(source.jsonl_record_count || 0)}</p>
      </article>
      <article class="metric">
        <p class="label">Metadata Count</p>
        <p class="value">${source.metadata_record_count == null ? "-" : formatNumber(source.metadata_record_count)}</p>
      </article>
      <article class="metric">
        <p class="label">Status</p>
        <p class="value">${escapeHtml(statusLabel(source.status))}</p>
      </article>
    </div>

    ${notice}
  `;
}

function procedureChip(preview) {
  if (!preview || typeof preview !== "object") {
    return "-";
  }
  return `${preview.steps || 0} steps • ${preview.commands || 0} cmd • ${preview.payloads || 0} payload`;
}

function renderRecordRows() {
  const tbody = elements.recordsBody;
  tbody.innerHTML = "";

  if (!state.records.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.append(elements.emptyStateTemplate.content.cloneNode(true));
    row.append(cell);
    tbody.append(row);
    return;
  }

  for (const record of state.records) {
    const row = document.createElement("tr");
    row.className = "record-row";
    if (record.index === state.selectedRecordIndex) {
      row.classList.add("active");
    }

    const identifiers = (record.identifier_preview || [])
      .slice(0, 4)
      .map((id) => `<span class="chip mono">${escapeHtml(id)}</span>`)
      .join("");

    row.innerHTML = `
      <td class="mono tiny">${record.index}</td>
      <td>
        <div class="title-cell">
          <strong>${escapeHtml(record.title || "(untitled)")}</strong>
          <span class="uid">${escapeHtml(record.record_uid || "")}</span>
          <span class="tiny">${escapeHtml(record.description_preview || "")}</span>
        </div>
      </td>
      <td><div class="identifiers">${identifiers || "<span class='tiny'>-</span>"}</div></td>
      <td class="tiny">${record.reference_count || 0} refs<br/>${record.artifact_count || 0} artifacts</td>
      <td class="tiny">${escapeHtml(procedureChip(record.procedure))}</td>
    `;

    row.addEventListener("click", async () => {
      state.selectedRecordIndex = record.index;
      renderRecordRows();
      await loadRecordDetail(record.index);
    });

    tbody.append(row);
  }
}

function createFoldableText(text, maxLength = 1300) {
  const container = document.createElement("div");
  const content = document.createElement("div");
  content.className = "reader foldable";
  content.textContent = text || "";
  container.append(content);

  if ((text || "").length > maxLength) {
    content.classList.add("collapsed");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toggle-link";
    button.textContent = "Expand";
    button.addEventListener("click", () => {
      const collapsed = content.classList.toggle("collapsed");
      button.textContent = collapsed ? "Expand" : "Collapse";
    });
    container.append(button);
  }

  return container;
}

function renderJsonNode(key, value, depth = 0) {
  const wrapper = document.createElement("div");
  wrapper.className = "json-tree";

  if (value === null || value === undefined || typeof value !== "object") {
    wrapper.innerHTML = `<span class="mono">${escapeHtml(key)}:</span> ${escapeHtml(String(value))}`;
    return wrapper;
  }

  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item])
    : Object.entries(value);

  const details = document.createElement("details");
  details.open = depth < 1;

  const summary = document.createElement("summary");
  summary.textContent = `${key} (${Array.isArray(value) ? "array" : "object"}, ${entries.length})`;
  details.append(summary);

  for (const [childKey, childValue] of entries) {
    details.append(renderJsonNode(childKey, childValue, depth + 1));
  }

  wrapper.append(details);
  return wrapper;
}

function keyValueRows(record) {
  const rows = [
    ["record_uid", record.record_uid],
    ["source", record.source],
    ["source_record_id", record.source_record_id],
    ["title", record.title],
    ["vuln_status", record.vuln_status],
    ["published_at_utc", record.published_at_utc],
    ["modified_at_utc", record.modified_at_utc],
    ["withdrawn_at_utc", record.withdrawn_at_utc],
    ["references", (record.references || []).length],
    ["exploit_artifacts", (record.exploit_artifacts || []).length],
    ["tags", (record.tags || []).length],
  ];

  return rows
    .map(
      ([key, value]) => `
      <div class="key">${escapeHtml(String(key))}</div>
      <div class="value">${escapeHtml(value == null ? "-" : String(value))}</div>
    `
    )
    .join("");
}

function renderRecordDetail() {
  const host = elements.detailBody;
  host.innerHTML = "";

  if (!state.selectedRecord) {
    host.innerHTML = `
      <div class="empty-state">
        <h3>No selected record</h3>
        <p>Click a row to open full normalized fields and source-native raw payload.</p>
      </div>
    `;
    elements.detailHint.textContent = "Select a row";
    return;
  }

  const record = state.selectedRecord;
  elements.detailHint.textContent = `index ${state.selectedRecordIndex}`;

  const summary = document.createElement("section");
  summary.className = "block";
  summary.innerHTML = `
    <h3>Summary</h3>
    <div class="key-grid">${keyValueRows(record)}</div>
  `;
  host.append(summary);

  const ids = document.createElement("section");
  ids.className = "block";
  ids.innerHTML = `<h3>Identifiers</h3>`;
  const idWrap = document.createElement("div");
  idWrap.className = "identifiers";

  const idValues = [
    ...(record.cve_ids || []),
    ...(record.ghsa_ids || []),
    ...(record.cwe_ids || []),
  ];

  if (idValues.length === 0) {
    const muted = document.createElement("span");
    muted.className = "tiny";
    muted.textContent = "No normalized identifiers on this record.";
    idWrap.append(muted);
  } else {
    idValues.slice(0, 20).forEach((id) => {
      const chip = document.createElement("span");
      chip.className = "chip mono";
      chip.textContent = id;
      idWrap.append(chip);
    });
  }
  ids.append(idWrap);
  host.append(ids);

  const description = document.createElement("section");
  description.className = "block";
  description.innerHTML = `<h3>Description / Narrative</h3>`;
  description.append(createFoldableText(record.description || record.summary || "", 1800));
  host.append(description);

  const procedure = document.createElement("section");
  procedure.className = "block";
  procedure.innerHTML = `<h3>Procedure Evidence</h3>`;

  const proc = record.procedure || {};
  const procText = [
    `Steps: ${(proc.steps || []).length}`,
    `Commands: ${(proc.commands || []).length}`,
    `Payloads: ${(proc.payloads || []).length}`,
  ].join(" | ");
  const procSummary = document.createElement("p");
  procSummary.className = "tiny mono";
  procSummary.textContent = procText;
  procedure.append(procSummary);

  ["steps", "commands", "payloads"].forEach((field) => {
    const list = Array.isArray(proc[field]) ? proc[field] : [];
    const section = document.createElement("div");
    section.className = "block";
    section.innerHTML = `<h3>${field}</h3>`;
    if (list.length === 0) {
      const none = document.createElement("p");
      none.className = "tiny";
      none.textContent = "None extracted.";
      section.append(none);
    } else {
      const joined = list.map((item, index) => `${index + 1}. ${item}`).join("\n");
      section.append(createFoldableText(joined, 1200));
    }
    procedure.append(section);
  });
  host.append(procedure);

  const normalized = document.createElement("section");
  normalized.className = "block";
  normalized.innerHTML = `<h3>Normalized JSON</h3>`;
  normalized.append(createFoldableText(JSON.stringify(record, null, 2), 2500));
  host.append(normalized);

  const raw = document.createElement("section");
  raw.className = "block";
  raw.innerHTML = `<h3>Raw Source Payload</h3>`;
  raw.append(renderJsonNode("raw", record.raw || {}, 0));
  host.append(raw);
}

function updatePager() {
  const start = state.records.length ? state.offset + 1 : 0;
  const end = state.offset + state.records.length;
  const total = state.totalRecords;

  if (state.query) {
    elements.pageLabel.textContent = `${start}-${end} matches`;
  } else {
    elements.pageLabel.textContent = `${start}-${end} / ${formatNumber(total)}`;
  }

  elements.prevPageButton.disabled = state.offset === 0;
  elements.nextPageButton.disabled = !state.hasMore;
}

async function loadRuns() {
  const payload = await api("/api/runs");
  state.runs = payload.runs || [];

  if (!state.runs.length) {
    state.selectedRun = null;
    state.sources = [];
    state.selectedSource = null;
    renderRuns();
    renderSources();
    renderOverview();
    renderRecordRows();
    renderRecordDetail();
    return;
  }

  if (!state.selectedRun) {
    state.selectedRun = state.runs[0].name;
  }

  renderRuns();
  await loadSources();
}

async function loadSources() {
  if (!state.selectedRun) {
    return;
  }

  const payload = await api(
    `/api/runs/${encodeURIComponent(state.selectedRun)}/sources`
  );
  state.sources = payload.sources || [];

  if (!state.sources.length) {
    state.selectedSource = null;
    state.records = [];
    state.selectedRecord = null;
    state.selectedRecordIndex = null;
    renderSources();
    renderOverview();
    renderRecordRows();
    renderRecordDetail();
    updatePager();
    return;
  }

  if (!state.selectedSource || !state.sources.some((item) => item.name === state.selectedSource)) {
    state.selectedSource = state.sources[0].name;
  }

  renderSources();
  renderOverview();
  await loadRecords();
}

async function loadRecords() {
  if (!state.selectedRun || !state.selectedSource) {
    return;
  }

  const url = new URL(
    `/api/runs/${encodeURIComponent(state.selectedRun)}/sources/${encodeURIComponent(
      state.selectedSource
    )}/records`,
    window.location.origin
  );
  url.searchParams.set("offset", String(state.offset));
  url.searchParams.set("limit", String(state.limit));
  if (state.query) {
    url.searchParams.set("q", state.query);
  }

  const payload = await api(url.toString());
  const recordsPayload = payload.records || {};

  state.records = recordsPayload.records || [];
  state.totalRecords = Number(recordsPayload.total_records || 0);
  state.hasMore = Boolean(recordsPayload.has_more);

  const latestSummary = payload.summary;
  state.sources = state.sources.map((source) =>
    source.name === state.selectedSource ? latestSummary : source
  );

  renderSources();
  renderOverview();
  renderRecordRows();
  updatePager();

  if (!state.records.length) {
    state.selectedRecord = null;
    state.selectedRecordIndex = null;
    renderRecordDetail();
    return;
  }

  if (
    state.selectedRecordIndex == null ||
    !state.records.some((record) => record.index === state.selectedRecordIndex)
  ) {
    state.selectedRecordIndex = state.records[0].index;
  }

  await loadRecordDetail(state.selectedRecordIndex);
}

async function loadRecordDetail(index) {
  if (!state.selectedRun || !state.selectedSource) {
    return;
  }

  const url = new URL(
    `/api/runs/${encodeURIComponent(state.selectedRun)}/sources/${encodeURIComponent(
      state.selectedSource
    )}/record`,
    window.location.origin
  );
  url.searchParams.set("index", String(index));

  const payload = await api(url.toString());
  state.selectedRecord = payload.record.record;
  state.selectedRecordIndex = payload.record.index;
  renderRecordRows();
  renderRecordDetail();
}

async function refreshAll() {
  try {
    await loadRuns();
  } catch (error) {
    elements.overviewPanel.innerHTML = `
      <div class="notice">
        Failed to load dataset information: ${escapeHtml(error.message)}
      </div>
    `;
    elements.recordsBody.innerHTML = "";
    elements.detailBody.innerHTML = "";
    elements.pageLabel.textContent = "error";
  }
}

function wireEvents() {
  elements.refreshButton.addEventListener("click", async () => {
    await refreshAll();
  });

  let searchTimer = null;
  elements.searchInput.addEventListener("input", () => {
    if (searchTimer) {
      clearTimeout(searchTimer);
    }
    searchTimer = setTimeout(async () => {
      state.query = elements.searchInput.value.trim();
      state.offset = 0;
      await loadRecords();
    }, 220);
  });

  elements.pageSizeSelect.addEventListener("change", async () => {
    state.limit = Number(elements.pageSizeSelect.value);
    state.offset = 0;
    await loadRecords();
  });

  elements.prevPageButton.addEventListener("click", async () => {
    if (state.offset === 0) {
      return;
    }
    state.offset = Math.max(0, state.offset - state.limit);
    await loadRecords();
  });

  elements.nextPageButton.addEventListener("click", async () => {
    if (!state.hasMore) {
      return;
    }
    state.offset += state.limit;
    await loadRecords();
  });
}

async function bootstrap() {
  wireEvents();
  await refreshAll();
}

bootstrap();

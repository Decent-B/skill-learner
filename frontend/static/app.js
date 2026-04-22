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
  mobilePane: "sidebar",
};

function getByAnyId(...ids) {
  for (const id of ids) {
    const node = document.getElementById(id);
    if (node) {
      return node;
    }
  }
  return null;
}

const elements = {
  shell: document.getElementById("shell"),
  runList: getByAnyId("runList", "benchmarkList"),
  sourceList: document.getElementById("sourceList"),
  runCount: getByAnyId("runCount", "benchmarkCount"),
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
  resizerLeft: document.getElementById("resizerLeft"),
  resizerRight: document.getElementById("resizerRight"),
  tabButtons: Array.from(document.querySelectorAll("[data-pane-target]")),
  panes: Array.from(document.querySelectorAll("[data-pane]")),
};

const REQUIRED_ELEMENTS = [
  ["runList", elements.runList],
  ["sourceList", elements.sourceList],
  ["runCount", elements.runCount],
  ["sourceCount", elements.sourceCount],
  ["overviewPanel", elements.overviewPanel],
  ["recordsBody", elements.recordsBody],
  ["detailBody", elements.detailBody],
  ["detailHint", elements.detailHint],
  ["searchInput", elements.searchInput],
  ["pageSizeSelect", elements.pageSizeSelect],
  ["prevPageButton", elements.prevPageButton],
  ["nextPageButton", elements.nextPageButton],
  ["pageLabel", elements.pageLabel],
  ["refreshButton", elements.refreshButton],
  ["emptyStateTemplate", elements.emptyStateTemplate],
  ["shell", elements.shell],
];

function ensureDomWiring() {
  const missing = REQUIRED_ELEMENTS.filter(([, node]) => !node).map(([name]) => name);
  if (!missing.length) {
    return;
  }
  const message = `Frontend wiring error: missing element(s): ${missing.join(", ")}`;
  document.body.innerHTML = `<main style="padding:2rem;font-family:system-ui"><h1>UI wiring error</h1><p>${escapeHtml(message)}</p></main>`;
  throw new Error(message);
}

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

function looksLikeHttpUrl(value) {
  if (typeof value !== "string") {
    return false;
  }
  const text = value.trim();
  if (!text) {
    return false;
  }
  try {
    const parsed = new URL(text);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function truncateMiddle(text, maxLength = 88) {
  if (text.length <= maxLength) {
    return text;
  }
  const left = Math.max(20, Math.floor(maxLength * 0.65));
  const right = Math.max(10, maxLength - left - 1);
  return `${text.slice(0, left)}…${text.slice(-right)}`;
}

function createExternalLink(url, className = "truncated-link", maxLength = 88) {
  const link = document.createElement("a");
  link.href = url;
  link.className = className;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.title = url;
  link.textContent = truncateMiddle(url, maxLength);
  return link;
}

function createTruncatableText(text, previewLength = 240, className = "") {
  const value = String(text || "");
  const host = document.createElement("span");
  host.className = `truncatable ${className}`.trim();

  if (value.length <= previewLength) {
    host.textContent = value;
    return host;
  }

  const preview = document.createElement("span");
  preview.className = "truncatable-preview";
  preview.textContent = `${value.slice(0, previewLength)}…`;

  const full = document.createElement("span");
  full.className = "truncatable-full";
  full.textContent = value;
  full.hidden = true;

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "toggle-link truncatable-toggle";
  toggle.textContent = "Expand";
  toggle.addEventListener("click", () => {
    const expanded = !full.hidden;
    full.hidden = expanded;
    preview.hidden = !expanded;
    toggle.textContent = expanded ? "Expand" : "Collapse";
  });

  host.append(preview, full, toggle);
  return host;
}

function createValueNode(value) {
  if (value == null) {
    const empty = document.createElement("span");
    empty.textContent = "-";
    return empty;
  }

  if (typeof value === "string" && looksLikeHttpUrl(value)) {
    return createExternalLink(value, "truncated-link mono", 76);
  }

  const text = String(value);
  if (text.length > 180) {
    return createTruncatableText(text, 140, "value-text");
  }

  const plain = document.createElement("span");
  plain.className = "value-text";
  plain.textContent = text;
  return plain;
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

function isMobileViewport() {
  return window.matchMedia("(max-width: 980px)").matches;
}

function setMobilePane(target) {
  state.mobilePane = target;
  elements.panes.forEach((pane) => {
    pane.classList.toggle("active", pane.dataset.pane === target);
  });
  elements.tabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.paneTarget === target);
  });
}

function initPaneTabs() {
  elements.tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setMobilePane(button.dataset.paneTarget || "main");
    });
  });

  if (isMobileViewport()) {
    setMobilePane("sidebar");
  }

  window.addEventListener("resize", () => {
    if (!isMobileViewport()) {
      elements.panes.forEach((pane) => pane.classList.add("active"));
      elements.tabButtons.forEach((button) => button.classList.remove("active"));
      return;
    }
    setMobilePane(state.mobilePane);
  });
}

function initPaneResizers() {
  if (!elements.shell || !elements.resizerLeft || !elements.resizerRight) {
    return;
  }

  const storageKey = "skill-learner-observatory-splits";
  const stored = localStorage.getItem(storageKey);
  if (stored) {
    try {
      const parsed = JSON.parse(stored);
      if (typeof parsed.sidebar === "number") {
        elements.shell.style.setProperty("--sidebar-width", `${parsed.sidebar}px`);
      }
      if (typeof parsed.detail === "number") {
        elements.shell.style.setProperty("--detail-width", `${parsed.detail}px`);
      }
    } catch {
      // Ignore invalid local storage payload.
    }
  }

  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

  function saveSplits() {
    const sidebar = Number.parseFloat(
      getComputedStyle(elements.shell).getPropertyValue("--sidebar-width")
    );
    const detail = Number.parseFloat(
      getComputedStyle(elements.shell).getPropertyValue("--detail-width")
    );
    localStorage.setItem(storageKey, JSON.stringify({ sidebar, detail }));
  }

  function startDrag(mode, event) {
    if (isMobileViewport()) {
      return;
    }
    event.preventDefault();
    const shellRect = elements.shell.getBoundingClientRect();
    const sidebarRect = document.querySelector("[data-pane='sidebar']")?.getBoundingClientRect();
    const detailRect = document.querySelector("[data-pane='detail']")?.getBoundingClientRect();

    if (!sidebarRect || !detailRect) {
      return;
    }

    const startX = event.clientX;
    const startSidebar = sidebarRect.width;
    const startDetail = detailRect.width;

    function onMove(moveEvent) {
      const delta = moveEvent.clientX - startX;
      if (mode === "left") {
        const next = clamp(startSidebar + delta, 220, Math.max(340, shellRect.width * 0.45));
        elements.shell.style.setProperty("--sidebar-width", `${next}px`);
      } else {
        const next = clamp(startDetail - delta, 300, Math.max(420, shellRect.width * 0.5));
        elements.shell.style.setProperty("--detail-width", `${next}px`);
      }
    }

    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      document.body.classList.remove("resizing");
      saveSplits();
    }

    document.body.classList.add("resizing");
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  elements.resizerLeft.addEventListener("pointerdown", (event) => startDrag("left", event));
  elements.resizerRight.addEventListener("pointerdown", (event) => startDrag("right", event));
}

function safeHtml(node, html) {
  if (node) {
    node.innerHTML = html;
  }
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
  if (!elements.runList || !elements.runCount) {
    return;
  }

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
      if (isMobileViewport()) {
        setMobilePane("main");
      }
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
  if (!elements.sourceList || !elements.sourceCount) {
    return;
  }

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
        <span class="status-chip ${statusClass(source.status)}" title="${escapeHtml(statusLabel(source.status))}">${escapeHtml(statusLabel(source.status))}</span>
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
      if (isMobileViewport()) {
        setMobilePane("main");
      }
    });

    elements.sourceList.append(item);
  }
}

function renderOverview() {
  if (!elements.overviewPanel) {
    return;
  }

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
        Metadata is currently missing for this source. The viewer uses JSONL line count as live progress.
        This is expected while long sources are still downloading or when a run stops early.
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
        <span class="status-chip ${statusClass(source.status)}" title="${escapeHtml(statusLabel(source.status))}">${escapeHtml(statusLabel(source.status))}</span>
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
  if (!elements.recordsBody || !elements.emptyStateTemplate) {
    return;
  }

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
      if (isMobileViewport()) {
        setMobilePane("detail");
      }
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
    const line = document.createElement("div");
    line.className = "json-line";

    const keyNode = document.createElement("span");
    keyNode.className = "json-key mono";
    keyNode.textContent = `${key}:`;
    line.append(keyNode);

    if (typeof value === "string") {
      line.append(document.createTextNode(" "));
      if (looksLikeHttpUrl(value)) {
        line.append(document.createTextNode('"'));
        line.append(createExternalLink(value, "json-link mono", 84));
        line.append(document.createTextNode('"'));
      } else {
        const quoted = createTruncatableText(value, 220, "json-string");
        const host = document.createElement("span");
        host.className = "json-string-host";
        host.append(document.createTextNode('"'));
        host.append(quoted);
        host.append(document.createTextNode('"'));
        line.append(host);
      }
    } else if (typeof value === "number") {
      const numberNode = document.createElement("span");
      numberNode.className = "json-number";
      numberNode.textContent = ` ${String(value)}`;
      line.append(numberNode);
    } else if (typeof value === "boolean") {
      const boolNode = document.createElement("span");
      boolNode.className = "json-boolean";
      boolNode.textContent = ` ${String(value)}`;
      line.append(boolNode);
    } else if (value === null) {
      const nullNode = document.createElement("span");
      nullNode.className = "json-null";
      nullNode.textContent = " null";
      line.append(nullNode);
    } else {
      line.append(document.createTextNode(` ${String(value)}`));
    }

    wrapper.append(line);
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

function syntaxHighlightJson(value) {
  const jsonText = JSON.stringify(value, null, 2);
  const escaped = escapeHtml(jsonText);
  return escaped.replace(
    /("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"\s*:?)|(\btrue\b|\bfalse\b)|(\bnull\b)|(-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?)/g,
    (match, stringToken, boolToken, nullToken, numberToken) => {
      if (stringToken) {
        if (stringToken.endsWith(":")) {
          return `<span class="json-key">${stringToken}</span>`;
        }
        try {
          const parsed = JSON.parse(stringToken);
          if (typeof parsed === "string" && looksLikeHttpUrl(parsed)) {
            const safeUrl = escapeHtml(parsed);
            const label = escapeHtml(truncateMiddle(parsed, 84));
            return `<span class="json-string">"<a class="json-link mono" href="${safeUrl}" title="${safeUrl}" target="_blank" rel="noopener noreferrer">${label}</a>"</span>`;
          }
        } catch {
          // Fall through to generic token highlighting.
        }
        return `<span class="json-string">${stringToken}</span>`;
      }
      if (boolToken) {
        return `<span class="json-boolean">${boolToken}</span>`;
      }
      if (nullToken) {
        return `<span class="json-null">${nullToken}</span>`;
      }
      if (numberToken) {
        return `<span class="json-number">${numberToken}</span>`;
      }
      return match;
    }
  );
}

function createPrettyJsonSection(title, value, buttonLabel = "Copy JSON") {
  const section = document.createElement("section");
  section.className = "block";

  const head = document.createElement("div");
  head.className = "json-head";

  const heading = document.createElement("h3");
  heading.textContent = title;
  head.append(heading);

  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "btn btn-inline";
  copyButton.textContent = buttonLabel;
  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(value, null, 2));
      copyButton.textContent = "Copied";
      setTimeout(() => {
        copyButton.textContent = buttonLabel;
      }, 1200);
    } catch {
      copyButton.textContent = "Copy failed";
      setTimeout(() => {
        copyButton.textContent = buttonLabel;
      }, 1400);
    }
  });
  head.append(copyButton);

  const pre = document.createElement("pre");
  pre.className = "json-pre foldable collapsed";
  pre.innerHTML = syntaxHighlightJson(value);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "toggle-link";
  toggle.textContent = "Expand";
  toggle.addEventListener("click", () => {
    const collapsed = pre.classList.toggle("collapsed");
    toggle.textContent = collapsed ? "Expand" : "Collapse";
  });

  section.append(head, pre, toggle);
  return section;
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

  const fragment = document.createDocumentFragment();
  for (const [key, value] of rows) {
    const keyNode = document.createElement("div");
    keyNode.className = "key";
    keyNode.textContent = String(key);

    const valueNode = document.createElement("div");
    valueNode.className = "value";
    valueNode.append(createValueNode(value));

    fragment.append(keyNode, valueNode);
  }
  return fragment;
}

function renderRecordDetail() {
  if (!elements.detailBody || !elements.detailHint) {
    return;
  }

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
  summary.innerHTML = `<h3>Summary</h3><div class="key-grid"></div>`;
  const keyGrid = summary.querySelector(".key-grid");
  if (keyGrid) {
    keyGrid.append(keyValueRows(record));
  }
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
    idValues.slice(0, 28).forEach((id) => {
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
  description.append(createFoldableText(record.description || record.summary || "", 2000));
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

  host.append(createPrettyJsonSection("Normalized JSON", record, "Copy normalized"));

  const rawTree = document.createElement("section");
  rawTree.className = "block";
  rawTree.innerHTML = `<h3>Raw Source Payload Tree</h3>`;
  rawTree.append(renderJsonNode("raw", record.raw || {}, 0));
  host.append(rawTree);

  host.append(createPrettyJsonSection("Raw Source JSON", record.raw || {}, "Copy raw"));
}

function updatePager() {
  if (!elements.pageLabel || !elements.prevPageButton || !elements.nextPageButton) {
    return;
  }

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
  state.runs = payload.runs || payload.benchmarks || [];

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

  const payload = await api(`/api/runs/${encodeURIComponent(state.selectedRun)}/sources`);
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
    safeHtml(
      elements.overviewPanel,
      `<div class="notice">Failed to load dataset information: ${escapeHtml(error.message)}</div>`
    );
    safeHtml(elements.recordsBody, "");
    safeHtml(elements.detailBody, "");
    if (elements.pageLabel) {
      elements.pageLabel.textContent = "error";
    }
  }
}

function wireEvents() {
  if (elements.refreshButton) {
    elements.refreshButton.addEventListener("click", async () => {
      await refreshAll();
    });
  }

  let searchTimer = null;
  if (elements.searchInput) {
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
  }

  if (elements.pageSizeSelect) {
    elements.pageSizeSelect.addEventListener("change", async () => {
      state.limit = Number(elements.pageSizeSelect.value);
      state.offset = 0;
      await loadRecords();
    });
  }

  if (elements.prevPageButton) {
    elements.prevPageButton.addEventListener("click", async () => {
      if (state.offset === 0) {
        return;
      }
      state.offset = Math.max(0, state.offset - state.limit);
      await loadRecords();
    });
  }

  if (elements.nextPageButton) {
    elements.nextPageButton.addEventListener("click", async () => {
      if (!state.hasMore) {
        return;
      }
      state.offset += state.limit;
      await loadRecords();
    });
  }
}

async function bootstrap() {
  ensureDomWiring();
  initPaneTabs();
  initPaneResizers();
  wireEvents();
  await refreshAll();
}

bootstrap();

const fileInput = document.querySelector("#fileInput");
const dropZone = document.querySelector("#dropZone");
const previewGrid = document.querySelector("#previewGrid");
const previewTemplate = document.querySelector("#previewTemplate");
const requirementsInput = document.querySelector("#requirements");
const contextInput = document.querySelector("#context");
const generateButton = document.querySelector("#generateButton");
const clearButton = document.querySelector("#clearButton");
const downloadButton = document.querySelector("#downloadButton");
const copyButton = document.querySelector("#copyButton");
const statusText = document.querySelector("#statusText");
const caseCount = document.querySelector("#caseCount");
const priorityMix = document.querySelector("#priorityMix");
const progressBar = document.querySelector("#progressBar");
const searchInput = document.querySelector("#searchInput");
const cardsView = document.querySelector("#cardsView");
const tableView = document.querySelector("#tableView");
const streamView = document.querySelector("#streamView");
const caseTableBody = document.querySelector("#caseTableBody");
const themeToggle = document.querySelector("#themeToggle");

let selectedFiles = [];
let cases = [];
let downloadUrl = "";
let activeView = "cards";
let isGenerating = false;

renderEmptyState();

fileInput.addEventListener("change", () => {
  addFiles([...fileInput.files]);
  fileInput.value = "";
});

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
});

dropZone.addEventListener("drop", (event) => {
  addFiles([...event.dataTransfer.files]);
});

generateButton.addEventListener("click", startGeneration);
clearButton.addEventListener("click", resetAll);
downloadButton.addEventListener("click", () => {
  if (downloadUrl) {
    window.location.href = downloadUrl;
  }
});
copyButton.addEventListener("click", copyCases);
searchInput.addEventListener("input", renderCases);
themeToggle.addEventListener("click", () => {
  document.body.classList.toggle("dark");
});

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => {
    activeView = button.dataset.view;
    document.querySelectorAll(".tab-button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    updateActiveView();
  });
});

function addFiles(files) {
  const imageFiles = files.filter((file) => file.type.startsWith("image/"));
  for (const file of imageFiles) {
    const duplicated = selectedFiles.some(
      (item) => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified,
    );
    if (!duplicated) {
      selectedFiles.push(file);
    }
  }
  renderPreviews();
}

function renderPreviews() {
  previewGrid.replaceChildren();
  for (const [index, file] of selectedFiles.entries()) {
    const node = previewTemplate.content.firstElementChild.cloneNode(true);
    const image = node.querySelector("img");
    const caption = node.querySelector("figcaption");
    const removeButton = node.querySelector("button");
    image.src = URL.createObjectURL(file);
    image.alt = file.name;
    caption.textContent = file.name;
    removeButton.addEventListener("click", () => {
      selectedFiles.splice(index, 1);
      renderPreviews();
    });
    previewGrid.appendChild(node);
  }
}

async function startGeneration() {
  if (isGenerating) return;
  if (!selectedFiles.length && !requirementsInput.value.trim() && !contextInput.value.trim()) {
    showToast("请至少上传图片或填写需求背景。");
    return;
  }

  const formData = new FormData();
  selectedFiles.forEach((file) => formData.append("images", file));
  formData.append("requirements", requirementsInput.value.trim());
  formData.append("context", contextInput.value.trim());

  prepareGenerationState();

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      body: formData,
    });

    if (!response.ok || !response.body) {
      const text = await response.text();
      throw new Error(text || "生成请求失败");
    }

    await readSseStream(response.body);
  } catch (error) {
    setStatus("生成失败");
    appendLog(error.message || String(error));
    showToast(error.message || "生成失败");
  } finally {
    isGenerating = false;
    generateButton.disabled = false;
    clearButton.disabled = false;
  }
}

function prepareGenerationState() {
  isGenerating = true;
  cases = [];
  downloadUrl = "";
  generateButton.disabled = true;
  clearButton.disabled = true;
  downloadButton.disabled = true;
  copyButton.disabled = true;
  streamView.replaceChildren();
  setStatus("生成中");
  updateProgress(6);
  updateStats();
  renderCases();
}

async function readSseStream(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\n\n/);
    buffer = blocks.pop() || "";
    blocks.forEach(processSseBlock);
  }

  if (buffer.trim()) {
    processSseBlock(buffer);
  }
}

function processSseBlock(block) {
  const lines = block.split(/\r?\n/);
  let eventName = "message";
  const dataLines = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!dataLines.length) return;

  let data;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    data = { text: dataLines.join("\n") };
  }

  handleEvent(eventName, data);
}

function handleEvent(eventName, data) {
  if (eventName === "status" || eventName === "thought") {
    setStatus(data.text || "生成中");
    appendLog(data.text || "");
    updateProgress(Math.min(86, 12 + cases.length * 4));
    return;
  }

  if (eventName === "case") {
    cases.push(data);
    appendLog(`生成 ${data.id || ""}：${data.title || ""}`);
    updateStats();
    renderCases();
    updateProgress(Math.min(92, 18 + cases.length * 4));
    return;
  }

  if (eventName === "done") {
    downloadUrl = data.downloadUrl;
    setStatus(`完成，已保存 ${data.count || cases.length} 条`);
    updateProgress(100);
    downloadButton.disabled = !downloadUrl;
    copyButton.disabled = !cases.length;
    appendLog("Excel 已生成。");
    return;
  }

  if (eventName === "error") {
    setStatus("生成失败");
    appendLog(data.message || "生成失败");
    showToast(data.message || "生成失败");
  }
}

function renderCases() {
  const keyword = searchInput.value.trim().toLowerCase();
  const visibleCases = cases.filter((item) => {
    if (!keyword) return true;
    return JSON.stringify(item).toLowerCase().includes(keyword);
  });

  cardsView.replaceChildren();
  caseTableBody.replaceChildren();

  if (!visibleCases.length) {
    renderEmptyState();
    return;
  }

  for (const item of visibleCases) {
    cardsView.appendChild(createCaseCard(item));
    caseTableBody.appendChild(createTableRow(item));
  }
}

function renderEmptyState() {
  cardsView.replaceChildren();
  caseTableBody.replaceChildren();
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.textContent = cases.length ? "没有匹配的用例" : "等待生成";
  cardsView.appendChild(empty);
}

function createCaseCard(item) {
  const card = document.createElement("article");
  card.className = "case-card";
  card.innerHTML = `
    <header>
      <div class="case-meta">
        <span class="pill ${priorityClass(item.priority)}">${escapeHtml(item.priority || "P1")}</span>
        <span class="pill">${escapeHtml(item.id || "")}</span>
        <span class="pill">${escapeHtml(item.case_type || "功能")}</span>
      </div>
      <h3>${escapeHtml(item.title || "未命名用例")}</h3>
      <div class="pill">${escapeHtml(item.module || "核心流程")}</div>
    </header>
    ${sectionHtml("场景", item.scenario)}
    ${sectionHtml("步骤", item.steps, "ol")}
    ${sectionHtml("预期", item.expected_results, "ul")}
  `;
  return card;
}

function createTableRow(item) {
  const row = document.createElement("tr");
  row.innerHTML = `
    <td>${escapeHtml(item.id || "")}</td>
    <td>${escapeHtml(item.module || "")}</td>
    <td>${escapeHtml(item.title || "")}</td>
    <td><span class="pill ${priorityClass(item.priority)}">${escapeHtml(item.priority || "")}</span></td>
    <td>${escapeHtml(item.case_type || "")}</td>
    <td>${listToText(item.steps)}</td>
    <td>${listToText(item.expected_results)}</td>
  `;
  return row;
}

function sectionHtml(title, value, listType = "p") {
  const content = Array.isArray(value) ? value.filter(Boolean) : String(value || "").trim();
  if (Array.isArray(content) && !content.length) return "";
  if (!Array.isArray(content) && !content) return "";
  if (Array.isArray(content)) {
    const items = content.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    return `<section class="case-section"><h4>${title}</h4><${listType}>${items}</${listType}></section>`;
  }
  return `<section class="case-section"><h4>${title}</h4><p>${escapeHtml(content)}</p></section>`;
}

function listToText(value) {
  if (!Array.isArray(value)) {
    return escapeHtml(value || "");
  }
  return value.map((item, index) => `${index + 1}. ${escapeHtml(item)}`).join("<br>");
}

function priorityClass(priority) {
  return `priority-${String(priority || "p1").toLowerCase()}`;
}

function updateStats() {
  caseCount.textContent = String(cases.length);
  const priorityCounter = cases.reduce((acc, item) => {
    const key = item.priority || "P1";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  priorityMix.textContent = Object.entries(priorityCounter)
    .map(([key, value]) => `${key}:${value}`)
    .join(" / ") || "-";
}

function updateActiveView() {
  cardsView.classList.toggle("active", activeView === "cards");
  tableView.classList.toggle("active", activeView === "table");
  streamView.classList.toggle("active", activeView === "stream");
}

function appendLog(text) {
  if (!text) return;
  const line = document.createElement("div");
  line.className = "log-line";
  const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  line.innerHTML = `<time>${time}</time><span>${escapeHtml(text)}</span>`;
  streamView.appendChild(line);
  streamView.scrollTop = streamView.scrollHeight;
}

function setStatus(text) {
  statusText.textContent = text;
}

function updateProgress(value) {
  progressBar.style.width = `${Math.max(0, Math.min(100, value))}%`;
}

function resetAll() {
  selectedFiles = [];
  cases = [];
  downloadUrl = "";
  requirementsInput.value = "";
  contextInput.value = "";
  downloadButton.disabled = true;
  copyButton.disabled = true;
  previewGrid.replaceChildren();
  streamView.replaceChildren();
  setStatus("待生成");
  updateProgress(0);
  updateStats();
  renderCases();
}

async function copyCases() {
  try {
    await navigator.clipboard.writeText(JSON.stringify(cases, null, 2));
    showToast("已复制。");
  } catch {
    showToast("复制失败。");
  }
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 2600);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

<template>
  <div class="app-shell">
    <aside class="sidebar" aria-label="主导航">
      <div class="side-brand">
        <span class="brand-mark" aria-hidden="true">QA</span>
        <div>
          <p class="eyebrow">TestOps AI</p>
          <strong>测试中枢</strong>
        </div>
      </div>

      <nav class="side-nav">
        <a class="nav-item active" href="#inputTitle">
          <FileText aria-hidden="true" />
          工作台
        </a>
        <a class="nav-item" href="#resultTitle">
          <BarChart3 aria-hidden="true" />
          用例矩阵
        </a>
        <a class="nav-item" href="#streamView">
          <List aria-hidden="true" />
          流式日志
        </a>
        <a class="nav-item" href="#apiRunnerTitle" @click="fetchApiRunHistory">
          <PlayCircle aria-hidden="true" />
          接口执行
        </a>
        <a class="nav-item" href="#historyTitle" @click="refreshHistory">
          <History aria-hidden="true" />
          历史记录
        </a>
        <a class="nav-item" href="#downloadButton">
          <FileDown aria-hidden="true" />
          Excel 导出
        </a>
      </nav>

      <div class="side-card">
        <span class="side-card-label">MODEL LINK</span>
        <strong>OpenAI-compatible</strong>
        <p>支持图片、表格、文档、文本、链接、MySQL 历史记录与本地演示回退。</p>
      </div>

      <div class="side-metrics">
        <div>
          <span>Coverage</span>
          <strong>P0-P3</strong>
        </div>
        <div>
          <span>Mode</span>
          <strong>SSE</strong>
        </div>
      </div>
    </aside>

    <main class="main-shell">
      <header class="topbar">
        <div class="hero-copy">
          <p class="eyebrow">AI QA COMMAND CENTER</p>
          <h1>测试用例智能生成系统</h1>
          <p class="hero-subtitle">图片材料、业务上下文和测试要求进入同一条生成链路，实时输出结构化测试用例。</p>
        </div>
        <div class="top-actions">
          <button class="icon-button" type="button" aria-label="切换主题" title="切换主题" @click="toggleTheme">
            <Moon aria-hidden="true" />
          </button>
        </div>
      </header>

      <section class="signal-row" aria-label="系统状态">
        <div class="signal-card">
          <span>INPUT</span>
          <strong>Multi-source Input</strong>
        </div>
        <div class="signal-card">
          <span>ENGINE</span>
          <strong>Vision LLM</strong>
        </div>
        <div class="signal-card">
          <span>OUTPUT</span>
          <strong>Cases + XLSX</strong>
        </div>
        <div class="signal-card">
          <span>EXECUTION</span>
          <strong>API Test Run</strong>
        </div>
      </section>

      <section class="panel api-runner-panel" aria-labelledby="apiRunnerTitle">
        <div class="panel-heading result-heading">
          <div>
            <p class="eyebrow">Execution Node</p>
            <h2 id="apiRunnerTitle">接口测试执行</h2>
          </div>
          <div class="result-actions">
            <button class="icon-button" type="button" aria-label="刷新接口执行历史" title="刷新接口执行历史" :disabled="isApiHistoryLoading" @click="fetchApiRunHistory">
              <RefreshCw aria-hidden="true" />
            </button>
          </div>
        </div>

        <div class="api-runner-grid">
          <div class="api-form-stack">
            <div class="api-form-row">
              <div class="field-group compact-field">
                <label for="apiName">用例名称</label>
                <input id="apiName" v-model="apiTest.name" class="text-input" type="text" placeholder="本地数据库状态检查" />
              </div>
              <div class="field-group method-field">
                <label for="apiMethod">方法</label>
                <select id="apiMethod" v-model="apiTest.method" class="select-input">
                  <option v-for="method in apiMethods" :key="method" :value="method">{{ method }}</option>
                </select>
              </div>
            </div>

            <div class="field-group compact-field">
              <label for="apiUrl">接口地址</label>
              <input id="apiUrl" v-model="apiTest.url" class="text-input" type="url" placeholder="http://127.0.0.1:8000/api/database/status" />
            </div>

            <div class="api-form-row">
              <div class="field-group compact-field">
                <label for="apiExpectedStatus">期望状态码</label>
                <input id="apiExpectedStatus" v-model="apiTest.expectedStatus" class="number-input" type="number" min="100" max="599" />
              </div>
              <div class="field-group compact-field">
                <label for="apiExpectedContains">响应包含</label>
                <input id="apiExpectedContains" v-model="apiTest.expectedContains" class="text-input" type="text" placeholder="connected" />
              </div>
              <div class="field-group compact-field">
                <label for="apiTimeout">超时秒数</label>
                <input id="apiTimeout" v-model.number="apiTest.timeoutSeconds" class="number-input" type="number" min="1" max="30" step="1" />
              </div>
            </div>

            <div class="api-form-row">
              <div class="field-group compact-field">
                <label for="apiHeaders">Headers JSON</label>
                <textarea id="apiHeaders" v-model="apiTest.headersText" rows="7" spellcheck="false"></textarea>
              </div>
              <div class="field-group compact-field">
                <label for="apiBody">Body</label>
                <textarea id="apiBody" v-model="apiTest.body" rows="7" spellcheck="false" placeholder="{ &quot;keyword&quot;: &quot;test&quot; }"></textarea>
              </div>
            </div>

            <div class="composer-actions api-actions">
              <button class="secondary-button" type="button" :disabled="isApiRunning" @click="resetApiTest">
                <RefreshCw aria-hidden="true" />
                重置
              </button>
              <button class="primary-button" type="button" :disabled="isApiRunning" @click="runApiTest">
                <Send aria-hidden="true" />
                {{ isApiRunning ? "执行中" : "执行接口" }}
              </button>
            </div>
          </div>

          <div class="api-result-stack">
            <div class="api-result-card" :class="apiResultClass">
              <div v-if="apiRunResult" class="api-result-content">
                <div class="api-result-head">
                  <span class="pill" :class="apiRunResult.passed ? 'run-pass' : 'run-fail'">
                    <CheckCircle2 v-if="apiRunResult.passed" aria-hidden="true" />
                    <AlertTriangle v-else aria-hidden="true" />
                    {{ apiRunResult.passed ? "通过" : "未通过" }}
                  </span>
                  <span class="pill">{{ apiRunResult.response?.durationMs ?? 0 }} ms</span>
                  <span class="pill">HTTP {{ apiRunResult.response?.statusCode ?? "-" }}</span>
                </div>
                <h3>{{ apiRunResult.name }}</h3>
                <p>{{ apiRunResult.request?.method }} {{ apiRunResult.request?.url }}</p>

                <div class="assertion-grid">
                  <div v-for="assertion in apiRunResult.assertions || []" :key="assertion.name" class="assertion-card" :class="{ passed: assertion.passed }">
                    <strong>{{ assertion.name }}</strong>
                    <span>{{ assertion.message }}</span>
                  </div>
                </div>

                <pre class="response-preview">{{ apiRunResult.response?.bodyPreview || apiRunResult.error || "无响应体" }}</pre>
              </div>
              <div v-else class="empty-state api-empty">
                {{ isApiRunning ? "接口执行中" : "等待接口执行" }}
              </div>
            </div>

            <div class="api-history-strip" aria-live="polite">
              <div class="api-history-heading">
                <span class="side-card-label">RUN HISTORY</span>
                <strong>{{ apiRunHistory.length }} 次</strong>
              </div>
              <button
                v-for="item in apiRunHistory"
                :key="item.runId"
                class="api-history-item"
                :class="{ active: apiRunResult?.runId === item.runId }"
                type="button"
                @click="loadApiRun(item)"
              >
                <span class="pill" :class="item.passed ? 'run-pass' : 'run-fail'">{{ item.passed ? "PASS" : "FAIL" }}</span>
                <strong>{{ item.name || `${item.request?.method || ""} ${item.request?.url || ""}` }}</strong>
                <small>{{ formatDate(item.createdAt) }} · {{ item.response?.durationMs ?? 0 }} ms</small>
              </button>
              <div v-if="!apiRunHistory.length" class="api-history-empty">
                {{ isApiHistoryLoading ? "正在读取接口执行历史" : "暂无接口执行历史" }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="workspace">
        <section class="panel composer-panel" aria-labelledby="inputTitle">
          <div class="panel-heading">
            <div>
              <p class="eyebrow">Input Node</p>
              <h2 id="inputTitle">输入材料</h2>
            </div>
            <span class="step-chip">01</span>
          </div>

          <input
            ref="fileInput"
            id="fileInput"
            class="sr-only"
            type="file"
            accept="image/*,.xlsx,.xlsm,.xls,.csv,.tsv,.txt,.md,.markdown,.json,.yaml,.yml,.log,.feature,.html,.htm,.docx,.pdf"
            multiple
            @change="handleFileChange"
          />
          <label
            class="upload-zone"
            :class="{ dragging: isDragging }"
            for="fileInput"
            @dragenter.prevent="isDragging = true"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="handleDrop"
          >
            <span class="upload-icon" aria-hidden="true">
              <Upload />
            </span>
            <span class="upload-title">上传图片、Excel、Word、PDF、CSV 或文本材料</span>
            <span class="upload-subtitle">图片会作为视觉输入，文档和表格会先抽取文本</span>
          </label>

          <div class="material-hints" aria-label="支持的材料类型">
            <span>图片</span>
            <span>Excel/CSV</span>
            <span>Word/PDF</span>
            <span>TXT/MD/JSON</span>
            <span>飞书链接</span>
          </div>

          <div class="preview-grid" aria-live="polite">
            <figure v-for="(item, index) in selectedFiles" :key="item.key" class="preview-card">
              <div class="file-thumb" :class="{ 'file-thumb-generic': !item.isImage }">
                <img v-if="item.isImage" :src="item.url" :alt="item.file.name" />
                <span class="file-badge">{{ item.isImage ? "IMG" : item.extension }}</span>
              </div>
              <figcaption>{{ item.file.name }} · {{ formatFileSize(item.file.size) }}</figcaption>
              <button type="button" aria-label="移除图片" title="移除图片" @click="removeFile(index)">
                <X aria-hidden="true" />
              </button>
            </figure>
          </div>

          <div class="field-group">
            <label for="requirements">用户要求</label>
            <textarea id="requirements" v-model="requirements" rows="6" placeholder="例如：重点覆盖登录、审批流、异常回退、权限和移动端兼容性"></textarea>
          </div>

          <div class="field-group">
            <label for="context">上下文背景</label>
            <textarea id="context" v-model="context" rows="6" placeholder="例如：系统面向企业内部用户，流程包含发起、主管审批、财务复核和归档"></textarea>
          </div>

          <div class="field-group">
            <label for="references">外部文档 / 飞书链接</label>
            <textarea id="references" v-model="references" rows="4" placeholder="粘贴飞书文档、知识库、PRD、接口文档链接；私有文档建议同时导出 Word/PDF/Excel 上传，或把关键内容粘贴到上下文背景中"></textarea>
          </div>

          <div class="composer-actions">
            <button class="secondary-button" type="button" :disabled="isGenerating" @click="resetAll">
              <Trash2 aria-hidden="true" />
              清空
            </button>
            <button class="primary-button" type="button" :disabled="isGenerating" @click="startGeneration">
              <Zap aria-hidden="true" />
              生成用例
            </button>
          </div>
        </section>

        <section class="panel result-panel" aria-labelledby="resultTitle">
          <div class="panel-heading result-heading">
            <div>
              <p class="eyebrow">Output Matrix</p>
              <h2 id="resultTitle">生成结果</h2>
            </div>
            <div class="result-actions">
              <button class="icon-button" type="button" aria-label="复制用例 JSON" title="复制用例 JSON" :disabled="!cases.length" @click="copyCases">
                <Copy aria-hidden="true" />
              </button>
              <button id="downloadButton" class="download-button" type="button" :disabled="!downloadUrl" @click="downloadExcel">
                <Download aria-hidden="true" />
                Excel
              </button>
            </div>
          </div>

          <div class="status-strip">
            <div class="status-item">
              <span class="status-label">状态</span>
              <strong>{{ statusText }}</strong>
            </div>
            <div class="status-item">
              <span class="status-label">用例</span>
              <strong>{{ cases.length }}</strong>
            </div>
            <div class="status-item">
              <span class="status-label">优先级</span>
              <strong>{{ priorityMix }}</strong>
            </div>
          </div>

          <div class="progress-track" aria-hidden="true">
            <span :style="{ width: `${progress}%` }"></span>
          </div>

          <div class="toolbar">
            <div class="search-box">
              <Search aria-hidden="true" />
              <input v-model="searchText" type="search" placeholder="搜索模块、标题、标签" />
            </div>
            <div class="segmented" role="tablist" aria-label="结果视图">
              <button class="tab-button" :class="{ active: activeView === 'cards' }" type="button" @click="activeView = 'cards'">卡片</button>
              <button class="tab-button" :class="{ active: activeView === 'table' }" type="button" @click="activeView = 'table'">表格</button>
              <button class="tab-button" :class="{ active: activeView === 'stream' }" type="button" @click="activeView = 'stream'">流</button>
            </div>
          </div>

          <div class="view-stack">
            <div class="case-grid" :class="{ active: activeView === 'cards' }">
              <div v-if="!visibleCases.length" class="empty-state">{{ cases.length ? "没有匹配的用例" : "等待生成" }}</div>
              <article v-for="item in visibleCases" :key="item.id || item.title" class="case-card">
                <header>
                  <div class="case-meta">
                    <span class="pill" :class="priorityClass(item.priority)">{{ item.priority || "P1" }}</span>
                    <span class="pill">{{ item.id || "" }}</span>
                    <span class="pill">{{ item.case_type || "功能" }}</span>
                  </div>
                  <h3>{{ item.title || "未命名用例" }}</h3>
                  <div class="pill">{{ item.module || "核心流程" }}</div>
                </header>
                <section v-if="item.scenario" class="case-section">
                  <h4>场景</h4>
                  <p>{{ item.scenario }}</p>
                </section>
                <section v-if="toList(item.steps).length" class="case-section">
                  <h4>步骤</h4>
                  <ol>
                    <li v-for="step in toList(item.steps)" :key="step">{{ step }}</li>
                  </ol>
                </section>
                <section v-if="toList(item.expected_results).length" class="case-section">
                  <h4>预期</h4>
                  <ul>
                    <li v-for="result in toList(item.expected_results)" :key="result">{{ result }}</li>
                  </ul>
                </section>
              </article>
            </div>

            <div class="table-wrap" :class="{ active: activeView === 'table' }">
              <table>
                <thead>
                  <tr>
                    <th>编号</th>
                    <th>模块</th>
                    <th>标题</th>
                    <th>优先级</th>
                    <th>类型</th>
                    <th>步骤</th>
                    <th>预期结果</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in visibleCases" :key="`row-${item.id || item.title}`">
                    <td>{{ item.id || "" }}</td>
                    <td>{{ item.module || "" }}</td>
                    <td>{{ item.title || "" }}</td>
                    <td><span class="pill" :class="priorityClass(item.priority)">{{ item.priority || "" }}</span></td>
                    <td>{{ item.case_type || "" }}</td>
                    <td>
                      <template v-for="(step, index) in toList(item.steps)" :key="step">
                        {{ index + 1 }}. {{ step }}<br />
                      </template>
                    </td>
                    <td>
                      <template v-for="(result, index) in toList(item.expected_results)" :key="result">
                        {{ index + 1 }}. {{ result }}<br />
                      </template>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div id="streamView" ref="streamView" class="stream-log" :class="{ active: activeView === 'stream' }" aria-live="polite">
              <div v-for="line in logs" :key="line.id" class="log-line">
                <time>{{ line.time }}</time>
                <span>{{ line.text }}</span>
              </div>
            </div>
          </div>
        </section>
      </section>

      <section class="panel history-panel" aria-labelledby="historyTitle">
        <div class="panel-heading result-heading">
          <div>
            <p class="eyebrow">MySQL Archive</p>
            <h2 id="historyTitle">历史记录</h2>
          </div>
          <div class="result-actions">
            <button class="icon-button" type="button" aria-label="刷新历史记录" title="刷新历史记录" :disabled="isHistoryLoading" @click="refreshHistory">
              <RefreshCw aria-hidden="true" />
            </button>
          </div>
        </div>

        <div class="history-toolbar">
          <div class="database-status" :class="{ connected: databaseConnected }">
            <Database aria-hidden="true" />
            <span>{{ databaseMessage }}</span>
          </div>
          <div class="search-box history-search">
            <Search aria-hidden="true" />
            <input v-model="historyKeyword" type="search" placeholder="搜索历史会话、需求、上下文" @keyup.enter="fetchHistory" />
          </div>
          <button class="secondary-button" type="button" :disabled="isHistoryLoading" @click="fetchHistory">
            <Search aria-hidden="true" />
            查询
          </button>
        </div>

        <div class="history-grid" aria-live="polite">
          <article
            v-for="item in historyItems"
            :key="item.sessionId"
            class="history-card"
            :class="{ active: selectedHistoryId === item.sessionId }"
          >
            <header>
              <div>
                <span class="side-card-label">{{ formatDate(item.createdAt) }}</span>
                <h3>{{ item.requirementsSummary || item.contextSummary || "未填写摘要" }}</h3>
              </div>
              <span class="pill">{{ item.caseCount }} 条</span>
            </header>
            <p>{{ item.contextSummary || "无上下文摘要" }}</p>
            <div class="history-meta">
              <span>材料 {{ item.materialCount }}</span>
              <span>{{ prioritySummary(item.summary) }}</span>
              <span>{{ item.status }}</span>
            </div>
            <div class="history-actions">
              <button class="secondary-button" type="button" @click="loadHistoryDetail(item.sessionId)">
                <FileText aria-hidden="true" />
                查看
              </button>
              <button class="download-button" type="button" :disabled="!item.downloadUrl" @click="downloadHistoryExcel(item.downloadUrl)">
                <Download aria-hidden="true" />
                Excel
              </button>
            </div>
          </article>
          <div v-if="!historyItems.length" class="empty-state history-empty">
            {{ isHistoryLoading ? "正在读取 MySQL 历史记录" : "暂无历史记录" }}
          </div>
        </div>
      </section>
    </main>
    <div v-if="toastMessage" class="toast">{{ toastMessage }}</div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from "vue";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Copy,
  Download,
  FileDown,
  FileText,
  Database,
  History,
  List,
  Moon,
  PlayCircle,
  RefreshCw,
  Search,
  Send,
  Trash2,
  Upload,
  X,
  Zap,
} from "lucide-vue-next";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const MAX_CLIENT_FILE_MB = 20;
const apiMethods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];
const SUPPORTED_EXTENSIONS = new Set([
  "png",
  "jpg",
  "jpeg",
  "webp",
  "gif",
  "bmp",
  "svg",
  "xlsx",
  "xlsm",
  "xls",
  "csv",
  "tsv",
  "txt",
  "md",
  "markdown",
  "json",
  "yaml",
  "yml",
  "log",
  "feature",
  "html",
  "htm",
  "docx",
  "pdf",
]);

const fileInput = ref(null);
const streamView = ref(null);
const selectedFiles = ref([]);
const cases = ref([]);
const logs = ref([]);
const historyItems = ref([]);
const apiRunHistory = ref([]);
const downloadUrl = ref("");
const activeView = ref("cards");
const isGenerating = ref(false);
const isDragging = ref(false);
const isHistoryLoading = ref(false);
const isApiRunning = ref(false);
const isApiHistoryLoading = ref(false);
const requirements = ref("");
const context = ref("");
const references = ref("");
const apiTest = ref(createDefaultApiTest());
const apiRunResult = ref(null);
const statusText = ref("待生成");
const progress = ref(0);
const searchText = ref("");
const historyKeyword = ref("");
const selectedHistoryId = ref("");
const databaseMessage = ref("MySQL 状态检测中");
const databaseConnected = ref(false);
const toastMessage = ref("");
let toastTimer = null;
let logCounter = 0;

const visibleCases = computed(() => {
  const keyword = searchText.value.trim().toLowerCase();
  if (!keyword) {
    return cases.value;
  }
  return cases.value.filter((item) => JSON.stringify(item).toLowerCase().includes(keyword));
});

const priorityMix = computed(() => {
  const counts = cases.value.reduce((acc, item) => {
    const key = item.priority || "P1";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  return Object.entries(counts)
    .map(([key, value]) => `${key}:${value}`)
    .join(" / ") || "-";
});

const apiResultClass = computed(() => {
  if (!apiRunResult.value) {
    return "";
  }
  return apiRunResult.value.passed ? "passed" : "failed";
});

onMounted(() => {
  document.body.classList.add("dark");
  fetchDatabaseStatus();
  fetchHistory();
  fetchApiRunHistory();
});

function toggleTheme() {
  document.body.classList.toggle("dark");
}

function handleFileChange(event) {
  addFiles([...event.target.files]);
  if (fileInput.value) {
    fileInput.value.value = "";
  }
}

function handleDrop(event) {
  isDragging.value = false;
  addFiles([...event.dataTransfer.files]);
}

function addFiles(files) {
  const acceptedFiles = [];
  const rejectedNames = [];
  for (const file of files) {
    if (isSupportedFile(file) && file.size <= MAX_CLIENT_FILE_MB * 1024 * 1024) {
      acceptedFiles.push(file);
    } else {
      rejectedNames.push(file.name);
    }
  }

  for (const file of acceptedFiles) {
    const duplicated = selectedFiles.value.some(
      (item) => item.file.name === file.name && item.file.size === file.size && item.file.lastModified === file.lastModified,
    );
    if (!duplicated) {
      const isImage = file.type.startsWith("image/");
      selectedFiles.value.push({
        file,
        isImage,
        url: isImage ? URL.createObjectURL(file) : "",
        extension: (getFileExtension(file.name) || "FILE").toUpperCase(),
        key: `${file.name}-${file.size}-${file.lastModified}`,
      });
    }
  }

  if (rejectedNames.length) {
    showToast(`已忽略不支持或超过 ${MAX_CLIENT_FILE_MB}MB 的文件：${rejectedNames.join("、")}`);
  }
}

function removeFile(index) {
  const [item] = selectedFiles.value.splice(index, 1);
  if (item?.url) {
    URL.revokeObjectURL(item.url);
  }
}

async function startGeneration() {
  if (isGenerating.value) {
    return;
  }
  if (!selectedFiles.value.length && !requirements.value.trim() && !context.value.trim() && !references.value.trim()) {
    showToast("请至少上传材料、填写需求背景或粘贴文档链接。");
    return;
  }

  const formData = new FormData();
  selectedFiles.value.forEach((item) => formData.append("files", item.file));
  formData.append("requirements", requirements.value.trim());
  formData.append("context", context.value.trim());
  formData.append("references", references.value.trim());

  prepareGenerationState();

  try {
    const response = await fetch(apiUrl("/api/generate"), {
      method: "POST",
      body: formData,
    });

    if (!response.ok || !response.body) {
      const text = await response.text();
      throw new Error(text || "生成请求失败");
    }

    await readSseStream(response.body);
  } catch (error) {
    statusText.value = "生成失败";
    appendLog(error.message || String(error));
    showToast(error.message || "生成失败");
  } finally {
    isGenerating.value = false;
  }
}

function prepareGenerationState() {
  isGenerating.value = true;
  cases.value = [];
  logs.value = [];
  downloadUrl.value = "";
  statusText.value = "生成中";
  progress.value = 6;
}

async function readSseStream(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
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

  if (!dataLines.length) {
    return;
  }

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
    statusText.value = data.text || "生成中";
    appendLog(data.text || "");
    progress.value = Math.min(86, 12 + cases.value.length * 4);
    return;
  }

  if (eventName === "case") {
    cases.value.push(data);
    appendLog(`生成 ${data.id || ""}：${data.title || ""}`);
    progress.value = Math.min(92, 18 + cases.value.length * 4);
    return;
  }

  if (eventName === "done") {
    downloadUrl.value = data.downloadUrl;
    statusText.value = `完成，已保存 ${data.count || cases.value.length} 条`;
    progress.value = 100;
    appendLog("Excel 已生成。");
    if (data.historyStatus === "saved") {
      appendLog("历史记录已保存到 MySQL。");
    }
    fetchDatabaseStatus();
    fetchHistory();
    return;
  }

  if (eventName === "error") {
    statusText.value = "生成失败";
    appendLog(data.message || "生成失败");
    showToast(data.message || "生成失败");
  }
}

function appendLog(text) {
  if (!text) {
    return;
  }
  logs.value.push({
    id: `${Date.now()}-${logCounter++}`,
    time: new Date().toLocaleTimeString("zh-CN", { hour12: false }),
    text,
  });
  nextTick(() => {
    if (streamView.value) {
      streamView.value.scrollTop = streamView.value.scrollHeight;
    }
  });
}

function resetAll() {
  selectedFiles.value.forEach((item) => {
    if (item.url) {
      URL.revokeObjectURL(item.url);
    }
  });
  selectedFiles.value = [];
  cases.value = [];
  logs.value = [];
  downloadUrl.value = "";
  requirements.value = "";
  context.value = "";
  references.value = "";
  statusText.value = "待生成";
  progress.value = 0;
}

async function copyCases() {
  try {
    await navigator.clipboard.writeText(JSON.stringify(cases.value, null, 2));
    showToast("已复制。");
  } catch {
    showToast("复制失败。");
  }
}

async function fetchDatabaseStatus() {
  try {
    const response = await fetch(apiUrl("/api/database/status"));
    const data = await response.json();
    databaseConnected.value = Boolean(data.connected);
    databaseMessage.value = data.message || (data.connected ? "MySQL 连接正常" : "MySQL 未连接");
  } catch (error) {
    databaseConnected.value = false;
    databaseMessage.value = "MySQL 状态读取失败";
  }
}

async function fetchHistory() {
  isHistoryLoading.value = true;
  try {
    const params = new URLSearchParams({
      limit: "30",
      keyword: historyKeyword.value.trim(),
    });
    const response = await fetch(apiUrl(`/api/history?${params.toString()}`));
    const data = await response.json();
    historyItems.value = data.items || [];
    databaseConnected.value = Boolean(data.connected);
    databaseMessage.value = data.message && data.message !== "ok" ? data.message : databaseMessage.value;
  } catch (error) {
    historyItems.value = [];
    databaseConnected.value = false;
    databaseMessage.value = "历史记录读取失败";
  } finally {
    isHistoryLoading.value = false;
  }
}

function refreshHistory() {
  fetchDatabaseStatus();
  fetchHistory();
}

async function runApiTest() {
  if (isApiRunning.value) {
    return;
  }
  if (!apiTest.value.url.trim()) {
    showToast("请填写接口地址。");
    return;
  }

  let headers;
  try {
    headers = parseHeaders(apiTest.value.headersText);
  } catch (error) {
    showToast(error.message || "Headers JSON 格式不正确");
    return;
  }

  isApiRunning.value = true;
  apiRunResult.value = null;
  try {
    const response = await fetch(apiUrl("/api/api-tests/run"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: apiTest.value.name.trim(),
        method: apiTest.value.method,
        url: apiTest.value.url.trim(),
        headers,
        body: apiTest.value.body,
        expectedStatus: normalizeExpectedStatus(apiTest.value.expectedStatus),
        expectedContains: apiTest.value.expectedContains.trim(),
        timeoutSeconds: Number(apiTest.value.timeoutSeconds) || 10,
      }),
    });

    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }

    const data = await response.json();
    apiRunResult.value = data;
    showToast(data.passed ? "接口测试执行通过。" : "接口测试执行未通过。");
    fetchApiRunHistory();
  } catch (error) {
    showToast(error.message || "接口执行失败");
  } finally {
    isApiRunning.value = false;
  }
}

async function fetchApiRunHistory() {
  isApiHistoryLoading.value = true;
  try {
    const response = await fetch(apiUrl("/api/api-tests/history?limit=20"));
    const data = await response.json();
    apiRunHistory.value = data.items || [];
  } catch (error) {
    apiRunHistory.value = [];
  } finally {
    isApiHistoryLoading.value = false;
  }
}

function loadApiRun(item) {
  apiRunResult.value = item;
  apiTest.value = {
    name: item.name || "",
    method: item.request?.method || "GET",
    url: item.request?.url || "",
    headersText: JSON.stringify(item.request?.headers || {}, null, 2),
    body: item.request?.body || "",
    expectedStatus: item.expected?.status ?? "",
    expectedContains: item.expected?.contains || "",
    timeoutSeconds: 10,
  };
}

function resetApiTest() {
  apiTest.value = createDefaultApiTest();
  apiRunResult.value = null;
}

async function loadHistoryDetail(sessionId) {
  try {
    const response = await fetch(apiUrl(`/api/history/${encodeURIComponent(sessionId)}`));
    if (!response.ok) {
      throw new Error("历史记录不存在或 MySQL 暂不可用");
    }
    const detail = await response.json();
    selectedHistoryId.value = sessionId;
    cases.value = detail.cases || [];
    downloadUrl.value = detail.downloadUrl || "";
    statusText.value = `已加载历史 ${cases.value.length} 条`;
    progress.value = cases.value.length ? 100 : 0;
    activeView.value = "cards";
    appendLog(`已加载历史记录：${sessionId}`);
  } catch (error) {
    showToast(error.message || "读取历史记录失败");
  }
}

function downloadExcel() {
  if (downloadUrl.value) {
    window.location.href = apiUrl(downloadUrl.value);
  }
}

function downloadHistoryExcel(url) {
  if (url) {
    window.location.href = apiUrl(url);
  }
}

function showToast(message) {
  toastMessage.value = message;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    toastMessage.value = "";
  }, 2600);
}

function createDefaultApiTest() {
  const baseUrl = API_BASE_URL || "http://127.0.0.1:8000";
  return {
    name: "本地数据库状态检查",
    method: "GET",
    url: `${baseUrl}/api/database/status`,
    headersText: '{\n  "Accept": "application/json"\n}',
    body: "",
    expectedStatus: 200,
    expectedContains: "connected",
    timeoutSeconds: 10,
  };
}

function parseHeaders(value) {
  const text = String(value || "").trim();
  if (!text) {
    return {};
  }
  const parsed = JSON.parse(text);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Headers 必须是 JSON 对象。");
  }
  return parsed;
}

function normalizeExpectedStatus(value) {
  if (value === "" || value === null || value === undefined) {
    return null;
  }
  return Number(value);
}

async function readErrorMessage(response) {
  const text = await response.text();
  try {
    const data = JSON.parse(text);
    return data.detail || text || "接口执行请求失败";
  } catch {
    return text || "接口执行请求失败";
  }
}

function isSupportedFile(file) {
  if (file.type.startsWith("image/")) {
    return true;
  }
  return SUPPORTED_EXTENSIONS.has(getFileExtension(file.name));
}

function getFileExtension(filename) {
  const parts = filename.toLowerCase().split(".");
  return parts.length > 1 ? parts.pop() : "";
}

function formatFileSize(size) {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function toList(value) {
  if (Array.isArray(value)) {
    return value.filter(Boolean);
  }
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function priorityClass(priority) {
  return `priority-${String(priority || "p1").toLowerCase()}`;
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function prioritySummary(summary) {
  const mix = summary?.priorityMix || {};
  const text = Object.entries(mix)
    .map(([key, value]) => `${key}:${value}`)
    .join(" / ");
  return text || "无优先级";
}

function apiUrl(path) {
  if (!path || path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}
</script>

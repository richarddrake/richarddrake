<!-- 这个页面文件负责渲染测试平台主界面，并串联生成、导入、执行和历史记录等前端交互。 -->
<template>
  <div v-if="authLoading" class="auth-page auth-loading-page">
    <div class="auth-panel auth-loading-panel">
      <span class="brand-mark" aria-hidden="true">QA</span>
      <strong>正在校验登录状态</strong>
      <p>测试平台马上就绪。</p>
    </div>
  </div>

  <div v-else-if="!isAuthenticated" class="auth-page">
    <section class="auth-panel" aria-labelledby="loginTitle">
      <div class="auth-brand">
        <span class="brand-mark" aria-hidden="true">QA</span>
        <div>
          <p class="eyebrow">TestOps AI</p>
          <h1 id="loginTitle">测试用例智能生成系统</h1>
        </div>
      </div>
      <form class="login-form" @submit.prevent="submitLogin">
        <div class="field-group">
          <label for="loginUsername">用户名</label>
          <input id="loginUsername" v-model.trim="loginForm.username" class="text-input" type="text" autocomplete="username" placeholder="admin" />
        </div>
        <div class="field-group">
          <label for="loginPassword">密码</label>
          <input id="loginPassword" v-model="loginForm.password" class="text-input" type="password" autocomplete="current-password" placeholder="Admin@123456" />
        </div>
        <div v-if="loginError" class="auth-error">
          <AlertTriangle aria-hidden="true" />
          <span>{{ loginError }}</span>
        </div>
        <button class="primary-button auth-submit" type="submit" :disabled="isLoggingIn">
          <LogIn aria-hidden="true" />
          {{ isLoggingIn ? "登录中" : "登录" }}
        </button>
      </form>
      <div class="auth-hints">
        <span>默认管理员</span>
        <strong>admin / Admin@123456</strong>
      </div>
    </section>
  </div>

  <div v-else class="app-shell">
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
          <Zap aria-hidden="true" />
          用例生成
        </a>
        <a class="nav-item" href="#reviewTitle">
          <CheckCircle2 aria-hidden="true" />
          用例评审
        </a>
        <a class="nav-item" href="#uiRunnerTitle" @click="fetchUiRunHistory">
          <PlayCircle aria-hidden="true" />
          UI 自动化
        </a>
        <a class="nav-item" href="#openApiTitle">
          <Network aria-hidden="true" />
          Swagger 导入
        </a>
        <a class="nav-item" href="#apiRunnerTitle" @click="fetchApiRunHistory">
          <PlayCircle aria-hidden="true" />
          接口执行
        </a>
        <a class="nav-item" href="#reportTitle" @click="fetchApiRunHistory">
          <BarChart3 aria-hidden="true" />
          报告中心
        </a>
        <a class="nav-item" href="#defectTitle" @click="syncDefectCandidates">
          <AlertTriangle aria-hidden="true" />
          缺陷跟踪
        </a>
        <a v-if="isAdmin" class="nav-item" href="#userAdminTitle" @click="fetchUsers">
          <Users aria-hidden="true" />
          用户管理
        </a>
        <a class="nav-item" href="#historyTitle" @click="refreshHistory">
          <History aria-hidden="true" />
          历史记录
        </a>
      </nav>
    </aside>

    <main class="main-shell">
      <header class="topbar">
        <div class="hero-copy">
          <p class="eyebrow">AI QA COMMAND CENTER</p>
          <h1>测试用例智能生成系统</h1>
          <p class="hero-subtitle">图片材料、业务上下文和测试要求进入同一条生成链路，实时输出结构化测试用例。</p>
        </div>
        <div class="top-actions">
          <div class="user-chip" :title="currentUser?.username">
            <Shield aria-hidden="true" />
            <span>{{ currentUser?.displayName || currentUser?.username }}</span>
            <small>{{ roleLabel(currentUser?.role) }}</small>
          </div>
          <button class="icon-button" type="button" aria-label="切换主题" title="切换主题" @click="toggleTheme">
            <Moon aria-hidden="true" />
          </button>
          <button class="icon-button" type="button" aria-label="退出登录" title="退出登录" @click="logout">
            <LogOut aria-hidden="true" />
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
          <strong>API + UI Run</strong>
        </div>
      </section>

      <section class="workspace">
        <section class="panel composer-panel" aria-labelledby="inputTitle">
          <div class="panel-heading">
            <div>
              <p class="eyebrow">Step 01</p>
              <h2 id="inputTitle">工作台</h2>
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
              <figcaption>
                <strong>{{ item.file.name }}</strong>
                <small>{{ formatFileSize(item.file.size) }} · {{ clientMaterialStatus(item).label }}</small>
                <small>{{ clientMaterialStatus(item).detail }}</small>
              </figcaption>
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
            <textarea id="references" v-model="references" rows="4" placeholder="粘贴飞书文档、知识库、PRD、接口文档链接；已配置飞书开放平台授权时，后端会尝试读取私有文档正文"></textarea>
          </div>

          <div v-if="referenceInsights.length" class="reference-insights">
            <article v-for="item in referenceInsights" :key="item.url" class="reference-card" :class="`reference-${item.state}`">
              <div class="reference-head">
                <span class="pill">{{ item.type }}</span>
                <span class="pill">{{ item.status }}</span>
              </div>
              <strong>{{ item.url }}</strong>
              <p>{{ item.suggestion }}</p>
            </article>
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
              <p class="eyebrow">Step 02</p>
              <h2 id="resultTitle">用例生成</h2>
            </div>
            <div class="result-actions">
              <button class="icon-button" type="button" aria-label="复制用例 JSON" title="复制用例 JSON" :disabled="!cases.length" @click="copyCases">
                <Copy aria-hidden="true" />
              </button>
              <button class="download-button" type="button" :disabled="!downloadUrl" @click="downloadExcel">
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
            <div class="status-item">
              <span class="status-label">质量均分</span>
              <strong>{{ coverageReport?.averageQualityScore ?? "-" }}</strong>
            </div>
            <div class="status-item">
              <span class="status-label">可执行</span>
              <strong>{{ coverageReport?.automationReady ?? executableCaseCount }}/{{ cases.length || 0 }}</strong>
            </div>
          </div>

          <div class="progress-track" aria-hidden="true">
            <span :style="{ width: `${progress}%` }"></span>
          </div>

          <div v-if="streamMessages.length" class="stream-insights">
            <div class="stream-heading">
              <span class="side-card-label">解析动态</span>
              <strong>{{ streamMessages.length }} 条</strong>
            </div>
            <ul>
              <li v-for="item in streamMessages.slice(-5)" :key="item.id">{{ item.text }}</li>
            </ul>
          </div>

          <div v-if="coverageReport" class="coverage-panel">
            <div class="coverage-head">
              <span class="side-card-label">COVERAGE MATRIX</span>
              <strong>{{ Math.round((coverageReport.automationRatio || 0) * 100) }}% 自动化就绪</strong>
            </div>
            <div class="coverage-grid">
              <div v-for="item in coverageCards" :key="item.key" class="coverage-card">
                <span>{{ item.label }}</span>
                <strong>{{ item.covered }}/{{ coverageReport.totalCases || 0 }}</strong>
                <div class="coverage-bar" aria-hidden="true"><i :style="{ width: `${item.percent}%` }"></i></div>
              </div>
            </div>
            <div v-if="(coverageReport.risks || []).length" class="risk-strip">
              <AlertTriangle aria-hidden="true" />
              <span>{{ coverageReport.risks.slice(0, 2).join("；") }}</span>
            </div>
            <div v-if="coverageReport.uncoveredDetails?.length" class="coverage-detail-grid">
              <article v-for="item in coverageReport.uncoveredDetails.slice(0, 3)" :key="item.key" class="coverage-detail-card">
                <strong>{{ item.label }}</strong>
                <p>{{ item.reason }}</p>
                <small>{{ item.suggestion }}</small>
              </article>
            </div>
            <div v-if="coverageReport.automationSummary?.blockedExamples?.length" class="coverage-detail-grid">
              <article v-for="item in coverageReport.automationSummary.blockedExamples.slice(0, 2)" :key="item.id || item.title" class="coverage-detail-card">
                <strong>{{ item.title }}</strong>
                <p>{{ item.reason }}</p>
              </article>
            </div>
          </div>

          <div class="toolbar">
            <div class="search-box">
              <Search aria-hidden="true" />
              <input v-model="searchText" type="search" placeholder="搜索模块、标题、标签" />
            </div>
            <div class="segmented" role="tablist" aria-label="结果视图">
              <button class="tab-button" :class="{ active: activeView === 'cards' }" type="button" @click="activeView = 'cards'">卡片</button>
              <button class="tab-button" :class="{ active: activeView === 'table' }" type="button" @click="activeView = 'table'">表格</button>
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
                    <span v-if="item.quality?.score" class="pill quality-pill">Q{{ item.quality.score }}</span>
                    <span class="pill" :class="caseReadinessClass(item)">{{ caseReadiness(item).label }}</span>
                    <span v-if="caseApiConfig(item)" class="pill api-ready-pill">API</span>
                  </div>
                  <h3>{{ item.title || "未命名用例" }}</h3>
                  <div class="pill">{{ item.module || "核心流程" }}</div>
                </header>
                <section class="case-section">
                  <h4>执行就绪</h4>
                  <p>{{ caseReadiness(item).reason }}</p>
                  <ul v-if="caseReadiness(item).missing?.length">
                    <li v-for="field in caseReadiness(item).missing" :key="field">缺少 {{ field }}</li>
                  </ul>
                </section>
                <section v-if="item.requirement_id || item.requirementId" class="case-section">
                  <h4>需求追溯</h4>
                  <p>{{ item.requirement_id || item.requirementId }}</p>
                </section>
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
                <section v-if="caseApiConfig(item)" class="case-section case-api-section">
                  <h4>接口</h4>
                  <div class="case-api-line">
                    <code>{{ caseApiConfig(item).method }} {{ caseApiConfig(item).url }}</code>
                    <button class="mini-run-button" type="button" :disabled="executingCaseId === item.id" @click="executeGeneratedCase(item)">
                      <PlayCircle aria-hidden="true" />
                      {{ executingCaseId === item.id ? "执行中" : "执行" }}
                    </button>
                  </div>
                  <div v-if="caseExecutionMap[item.id]" class="case-execution" :class="{ passed: caseExecutionMap[item.id].passed }">
                    <span>{{ caseExecutionMap[item.id].passed ? "通过" : "未通过" }}</span>
                    <strong>HTTP {{ caseExecutionMap[item.id].response?.statusCode ?? "-" }} · {{ caseExecutionMap[item.id].response?.durationMs ?? 0 }} ms</strong>
                  </div>
                  <div v-if="caseExecutionMap[item.id]?.failureAnalysis && !caseExecutionMap[item.id].passed" class="failure-analysis">
                    <strong>{{ caseExecutionMap[item.id].failureAnalysis.summary }}</strong>
                    <span>{{ (caseExecutionMap[item.id].failureAnalysis.nextSteps || []).slice(0, 2).join("；") }}</span>
                    <small v-if="caseExecutionMap[item.id].failureAnalysis.evidence?.length">证据：{{ caseExecutionMap[item.id].failureAnalysis.evidence.slice(0, 2).join("；") }}</small>
                  </div>
                </section>
                <section v-if="caseUiConfig(item)" class="case-section case-api-section">
                  <h4>UI 自动化</h4>
                  <div class="case-api-line">
                    <code>{{ caseUiConfig(item).baseUrl || caseUiConfig(item).base_url || "页面步骤配置" }}</code>
                    <button class="mini-run-button" type="button" @click="loadGeneratedUiCase(item)">
                      <PlayCircle aria-hidden="true" />
                      载入 UI
                    </button>
                  </div>
                </section>
                <section v-if="item.quality?.deductions?.length || item.quality?.suggestions?.length" class="case-section quality-section">
                  <h4>质量建议</h4>
                  <ul v-if="item.quality?.deductions?.length">
                    <li v-for="deduction in item.quality.deductions.slice(0, 3)" :key="deduction.key">{{ deduction.label }} -{{ deduction.lost }}：{{ deduction.reason }}</li>
                  </ul>
                  <ul>
                    <li v-for="tip in (item.quality?.suggestions || []).slice(0, 2)" :key="tip">{{ tip }}</li>
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
                    <th>质量</th>
                    <th>执行状态</th>
                    <th>需求追溯</th>
                    <th>接口</th>
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
                    <td>{{ item.quality?.score ?? "-" }}</td>
                    <td>{{ caseReadiness(item).label }}</td>
                    <td>{{ item.requirement_id || item.requirementId || "-" }}</td>
                    <td>{{ caseApiConfig(item)?.method || "-" }}</td>
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

          </div>
        </section>
      </section>

      <section class="panel review-panel" aria-labelledby="reviewTitle">
        <div class="panel-heading result-heading">
          <div>
            <p class="eyebrow">Step 03</p>
            <h2 id="reviewTitle">用例评审</h2>
          </div>
          <div class="result-actions">
            <button class="secondary-button" type="button" :disabled="!cases.length || isReviewing" @click="() => runCaseReview()">
              <RefreshCw aria-hidden="true" />
              {{ isReviewing ? "评审中" : "重新评审" }}
            </button>
          </div>
        </div>

        <div class="review-layout">
          <div class="review-summary">
            <div class="review-verdict" :class="`review-${caseReviewReport?.verdictLevel || 'empty'}`">
              <span class="side-card-label">REVIEW VERDICT</span>
              <strong>{{ caseReviewReport?.verdict || "待评审" }}</strong>
              <p>{{ caseReviewReport?.verdictReason || "生成或导入用例后，系统会从追溯、步骤、预期、执行就绪和重复风险等维度给出评审结论。" }}</p>
            </div>
            <div class="review-metrics">
              <div v-for="item in reviewSummaryCards" :key="item.label" class="review-metric-card">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
                <small>{{ item.hint }}</small>
              </div>
            </div>
          </div>

          <div class="review-checklist">
            <article v-for="item in reviewChecklist" :key="item.label" class="review-check-card" :class="`check-${item.status}`">
              <span>{{ item.label }}</span>
              <strong>{{ item.passed }}/{{ item.total }}</strong>
              <div class="coverage-bar" aria-hidden="true"><i :style="{ width: `${Math.round((item.ratio || 0) * 100)}%` }"></i></div>
              <small>{{ item.suggestion }}</small>
            </article>
          </div>

          <div v-if="reviewTopIssues.length || reviewRecommendations.length" class="review-insight-grid">
            <article class="review-insight-card">
              <span class="side-card-label">TOP ISSUES</span>
              <ul v-if="reviewTopIssues.length">
                <li v-for="item in reviewTopIssues" :key="item.issue">{{ item.issue }} · {{ item.count }} 次</li>
              </ul>
              <p v-else>当前没有明显集中问题。</p>
            </article>
            <article class="review-insight-card">
              <span class="side-card-label">ACTIONS</span>
              <ul v-if="reviewRecommendations.length">
                <li v-for="item in reviewRecommendations" :key="item">{{ item }}</li>
              </ul>
              <p v-else>等待评审结果。</p>
            </article>
          </div>

          <div class="review-list">
            <div class="review-list-heading">
              <span class="side-card-label">CASE REVIEW ITEMS</span>
              <strong>{{ reviewItems.length }} 条</strong>
            </div>
            <article v-for="item in reviewItems" :key="`review-${item.id || item.title}`" class="review-item-card" :class="reviewStatusClass(item.status)">
              <header>
                <div>
                  <span class="pill" :class="priorityClass(item.priority)">{{ item.priority }}</span>
                  <span class="pill">{{ item.id || "未编号" }}</span>
                  <span class="pill">{{ item.qualityScore }} 分</span>
                </div>
                <span class="pill" :class="reviewStatusClass(item.status)">{{ reviewStatusLabel(item.status) }}</span>
              </header>
              <h3>{{ item.title }}</h3>
              <p>{{ item.module }} · {{ item.caseType }} · {{ item.readinessLabel }}</p>
              <div v-if="item.issues.length" class="review-tags">
                <span v-for="issue in item.issues.slice(0, 4)" :key="issue">{{ issue }}</span>
              </div>
              <ul v-if="item.actions.length">
                <li v-for="action in item.actions.slice(0, 3)" :key="action">{{ action }}</li>
              </ul>
            </article>
            <div v-if="!reviewItems.length" class="empty-state review-empty">{{ cases.length ? "等待评审结果" : "生成或导入用例后可开始评审" }}</div>
          </div>
        </div>
      </section>

      <section class="panel ui-runner-panel api-runner-panel" aria-labelledby="uiRunnerTitle">
        <div class="panel-heading result-heading">
          <div>
            <p class="eyebrow">Step 04</p>
            <h2 id="uiRunnerTitle">UI 自动化</h2>
          </div>
          <div class="result-actions">
            <button class="secondary-button" type="button" :disabled="isUiRunning" @click="resetUiTest">
              <RefreshCw aria-hidden="true" />
              重置
            </button>
            <button class="primary-button" type="button" :disabled="isUiRunning" @click="runUiTest">
              <Send aria-hidden="true" />
              {{ isUiRunning ? "执行中" : "执行 UI 用例" }}
            </button>
          </div>
        </div>

        <div class="api-runner-grid">
          <div class="api-form-stack">
            <div class="api-form-row">
              <div class="field-group">
                <label for="uiName">用例名称</label>
                <input id="uiName" v-model="uiTest.name" class="text-input" type="text" placeholder="登录成功流程" />
              </div>
              <div class="field-group">
                <label for="uiBaseUrl">页面基础地址</label>
                <input id="uiBaseUrl" v-model="uiTest.baseUrl" class="text-input" type="url" placeholder="http://127.0.0.1:5173" />
              </div>
            </div>

            <div class="api-form-row ui-options-row">
              <div class="field-group">
                <label for="uiBrowser">浏览器</label>
                <select id="uiBrowser" v-model="uiTest.browser" class="select-input">
                  <option value="chromium">Chromium</option>
                  <option value="firefox">Firefox</option>
                  <option value="webkit">WebKit</option>
                </select>
              </div>
              <div class="field-group">
                <label for="uiViewportWidth">宽度</label>
                <input id="uiViewportWidth" v-model="uiTest.viewportWidth" class="text-input" type="number" min="320" max="3840" />
              </div>
              <div class="field-group">
                <label for="uiViewportHeight">高度</label>
                <input id="uiViewportHeight" v-model="uiTest.viewportHeight" class="text-input" type="number" min="320" max="2160" />
              </div>
              <label class="toggle-line">
                <input v-model="uiTest.captureTrace" type="checkbox" />
                <span>Trace</span>
              </label>
            </div>

            <div class="advanced-grid ui-config-grid">
              <div class="field-group compact-field">
                <label for="uiVariables">变量 JSON</label>
                <textarea id="uiVariables" v-model="uiTest.variablesText" rows="8" spellcheck="false"></textarea>
              </div>
              <div class="field-group compact-field">
                <label for="uiSteps">步骤 JSON</label>
                <textarea id="uiSteps" v-model="uiTest.stepsText" rows="8" spellcheck="false"></textarea>
              </div>
            </div>
          </div>

          <div class="api-result-stack">
            <div class="api-result-card" :class="uiResultClass">
              <div v-if="uiRunResult" class="api-result-content">
                <div class="api-result-head">
                  <span class="pill" :class="uiRunResult.passed ? 'run-pass' : 'run-fail'">
                    <CheckCircle2 v-if="uiRunResult.passed" aria-hidden="true" />
                    <AlertTriangle v-else aria-hidden="true" />
                    {{ uiRunResult.passed ? "通过" : "未通过" }}
                  </span>
                  <span class="pill">{{ uiRunResult.response?.durationMs ?? 0 }} ms</span>
                  <span class="pill">{{ uiRunResult.request?.browser || uiTest.browser }}</span>
                  <span class="pill">{{ runTypeLabel(uiRunResult.runType) }}</span>
                </div>
                <h3>{{ uiRunResult.name }}</h3>
                <p>{{ runTargetLabel(uiRunResult) }}</p>

                <div class="api-summary-grid">
                  <div>
                    <span>步骤</span>
                    <strong>{{ uiRunResult.summary?.passedSteps ?? 0 }}/{{ uiRunResult.summary?.executedSteps ?? (uiRunResult.steps || []).length }}</strong>
                  </div>
                  <div>
                    <span>断言</span>
                    <strong>{{ uiRunResult.summary?.passedAssertions ?? passedAssertionCount(uiRunResult) }}/{{ uiRunResult.summary?.assertionCount ?? (uiRunResult.assertions || []).length }}</strong>
                  </div>
                  <div>
                    <span>证据</span>
                    <strong>{{ Object.keys(uiRunResult.artifacts || {}).length }}</strong>
                  </div>
                </div>

                <div class="assertion-grid">
                  <div v-for="step in uiRunResult.steps || []" :key="`${uiRunResult.runId}-${step.index}`" class="assertion-card" :class="{ passed: step.passed }">
                    <strong>{{ step.index }}. {{ step.name }}</strong>
                    <span>{{ step.message }}</span>
                  </div>
                </div>

                <div v-if="Object.keys(uiRunResult.artifacts || {}).length" class="ui-artifact-links">
                  <a v-if="uiRunResult.artifacts?.screenshot" :href="apiUrl(uiRunResult.artifacts.screenshot)" target="_blank" rel="noreferrer">失败截图</a>
                  <a v-if="uiRunResult.artifacts?.trace" :href="apiUrl(uiRunResult.artifacts.trace)" target="_blank" rel="noreferrer">Trace</a>
                </div>

                <div v-if="uiRunResult.failureAnalysis && !uiRunResult.passed" class="failure-analysis api-failure-analysis">
                  <strong>{{ uiRunResult.failureAnalysis.summary }}</strong>
                  <span>{{ (uiRunResult.failureAnalysis.nextSteps || []).slice(0, 3).join("；") }}</span>
                  <small>置信度 {{ Math.round((uiRunResult.failureAnalysis.confidence || 0) * 100) }}% · {{ uiRunResult.failureAnalysis.shouldCreateDefect ? "建议纳入缺陷跟踪" : "建议先更新用例" }}</small>
                  <ul v-if="uiRunResult.failureAnalysis.evidence?.length" class="failure-evidence-list">
                    <li v-for="item in uiRunResult.failureAnalysis.evidence.slice(0, 3)" :key="item">{{ item }}</li>
                  </ul>
                </div>

                <pre class="response-preview">{{ uiRunResult.response?.bodyPreview || uiRunResult.error || "无页面执行摘要" }}</pre>
              </div>
              <div v-else class="empty-state api-empty">
                {{ isUiRunning ? "UI 用例执行中" : "等待 UI 自动化执行" }}
              </div>
            </div>

            <div class="api-history-strip" aria-live="polite">
              <div class="api-history-heading">
                <span class="side-card-label">UI RUN HISTORY</span>
                <strong>{{ uiRunHistory.length }} 次</strong>
              </div>
              <button
                v-for="item in uiRunHistory"
                :key="item.runId"
                class="api-history-item"
                :class="{ active: uiRunResult?.runId === item.runId }"
                type="button"
                @click="loadUiRun(item)"
              >
                <span class="pill" :class="item.passed ? 'run-pass' : 'run-fail'">{{ item.passed ? "PASS" : "FAIL" }}</span>
                <strong>{{ item.name || "Web UI 自动化用例" }}</strong>
                <small>{{ formatDate(item.createdAt) }} · {{ item.response?.durationMs ?? 0 }} ms</small>
              </button>
              <div v-if="!uiRunHistory.length" class="api-history-empty">
                {{ isUiHistoryLoading ? "正在读取 UI 执行历史" : "暂无 UI 执行历史" }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="panel openapi-panel" aria-labelledby="openApiTitle">
        <div class="panel-heading result-heading">
          <div>
            <p class="eyebrow">Step 05</p>
            <h2 id="openApiTitle">Swagger 导入</h2>
          </div>
          <div class="result-actions">
            <button class="secondary-button" type="button" :disabled="isOpenApiImporting" @click="resetOpenApiImport">
              <RefreshCw aria-hidden="true" />
              重置
            </button>
            <button class="primary-button" type="button" :disabled="isOpenApiImporting" @click="importOpenApi">
              <Upload aria-hidden="true" />
              {{ isOpenApiImporting ? "导入中" : "导入生成" }}
            </button>
          </div>
        </div>

        <div class="openapi-grid">
          <div class="api-form-stack">
            <div class="api-form-row">
              <div class="field-group compact-field">
                <label for="openApiUrl">文档 URL</label>
                <input id="openApiUrl" v-model="openApiUrl" class="text-input" type="url" placeholder="https://example.com/openapi.json" />
              </div>
              <div class="field-group compact-field">
                <label for="openApiBaseUrl">接口基础地址</label>
                <input id="openApiBaseUrl" v-model="openApiBaseUrl" class="text-input" type="url" placeholder="http://127.0.0.1:8000" />
              </div>
            </div>
            <div class="field-group compact-field">
              <label for="openApiContent">OpenAPI JSON / YAML</label>
              <textarea id="openApiContent" v-model="openApiContent" rows="9" spellcheck="false" placeholder="{ &quot;openapi&quot;: &quot;3.0.0&quot;, &quot;paths&quot;: {} }"></textarea>
            </div>
          </div>

          <div class="openapi-summary">
            <div class="status-item">
              <span class="status-label">接口数</span>
              <strong>{{ openApiSummary.operationCount ?? "-" }}</strong>
            </div>
            <div class="status-item">
              <span class="status-label">生成用例</span>
              <strong>{{ openApiSummary.caseCount ?? "-" }}</strong>
            </div>
            <div class="status-item">
              <span class="status-label">文档来源</span>
              <strong>{{ openApiSummary.title || "等待导入" }}</strong>
            </div>
          </div>
        </div>
      </section>

      <section class="panel api-runner-panel" aria-labelledby="apiRunnerTitle">
        <div class="panel-heading result-heading">
          <div>
            <p class="eyebrow">Step 06</p>
            <h2 id="apiRunnerTitle">接口执行</h2>
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
                <input id="apiName" v-model="apiTest.name" class="text-input" type="text" placeholder="后端健康检查" />
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
              <input id="apiUrl" v-model="apiTest.url" class="text-input" type="url" placeholder="http://127.0.0.1:8000/" />
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

            <div class="api-form-row api-execution-row">
              <div class="field-group compact-field">
                <label for="apiBodyMode">Body 模式</label>
                <select id="apiBodyMode" v-model="apiTest.bodyMode" class="select-input">
                  <option value="raw">raw</option>
                  <option value="json">json</option>
                  <option value="form">form</option>
                  <option value="multipart">multipart</option>
                </select>
              </div>
              <div class="field-group compact-field">
                <label for="apiMaxResponseMs">最大耗时 ms</label>
                <input id="apiMaxResponseMs" v-model="apiTest.maxResponseMs" class="number-input" type="number" min="1" placeholder="1000" />
              </div>
              <div class="field-group compact-field">
                <label for="apiRepeat">并发次数</label>
                <input id="apiRepeat" v-model.number="apiTest.repeat" class="number-input" type="number" min="1" max="100" />
              </div>
              <div class="field-group compact-field">
                <label for="apiConcurrency">并发数</label>
                <input id="apiConcurrency" v-model.number="apiTest.concurrency" class="number-input" type="number" min="1" max="20" />
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

            <details class="advanced-config" open>
              <summary>
                <span>高级接口测试配置</span>
                <span>{{ advancedConfigCount }} 项</span>
              </summary>
              <div class="advanced-grid">
                <div class="field-group compact-field">
                  <label for="apiVariables">环境变量 JSON</label>
                  <textarea id="apiVariables" v-model="apiTest.variablesText" rows="7" spellcheck="false"></textarea>
                </div>
                <div class="field-group compact-field">
                  <label for="apiAssertions">字段断言 JSON</label>
                  <textarea id="apiAssertions" v-model="apiTest.assertionsText" rows="7" spellcheck="false"></textarea>
                </div>
                <div class="field-group compact-field">
                  <label for="apiExtractors">变量提取 JSON</label>
                  <textarea id="apiExtractors" v-model="apiTest.extractorsText" rows="7" spellcheck="false"></textarea>
                </div>
                <div class="field-group compact-field">
                  <label for="apiDbAssertions">数据库校验 JSON</label>
                  <textarea id="apiDbAssertions" v-model="apiTest.databaseAssertionsText" rows="7" spellcheck="false"></textarea>
                </div>
                <div class="field-group compact-field">
                  <label for="apiSchema">JSON Schema</label>
                  <textarea id="apiSchema" v-model="apiTest.jsonSchemaText" rows="7" spellcheck="false"></textarea>
                </div>
                <div class="field-group compact-field">
                  <label for="apiSuiteSteps">用例集步骤 JSON</label>
                  <textarea id="apiSuiteSteps" v-model="apiTest.suiteStepsText" rows="7" spellcheck="false"></textarea>
                </div>
              </div>
            </details>

            <div class="composer-actions api-actions">
              <button class="secondary-button" type="button" :disabled="isApiRunning" @click="resetApiTest">
                <RefreshCw aria-hidden="true" />
                重置
              </button>
              <button class="secondary-button" type="button" :disabled="isApiRunning" @click="runApiSuite">
                <ListChecks aria-hidden="true" />
                执行用例集
              </button>
              <button class="secondary-button" type="button" :disabled="isApiRunning" @click="runApiLoad">
                <Gauge aria-hidden="true" />
                并发执行
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
                  <span class="pill">{{ runTypeLabel(apiRunResult.runType) }}</span>
                </div>
                <h3>{{ apiRunResult.name }}</h3>
                <p>{{ apiRunResult.request?.method }} {{ apiRunResult.request?.url }}</p>

                <div class="api-summary-grid">
                  <div>
                    <span>断言</span>
                    <strong>{{ apiRunResult.summary?.passedAssertions ?? passedAssertionCount(apiRunResult) }}/{{ apiRunResult.summary?.assertionCount ?? (apiRunResult.assertions || []).length }}</strong>
                  </div>
                  <div>
                    <span>提取变量</span>
                    <strong>{{ Object.keys(apiRunResult.variables || {}).length }}</strong>
                  </div>
                  <div>
                    <span>数据库校验</span>
                    <strong>{{ (apiRunResult.databaseChecks || []).length }}</strong>
                  </div>
                </div>

                <div class="assertion-grid">
                  <div v-for="assertion in apiRunResult.assertions || []" :key="assertion.name" class="assertion-card" :class="{ passed: assertion.passed }">
                    <strong>{{ assertion.name }}</strong>
                    <span>{{ assertion.message }}</span>
                  </div>
                </div>

                <div v-if="(apiRunResult.extractions || []).length" class="api-detail-grid">
                  <div v-for="item in apiRunResult.extractions" :key="item.name" class="api-detail-card" :class="{ passed: item.passed }">
                    <strong>{{ item.name }}</strong>
                    <span>{{ stringifyValue(item.value || item.message) }}</span>
                  </div>
                </div>

                <div v-if="apiRunResult.failureAnalysis && !apiRunResult.passed" class="failure-analysis api-failure-analysis">
                  <strong>{{ apiRunResult.failureAnalysis.summary }}</strong>
                  <span>{{ (apiRunResult.failureAnalysis.nextSteps || []).slice(0, 3).join("；") }}</span>
                  <small>置信度 {{ Math.round((apiRunResult.failureAnalysis.confidence || 0) * 100) }}% · {{ apiRunResult.failureAnalysis.shouldCreateDefect ? "建议纳入缺陷跟踪" : "建议先继续排查" }}</small>
                  <ul v-if="apiRunResult.failureAnalysis.evidence?.length" class="failure-evidence-list">
                    <li v-for="item in apiRunResult.failureAnalysis.evidence.slice(0, 3)" :key="item">{{ item }}</li>
                  </ul>
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

      <section class="panel report-panel" aria-labelledby="reportTitle">
        <div class="panel-heading result-heading">
          <div>
            <p class="eyebrow">Step 07</p>
            <h2 id="reportTitle">报告中心</h2>
          </div>
          <div class="result-actions">
            <button class="download-button" type="button" :disabled="!allRunRecords.length && !cases.length" @click="downloadReport('html')">
              <Download aria-hidden="true" />
              HTML
            </button>
            <button class="download-button" type="button" :disabled="!allRunRecords.length && !cases.length" @click="downloadReport('md')">
              <Download aria-hidden="true" />
              Markdown
            </button>
          </div>
        </div>

        <div class="report-grid">
          <div class="report-summary-grid">
            <div v-for="item in reportSummaryCards" :key="item.label" class="report-summary-card">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <small>{{ item.hint }}</small>
            </div>
          </div>

          <div class="report-side-stack">
            <div class="report-focus-card">
              <span class="side-card-label">执行概览</span>
              <strong>{{ reportOverviewText }}</strong>
              <p>{{ reportOverviewHint }}</p>
            </div>
            <div class="report-focus-card">
              <span class="side-card-label">覆盖风险</span>
              <strong>{{ (coverageReport?.risks || []).length }} 项</strong>
              <p>{{ reportRiskText }}</p>
            </div>
          </div>
        </div>

        <div class="report-run-list">
          <div class="report-list-heading">
            <span class="side-card-label">RECENT RUNS</span>
            <strong>{{ recentReportRuns.length }} 条</strong>
          </div>
          <div v-if="recentReportRuns.length" class="report-run-grid">
            <article v-for="item in recentReportRuns" :key="item.runId || item.createdAt || item.name" class="report-run-card" :class="{ failed: item.passed === false }">
              <div class="report-run-head">
                <span class="pill" :class="item.passed ? 'run-pass' : 'run-fail'">{{ item.passed ? "PASS" : "FAIL" }}</span>
                <span class="pill">{{ runTypeLabel(item.runType) }}</span>
              </div>
              <strong>{{ item.name || `${item.request?.method || ""} ${item.request?.url || ""}` }}</strong>
              <p>{{ runTargetLabel(item) }}</p>
              <small>{{ formatDate(item.createdAt) }} · {{ item.response?.durationMs ?? 0 }} ms · {{ runStatusLabel(item) }}</small>
            </article>
          </div>
          <div v-else class="empty-state report-empty">等待接口或 UI 自动化执行后汇总报告</div>
        </div>

        <div class="report-detail-grid">
          <article class="report-detail-card">
            <h3>测试环境</h3>
            <ul>
              <li v-for="item in reportEnvironmentItems" :key="item.label"><strong>{{ item.label }}：</strong>{{ item.value }}</li>
            </ul>
          </article>
          <article class="report-detail-card">
            <h3>测试范围</h3>
            <ul>
              <li v-for="item in reportScopeItems" :key="item.label"><strong>{{ item.label }}：</strong>{{ item.value }}</li>
            </ul>
          </article>
          <article class="report-detail-card">
            <h3>用例执行统计</h3>
            <ul>
              <li><strong>执行总次数：</strong>{{ reportMetrics.totalRuns }}</li>
              <li><strong>用例总数：</strong>{{ reportMetrics.totalCases }}</li>
              <li><strong>通过数：</strong>{{ reportMetrics.passedRuns }}</li>
              <li><strong>失败数：</strong>{{ reportMetrics.failedRuns }}</li>
              <li><strong>跳过数：</strong>{{ reportMetrics.skippedRuns }}</li>
            </ul>
          </article>
          <article class="report-detail-card">
            <h3>自动化执行统计</h3>
            <ul>
              <li><strong>通过率：</strong>{{ reportMetrics.passRate }}</li>
              <li><strong>平均响应时间：</strong>{{ reportMetrics.averageDuration }} ms</li>
              <li><strong>最慢执行：</strong>{{ reportMetrics.slowestInterface }}</li>
              <li><strong>P0/P1 失败：</strong>{{ reportMetrics.p0Failures }}/{{ reportMetrics.p1Failures }}</li>
            </ul>
          </article>
          <article class="report-detail-card">
            <h3>失败分析</h3>
            <ul v-if="reportFailureCategoryItems.length">
              <li v-for="item in reportFailureCategoryItems.slice(0, 5)" :key="item.label"><strong>{{ item.label }}：</strong>{{ item.value }}</li>
            </ul>
            <p v-else>当前没有失败分类数据。</p>
          </article>
          <article class="report-detail-card">
            <h3>慢执行统计</h3>
            <ul v-if="reportSlowRunItems.length">
              <li v-for="item in reportSlowRunItems.slice(0, 3)" :key="item.runId || item.label"><strong>{{ item.durationMs }} ms：</strong>{{ item.label }}</li>
            </ul>
            <p v-else>当前没有可统计的慢执行。</p>
          </article>
          <article class="report-detail-card">
            <h3>数据库校验结果</h3>
            <ul>
              <li><strong>总校验数：</strong>{{ reportDatabaseSummary.total }}</li>
              <li><strong>通过数：</strong>{{ reportDatabaseSummary.passed }}</li>
              <li><strong>失败数：</strong>{{ reportDatabaseSummary.failed }}</li>
            </ul>
            <p v-if="reportDatabaseSummary.recentFailures.length">最近失败：{{ reportDatabaseSummary.recentFailures.map((item) => item.name).join("、") }}</p>
          </article>
          <article class="report-detail-card report-conclusion-card">
            <h3>测试结论</h3>
            <p>{{ reportConclusionText }}</p>
            <ul v-if="coverageReport?.risks?.length">
              <li v-for="item in coverageReport.risks.slice(0, 3)" :key="item">{{ item }}</li>
            </ul>
          </article>
        </div>
      </section>

      <section class="panel defect-panel" aria-labelledby="defectTitle">
        <div class="panel-heading result-heading">
          <div>
            <p class="eyebrow">Step 08</p>
            <h2 id="defectTitle">缺陷跟踪</h2>
          </div>
          <div class="result-actions">
            <button class="secondary-button" type="button" :disabled="!defectItems.length" @click="syncDefectCandidates">
              <RefreshCw aria-hidden="true" />
              同步失败项
            </button>
          </div>
        </div>

        <div class="defect-toolbar">
          <div class="database-status" :class="{ connected: defectOpenCount === 0 }">
            <AlertTriangle aria-hidden="true" />
            <span>{{ defectToolbarText }}</span>
          </div>
        </div>

        <div v-if="defectItems.length" class="defect-grid">
          <article v-for="item in defectItems" :key="item.id" class="defect-card" :class="`severity-${item.severity}`">
            <header>
              <div>
                <span class="side-card-label">{{ item.source }}</span>
                <h3>{{ item.title }}</h3>
              </div>
              <span class="pill" :class="defectStatusClass(item.status)">{{ defectStatusLabel(item.status) }}</span>
            </header>
            <p>{{ item.summary }}</p>
            <div class="defect-meta">
              <span>{{ item.createdAt ? formatDate(item.createdAt) : "无时间" }}</span>
              <span>{{ item.requestLabel || "无请求信息" }}</span>
              <span>重复 {{ item.occurrences || 1 }} 次</span>
            </div>
            <p v-if="item.failureCategory">失败分类：{{ item.failureCategory }} · 置信度 {{ Math.round((item.confidence || 0) * 100) }}%</p>

            <div class="defect-controls">
              <div class="field-group compact-field">
                <label :for="`defect-status-${item.id}`">状态</label>
                <select :id="`defect-status-${item.id}`" class="select-input" :value="item.status" @change="updateDefectRecord(item.id, 'status', $event.target.value)">
                  <option value="open">待处理</option>
                  <option value="in_progress">处理中</option>
                  <option value="resolved">已解决</option>
                </select>
              </div>
              <div class="field-group compact-field">
                <label :for="`defect-severity-${item.id}`">优先级</label>
                <select :id="`defect-severity-${item.id}`" class="select-input" :value="item.severity" @change="updateDefectRecord(item.id, 'severity', $event.target.value)">
                  <option value="high">高</option>
                  <option value="medium">中</option>
                  <option value="low">低</option>
                </select>
              </div>
            </div>

            <div class="field-group compact-field">
              <label :for="`defect-owner-${item.id}`">负责人</label>
              <input :id="`defect-owner-${item.id}`" class="text-input" type="text" :value="item.owner" placeholder="填写处理人" @change="updateDefectRecord(item.id, 'owner', $event.target.value)" />
            </div>

            <div class="field-group compact-field">
              <label :for="`defect-note-${item.id}`">跟踪备注</label>
              <textarea :id="`defect-note-${item.id}`" rows="4" spellcheck="false" :value="item.note" placeholder="记录定位结果、复现条件、修复进度" @change="updateDefectRecord(item.id, 'note', $event.target.value)"></textarea>
            </div>

            <div v-if="item.nextSteps.length" class="defect-next-steps">
              <strong>建议动作</strong>
              <ul>
                <li v-for="step in item.nextSteps.slice(0, 3)" :key="step">{{ step }}</li>
              </ul>
            </div>

            <div v-if="item.evidence?.length" class="defect-next-steps">
              <strong>失败证据</strong>
              <ul>
                <li v-for="evidence in item.evidence.slice(0, 3)" :key="evidence">{{ evidence }}</li>
              </ul>
            </div>

            <div class="defect-actions">
              <button v-if="item.latestRunId" class="secondary-button" type="button" @click="loadDefectRun(item)">
                <History aria-hidden="true" />
                查看执行
              </button>
              <button class="secondary-button" type="button" @click="updateDefectRecord(item.id, 'status', item.status === 'resolved' ? 'open' : 'resolved')">
                <CheckCircle2 aria-hidden="true" />
                {{ item.status === "resolved" ? "重新打开" : "标记已解决" }}
              </button>
              <button class="secondary-button" type="button" @click="removeDefectRecord(item.id)">
                <Trash2 aria-hidden="true" />
                移除
              </button>
            </div>
          </article>
        </div>
        <div v-else class="empty-state defect-empty">当前没有待跟踪的失败项</div>
      </section>

      <section v-if="isAdmin" class="panel user-panel" aria-labelledby="userAdminTitle">
        <div class="panel-heading result-heading">
          <div>
            <p class="eyebrow">Step 09</p>
            <h2 id="userAdminTitle">用户管理</h2>
          </div>
          <div class="result-actions">
            <button class="icon-button" type="button" aria-label="刷新用户列表" title="刷新用户列表" :disabled="isUsersLoading" @click="fetchUsers">
              <RefreshCw aria-hidden="true" />
            </button>
          </div>
        </div>

        <div class="user-admin-grid">
          <form class="user-create-form" @submit.prevent="createUser">
            <div class="panel-subheading">
              <span class="side-card-label">CREATE USER</span>
              <strong>创建平台账号</strong>
            </div>
            <div class="api-form-row">
              <div class="field-group">
                <label for="newUsername">用户名</label>
                <input id="newUsername" v-model.trim="newUserForm.username" class="text-input" type="text" autocomplete="off" placeholder="tester01" />
              </div>
              <div class="field-group">
                <label for="newDisplayName">显示名称</label>
                <input id="newDisplayName" v-model.trim="newUserForm.displayName" class="text-input" type="text" autocomplete="off" placeholder="测试工程师" />
              </div>
            </div>
            <div class="api-form-row">
              <div class="field-group">
                <label for="newPassword">初始密码</label>
                <input id="newPassword" v-model="newUserForm.password" class="text-input" type="password" autocomplete="new-password" placeholder="Tester@123456" />
              </div>
              <div class="field-group">
                <label for="newRole">角色</label>
                <select id="newRole" v-model="newUserForm.role" class="select-input">
                  <option value="tester">tester</option>
                  <option value="admin">admin</option>
                </select>
              </div>
            </div>
            <label class="check-row">
              <input v-model="newUserForm.isActive" type="checkbox" />
              <span>启用账号</span>
            </label>
            <div v-if="userError" class="auth-error inline-error">
              <AlertTriangle aria-hidden="true" />
              <span>{{ userError }}</span>
            </div>
            <button class="primary-button" type="submit" :disabled="isCreatingUser">
              <UserPlus aria-hidden="true" />
              {{ isCreatingUser ? "创建中" : "创建用户" }}
            </button>
          </form>

          <div class="user-list">
            <div class="panel-subheading">
              <span class="side-card-label">USERS</span>
              <strong>{{ users.length }} 个账号</strong>
            </div>
            <div v-if="users.length" class="user-card-grid">
              <article v-for="user in users" :key="user.id" class="user-card" :class="{ inactive: !user.isActive }">
                <header>
                  <div>
                    <span class="side-card-label">{{ roleLabel(user.role) }}</span>
                    <h3>{{ user.displayName || user.username }}</h3>
                  </div>
                  <span class="pill" :class="user.isActive ? 'run-pass' : 'run-fail'">{{ user.isActive ? "启用" : "禁用" }}</span>
                </header>
                <p>{{ user.username }}</p>
                <small>最近登录：{{ user.lastLoginAt ? formatDate(user.lastLoginAt) : "暂无" }}</small>
                <div class="defect-actions">
                  <button class="secondary-button" type="button" :disabled="user.id === currentUser?.id && user.isActive" @click="toggleUserStatus(user)">
                    <UserCog aria-hidden="true" />
                    {{ user.isActive ? "禁用" : "启用" }}
                  </button>
                </div>
              </article>
            </div>
            <div v-else class="empty-state defect-empty">
              {{ isUsersLoading ? "正在读取用户列表" : "暂无用户" }}
            </div>
          </div>
        </div>
      </section>

      <section class="panel history-panel" aria-labelledby="historyTitle">
        <div class="panel-heading result-heading">
          <div>
            <p class="eyebrow">{{ isAdmin ? "Step 10" : "Step 09" }}</p>
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
  </div>
  <div v-if="toastMessage" class="toast">{{ toastMessage }}</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Copy,
  Download,
  FileText,
  Gauge,
  Database,
  History,
  ListChecks,
  LogIn,
  LogOut,
  Moon,
  Network,
  PlayCircle,
  RefreshCw,
  Search,
  Send,
  Shield,
  Trash2,
  Upload,
  X,
  UserCog,
  UserPlus,
  Users,
  Zap,
} from "lucide-vue-next";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const MAX_CLIENT_FILE_MB = 20;
const DEFECT_STORAGE_KEY = "ai-test-defect-tracker-v1";
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

const authLoading = ref(true);
const currentUser = ref(null);
const loginForm = ref({
  username: "admin",
  password: "Admin@123456",
});
const loginError = ref("");
const isLoggingIn = ref(false);
const users = ref([]);
const isUsersLoading = ref(false);
const isCreatingUser = ref(false);
const userError = ref("");
const newUserForm = ref(createDefaultUserForm());
const fileInput = ref(null);
const selectedFiles = ref([]);
const cases = ref([]);
const historyItems = ref([]);
const apiRunHistory = ref([]);
const uiRunHistory = ref([]);
const downloadUrl = ref("");
const activeView = ref("cards");
const isGenerating = ref(false);
const isDragging = ref(false);
const isHistoryLoading = ref(false);
const isApiRunning = ref(false);
const isApiHistoryLoading = ref(false);
const isUiRunning = ref(false);
const isUiHistoryLoading = ref(false);
const isReviewing = ref(false);
const requirements = ref("");
const context = ref("");
const references = ref("");
const apiTest = ref(createDefaultApiTest());
const apiRunResult = ref(null);
const uiTest = ref(createDefaultUiTest());
const uiRunResult = ref(null);
const statusText = ref("待生成");
const progress = ref(0);
const searchText = ref("");
const historyKeyword = ref("");
const selectedHistoryId = ref("");
const databaseMessage = ref("MySQL 状态检测中");
const databaseConnected = ref(false);
const toastMessage = ref("");
const coverageReport = ref(null);
const caseReviewReport = ref(null);
const openApiContent = ref("");
const openApiUrl = ref("");
const openApiBaseUrl = ref(API_BASE_URL || "http://127.0.0.1:8000");
const openApiSummary = ref({});
const isOpenApiImporting = ref(false);
const caseExecutionMap = ref({});
const localRunDetails = ref({});
const executingCaseId = ref("");
const defectRecords = ref({});
const streamMessages = ref([]);
let toastTimer = null;

const isAuthenticated = computed(() => Boolean(currentUser.value));
const isAdmin = computed(() => currentUser.value?.role === "admin");

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

const executableCaseCount = computed(() => cases.value.filter((item) => Boolean(caseApiConfig(item))).length);

const coverageCards = computed(() => {
  const report = coverageReport.value;
  const coverage = report?.coverage || {};
  const labels = [
    ["requirement", "需求"],
    ["interface", "接口"],
    ["field", "字段"],
    ["exception", "异常"],
    ["permission", "权限"],
    ["boundary", "边界"],
  ];
  return labels.map(([key, label]) => {
    const item = coverage[key] || {};
    return {
      key,
      label,
      covered: item.covered || 0,
      percent: Math.round((item.ratio || 0) * 100),
    };
  });
});

const reviewSummaryCards = computed(() => {
  const report = caseReviewReport.value || {};
  return [
    { label: "总用例", value: report.totalCases ?? cases.value.length, hint: "当前进入评审的用例数" },
    { label: "通过", value: report.approved ?? 0, hint: "结构完整，可进入执行或归档" },
    { label: "需修改", value: report.needsRevision ?? 0, hint: "存在非阻塞修改建议" },
    { label: "阻塞", value: report.blocked ?? 0, hint: "建议先修复后再执行" },
    { label: "质量均分", value: report.averageQualityScore ?? "-", hint: "按当前用例质量评分汇总" },
  ];
});

const reviewChecklist = computed(() => caseReviewReport.value?.checklist || []);
const reviewItems = computed(() => caseReviewReport.value?.items || []);
const reviewTopIssues = computed(() => caseReviewReport.value?.topIssues || []);
const reviewRecommendations = computed(() => caseReviewReport.value?.recommendations || []);

const apiResultClass = computed(() => {
  if (!apiRunResult.value) {
    return "";
  }
  return apiRunResult.value.passed ? "passed" : "failed";
});

const uiResultClass = computed(() => {
  if (!uiRunResult.value) {
    return "";
  }
  return uiRunResult.value.passed ? "passed" : "failed";
});

const advancedConfigCount = computed(() => {
  const fields = [
    apiTest.value.variablesText,
    apiTest.value.assertionsText,
    apiTest.value.extractorsText,
    apiTest.value.databaseAssertionsText,
    apiTest.value.jsonSchemaText,
    apiTest.value.suiteStepsText,
  ];
  return fields.filter((value) => String(value || "").trim() && String(value || "").trim() !== "[]" && String(value || "").trim() !== "{}").length;
});

const allRunRecords = computed(() => {
  const merged = new Map();
  const candidates = [
    ...apiRunHistory.value,
    ...uiRunHistory.value,
    ...Object.values(localRunDetails.value || {}),
    ...Object.values(caseExecutionMap.value || {}),
  ];
  for (const item of candidates) {
    if (!item) {
      continue;
    }
    const key = item.runId || `${item.name || ""}-${item.createdAt || ""}-${item.request?.url || ""}`;
    const existing = merged.get(key);
    merged.set(key, mergeRunRecord(existing, item));
  }
  return Array.from(merged.values()).sort((left, right) => new Date(right.createdAt || 0).getTime() - new Date(left.createdAt || 0).getTime());
});

const reportSummaryCards = computed(() => {
  const totalRuns = allRunRecords.value.length;
  const passedRuns = allRunRecords.value.filter((item) => item.passed).length;
  const failedRuns = totalRuns - passedRuns;
  const passRate = totalRuns ? `${Math.round((passedRuns / totalRuns) * 100)}%` : "-";
  const averageQuality = coverageReport.value?.averageQualityScore ?? "-";
  const automationReady = coverageReport.value?.automationReady ?? executableCaseCount.value;
  const uiRuns = allRunRecords.value.filter((item) => item.runType === "ui").length;
  return [
    { label: "当前用例", value: cases.value.length || "-", hint: "当前页面中的测试用例数" },
    { label: "可执行接口", value: executableCaseCount.value || "-", hint: "具备接口配置的用例数" },
    { label: "UI 执行", value: uiRuns || "-", hint: "已完成的页面自动化执行次数" },
    { label: "执行通过率", value: passRate, hint: `${passedRuns}/${totalRuns || 0} 次执行通过` },
    { label: "失败项", value: failedRuns || "-", hint: "需要继续跟进的执行失败数" },
    { label: "质量均分", value: averageQuality, hint: "当前用例质量平均分" },
    { label: "自动化就绪", value: `${automationReady}/${cases.value.length || 0}`, hint: "适合继续做接口或 UI 自动化的用例" },
  ];
});

const recentReportRuns = computed(() => allRunRecords.value.slice(0, 6));

const reportOverviewText = computed(() => {
  if (!allRunRecords.value.length) {
    return "等待执行数据";
  }
  const latest = allRunRecords.value[0];
  const label = latest.name || `${latest.request?.method || ""} ${latest.request?.url || ""}`.trim();
  return label || "最近一次执行";
});

const reportOverviewHint = computed(() => {
  if (!allRunRecords.value.length) {
    return "先完成一轮接口或 UI 自动化执行，这里会自动汇总最近结果。";
  }
  const latest = allRunRecords.value[0];
  return `${latest.passed ? "最近一次执行通过" : "最近一次执行失败"}，耗时 ${latest.response?.durationMs ?? 0} ms。`;
});

const reportRiskText = computed(() => {
  const risks = coverageReport.value?.risks || [];
  if (!risks.length) {
    return "当前没有额外风险提示。";
  }
  return risks.slice(0, 2).join("；");
});

const defectItems = computed(() =>
  Object.values(defectRecords.value).sort((a, b) => {
    const left = new Date(b.updatedAt || b.createdAt || 0).getTime();
    const right = new Date(a.updatedAt || a.createdAt || 0).getTime();
    return left - right;
  }),
);

const defectOpenCount = computed(() => defectItems.value.filter((item) => item.status !== "resolved").length);

const defectToolbarText = computed(() => {
  if (!defectItems.value.length) {
    return "还没有进入缺陷跟踪的失败项";
  }
  return `共 ${defectItems.value.length} 项失败记录，当前 ${defectOpenCount.value} 项待处理`;
});

const referenceInsights = computed(() => analyzeReferenceLinks(references.value));
const reportMetrics = computed(() => buildReportMetrics());
const reportEnvironmentItems = computed(() => buildReportEnvironmentItems());
const reportScopeItems = computed(() => buildReportScopeItems());
const reportFailureCategoryItems = computed(() => buildReportFailureCategoryItems());
const reportSlowRunItems = computed(() => buildReportSlowRunItems());
const reportDatabaseSummary = computed(() => buildReportDatabaseSummary());
const reportConclusionText = computed(() => buildReportConclusion());

onMounted(async () => {
  document.body.classList.add("dark");
  loadDefectRecords();
  await loadCurrentUser();
});

function toggleTheme() {
  document.body.classList.toggle("dark");
}

async function loadCurrentUser() {
  authLoading.value = true;
  try {
    const response = await fetch(apiUrl("/api/auth/me"), {
      credentials: "include",
    });
    if (!response.ok) {
      currentUser.value = null;
      return;
    }
    const data = await response.json();
    currentUser.value = data.user || null;
    await loadInitialData();
  } catch {
    currentUser.value = null;
  } finally {
    authLoading.value = false;
  }
}

async function loadInitialData() {
  await Promise.allSettled([
    fetchDatabaseStatus(),
    fetchHistory(),
    fetchApiRunHistory(),
    fetchUiRunHistory(),
    isAdmin.value ? fetchUsers() : Promise.resolve(),
  ]);
}

async function submitLogin() {
  if (isLoggingIn.value) {
    return;
  }
  loginError.value = "";
  if (!loginForm.value.username.trim() || !loginForm.value.password) {
    loginError.value = "请输入用户名和密码。";
    return;
  }
  isLoggingIn.value = true;
  try {
    const response = await fetch(apiUrl("/api/auth/login"), {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(loginForm.value),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    const data = await response.json();
    currentUser.value = data.user || null;
    loginForm.value.password = "";
    showToast("登录成功。");
    await loadInitialData();
  } catch (error) {
    loginError.value = error.message || "登录失败。";
  } finally {
    isLoggingIn.value = false;
  }
}

async function logout() {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } finally {
    currentUser.value = null;
    users.value = [];
    showToast("已退出登录。");
  }
}

async function fetchUsers() {
  if (!isAdmin.value) {
    return;
  }
  isUsersLoading.value = true;
  userError.value = "";
  try {
    const response = await apiFetch("/api/auth/users");
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    const data = await response.json();
    users.value = data.items || [];
  } catch (error) {
    userError.value = error.message || "用户列表读取失败。";
    users.value = [];
  } finally {
    isUsersLoading.value = false;
  }
}

async function createUser() {
  if (isCreatingUser.value) {
    return;
  }
  userError.value = "";
  isCreatingUser.value = true;
  try {
    const response = await apiFetch("/api/auth/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newUserForm.value),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    newUserForm.value = createDefaultUserForm();
    await fetchUsers();
    showToast("用户已创建。");
  } catch (error) {
    userError.value = error.message || "创建用户失败。";
  } finally {
    isCreatingUser.value = false;
  }
}

async function toggleUserStatus(user) {
  try {
    const response = await apiFetch(`/api/auth/users/${user.id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ isActive: !user.isActive }),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    await fetchUsers();
    showToast(user.isActive ? "用户已禁用。" : "用户已启用。");
  } catch (error) {
    userError.value = error.message || "更新用户状态失败。";
  }
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
    const response = await apiFetch("/api/generate", {
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
    showToast(error.message || "生成失败");
  } finally {
    isGenerating.value = false;
  }
}

function prepareGenerationState() {
  isGenerating.value = true;
  cases.value = [];
  downloadUrl.value = "";
  coverageReport.value = null;
  caseReviewReport.value = null;
  caseExecutionMap.value = {};
  streamMessages.value = [];
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
    recordStreamMessage(data.text || "生成中");
    progress.value = Math.min(86, 12 + cases.value.length * 4);
    return;
  }

  if (eventName === "case") {
    cases.value.push(data);
    progress.value = Math.min(92, 18 + cases.value.length * 4);
    return;
  }

  if (eventName === "cases") {
    cases.value = data.items || cases.value;
    return;
  }

  if (eventName === "coverage") {
    coverageReport.value = data;
    return;
  }

  if (eventName === "done") {
    downloadUrl.value = data.downloadUrl;
    coverageReport.value = data.coverageReport || coverageReport.value;
    statusText.value = `完成，已保存 ${data.count || cases.value.length} 条`;
    progress.value = 100;
    runCaseReview(true);
    fetchDatabaseStatus();
    fetchHistory();
    return;
  }

  if (eventName === "error") {
    statusText.value = "生成失败";
    showToast(data.message || "生成失败");
  }
}

function resetAll() {
  selectedFiles.value.forEach((item) => {
    if (item.url) {
      URL.revokeObjectURL(item.url);
    }
  });
  selectedFiles.value = [];
  cases.value = [];
  downloadUrl.value = "";
  coverageReport.value = null;
  caseReviewReport.value = null;
  caseExecutionMap.value = {};
  streamMessages.value = [];
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

async function importOpenApi() {
  if (isOpenApiImporting.value) {
    return;
  }
  if (!openApiUrl.value.trim() && !openApiContent.value.trim()) {
    showToast("请填写 OpenAPI URL 或粘贴 JSON/YAML 内容。");
    return;
  }

  isOpenApiImporting.value = true;
  statusText.value = "导入 Swagger";
  try {
    const response = await apiFetch("/api/openapi/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: openApiUrl.value.trim(),
        content: openApiContent.value.trim(),
        baseUrl: openApiBaseUrl.value.trim(),
      }),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    const data = await response.json();
    cases.value = data.cases || [];
    coverageReport.value = data.coverageReport || null;
    openApiSummary.value = {
      title: data.title,
      operationCount: data.operationCount,
      caseCount: data.caseCount,
    };
    downloadUrl.value = data.downloadUrl || "";
    statusText.value = `Swagger 已生成 ${cases.value.length} 条`;
    progress.value = 100;
    activeView.value = "cards";
    runCaseReview(true);
    fetchHistory();
    showToast("OpenAPI 用例已生成。");
  } catch (error) {
    showToast(error.message || "OpenAPI 导入失败");
  } finally {
    isOpenApiImporting.value = false;
  }
}

async function runCaseReview(silent = false) {
  if (!cases.value.length) {
    caseReviewReport.value = null;
    if (!silent) {
      showToast("请先生成或导入用例。");
    }
    return;
  }
  isReviewing.value = true;
  try {
    const response = await apiFetch("/api/cases/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cases: cases.value }),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    caseReviewReport.value = await response.json();
    if (!silent) {
      showToast(`评审完成：${caseReviewReport.value.verdict || "待评审"}`);
    }
  } catch (error) {
    if (!silent) {
      showToast(error.message || "用例评审失败");
    }
  } finally {
    isReviewing.value = false;
  }
}

function resetOpenApiImport() {
  openApiContent.value = "";
  openApiUrl.value = "";
  openApiBaseUrl.value = API_BASE_URL || "http://127.0.0.1:8000";
  openApiSummary.value = {};
}

async function fetchDatabaseStatus() {
  try {
    const response = await apiFetch("/api/database/status");
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
    const response = await apiFetch(`/api/history?${params.toString()}`);
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

  let payload;
  try {
    payload = buildApiPayload();
  } catch (error) {
    showToast(error.message || "接口配置格式不正确");
    return;
  }

  isApiRunning.value = true;
  apiRunResult.value = null;
  try {
    const response = await apiFetch("/api/api-tests/run", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }

    const data = await response.json();
    apiRunResult.value = data;
    rememberRunDetail(data);
    showToast(data.passed ? "接口测试执行通过。" : "接口测试执行未通过。");
    fetchApiRunHistory();
  } catch (error) {
    showToast(error.message || "接口执行失败");
  } finally {
    isApiRunning.value = false;
  }
}

async function executeGeneratedCase(item) {
  const config = caseApiConfig(item);
  if (!config) {
    showToast("这条用例没有可执行接口配置。");
    return;
  }
  const caseId = item.id || item.title || String(Date.now());
  executingCaseId.value = caseId;
  try {
    const response = await apiFetch("/api/cases/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        case: item,
        apiTest: config,
      }),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    const data = await response.json();
    rememberRunDetail(data);
    caseExecutionMap.value = { ...caseExecutionMap.value, [caseId]: data };
    cases.value = cases.value.map((current) =>
      (current.id || current.title) === caseId
        ? {
            ...current,
            execution: {
              runId: data.runId,
              passed: data.passed,
              statusCode: data.response?.statusCode,
              durationMs: data.response?.durationMs,
              executedAt: data.createdAt,
            },
            failure_analysis: data.failureAnalysis,
          }
        : current,
    );
    apiRunResult.value = data;
    fetchApiRunHistory();
    showToast(data.passed ? "生成用例执行通过。" : "生成用例执行未通过。");
  } catch (error) {
    showToast(error.message || "生成用例执行失败");
  } finally {
    executingCaseId.value = "";
  }
}

async function runApiSuite() {
  if (isApiRunning.value) {
    return;
  }

  let steps;
  let variables;
  try {
    steps = parseJsonText(apiTest.value.suiteStepsText, [], "用例集步骤 JSON");
    variables = parseJsonText(apiTest.value.variablesText, {}, "环境变量 JSON");
  } catch (error) {
    showToast(error.message || "用例集配置格式不正确");
    return;
  }
  if (!Array.isArray(steps) || !steps.length) {
    showToast("请在用例集步骤 JSON 中至少配置 1 个步骤。");
    return;
  }

  isApiRunning.value = true;
  apiRunResult.value = null;
  try {
    const response = await apiFetch("/api/api-tests/suite", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: `${apiTest.value.name || "接口"}用例集`,
        variables,
        steps,
        stopOnFailure: false,
      }),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    const data = await response.json();
    apiRunResult.value = data;
    rememberRunDetail(data);
    showToast(data.passed ? "接口用例集执行通过。" : "接口用例集存在失败。");
    fetchApiRunHistory();
  } catch (error) {
    showToast(error.message || "接口用例集执行失败");
  } finally {
    isApiRunning.value = false;
  }
}

async function runApiLoad() {
  if (isApiRunning.value) {
    return;
  }

  let payload;
  try {
    payload = buildApiPayload();
  } catch (error) {
    showToast(error.message || "并发配置格式不正确");
    return;
  }

  isApiRunning.value = true;
  apiRunResult.value = null;
  try {
    const response = await apiFetch("/api/api-tests/load", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...payload,
        repeat: Number(apiTest.value.repeat) || 10,
        concurrency: Number(apiTest.value.concurrency) || 3,
      }),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    const data = await response.json();
    apiRunResult.value = data;
    rememberRunDetail(data);
    showToast(data.passed ? "并发执行全部通过。" : "并发执行存在失败。");
    fetchApiRunHistory();
  } catch (error) {
    showToast(error.message || "并发执行失败");
  } finally {
    isApiRunning.value = false;
  }
}

async function fetchApiRunHistory() {
  isApiHistoryLoading.value = true;
  try {
    const response = await apiFetch("/api/api-tests/history?limit=20");
    const data = await response.json();
    apiRunHistory.value = data.items || [];
    syncDefectCandidates();
  } catch (error) {
    apiRunHistory.value = [];
  } finally {
    isApiHistoryLoading.value = false;
  }
}

async function runUiTest() {
  if (isUiRunning.value) {
    return;
  }

  let payload;
  try {
    payload = buildUiPayload();
  } catch (error) {
    showToast(error.message || "UI 自动化配置格式不正确");
    return;
  }

  isUiRunning.value = true;
  uiRunResult.value = null;
  try {
    const response = await apiFetch("/api/ui-tests/run", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }

    const data = await response.json();
    uiRunResult.value = data;
    rememberRunDetail(data);
    showToast(data.passed ? "UI 自动化执行通过。" : "UI 自动化执行未通过。");
    fetchUiRunHistory();
    syncDefectCandidates();
  } catch (error) {
    showToast(error.message || "UI 自动化执行失败");
  } finally {
    isUiRunning.value = false;
  }
}

async function fetchUiRunHistory() {
  isUiHistoryLoading.value = true;
  try {
    const response = await apiFetch("/api/ui-tests/history?limit=20");
    const data = await response.json();
    uiRunHistory.value = data.items || [];
    syncDefectCandidates();
  } catch (error) {
    uiRunHistory.value = [];
  } finally {
    isUiHistoryLoading.value = false;
  }
}

function loadUiRun(item) {
  uiRunResult.value = mergeRunRecord(item, localRunDetails.value[item.runId] || null);
  uiTest.value = {
    ...createDefaultUiTest(),
    name: item.name || "",
    baseUrl: item.request?.url || "",
    browser: item.request?.browser || "chromium",
  };
}

function resetUiTest() {
  uiTest.value = createDefaultUiTest();
  uiRunResult.value = null;
}

function loadApiRun(item) {
  apiRunResult.value = mergeRunRecord(item, localRunDetails.value[item.runId] || null);
  apiTest.value = {
    ...createDefaultApiTest(),
    name: item.name || "",
    method: item.request?.method || "GET",
    url: item.request?.url || "",
    headersText: JSON.stringify(item.request?.headers || {}, null, 2),
    body: item.request?.body || "",
    bodyMode: item.request?.bodyMode || "raw",
    expectedStatus: item.expected?.status ?? "",
    expectedContains: item.expected?.contains || "",
    maxResponseMs: item.expected?.maxResponseMs ?? "",
    timeoutSeconds: 10,
  };
}

function loadDefectRecords() {
  if (typeof window === "undefined") {
    return;
  }
  try {
    const text = window.localStorage.getItem(DEFECT_STORAGE_KEY);
    defectRecords.value = text ? JSON.parse(text) : {};
  } catch {
    defectRecords.value = {};
  }
}

function persistDefectRecords() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(DEFECT_STORAGE_KEY, JSON.stringify(defectRecords.value));
}

function syncDefectCandidates() {
  const merged = { ...defectRecords.value };
  const candidates = allRunRecords.value.filter((item) => item?.passed === false);

  candidates.forEach((item) => {
    const id = defectRecordId(item);
    const existing = merged[id] || {};
    const failure = item.failureAnalysis || {};
    const evidence = Array.isArray(failure.evidence) ? failure.evidence : [];
    const failedAssertions = (item.assertions || []).filter((entry) => entry && entry.passed === false).map((entry) => entry.name).slice(0, 5);
    const previousRuns = Array.isArray(existing.runIds) ? existing.runIds : [];
    const nextRunIds = item.runId ? Array.from(new Set([...previousRuns, item.runId])) : previousRuns;
    merged[id] = {
      id,
      title: item.caseTitle || item.name || `${item.request?.method || ""} ${item.request?.url || ""}`.trim() || "未命名失败项",
      source: item.caseTitle ? "生成用例执行" : runTypeLabel(item.runType),
      summary: failure.summary || item.error || item.response?.bodyPreview || "执行失败",
      requestLabel: `${item.request?.method || "-"} ${item.request?.url || "-"}`,
      latestRunId: item.runId || existing.latestRunId || "",
      runIds: nextRunIds,
      caseIds: Array.from(new Set([...(existing.caseIds || []), ...(item.caseId ? [item.caseId] : [])])),
      responseStatus: item.response?.statusCode ?? existing.responseStatus ?? null,
      responsePreview: item.response?.bodyPreview || existing.responsePreview || "",
      failedAssertions,
      failureCategory: failure.category || existing.failureCategory || "",
      confidence: failure.confidence || existing.confidence || 0,
      evidence,
      shouldCreateDefect: Boolean(failure.shouldCreateDefect ?? existing.shouldCreateDefect),
      nextSteps: Array.isArray(failure.nextSteps) ? failure.nextSteps : [],
      createdAt: item.createdAt || existing.createdAt || "",
      status: existing.status || "open",
      severity: existing.severity || inferDefectSeverity(item),
      owner: existing.owner || "",
      note: existing.note || "",
      occurrences: Math.max(existing.occurrences || 0, nextRunIds.length || 1),
      updatedAt: item.createdAt || new Date().toISOString(),
    };
  });

  defectRecords.value = merged;
  persistDefectRecords();
}

function defectRecordId(item) {
  const failure = item.failureAnalysis || {};
  const parts = [
    item.caseId || item.caseTitle || item.name || "",
    item.request?.method || "",
    item.request?.url || "",
    failure.category || "",
    ((item.assertions || []).filter((entry) => entry && entry.passed === false).map((entry) => entry.name).join("|")) || "",
  ];
  return `defect:${parts.join("::") || Date.now()}`;
}

function inferDefectSeverity(item) {
  const summary = `${item.failureAnalysis?.summary || ""} ${item.error || ""}`.toLowerCase();
  if (summary.includes("鉴权") || summary.includes("权限") || summary.includes("数据库") || summary.includes("后端")) {
    return "high";
  }
  if (summary.includes("参数") || summary.includes("断言")) {
    return "medium";
  }
  return "low";
}

function updateDefectRecord(id, field, value) {
  const current = defectRecords.value[id];
  if (!current) {
    return;
  }
  defectRecords.value = {
    ...defectRecords.value,
    [id]: {
      ...current,
      [field]: value,
      updatedAt: new Date().toISOString(),
    },
  };
  persistDefectRecords();
}

function removeDefectRecord(id) {
  const next = { ...defectRecords.value };
  delete next[id];
  defectRecords.value = next;
  persistDefectRecords();
}

function defectStatusLabel(status) {
  const labels = {
    open: "待处理",
    in_progress: "处理中",
    resolved: "已解决",
  };
  return labels[status] || "待处理";
}

function defectStatusClass(status) {
  return `defect-status-${status || "open"}`;
}

function resetApiTest() {
  apiTest.value = createDefaultApiTest();
  apiRunResult.value = null;
}

async function loadHistoryDetail(sessionId) {
  try {
    const response = await apiFetch(`/api/history/${encodeURIComponent(sessionId)}`);
    if (!response.ok) {
      throw new Error("历史记录不存在或 MySQL 暂不可用");
    }
    const detail = await response.json();
    selectedHistoryId.value = sessionId;
    cases.value = detail.cases || [];
    caseExecutionMap.value = {};
    caseReviewReport.value = null;
    streamMessages.value = [];
    coverageReport.value = await analyzeCurrentCoverage(cases.value);
    downloadUrl.value = detail.downloadUrl || "";
    statusText.value = `已加载历史 ${cases.value.length} 条`;
    progress.value = cases.value.length ? 100 : 0;
    activeView.value = "cards";
    runCaseReview(true);
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

function rememberRunDetail(run) {
  if (!run?.runId) {
    return;
  }
  localRunDetails.value = {
    ...localRunDetails.value,
    [run.runId]: mergeRunRecord(localRunDetails.value[run.runId] || null, run),
  };
}

function mergeRunRecord(base, override) {
  if (!base) {
    return override ? JSON.parse(JSON.stringify(override)) : null;
  }
  if (!override) {
    return JSON.parse(JSON.stringify(base));
  }
  return {
    ...base,
    ...override,
    request: {
      ...(base.request || {}),
      ...(override.request || {}),
    },
    expected: {
      ...(base.expected || {}),
      ...(override.expected || {}),
    },
    response: {
      ...(base.response || {}),
      ...(override.response || {}),
    },
    summary: {
      ...(base.summary || {}),
      ...(override.summary || {}),
    },
    failureAnalysis: override.failureAnalysis || base.failureAnalysis || null,
    databaseChecks: override.databaseChecks || base.databaseChecks || [],
    extractions: override.extractions || base.extractions || [],
    variables: override.variables || base.variables || {},
    assertions: override.assertions || base.assertions || [],
    steps: override.steps || base.steps || [],
    artifacts: override.artifacts || base.artifacts || {},
    consoleMessages: override.consoleMessages || base.consoleMessages || [],
    networkErrors: override.networkErrors || base.networkErrors || [],
  };
}

function recordStreamMessage(text) {
  if (!text) {
    return;
  }
  streamMessages.value = [
    ...streamMessages.value,
    {
      id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      text: String(text),
    },
  ].slice(-12);
}

function clientMaterialStatus(item) {
  if (item?.isImage) {
    return {
      label: "视觉材料",
      detail: "生成时会把图片作为多模态输入发送给模型。",
    };
  }
  const extension = String(item?.extension || "").toLowerCase();
  if (["xlsx", "xlsm", "xls", "csv", "tsv"].includes(extension)) {
    return {
      label: "表格抽取",
      detail: "上传后会优先抽取表格文本和字段结构。",
    };
  }
  if (["docx", "pdf"].includes(extension)) {
    return {
      label: "文档抽取",
      detail: "上传后会尝试提取正文，再并入生成上下文。",
    };
  }
  if (["json", "yaml", "yml", "md", "markdown", "txt", "html", "htm", "log", "feature"].includes(extension)) {
    return {
      label: "文本解析",
      detail: "上传后会读取文本内容并作为规则来源。",
    };
  }
  return {
    label: "文件线索",
    detail: "当前类型可能只保留文件名作为上下文提示。",
  };
}

function analyzeReferenceLinks(text) {
  const matches = String(text || "").match(/https?:\/\/[^\s)]+/g) || [];
  return matches.map((url) => {
    const lower = url.toLowerCase();
    if (lower.includes("openapi.json") || lower.endsWith(".json") || lower.endsWith(".yaml") || lower.endsWith(".yml")) {
      return {
        url,
        type: "OpenAPI",
        status: "可结构化解析",
        state: "good",
        suggestion: "这是最适合导入 Swagger 模块的链接类型，可直接生成接口用例。",
      };
    }
    if (lower.includes("swagger-ui") || lower.includes("/swagger") || lower.includes("/docs")) {
      return {
        url,
        type: "Swagger UI",
        status: "建议换源",
        state: "warn",
        suggestion: "优先改填 openapi.json / swagger.json 地址，页面链接本身通常不适合直接解析。",
      };
    }
    if (lower.includes("feishu.cn") || lower.includes("larksuite.com")) {
      return {
        url,
        type: "飞书文档",
        status: "可尝试授权读取",
        state: "warn",
        suggestion: "后端配置 FEISHU_APP_ID / FEISHU_APP_SECRET 且应用具备文档权限时，可读取 docx、docs/doc 和 wiki 正文；无授权时仍建议上传导出文件或粘贴关键内容。",
      };
    }
    if (lower.includes("yuque.com")) {
      return {
        url,
        type: "语雀",
        status: "可能需要登录",
        state: "warn",
        suggestion: "如果是私有知识库，平台更适合读取你导出的文件或你手动粘贴的关键段落。",
      };
    }
    if (lower.includes("confluence")) {
      return {
        url,
        type: "Confluence",
        status: "可能需要登录",
        state: "warn",
        suggestion: "建议确认是否可公开访问；若不可公开，请上传导出文件。",
      };
    }
    if (lower.includes("apifox") || lower.includes("yapi")) {
      return {
        url,
        type: "接口平台",
        status: "优先找 OpenAPI",
        state: "warn",
        suggestion: "这类页面更适合作为线索，最好补充 OpenAPI JSON/YAML 地址。",
      };
    }
    return {
      url,
      type: "网页链接",
      status: "仅作辅助上下文",
      state: "info",
      suggestion: "普通网页可能只能作为背景参考；若要稳定生成用例，建议补充正文或导出文件。",
    };
  });
}

function buildReportMetrics() {
  const runs = allRunRecords.value;
  const totalRuns = runs.length;
  const passedRuns = runs.filter((item) => item.passed).length;
  const failedRuns = runs.filter((item) => item.passed === false).length;
  const skippedRuns = Math.max(0, executableCaseCount.value - runs.filter((item) => item.caseId || item.caseTitle).length);
  const interfaceCoverage = Math.round(((coverageReport.value?.coverage?.interface?.ratio || 0) * 100));
  const requirementCoverage = Math.round(((coverageReport.value?.coverage?.requirement?.ratio || 0) * 100));
  const exceptionCoverage = Math.round(((coverageReport.value?.coverage?.exception?.ratio || 0) * 100));
  const automationReadyRatio = Math.round(((coverageReport.value?.automationRatio || 0) * 100));
  const averageQuality = coverageReport.value?.averageQualityScore ?? "-";
  const failedGeneratedCases = runs.filter((item) => item.passed === false && (item.caseId || item.caseTitle));
  const p0Failures = failedGeneratedCases.filter((item) => findCasePriority(item) === "P0").length;
  const p1Failures = failedGeneratedCases.filter((item) => findCasePriority(item) === "P1").length;
  const durations = runs.map((item) => Number(item.response?.durationMs || 0)).filter((item) => item > 0);
  const averageDuration = durations.length ? Math.round(durations.reduce((sum, item) => sum + item, 0) / durations.length) : 0;
  const slowest = buildReportSlowRunItems()[0];
  return {
    totalRuns,
    totalCases: cases.value.length,
    passedRuns,
    failedRuns,
    skippedRuns,
    passRate: totalRuns ? `${Math.round((passedRuns / totalRuns) * 100)}%` : "-",
    interfaceCoverage: `${interfaceCoverage}%`,
    requirementCoverage: `${requirementCoverage}%`,
    exceptionCoverage: `${exceptionCoverage}%`,
    automationReadyRatio: `${automationReadyRatio}%`,
    averageQuality,
    p0Failures,
    p1Failures,
    defectCount: defectItems.value.length,
    unresolvedDefects: defectOpenCount.value,
    averageDuration,
    slowestInterface: slowest ? `${slowest.label} · ${slowest.durationMs} ms` : "-",
  };
}

function buildReportEnvironmentItems() {
  const baseUrl = API_BASE_URL || openApiBaseUrl.value || extractBaseUrl(apiTest.value.url) || "未配置";
  return [
    { label: "接口基础地址", value: baseUrl },
    { label: "UI 基础地址", value: uiTest.value.baseUrl || "未配置" },
    { label: "数据库状态", value: databaseMessage.value || "未检测" },
    { label: "历史记录", value: databaseConnected.value ? "MySQL 已连接" : "MySQL 未连接" },
    { label: "当前报告来源", value: openApiSummary.value.title || "当前工作台 / 接口执行结果" },
  ];
}

function buildReportScopeItems() {
  const modules = Array.from(new Set(cases.value.map((item) => item.module).filter(Boolean)));
  const priorities = priorityMix.value || "-";
  return [
    { label: "用例模块范围", value: modules.slice(0, 4).join("、") || "当前未生成用例" },
    { label: "优先级分布", value: priorities },
    { label: "可执行接口用例", value: `${executableCaseCount.value}/${cases.value.length || 0}` },
    { label: "UI 自动化执行", value: `${allRunRecords.value.filter((item) => item.runType === "ui").length} 次` },
    { label: "测试范围说明", value: `${cases.value.length || 0} 条用例，覆盖主流程、异常、边界和权限等维度` },
  ];
}

function buildReportFailureCategoryItems() {
  const counts = {};
  for (const item of allRunRecords.value.filter((run) => run.passed === false)) {
    const key = inferRunFailureCategory(item);
    counts[key] = (counts[key] || 0) + 1;
  }
  return Object.entries(counts)
    .map(([key, value]) => ({ label: failureCategoryLabel(key), value }))
    .sort((left, right) => right.value - left.value);
}

function buildReportSlowRunItems() {
  return allRunRecords.value
    .map((item) => ({
      runId: item.runId,
      label: item.name || `${item.request?.method || ""} ${item.request?.url || ""}`.trim() || "未命名执行",
      durationMs: Number(item.response?.durationMs || 0),
      statusCode: item.response?.statusCode ?? "-",
      method: runTypeLabel(item.runType),
      url: item.request?.url || "-",
      status: runStatusLabel(item),
    }))
    .filter((item) => item.durationMs > 0)
    .sort((left, right) => right.durationMs - left.durationMs)
    .slice(0, 5);
}

function buildReportDatabaseSummary() {
  const checks = allRunRecords.value.flatMap((item) => item.databaseChecks || []);
  const passed = checks.filter((item) => item.passed).length;
  const failed = checks.filter((item) => item.passed === false).length;
  const recentFailures = checks.filter((item) => item.passed === false).slice(0, 4);
  return {
    total: checks.length,
    passed,
    failed,
    recentFailures,
  };
}

function buildReportConclusion() {
  const metrics = reportMetrics.value;
  const categoryTop = buildReportFailureCategoryItems()[0];
  const riskCount = (coverageReport.value?.risks || []).length;
  if (metrics.p0Failures > 0) {
    return `当前存在 ${metrics.p0Failures} 条 P0 失败，用例风险较高，建议阻塞上线并优先修复。`;
  }
  if (metrics.failedRuns > 0) {
    return `当前共有 ${metrics.failedRuns} 条执行失败，主要集中在${categoryTop?.label || "失败场景"}，建议修复后再做回归。`;
  }
  if (riskCount > 0) {
    return `当前执行结果整体通过，但仍有 ${riskCount} 项覆盖风险，建议补齐后再作为正式结论。`;
  }
  return "当前执行结果整体稳定，未发现阻塞性失败，可以进入下一轮回归或发布评审。";
}

function extractBaseUrl(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.protocol}//${parsed.host}`;
  } catch {
    return "";
  }
}

function findCasePriority(run) {
  const matched = cases.value.find((item) => item.id === run.caseId || item.title === run.caseTitle || item.title === run.name);
  return matched?.priority || "";
}

function inferRunFailureCategory(run) {
  if (run.failureAnalysis?.category) {
    return run.failureAnalysis.category;
  }
  if (run.runType === "ui") {
    const text = `${run.error || ""} ${run.response?.bodyPreview || ""}`.toLowerCase();
    if (text.includes("timeout") || text.includes("超时")) {
      return "ui_timeout";
    }
    if (text.includes("locator") || text.includes("strict mode") || text.includes("定位")) {
      return "ui_locator";
    }
    if (text.includes("http") || text.includes("页面返回")) {
      return "ui_navigation";
    }
    if ((run.networkErrors || []).length) {
      return "ui_network";
    }
    return "ui_assertion";
  }
  const status = Number(run.response?.statusCode || 0);
  const error = String(run.error || "").toLowerCase();
  if (error.includes("超时") || error.includes("timeout") || error.includes("connect")) {
    return "environment";
  }
  if (status === 401 || status === 403) {
    return "auth";
  }
  if (status === 400 || status === 422) {
    return "request_params";
  }
  if (status === 404) {
    return "api_contract_changed";
  }
  if (status >= 500) {
    return "backend_bug";
  }
  const databaseAssertion = (run.assertions || []).some((item) => item.category === "database" && item.passed === false);
  if (databaseAssertion) {
    return "database_consistency";
  }
  return "assertion";
}

function failureCategoryLabel(category) {
  const labels = {
    environment: "环境问题",
    auth: "鉴权问题",
    request_params: "参数问题",
    assertion: "断言问题",
    api_contract_changed: "契约变化",
    backend_bug: "后端缺陷",
    database_consistency: "数据库一致性",
    ui_timeout: "UI 超时",
    ui_locator: "UI 定位器",
    ui_assertion: "UI 断言",
    ui_navigation: "页面访问",
    ui_network: "页面网络",
    ui_runtime: "UI 执行",
    passed: "执行通过",
  };
  return labels[category] || "其他";
}

function caseReadiness(item) {
  return (
    item?.quality?.executionReadiness || {
      kind: caseApiConfig(item) ? "api" : "manual",
      ready: Boolean(caseApiConfig(item)),
      status: caseApiConfig(item) ? "ready" : "manual",
      label: caseApiConfig(item) ? "可执行" : "手工用例",
      reason: caseApiConfig(item) ? "接口配置已存在，可直接执行。" : "当前没有接口执行配置。",
      missing: caseApiConfig(item) ? [] : ["api_test"],
    }
  );
}

function caseReadinessClass(item) {
  const status = caseReadiness(item).status;
  if (status === "ready") {
    return "execution-ready-pill";
  }
  if (status === "needs_info") {
    return "execution-warn-pill";
  }
  return "execution-manual-pill";
}

function reviewStatusLabel(status) {
  const labels = {
    approved: "通过",
    needs_revision: "需修改",
    blocked: "阻塞",
  };
  return labels[status] || "待评审";
}

function reviewStatusClass(status) {
  return `review-status-${status || "empty"}`;
}

function downloadReport(format = "md") {
  const content = format === "html" ? createReportHtml() : createReportMarkdown();
  const mimeType = format === "html" ? "text/html;charset=utf-8" : "text/markdown;charset=utf-8";
  const extension = format === "html" ? "html" : "md";
  const blob = new Blob([content], { type: mimeType });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = `test-report-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.${extension}`;
  link.click();
  URL.revokeObjectURL(url);
}

function createReportMarkdown() {
  const model = buildReportModel();
  const lines = [
    "# 测试报告",
    "",
    `- 生成时间：${model.generatedAt}`,
    `- 执行总次数：${model.metrics.totalRuns}`,
    `- 用例总数：${model.metrics.totalCases}`,
    `- 通过数：${model.metrics.passedRuns}`,
    `- 失败数：${model.metrics.failedRuns}`,
    `- 跳过数：${model.metrics.skippedRuns}`,
    `- 通过率：${model.metrics.passRate}`,
    `- 接口覆盖率：${model.metrics.interfaceCoverage}`,
    `- 需求覆盖率：${model.metrics.requirementCoverage}`,
    `- 异常场景覆盖率：${model.metrics.exceptionCoverage}`,
    `- 自动化就绪比例：${model.metrics.automationReadyRatio}`,
    `- 质量平均分：${model.metrics.averageQuality}`,
    "",
    "## 报告概览",
    ...Object.entries(model.metrics).map(([key, value]) => `- ${metricLabel(key)}：${value}`),
    "",
    "## 测试环境",
    ...model.environment.map((item) => `- ${item.label}：${item.value}`),
    "",
    "## 测试范围",
    ...model.scope.map((item) => `- ${item.label}：${item.value}`),
    "",
    "## 用例执行统计",
    ...model.caseExecutionStats.map((item) => `- ${item.label}：${item.value}`),
    "",
    "## 自动化执行统计",
    ...model.apiExecutionStats.map((item) => `- ${item.label}：${item.value}`),
    "",
    "## 覆盖率分析",
    ...model.coverageAnalysis.map((item) => `- ${item.label}：${item.value}${item.note ? `（${item.note}）` : ""}`),
    "",
    "## 用例质量分析",
    ...model.qualityAnalysis.map((item) => `- ${item.label}：${item.value}`),
    "",
    "## 失败分析",
    ...(model.failureAnalysis.length ? model.failureAnalysis.map((item) => `- ${item.label}：${item.value}`) : ["- 当前没有失败分类数据"]),
    "",
    "## 缺陷跟踪",
    ...(model.defects.length ? model.defects.map((item) => `- ${item.title} | 状态：${item.status} | 优先级：${item.severity} | 重复：${item.occurrences}`) : ["- 当前没有缺陷记录"]),
    "",
    "## 慢执行统计",
    ...(model.slowRuns.length ? model.slowRuns.map((item) => `- ${item.label} · ${item.durationMs} ms · ${item.status}`) : ["- 当前没有慢执行数据"]),
    "",
    "## 数据库校验结果",
    ...model.databaseChecks.map((item) => `- ${item.label}：${item.value}`),
    "",
    "## 风险提示",
    ...(model.risks.length ? model.risks.map((item) => `- ${item}`) : ["- 当前没有额外风险提示"]),
    "",
    "## 测试结论",
    `- ${model.conclusion}`,
    "",
    "## 附录：执行明细",
    ...(model.executionDetails.length ? model.executionDetails.map((item) => `- [${item.result}] ${item.name} | ${item.method} ${item.url} | HTTP ${item.statusCode} | ${item.durationMs} ms`) : ["- 当前没有执行明细"]),
  ];
  return lines.filter(Boolean).join("\n");
}

function createReportHtml() {
  const model = buildReportModel();
  const css = `
    body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#071019;color:#e9f6ff}
    .page{max-width:1200px;margin:0 auto;padding:32px 28px 60px}
    h1,h2,h3{margin:0}
    h1{font-size:32px;margin-bottom:10px}
    h2{font-size:20px;margin:28px 0 12px;color:#6ee7ff}
    h3{font-size:16px;margin-bottom:10px}
    p,li,td,th{line-height:1.6}
    .muted{color:#9cb8c7}
    .hero,.card,.table-wrap{background:#0c1724;border:1px solid #1b3448;border-radius:12px}
    .hero{padding:24px}
    .grid{display:grid;gap:14px}
    .summary-grid{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:18px}
    .card{padding:16px}
    .metric{font-size:28px;font-weight:700;margin-top:8px}
    .section-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
    table{width:100%;border-collapse:collapse}
    th,td{padding:10px 12px;border-bottom:1px solid #1b3448;text-align:left;vertical-align:top}
    th{color:#6ee7ff;background:#0f1d2d}
    .pill{display:inline-block;padding:2px 8px;border-radius:999px;background:#12283a;border:1px solid #244762;color:#cdeeff;font-size:12px}
    .risk{color:#ffd166}
    .fail{color:#ff8fa3}
    .pass{color:#38d39f}
    ul{margin:0;padding-left:18px}
    @media (max-width: 900px){.summary-grid,.section-grid{grid-template-columns:1fr}}
  `;
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>测试报告</title>
  <style>${css}</style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>测试报告</h1>
      <p class="muted">生成时间：${escapeHtml(model.generatedAt)}</p>
      <div class="grid summary-grid">
        ${model.summaryCards.map((item) => `<article class="card"><span class="muted">${escapeHtml(item.label)}</span><div class="metric">${escapeHtml(String(item.value))}</div><p class="muted">${escapeHtml(item.hint || "")}</p></article>`).join("")}
      </div>
    </section>

    ${renderDefinitionSection("报告概览", model.overview)}
    ${renderDefinitionSection("测试环境", model.environment)}
    ${renderDefinitionSection("测试范围", model.scope)}
    ${renderDefinitionSection("用例执行统计", model.caseExecutionStats)}
    ${renderDefinitionSection("自动化执行统计", model.apiExecutionStats)}
    ${renderDefinitionSection("覆盖率分析", model.coverageAnalysis)}
    ${renderDefinitionSection("用例质量分析", model.qualityAnalysis)}
    ${renderDefinitionSection("失败分析", model.failureAnalysis, "当前没有失败分类数据。")}
    ${renderTableSection("缺陷跟踪", ["标题", "状态", "优先级", "重复次数", "负责人"], model.defects.map((item) => [item.title, item.status, item.severity, item.occurrences, item.owner || "-"]), "当前没有缺陷记录。")}
    ${renderTableSection("慢执行统计", ["名称", "类型", "目标", "耗时(ms)", "状态"], model.slowRuns.map((item) => [item.label, item.method, item.url, item.durationMs, item.status]), "当前没有慢执行数据。")}
    ${renderDefinitionSection("数据库校验结果", model.databaseChecks)}
    ${renderListSection("风险提示", model.risks, "当前没有额外风险提示。")}
    <section><h2>测试结论</h2><div class="card"><p>${escapeHtml(model.conclusion)}</p></div></section>
    ${renderTableSection("附录：执行明细", ["结果", "名称", "方法", "URL", "状态码", "耗时(ms)", "时间"], model.executionDetails.map((item) => [item.result, item.name, item.method, item.url, item.statusCode, item.durationMs, item.createdAt]), "当前没有执行明细。")}
    <section><h2>附加说明</h2><div class="card"><p>Markdown 报告下载：平台同时支持导出 Markdown 版本，便于存档、邮件发送和二次编辑。</p></div></section>
  </div>
</body>
</html>`;
}

function buildReportModel() {
  const metrics = reportMetrics.value;
  const overview = [
    { label: "执行总次数", value: metrics.totalRuns },
    { label: "用例总数", value: metrics.totalCases },
    { label: "通过数", value: metrics.passedRuns },
    { label: "失败数", value: metrics.failedRuns },
    { label: "跳过数", value: metrics.skippedRuns },
    { label: "通过率", value: metrics.passRate },
  ];
  return {
    generatedAt: formatDate(new Date().toISOString()),
    metrics,
    summaryCards: [
      { label: "执行总次数", value: metrics.totalRuns, hint: "当前可用于报告的执行记录总数" },
      { label: "通过率", value: metrics.passRate, hint: "按当前执行记录计算" },
      { label: "自动化就绪比例", value: metrics.automationReadyRatio, hint: "具备接口执行条件的用例比例" },
      { label: "质量平均分", value: metrics.averageQuality, hint: "当前用例质量均分" },
    ],
    overview,
    environment: reportEnvironmentItems.value,
    scope: reportScopeItems.value,
    caseExecutionStats: [
      { label: "执行总次数", value: metrics.totalRuns },
      { label: "用例总数", value: metrics.totalCases },
      { label: "通过数", value: metrics.passedRuns },
      { label: "失败数", value: metrics.failedRuns },
      { label: "跳过数", value: metrics.skippedRuns },
    ],
    apiExecutionStats: [
      { label: "通过率", value: metrics.passRate },
      { label: "平均响应时间", value: `${metrics.averageDuration} ms` },
      { label: "最慢执行", value: metrics.slowestInterface },
      { label: "最近执行记录", value: recentReportRuns.value.length ? recentReportRuns.value.map((item) => item.name || `${item.request?.method || ""} ${item.request?.url || ""}`).slice(0, 3).join("；") : "暂无" },
    ],
    coverageAnalysis: [
      { label: "接口覆盖率", value: metrics.interfaceCoverage, note: `已覆盖 ${coverageReport.value?.coverage?.interface?.covered || 0}/${coverageReport.value?.totalCases || 0}` },
      { label: "需求覆盖率", value: metrics.requirementCoverage, note: `已覆盖 ${coverageReport.value?.coverage?.requirement?.covered || 0}/${coverageReport.value?.totalCases || 0}` },
      { label: "异常场景覆盖率", value: metrics.exceptionCoverage, note: `已覆盖 ${coverageReport.value?.coverage?.exception?.covered || 0}/${coverageReport.value?.totalCases || 0}` },
      ...((coverageReport.value?.uncoveredDetails || []).slice(0, 3).map((item) => ({ label: `未覆盖：${item.label}`, value: item.reason, note: item.suggestion }))),
    ],
    qualityAnalysis: [
      { label: "质量平均分", value: metrics.averageQuality },
      { label: "自动化就绪比例", value: metrics.automationReadyRatio },
      ...((coverageReport.value?.qualitySummary?.topIssues || []).map((item) => ({ label: item.issue, value: `${item.count} 次` }))),
    ],
    failureAnalysis: reportFailureCategoryItems.value.map((item) => ({ label: item.label, value: `${item.value} 次` })),
    defects: defectItems.value.map((item) => ({
      title: item.title,
      status: defectStatusLabel(item.status),
      severity: item.severity,
      occurrences: item.occurrences || 1,
      owner: item.owner || "",
    })),
    slowRuns: reportSlowRunItems.value,
    databaseChecks: [
      { label: "总校验数", value: reportDatabaseSummary.value.total },
      { label: "通过数", value: reportDatabaseSummary.value.passed },
      { label: "失败数", value: reportDatabaseSummary.value.failed },
      ...reportDatabaseSummary.value.recentFailures.map((item) => ({ label: item.name, value: item.message || "数据库校验失败" })),
    ],
    risks: [...(coverageReport.value?.risks || []), ...(coverageReport.value?.recommendations || []).slice(0, 3)],
    conclusion: reportConclusionText.value,
    executionDetails: allRunRecords.value.map((item) => ({
      result: item.passed ? "PASS" : "FAIL",
      name: item.name || `${item.request?.method || ""} ${item.request?.url || ""}`,
      method: item.request?.method || "-",
      url: item.request?.url || "-",
      statusCode: item.response?.statusCode ?? "-",
      durationMs: item.response?.durationMs ?? 0,
      createdAt: formatDate(item.createdAt),
    })),
  };
}

function metricLabel(key) {
  const labels = {
    totalRuns: "执行总次数",
    totalCases: "用例总数",
    passedRuns: "通过数",
    failedRuns: "失败数",
    skippedRuns: "跳过数",
    passRate: "通过率",
    interfaceCoverage: "接口覆盖率",
    requirementCoverage: "需求覆盖率",
    exceptionCoverage: "异常场景覆盖率",
    automationReadyRatio: "自动化就绪比例",
    averageQuality: "质量平均分",
    p0Failures: "P0 失败数",
    p1Failures: "P1 失败数",
    defectCount: "缺陷总数",
    unresolvedDefects: "未解决缺陷数",
    averageDuration: "平均响应时间",
    slowestInterface: "最慢执行",
  };
  return labels[key] || key;
}

function renderDefinitionSection(title, items, emptyText = "暂无数据。") {
  return `<section><h2>${escapeHtml(title)}</h2><div class="grid section-grid">${items.length ? items.map((item) => `<article class="card"><h3>${escapeHtml(item.label)}</h3><p>${escapeHtml(String(item.value))}</p>${item.note ? `<p class="muted">${escapeHtml(item.note)}</p>` : ""}</article>`).join("") : `<article class="card"><p>${escapeHtml(emptyText)}</p></article>`}</div></section>`;
}

function renderTableSection(title, headers, rows, emptyText = "暂无数据。") {
  if (!rows.length) {
    return `<section><h2>${escapeHtml(title)}</h2><div class="card"><p>${escapeHtml(emptyText)}</p></div></section>`;
  }
  return `<section><h2>${escapeHtml(title)}</h2><div class="table-wrap"><table><thead><tr>${headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(String(cell ?? "-"))}</td>`).join("")}</tr>`).join("")}</tbody></table></div></section>`;
}

function renderListSection(title, items, emptyText = "暂无数据。") {
  if (!items.length) {
    return `<section><h2>${escapeHtml(title)}</h2><div class="card"><p>${escapeHtml(emptyText)}</p></div></section>`;
  }
  return `<section><h2>${escapeHtml(title)}</h2><div class="card"><ul>${items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul></div></section>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function loadDefectRun(item) {
  const matched = allRunRecords.value.find((run) => run.runId === item.latestRunId);
  if (!matched) {
    showToast("没有找到对应的执行记录。");
    return;
  }
  if (matched.runType === "ui") {
    loadUiRun(matched);
    window.location.hash = "#uiRunnerTitle";
  } else {
    loadApiRun(matched);
    window.location.hash = "#apiRunnerTitle";
  }
}

function createDefaultUserForm() {
  return {
    username: "",
    displayName: "",
    password: "Tester@123456",
    role: "tester",
    isActive: true,
  };
}

function roleLabel(role) {
  const labels = {
    admin: "管理员",
    tester: "测试人员",
  };
  return labels[role] || "测试人员";
}

function createDefaultApiTest() {
  const baseUrl = API_BASE_URL || "http://127.0.0.1:8000";
  return {
    name: "后端健康检查",
    method: "GET",
    url: `${baseUrl}/`,
    headersText: '{\n  "Accept": "application/json"\n}',
    body: "",
    bodyMode: "raw",
    expectedStatus: 200,
    expectedContains: "ok",
    maxResponseMs: 1000,
    timeoutSeconds: 10,
    repeat: 10,
    concurrency: 3,
    variablesText: `{\n  "base_url": "${baseUrl}"\n}`,
    assertionsText: '[\n  {\n    "name": "服务状态为 ok",\n    "source": "json",\n    "path": "$.status",\n    "operator": "equals",\n    "expected": "ok"\n  },\n  {\n    "name": "文档入口存在",\n    "source": "json",\n    "path": "$.docs",\n    "operator": "equals",\n    "expected": "/docs"\n  }\n]',
    extractorsText: '[\n  {\n    "name": "service_name",\n    "source": "json",\n    "path": "$.service"\n  }\n]',
    databaseAssertionsText: "[]",
    jsonSchemaText: '{\n  "type": "object",\n  "required": ["status", "service", "docs"],\n  "properties": {\n    "status": { "type": "string" },\n    "service": { "type": "string" },\n    "docs": { "type": "string" }\n  }\n}',
    suiteStepsText: `[\n  {\n    "name": "后端健康检查",\n    "method": "GET",\n    "url": "{{base_url}}/",\n    "headers": { "Accept": "application/json" },\n    "expectedStatus": 200,\n    "assertions": [\n      { "name": "服务状态为 ok", "source": "json", "path": "$.status", "operator": "equals", "expected": "ok" }\n    ],\n    "extractors": [\n      { "name": "service_name", "source": "json", "path": "$.service" }\n    ]\n  },\n  {\n    "name": "OpenAPI 文档入口检查",\n    "method": "GET",\n    "url": "{{base_url}}/openapi.json",\n    "headers": { "Accept": "application/json" },\n    "expectedStatus": 200,\n    "assertions": [\n      { "name": "openapi 字段存在", "source": "json", "path": "$.openapi", "operator": "exists" }\n    ]\n  }\n]`,
  };
}

function createDefaultUiTest() {
  const baseUrl = "http://127.0.0.1:5173";
  return {
    name: "本地首页可访问检查",
    baseUrl,
    browser: "chromium",
    viewportWidth: 1280,
    viewportHeight: 720,
    captureTrace: true,
    variablesText: `{\n  "web_base_url": "${baseUrl}"\n}`,
    stepsText: '[\n  {\n    "name": "打开测试平台首页",\n    "action": "goto",\n    "url": "{{web_base_url}}/"\n  },\n  {\n    "name": "系统标题可见",\n    "assertion": "textVisible",\n    "locator": "text=测试用例智能生成系统"\n  }\n]',
  };
}

async function analyzeCurrentCoverage(items) {
  if (!items.length) {
    return null;
  }
  try {
    const response = await apiFetch("/api/coverage/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cases: items }),
    });
    if (!response.ok) {
      return null;
    }
    return await response.json();
  } catch {
    return null;
  }
}

function buildUiPayload() {
  const variables = parseJsonText(uiTest.value.variablesText, {}, "UI 变量 JSON");
  const steps = parseJsonText(uiTest.value.stepsText, [], "UI 步骤 JSON");
  if (!Array.isArray(steps) || !steps.length) {
    throw new Error("UI 步骤 JSON 至少需要 1 个步骤。");
  }
  return {
    name: uiTest.value.name.trim() || "Web UI 自动化用例",
    baseUrl: uiTest.value.baseUrl.trim(),
    browser: uiTest.value.browser || "chromium",
    headless: true,
    viewport: {
      width: Number(uiTest.value.viewportWidth) || 1280,
      height: Number(uiTest.value.viewportHeight) || 720,
    },
    variables,
    steps,
    timeoutSeconds: 30,
    stepTimeoutMs: 8000,
    captureTrace: Boolean(uiTest.value.captureTrace),
    captureScreenshot: true,
    continueOnFailure: false,
  };
}

function caseApiConfig(item) {
  const config = item?.api_test || item?.apiTest;
  return config && config.method && config.url ? config : null;
}

function caseUiConfig(item) {
  const config = item?.ui_test || item?.uiTest;
  return config && Array.isArray(config.steps) && config.steps.length ? config : null;
}

function loadGeneratedUiCase(item) {
  const config = caseUiConfig(item);
  if (!config) {
    showToast("这条用例没有可执行 UI 配置。");
    return;
  }
  uiTest.value = {
    ...createDefaultUiTest(),
    name: config.name || item.title || "Web UI 自动化用例",
    baseUrl: config.baseUrl || config.base_url || "",
    browser: config.browser || "chromium",
    viewportWidth: config.viewport?.width || 1280,
    viewportHeight: config.viewport?.height || 720,
    variablesText: JSON.stringify(config.variables || {}, null, 2),
    stepsText: JSON.stringify(config.steps || [], null, 2),
  };
  uiRunResult.value = null;
  window.location.hash = "#uiRunnerTitle";
  showToast("已载入 UI 自动化配置，请确认变量和定位器后执行。");
}

function buildApiPayload() {
  const variables = parseJsonText(apiTest.value.variablesText, {}, "环境变量 JSON");
  const assertions = parseJsonText(apiTest.value.assertionsText, [], "字段断言 JSON");
  const extractors = parseJsonText(apiTest.value.extractorsText, [], "变量提取 JSON");
  const databaseAssertions = parseJsonText(apiTest.value.databaseAssertionsText, [], "数据库校验 JSON");
  const jsonSchema = parseJsonText(apiTest.value.jsonSchemaText, null, "JSON Schema");
  return {
    name: apiTest.value.name.trim(),
    method: apiTest.value.method,
    url: apiTest.value.url.trim(),
    headers: parseHeaders(apiTest.value.headersText),
    body: apiTest.value.body,
    bodyMode: apiTest.value.bodyMode,
    expectedStatus: normalizeExpectedStatus(apiTest.value.expectedStatus),
    expectedContains: apiTest.value.expectedContains.trim(),
    maxResponseMs: normalizeOptionalNumber(apiTest.value.maxResponseMs),
    timeoutSeconds: Number(apiTest.value.timeoutSeconds) || 10,
    variables,
    assertions: ensureArray(assertions, "字段断言 JSON"),
    extractors: ensureArray(extractors, "变量提取 JSON"),
    databaseAssertions: ensureArray(databaseAssertions, "数据库校验 JSON"),
    jsonSchema,
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

function parseJsonText(value, fallback, label) {
  const text = String(value || "").trim();
  if (!text) {
    return fallback;
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`${label} 格式不正确：${error.message}`);
  }
}

function ensureArray(value, label) {
  if (!Array.isArray(value)) {
    throw new Error(`${label} 必须是数组。`);
  }
  return value;
}

function normalizeExpectedStatus(value) {
  if (value === "" || value === null || value === undefined) {
    return null;
  }
  return Number(value);
}

function normalizeOptionalNumber(value) {
  if (value === "" || value === null || value === undefined) {
    return null;
  }
  return Number(value);
}

function runTypeLabel(value) {
  const labels = {
    single: "单接口",
    suite: "用例集",
    load: "并发",
    ui: "UI 自动化",
  };
  return labels[value] || "单接口";
}

function runTargetLabel(item) {
  if (item?.runType === "ui") {
    return `${item.request?.browser || "chromium"} · ${item.request?.url || "页面自动化"}`;
  }
  return `${item?.request?.method || "-"} ${item?.request?.url || "-"}`;
}

function runStatusLabel(item) {
  if (item?.runType === "ui") {
    const steps = item.summary?.executedSteps ?? (item.steps || []).length;
    return `UI 步骤 ${steps}`;
  }
  return `HTTP ${item?.response?.statusCode ?? "-"}`;
}

function passedAssertionCount(result) {
  return (result?.assertions || []).filter((item) => item.passed).length;
}

function stringifyValue(value) {
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value ?? "");
  }
}

async function readErrorMessage(response) {
  const text = await response.text();
  try {
    const data = JSON.parse(text);
    return formatErrorDetail(data.detail) || text || "接口执行请求失败";
  } catch {
    return text || "接口执行请求失败";
  }
}

function formatErrorDetail(detail) {
  if (!detail) {
    return "";
  }
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map(formatErrorDetail).filter(Boolean).join("；");
  }
  if (typeof detail === "object") {
    const message = normalizeValidationMessage(detail.msg || detail.message || detail.detail || "");
    const location = Array.isArray(detail.loc) ? detail.loc.filter((item) => item !== "body").join(".") : "";
    if (message && location) {
      return `${errorFieldLabel(location)}：${message}`;
    }
    if (message) {
      return String(message);
    }
    try {
      return JSON.stringify(detail);
    } catch {
      return String(detail);
    }
  }
  return String(detail);
}

function errorFieldLabel(location) {
  const labels = {
    username: "用户名",
    password: "密码",
    displayName: "显示名称",
    role: "角色",
    isActive: "启用状态",
    oldPassword: "旧密码",
    newPassword: "新密码",
  };
  return labels[location] || location;
}

function normalizeValidationMessage(message) {
  const text = String(message || "");
  const atLeastMatch = text.match(/String should have at least (\d+) characters?/i);
  if (atLeastMatch) {
    return `至少需要 ${atLeastMatch[1]} 位。`;
  }
  const atMostMatch = text.match(/String should have at most (\d+) characters?/i);
  if (atMostMatch) {
    return `最多允许 ${atMostMatch[1]} 位。`;
  }
  const missingMatch = text.match(/Field required/i);
  if (missingMatch) {
    return "不能为空。";
  }
  return text;
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

async function apiFetch(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    credentials: "include",
    headers: {
      ...(options.headers || {}),
    },
  });
  if (response.status === 401 && !String(path).startsWith("/api/auth/")) {
    currentUser.value = null;
    showToast("登录状态已失效，请重新登录。");
  }
  return response;
}
</script>

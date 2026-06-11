# 测试用例智能生成系统

一个前后端分离的 AI 测试用例生成系统。用户可以上传思维导图、流程图、界面截图、Excel、Word、PDF、Markdown、JSON、文本材料，也可以补充飞书文档/知识库/PRD 链接、用户要求和业务上下文。系统通过多模态大模型或本地演示生成器流式生成结构化测试用例，并自动保存为 Excel 文件供下载；同时支持接口测试执行、接口用例集串联、增强断言、数据库校验、并发执行和执行历史保存。

## 当前架构

```text
frontend/                  Vue 3 + Vite 前端，默认运行在 127.0.0.1:5173
app/                       FastAPI 后端 API，默认运行在 127.0.0.1:8000
generated/                 运行时生成的 Excel 文件
docs/                      配置与输入材料说明
scripts/                   Windows 启动和端口释放脚本
```

前端和后端已经分离：

- 前端页面由 `frontend/` 中的 Vue 应用实现。
- 后端只提供 API、流式生成和 Excel 下载，不再托管静态页面。
- 开发环境下，Vite 会把 `/api` 请求代理到 `http://127.0.0.1:8000`。

## 文档入口

- 产品汇报版文档：[`docs/PRODUCT_REPORT.md`](docs/PRODUCT_REPORT.md)
- 多源材料输入说明：[`docs/MATERIAL_INPUTS.md`](docs/MATERIAL_INPUTS.md)
- 模型接入配置说明：[`docs/MODEL_SETUP.md`](docs/MODEL_SETUP.md)
- MySQL 配置说明：[`docs/MYSQL_SETUP.md`](docs/MYSQL_SETUP.md)
- 接口测试执行说明：[`docs/API_TEST_EXECUTION.md`](docs/API_TEST_EXECUTION.md)

> 维护约定：每次系统版本更新、功能迭代或能力下线后，必须同步更新 `docs/PRODUCT_REPORT.md`。

## 功能

- 科技风 Vue 前端界面，包含左侧导航栏、工作台、用例生成、Swagger 导入、接口执行、报告中心、缺陷跟踪和历史记录
- 多源材料上传与预览
- 支持图片、Excel、CSV、Word、PDF、Markdown、JSON、YAML、文本文件、飞书/网页链接
- 需求、上下文背景、外部文档链接输入
- 自动识别链接类型，并提示飞书、Swagger UI、OpenAPI JSON 等不同导入建议
- SSE 流式输出生成过程与测试用例
- 生成过程解析动态展示
- 测试用例卡片视图、表格视图、搜索过滤
- 每条用例展示执行就绪状态、不可执行原因、需求追溯和质量扣分原因
- 自动保存 Excel 并提供下载
- 支持 MySQL 保存生成历史和用例明细
- 支持报告中心汇总最近执行结果、通过率和覆盖风险
- 支持报告中心导出 Markdown 报告
- 支持缺陷跟踪模块管理失败项、自动合并重复失败、查看失败证据与最近执行
- 支持接口测试用例执行：方法、URL、Headers、Body、Form、Multipart、状态码断言、响应内容断言和超时控制
- 支持增强断言：JSONPath、Header、Body、状态码、响应时间、类型、正则、存在性、大小比较和 JSON Schema
- 支持环境变量、`{{variable}}` 变量替换、响应提取和多接口串联
- 支持 MySQL 只读 SELECT 校验，用于验证接口执行后的数据落库和数据一致性
- 支持接口用例集批量顺序执行、失败中断、并发执行和基础性能指标
- 支持 MySQL 保存接口测试执行历史、响应摘要、断言结果、变量提取结果和耗时
- 支持 AI 生成用例携带可执行接口配置，并在用例卡片上一键执行
- 支持 OpenAPI / Swagger JSON/YAML 导入，自动生成正向、缺参、非法参数、边界、权限和幂等用例
- 支持覆盖率矩阵：需求、接口、字段、异常、权限、边界、数据一致性、性能、安全
- 支持用例质量评分：步骤可执行性、预期可验证性、测试数据、覆盖标签、自动化就绪和重复度
- 支持接口失败分析 Agent，自动归类环境、鉴权、参数、断言、契约变更、后端缺陷和数据库一致性问题
- 支持失败分析证据链、置信度、是否建议创建缺陷和是否建议更新用例
- 支持请求/响应敏感 Header 脱敏，并支持按环境变量启用更严格的内网访问限制
- 支持 OpenAI-compatible 多模态接口
- 未配置模型 Key 时提供本地演示生成器，便于验证完整流程

## 后端启动

第一次运行先安装 Python 依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

启动 FastAPI 后端：

```powershell
.\scripts\start.cmd
```

后端地址：

```text
http://127.0.0.1:8000
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

如果 8000 端口被旧进程占用：

```powershell
.\scripts\stop.cmd -Port 8000
```

换端口启动：

```powershell
.\scripts\start.cmd -Port 8001
```

开发时启用后端自动重载：

```powershell
.\scripts\start.cmd -Reload
```

## 前端启动

进入前端目录安装依赖：

```powershell
cd frontend
npm.cmd install
```

也可以直接在项目根目录运行前端启动脚本，脚本会在缺少 `node_modules` 时自动执行 `npm install`：

```powershell
.\scripts\start-frontend.cmd
```

前端页面地址：

```text
http://127.0.0.1:5173
```

如果 5173 端口被旧进程占用：

```powershell
.\scripts\stop-frontend.cmd -Port 5173
```

换端口启动：

```powershell
.\scripts\start-frontend.cmd -Port 5174
```

如果后端不是运行在 `127.0.0.1:8000`，可以在 `frontend/.env` 中指定：

```text
VITE_API_BASE_URL=http://127.0.0.1:8001
```

## 推荐运行顺序

```powershell
.\scripts\start.cmd
```

另开一个 PowerShell 窗口：

```powershell
.\scripts\start-frontend.cmd
```

然后打开：

```text
http://127.0.0.1:5173
```

## Docker Compose 演示启动

本地开发仍推荐使用上面的固定启动流程。若你已经安装 Docker Desktop，也可以用 Compose 一键启动前端、后端和 MySQL：

```powershell
docker compose up --build
```

启动后访问：

```text
前端：http://127.0.0.1:5173
后端：http://127.0.0.1:8000
```

演示材料：

```text
docs/demo/openapi.json
docs/demo/prd.md
```

在前端“OpenAPI / Swagger 导入”面板粘贴 `docs/demo/openapi.json` 内容，可以生成可执行接口用例和覆盖率报告。

## 模型配置

默认会读取以下环境变量：

```powershell
$env:OPENAI_API_KEY="你的 API Key"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="gpt-4o-mini"
```

也可以把 `OPENAI_BASE_URL` 指向任意兼容 Chat Completions 的多模态服务。

详细配置步骤见：[docs/MODEL_SETUP.md](docs/MODEL_SETUP.md)

## MySQL 历史记录

系统支持将生成会话、输入摘要、材料摘要、测试用例明细和 Excel 下载地址保存到 MySQL。

配置入口在 `.env`：

```text
DATABASE_ENABLED=true
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=ai_test_user
MYSQL_PASSWORD=your-mysql-password
MYSQL_DATABASE=ai_testcase
MYSQL_CHARSET=utf8mb4
```

后端启动时会自动创建表。连接状态可以访问：

```text
http://127.0.0.1:8000/api/database/status
```

详细配置步骤见：[docs/MYSQL_SETUP.md](docs/MYSQL_SETUP.md)

## 接口测试执行

前端“接口执行”面板提供一个默认的本地健康检查用例：

```text
GET http://127.0.0.1:8000/api/database/status
```

你可以修改以下字段执行自己的接口测试：

- 方法：GET / POST / PUT / PATCH / DELETE / HEAD / OPTIONS
- 接口地址：完整的 `http://` 或 `https://` URL
- Headers JSON：例如 `{ "Authorization": "Bearer token" }`
- Body：POST、PUT、PATCH 等请求体，支持 raw / json / form / multipart
- 期望状态码：例如 `200`
- 响应包含：用于检查响应体里是否包含指定文本
- 最大耗时：用于响应时间断言
- 超时秒数：1-30 秒
- 环境变量 JSON：支持 `{{base_url}}`、`{{token}}` 这样的变量替换
- 字段断言 JSON：支持 JSONPath、Header、Body、状态码、响应时间等断言
- 变量提取 JSON：支持从响应 JSON、Header、Body 正则提取变量给后续步骤使用
- 数据库校验 JSON：只允许 SELECT，用于执行接口后校验 MySQL 数据
- JSON Schema：用于校验响应结构
- 用例集步骤 JSON：用于多接口串联和批量执行

后端接口：

```text
POST /api/api-tests/run
POST /api/api-tests/suite
POST /api/api-tests/load
POST /api/cases/execute
GET  /api/api-tests/history?limit=20
POST /api/openapi/import
POST /api/coverage/analyze
```

执行结果会返回通过状态、实际状态码、耗时、响应预览、断言明细、变量提取结果、数据库校验结果和并发指标；如果 MySQL 已启用，会自动写入 `api_test_runs` 表。

详细配置示例见：[docs/API_TEST_EXECUTION.md](docs/API_TEST_EXECUTION.md)

## 输入材料

系统现在支持多种输入来源：

```text
图片：PNG / JPG / WebP / GIF / BMP / SVG
表格：XLSX / XLSM / XLS / CSV / TSV
文档：DOCX / PDF
文本：TXT / MD / JSON / YAML / LOG / FEATURE / HTML
链接：飞书文档、知识库、PRD、接口文档或其他网页链接
```

私有飞书文档通常需要登录授权，系统不会直接读取你的飞书账号内容。推荐同时上传导出的 Word/PDF/Excel，或把关键内容粘贴到“上下文背景”中。

详细说明见：[docs/MATERIAL_INPUTS.md](docs/MATERIAL_INPUTS.md)

## 构建前端

```powershell
cd frontend
npm.cmd run build
```

构建产物位于：

```text
frontend/dist/
```

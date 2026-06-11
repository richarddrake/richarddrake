# AGENTS.md

本文件是测试用例智能生成系统项目的长期协作规则。后续任何 Codex / Agent 会话在修改本项目之前，都应先阅读并遵守本文件。

## 项目基本信息

- 项目名称：测试用例智能生成系统
- 本地项目路径：`D:\AI_code\AI_Test`
- GitHub 仓库：`https://github.com/richarddrake/richarddrake.git`
- 默认分支：`main`
- 技术形态：前后端分离
- 前端：`frontend/`，Vue 3 + Vite
- 后端：`app/`，FastAPI
- 数据库：MySQL，可选启用

## 每次开始前必须阅读

开始任何优化、修复、重构或功能新增之前，必须先阅读：

1. `README.md`
2. `docs/PRODUCT_REPORT.md`

如果任务涉及某个专项能力，也应阅读对应文档，例如：

- `docs/MATERIAL_INPUTS.md`
- `docs/MODEL_SETUP.md`
- `docs/MYSQL_SETUP.md`
- `docs/API_TEST_EXECUTION.md`

## 默认任务规则

后续任务默认都是围绕“测试用例智能生成系统”的完善和优化。

每次新任务只聚焦一个明确模块，例如：

- 用例生成
- Swagger 导入
- 接口执行
- 报告中心
- 缺陷跟踪
- 历史记录
- 数据库能力
- 前端界面
- 部署配置
- 文档整理

除非用户明确要求，不要把多个大模块混在一次改动里。

## 启动流程约束

不要改变当前既有启动流程。

后端启动方式保持为：

```powershell
.\scripts\start.cmd
```

前端启动方式保持为：

```powershell
.\scripts\start-frontend.cmd
```

默认地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

如果需要优化启动脚本，必须保证旧命令仍然可用。

## 每次修改完成后的必要动作

每次增加新功能、修复 bug、调整旧功能或更新文档后，必须完成：

1. 更新本地代码
2. 运行必要验证
3. 更新相关文档
4. 提交并推送到 GitHub `main` 分支

常用验证命令：

```powershell
cd D:\AI_code\AI_Test\frontend
npm.cmd run build
```

```powershell
cd D:\AI_code\AI_Test
python -m compileall app
```

Git 提交和推送应在项目根目录执行。

如 GitHub 推送遇到网络或 TLS 问题，可优先使用本机代理：

```powershell
$env:https_proxy='http://127.0.0.1:7897'
$env:http_proxy='http://127.0.0.1:7897'
git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin main
```

## 文档维护规则

每次功能变化后，至少检查是否需要更新：

1. `README.md`
2. `docs/PRODUCT_REPORT.md`

如果新增了专项能力，应新增或更新 `docs/` 下的专题说明。

文档要写成人能看懂的产品说明，不要使用过度 AI 化或生硬翻译的表达。

推荐使用“测试资源”而不是“测试资产沉淀”这类不自然表述。

## 当前产品定位

本项目不是单纯的测试用例生成工具，而是一套初版 AI 测试平台。

当前主链路是：

1. 多源材料输入
2. AI 测试用例生成
3. 用例质量与覆盖率分析
4. Swagger / OpenAPI 导入
5. 接口测试执行
6. 失败分析
7. 报告中心
8. 缺陷跟踪
9. 历史记录与 MySQL 保存
10. Excel / Markdown / HTML 报告导出

## 前端设计原则

- 保持当前科技风界面，不要随意改成普通后台模板
- 左侧导航顺序应贴近测试流程
- 不要重新加入已经删除的独立“Excel 导出”导航
- 不要重新加入 `MODEL LINK`、`Coverage`、`Mode` 这类突兀侧栏块
- `用例生成`、`接口执行`、`报告中心`、`缺陷跟踪` 是当前重点模块
- UI 调整必须兼顾桌面和移动端，不允许文字明显溢出或重叠

## 后端设计原则

- 后端继续基于 FastAPI
- 保持 API 结构清晰，优先复用 `app/services/` 中已有服务模块
- 接口执行器要注意安全边界、超时控制、敏感信息脱敏
- 数据库校验默认只允许 MySQL 只读 SELECT
- 不要为了单个功能引入过重的新框架

## 新会话推荐指令

后续开启新会话时，可以这样告诉 Codex：

```text
这是测试用例智能生成系统项目，项目路径是 D:\AI_code\AI_Test。

请先阅读 AGENTS.md、README.md 和 docs/PRODUCT_REPORT.md，了解当前系统能力和项目规则。
本次只优化【模块名称】，不要改变既有启动流程。
修改完成后需要：
1. 更新本地代码
2. 运行必要验证
3. 更新相关文档
4. 提交并推送到 GitHub main 分支
```

如果本次只想咨询、不想改代码，应明确说明：

```text
本次只讨论方案，不要修改代码。
```

## 工作方式偏好

- 优先做小而完整的模块化迭代
- 每次改动要能解释清楚用户价值
- 不要为了炫技做大规模重构
- 不要破坏当前已可用功能
- 不要回滚用户已有改动
- 遇到可验证的问题，优先用命令或本地服务验证


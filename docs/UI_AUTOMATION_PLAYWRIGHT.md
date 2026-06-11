# Playwright UI 自动化说明

本文档说明系统当前如何接入 Playwright 执行 Web UI 自动化测试。

## 当前定位

UI 自动化是平台在接口执行之后新增的页面级执行能力。当前版本优先保证最小闭环稳定：

1. 在前端填写页面基础地址、变量和步骤 JSON
2. 后端使用 Playwright 执行受控步骤
3. 返回步骤结果、页面断言、失败截图和 trace
4. 结果进入报告中心、缺陷跟踪和 UI 执行历史

当前不会执行用户粘贴的任意 JavaScript / TypeScript 脚本，只执行平台定义的动作和断言。

## 安装要求

安装 Python 依赖：

```powershell
pip install -r requirements.txt
```

安装 Chromium 浏览器运行时：

```powershell
python -m playwright install chromium
```

如果需要 Firefox 或 WebKit，可按需执行：

```powershell
python -m playwright install firefox webkit
```

项目启动流程不变：

```powershell
.\scripts\start.cmd
```

```powershell
.\scripts\start-frontend.cmd
```

## 后端接口

```text
POST /api/ui-tests/run
GET  /api/ui-tests/history?limit=20
GET  /api/ui-tests/artifacts/{run_id}/{filename}
```

`/api/ui-tests/run` 请求示例：

```json
{
  "name": "本地首页可访问检查",
  "baseUrl": "http://127.0.0.1:5173",
  "browser": "chromium",
  "headless": true,
  "viewport": { "width": 1280, "height": 720 },
  "variables": {
    "web_base_url": "http://127.0.0.1:5173"
  },
  "steps": [
    {
      "name": "打开测试平台首页",
      "action": "goto",
      "url": "{{web_base_url}}/"
    },
    {
      "name": "系统标题可见",
      "assertion": "textVisible",
      "locator": "text=测试用例智能生成系统"
    }
  ],
  "captureTrace": true,
  "captureScreenshot": true
}
```

## 支持的动作

| action | 说明 | 必填字段 |
| --- | --- | --- |
| `goto` | 打开页面 | `url` |
| `click` | 点击元素 | `locator` |
| `fill` | 清空并填写输入框 | `locator`, `value` |
| `type` | 模拟键盘输入 | `locator`, `value` |
| `press` | 按键 | `locator`, `key` |
| `select` | 选择下拉选项 | `locator`, `value` |
| `check` | 勾选复选框或单选框 | `locator` |
| `uncheck` | 取消勾选 | `locator` |
| `waitForSelector` | 等待元素状态 | `locator`, `state` |
| `wait` / `waitForTimeout` | 固定等待 | `ms` |
| `screenshot` | 页面截图 | 可选 |

## 支持的断言

| assertion | 说明 | 常用字段 |
| --- | --- | --- |
| `visible` | 元素可见 | `locator` |
| `hidden` | 元素隐藏 | `locator` |
| `textVisible` | 文本或元素可见 | `locator` |
| `urlContains` | 当前 URL 包含指定内容 | `expected` |
| `urlEquals` | 当前 URL 完全等于指定内容 | `expected` |
| `titleContains` | 页面标题包含指定内容 | `expected` |
| `textContains` | 元素文本包含指定内容 | `locator`, `expected` |

## Locator 写法

推荐优先使用稳定定位器：

```text
role=button[name=登录]
getByLabel:用户名
getByPlaceholder:请输入密码
text=保存成功
testId=submit-button
css=.submit-button
xpath=//button[contains(., "提交")]
```

建议优先级：

1. `role`
2. `label`
3. `placeholder`
4. `text`
5. `testId`
6. CSS / XPath

如果 AI 无法从材料中确认稳定定位器，应把用例标记为待补齐，不应臆造复杂 CSS 层级。

## 执行结果

执行结果包含：

- `passed`：整体是否通过
- `steps`：每一步动作或断言的执行状态
- `assertions`：页面断言统计
- `consoleMessages`：最近控制台消息
- `networkErrors`：页面执行期间的网络失败摘要
- `artifacts.screenshot`：失败截图
- `artifacts.trace`：Playwright trace
- `failureAnalysis`：失败分类、证据和建议动作

如果 MySQL 已启用，系统会保存到 `ui_test_runs` 表。报告中心会合并接口执行和 UI 执行结果，缺陷跟踪会自动同步失败的 UI 执行记录。

## 安全边界

当前版本默认约束：

- 只允许 `http` / `https` 页面
- 不执行任意用户脚本
- 单次最多 30 个步骤
- 单步默认超时 8 秒，最大 30 秒
- 总超时最大 120 秒
- 默认 headless 执行
- 失败截图和 trace 会保存在 `generated/ui-runs/`

可选环境变量：

```text
UI_RUNNER_ALLOWED_HOSTS=example.com,test.example.com
UI_RUNNER_BLOCK_PRIVATE_NETWORK=true
UI_RUNNER_ALLOW_LOCALHOST=true
```

如果配置了 `UI_RUNNER_ALLOWED_HOSTS`，只允许访问其中列出的域名。

## 当前边界

当前 UI 自动化仍是基础版：

- 尚未提供可视化步骤编排器
- 尚未提供 Playwright codegen 导入
- 尚未提供 Page Object 代码生成
- 尚未提供 CI 用例包导出
- 验证码、短信、人脸识别等强人工环节仍需要测试环境旁路或人工处理

推荐先用于登录、搜索、表单提交、页面跳转、状态提示、权限可见性等稳定页面流程。

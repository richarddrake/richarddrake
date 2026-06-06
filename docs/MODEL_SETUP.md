# 真实多模态大模型接入配置指南

这份文档说明如何把系统从“本地演示生成器”切换到“真实多模态大模型”。配置完成后，用户上传思维导图、流程图、界面截图、Excel、Word、PDF、文本材料或飞书文档链接时，后端会把图片、可解析文件文本、用户要求、上下文背景一起发送给模型，并通过流式输出返回测试用例。

## 1. 当前系统如何调用模型

后端代码位置：

```text
app/services/generator.py
```

系统会读取这些环境变量：

```text
OPENAI_API_KEY
OPENAI_BASE_URL
OPENAI_MODEL
LLM_TIMEOUT_SECONDS
LLM_MAX_TOKENS
```

如果 `OPENAI_API_KEY` 没有配置，系统会自动使用本地演示生成器。

如果 `OPENAI_API_KEY` 已配置，系统会调用：

```text
POST {OPENAI_BASE_URL}/chat/completions
```

也就是说，如果你使用官方 OpenAI 地址，`OPENAI_BASE_URL` 应该是：

```text
https://api.openai.com/v1
```

最终请求地址会是：

```text
https://api.openai.com/v1/chat/completions
```

## 2. 准备 API Key

你需要准备一个可用的模型 API Key。

可以使用：

- OpenAI 官方 API Key
- 其他兼容 OpenAI Chat Completions 接口的多模态模型服务

模型必须满足这些条件：

- 支持图片输入
- 支持 `chat/completions`
- 支持 `stream: true`
- 返回格式兼容 OpenAI Chat Completions streaming

非图片文件会先由后端抽取文本，再作为提示词上下文发送给模型。

## 3. 创建 `.env` 配置文件

项目根目录已经提供了一个示例文件：

```text
.env.example
```

在 PowerShell 中进入项目目录：

```powershell
cd C:\Users\Administrator\Documents\AI_Test
```

复制一份配置文件：

```powershell
Copy-Item .env.example .env
```

打开 `.env`：

```powershell
notepad .env
```

把内容改成你的真实配置。

## 4. 使用 OpenAI 官方接口

如果你使用 OpenAI 官方接口，`.env` 可以这样写：

```env
OPENAI_API_KEY=sk-你的真实APIKey
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
LLM_TIMEOUT_SECONDS=120
LLM_MAX_TOKENS=5000
```

注意：

- `OPENAI_API_KEY` 不要加引号。
- `OPENAI_BASE_URL` 末尾可以不加 `/`。
- `OPENAI_MODEL` 要填写支持图片输入的模型。
- 如果模型输出被截断，可以适当调大 `LLM_MAX_TOKENS`。

## 5. 使用第三方 OpenAI-compatible 服务

如果你使用的是兼容 OpenAI 接口的服务，配置方式类似：

```env
OPENAI_API_KEY=你的服务商APIKey
OPENAI_BASE_URL=https://你的服务商域名/v1
OPENAI_MODEL=你的多模态模型名称
LLM_TIMEOUT_SECONDS=120
LLM_MAX_TOKENS=5000
```

重点检查：

- `OPENAI_BASE_URL` 通常需要包含 `/v1`。
- `OPENAI_MODEL` 必须和服务商控制台里的模型名称完全一致。
- 服务商必须支持图片输入。这个系统会把上传图片转成 `image_url` 的 data URL 传给模型。

## 6. 如果需要代理

如果你的电脑访问模型服务需要代理，可以在启动服务前设置代理环境变量。

例如你的系统代理是 `127.0.0.1:7897`：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7897"
$env:HTTPS_PROXY="http://127.0.0.1:7897"
```

然后再启动服务。

如果不需要代理，可以跳过这一步。

## 7. 启动服务

安装依赖：

```powershell
pip install -r requirements.txt
```

启动后端：

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开页面：

```text
http://127.0.0.1:8000
```

修改 `.env` 后需要重启 `uvicorn`，新配置才会生效。

## 8. 验证是否已经调用真实模型

打开页面后：

1. 上传一张思维导图、流程图或界面截图。
2. 填写“用户要求”。
3. 填写“上下文背景”。
4. 点击“生成用例”。

如果配置正确，页面会开始流式输出模型分析过程和测试用例。

如果配置错误，页面可能会看到类似提示：

```text
模型调用暂不可用，已切换本地生成器
```

这说明系统没有成功调用真实模型，已经自动回退到了演示生成器。

## 9. 常见问题

### 页面仍然使用演示生成器

检查：

- `.env` 文件是否在项目根目录。
- `.env` 文件名是不是 `.env`，不是 `.env.txt`。
- `OPENAI_API_KEY` 是否填写。
- 修改 `.env` 后是否重启了 `uvicorn`。
- 当前启动服务的目录是否是 `C:\Users\Administrator\Documents\AI_Test`。

### 401 或 403

通常是 API Key 无效、权限不足或账户没有对应模型权限。

处理方式：

- 重新复制 API Key。
- 确认 Key 没有多余空格。
- 确认账户有当前模型的调用权限。

### 404

通常是 `OPENAI_BASE_URL` 或 `OPENAI_MODEL` 写错。

检查：

- `OPENAI_BASE_URL` 是否应该包含 `/v1`。
- `OPENAI_MODEL` 是否和服务商模型名称一致。

### 请求超时

可能是网络、代理或模型响应较慢。

可以尝试：

```env
LLM_TIMEOUT_SECONDS=180
```

如果你需要代理，确认先设置了：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7897"
$env:HTTPS_PROXY="http://127.0.0.1:7897"
```

### 模型返回了内容，但页面没有出现用例

这个系统要求模型按 NDJSON 格式逐行返回。

后端提示词已经强制要求模型输出类似：

```json
{"event":"thought","text":"识别到核心流程包含创建、提交、审批和结果通知。"}
{"event":"case","id":"TC-001","module":"提交流程","title":"必填信息完整时提交成功","priority":"P0","case_type":"功能","scenario":"覆盖主流程提交","preconditions":["用户已登录","进入提交页面"],"steps":["填写所有必填项","点击提交"],"expected_results":["提交成功","生成记录编号"],"test_data":"有效表单数据","tags":["主流程","正向"],"source":"界面截图和用户要求"}
```

如果某个模型经常不遵守格式，可以考虑换一个更擅长结构化输出的模型。

## 10. 安全提醒

`.env` 已经被 `.gitignore` 忽略，不会被提交到 GitHub。

不要把真实 API Key 写进：

- README
- 前端 JS
- GitHub Issue
- 截图
- 聊天窗口

真实 API Key 只应该保存在本机 `.env` 或服务器环境变量中。

## 11. 推荐配置流程

最简单的一次性流程如下：

```powershell
cd C:\Users\Administrator\Documents\AI_Test
Copy-Item .env.example .env
notepad .env
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

然后打开：

```text
http://127.0.0.1:8000
```

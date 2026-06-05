# 测试用例智能生成系统

一个基于 FastAPI 的轻量全栈应用：用户上传思维导图、流程图或界面截图，并填写需求与上下文信息，系统通过多模态大模型生成结构化测试用例，前端流式展示，并自动保存为 Excel 文件供下载。

## 功能

- 多图片上传与预览
- 需求、上下文背景输入
- SSE 流式输出生成过程与测试用例
- 测试用例卡片视图、表格视图、搜索过滤
- 自动保存 Excel 并提供下载
- 支持 OpenAI-compatible 多模态接口
- 未配置模型 Key 时提供本地演示生成器，便于验证完整流程

## 启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

## 模型配置

默认会读取以下环境变量：

```powershell
$env:OPENAI_API_KEY="你的 API Key"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="gpt-4o-mini"
```

也可以把 `OPENAI_BASE_URL` 指向任意兼容 Chat Completions 的多模态服务。

## 目录

```text
app/
  main.py                    FastAPI 入口
  schemas.py                 数据结构与规范化逻辑
  services/
    generator.py             LLM 生成器与本地演示生成器
    excel_exporter.py        Excel 导出
static/
  index.html                 前端页面
  styles.css                 页面样式
  app.js                     上传、流式读取与渲染逻辑
generated/                   运行时生成的 Excel 文件
```

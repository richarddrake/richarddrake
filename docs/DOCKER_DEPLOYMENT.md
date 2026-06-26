# Docker Compose 部署说明

> 最近更新：2026-06-26  
> 文档用途：说明如何使用 Docker / Docker Compose 一键启动测试用例智能生成系统。

## 1. 能力说明

当前项目已经支持通过 Docker Compose 启动完整演示环境，包括：

- `frontend`：Vue 3 前端，经 Nginx 托管，对外端口默认 `5173`。
- `backend`：FastAPI 后端，对外端口默认 `8000`。
- `mysql`：MySQL 8 数据库，宿主机端口默认 `3307`，容器内部端口 `3306`。

前端容器会把 `/api`、`/docs` 和 `/openapi.json` 代理到后端容器，因此浏览器访问前端地址即可完成页面操作和后端 API 调用。

## 2. 前置条件

需要先安装并启动 Docker Desktop，然后在项目根目录执行命令：

```powershell
docker --version
docker compose version
```

如果能正常输出版本号，说明 Docker CLI 和 Compose 可用。

## 3. 一键启动

在项目根目录执行：

```powershell
.\scripts\docker-start.cmd
```

或者直接执行：

```powershell
docker compose up --build
```

启动后访问：

```text
前端：http://127.0.0.1:5173
后端：http://127.0.0.1:8000
后端文档：http://127.0.0.1:8000/docs
MySQL：127.0.0.1:3307
```

## 4. 后台启动和停止

后台启动：

```powershell
.\scripts\docker-start.cmd -Detached
```

停止容器：

```powershell
.\scripts\docker-stop.cmd
```

停止并删除 MySQL 数据卷：

```powershell
.\scripts\docker-stop.cmd -Volumes
```

删除数据卷会清空 Docker 环境里的 MySQL 数据，适合重新初始化演示环境。

## 5. 环境变量

默认情况下不需要额外配置环境变量，Compose 会使用内置默认值启动。

如果需要修改端口、数据库账号或模型配置，可以复制模板：

```powershell
Copy-Item .env.docker.example .env.docker
```

然后编辑 `.env.docker`，再使用脚本启动：

```powershell
.\scripts\docker-start.cmd
```

常用变量：

```text
DOCKER_FRONTEND_PORT=5173
DOCKER_BACKEND_PORT=8000
DOCKER_MYSQL_PORT=3307
DOCKER_MYSQL_DATABASE=ai_testcase
DOCKER_MYSQL_USER=ai_test_user
DOCKER_MYSQL_PASSWORD=ai_test_password
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

如果 `OPENAI_API_KEY` 留空，系统仍可使用本地演示生成器验证完整流程。

## 6. 查看日志

查看全部服务日志：

```powershell
docker compose logs -f
```

只查看后端日志：

```powershell
docker compose logs -f backend
```

只查看前端日志：

```powershell
docker compose logs -f frontend
```

只查看 MySQL 日志：

```powershell
docker compose logs -f mysql
```

## 7. 验证方式

容器启动后可以按以下顺序验证：

1. 打开 `http://127.0.0.1:5173`，确认前端页面能访问。
2. 打开 `http://127.0.0.1:8000/docs`，确认 FastAPI 文档能访问。
3. 打开 `http://127.0.0.1:8000/api/database/status`，确认返回 MySQL 已启用且连接正常。
4. 在前端 Swagger 导入面板粘贴 `docs/demo/openapi.json`，确认可以生成接口用例。
5. 在接口执行面板运行数据库状态检查用例，确认接口执行和断言结果正常。

## 8. 端口冲突处理

如果本机端口被占用，可以在 `.env.docker` 中修改：

```text
DOCKER_FRONTEND_PORT=5174
DOCKER_BACKEND_PORT=8001
DOCKER_MYSQL_PORT=3308
```

修改后重新执行：

```powershell
.\scripts\docker-start.cmd
```

## 9. 与本地启动流程的关系

Docker 启动流程是新增的部署方式，不替代原有本地开发流程。

原有命令保持不变：

```powershell
.\scripts\start.cmd
.\scripts\start-frontend.cmd
```

Docker 方式更适合演示、交付和快速搭建可复现测试环境；本地方式更适合日常开发和调试。

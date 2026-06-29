# GitHub Actions CD 部署说明

> 最近更新：2026-06-30
> 文档用途：说明如何把 GitHub Actions 从“构建并发布镜像”扩展为“发布镜像后自动部署到服务器”。

## 1. 当前 CD 能力

当前工作流位于 `.github/workflows/ci.yml`，代码推送到 `main` 后会执行以下流程：

1. 后端 Python 编译检查。
2. 前端 Vue 构建检查。
3. Docker Compose 配置校验。
4. 构建前后端 Docker 镜像。
5. 发布镜像到 GitHub Container Registry。
6. 如果已配置服务器 SSH secrets，自动登录服务器，拉取最新镜像并执行 `docker compose up -d`。

PR 场景只做检查，不会发布镜像，也不会部署服务器。

## 2. 镜像产物

`main` 分支 push 后会生成以下镜像：

```text
ghcr.io/<owner>/<repo>-backend:latest
ghcr.io/<owner>/<repo>-backend:sha-xxxxxxx
ghcr.io/<owner>/<repo>-frontend:latest
ghcr.io/<owner>/<repo>-frontend:sha-xxxxxxx
```

部署时默认使用本次提交对应的 `sha-xxxxxxx` 标签，避免服务器误拉到其他提交的 `latest`。

## 3. 服务器前置条件

服务器建议使用 Linux，并提前准备：

- Docker Engine。
- Docker Compose v2。
- 一个可以 SSH 登录并执行 Docker 命令的用户。
- 服务器防火墙放行前端端口，默认是 `80`。

如果 Docker 需要 sudo，请优先把部署用户加入 `docker` 用户组，否则 GitHub Actions 的非交互式部署会失败。

## 4. GitHub Secrets

进入 GitHub 仓库：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

至少配置以下三个：

```text
DEPLOY_HOST=服务器 IP 或域名
DEPLOY_USER=SSH 用户名
DEPLOY_SSH_KEY=SSH 私钥内容
```

可选配置：

```text
DEPLOY_PORT=22
DEPLOY_PATH=ai-testcase-platform
DEPLOY_ENV_FILE=.env.production.example 修改后的完整内容
GHCR_USERNAME=GitHub 用户名
GHCR_TOKEN=有 read:packages 权限的 GitHub Token
```

如果 GHCR 镜像是私有的，服务器拉取镜像时需要 `GHCR_USERNAME` 和 `GHCR_TOKEN`。如果镜像已设为公开，或者服务器已经手动 `docker login ghcr.io`，这两个 secret 可以不配。

## 5. 生产环境变量

仓库提供了 `.env.production.example`。建议复制其中内容，修改数据库密码、管理员密码、`AUTH_SECRET_KEY` 和模型配置后，整体保存为 GitHub secret：

```text
DEPLOY_ENV_FILE
```

部署时 Actions 会把该 secret 写入服务器部署目录的 `.env` 文件，供 `docker-compose.prod.yml` 读取。

最重要的变量：

```text
DOCKER_FRONTEND_PORT=80
DOCKER_BACKEND_PORT=8000
DOCKER_MYSQL_PASSWORD=change-this-db-password
AUTH_SECRET_KEY=change-this-to-a-long-random-production-secret
APP_ADMIN_USERNAME=admin
APP_ADMIN_PASSWORD=change-this-admin-password
OPENAI_API_KEY=
```

## 6. 服务器部署目录

默认部署目录是 SSH 用户家目录下的：

```text
ai-testcase-platform
```

如果配置了 `DEPLOY_PATH`，则使用你指定的目录。Actions 会上传：

```text
docker-compose.prod.yml
scripts/deploy-prod.sh
docker/mysql/init
.env
```

随后在服务器上执行部署脚本，完成镜像拉取、容器重建和旧镜像清理。

## 7. 部署后访问

默认端口：

```text
前端：http://服务器地址/
后端：http://服务器地址:8000
后端文档：http://服务器地址/docs
```

前端 Nginx 会把 `/api`、`/docs` 和 `/openapi.json` 代理到后端容器，所以大多数情况下只访问前端地址即可。

## 8. 常用排查命令

登录服务器后进入部署目录：

```bash
cd ~/ai-testcase-platform
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f frontend
docker compose -f docker-compose.prod.yml logs -f mysql
```

手动重新部署当前 `.env` 中配置的镜像：

```bash
BACKEND_IMAGE=ghcr.io/<owner>/<repo>-backend \
FRONTEND_IMAGE=ghcr.io/<owner>/<repo>-frontend \
IMAGE_TAG=latest \
DEPLOY_PATH="$PWD" \
./deploy-prod.sh
```

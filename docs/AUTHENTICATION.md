# 登录系统说明

> 最近更新：2026-06-27

## 1. 功能范围

平台当前支持账号密码登录、退出登录、当前用户查询、管理员创建用户、启用或禁用用户、基础角色权限和登录审计。用户登录后才能访问用例生成、Swagger 导入、接口执行、UI 自动化、报告中心、缺陷跟踪和历史记录等业务功能。

## 2. 默认管理员

后端启动时会检查是否存在管理员账号。如果不存在，会按环境变量自动创建默认管理员：

```text
APP_ADMIN_USERNAME=admin
APP_ADMIN_PASSWORD=Admin@123456
APP_ADMIN_DISPLAY_NAME=管理员
```

演示环境可以直接使用该账号登录。正式使用前建议修改默认密码，并设置足够长的 `AUTH_SECRET_KEY`。

## 3. 会话与密码安全

- 登录态通过 `HttpOnly Cookie` 保存，Cookie 名称默认为 `ai_test_access_token`。
- Token 使用 HS256 签名，过期时间由 `AUTH_TOKEN_EXPIRE_MINUTES` 控制，默认 1440 分钟。
- 密码使用 PBKDF2-HMAC-SHA256 加盐哈希保存，不保存明文密码。
- 登录成功和失败都会写入登录审计记录。

常用环境变量：

```text
AUTH_SECRET_KEY=change-this-to-a-long-random-secret
AUTH_TOKEN_EXPIRE_MINUTES=1440
AUTH_COOKIE_SECURE=false
APP_ADMIN_USERNAME=admin
APP_ADMIN_PASSWORD=Admin@123456
APP_ADMIN_DISPLAY_NAME=管理员
AUTH_SQLITE_PATH=generated/auth.db
```

本地 HTTP 环境保持 `AUTH_COOKIE_SECURE=false`。如果后续部署到 HTTPS 环境，可改为 `true`。

## 4. 用户角色

当前角色包括：

- `admin`：可以使用所有测试功能，并可以进入用户管理创建、启用或禁用账号。
- `tester`：可以使用测试平台功能，但不能访问用户管理接口。

第一版权限粒度保持在角色级别，后续如果需要团队协作空间、项目级权限或历史记录按用户隔离，可以在此基础上扩展。

## 5. 存储方式

如果启用 MySQL：

```text
DATABASE_ENABLED=true
```

系统会在 MySQL 中创建 `users` 和 `login_audit_logs` 表，并把用户账号和登录审计写入 MySQL。

如果未启用 MySQL，登录系统会使用本地 SQLite 文件：

```text
generated/auth.db
```

这样不连接 MySQL 时也可以登录平台、创建用户和演示权限功能。生成历史、接口执行历史和 UI 执行历史仍按原有 MySQL 开关控制。

## 6. 接口清单

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
GET  /api/auth/users
POST /api/auth/users
PATCH /api/auth/users/{user_id}/status
POST /api/auth/change-password
```

其中用户管理接口需要管理员权限。

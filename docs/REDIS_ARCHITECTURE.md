# Redis 高并发能力说明

> 最近更新：2026-06-30
> 文档用途：说明 Redis 如何融入 FastAPI + Vue + MySQL 架构，并支撑缓存、任务队列、任务状态、限流和分布式锁。

## 1. 架构定位

Redis 不替代 MySQL。当前系统中：

- MySQL 负责用户、历史记录、执行结果等持久化数据。
- Redis 负责高频临时数据、任务队列、任务状态、限流和分布式锁。
- FastAPI 继续提供 API 和权限控制。
- Vue 前端通过任务中心查看后台任务状态。

```text
Vue
  -> FastAPI
      -> MySQL: 持久化历史和结果
      -> Redis: 缓存、队列、进度、限流、锁
          -> FastAPI Worker: 执行接口、并发、UI 自动化任务
```

## 2. 五阶段落地内容

### 阶段一：Redis 基础设施

已新增：

- `app/services/redis_service.py`
- `redis` Python 依赖
- `docker-compose.yml` Redis 服务
- `docker-compose.prod.yml` Redis 服务
- `.env.docker.example` 和 `.env.production.example` Redis 配置
- `/api/redis/status` 状态接口

关键变量：

```text
REDIS_ENABLED=true
REDIS_URL=redis://redis:6379/0
REDIS_KEY_PREFIX=ai-test
```

### 阶段二：缓存

已对这些低风险读接口增加短 TTL 缓存：

```text
GET /api/history
GET /api/history/{session_id}
GET /api/api-tests/history
GET /api/ui-tests/history
```

写入新历史后会主动失效相关缓存，避免报告中心和历史列表长时间显示旧数据。

### 阶段三：任务队列

已新增 Redis 后台任务入口：

```text
POST /api/tasks/api-tests/run
POST /api/tasks/api-tests/suite
POST /api/tasks/api-tests/load
POST /api/tasks/ui-tests/run
GET  /api/tasks
GET  /api/tasks/{task_id}
POST /api/tasks/{task_id}/cancel
```

前端已新增“任务中心”，并在接口执行、接口用例集、并发执行和 UI 自动化区域提供“入队执行”按钮。

### 阶段四：限流与分布式锁

已新增：

- 用户级任务提交限流。
- 同用户相同任务短时间防重复提交。
- Redis 锁自动释放。

关键变量：

```text
TASK_SUBMIT_RATE_LIMIT=30
TASK_SUBMIT_RATE_WINDOW_SECONDS=60
TASK_RESULT_TTL_SECONDS=86400
```

### 阶段五：前端任务中心

任务中心显示：

- Redis 连接状态。
- 队列 worker 数。
- 当前排队数量。
- 最近后台任务。
- 任务进度、状态、错误信息。
- 成功任务结果一键载入。
- 排队或运行任务取消。

## 3. 启动方式

Docker Compose 方式会自动启动 Redis：

```powershell
.\scripts\docker-start.cmd
```

裸本地开发如果不想启动 Redis，可以保持 `REDIS_ENABLED=false` 或不配置 `REDIS_URL`，原有同步执行能力不受影响。

## 4. 当前边界

当前版本为了易部署，任务 worker 运行在 FastAPI 进程内。对于课程设计、项目演示和中小规模团队内部使用已经足够。

如果后续要做更大规模并发，可以继续扩展为独立 worker 进程：

```text
Web API 进程：只负责接收请求和查询任务状态
Worker 进程：只负责消费 Redis 队列并执行任务
```

这时可以进一步演进到 Celery/RQ/arq 等成熟任务框架。

# 接口测试执行配置说明

平台的“接口执行”模块已经从单接口请求扩展为接口测试执行中心，覆盖常见接口测试点：参数与 Header、响应内容、状态码、业务字段、Schema、鉴权变量、接口串联、数据库校验、批量执行、并发执行和执行历史。

## 启动方式不变

后端：

```powershell
cd D:\AI_code\AI_Test
.\scripts\start.cmd
```

前端另开窗口：

```powershell
cd D:\AI_code\AI_Test
.\scripts\start-frontend.cmd
```

访问：

```text
http://127.0.0.1:5173
```

前端打开后需要先登录。默认管理员账号为 `admin / Admin@123456`，可通过环境变量调整。

## 字段断言 JSON

字段断言写在“字段断言 JSON”中，支持数组格式：

```json
[
  {
    "name": "服务状态为 ok",
    "source": "json",
    "path": "$.status",
    "operator": "equals",
    "expected": "ok"
  },
  {
    "name": "响应头 Trace 存在",
    "source": "header",
    "header": "X-Trace-Id",
    "operator": "exists"
  },
  {
    "name": "响应时间小于 1 秒",
    "source": "time",
    "operator": "lt",
    "expected": 1000
  }
]
```

支持的 `source`：

- `json`：从 JSON 响应体读取，使用 `path`
- `header`：从响应头读取，使用 `header`
- `body`：从响应文本读取
- `status`：读取 HTTP 状态码
- `time`：读取接口耗时毫秒
- `variable`：读取环境变量或上一步提取变量

支持的 `operator`：

```text
equals / notEquals / contains / notContains / exists / notExists
gt / gte / lt / lte / regex / in / startsWith / endsWith / type / length
```

## JSONPath 支持

当前支持常见 JSONPath 子集：

```text
$                    整个 JSON
$.data.id            对象字段
$.items[0].name      数组下标
$.items[*].id        数组展开
```

## JSON Schema

写在“JSON Schema”中：

```json
{
  "type": "object",
  "required": ["status", "service", "docs"],
  "properties": {
    "status": { "type": "string" },
    "service": { "type": "string" },
    "docs": { "type": "string" }
  }
}
```

支持 `type`、`required`、`properties`、`items`、`enum`。

## 环境变量与变量替换

环境变量写在“环境变量 JSON”中：

```json
{
  "base_url": "http://127.0.0.1:8000",
  "token": "example-token"
}
```

在 URL、Header、Body、SQL、断言内容中都可以使用：

```text
{{base_url}}/api/history
Bearer {{token}}
```

## 变量提取

写在“变量提取 JSON”中，用于把当前响应中的值保存给后续接口步骤：

```json
[
  {
    "name": "token",
    "source": "json",
    "path": "$.data.token"
  },
  {
    "name": "trace_id",
    "source": "header",
    "header": "X-Trace-Id"
  }
]
```

## 数据库校验

写在“数据库校验 JSON”中。为了安全，平台只允许执行单条 `SELECT` 查询：

```json
[
  {
    "name": "生成历史已写入",
    "sql": "SELECT COUNT(*) AS total FROM generation_sessions",
    "operator": "gte",
    "expected": 1
  }
]
```

也可以指定列名：

```json
[
  {
    "name": "接口执行记录已写入",
    "sql": "SELECT COUNT(*) AS total FROM api_test_runs",
    "column": "total",
    "operator": "gte",
    "expected": 1
  }
]
```

## 用例集步骤 JSON

“执行用例集”会按顺序执行步骤，支持从前一个步骤提取变量给后续步骤使用：

单个接口用例集最多支持 `500` 个步骤。这个上限适合做完整业务回归，例如登录、鉴权、商品、购物车、订单、支付、取消、异常参数和权限边界串联验证。执行大型用例集时建议优先使用测试环境，并避免把它当作高并发压测工具使用。

前端“执行用例集”默认会在单个步骤失败后继续执行后续步骤，便于一次性收集完整失败清单。后端接口仍支持通过 `stopOnFailure` 控制是否遇到失败立即中断。

```json
[
  {
    "name": "登录",
    "method": "POST",
    "url": "{{base_url}}/api/login",
    "headers": { "Content-Type": "application/json" },
    "bodyMode": "json",
    "body": "{ \"username\": \"demo\", \"password\": \"demo\" }",
    "expectedStatus": 200,
    "extractors": [
      { "name": "token", "source": "json", "path": "$.data.token" }
    ]
  },
  {
    "name": "携带 token 查询用户信息",
    "method": "GET",
    "url": "{{base_url}}/api/user/profile",
    "headers": {
      "Authorization": "Bearer {{token}}"
    },
    "expectedStatus": 200,
    "assertions": [
      { "name": "用户 ID 存在", "source": "json", "path": "$.data.id", "operator": "exists" }
    ]
  }
]
```

## 并发执行

设置“并发次数”和“并发数”，点击“并发执行”。结果会返回：

- 总请求数
- 并发数
- 通过数和失败数
- 总耗时
- 最小、最大、平均耗时
- P50、P95 耗时

这不是完整压测工具，但可以覆盖接口稳定性和基础性能冒烟。

## 覆盖能力清单

- 基础连通性：请求可达、方法、URL、状态码
- 参数与 Header：Headers JSON、Body、Form、Multipart、变量替换
- 响应内容：Body 包含、JSONPath 字段、响应头、Schema
- 业务断言：自定义字段断言和操作符
- 鉴权与串联：提取 token、后续请求引用变量
- 数据一致性：执行接口后用 SELECT 校验 MySQL
- 批量执行：用例集顺序执行、失败中断
- 性能稳定性：并发执行、耗时指标
- 历史追踪：所有执行结果保存到 MySQL

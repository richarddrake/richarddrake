# MySQL 数据库配置说明

本项目现在支持把生成历史保存到 MySQL。数据库用于持久化保存生成会话、输入摘要、材料摘要、测试用例明细和 Excel 下载地址。

## 1. 安装依赖

在项目根目录执行：

```powershell
pip install -r requirements.txt
```

新增依赖包括：

```text
SQLAlchemy
PyMySQL
```

## 2. 创建数据库

登录 MySQL 后执行：

```sql
CREATE DATABASE ai_testcase
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
```

推荐创建独立账号：

```sql
CREATE USER 'ai_test_user'@'%' IDENTIFIED BY 'your-mysql-password';
GRANT ALL PRIVILEGES ON ai_testcase.* TO 'ai_test_user'@'%';
FLUSH PRIVILEGES;
```

如果只在本机访问，也可以把 `%` 改成 `localhost`。

## 3. 配置 .env

复制 `.env.example` 为 `.env`，然后修改 MySQL 配置：

```text
DATABASE_ENABLED=true
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=ai_test_user
MYSQL_PASSWORD=your-mysql-password
MYSQL_DATABASE=ai_testcase
MYSQL_CHARSET=utf8mb4
```

也可以直接使用完整连接串：

```text
DATABASE_ENABLED=true
DATABASE_URL=mysql+pymysql://ai_test_user:your-mysql-password@127.0.0.1:3306/ai_testcase?charset=utf8mb4
```

如果同时配置了 `DATABASE_URL` 和 `MYSQL_*`，系统优先使用 `DATABASE_URL`。

## 4. 启动后端

```powershell
.\scripts\start.cmd
```

后端启动时会自动创建以下表：

```text
generation_sessions
generation_materials
test_cases
```

## 5. 检查连接状态

打开：

```text
http://127.0.0.1:8000/api/database/status
```

返回示例：

```json
{
  "enabled": true,
  "connected": true,
  "message": "MySQL 连接正常。"
}
```

## 6. 历史记录接口

查询最近历史：

```text
http://127.0.0.1:8000/api/history
```

查询指定会话：

```text
http://127.0.0.1:8000/api/history/{session_id}
```

前端页面会自动调用这些接口，在“历史记录”区域展示最近生成结果。

## 7. 常见问题

如果接口显示 MySQL 未启用，检查：

```text
DATABASE_ENABLED=true
```

如果接口显示连接失败，检查：

```text
MySQL 服务是否启动
账号密码是否正确
数据库 ai_testcase 是否已创建
防火墙是否允许 3306 端口
MYSQL_HOST 是否写成了正确地址
```

如果密码里有特殊字符，推荐使用 `MYSQL_*` 分项配置；系统会自动处理 URL 转义。

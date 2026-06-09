-- 这个初始化脚本负责准备演示环境所需的数据库字符集和种子说明数据。
ALTER DATABASE ai_testcase CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS demo_seed_notes (
  id INT PRIMARY KEY AUTO_INCREMENT,
  title VARCHAR(120) NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO demo_seed_notes (title, content)
VALUES
  ('demo-openapi', 'Use docs/demo/openapi.json to import executable API cases.'),
  ('demo-prd', 'Use docs/demo/prd.md as a multi-source requirement material.')
ON DUPLICATE KEY UPDATE title = title;

-- EchoSQL / MiniDB 端到端演示 SQL（测试文档 3.3 演示脚本）
-- 用法: python main.py -f demo.sql    或    python -m cli -f demo.sql
-- 说明: 本脚本每次执行都会向 data/minidb.db 追加同名表，若表已存在会报错；
--       如需干净演示，可先删除 data/minidb.db 或换 --data-dir。

-- 1) 建表
CREATE TABLE student(id INT, name VARCHAR, age INT);

-- 2) 插入
INSERT INTO student(id, name, age) VALUES (1, 'Alice', 20);
INSERT INTO student(id, name, age) VALUES (2, 'Bob', 17);
INSERT INTO student(id, name, age) VALUES (3, 'Carol', 22);

-- 3) 条件查询：期望返回 Alice、Carol
SELECT id, name FROM student WHERE age > 18;

-- 4) 删除
DELETE FROM student WHERE id = 2;

-- 5) 再查询：期望 id=2 的 Bob 不可见
SELECT * FROM student WHERE id = 2;
SELECT id, name FROM student;

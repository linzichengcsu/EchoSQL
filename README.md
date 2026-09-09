# EchoSQL · MiniDB 数据库管理系统

中南大学《大型平台软件设计实习》课程设计 —— **数据库管理系统（MiniDB）**。

一个可在单机运行的教学型关系型数据库原型：接收 SQL，经 **SQL 编译器** 翻译为逻辑执行计划，
由 **数据库引擎** 调用 **页式存储系统** 完成物理读写，贯通「SQL → 执行计划 → 数据页」完整链路。

## 技术栈

| 层级 | 技术 | 说明 |
| --- | --- | --- |
| 语言 | Python 3.9+（本机 3.9.13） | 标准库即可实现页式存储与编译器 |
| 编译器 | 手写递归下降（Lexer/Parser） | 词法 → 语法 → 语义 → 计划 |
| 存储层 | 文件 I/O + `struct`/位图页表 | 4KB 页、LRU/FIFO 缓存与命中统计、Checkpoint 持久化 |
| Web 接口 | Flask（可选扩展） | Web 控制台 / REST API（SRS 2.3） |
| 测试 | pytest + pytest-cov | 分层用例（单元/集成/E2E/边界/持久化） |
| 可视化 | graphviz（可选） | AST / Logical Plan 树形可视化 |

## 目录结构（指导文档 5 章推荐结构 + Web 层）

```
EchoSQL/
├── sql_compiler/        # SQL 编译器：lexer / parser / semantic / planner / catalog
│   ├── tokens.py        # Token 与 TokenType（词法单元）
│   ├── lexer.py         # 词法分析器（FR-1.1）
│   ├── ast_nodes.py     # AST 节点定义
│   ├── parser.py        # 递归下降语法分析器（FR-1.2）
│   ├── catalog.py       # 编译期模式目录（FR-1.3）
│   ├── semantic.py      # 语义分析器（FR-1.3）
│   ├── planner.py       # 逻辑执行计划生成（FR-1.4，含常量折叠优化）
│   └── errors.py        # 词法/语法/语义错误类型（[类型, 位置, 原因]）
├── storage/             # 存储系统：page / buffer(LRU/FIFO) / file_manager / errors
│   ├── page.py          # 页式存储模型：固定 4KB 页、Page 对象（FR-2.1）
│   ├── buffer.py        # 页缓存池：LRU/FIFO 替换、命中统计、替换日志（FR-2.2）
│   ├── file_manager.py  # 磁盘文件管理：页分配/释放、页表持久化（FR-2.1/2.4）
│   └── errors.py        # 存储错误类型（StorageError 及子类）
├── engine/              # 数据库引擎（FR-3.x）：executor / storage_engine / catalog_manager
│   ├── executor.py      # 执行引擎：CreateTable/Insert/SeqScan/Filter/Project/Delete 算子 + 表达式求值（FR-3.1/3.5）
│   ├── storage_engine.py# 存储引擎：槽页 RowPage、行序列化、表扩展与回收（FR-3.2）
│   ├── catalog_manager.py # 系统目录：元数据以特殊表持久化，本身经存储引擎读写（FR-3.3）
│   └── errors.py        # 引擎运行时错误（EngineError / RowTooLarge / CatalogCorrupted）
├── cli/                 # 命令行接口（cmd REPL，FR-3.4）：输入 SQL 返回结果/错误，-f 批处理
├── web/                 # Flask Web 控制台与 API（/api/sql、/api/tables、/api/stats）
├── tests/               # pytest 测试（test_lexer/parser/semantic/planner/pipeline 编译器；test_storage 存储；
│   │                    #   test_engine 引擎端到端 TC-E2E-01~05；test_web_api Web API 集成；
│   │                    #   P5 新增 test_boundary 边界 / test_optimizer 规则优化 / test_cli 命令行；
│   │                    #   runner.py + run_all.py 统一启动方法，每个 test_*.py 均提供 run_tests()）
├── utils/               # 工具函数
├── data/                # 数据文件目录（页式存储落盘位置，minidb.db + 引擎系统目录）
├── grammar.md           # SQL 子集文法（必提交，P2 阶段细化定稿）
├── demo.sql             # 端到端演示 SQL（测试文档 3.3 演示脚本）
├── requirements.txt
├── smoke_test.py        # 环境冒烟
└── main.py              # 主程序入口（CLI：REPL / -f 批处理 / doctor 环境自检）
```

## 开发环境搭建

```powershell
# 1. 创建虚拟环境（Windows；macOS/Linux 用 python3 -m venv venv）
py -3.9 -m venv venv            # 本机系统 Python 为 3.9.13（VS Shared）

# 2. 激活虚拟环境
.\venv\Scripts\activate         # Windows PowerShell
# source venv/bin/activate      # macOS / Linux

# 3. 安装依赖（网络慢可加 -i https://pypi.tuna.tsinghua.edu.cn/simple）
pip install -r requirements.txt

# 4. 环境自检
python smoke_test.py            # 期望输出 Python version: 3.9.x / Smoke test OK
python main.py doctor           # 打印各依赖版本
```

## 运行测试

```powershell
pytest -v                       # 全部测试
pytest --cov=. --cov-report=term-missing   # 覆盖率统计
```

P5 起，每个测试模块（tests/test_*.py）都提供**同名统一启动方法** `run_tests()`，
开发者无需了解 pytest 细节即可按同一方式运行任意测试类（模块）：

```powershell
python tests/test_engine.py     # 直接运行单个测试模块（任意 test_*.py）
python tests/run_all.py         # 一键运行全部测试（等价 pytest tests，参数透传）
python tests/run_all.py --cov=. --cov-report=term-missing   # 总入口带覆盖率
```

编程方式调用（每个模块的 run_tests 返回 pytest 退出码，0 = 全部通过）：

```python
import sys
sys.path.insert(0, "tests")
import test_optimizer as m
sys.exit(m.run_tests(verbose=False))          # 运行 test_optimizer 全部用例
```

## 启动 Flask Web 控制台

```powershell
python -m web.app               # http://127.0.0.1:5000（SQL 控制台）
# 健康检查：GET http://127.0.0.1:5000/api/health
# 执行 SQL：POST /api/sql  {"sql": "SELECT * FROM t;"}
# 表结构：  GET /api/tables     运行统计：GET /api/stats
```

## 文档索引

- `docs/《数据库管理系统》软件需求规约文档.docx` —— SRS（功能/接口/验收）
- `docs/《数据库管理系统》软件测试文档.docx` —— 测试用例与验收准则
- `docs/《数据库管理系统》推荐技术栈安装指导文档.docx` —— 环境与结构指引
- `grammar.md` —— SQL 子集文法（P2 阶段细化定稿，与编译器实现对照）

## 编译器流水线（P2 交付）

```python
from sql_compiler import pipeline, Catalog, SQLError

cat = Catalog()
try:
    result = pipeline("SELECT id, name FROM student WHERE age > 18;", cat)
    print(result)        # Token 流 → AST → 执行计划
except SQLError as e:
    print(e)             # [错误类型, 行:列, 原因]（词法/语法/语义，不崩溃）
```

## 存储系统（P3 交付）

```python
from storage import Storage, FileManager, BufferPool, PAGE_SIZE

# 统一入口：文件管理 + 页缓存（FR-2.3）
st = Storage(data_dir="data", capacity=8, policy="LRU")   # 落盘 data/minidb.db

pid = st.allocate_page()              # 分配页（页编号唯一，页 0 保留给页表）
st.write_page(pid, b"hello")          # 写缓存并标记脏（不足 4KB 自动补零）
page = st.get_page(pid)               # 带缓存取页（命中/读盘）
st.flush_page(pid)                    # 单页刷盘（TC-ST-05）
st.checkpoint()                       # Checkpoint：全部脏页刷盘（FR-2.4）
print(st.stats())                     # 命中率等统计（FR-2.2）
st.close()                            # 关闭前自动刷盘 + 写回页表

# 也可以分层使用 / 切换替换策略
fm = FileManager("data")
bp = BufferPool(fm, capacity=8, policy="FIFO")   # LRU / FIFO 可切换
bp.set_policy("LRU")
# 超大块数据按页分段写入（TC-ST-02）
from storage import split_into_pages, combine_pages
for pid, chunk in zip(pids, split_into_pages(big_data)):
    st.write_page(pid, chunk)
```

存储层需求覆盖：`read_page/write_page` 页式读写（FR-2.1）、`get_page/flush_page`
缓存与命中统计（FR-2.2）、统一 `Storage` 入口（FR-2.3）、脏页 Checkpoint 与
重启持久化（FR-2.4）。存储错误统一为 `[StorageError] 原因` 格式（见
`storage/errors.py`），非法操作不崩溃。

## 数据库引擎（P4 交付）

```python
from engine import Database

db = Database(data_dir="data")                 # 打开/创建数据库（自动加载系统目录）

db.execute("CREATE TABLE student(id INT, name VARCHAR, age INT);")  # OK
db.execute("INSERT INTO student VALUES(1,'Alice',20);")             # 1 row inserted
db.execute("INSERT INTO student VALUES(2,'Bob',17);")
db.execute("INSERT INTO student VALUES(3,'Carol',22);")

result = db.execute("SELECT id,name FROM student WHERE age > 18;")  # 条件查询
print(result.format())        # SELECT 输出对齐表格 / 其余输出 message
# id  | name
# ----+-------
# 1   | Alice
# 3   | Carol

db.execute("DELETE FROM student WHERE id = 2;")                     # 1 row deleted
db.execute_script("...;...;")     # 按 ';' 切分逐条执行，返回结果列表
db.tables() / db.table_infos()    # 目录查询（FR-3.3）
db.stats()                        # 缓存命中率等运行统计（贯通 FR-2.2）
db.drop_table("student")          # 删表并回收全部数据页（FR-3.2 表的回收）
db.close()                        # 关闭前持久化目录 + Checkpoint 刷盘
```

命令行（FR-3.4 / SRS 5.1 交互）：

```powershell
python main.py                    # 交互式 REPL：MiniDB> 输入 SQL，quit 退出
python main.py -f demo.sql        # 批处理执行 SQL 脚本
python main.py --data-dir tmp --policy FIFO   # 指定数据目录 / 替换策略
```

Web 控制台（SRS 2.3「也可通过 API 调用」）：`python -m web.app` 后打开
http://127.0.0.1:5000，可直接在页面上执行 SQL 并查看结果表格。

引擎内部结构（三模块 + 门面）：
- `executor.py` 执行引擎（FR-3.1）：CreateTable / Insert / SeqScan / Filter /
  Project / Delete 算子；表达式求值遵循 SQL 三值逻辑（NULL 为 unknown），
  与编译期常量折叠（planner）语义一致；
- `storage_engine.py` 存储引擎（FR-3.2）：`RowPage` 槽页（页头 + 槽数组 +
  行数据 + 空闲区，SRS 第 6 章）、`encode_row/decode_row` 行序列化
  （INT/FLOAT/VARCHAR/NULL 自描述编码）、表页集合管理（插入自动扩展新页、
  删除标记 + 整页回收、释放全部页）；
- `catalog_manager.py` 系统目录（FR-3.3）：元数据（表名/列名/列类型/页集合）
  以 JSON blob 持久化为「特殊表」，占用文件开头固定目录区（页 1~16，
  本身经存储引擎读写），重启后表结构与数据页映射不丢失；
- `errors.py` 引擎运行时错误（`[EngineError, 原因]`），非法输入不崩溃。

引擎需求覆盖：四类核心 SQL 完整执行（FR-3.5）、持久化重启可查询（TC-E2E-05）、
条件查询准确性（TC-E2E-03）、删除后不可见与整页回收（TC-E2E-04）、
建表重复报错（TC-E2E-01）、大量数据插入跨页存储（TC-E2E-02，见 `tests/test_engine.py`）。

## P5 测试与优化（交付）

P5 阶段聚焦「系统测试、边界测试、优化、调试」，交付如下。

### 1. 测试类扩展：每个测试类都有统一启动方法 `run_tests()`

| 测试模块（tests/） | 类型 | 说明 |
| --- | --- | --- |
| test_lexer / test_parser / test_semantic / test_planner / test_pipeline | 编译器单测 | P2 既有 |
| test_storage | 存储单测 | P3 既有 |
| test_engine / test_web_api / test_env | 引擎 E2E / Web API / 环境 | P4 既有 |
| **test_boundary**（P5 新增） | 边界 / 系统测试 | 超长输入、字符串/数字/注释边界、深度嵌套括号、缓存容量/策略参数、页大小与行大小上限、INT 32 位范围、跨页大量行、非 JSON 请求、INT 溢出 400 等 |
| **test_optimizer**（P5 新增） | 规则优化测试 | 常量折叠全规则（算术/比较/逻辑/NOT/NULL 三值逻辑全值表）、优化幂等性、无谓词计划不变、**优化不改变查询语义**（引擎级保真） |
| **test_cli**（P5 新增） | CLI 系统测试 | MiniDBShell 输出（表格/message/错误打印）、tables/stats/quit、run_sql_file 批处理成功/失败、cli.main 参数解析 |

统一启动方法约定（实现见 `tests/runner.py`，总入口 `tests/run_all.py`）：
- 每个 `tests/test_*.py` 均定义 **同名** `run_tests(verbose=True, extra_args=None) -> int`；
- 命令行直接运行：`python tests/test_xxx.py`；一键全部：`python tests/run_all.py`；
- 编程调用：`from runner import run_module; run_module("tests/test_xxx.py")`；
- 返回 pytest 退出码（0 = 全部通过），可接入脚本 / CI。

### 2. 测试与覆盖率

- 用例数由 P4 的 **145 增至 222**，`pytest tests` 全绿；
- 覆盖率：`pytest tests --cov=. --cov-report=term-missing`（核心模块均 >90%）；
- 补齐缺口：`cli` 模块由 0% 覆盖到全绿（test_cli.py）。

### 3. 缺陷修复记录（调试）

| 编号 | 缺陷 | 修复 | 验证 |
| --- | --- | --- | --- |
| #1 | INT 字面量超出 32 位范围时 `struct.pack` 抛未定义异常 `struct.error`（CLI/Web 层无法捕获，Web 直接 500） | `encode_row` 增加 32 位范围检查，改抛 `RowTooLarge`（EngineError 子类，`[RowTooLarge, ...]` 格式） | test_boundary `test_int_32bit_range_boundary` / `test_api_int_overflow_returns_400`；Web 返回 400 而非 500 |
| #2 | grammar.md §1.2.5 承诺浮点 `1.`、`.5` 合法，词法分析器实际拒绝 | lexer `_lex_number` 支持三种浮点形式（`3.14` / `1.` / `.5`），`1.2.3`、`.5.6`、`12abc` 等仍按非法数字报错 | test_boundary `test_lexer_float_forms_from_grammar` / `test_lexer_float_illegal_still_rejected` |

### 4. 已知限制（文法内不承诺，不视为缺陷）

- 无一元负号：`-1` 不能作为字面量（literal 文法仅 INT_CONST / FLOAT_CONST / STRING / TRUE / FALSE / NULL）；
- 不支持科学计数法（`1e3` 报 LexError）；
- 孤立分号 `;` 在语法层拒绝（`Database.execute` 层宽容处理）。

## 当前进度

- [x] P0 环境准备：venv + 依赖 + 项目骨架 + Flask 开发环境 + 环境冒烟测试
- [x] P1 文法与项目结构（grammar.md 细化定稿 + 目录结构完善）
- [x] P2 SQL 编译器（Lexer / Parser / Semantic / Planner / Catalog + 单测）
- [x] P3 存储系统（页式存储 / 缓存与替换 LRU+FIFO / 持久化 + 单测）
- [x] P4 数据库引擎（执行引擎 / 存储引擎 / Catalog / CLI + Web 集成）
- [x] P5 测试与优化（新增边界/优化/CLI 测试 + 统一启动方法 + 缺陷修复，详见上节）
- [x] P6 黑盒测试（将特定测试数据集注入测试脚本，不依赖内部调用）
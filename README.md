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
├── engine/              # 数据库引擎：executor / storage_engine / catalog_manager
├── cli/                 # 命令行接口（cmd/argparse）
├── web/                 # Flask Web 控制台与 API
├── tests/               # pytest 测试（test_env 环境冒烟；test_lexer/parser/semantic/planner/pipeline 编译器；test_storage 存储）
├── utils/               # 工具函数
├── data/                # 数据文件目录（页式存储落盘位置，minidb.db）
├── grammar.md           # SQL 子集文法（必提交，P2 阶段细化定稿）
├── requirements.txt
├── smoke_test.py        # 环境冒烟
└── main.py              # 主程序入口（CLI，doctor 子命令为环境自检）
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

## 启动 Flask Web 控制台

```powershell
python -m web.app               # http://127.0.0.1:5000
# 健康检查：GET http://127.0.0.1:5000/api/health
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

## 当前进度

- [x] P0 环境准备：venv + 依赖 + 项目骨架 + Flask 开发环境 + 环境冒烟测试
- [x] P1 文法与项目结构（grammar.md 细化定稿 + 目录结构完善）
- [x] P2 SQL 编译器（Lexer / Parser / Semantic / Planner / Catalog + 单测）
- [x] P3 存储系统（页式存储 / 缓存与替换 LRU+FIFO / 持久化 + 单测）
- [ ] P4 数据库引擎（执行引擎 / 存储引擎 / Catalog / CLI + Web 集成）
- [ ] P5 测试与优化（覆盖率 / 边界 / 规则优化）

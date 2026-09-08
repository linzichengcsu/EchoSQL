# EchoSQL · MiniDB 数据库管理系统

中南大学《大型平台软件设计实习》课程设计 —— **数据库管理系统（MiniDB）**。

一个可在单机运行的教学型关系型数据库原型：接收 SQL，经 **SQL 编译器** 翻译为逻辑执行计划，
由 **数据库引擎** 调用 **页式存储系统** 完成物理读写，贯通「SQL → 执行计划 → 数据页」完整链路。

## 技术栈（依据《推荐技术栈安装指导文档》）

| 层级 | 技术 | 说明 |
| --- | --- | --- |
| 语言 | Python 3.9+（本机 3.9.13） | 标准库即可实现页式存储与编译器 |
| 编译器 | 手写递归下降（Lexer/Parser） | 词法 → 语法 → 语义 → 计划 |
| 存储层 | 文件 I/O + `struct` 序列化 | 4KB 页、Row↔Page 映射、LRU/FIFO 缓存 |
| Web 接口 | Flask（可选扩展） | Web 控制台 / REST API（SRS 2.3） |
| 测试 | pytest + pytest-cov | 分层用例（单元/集成/E2E/边界/持久化） |
| 可视化 | graphviz（可选） | AST / Logical Plan 树形可视化 |

## 目录结构（指导文档 5 章推荐结构 + Web 层）

```
EchoSQL/
├── sql_compiler/        # SQL 编译器：lexer / parser / semantic / planner / catalog
├── storage/             # 存储系统：page / buffer(LRU/FIFO) / file_manager
├── engine/              # 数据库引擎：executor / storage_engine / catalog_manager
├── cli/                 # 命令行接口（cmd/argparse）
├── web/                 # Flask Web 控制台与 API
├── tests/               # pytest 测试（test_env 为环境冒烟）
├── utils/               # 工具函数
├── data/                # 数据文件目录（页式存储落盘位置）
├── grammar.md           # SQL 子集文法（必提交）
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
- `grammar.md` —— SQL 子集文法（P2 阶段细化）

## 当前进度

- [x] P0 环境准备：venv + 依赖 + 项目骨架 + Flask 开发环境 + 环境冒烟测试
- [ ] P1 文法与项目结构（grammar.md 细化）
- [ ] P2 SQL 编译器（Lexer / Parser / Semantic / Planner）
- [ ] P3 存储系统（页式存储 / 缓存与替换 / 持久化）
- [ ] P4 数据库引擎（执行引擎 / 存储引擎 / Catalog / CLI + Web 集成）
- [ ] P5 测试与优化（覆盖率 / 边界 / 规则优化）

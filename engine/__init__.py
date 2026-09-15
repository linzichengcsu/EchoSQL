"""数据库引擎模块（对应 SRS FR-3.1 ~ FR-3.5）。

    executor.py         执行引擎:CreateTable / Insert / SeqScan / Filter / Project / Delete 算子
    storage_engine.py   存储引擎:Row<->Page 序列化(槽页)、空闲页管理、表扩展与回收
    catalog_manager.py  系统目录:元数据以特殊表形式持久化(类似 pg_catalog),本身经存储引擎读写
    errors.py           引擎运行时错误类型(EngineError / RowTooLarge / CatalogCorrupted)

引擎向上对接 SQL 编译器产出的逻辑执行计划,向下调用 storage 的页式存储接口。
统一入口 Database 门面:

    db = Database(data_dir="data")            # 打开/创建数据库(自动加载系统目录)
    db.execute("CREATE TABLE t(id INT);")     # 单条 SQL(可含多条语句,返回最后一条结果)
    db.execute_script("...;...;")             # 按 ';' 切分逐条执行,返回结果列表
    db.tables() / db.table_infos()            # 目录查询
    db.close()                                # 关闭前持久化目录并 Checkpoint 刷盘
"""

from typing import List, Optional

from sql_compiler import SQLError, analyze, lex, parse, plan
from sql_compiler.tokens import TokenType

from storage import Storage

from .catalog_manager import CatalogManager, DIR_PAGES, DIR_START_PAGE
from .errors import CatalogCorrupted, EngineError, RowTooLarge
from .executor import ExecutionResult, Executor, eval_expr
from .storage_engine import (
    TOMBSTONE,
    RowPage,
    TableStorage,
    decode_row,
    encode_row,
)

__all__ = [
    # 统一入口
    "Database",
    # 执行引擎
    "Executor", "ExecutionResult", "eval_expr",
    # 存储引擎
    "RowPage", "TableStorage", "encode_row", "decode_row", "TOMBSTONE",
    # 系统目录
    "CatalogManager", "DIR_START_PAGE", "DIR_PAGES",
    # 错误类型
    "EngineError", "RowTooLarge", "CatalogCorrupted",
    # 工具
    "split_statements",
]


class Database:
    """MiniDB 统一入口:编译 + 执行 + 目录 + 存储 的组合门面。

    用法:
        db = Database(data_dir="data")
        result = db.execute("SELECT id FROM t WHERE age > 18;")
        print(result.format())          # CLI 文本格式
        results = db.execute_script("INSERT ...; INSERT ...;")
        db.close()                      # with 语句亦可自动关闭
    """

    def __init__(
        self,
        data_dir: str = "data",
        capacity: int = 8,
        policy: str = "LRU",
        log: bool = True,
    ):
        self.storage = Storage(
            data_dir=data_dir, capacity=capacity, policy=policy, log=log,
        )
        self.catalog_mgr = CatalogManager(self.storage)
        self.catalog_mgr.load()
        self.executor = Executor(self.storage, self.catalog_mgr)

    # ------------------------------------------------------------------
    # 编译期目录视图(供语义分析 / 计划生成)
    # ------------------------------------------------------------------

    @property
    def catalog(self):
        return self.catalog_mgr.catalog

    # ------------------------------------------------------------------
    # SQL 执行(FR-3.4 / FR-3.5)
    # ------------------------------------------------------------------

    def execute(self, sql: str) -> Optional[ExecutionResult]:
        """编译并执行 SQL。

        支持一次输入多条语句(副作用全部生效),返回最后一条语句的结果;
        空输入(空串/纯空白/纯注释)返回 None。孤立分号或语句间多余分号属空语句,
        不再视为空输入,而是抛出语法错误 ParseError(grammar.md §2);
        编译错误(SQLError)与引擎错误(EngineError)直接抛出,
        由调用方(CLI/Web)捕获后展示,不崩溃。
        """
        tokens = lex(sql)
        if len(tokens) <= 1:  # 仅 EOF，即空输入(含纯空白/纯注释)
            return None
        ast = parse(tokens)
        analyze(ast, self.catalog_mgr.catalog)
        plans = plan(ast, self.catalog_mgr.catalog)
        results = [self.executor.execute(p) for p in plans]
        return results[-1] if results else None

    def execute_script(self, sql: str) -> List[ExecutionResult]:
        """把 SQL 文本按语句切分后逐条执行,返回每条语句的结果列表。

        用于批处理文件(demo.sql)与 CLI 多语句输入;
        任一条语句出错即抛出,已执行语句的副作用保留。
        """
        results = []
        for group in split_statements(sql):
            if not group:
                continue
            results.append(self._execute_tokens(group))
        return results

    def _execute_tokens(self, tokens) -> ExecutionResult:
        ast = parse(tokens)
        analyze(ast, self.catalog_mgr.catalog)
        plans = plan(ast, self.catalog_mgr.catalog)
        return self.executor.execute(plans[-1])

    # ------------------------------------------------------------------
    # 目录查询
    # ------------------------------------------------------------------

    def tables(self) -> List[str]:
        return self.catalog_mgr.table_names()

    def table_infos(self) -> List[dict]:
        return self.catalog_mgr.to_dict()

    def drop_table(self, name: str) -> int:
        """删表并回收数据页(引擎级 API,FR-3.2 表的回收;语法扩展见 P5)。"""
        return self.catalog_mgr.drop_table(name)

    # ------------------------------------------------------------------
    # 统计 / 生命周期
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """运行统计:缓存命中率等(FR-2.2 命中统计贯通到引擎层)。"""
        stats = self.storage.stats()
        stats["tables"] = len(self.catalog_mgr.table_names())
        return stats

    def close(self) -> None:
        """关闭前持久化目录并 Checkpoint 刷盘,保证重启后数据不丢失(TC-E2E-05)。"""
        try:
            self.catalog_mgr.save()
        finally:
            self.storage.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __repr__(self):
        return "Database(data_dir=%r, tables=%d)" % (
            self.storage.fm.data_dir, len(self.catalog_mgr.table_names()),
        )


def split_statements(sql: str) -> List[List]:
    """把 SQL 文本按 ';' 切分为 Token 组(每组一条语句,含结尾 ';')。

    基于词法分析器切分,字符串字面量内的分号不会被误切(TC-E2E 健壮性);
    孤立分号 / 连续分号是空语句,不再跳过,而是作为独立组交给语法分析器,
    由 parse 抛出 ParseError(语法层拒绝,grammar.md §2);
    末尾缺分号时宽容补一个。
    """
    from sql_compiler import Token

    tokens = lex(sql)
    groups: List[List] = []
    current: List = []
    for tok in tokens:
        if tok.type is TokenType.SEMICOLON:
            current.append(tok)  # ';' 既结束当前语句,又作为该语句的结束符
            groups.append(current)
            current = []
        elif tok.type is not TokenType.EOF:
            current.append(tok)
    if current:
        # 末尾无分号:宽容补一个(位置取最后 token)
        last = current[-1]
        current.append(Token(TokenType.SEMICOLON, ";", last.line, last.col))
        groups.append(current)
    # 每组补 EOF(Parser 依赖 EOF 结束)
    for group in groups:
        last = group[-1]
        group.append(Token(TokenType.EOF, "", last.line, last.col))
    return groups

"""SQL 编译器模块(对应 SRS FR-1.1 ~ FR-1.5)。

依据《软件需求规约文档》第 3.2 节实现编译流水线:

    lex(sql) -> Token[]     词法分析(FR-1.1)
    parse(tokens) -> AST    语法分析(FR-1.2)
    analyze(ast) -> AST     语义分析(FR-1.3)
    plan(ast) -> Plan       执行计划生成(FR-1.4)
    pipeline(sql)           完整流水线输出 Token/AST/Plan(FR-1.5)

模块边界(与 grammar.md §6 对照):
    tokens.py    Token / TokenType 与关键字表
    lexer.py     词法分析器(手写递归扫描)
    parser.py    语法分析器(递归下降)
    ast_nodes.py AST 节点定义
    semantic.py  语义分析器(名字解析 + 类型检查)
    catalog.py   编译期模式目录(createTable / findTable / findColumn / getType)
    planner.py   逻辑执行计划生成器(含常量折叠优化)
    errors.py    错误类型(词法/语法/语义,统一 [类型, 位置, 原因] 格式)

错误不崩溃:非法输入分别抛出 LexError / ParseError / SemanticError 子类,
统一可通过 SQLError 捕获,str() 输出为 [错误类型, 行:列, 原因]。
"""

from dataclasses import dataclass
from typing import List, Optional

from .ast_nodes import (
    BOOL,
    NULL,
    Program,
    Statement,
    CreateTableStmt,
    InsertStmt,
    SelectStmt,
    DeleteStmt,
    ColumnDef,
    Star,
    ColumnRef,
    Literal,
    NotExpr,
    BinaryExpr,
    Expression,
)
from .catalog import Catalog, ColumnInfo, TableInfo
from .errors import (
    SQLError,
    LexError,
    ParseError,
    SemanticError,
    UnknownTable,
    UnknownColumn,
    TableAlreadyExists,
    ColumnCountMismatch,
    TypeMismatch,
)
from .lexer import lex
from .parser import parse
from .planner import (
    Plan,
    CreateTablePlan,
    InsertPlan,
    SeqScanPlan,
    FilterPlan,
    ProjectPlan,
    DeletePlan,
    plan,
    build,
    constant_fold,
    optimize,
    optimize_with_diff,
    plan_tree,
    expr_to_string,
)
from .semantic import analyze
from .tokens import Token, TokenType, KEYWORDS, DATA_TYPE_KEYWORDS

__all__ = [
    # 编译流水线入口
    "lex", "parse", "analyze", "plan", "pipeline",
    # Token / AST
    "Token", "TokenType", "KEYWORDS", "DATA_TYPE_KEYWORDS",
    "Program", "Statement",
    "CreateTableStmt", "InsertStmt", "SelectStmt", "DeleteStmt", "ColumnDef",
    "Star", "ColumnRef", "Literal", "NotExpr", "BinaryExpr", "Expression",
    "BOOL", "NULL",
    # Catalog
    "Catalog", "ColumnInfo", "TableInfo",
    # 错误类型
    "SQLError", "LexError", "ParseError", "SemanticError",
    "UnknownTable", "UnknownColumn", "TableAlreadyExists",
    "ColumnCountMismatch", "TypeMismatch",
    # 逻辑计划
    "Plan", "CreateTablePlan", "InsertPlan", "SeqScanPlan",
    "FilterPlan", "ProjectPlan", "DeletePlan",
    "build", "constant_fold", "optimize", "optimize_with_diff", "plan_tree",
    "expr_to_string",
]


@dataclass
class PipelineResult:
    """编译流水线输出(FR-1.5):Token 流 → AST → 执行计划。"""

    sql: str
    tokens: List[Token]
    ast: Program
    plans: List[Plan]

    def __str__(self):
        lines = ["-- Token 流 --"]
        for tok in self.tokens:
            lines.append("  %s" % tok)
        lines.append("-- AST --")
        lines.append(self.ast_repr())
        lines.append("-- 执行计划 --")
        for p in self.plans:
            lines.append(p.tree())
        return "\n".join(lines)

    def ast_repr(self) -> str:
        """以缩进树形式打印 AST(便于人工核对)。"""
        return "\n".join("  %s" % node for node in self.ast.statements)


def pipeline(sql: str, catalog: Optional[Catalog] = None) -> PipelineResult:
    """完整编译流水线(FR-1.5 / SRS 5.2)。

    依次执行 词法 → 语法 → 语义 → 计划 并返回各阶段产物;
    任一步骤失败抛出对应错误(LexError / ParseError / SemanticError),
    由调用方捕获后输出,非法输入不崩溃。
    """
    tokens = lex(sql)
    ast = parse(tokens)
    analyze(ast, catalog)
    plans = plan(ast, catalog)
    return PipelineResult(sql=sql, tokens=tokens, ast=ast, plans=plans)

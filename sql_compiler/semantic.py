"""语义分析器(FR-1.3)。

依据 SRS 3.2.3:
- 表/列存在性检查(依赖 Catalog 注册信息);
- 类型一致性检查(列类型与输入值/表达式是否匹配);
- INSERT 列数/列序检查(值的数量与列定义一致);
- 构建并维护 Catalog(createTable / findTable / findColumn / getType);
- 出错抛出 SemanticError 子类,格式:[错误类型, 位置, 原因说明]。

对外接口(与 SRS 5.2 内部接口一致):
    analyze(ast, catalog=None) -> AST   语义分析,名字解析与类型检查(返回通过检查的 AST)
"""

from typing import List, Optional

from .ast_nodes import (
    BOOL,
    NULL,
    NUMERIC_TYPES,
    BinaryExpr,
    ColumnDef,
    ColumnRef,
    CreateTableStmt,
    DeleteStmt,
    Expression,
    InsertStmt,
    Literal,
    NotExpr,
    Program,
    SelectStmt,
    Star,
    Statement,
)
from .catalog import Catalog, ColumnInfo
from .errors import (
    ColumnCountMismatch,
    SemanticError,
    TableAlreadyExists,
    TypeMismatch,
    UnknownColumn,
    UnknownTable,
)

__all__ = ["analyze", "SemanticAnalyzer"]

#: 比较运算符词素
_COMPARISON_OPS = {"=", "<>", "!=", "<", "<=", ">", ">="}
#: 逻辑运算符词素
_LOGICAL_OPS = {"AND", "OR"}
#: 算术运算符词素
_ARITH_OPS = {"+", "-"}
#: 字符串类类型(可互相比较/赋值)
_STRING_TYPES = {"VARCHAR", "CHAR"}


class SemanticAnalyzer:
    """对 Program 中每条语句做名字解析与类型检查,并维护 Catalog。"""

    def __init__(self, catalog: Optional[Catalog] = None):
        self.catalog = catalog if catalog is not None else Catalog()

    # ---------- 主入口 ----------
    def analyze(self, program: Program) -> Program:
        for stmt in program.statements:
            self._check_statement(stmt)
        return program

    def _check_statement(self, stmt: Statement):
        if isinstance(stmt, CreateTableStmt):
            self._check_create_table(stmt)
        elif isinstance(stmt, InsertStmt):
            self._check_insert(stmt)
        elif isinstance(stmt, SelectStmt):
            self._check_select(stmt)
        elif isinstance(stmt, DeleteStmt):
            self._check_delete(stmt)
        else:  # pragma: no cover - 防御未知节点
            raise SemanticError(stmt.line, stmt.col,
                                "unsupported statement %s" % type(stmt).__name__)

    # ---------- CREATE TABLE ----------
    def _check_create_table(self, stmt: CreateTableStmt):
        if self.catalog.has_table(stmt.table):
            raise TableAlreadyExists(
                stmt.line, stmt.col, "table %r already exists" % stmt.table
            )
        columns = [
            ColumnInfo(name=c.name, data_type=c.data_type) for c in stmt.columns
        ]
        self.catalog.create_table(stmt.table, columns)

    # ---------- INSERT ----------
    def _check_insert(self, stmt: InsertStmt):
        table = self._require_table(stmt, stmt.table)
        # 确定目标列:指定列清单则按其列序;省略则按表定义列序(TC-S-02)
        if stmt.columns is None:
            target = table.columns
        else:
            target = []
            for col_name in stmt.columns:
                col = table.find_column(col_name)
                if col is None:
                    raise UnknownColumn(
                        stmt.line, stmt.col,
                        "column %r does not exist in table %r"
                        % (col_name, table.name),
                    )
                target.append(col)
        if len(stmt.values) != len(target):
            raise ColumnCountMismatch(
                stmt.line, stmt.col,
                "INSERT has %d values but %d columns (%s)"
                % (len(stmt.values), len(target), table.name),
            )
        # 逐列类型匹配(TC-S-03)
        for col, lit in zip(target, stmt.values):
            self._check_literal_type(stmt, col, lit)

    def _check_literal_type(self, stmt: InsertStmt, col: ColumnInfo, lit: Literal):
        want = col.data_type
        got = lit.data_type
        if got == NULL:
            return  # NULL 可匹配任意列类型
        if self._assignable(want, got):
            return
        raise TypeMismatch(
            lit.line, lit.col,
            "column %r expects %s but got %s" % (col.name, want, got),
        )

    @staticmethod
    def _assignable(want: str, got: str) -> bool:
        """列类型 want 能否接受值类型 got。"""
        if want in NUMERIC_TYPES and got in NUMERIC_TYPES:
            return True  # INT/FLOAT 互相可赋(数值兼容)
        if want in _STRING_TYPES and got in _STRING_TYPES:
            return True  # VARCHAR/CHAR 同为字符串
        return want == got

    # ---------- SELECT / DELETE ----------
    def _check_select(self, stmt: SelectStmt):
        table = self._require_table(stmt, stmt.table)
        for item in stmt.select_list:
            if isinstance(item, ColumnRef) and table.find_column(item.name) is None:
                raise UnknownColumn(
                    item.line, item.col,
                    "column %r does not exist in table %r" % (item.name, table.name),
                )
        if stmt.where is not None:
            self._check_where(stmt.where, table.name)

    def _check_delete(self, stmt: DeleteStmt):
        table = self._require_table(stmt, stmt.table)
        if stmt.where is not None:
            self._check_where(stmt.where, table.name)

    def _require_table(self, stmt: Statement, name: str):
        table = self.catalog.find_table(name)
        if table is None:
            raise UnknownTable(
                stmt.line, stmt.col, "table %r does not exist" % name
            )
        return table

    def _check_where(self, expr: Expression, table_name: str):
        t = self._infer_type(expr, table_name)
        if t != BOOL:
            raise TypeMismatch(
                expr.line, expr.col,
                "WHERE condition must be boolean, got %s" % t,
            )

    # ---------- 表达式类型推断 ----------
    def _infer_type(self, expr: Expression, table_name: str) -> str:
        """推断表达式静态类型;同时完成列存在性与运算符类型检查。"""
        if isinstance(expr, ColumnRef):
            t = self.catalog.get_type(table_name, expr.name)
            if t is None:
                raise UnknownColumn(
                    expr.line, expr.col,
                    "column %r does not exist in table %r"
                    % (expr.name, table_name),
                )
            return t
        if isinstance(expr, Literal):
            return expr.data_type
        if isinstance(expr, NotExpr):
            operand_t = self._infer_type(expr.operand, table_name)
            if operand_t != BOOL:
                raise TypeMismatch(
                    expr.line, expr.col,
                    "operator NOT cannot be applied to %s" % operand_t,
                )
            return BOOL
        if isinstance(expr, BinaryExpr):
            left_t = self._infer_type(expr.left, table_name)
            right_t = self._infer_type(expr.right, table_name)
            op = expr.op.upper()
            if op in _LOGICAL_OPS:
                if left_t != BOOL or right_t != BOOL:
                    raise TypeMismatch(
                        expr.line, expr.col,
                        "operator %s requires boolean operands, got %s and %s"
                        % (op, left_t, right_t),
                    )
                return BOOL
            if op in _COMPARISON_OPS:
                self._check_comparable(expr, left_t, right_t)
                return BOOL
            if op in _ARITH_OPS:
                if left_t not in NUMERIC_TYPES or right_t not in NUMERIC_TYPES:
                    raise TypeMismatch(
                        expr.line, expr.col,
                        "operator %s cannot be applied to %s and %s"
                        % (op, left_t, right_t),
                    )
                return "FLOAT" if "FLOAT" in (left_t, right_t) else "INT"
            raise SemanticError(expr.line, expr.col,
                                "unsupported operator %r" % op)
        raise SemanticError(expr.line, expr.col,  # pragma: no cover
                            "unsupported expression %s" % type(expr).__name__)

    def _check_comparable(self, expr: BinaryExpr, left_t: str, right_t: str):
        """比较运算两侧类型须兼容(TC-S-04 等)。"""
        if left_t == NULL or right_t == NULL:
            return
        if left_t in NUMERIC_TYPES and right_t in NUMERIC_TYPES:
            return
        if left_t in _STRING_TYPES and right_t in _STRING_TYPES:
            return
        if left_t == right_t:
            return
        raise TypeMismatch(
            expr.line, expr.col,
            "cannot compare %s with %s" % (left_t, right_t),
        )


def analyze(ast: Program, catalog: Optional[Catalog] = None) -> Program:
    """语义分析:名字解析与类型检查,维护 Catalog(FR-1.3 / SRS 5.2)。"""
    return SemanticAnalyzer(catalog).analyze(ast)

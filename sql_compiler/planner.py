"""逻辑执行计划生成器(FR-1.4)。

将 AST 转换为逻辑执行计划:
- CREATE TABLE  → CreateTable
- INSERT        → Insert
- SELECT        → Project(Filter(SeqScan)):FROM→SeqScan、WHERE→Filter、SELECT 列表→Project
- DELETE        → Delete(含 WHERE 谓词)

规则式优化(进阶,TC-PL-02):常量折叠(Constant Folding),
对 Filter/Delete 谓词中的纯常量表达式求值,并展示优化前后结构差异。

对外接口(与 SRS 5.2 内部接口一致):
    plan(ast, catalog=None) -> list[Plan]    执行计划生成(可含优化)
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .ast_nodes import (
    BOOL,
    NULL,
    BinaryExpr,
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
from .catalog import Catalog

__all__ = [
    "Plan",
    "CreateTablePlan",
    "InsertPlan",
    "SeqScanPlan",
    "FilterPlan",
    "ProjectPlan",
    "DeletePlan",
    "plan",
    "build",
    "constant_fold",
    "plan_tree",
    "optimize_with_diff",
]

_COMPARISON_OPS = {"=", "<>", "!=", "<", "<=", ">", ">="}
_LOGICAL_OPS = {"AND", "OR"}
_ARITH_OPS = {"+", "-"}


# ======================================================================
# 逻辑计划节点(S 表达式风格打印:CreateTable(...) / Project(...))
# ======================================================================


@dataclass
class Plan:
    """逻辑计划节点基类。"""

    def tree(self, indent: int = 0) -> str:
        """输出树形结构文本(缩进表示父子关系)。"""
        pad = "    " * indent
        return pad + str(self)


@dataclass
class CreateTablePlan(Plan):
    table: str
    columns: List[tuple]  # [(列名, 类型), ...]

    def __str__(self):
        cols = ", ".join("%s %s" % (n, t) for n, t in self.columns)
        return "CreateTable(%s, [%s])" % (self.table, cols)


@dataclass
class InsertPlan(Plan):
    table: str
    columns: List[str]
    values: List[Literal]

    def __str__(self):
        vals = ", ".join(repr(v.value) for v in self.values)
        return "Insert(%s, [%s], [%s])" % (
            self.table, ", ".join(self.columns), vals,
        )


@dataclass
class SeqScanPlan(Plan):
    table: str

    def __str__(self):
        return "SeqScan(%s)" % self.table


@dataclass
class FilterPlan(Plan):
    predicate: Expression
    child: Plan

    def tree(self, indent: int = 0) -> str:
        pad = "    " * indent
        lines = ["%sFilter(%s)" % (pad, expr_to_string(self.predicate))]
        lines.append(self.child.tree(indent + 1))
        return "\n".join(lines)

    def __str__(self):
        return "Filter(%s)" % expr_to_string(self.predicate)


@dataclass
class ProjectPlan(Plan):
    columns: List[str]  # 展开后的列名;['*'] 保留星号表示全列
    child: Plan

    def tree(self, indent: int = 0) -> str:
        pad = "    " * indent
        lines = ["%sProject(columns=[%s])" % (pad, ", ".join(self.columns))]
        lines.append(self.child.tree(indent + 1))
        return "\n".join(lines)

    def __str__(self):
        return "Project(columns=[%s])" % ", ".join(self.columns)


@dataclass
class DeletePlan(Plan):
    table: str
    predicate: Optional[Expression]

    def __str__(self):
        if self.predicate is None:
            return "Delete(%s)" % self.table
        return "Delete(%s, where=%s)" % (self.table, expr_to_string(self.predicate))


# ======================================================================
# AST → Plan 转换
# ======================================================================


class Planner:
    def __init__(self, catalog: Optional[Catalog] = None):
        self.catalog = catalog if catalog is not None else Catalog()

    def build(self, program: Program) -> List[Plan]:
        plans = []
        for stmt in program.statements:
            plans.append(self._build_statement(stmt))
        return plans

    def _build_statement(self, stmt: Statement) -> Plan:
        if isinstance(stmt, CreateTableStmt):
            return CreateTablePlan(
                table=stmt.table,
                columns=[(c.name, c.data_type) for c in stmt.columns],
            )
        if isinstance(stmt, InsertStmt):
            table = self.catalog.find_table(stmt.table)
            if stmt.columns is None:
                columns = table.column_names() if table else []
            else:
                columns = list(stmt.columns)
            return InsertPlan(stmt.table, columns, list(stmt.values))
        if isinstance(stmt, SelectStmt):
            return self._build_select(stmt)
        if isinstance(stmt, DeleteStmt):
            return DeletePlan(stmt.table, stmt.where)
        raise TypeError("unsupported statement %s" % type(stmt).__name__)  # pragma: no cover

    def _build_select(self, stmt: SelectStmt) -> Plan:
        # FROM → SeqScan
        scan: Plan = SeqScanPlan(stmt.table)
        # WHERE → Filter
        if stmt.where is not None:
            scan = FilterPlan(stmt.where, scan)
        # SELECT 列表 → Project;'*' 展开为表全部列
        columns = self._expand_select_list(stmt)
        return ProjectPlan(columns, scan)

    def _expand_select_list(self, stmt: SelectStmt) -> List[str]:
        if len(stmt.select_list) == 1 and isinstance(stmt.select_list[0], Star):
            table = self.catalog.find_table(stmt.table)
            if table is not None:
                return table.column_names()
            return ["*"]
        return [item.name for item in stmt.select_list]


# ======================================================================
# 规则式优化:常量折叠
# ======================================================================


def _fold_binary(expr: BinaryExpr):
    """对 BinaryExpr 做常量折叠;无法折叠时返回原节点(含已折叠子节点)。

    遵循 SQL 三值逻辑:NULL 参与的比较结果为 NULL(unknown),
    AND/OR 按 三值逻辑 表求值(如 TRUE OR NULL → TRUE)。
    """
    left = constant_fold(expr.left)
    right = constant_fold(expr.right)
    op = expr.op.upper()
    if not (isinstance(left, Literal) and isinstance(right, Literal)):
        return BinaryExpr(expr.line, expr.col, expr.op, left, right)

    lv, rv = left.value, right.value
    if op in _ARITH_OPS:
        if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
            if op == "+":
                result = lv + rv
            else:
                result = lv - rv
            rtype = "FLOAT" if isinstance(result, float) else "INT"
            return Literal(expr.line, expr.col, result, rtype)
    elif op in _COMPARISON_OPS:
        result = _compare(lv, rv, op)
        rtype = BOOL if result is not None else NULL
        return Literal(expr.line, expr.col, result, rtype)
    elif op in _LOGICAL_OPS:
        result = _logic(lv, rv, op)
        rtype = BOOL if result is not None else NULL
        return Literal(expr.line, expr.col, result, rtype)
    return BinaryExpr(expr.line, expr.col, expr.op, left, right)


def _compare(lv, rv, op: str):
    """比较运算;任一操作数为 NULL 时结果为 NULL(unknown)。"""
    if lv is None or rv is None:
        return None
    if op == "=":
        return lv == rv
    if op in ("<>", "!="):
        return lv != rv
    if op == "<":
        return lv < rv
    if op == "<=":
        return lv <= rv
    if op == ">":
        return lv > rv
    if op == ">=":
        return lv >= rv
    raise ValueError("unsupported comparison %s" % op)  # pragma: no cover


def _logic(lv, rv, op: str):
    """AND/OR 三值逻辑(TRUE/FALSE/NULL),与 SQL unknown 语义近似。"""
    if op == "AND":
        if lv is False or rv is False:
            return False
        if lv is True and rv is True:
            return True
        return None
    # OR
    if lv is True or rv is True:
        return True
    if lv is False and rv is False:
        return False
    return None


def constant_fold(expr: Expression) -> Expression:
    """常量折叠:对表达式树中的纯常量子表达式求值(TC-PL-02)。"""
    if isinstance(expr, BinaryExpr):
        return _fold_binary(expr)
    if isinstance(expr, NotExpr):
        operand = constant_fold(expr.operand)
        if isinstance(operand, Literal) and operand.data_type == BOOL:
            if operand.value is None:
                return Literal(expr.line, expr.col, None, NULL)
            return Literal(expr.line, expr.col, not operand.value, BOOL)
        return NotExpr(expr.line, expr.col, operand)
    return expr  # Literal / ColumnRef 原样返回


def _optimize_plan(p: Plan) -> Plan:
    """递归优化单个计划节点(常量折叠作用于 Filter/Delete 谓词)。"""
    if isinstance(p, FilterPlan):
        return FilterPlan(constant_fold(p.predicate), _optimize_plan(p.child))
    if isinstance(p, ProjectPlan):
        return ProjectPlan(p.columns, _optimize_plan(p.child))
    if isinstance(p, DeletePlan) and p.predicate is not None:
        return DeletePlan(p.table, constant_fold(p.predicate))
    return p


def optimize(plans: List[Plan]) -> List[Plan]:
    """对逻辑计划树应用规则式优化(常量折叠),返回优化后的新计划树。"""
    return [_optimize_plan(p) for p in plans]


def optimize_with_diff(plans: List[Plan]):
    """展示优化前后结构差异(TC-PL-02)。

    返回 (optimized_plans, diff_text),diff_text 含 before/after 两棵计划树。
    """
    optimized = optimize(plans)
    lines = ["[before]"]
    for p in plans:
        lines.append(p.tree())
    lines.append("[after constant folding]")
    for p in optimized:
        lines.append(p.tree())
    return optimized, "\n".join(lines)


# ======================================================================
# 表达式打印与对外接口
# ======================================================================


def expr_to_string(expr: Optional[Expression]) -> str:
    """将表达式打印为中缀形式(用于计划展示)。"""
    if expr is None:
        return ""
    if isinstance(expr, Literal):
        if expr.data_type == NULL:
            return "NULL"
        if expr.data_type == BOOL:
            return "TRUE" if expr.value else "FALSE"
        return repr(expr.value)
    if isinstance(expr, ColumnRef):
        return expr.name
    if isinstance(expr, NotExpr):
        return "NOT (%s)" % expr_to_string(expr.operand)
    if isinstance(expr, BinaryExpr):
        return "(%s %s %s)" % (
            expr_to_string(expr.left), expr.op, expr_to_string(expr.right),
        )
    return str(expr)  # pragma: no cover


def plan_tree(plan: Plan) -> str:
    """输出单个计划的树形文本(FR-1.4:输出可为树形结构)。"""
    return plan.tree()


def build(program: Program, catalog: Optional[Catalog] = None) -> List[Plan]:
    """AST → 逻辑执行计划(不做优化)。"""
    return Planner(catalog).build(program)


def plan(ast: Program, catalog: Optional[Catalog] = None) -> List[Plan]:
    """执行计划生成(FR-1.4 / SRS 5.2)。"""
    return build(ast, catalog)

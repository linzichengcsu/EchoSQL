"""执行引擎（FR-3.1 / FR-3.5）。

把 SQL 编译器产出的逻辑执行计划翻译为对存储引擎的实际操作，实现算子：

    CreateTable   建表:注册系统目录并持久化(FR-3.5)
    Insert        行序列化写入数据页,表满自动扩展新页(FR-3.5)
    SeqScan       顺序扫描表的所有数据页(FR-3.1)
    Filter        依据 WHERE 谓词对记录过滤(FR-3.1,含 NULL 三值逻辑)
    Project       依据 SELECT 列清单投影(FR-3.1)
    Delete        定位满足条件的记录并删除(删除标记 + 整页回收,FR-3.5)

表达式求值 eval_expr 遵循 SQL 语义:NULL 参与运算结果为 NULL(unknown),
AND/OR 采用三值逻辑,与编译期常量折叠(planner._logic)一致。
"""

from typing import Any, Dict, List, Optional, Tuple

from sql_compiler import (
    BinaryExpr,
    ColumnRef,
    CreateTablePlan,
    DeletePlan,
    Expression,
    FilterPlan,
    InsertPlan,
    Literal,
    NotExpr,
    Plan,
    ProjectPlan,
    SeqScanPlan,
)
from sql_compiler.catalog import ColumnInfo

from storage import Storage

from .catalog_manager import CatalogManager
from .errors import EngineError
from .storage_engine import RowPage, decode_row

__all__ = ["ExecutionResult", "Executor", "eval_expr"]


class ExecutionResult:
    """一次 SQL 语句的执行结果（FR-3.4 返回执行结果或错误信息）。

    kind: "CREATE" | "INSERT" | "SELECT" | "DELETE"
    columns / rows:  SELECT 结果的表头与数据行
    rows_affected:   INSERT / DELETE 影响行数
    message:         给用户的文本(OK / N row(s) inserted / N row(s) deleted)
    """

    def __init__(
        self,
        kind: str,
        columns: Optional[List[str]] = None,
        rows: Optional[List[list]] = None,
        rows_affected: int = 0,
        message: Optional[str] = None,
    ):
        self.kind = kind
        self.columns = list(columns) if columns else []
        self.rows = [list(r) for r in (rows or [])]
        self.rows_affected = rows_affected
        self.message = message

    # ---------- 输出 ----------

    def to_dict(self) -> dict:
        """JSON 友好表示(供 Web API)。"""
        d = {
            "kind": self.kind,
            "columns": self.columns,
            "rows": self.rows,
            "rows_affected": self.rows_affected,
        }
        if self.message is not None:
            d["message"] = self.message
        return d

    def format(self) -> str:
        """文本格式(供 CLI):SELECT 输出对齐表格,其余输出 message。"""
        if self.kind == "SELECT":
            if not self.columns:
                return "(empty result)"
            widths = [len(str(col)) for col in self.columns]
            for row in self.rows:
                for i, value in enumerate(row):
                    widths[i] = max(widths[i], len(self._cell(value)))
            head = " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(self.columns))
            sep = "-+-".join("-" * w for w in widths)
            lines = [head, sep]
            for row in self.rows:
                lines.append(
                    " | ".join(self._cell(v).ljust(widths[i]) for i, v in enumerate(row))
                )
            return "\n".join(lines)
        return self.message or ""

    @staticmethod
    def _cell(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, float):
            return repr(value)
        return str(value)

    def __repr__(self):
        return "ExecutionResult(kind=%s, rows_affected=%d)" % (
            self.kind, self.rows_affected,
        )


class Executor:
    """逻辑执行计划 -> 存储引擎操作的翻译器。"""

    def __init__(self, storage: Storage, catalog_mgr: CatalogManager):
        self._storage = storage
        self._catalog = catalog_mgr

    # ------------------------------------------------------------------
    # 计划分发（FR-3.1）
    # ------------------------------------------------------------------

    def execute(self, plan: Plan) -> ExecutionResult:
        if isinstance(plan, CreateTablePlan):
            return self._exec_create(plan)
        if isinstance(plan, InsertPlan):
            return self._exec_insert(plan)
        if isinstance(plan, ProjectPlan):
            return self._exec_select(plan)
        if isinstance(plan, SeqScanPlan):
            return self._exec_scan(plan)
        if isinstance(plan, FilterPlan):
            return self._exec_filter(plan)
        if isinstance(plan, DeletePlan):
            return self._exec_delete(plan)
        raise EngineError("unsupported plan %s" % type(plan).__name__)

    # ------------------------------------------------------------------
    # CreateTable / Insert（FR-3.5）
    # ------------------------------------------------------------------

    def _exec_create(self, plan: CreateTablePlan) -> ExecutionResult:
        columns = [ColumnInfo(name, dtype) for name, dtype in plan.columns]
        self._catalog.create_table(plan.table, columns)
        return ExecutionResult("CREATE", message="OK")

    def _exec_insert(self, plan: InsertPlan) -> ExecutionResult:
        table = self._catalog.table_storage(plan.table)
        col_defs = table.columns
        col_index = {c.name.lower(): i for i, c in enumerate(col_defs)}
        full = [None] * len(col_defs)
        for col_name, lit in zip(plan.columns, plan.values):
            key = col_name.lower()
            if key not in col_index:
                raise EngineError("unknown column %r in table %r" % (col_name, table.name))
            full[col_index[key]] = lit.value
        converted = self._coerce(full, col_defs)
        pages_changed = table.insert_row(converted)
        if pages_changed:
            self._catalog.save()
        return ExecutionResult("INSERT", rows_affected=1, message="1 row inserted")

    @staticmethod
    def _coerce(values: List[Any], col_defs: List[ColumnInfo]) -> List[Any]:
        """按列类型把字面量值转换为物理存储值(INT/FLOAT 数值、字符串等)。"""
        out: List[Any] = []
        for value, col in zip(values, col_defs):
            if value is None:
                out.append(None)
            elif col.data_type == "INT":
                out.append(int(value))
            elif col.data_type == "FLOAT":
                out.append(float(value))
            else:  # VARCHAR / CHAR
                out.append(str(value))
        return out

    # ------------------------------------------------------------------
    # SELECT：Project(Filter(SeqScan))（FR-3.1 / FR-3.5）
    # ------------------------------------------------------------------

    def _exec_scan(self, plan: SeqScanPlan) -> ExecutionResult:
        table = self._catalog.table_storage(plan.table)
        rows = [[row.get(c.name.lower()) for c in table.columns]
                for _, row in self._scan_table(plan.table)]
        return ExecutionResult(
            "SELECT", columns=[c.name for c in table.columns], rows=rows,
        )

    def _exec_filter(self, plan: FilterPlan) -> ExecutionResult:
        # 语法上顶层必为 Project；此处防御 Filter 直出全列
        child = self._scan_plan(plan.child)
        table = self._catalog.table_storage(self._scan_table_name(plan.child))
        rows = [[r.get(c.name.lower()) for c in table.columns]
                for rid, r in child if eval_expr(plan.predicate, r, self._catalog) is True]
        return ExecutionResult(
            "SELECT", columns=[c.name for c in table.columns], rows=rows,
        )

    def _exec_select(self, plan: ProjectPlan) -> ExecutionResult:
        rows = self._scan_plan(plan)
        col_names = plan.columns
        out_rows = [[row.get(c.lower()) for c in col_names] for _, row in rows]
        return ExecutionResult("SELECT", columns=col_names, rows=out_rows)

    def _scan_plan(self, plan: Plan) -> List[Tuple[Any, Dict[str, Any]]]:
        """把 Project(Filter(SeqScan)) 子树翻译为 (rid, row_dict) 行列表。"""
        if isinstance(plan, SeqScanPlan):
            return self._scan_table(plan.table)
        if isinstance(plan, FilterPlan):
            out = []
            for rid, row in self._scan_plan(plan.child):
                if eval_expr(plan.predicate, row, self._catalog) is True:
                    out.append((rid, row))
            return out
        if isinstance(plan, ProjectPlan):
            return self._scan_plan(plan.child)
        raise EngineError("unsupported scan plan %s" % type(plan).__name__)

    def _scan_table(self, name: str) -> List[Tuple[Any, Dict[str, Any]]]:
        """SeqScan：迭代访问表的所有数据页（FR-3.1）。"""
        table = self._catalog.table_storage(name)
        out = []
        for page_id, slot, values in table.scan():
            row = {c.name.lower(): v for c, v in zip(table.columns, values)}
            out.append(((page_id, slot), row))
        return out

    @staticmethod
    def _scan_table_name(plan: Plan) -> str:
        if isinstance(plan, SeqScanPlan):
            return plan.table
        if isinstance(plan, FilterPlan):
            return Executor._scan_table_name(plan.child)
        if isinstance(plan, ProjectPlan):
            return Executor._scan_table_name(plan.child)
        raise EngineError("cannot determine table of plan %s" % type(plan).__name__)

    # ------------------------------------------------------------------
    # DELETE（FR-3.5）
    # ------------------------------------------------------------------

    def _exec_delete(self, plan: DeletePlan) -> ExecutionResult:
        table = self._catalog.table_storage(plan.table)
        col_defs = table.columns
        deleted = 0
        pages_changed = False
        for page_id in table.page_ids():
            page = self._storage.get_page(page_id)
            rp = RowPage.decode(page.data)
            if rp.slot_count == 0:
                continue
            for slot in range(rp.slot_count):
                raw = rp.get(slot)
                if raw is None:
                    continue
                values = decode_row(raw)
                row = {c.name.lower(): v for c, v in zip(col_defs, values)}
                if plan.predicate is not None:
                    keep = eval_expr(plan.predicate, row, self._catalog)
                    if keep is not True:
                        continue
                rp.delete(slot)
                deleted += 1
            if rp.active_count == 0:
                # 整页回收：释放页 + 移出页集合（本页已处理完，不会影响迭代）
                table.remove_page(page_id)
                self._storage.invalidate_page(page_id)
                self._storage.release_page(page_id)
                pages_changed = True
            else:
                page.data = rp.encode()
                self._storage.mark_dirty(page_id)
        if pages_changed:
            self._catalog.save()
        message = "1 row deleted" if deleted == 1 else "%d rows deleted" % deleted
        return ExecutionResult("DELETE", rows_affected=deleted, message=message)


# ----------------------------------------------------------------------
# 表达式求值（Filter 谓词 / WHERE 条件）
# ----------------------------------------------------------------------

_COMPARISON_OPS = {"=", "<>", "!=", "<", "<=", ">", ">="}


def eval_expr(expr: Expression, row: Dict[str, Any], catalog=None) -> Any:
    """在给定行上下文下求值表达式,返回 Python 值(NULL 为 None)。

    遵循 SQL 三值逻辑:NULL 参与运算结果为 None(unknown);
    Filter 仅保留结果为 True 的行。
    """
    if isinstance(expr, Literal):
        return expr.value
    if isinstance(expr, ColumnRef):
        return row.get(expr.name.lower())
    if isinstance(expr, NotExpr):
        value = eval_expr(expr.operand, row, catalog)
        return None if value is None else (not value)
    if isinstance(expr, BinaryExpr):
        op = expr.op.upper()
        if op == "AND" or op == "OR":
            left = eval_expr(expr.left, row, catalog)
            right = eval_expr(expr.right, row, catalog)
            return _logic_value(left, right, op)
        left = eval_expr(expr.left, row, catalog)
        right = eval_expr(expr.right, row, catalog)
        if left is None or right is None:
            return None  # NULL 参与运算结果未知
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op in _COMPARISON_OPS:
            return _compare_value(left, right, op)
        raise EngineError("unsupported operator %r" % op)
    raise EngineError("unsupported expression %s" % type(expr).__name__)


def _logic_value(left, right, op: str):
    """AND / OR 三值逻辑(与 planner._logic 一致)。"""
    if op == "AND":
        if left is False or right is False:
            return False
        if left is True and right is True:
            return True
        return None
    # OR
    if left is True or right is True:
        return True
    if left is False and right is False:
        return False
    return None


def _compare_value(left, right, op: str) -> bool:
    if op == "=":
        return left == right
    if op in ("<>", "!="):
        return left != right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    raise EngineError("unsupported comparison %r" % op)  # pragma: no cover

"""规则优化测试（P5：规则优化）。

针对 planner 的规则式优化（常量折叠 Constant Folding + SQL 三值逻辑）做
**系统化**验证，按三层组织：
    A. constant_fold 单元    算术/比较/逻辑/NOT/NULL 的逐规则折叠，
                             含三值逻辑全值表与不可折叠保持
    B. optimize 计划级       优化应用位置（Filter/Delete 谓词、递归子树）、
                             幂等性、无谓词计划不变、diff 展示
    C. 引擎级语义保真       优化前（未折叠执行）与优化后计划执行结果一致，
                             证明优化不改变查询语义（P5 规则优化核心准则）
"""
import os
import sys

# 直接运行(python tests/test_optimizer.py)时也能导入项目根包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from sql_compiler import (
    BOOL,
    NULL,
    Catalog,
    CreateTablePlan,
    DeletePlan,
    FilterPlan,
    InsertPlan,
    Literal,
    ProjectPlan,
    SeqScanPlan,
    analyze,
    build,
    constant_fold,
    lex,
    optimize,
    optimize_with_diff,
    parse,
)
from sql_compiler.ast_nodes import BinaryExpr, ColumnRef, NotExpr

# ----------------------------------------------------------------------
# 构造辅助：行号/列号统一 1:1
# ----------------------------------------------------------------------


def lit(value, dtype="INT"):
    return Literal(1, 1, value, dtype)


def col(name):
    return ColumnRef(1, 1, name)


def bin_(op, left, right):
    return BinaryExpr(1, 1, op, left, right)


def not_(operand):
    return NotExpr(1, 1, operand)


def build_plans(sql: str, catalog: Catalog):
    """辅助：语义分析 + 生成逻辑计划（未优化）。"""
    ast = analyze(parse(lex(sql)), catalog)
    return build(ast, catalog)


def make_catalog():
    cat = Catalog()
    analyze(parse(lex("CREATE TABLE t(a INT, b VARCHAR, c INT);")), cat)
    return cat


# ======================================================================
# A. constant_fold 单元测试
# ======================================================================


def test_fold_arithmetic_add_sub():
    assert constant_fold(bin_("+", lit(1), lit(2))).value == 3
    assert constant_fold(bin_("-", lit(5), lit(2))).value == 3
    # FLOAT 参与 → 结果 FLOAT
    folded = constant_fold(bin_("+", lit(1.5, "FLOAT"), lit(2)))
    assert folded.value == 3.5 and folded.data_type == "FLOAT"
    # 嵌套折叠：((1+2)+3) → 6
    assert constant_fold(bin_("+", bin_("+", lit(1), lit(2)), lit(3))).value == 6


def test_fold_all_comparison_operators():
    """六种比较操作符逐一折叠（planner._compare 全分支）。"""
    cases = [
        ("=", 1, 1, True), ("=", 1, 2, False),
        ("<>", 1, 2, True), ("<>", 1, 1, False),
        ("!=", 1, 2, True), ("!=", 1, 1, False),
        ("<", 1, 2, True), ("<", 2, 1, False),
        ("<=", 2, 2, True), ("<=", 3, 2, False),
        (">", 2, 1, True), (">", 1, 2, False),
        (">=", 2, 2, True), (">=", 1, 2, False),
    ]
    for op, lv, rv, expect in cases:
        folded = constant_fold(bin_(op, lit(lv), lit(rv)))
        assert folded.data_type == BOOL and folded.value is expect, (
            "%s %s %s" % (lv, op, rv)
        )


def test_fold_comparison_strings():
    assert constant_fold(bin_("=", lit("a", "VARCHAR"), lit("a", "VARCHAR"))).value is True
    assert constant_fold(bin_("<>", lit("a", "VARCHAR"), lit("b", "VARCHAR"))).value is True


def test_fold_null_comparison_is_unknown():
    """NULL 参与比较 → NULL（unknown），data_type 为 NULL。"""
    folded = constant_fold(bin_("=", lit(None, "NULL"), lit(1)))
    assert folded.value is None and folded.data_type == NULL
    folded2 = constant_fold(bin_(">", lit(1), lit(None, "NULL")))
    assert folded2.value is None and folded2.data_type == NULL


_AND_EXPECT = {
    (True, True): True, (True, None): None, (True, False): False,
    (None, True): None, (None, None): None, (None, False): False,
    (False, True): False, (False, None): False, (False, False): False,
}
_OR_EXPECT = {
    (True, True): True, (True, None): True, (True, False): True,
    (None, True): True, (None, None): None, (None, False): None,
    (False, True): True, (False, None): None, (False, False): False,
}


@pytest.mark.parametrize("op,expect_table", [
    ("AND", _AND_EXPECT), ("OR", _OR_EXPECT),
])
def test_fold_logic_three_valued_full_table(op, expect_table):
    """AND/OR 三值逻辑全值表：TRUE/NULL/FALSE 共 9 种组合。"""
    for (lv, rv), expect in expect_table.items():
        folded = constant_fold(bin_(op, lit(lv, "BOOL"), lit(rv, "BOOL")))
        # 结果为 unknown（None）时折叠为 NULL 字面量，否则为 BOOL 字面量
        assert folded.data_type == (BOOL if expect is not None else NULL), (
            op, lv, rv
        )
        assert folded.value is expect, "%s %s %s -> %r, want %r" % (
            lv, op, rv, folded.value, expect,
        )


def test_fold_not_three_valued():
    """NOT 折叠：TRUE→FALSE、FALSE→TRUE；NOT NULL 保守保留 NotExpr。"""
    assert constant_fold(not_(lit(True, "BOOL"))).value is False
    assert constant_fold(not_(lit(False, "BOOL"))).value is True
    # 实现仅折叠 BOOL 字面量的 NOT；NOT NULL 保留原表达式（语义不改变）
    folded = constant_fold(not_(lit(None, "NULL")))
    assert isinstance(folded, NotExpr)


def test_fold_nested_not_and_comparison():
    """NOT(1<2) → FALSE（NOT 作用于折叠后的比较结果）。"""
    folded = constant_fold(not_(bin_("<", lit(1), lit(2))))
    assert folded.data_type == BOOL and folded.value is False


def test_fold_keeps_column_refs_untouched():
    """含列引用的子表达式不可折叠，原样保留（不丢失子树）。"""
    expr = bin_("+", col("a"), lit(1))
    folded = constant_fold(expr)
    assert isinstance(folded, BinaryExpr) and folded.op == "+"
    assert isinstance(folded.left, ColumnRef) and folded.left.name == "a"
    # 列引用本身不折叠
    assert constant_fold(col("a")) is not None


def test_fold_not_with_column_kept():
    """NOT(列引用) 不可折叠 → 保留 NotExpr；列引用原样返回。"""
    folded = constant_fold(not_(col("a")))
    assert isinstance(folded, NotExpr)
    assert isinstance(folded.operand, ColumnRef)
    assert isinstance(constant_fold(col("a")), ColumnRef)


def test_fold_partial_keeps_folded_children():
    """部分可折叠：(1+2) 折叠为 3，列比较分支保留。"""
    expr = bin_("AND", bin_("=", lit(1), lit(2)), bin_(">", col("a"), lit(0)))
    folded = constant_fold(expr)
    assert isinstance(folded, BinaryExpr) and folded.op == "AND"
    assert isinstance(folded.left, Literal) and folded.left.value is False
    assert isinstance(folded.right, BinaryExpr) and folded.right.op == ">"


# ======================================================================
# B. optimize 计划级测试
# ======================================================================


def test_optimize_folds_filter_predicate():
    """WHERE 常量部分折叠：1+2=3 → TRUE，列条件保留。"""
    cat = make_catalog()
    ast = analyze(parse(lex("SELECT a FROM t WHERE 1+2=3 AND c>1;")), cat)
    plans = build(ast, cat)
    optimized, diff = optimize_with_diff(plans)
    top = optimized[0]
    assert isinstance(top, ProjectPlan)
    assert isinstance(top.child, FilterPlan)
    pred = top.child.predicate
    assert pred.op == "AND"
    assert isinstance(pred.left, Literal) and pred.left.value is True
    assert pred.right.op == ">"            # c>1 保留（含列）
    assert "[before]" in diff and "[after constant folding]" in diff


def test_optimize_folds_delete_predicate():
    cat = make_catalog()
    ast = analyze(parse(lex("DELETE FROM t WHERE 0<>0;")), cat)
    plans = build(ast, cat)
    optimized = optimize(plans)
    del_plan = optimized[0]
    assert isinstance(del_plan, DeletePlan)
    assert isinstance(del_plan.predicate, Literal)
    assert del_plan.predicate.value is False


def test_optimize_delete_without_where_unchanged():
    cat = make_catalog()
    ast = analyze(parse(lex("DELETE FROM t;")), cat)
    optimized = optimize(build(ast, cat))
    del_plan = optimized[0]
    assert isinstance(del_plan, DeletePlan) and del_plan.predicate is None


def test_optimize_non_predicate_plans_unchanged():
    """无谓词计划（建表/插入）优化后结构等价。"""
    cat = Catalog()
    ast = analyze(parse(lex(
        "CREATE TABLE s(x INT); INSERT INTO s VALUES(1);"
    )), cat)
    before = build(ast, cat)
    after = optimize(before)
    assert [type(p) for p in after] == [CreateTablePlan, InsertPlan]
    # 结构串一致（建表/插入无折叠对象）
    assert after[0].table == "s"
    assert isinstance(after[1], InsertPlan) and after[1].rows[0][0].value == 1


def test_optimize_is_idempotent():
    """优化幂等：二次优化结果与一次优化一致（收敛）。"""
    cat = make_catalog()
    ast = analyze(parse(lex(
        "SELECT a FROM t WHERE 1+2=3 AND c>1 AND 5-5=0;"
    )), cat)
    once = optimize(build(ast, cat))
    twice = optimize(once)
    assert [p.tree() for p in once] == [p.tree() for p in twice]


def test_optimize_recurses_into_project_filter_scan():
    """优化递归进入 Project 子树：Project(Filter(SeqScan)) 结构保留。"""
    cat = make_catalog()
    ast = analyze(parse(lex("SELECT a, b FROM t WHERE 2-2=0;")), cat)
    optimized = optimize(build(ast, cat))
    top = optimized[0]
    assert isinstance(top, ProjectPlan) and top.columns == ["a", "b"]
    assert isinstance(top.child, FilterPlan)
    assert isinstance(top.child.predicate, Literal)
    assert top.child.predicate.value is True
    assert isinstance(top.child.child, SeqScanPlan)


# ======================================================================
# C. 引擎级语义保真（优化不改变查询语义）
# ======================================================================


@pytest.fixture
def db(tmp_path):
    from engine import Database
    database = Database(data_dir=str(tmp_path), log=False)
    yield database
    database.close()


def _seed(db):
    db.execute("CREATE TABLE t(a INT, b VARCHAR, c INT);")
    for i in range(6):
        db.execute("INSERT INTO t VALUES(%d,'v%d',%d);" % (i, i, i % 3))


@pytest.mark.parametrize("cond,expect_rows", [
    ("1+2=3", 6),          # 常量 TRUE → 全行
    ("0=0", 6),
    ("1<>1", 0),           # 常量 FALSE → 无行
    ("NULL=1", 0),         # NULL 比较 → unknown → 无行
    ("NOT 0=0", 0),        # NOT(0=0) = NOT TRUE = FALSE → 无行
    ("2-2=0 AND a>=3", 3), # 部分折叠（a>=3 保留）
    ("1+2=4 OR a<2", 2),   # FALSE OR a<2 → a<2 决定结果
])
def test_constant_conditions_semantics(db, cond, expect_rows):
    """常量 WHERE 谓词执行语义与三值逻辑一致（引擎级）。"""
    _seed(db)
    result = db.execute("SELECT a FROM t WHERE %s;" % cond)
    assert len(result.rows) == expect_rows, cond


def test_optimized_plan_results_match_unoptimized(db):
    """优化后计划的执行结果与直接执行 SQL 完全一致（优化保真）。"""
    _seed(db)
    sql = "SELECT a, b FROM t WHERE 1+2=3 AND c>=1 AND a<5;"
    expected = db.execute(sql)

    ast = analyze(parse(lex(sql)), db.catalog)
    optimized, diff = optimize_with_diff(build(ast, db.catalog))
    actual = db.executor.execute(optimized[0])

    assert actual.columns == expected.columns
    assert actual.rows == expected.rows
    assert "[before]" in diff and "[after constant folding]" in diff


def test_folded_false_filter_returns_empty(db):
    """优化后 Filter(FALSE) 计划执行返回空行集。"""
    _seed(db)
    scan = SeqScanPlan("t")
    false_filter = FilterPlan(lit(False, "BOOL"), scan)
    result = db.executor.execute(false_filter)
    assert result.rows == []
    true_filter = FilterPlan(lit(True, "BOOL"), SeqScanPlan("t"))
    assert len(db.executor.execute(true_filter).rows) == 6


def test_delete_with_constant_true_deletes_all(db):
    """DELETE WHERE 1=1（折叠 TRUE）删除全部行，与无 WHERE 一致。"""
    _seed(db)
    r1 = db.execute("DELETE FROM t WHERE 1=1;")
    assert r1.rows_affected == 6
    assert db.execute("SELECT * FROM t;").rows == []
    # 删空后重建同一张表再验证
    db.drop_table("t")
    _seed(db)
    r2 = db.execute("DELETE FROM t;")
    assert r2.rows_affected == 6


# ======================================================================
# 统一启动方法（P5）：开发者可直接运行本测试模块
#     python tests/test_optimizer.py
#     或编程调用 run_tests()（返回 pytest 退出码，0 = 全部通过）
# ======================================================================


def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本测试模块全部用例。

    用法:
        python tests/test_optimizer.py         # 命令行直接运行
        from runner import run_module          # 或编程调用(所有模块签名一致)
        run_module("tests/test_optimizer.py")
    """
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())

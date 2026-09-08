"""执行计划生成器单元测试(对应测试文档 3.1.4 TC-PL-01 ~ TC-PL-02)。"""
from sql_compiler import (
    Catalog,
    CreateTablePlan,
    DeletePlan,
    FilterPlan,
    InsertPlan,
    ProjectPlan,
    SeqScanPlan,
    analyze,
    constant_fold,
    expr_to_string,
    lex,
    optimize_with_diff,
    parse,
    plan,
    plan_tree,
)
from sql_compiler.ast_nodes import BinaryExpr, ColumnRef, Literal


def build_plans(sql: str, catalog: Catalog):
    """辅助:分析 + 生成逻辑计划。"""
    ast = analyze(parse(lex(sql)), catalog)
    return plan(ast, catalog)


def make_catalog():
    cat = Catalog()
    build_plans("CREATE TABLE t(a INT, b VARCHAR, c INT);", cat)
    return cat


# ---------- TC-PL-01: Project(Filter(SeqScan)) ----------


def test_tc_pl01_select_plan_structure():
    cat = make_catalog()
    plans = build_plans("SELECT a FROM t WHERE c>18;", cat)
    assert len(plans) == 1
    top = plans[0]
    assert isinstance(top, ProjectPlan)
    assert top.columns == ["a"]
    assert isinstance(top.child, FilterPlan)
    assert isinstance(top.child.child, SeqScanPlan)
    assert top.child.child.table == "t"
    # 树形输出包含三层
    tree = plan_tree(top)
    assert "Project" in tree and "Filter" in tree and "SeqScan" in tree


def test_tc_pl01_from_where_select_mapping():
    """FROM→SeqScan、WHERE→Filter、SELECT 列表→Project 的转换原则。"""
    cat = make_catalog()
    top = build_plans("SELECT b FROM t WHERE a=1;", cat)[0]
    assert isinstance(top, ProjectPlan)
    assert isinstance(top.child, FilterPlan)
    assert isinstance(top.child.child, SeqScanPlan)


# ---------- TC-PL-02: 常量折叠与前后差异 ----------


def test_tc_pl02_constant_folding():
    cat = make_catalog()
    plans = build_plans("SELECT a FROM t WHERE c>18 AND 1+2=3;", cat)
    optimized, diff = optimize_with_diff(plans)
    assert "[before]" in diff and "[after constant folding]" in diff
    # 优化后 Filter 谓词:右侧 1+2=3 折叠为 TRUE(左列比较保留)
    folded = optimized[0].child.predicate
    assert folded.op == "AND"
    assert isinstance(folded.left, BinaryExpr) and folded.left.op == ">"
    assert isinstance(folded.right, Literal)
    assert folded.right.data_type == "BOOL" and folded.right.value is True


def test_fold_whole_condition_to_constant():
    """纯常量谓词整体折叠为常量(优化前后差异可直接验证)。"""
    cat = make_catalog()
    plans = build_plans("SELECT a FROM t WHERE 1+2=3;", cat)
    before = plans[0].child.predicate
    optimized, diff = optimize_with_diff(plans)
    # 优化前保留原始常量表达式(中缀展示)
    assert "1 + 2" in expr_to_string(before)
    folded = optimized[0].child.predicate
    assert isinstance(folded, Literal)
    assert folded.data_type == "BOOL" and folded.value is True


def test_fold_arithmetic_and_comparison():
    folded = constant_fold(BinaryExpr(
        1, 1, "+", Literal(1, 1, 1, "INT"), Literal(1, 1, 2, "INT"),
    ))
    assert folded.value == 3


def test_fold_comparison_strings():
    folded = constant_fold(BinaryExpr(
        1, 1, "=", Literal(1, 1, "a", "VARCHAR"), Literal(1, 1, "a", "VARCHAR"),
    ))
    assert folded.data_type == "BOOL" and folded.value is True


def test_fold_keeps_column_refs_untouched():
    folded = constant_fold(BinaryExpr(
        1, 1, "+", ColumnRef(1, 1, "a"), Literal(1, 1, 1, "INT"),
    ))
    assert folded.op == "+"  # 含列引用,不可折叠


def test_fold_not_and_logic_operators():
    from sql_compiler.ast_nodes import NotExpr
    # NOT TRUE → FALSE
    folded = constant_fold(NotExpr(1, 1, Literal(1, 1, True, "BOOL")))
    assert folded.data_type == "BOOL" and folded.value is False
    # TRUE AND FALSE → FALSE
    folded = constant_fold(BinaryExpr(
        1, 1, "AND", Literal(1, 1, True, "BOOL"), Literal(1, 1, False, "BOOL"),
    ))
    assert folded.value is False
    # TRUE OR NULL → TRUE(三值逻辑)
    folded = constant_fold(BinaryExpr(
        1, 1, "OR", Literal(1, 1, True, "BOOL"), Literal(1, 1, None, "NULL"),
    ))
    assert folded.value is True


def test_optimize_folds_delete_predicate():
    cat = make_catalog()
    plans = build_plans("DELETE FROM t WHERE 1+2=3;", cat)
    optimized, diff = optimize_with_diff(plans)
    del_plan = optimized[0]
    assert isinstance(del_plan, DeletePlan)
    assert isinstance(del_plan.predicate, Literal)
    assert del_plan.predicate.value is True
    assert "[before]" in diff and "[after constant folding]" in diff


# ---------- 补充:各语句的计划类型 ----------


def test_create_table_plan():
    cat = Catalog()
    plans = build_plans("CREATE TABLE s(x INT, y VARCHAR);", cat)
    p = plans[0]
    assert isinstance(p, CreateTablePlan)
    assert p.columns == [("x", "INT"), ("y", "VARCHAR")]


def test_insert_plan_with_explicit_columns():
    cat = make_catalog()
    p = build_plans("INSERT INTO t(a, b) VALUES (1, 'x');", cat)[0]
    assert isinstance(p, InsertPlan)
    assert p.columns == ["a", "b"]
    assert [v.value for v in p.values] == [1, "x"]


def test_insert_plan_default_columns_expanded():
    cat = make_catalog()
    p = build_plans("INSERT INTO t VALUES (1, 'x', 3);", cat)[0]
    assert isinstance(p, InsertPlan)
    # 省略列清单时按表定义列序展开
    assert p.columns == ["a", "b", "c"]


def test_select_star_expanded():
    cat = make_catalog()
    p = build_plans("SELECT * FROM t;", cat)[0]
    assert isinstance(p, ProjectPlan)
    assert p.columns == ["a", "b", "c"]


def test_delete_plan():
    cat = make_catalog()
    p = build_plans("DELETE FROM t WHERE a=1;", cat)[0]
    assert isinstance(p, DeletePlan)
    assert p.predicate is not None


def test_delete_plan_without_where():
    cat = make_catalog()
    p = build_plans("DELETE FROM t;", cat)[0]
    assert isinstance(p, DeletePlan)
    assert p.predicate is None


def test_multiple_statements_multiple_plans():
    cat = make_catalog()
    sql = "INSERT INTO t VALUES (1, 'x', 3); SELECT a FROM t WHERE c=1;"
    plans = build_plans(sql, cat)
    assert len(plans) == 2
    assert isinstance(plans[0], InsertPlan)
    assert isinstance(plans[1], ProjectPlan)

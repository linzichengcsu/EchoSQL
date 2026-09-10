"""语法分析器单元测试(对应测试文档 3.1.2 TC-P-01 ~ TC-P-05)。"""
import os
import sys

# 直接运行(python tests/test_parser.py)时也能导入项目根包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from sql_compiler import ParseError, parse, lex
from sql_compiler.ast_nodes import (
    BinaryExpr,
    ColumnDef,
    CreateTableStmt,
    DeleteStmt,
    InsertStmt,
    NotExpr,
    Program,
    SelectStmt,
)

# ---------- TC-P-01: 建表 AST ----------


def test_tc_p01_create_table_ast():
    ast = parse(lex("CREATE TABLE t(a INT, b VARCHAR);"))
    assert len(ast.statements) == 1
    stmt = ast.statements[0]
    assert isinstance(stmt, CreateTableStmt)
    assert stmt.table == "t"
    assert [c.name for c in stmt.columns] == ["a", "b"]
    assert [c.data_type for c in stmt.columns] == ["INT", "VARCHAR"]
    assert isinstance(stmt.columns[0], ColumnDef)


# ---------- TC-P-02: SELECT 含 WHERE ----------


def test_tc_p02_select_with_where():
    ast = parse(lex("SELECT * FROM t WHERE a=1;"))
    stmt = ast.statements[0]
    assert isinstance(stmt, SelectStmt)
    assert stmt.table == "t"
    assert stmt.where is not None
    assert isinstance(stmt.where, BinaryExpr)
    assert stmt.where.op == "="


# ---------- TC-P-03: AND 优先级高于 OR ----------


def test_tc_p03_and_binds_tighter_than_or():
    ast = parse(lex("SELECT a FROM t WHERE a=1 OR b=2 AND c=3;"))
    where = ast.statements[0].where
    assert isinstance(where, BinaryExpr)
    assert where.op == "OR"
    assert where.left.op == "=" and where.left.left.name == "a"
    # 右操作数必须是 AND(b=2 AND c=3),体现 AND 优先于 OR
    assert isinstance(where.right, BinaryExpr)
    assert where.right.op == "AND"
    assert where.right.left.left.name == "b"
    assert where.right.right.left.name == "c"


def test_not_binds_tighter_than_and():
    ast = parse(lex("SELECT a FROM t WHERE NOT a=1 AND b=2;"))
    where = ast.statements[0].where
    assert where.op == "AND"
    assert isinstance(where.left, NotExpr)
    assert where.left.operand.op == "="


def test_parentheses_override_precedence():
    ast = parse(lex("SELECT a FROM t WHERE (a=1 OR b=2) AND c=3;"))
    where = ast.statements[0].where
    assert where.op == "AND"
    assert where.left.op == "OR"


# ---------- TC-P-04: 表达式缺失操作数 ----------


def test_tc_p04_missing_operand_after_and():
    with pytest.raises(ParseError) as ei:
        parse(lex("SELECT a FROM t WHERE age>18 AND ;"))
    msg = str(ei.value)
    # 报错:位置 + 期望 IDENTIFIER/CONST/'('/', NOT
    assert "IDENTIFIER" in msg
    assert "NOT" in msg
    assert "[ParseError," in msg
    assert ei.value.line == 1


# ---------- TC-P-05: 缺分号 / 括号不匹配 ----------


def test_tc_p05_missing_semicolon():
    with pytest.raises(ParseError) as ei:
        parse(lex("CREATE TABLE t(a INT)"))
    assert "expected ';'" in str(ei.value)


def test_tc_p05_unbalanced_parenthesis():
    with pytest.raises(ParseError) as ei:
        parse(lex("SELECT a FROM t WHERE (a=1;"))
    assert "expected ')'" in str(ei.value)


# ---------- 补充:INSERT / DELETE / 多语句 / 空输入 ----------


def test_insert_with_column_list():
    ast = parse(lex("INSERT INTO t(a, b) VALUES (1, 'x');"))
    stmt = ast.statements[0]
    assert isinstance(stmt, InsertStmt)
    assert stmt.table == "t"
    assert stmt.columns == ["a", "b"]
    assert [v.value for v in stmt.rows[0]] == [1, "x"]


def test_insert_without_column_list():
    ast = parse(lex("INSERT INTO t VALUES (1, 'x');"))
    stmt = ast.statements[0]
    assert stmt.columns is None
    assert len(stmt.rows) == 1
    assert len(stmt.rows[0]) == 2


def test_insert_multi_row_values():
    """单条 INSERT 可带多行 VALUES（grammar.md §2）。"""
    ast = parse(lex("INSERT INTO t(a, b) VALUES (1, 'x'), (2, 'y'), (3, 'z');"))
    stmt = ast.statements[0]
    assert isinstance(stmt, InsertStmt)
    assert len(stmt.rows) == 3
    assert [[v.value for v in row] for row in stmt.rows] == [[1, "x"], [2, "y"], [3, "z"]]


def test_insert_multi_row_without_column_list():
    ast = parse(lex("INSERT INTO t VALUES (1, 'x'), (2, 'y');"))
    stmt = ast.statements[0]
    assert stmt.columns is None
    assert [[v.value for v in row] for row in stmt.rows] == [[1, "x"], [2, "y"]]


def test_insert_multi_row_missing_row_rejected():
    """多行 VALUES 中缺括号的畸形行仍被语法拒绝。"""
    with pytest.raises(ParseError):
        parse(lex("INSERT INTO t VALUES (1, 'x'), 2, 'y';"))


def test_delete_with_where():
    ast = parse(lex("DELETE FROM t WHERE id=1;"))
    stmt = ast.statements[0]
    assert isinstance(stmt, DeleteStmt)
    assert stmt.table == "t"
    assert stmt.where.op == "="


def test_delete_without_where():
    ast = parse(lex("DELETE FROM t;"))
    assert ast.statements[0].where is None


def test_program_multiple_statements():
    sql = "CREATE TABLE t(a INT); INSERT INTO t VALUES (1); SELECT * FROM t;"
    ast = parse(lex(sql))
    assert isinstance(ast, Program)
    assert len(ast.statements) == 3


def test_empty_program():
    ast = parse(lex(""))
    assert isinstance(ast, Program)
    assert ast.statements == []


def test_keyword_case_insensitive_in_parser():
    ast = parse(lex("create table t (a int); select * from t;"))
    assert isinstance(ast.statements[0], CreateTableStmt)
    assert ast.statements[0].table == "t"


# ======================================================================
# 统一启动方法（P5）：开发者可直接运行本测试模块
#     python tests/test_parser.py
#     或编程调用 run_tests()（返回 pytest 退出码，0 = 全部通过）
# ======================================================================


def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本测试模块全部用例。

    用法:
        python tests/test_parser.py           # 命令行直接运行
        from runner import run_module         # 或编程调用(所有模块签名一致)
        run_module("tests/test_parser.py")
    """
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())

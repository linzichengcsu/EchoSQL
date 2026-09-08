"""语法分析器单元测试(对应测试文档 3.1.2 TC-P-01 ~ TC-P-05)。"""
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
    assert [v.value for v in stmt.values] == [1, "x"]


def test_insert_without_column_list():
    ast = parse(lex("INSERT INTO t VALUES (1, 'x');"))
    stmt = ast.statements[0]
    assert stmt.columns is None
    assert len(stmt.values) == 2


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

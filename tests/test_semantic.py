"""语义分析器单元测试(对应测试文档 3.1.3 TC-S-01 ~ TC-S-05)。"""
import os
import sys

# 直接运行(python tests/test_semantic.py)时也能导入项目根包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from sql_compiler import (
    ColumnCountMismatch,
    SemanticError,
    TableAlreadyExists,
    TypeMismatch,
    UnknownColumn,
    UnknownTable,
    analyze,
    lex,
    parse,
)
from sql_compiler.catalog import Catalog


def compile_program(sql: str, catalog: Catalog = None):
    """辅助:词法 + 语法 + 语义 全流程。"""
    return analyze(parse(lex(sql)), catalog)


@pytest.fixture
def catalog():
    cat = Catalog()
    compile_program("CREATE TABLE t(a INT, b VARCHAR, c FLOAT);", cat)
    return cat


# ---------- TC-S-01: 列不存在 ----------


def test_tc_s01_unknown_column(catalog):
    with pytest.raises(UnknownColumn) as ei:
        compile_program("SELECT score FROM t;", catalog)
    assert "column 'score' does not exist" in str(ei.value)
    assert "UnknownColumn" in str(ei.value)


# ---------- TC-S-02: INSERT 值数量 ≠ 列数 ----------


def test_tc_s02_column_count_mismatch(catalog):
    with pytest.raises(ColumnCountMismatch) as ei:
        compile_program("INSERT INTO t(a, b) VALUES (1);", catalog)
    assert "INSERT has 1 values but 2 columns" in str(ei.value)


# ---------- TC-S-03: 类型不匹配 ----------


def test_tc_s03_type_mismatch(catalog):
    with pytest.raises(TypeMismatch) as ei:
        compile_program("INSERT INTO t(a, b) VALUES ('Alice', 1);", catalog)
    msg = str(ei.value)
    assert "TypeMismatch" in msg
    assert "INT" in msg and "VARCHAR" in msg


# ---------- TC-S-04: 运算符类型不匹配 ----------


def test_tc_s04_operator_type_mismatch(catalog):
    with pytest.raises(TypeMismatch) as ei:
        compile_program("SELECT a FROM t WHERE a+'abc'>20;", catalog)
    assert "operator + cannot be applied to INT and VARCHAR" in str(ei.value)


# ---------- TC-S-05: 重复建表 ----------


def test_tc_s05_table_already_exists(catalog):
    with pytest.raises(TableAlreadyExists) as ei:
        compile_program("CREATE TABLE t(x INT);", catalog)
    assert "already exists" in str(ei.value)


# ---------- 补充:表不存在 / WHERE 非布尔 / 合法语句 / NULL ----------


def test_unknown_table():
    cat = Catalog()
    with pytest.raises(UnknownTable):
        compile_program("SELECT * FROM nosuch;", cat)


def test_where_must_be_boolean(catalog):
    with pytest.raises(TypeMismatch) as ei:
        compile_program("SELECT a FROM t WHERE a;", catalog)
    assert "WHERE condition must be boolean" in str(ei.value)


def test_and_requires_boolean(catalog):
    with pytest.raises(TypeMismatch):
        compile_program("SELECT a FROM t WHERE a AND b;", catalog)


def test_null_insertable_anywhere(catalog):
    # NULL 可插入任意类型列
    compile_program("INSERT INTO t VALUES (NULL, NULL, NULL);", catalog)


def test_valid_statement_passes(catalog):
    # 合法 INSERT 与 SELECT 不应抛错
    compile_program("INSERT INTO t VALUES (1, 'Alice', 1.5);", catalog)
    compile_program("SELECT * FROM t WHERE a>=1 AND b='x';", catalog)
    compile_program("DELETE FROM t WHERE c<2.0;", catalog)


def test_float_into_int_column(catalog):
    # 数值兼容:INT 列可赋 FLOAT 值
    compile_program("INSERT INTO t(a) VALUES (1.5);", catalog)


def test_catalog_query_interfaces(catalog):
    """Catalog 的 findTable / findColumn / getType / createTable 接口可用。"""
    info = catalog.find_table("t")
    assert info is not None and info.name == "t"
    assert [c.name for c in info.columns] == ["a", "b", "c"]
    assert catalog.get_type("t", "b") == "VARCHAR"
    assert catalog.find_column("t", "a").data_type == "INT"
    assert catalog.find_table("t") is not None  # 精确匹配可查
    assert catalog.find_table("T") is None  # 大小写敏感:不同大小写视为不同名字


def test_error_positions(catalog):
    with pytest.raises(UnknownColumn) as ei:
        compile_program("SELECT * FROM t WHERE nope=1;", catalog)
    assert ei.value.line == 1
    # 错误统一可被 SemanticError 基类捕获
    try:
        compile_program("SELECT * FROM t WHERE nope=1;", catalog)
    except SemanticError:
        pass


# ======================================================================
# 统一启动方法（P5）：开发者可直接运行本测试模块
#     python tests/test_semantic.py
#     或编程调用 run_tests()（返回 pytest 退出码，0 = 全部通过）
# ======================================================================


def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本测试模块全部用例。

    用法:
        python tests/test_semantic.py         # 命令行直接运行
        from runner import run_module         # 或编程调用(所有模块签名一致)
        run_module("tests/test_semantic.py")
    """
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())

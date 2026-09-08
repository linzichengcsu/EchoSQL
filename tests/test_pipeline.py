"""编译流水线测试(对应 SRS FR-1.5:Token 流 → AST → 语义检查 → 执行计划)。"""
import os
import sys

# 直接运行(python tests/test_pipeline.py)时也能导入项目根包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from sql_compiler import (
    SQLError,
    Catalog,
    LexError,
    ParseError,
    SemanticError,
    lex,
    pipeline,
)
from sql_compiler.ast_nodes import CreateTableStmt, InsertStmt, SelectStmt


def test_pipeline_outputs_all_stages():
    """正确 SQL:依次输出 Token 流、AST、语义检查结果、执行计划。"""
    cat = Catalog()
    result = pipeline("CREATE TABLE t(a INT); INSERT INTO t VALUES (1);", cat)
    # Token 流
    assert len(result.tokens) > 0 and result.tokens[-1].type.name == "EOF"
    # AST 含两条语句
    assert len(result.ast.statements) == 2
    assert isinstance(result.ast.statements[0], CreateTableStmt)
    assert isinstance(result.ast.statements[1], InsertStmt)
    # 执行计划
    assert len(result.plans) == 2
    # 字符串化输出包含三个阶段
    text = str(result)
    assert "Token" in text and "AST" in text and "执行计划" in text


def test_pipeline_error_stage_lexer():
    """词法错误在词法阶段抛出,不进入后续阶段。"""
    with pytest.raises(LexError):
        pipeline("'unclosed", Catalog())


def test_pipeline_error_stage_parser():
    with pytest.raises(ParseError):
        pipeline("CREATE TABLE t(a INT)", Catalog())


def test_pipeline_error_stage_semantic():
    cat = Catalog()
    pipeline("CREATE TABLE t(a INT);", cat)
    with pytest.raises(SemanticError):
        pipeline("SELECT nope FROM t;", cat)


def test_pipeline_never_crashes_on_bad_input():
    """非法输入均以 SQLError 抛出,不产生未捕获的系统异常。"""
    bad_inputs = [
        "",
        "   ",
        "@@@",
        "SELECT",
        "SELECT *",
        "SELECT * FROM",
        "INSERT INTO",
        "CREATE TABLE t(",
        "DELETE",
        "SELECT 'abc;",
        "SELECT * FROM t WHERE ;",
    ]
    cat = Catalog()
    for sql in bad_inputs:
        try:
            pipeline(sql, cat)
        except SQLError:
            pass  # 期望所有非法输入都以编译错误形式拒绝


def test_lex_parse_matching_srs_interfaces():
    """SRS 5.2 内部接口:lex(sql) / parse(tokens) 可直接调用。"""
    tokens = lex("SELECT a FROM t;")
    from sql_compiler import parse
    ast = parse(tokens)
    assert len(ast.statements) == 1
    assert isinstance(ast.statements[0], SelectStmt)


# ======================================================================
# 统一启动方法（P5）：开发者可直接运行本测试模块
#     python tests/test_pipeline.py
#     或编程调用 run_tests()（返回 pytest 退出码，0 = 全部通过）
# ======================================================================


def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本测试模块全部用例。

    用法:
        python tests/test_pipeline.py         # 命令行直接运行
        from runner import run_module         # 或编程调用(所有模块签名一致)
        run_module("tests/test_pipeline.py")
    """
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())

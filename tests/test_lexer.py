"""词法分析器单元测试(对应测试文档 3.1.1 TC-L-01 ~ TC-L-06)。"""
import os
import sys

# 直接运行(python tests/test_lexer.py)时也能导入项目根包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from sql_compiler import LexError, lex
from sql_compiler.tokens import TokenType

# ---------- TC-L-01: 正确 Token 流含位置 ----------


def test_tc_l01_token_stream_with_position():
    tokens = lex("SELECT name FROM student WHERE age>=18;")
    types = [t.type for t in tokens]
    assert TokenType.KEYWORD in types
    assert TokenType.IDENTIFIER in types
    assert TokenType.GE in types
    assert TokenType.SEMICOLON in types
    # 位置:第一个 token SELECT 位于 (1,1)
    assert tokens[0].type is TokenType.KEYWORD
    assert (tokens[0].line, tokens[0].col) == (1, 1)
    # age 的位置:SELECT(1-6) name(8-11) FROM(13-16) student(18-24) WHERE(26-30) age(32-34)
    age = [t for t in tokens if t.lexeme == "age"][0]
    assert (age.line, age.col) == (1, 32)
    assert tokens[-1].type is TokenType.EOF


# ---------- TC-L-02: 关键字大小写不敏感 ----------


def test_tc_l02_keyword_case_insensitive():
    for sql in ("select", "SELECT", "SeLeCt"):
        tokens = lex(sql)
        assert tokens[0].type is TokenType.KEYWORD
        assert tokens[0].lexeme.upper() == "SELECT"


# ---------- TC-L-03: 字符串转义,内容保持原样 ----------


def test_tc_l03_string_escape_kept():
    tokens = lex("'Tom''s book'")
    assert tokens[0].type is TokenType.STRING
    assert tokens[0].lexeme == "Tom's book"


def test_string_content_kept_verbatim():
    tokens = lex("'  Alice Smith  '")
    assert tokens[0].lexeme == "  Alice Smith  "


# ---------- TC-L-04: 多字符运算符 ----------


def test_tc_l04_multi_char_operators():
    tokens = lex("age >= 18")
    ops = [t for t in tokens if t.type in (TokenType.GE, TokenType.GT, TokenType.EQ)]
    assert [t.type for t in ops] == [TokenType.GE]
    # <> 与 != 均识别为 NE
    assert lex("a <> b")[1].type is TokenType.NE
    assert lex("a != b")[1].type is TokenType.NE


# ---------- TC-L-05: 未闭合字符串 ----------


def test_tc_l05_unterminated_string():
    with pytest.raises(LexError) as ei:
        lex("'Alice")
    err = ei.value
    assert "unterminated string" in str(err)
    assert err.line == 1 and err.col == 1
    # 错误可被 str 化,格式 [LexError, 行:列, 原因]
    assert str(err).startswith("[LexError, 1:1,")


# ---------- TC-L-06: 非法字符 ----------


def test_tc_l06_illegal_characters():
    with pytest.raises(LexError) as ei:
        lex("SELECT @#$")
    err = ei.value
    assert "unexpected character" in str(err)
    assert err.line == 1 and err.col == 8  # @ 位于第 8 列


# ---------- 补充:注释 / 非法数字 / 多语句 / 换行 ----------


def test_comments_skipped():
    sql = """-- 行注释
SELECT 1; /* 块注释
跨行 */ SELECT 2;"""
    tokens = lex(sql)
    ints = [t for t in tokens if t.type is TokenType.INT_CONST]
    assert [t.lexeme for t in ints] == ["1", "2"]


def test_unterminated_block_comment():
    with pytest.raises(LexError) as ei:
        lex("SELECT 1 /* 未闭合")
    assert "unterminated block comment" in str(ei.value)


def test_invalid_number_letter():
    with pytest.raises(LexError) as ei:
        lex("SELECT 12abc")
    assert "invalid number" in str(ei.value)
    assert ei.value.col == 8


def test_invalid_number_triple_dot():
    with pytest.raises(LexError):
        lex("SELECT 1.2.3")


def test_float_const():
    tokens = lex("3.14")
    assert tokens[0].type is TokenType.FLOAT_CONST
    assert tokens[0].lexeme == "3.14"


def test_multi_statement_with_newlines():
    tokens = lex("SELECT 1;\nSELECT 2;")
    semicolons = [t for t in tokens if t.type is TokenType.SEMICOLON]
    assert len(semicolons) == 2
    # 第二句 SELECT 所在行号为 2
    selects = [t for t in tokens if t.is_keyword("SELECT")]
    assert selects[1].line == 2


def test_empty_input_yields_eof():
    tokens = lex("")
    assert len(tokens) == 1 and tokens[0].type is TokenType.EOF


# ======================================================================
# 统一启动方法（P5）：开发者可直接运行本测试模块
#     python tests/test_lexer.py
#     或编程调用 run_tests()（返回 pytest 退出码，0 = 全部通过）
# ======================================================================


def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本测试模块全部用例。

    用法:
        python tests/test_lexer.py            # 命令行直接运行
        from runner import run_module         # 或编程调用(所有模块签名一致)
        run_module("tests/test_lexer.py")
    """
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())

"""边界测试（P5：边界测试 / 系统测试）。

覆盖 README P5「测试与优化」中的边界维度，按层组织：
    A. 编译器边界    超长输入、字符串/数字/注释边界、深度嵌套、空程序
    B. 存储边界      缓存容量/策略参数、容量退化、页大小边界
    C. 引擎边界      空库/空表、行大小上限、INT 32 位范围、跨页大量行、
                     脚本与名称边界、INT 溢出拒绝（缺陷 #1 修复验证）
    D. Web 边界      非 JSON 请求、空 SQL、INT 溢出 400、统计与未知端点

原则：非法输入一律抛出**项目定义的错误类型**（LexError / ParseError /
SemanticError / SQLError / EngineError 等），不产生 struct.error 等
未定义异常崩溃（FR 健壮性）。
"""
import os
import sys

# 直接运行(python tests/test_boundary.py)时也能导入项目根包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from sql_compiler import (
    Catalog,
    LexError,
    ParseError,
    SQLError,
    analyze,
    lex,
    parse,
    pipeline,
)
from sql_compiler.ast_nodes import BinaryExpr
from sql_compiler.tokens import TokenType


def compile_program(sql: str, catalog: Catalog = None):
    """辅助：词法 + 语法 + 语义 全流程。"""
    return analyze(parse(lex(sql)), catalog)


# ======================================================================
# A. 编译器边界（词法 / 语法 / 语义 / 流水线）
# ======================================================================


def test_lexer_huge_identifier_no_crash():
    """超长标识符（10 万字符）词法不崩溃。"""
    tokens = lex("a" * 100_000)
    assert tokens[0].type is TokenType.IDENTIFIER
    assert len(tokens[0].lexeme) == 100_000
    assert tokens[-1].type is TokenType.EOF


def test_lexer_many_statements_no_crash():
    """数百条语句拼接后词法分析不崩溃。"""
    tokens = lex("SELECT * FROM t;" * 300)
    semicolons = [t for t in tokens if t.type is TokenType.SEMICOLON]
    assert len(semicolons) == 300


def test_lexer_string_boundaries():
    """字符串边界：空串、转义单引号、含分号/换行/中文。"""
    assert lex("''")[0].lexeme == ""
    assert lex("''''")[0].lexeme == "'"
    assert lex("';'")[0].lexeme == ";"
    assert lex("'a\nb'")[0].lexeme == "a\nb"          # 字符串内换行保持原样
    assert lex("'中文'")[0].lexeme == "中文"
    # 超长字符串（5000 字符）词法不崩溃
    tokens = lex("'" + "x" * 5000 + "'")
    assert tokens[0].lexeme == "x" * 5000


def test_lexer_float_forms_from_grammar():
    """文法 §1.2.5 承诺的浮点形式（缺陷 #2 修复验证）。"""
    for sql, lexeme in ((".5", ".5"), ("1.", "1."), ("1.5", "1.5"), ("3.14", "3.14")):
        tok = lex(sql)[0]
        assert tok.type is TokenType.FLOAT_CONST, sql
        assert tok.lexeme == lexeme


def test_lexer_float_illegal_still_rejected():
    """非法数字仍按文法拒绝（不因浮点扩展回归）。"""
    for sql in ("12abc", "1.2.3", ".5.6", "1..2"):
        with pytest.raises(LexError):
            lex(sql)


def test_lexer_big_integer_tokenizes():
    """超长整数字面量可词法化（引擎层再拒绝，见 C 组）。"""
    tok = lex("99999999999999999999")[0]
    assert tok.type is TokenType.INT_CONST
    assert tok.lexeme == "99999999999999999999"


def test_lexer_empty_comment_forms():
    """空注释 /**/ 与裸 -- 不报错。"""
    tokens = lex("/**/ SELECT 1; -- 行尾")
    assert any(t.is_keyword("SELECT") for t in tokens)


def test_parser_deep_parentheses():
    """50 层括号嵌套不崩溃，WHERE 仍可解析。"""
    depth = 50
    sql = "SELECT a FROM t WHERE " + "(" * depth + "a=1" + ")" * depth + ";"
    ast = parse(lex(sql))
    where = ast.statements[0].where
    assert isinstance(where, BinaryExpr)
    assert where.op == "="


def test_parser_long_or_chain():
    """长 OR 链（100 项）解析正确且不崩溃。"""
    cond = " OR ".join(["a=%d" % i for i in range(100)])
    ast = parse(lex("SELECT a FROM t WHERE %s;" % cond))
    node = ast.statements[0].where
    assert isinstance(node, BinaryExpr) and node.op == "OR"


def test_pipeline_empty_and_semicolons():
    """空输入：程序为空且不崩溃；孤立分号在语法层被拒绝。"""
    for sql in ("", "   "):
        result = pipeline(sql, Catalog())
        assert len(result.ast.statements) == 0
        assert result.plans == []
    # 孤立分号 / 连续分号不能作为语句起始（语法层拒绝，Database 入口同样拒绝）
    for sql in (";", ";;;"):
        with pytest.raises(ParseError):
            pipeline(sql, Catalog())


def test_pipeline_all_error_kinds_are_sqlerror():
    """各类非法输入的异常均为 SQLError 子类（词法/语法/语义）。"""
    cat = Catalog()
    compile_program("CREATE TABLE t(a INT);", cat)
    bad = [
        ("'unclosed", LexError),                       # 词法
        ("CREATE TABLE t(a INT)", ParseError),         # 语法（缺分号）
        ("SELECT nope FROM t;", SQLError),             # 语义（未知列）
    ]
    for sql, kind in bad:
        with pytest.raises(kind):
            pipeline(sql, cat)


def test_parser_keyword_as_identifier_rejected():
    """保留字作表名/列名应被语法拒绝，而非崩溃。"""
    with pytest.raises(ParseError):
        parse(lex("CREATE TABLE select(a INT);"))


# ======================================================================
# B. 存储边界（缓存参数 / 容量退化）
# ======================================================================


def test_bufferpool_rejects_invalid_capacity(tmp_path):
    from storage import BufferPool, FileManager
    fm = FileManager(str(tmp_path))
    for bad in (0, -1, -5):
        with pytest.raises(ValueError):
            BufferPool(fm, capacity=bad)
    fm.close()


def test_bufferpool_rejects_invalid_policy(tmp_path):
    from storage import BufferPool, FileManager
    fm = FileManager(str(tmp_path))
    with pytest.raises(ValueError):
        BufferPool(fm, capacity=2, policy="CLOCK")
    fm.close()


def test_bufferpool_capacity_one_degrades(tmp_path):
    """容量为 1 时访问两页即触发逐出，命中率统计正确。"""
    from storage import BufferPool, FileManager
    fm = FileManager(str(tmp_path))
    bp = BufferPool(fm, capacity=1, policy="LRU")
    p1 = fm.allocate_page()
    p2 = fm.allocate_page()
    bp.get_page(p1)            # miss
    bp.get_page(p2)            # miss + 逐出 p1
    bp.get_page(p1)            # miss（p1 已被逐出）+ 逐出 p2
    assert bp.misses == 3 and bp.hits == 0
    assert bp.evictions == 2
    assert bp.cached_page_ids() == [p1]
    fm.close()


def test_page_size_exact_boundary(tmp_path):
    """恰好 4KB 数据可整页写入；超 1 字节被拒绝（不崩溃）。"""
    from storage import DataTooLarge, FileManager, PAGE_SIZE
    fm = FileManager(str(tmp_path))
    pid = fm.allocate_page()
    fm.write_page(pid, b"x" * PAGE_SIZE)          # 恰好一页
    assert fm.read_page(pid) == b"x" * PAGE_SIZE
    with pytest.raises(DataTooLarge):
        fm.write_page(pid, b"x" * (PAGE_SIZE + 1))
    fm.close()


# ======================================================================
# C. 引擎边界
# ======================================================================


@pytest.fixture
def db(tmp_path):
    from engine import Database
    database = Database(data_dir=str(tmp_path), log=False)
    yield database
    database.close()


def test_empty_database_initial_state(db):
    """全新空库：无表、统计为空、空输入返回 None。"""
    assert db.tables() == []
    assert db.stats()["tables"] == 0
    assert db.execute("") is None
    assert db.execute("   ") is None
    # 孤立分号 / 多余分号不再宽容为空输入（缺陷 #4 修复）：语法层拒绝
    from sql_compiler import ParseError
    for bad in (";", ";;", ";;;"):
        with pytest.raises(ParseError):
            db.execute(bad)
    assert db.execute_script("") == []
    with pytest.raises(ParseError):
        db.execute_script(";;;")


def test_select_empty_table_keeps_columns(db):
    """空表 SELECT：列头保留，行集为空。"""
    db.execute("CREATE TABLE t(a INT, b VARCHAR);")
    result = db.execute("SELECT * FROM t;")
    assert result.columns == ["a", "b"]
    assert result.rows == []


def test_row_size_upper_bound_single_varchar(db):
    """单 VARCHAR 列：4080 字符可存（≤页载荷上限），4090 字符拒绝。"""
    from engine import RowTooLarge
    db.execute("CREATE TABLE t(b VARCHAR);")
    ok = db.execute("INSERT INTO t VALUES('%s');" % ("x" * 4080))
    assert ok.rows_affected == 1
    assert len(db.execute("SELECT b FROM t;").rows[0][0]) == 4080
    with pytest.raises(RowTooLarge):
        db.execute("INSERT INTO t VALUES('%s');" % ("x" * 4090))


def test_string_value_hard_limit_65535():
    """单字符串值超过 65535 字节（VARCHAR 长度字段上限）被拒绝。"""
    from engine import RowTooLarge, encode_row
    with pytest.raises(RowTooLarge):
        encode_row(["x" * 70_000])
    # 单页容量内的普通长串可正常编码（tag 1 + 长度 2 + 内容）
    assert len(encode_row(["x" * 4000])) == 4003


def test_int_32bit_range_boundary(db):
    """INT 32 位范围：上限可存取，超界拒绝（缺陷 #1 修复验证）。

    注：文法 §2/§3 的 literal 不支持一元负号，INT 下界值无法以
    负字面量书写，属语法层限制（见下），此处验证上界与溢出拒绝。
    """
    from engine import RowTooLarge
    db.execute("CREATE TABLE i(a INT);")
    db.execute("INSERT INTO i VALUES(2147483647);")
    assert db.execute("SELECT a FROM i;").rows == [[2147483647]]
    # 文法限制：负数字面量（如 -2147483648）不被语法支持，安全拒绝
    with pytest.raises(ParseError):
        db.execute("INSERT INTO i VALUES(-1);")
    # 32 位溢出：引擎层以 RowTooLarge（EngineError 子类）拒绝，不崩溃
    for bad in (2147483648, 99999999999):
        with pytest.raises(RowTooLarge):
            db.execute("INSERT INTO i VALUES(%d);" % bad)


def test_bulk_rows_span_multiple_pages(db):
    """500 行数据跨多页存储，全部可查回（FR-3.2 表扩展）。"""
    db.execute("CREATE TABLE t(id INT, v VARCHAR);")
    for i in range(500):
        db.execute("INSERT INTO t VALUES(%d,'row-%d');" % (i, i))
    rows = db.execute("SELECT id FROM t;").rows
    assert len(rows) == 500
    assert rows[0] == [0] and rows[-1] == [499]
    infos = db.table_infos()
    assert len(infos[0]["pages"]) >= 2             # 至少跨两页


def test_chinese_and_escaped_string_roundtrip(db):
    """超长中文与转义串入库后可原样查回。"""
    chinese = "数据库管理系统" * 80            # 640 字 ≈ 1920 UTF-8 字节，可单行存放
    db.execute("CREATE TABLE t(name VARCHAR);")
    db.execute("INSERT INTO t VALUES('%s');" % chinese)
    db.execute("INSERT INTO t VALUES('a''b');")
    rows = db.execute("SELECT name FROM t;").rows
    assert rows[0] == [chinese]
    assert rows[1] == ["a'b"]


def test_script_with_errors_preserves_side_effects(db):
    """execute_script：多语句中出错即抛，已生效语句副作用保留。"""
    db.execute("CREATE TABLE t(a INT);")
    db.execute_script("INSERT INTO t VALUES(1); INSERT INTO t VALUES(2);")
    with pytest.raises(SQLError):
        db.execute_script("INSERT INTO t VALUES(3); SELECT nope FROM t;")
    # 第三条已插入，前两条也在
    assert len(db.execute("SELECT a FROM t;").rows) == 3


def test_drop_nonexistent_table_is_safe(db):
    """删除不存在的表返回 0，重复删除同样安全。"""
    assert db.drop_table("ghost") == 0
    assert db.drop_table("ghost") == 0
    db.execute("CREATE TABLE t(a INT);")
    db.execute("INSERT INTO t VALUES(1);")
    assert db.drop_table("t") == 1                  # 回收 1 个数据页
    assert db.drop_table("t") == 0
    # 同名表可重建
    db.execute("CREATE TABLE t(a INT);")
    assert "t" in db.tables()


def test_identifier_with_underscore_and_digits(db):
    """含下划线/数字的表名与列名可用。"""
    db.execute("CREATE TABLE t_1(col_2 INT, c3 VARCHAR);")
    db.execute("INSERT INTO t_1 VALUES(7, 'x');")
    assert db.execute("SELECT col_2 FROM t_1;").rows == [[7]]


def test_long_identifier_names(db):
    """长表名/列名（50 字符）可建表查询。"""
    name = "table_" + "n" * 50
    col = "col_" + "c" * 50
    db.execute("CREATE TABLE %s(%s INT);" % (name, col))
    db.execute("INSERT INTO %s VALUES(1);" % name)
    assert db.execute("SELECT %s FROM %s;" % (col, name)).rows == [[1]]


def test_statistics_after_work(db):
    """执行后 stats() 仍返回完整字段且表数正确。"""
    db.execute("CREATE TABLE t(a INT);")
    db.execute("INSERT INTO t VALUES(1);")
    stats = db.stats()
    assert stats["tables"] == 1
    assert "hit_rate" in stats and "policy" in stats


# ======================================================================
# D. Web 边界
# ======================================================================


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web.app as web_app
    from engine import Database
    db = Database(data_dir=str(tmp_path), log=False)
    monkeypatch.setattr(web_app, "get_db", lambda: db)
    app = web_app.create_app()
    app.config["TESTING"] = True
    yield app.test_client()
    db.close()


def test_api_non_json_body_ok(client):
    """非 JSON 请求体按空 SQL 处理（EMPTY，200）。"""
    resp = client.post("/api/sql", data="not-json", content_type="text/plain")
    assert resp.status_code == 200
    assert resp.get_json()["kind"] == "EMPTY"


def test_api_missing_sql_field_ok(client):
    """缺 sql 字段按空 SQL 处理。"""
    resp = client.post("/api/sql", json={"other": 1})
    assert resp.get_json()["ok"] is True and resp.get_json()["kind"] == "EMPTY"


def test_api_int_overflow_returns_400(client):
    """INT 溢出经 Web 返回 400 EngineError，而非 500（缺陷 #1 验证）。"""
    client.post("/api/sql", json={"sql": "CREATE TABLE t(a INT);"})
    resp = client.post("/api/sql", json={"sql": "INSERT INTO t VALUES(2147483648);"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False and data["kind"] == "RowTooLarge"


def test_api_stats_endpoint(client):
    client.post("/api/sql", json={"sql": "CREATE TABLE t(a INT);"})
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["tables"] == 1 and "hit_rate" in data


def test_api_unknown_route_404(client):
    assert client.get("/api/nope").status_code == 404


def test_api_index_page(client):
    assert client.get("/").status_code == 200


# ======================================================================
# 统一启动方法（P5）：开发者可直接运行本测试模块
#     python tests/test_boundary.py
#     或编程调用 run_tests()（返回 pytest 退出码，0 = 全部通过）
# ======================================================================


def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本测试模块全部用例。

    用法:
        python tests/test_boundary.py          # 命令行直接运行
        from runner import run_module          # 或编程调用(所有模块签名一致)
        run_module("tests/test_boundary.py")
    """
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())

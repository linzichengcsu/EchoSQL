"""数据库引擎测试（对应测试文档 3.3 TC-E2E-01 ~ 05 + SRS FR-3.1 ~ FR-3.5）。

    TC-E2E-01  建表后重复 CREATE TABLE：首次成功，重复报错            P0
    TC-E2E-02  大量数据插入 + 查询：数据完整                          P1
    TC-E2E-03  条件查询准确性：WHERE 过滤与预期一致                    P0
    TC-E2E-04  删除后再次查询：被删记录不可见（含整页回收）            P0
    TC-E2E-05  重启程序后查询：表结构与数据依然可查询（持久化）        P0

    补充    存储引擎单元（槽页 / 行序列化 / 表扩展与回收）、
            表达式求值（NULL 三值逻辑）、目录管理、脚本执行、错误处理。
"""
import os
import sys

# 直接运行(python tests/test_engine.py)时也能导入项目根包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from engine import (
    Database,
    EngineError,
    RowPage,
    RowTooLarge,
    TableStorage,
    decode_row,
    encode_row,
    eval_expr,
)
from sql_compiler import (
    ColumnCountMismatch,
    SQLError,
    TableAlreadyExists,
    TypeMismatch,
    UnknownColumn,
    UnknownTable,
)
from sql_compiler.ast_nodes import BinaryExpr, ColumnRef, Literal, NotExpr
from sql_compiler.catalog import ColumnInfo


@pytest.fixture
def db(tmp_path):
    """在临时目录构造全新数据库（避免污染 data/ 与测试间相互影响）。"""
    database = Database(data_dir=str(tmp_path), capacity=8, policy="LRU", log=False)
    yield database
    database.close()


def seed_student(db):
    """插入 SRS 5.1 演示数据。"""
    db.execute("CREATE TABLE student(id INT, name VARCHAR, age INT);")
    db.execute("INSERT INTO student VALUES(1,'Alice',20);")
    db.execute("INSERT INTO student VALUES(2,'Bob',17);")
    db.execute("INSERT INTO student VALUES(3,'Carol',22);")


# ======================================================================
# TC-E2E-01 建表后重复 CREATE TABLE
# ======================================================================


def test_e2e_create_table_ok(db):
    result = db.execute("CREATE TABLE student(id INT, name VARCHAR, age INT);")
    assert result.kind == "CREATE"
    assert result.message == "OK"
    assert "student" in db.tables()


def test_e2e_duplicate_create_raises(db):
    db.execute("CREATE TABLE student(id INT, name VARCHAR, age INT);")
    with pytest.raises(TableAlreadyExists):
        db.execute("CREATE TABLE student(id INT);")


def test_e2e_create_missing_table_error(db):
    """对未建表执行 SELECT/INSERT/DELETE 报 UnknownTable。"""
    with pytest.raises(UnknownTable):
        db.execute("SELECT * FROM ghost;")
    with pytest.raises(UnknownTable):
        db.execute("INSERT INTO ghost VALUES(1);")
    with pytest.raises(UnknownTable):
        db.execute("DELETE FROM ghost;")


# ======================================================================
# TC-E2E-02 大量数据插入 + 查询（数据完整、跨页存储）
# ======================================================================


def test_e2e_bulk_insert_select(db):
    db.execute("CREATE TABLE t(id INT, val VARCHAR);")
    for i in range(120):  # 超过单页容量，触发表扩展（FR-3.2）
        db.execute("INSERT INTO t(id,val) VALUES(%d,'v%d');" % (i, i))
    result = db.execute("SELECT id, val FROM t;")
    assert result.kind == "SELECT"
    assert result.columns == ["id", "val"]
    assert len(result.rows) == 120
    assert result.rows[0] == [0, "v0"]
    assert result.rows[-1] == [119, "v119"]


def test_e2e_multi_row_insert(db):
    """单条 INSERT 多行 VALUES：一次插入多行并汇总影响行数（缺陷 #3 修复）。"""
    db.execute("CREATE TABLE t(id INT, val VARCHAR);")
    result = db.execute(
        "INSERT INTO t(id,val) VALUES(1,'a'),(2,'b'),(3,'c');")
    assert result.kind == "INSERT"
    assert result.rows_affected == 3
    assert result.message == "3 rows inserted"
    assert db.execute("SELECT id,val FROM t;").rows == \
        [[1, "a"], [2, "b"], [3, "c"]]
    # 多行插入同样遵循列清单映射与跨页扩展
    db.execute("INSERT INTO t(val,id) VALUES('d',4),('e',5);")
    assert db.execute("SELECT id FROM t;").rows == [[1], [2], [3], [4], [5]]
    # 多行中任一行列数不符 → 语义错误，整条 INSERT 不执行
    with pytest.raises(ColumnCountMismatch):
        db.execute("INSERT INTO t(id,val) VALUES(9,'x'),(10);")
    assert db.execute("SELECT id FROM t;").rows == [[1], [2], [3], [4], [5]]


# ======================================================================
# TC-E2E-03 条件查询准确性
# ======================================================================


def test_e2e_select_where(db):
    seed_student(db)
    result = db.execute("SELECT id,name FROM student WHERE age > 18;")
    assert result.columns == ["id", "name"]
    assert result.rows == [[1, "Alice"], [3, "Carol"]]


def test_e2e_select_where_combined(db):
    seed_student(db)
    result = db.execute("SELECT name FROM student WHERE age > 18 AND name = 'Alice';")
    assert result.rows == [["Alice"]]
    result = db.execute("SELECT id FROM student WHERE age >= 20 OR age < 18;")
    assert sorted(r[0] for r in result.rows) == [1, 2, 3]


def test_e2e_select_star(db):
    seed_student(db)
    result = db.execute("SELECT * FROM student;")
    assert result.columns == ["id", "name", "age"]
    assert len(result.rows) == 3


def test_e2e_select_missing_column_error(db):
    seed_student(db)
    with pytest.raises(UnknownColumn):
        db.execute("SELECT nope FROM student;")


def test_e2e_select_unknown_table_error(db):
    with pytest.raises(UnknownTable):
        db.execute("SELECT * FROM student;")


# ======================================================================
# TC-E2E-04 删除后再次查询（被删记录不可见 + 整页回收）
# ======================================================================


def test_e2e_delete_then_select(db):
    seed_student(db)
    result = db.execute("DELETE FROM student WHERE id = 1;")
    assert result.rows_affected == 1
    assert result.message == "1 row deleted"
    # 被删记录不可见
    assert db.execute("SELECT * FROM student WHERE id = 1;").rows == []
    assert len(db.execute("SELECT * FROM student;").rows) == 2


def test_e2e_delete_all_rows_releases_pages(db):
    seed_student(db)
    before = db.table_infos()[0]["pages"]
    assert len(before) >= 1
    result = db.execute("DELETE FROM student;")
    assert result.rows_affected == 3
    assert db.execute("SELECT * FROM student;").rows == []
    # 全部行删除后整页回收：页集合清空，空闲页可被再分配（FR-3.2）
    assert db.table_infos()[0]["pages"] == []
    # 回收后仍可继续插入
    db.execute("INSERT INTO student VALUES(9,'Zoe',30);")
    assert db.execute("SELECT name FROM student;").rows == [["Zoe"]]


def test_e2e_delete_without_where_deletes_all(db):
    db.execute("CREATE TABLE t(a INT);")
    for i in range(5):
        db.execute("INSERT INTO t VALUES(%d);" % i)
    result = db.execute("DELETE FROM t;")
    assert result.rows_affected == 5


def test_e2e_delete_no_match(db):
    seed_student(db)
    result = db.execute("DELETE FROM student WHERE id = 99;")
    assert result.rows_affected == 0
    assert len(db.execute("SELECT * FROM student;").rows) == 3


# ======================================================================
# TC-E2E-05 重启程序后查询（持久化）
# ======================================================================


def test_e2e_persistence_restart(tmp_path):
    path = str(tmp_path)
    db1 = Database(data_dir=path, log=False)
    db1.execute("CREATE TABLE p(id INT, name VARCHAR, age INT);")
    db1.execute("INSERT INTO p VALUES(1,'Alice',20);")
    db1.execute("INSERT INTO p VALUES(2,'Bob',17);")
    db1.close()

    # 重启：表结构与数据均保留
    db2 = Database(data_dir=path, log=False)
    assert "p" in db2.tables()
    result = db2.execute("SELECT id,name FROM p WHERE age > 18;")
    assert result.rows == [[1, "Alice"]]
    # 重启后仍可继续写入
    db2.execute("INSERT INTO p VALUES(3,'Carol',22);")
    db2.close()

    db3 = Database(data_dir=path, log=False)
    assert len(db3.execute("SELECT * FROM p;").rows) == 3
    db3.close()


def test_e2e_persistence_after_delete(tmp_path):
    """删除并回收页后重启，页集合与剩余数据保持一致。"""
    path = str(tmp_path)
    db1 = Database(data_dir=path, log=False)
    db1.execute("CREATE TABLE t(a INT, b VARCHAR);")
    for i in range(30):
        db1.execute("INSERT INTO t VALUES(%d,'x%d');" % (i, i))
    db1.execute("DELETE FROM t WHERE a < 10;")
    db1.close()
    db2 = Database(data_dir=path, log=False)
    rows = db2.execute("SELECT a FROM t;").rows
    assert sorted(r[0] for r in rows) == list(range(10, 30))
    db2.close()


# ======================================================================
# 存储引擎单元（FR-3.2：槽页 / 行序列化 / 表扩展与回收）
# ======================================================================


def test_rowpage_insert_get_delete():
    rp = RowPage()
    s0 = rp.insert(b"row-0")
    s1 = rp.insert(b"row-1")
    assert s0 == 0 and s1 == 1
    assert rp.get(s0) == b"row-0"
    assert rp.active_count == 2
    rp.delete(s0)
    assert rp.get(s0) is None
    assert rp.active_count == 1
    assert rp.get(s1) == b"row-1"


def test_rowpage_encode_decode_roundtrip():
    rp = RowPage()
    rp.insert(b"aaa")
    rp.insert(b"bb")
    rp.insert(b"cccc")
    rp.delete(1)
    raw = rp.encode()
    assert len(raw) == 4096
    rp2 = RowPage.decode(raw)
    assert rp2.slot_count == 3
    assert rp2.get(0) == b"aaa"
    assert rp2.get(1) is None
    assert rp2.get(2) == b"cccc"


def test_rowpage_full_and_compact():
    rp = RowPage()
    payload = b"x" * 2000
    assert rp.insert(payload) == 0
    assert rp.insert(payload) == 1
    assert rp.insert(payload) is None  # 页满
    rp.delete(0)
    # 删除标记不回收空间，仍满
    assert rp.insert(payload) is None
    # compact 压缩后腾出空间
    rp2 = rp.compact()
    assert rp2.active_count == 1
    assert rp2.insert(payload) == 1


def test_row_serialization_roundtrip():
    values = [1, 2.5, "Alice", None, "Tom's"]
    raw = encode_row(values)
    assert decode_row(raw) == values


def test_row_too_large():
    with pytest.raises(RowTooLarge):
        encode_row(["x" * 5000])


def test_table_storage_insert_extends_pages(tmp_path):
    from storage import Storage
    with Storage(str(tmp_path), capacity=8, log=False) as st:
        ts = TableStorage(
            st, "t", [ColumnInfo("a", "INT"), ColumnInfo("b", "VARCHAR")]
        )
        extended = False
        for i in range(200):
            if ts.insert_row([i, "value-%d" % i]):
                extended = True
        assert extended  # 超过一页容量后扩展新页
        rows = [v for _, _, v in ts.scan()]
        assert len(rows) == 200
        assert rows[0] == [0, "value-0"]
        assert rows[-1] == [199, "value-199"]


def test_table_storage_delete_releases_page(tmp_path):
    from storage import Storage
    with Storage(str(tmp_path), capacity=8, log=False) as st:
        ts = TableStorage(st, "t", [ColumnInfo("a", "INT")])
        ts.insert_row([1])
        ts.insert_row([2])
        pages_before = ts.page_ids()
        assert len(pages_before) == 1
        # 删除后页内仍有活动行：页保留
        ts.delete_row(pages_before[0], 0)
        assert len(ts.page_ids()) == 1
        # 删除最后一行：整页回收
        ts.delete_row(pages_before[0], 1)
        assert ts.page_ids() == []
        assert sum(1 for _ in ts.scan()) == 0


def test_drop_table_releases_pages(db):
    db.execute("CREATE TABLE t(a INT);")
    for i in range(50):
        db.execute("INSERT INTO t VALUES(%d);" % i)
    pages = db.table_infos()[0]["pages"]
    assert len(pages) >= 1
    fm = db.storage.fm
    free_before = fm.free_count
    released = db.drop_table("t")
    assert released == len(pages)
    assert "t" not in db.tables()
    assert fm.free_count == free_before + len(pages)
    # 释放的页可被再分配
    db.execute("CREATE TABLE t2(a INT);")
    db.execute("INSERT INTO t2 VALUES(1);")
    assert len(db.tables()) == 1


# ======================================================================
# 表达式求值（WHERE 谓词，含 NULL 三值逻辑）
# ======================================================================


def test_eval_expr_literals_and_columns():
    row = {"id": 1, "age": 20, "name": "Alice"}
    assert eval_expr(Literal(1, 1, 18, "INT"), row) == 18
    assert eval_expr(ColumnRef(1, 1, "age"), row) == 20


def test_eval_expr_comparison_null_semantics():
    row = {"a": None, "b": 1}
    expr = BinaryExpr(1, 1, "=", ColumnRef(1, 1, "a"), Literal(1, 1, 1, "INT"))
    assert eval_expr(expr, row) is None  # NULL 比较 → unknown
    expr2 = BinaryExpr(1, 1, "=", ColumnRef(1, 1, "b"), Literal(1, 1, 1, "INT"))
    assert eval_expr(expr2, row) is True


def test_eval_expr_three_valued_logic():
    # TRUE OR NULL -> TRUE；FALSE AND NULL -> FALSE
    t = Literal(1, 1, True, "BOOL")
    null = Literal(1, 1, None, "NULL")
    f = Literal(1, 1, False, "BOOL")
    assert eval_expr(BinaryExpr(1, 1, "OR", t, null), {}) is True
    assert eval_expr(BinaryExpr(1, 1, "AND", f, null), {}) is False
    assert eval_expr(BinaryExpr(1, 1, "AND", t, null), {}) is None
    assert eval_expr(NotExpr(1, 1, t), {}) is False
    assert eval_expr(NotExpr(1, 1, null), {}) is None


def test_eval_expr_arithmetic(db):
    db.execute("CREATE TABLE t(a INT, b INT);")
    db.execute("INSERT INTO t VALUES(3,4);")
    result = db.execute("SELECT a FROM t WHERE a + b > 6;")
    assert result.rows == [[3]]
    result = db.execute("SELECT a FROM t WHERE a - b < 0;")
    assert result.rows == [[3]]


# ======================================================================
# 语义错误 / 健壮性（非法输入不崩溃，错误定位准确）
# ======================================================================


def test_insert_type_mismatch(db):
    db.execute("CREATE TABLE t(id INT);")
    with pytest.raises(TypeMismatch):
        db.execute("INSERT INTO t VALUES('abc');")


def test_insert_column_count_mismatch(db):
    db.execute("CREATE TABLE t(a INT, b VARCHAR);")
    with pytest.raises(ColumnCountMismatch):
        db.execute("INSERT INTO t VALUES(1);")


def test_insert_unknown_column(db):
    db.execute("CREATE TABLE t(a INT);")
    with pytest.raises(UnknownColumn):
        db.execute("INSERT INTO t(nope) VALUES(1);")


def test_execute_empty_and_whitespace(db):
    assert db.execute("") is None
    assert db.execute("   ") is None
    # 孤立分号 / 多余分号不再被宽容为空输入（缺陷 #4 修复），语法层拒绝
    for bad in (";", ";;", ";;;"):
        with pytest.raises(SQLError):
            db.execute(bad)
    with pytest.raises(SQLError):
        db.execute("INSERT INTO t VALUES(1);;")


def test_execute_script_rejects_empty_statements(db):
    """execute_script 遇到孤立分号 / 连续分号抛语法错误（缺陷 #4 修复）。"""
    for bad in (";", ";;", "INSERT INTO t VALUES(1);;"):
        with pytest.raises(SQLError):
            db.execute_script(bad)
    # 末尾缺分号仍宽容补全（BB-I003），纯注释脚本仍为空脚本
    db.execute("CREATE TABLE t(a INT);")
    rs = db.execute_script("INSERT INTO t VALUES(1); SELECT a FROM t")
    assert [r.kind for r in rs] == ["INSERT", "SELECT"]
    assert db.execute_script("-- only comment") == []


def test_execute_bad_sql_never_crashes(db):
    bad_inputs = [
        "@@@", "SELECT", "SELECT * FROM", "INSERT INTO",
        "CREATE TABLE t(", "SELECT 'abc;",
    ]
    for sql in bad_inputs:
        with pytest.raises(SQLError):
            db.execute(sql)


# ======================================================================
# 脚本执行 / 多语句 / 大小写 / NULL / 目录
# ======================================================================


def test_execute_script_multi_statements(db):
    results = db.execute_script(
        "CREATE TABLE t(a INT, b VARCHAR);"
        "INSERT INTO t VALUES(1,'x');"
        "INSERT INTO t VALUES(2,'y');"
        "SELECT b FROM t WHERE a = 2;"
    )
    assert [r.kind for r in results] == ["CREATE", "INSERT", "INSERT", "SELECT"]
    assert results[-1].rows == [["y"]]


def test_execute_multi_statements_returns_last(db):
    result = db.execute(
        "CREATE TABLE t(a INT); INSERT INTO t VALUES(7); SELECT a FROM t;"
    )
    assert result.kind == "SELECT"
    assert result.rows == [[7]]


def test_case_sensitive_names(db):
    """表名/列名大小写敏感:不同大小写视为不同名字(grammar.md §1.2.4)。"""
    db.execute("CREATE TABLE Student(Id INT, Name VARCHAR);")
    # 大小写不一致的表引用被语义分析拒绝(UnknownTable)
    with pytest.raises(SQLError):
        db.execute("INSERT INTO STUDENT(ID, NAME) VALUES(1, 'Alice');")
    with pytest.raises(SQLError):
        db.execute("SELECT * FROM student;")
    # 精确大小写引用正常
    db.execute("INSERT INTO Student(Id, Name) VALUES(1, 'Alice');")
    result = db.execute("SELECT Id, Name FROM Student;")
    assert result.rows == [[1, "Alice"]]
    assert "Student" in db.tables()
    # 仅大小写不同的表名可以同时存在
    db.execute("CREATE TABLE student(x INT);")
    assert sorted(db.tables()) == ["Student", "student"]


def test_insert_null_value(db):
    db.execute("CREATE TABLE t(a INT, b VARCHAR);")
    db.execute("INSERT INTO t(a) VALUES(1);")  # b 缺省为 NULL
    result = db.execute("SELECT a, b FROM t;")
    assert result.rows == [[1, None]]
    db.execute("INSERT INTO t VALUES(NULL, 'x');")
    result = db.execute("SELECT * FROM t;")
    assert result.rows == [[1, None], [None, "x"]]


def test_null_compare_returns_empty(db):
    db.execute("CREATE TABLE t(a INT);")
    db.execute("INSERT INTO t VALUES(1);")
    db.execute("INSERT INTO t VALUES(NULL);")
    # NULL = 1 为 unknown，不出现在结果中
    result = db.execute("SELECT a FROM t WHERE a = 1;")
    assert result.rows == [[1]]
    result = db.execute("SELECT a FROM t WHERE a <> 1;")
    assert result.rows == []


def test_table_infos_and_stats(db):
    seed_student(db)
    infos = db.table_infos()
    assert len(infos) == 1
    assert [c["name"] for c in infos[0]["columns"]] == ["id", "name", "age"]
    stats = db.stats()
    assert stats["tables"] == 1
    assert "hit_rate" in stats


def test_float_column_roundtrip(db):
    db.execute("CREATE TABLE t(x FLOAT);")
    db.execute("INSERT INTO t VALUES(3.14);")
    result = db.execute("SELECT x FROM t;")
    assert abs(result.rows[0][0] - 3.14) < 1e-9


# ======================================================================
# 输出格式化 / 防御路径 / 边界（FR-3.4 返回执行结果或错误信息）
# ======================================================================


def test_result_format_select_table(db):
    db.execute("CREATE TABLE t(a INT, b VARCHAR);")
    db.execute("INSERT INTO t VALUES(1,'Alice');")
    db.execute("INSERT INTO t VALUES(NULL,'Bob');")
    text = db.execute("SELECT a, b FROM t;").format()
    lines = text.splitlines()
    assert lines[0] == "a    | b    "
    assert lines[1] == "-----+------"
    assert "1    | Alice" in lines[2]
    assert "NULL | Bob  " in lines[3]


def test_result_format_non_select(db):
    r = db.execute("CREATE TABLE t(a INT);")
    assert r.format() == "OK"
    r = db.execute("INSERT INTO t VALUES(1);")
    assert r.format() == "1 row inserted"
    r = db.execute("DELETE FROM t;")
    assert r.format() == "1 row deleted"


def test_result_to_dict(db):
    db.execute("CREATE TABLE t(a INT);")
    db.execute("INSERT INTO t VALUES(1);")
    r = db.execute("SELECT a FROM t;")
    d = r.to_dict()
    assert d["kind"] == "SELECT"
    assert d["columns"] == ["a"]
    assert d["rows"] == [[1]]


def test_execute_scan_and_filter_plans_direct(db):
    """防御路径：直接执行 SeqScan / Filter 计划（无 Project 包装）。"""
    from sql_compiler import FilterPlan, ProjectPlan, SeqScanPlan, build, lex, parse
    from sql_compiler.ast_nodes import BinaryExpr, ColumnRef, Literal

    db.execute("CREATE TABLE t(a INT);")
    db.execute("INSERT INTO t VALUES(1);")
    db.execute("INSERT INTO t VALUES(2);")

    ast = parse(lex("SELECT * FROM t;"))
    plan = build(ast, db.catalog)[0]
    assert isinstance(plan, ProjectPlan)
    scan_plan = plan.child
    assert isinstance(scan_plan, SeqScanPlan)
    r = db.executor.execute(scan_plan)
    assert r.kind == "SELECT" and len(r.rows) == 2

    filter_plan = FilterPlan(
        BinaryExpr(1, 1, ">", ColumnRef(1, 1, "a"), Literal(1, 1, 1, "INT")),
        SeqScanPlan("t"),
    )
    r2 = db.executor.execute(filter_plan)
    assert r2.rows == [[2]]


def test_e2e_string_escape_and_chinese(db):
    """字符串转义与中文内容入库查询（grammar.md §1.2.6）。"""
    db.execute("CREATE TABLE t(name VARCHAR);")
    db.execute("INSERT INTO t VALUES('Tom''s book');")
    db.execute("INSERT INTO t VALUES('中文数据');")
    rows = db.execute("SELECT name FROM t;").rows
    assert rows[0] == ["Tom's book"]
    assert rows[1] == ["中文数据"]


# ======================================================================
# 统一启动方法（P5）：开发者可直接运行本测试模块
#     python tests/test_engine.py
#     或编程调用 run_tests()（返回 pytest 退出码，0 = 全部通过）
# ======================================================================


def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本测试模块全部用例。

    用法:
        python tests/test_engine.py           # 命令行直接运行
        from runner import run_module         # 或编程调用(所有模块签名一致)
        run_module("tests/test_engine.py")
    """
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())

"""命令行接口（CLI）测试（P5：系统测试）。

针对 cli 模块（FR-3.4 / SRS 5.1）做集成验证：
    - MiniDBShell：SQL 执行输出（表格 / message）、多语句、错误打印、
      辅助命令 tables / stats / quit、空行与空白输入
    - run_sql_file：SQL 脚本批处理成功 / 文件缺失 / SQL 错误
    - cli.main：argparse 参数解析（-f 批处理路径、非法 policy 拒绝）

CLI 层原本无测试（覆盖率 0%），本文件补齐后与 Web / 引擎形成完整测试链。
"""
import os
import sys

# 直接运行(python tests/test_cli.py)时也能导入项目根包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from cli import MiniDBShell, main as cli_main, run_sql_file
from engine import Database


@pytest.fixture
def db(tmp_path):
    database = Database(data_dir=str(tmp_path), log=False)
    yield database
    database.close()


def _shell(db):
    """构造不进入 cmdloop（避免阻塞与自动 close）的测试外壳。"""
    return MiniDBShell(db)


def _capture(capsys):
    return capsys.readouterr().out


# ======================================================================
# MiniDBShell：SQL 执行与输出
# ======================================================================


def test_shell_select_outputs_table(capsys, db):
    db.execute("CREATE TABLE student(id INT, name VARCHAR, age INT);")
    db.execute("INSERT INTO student VALUES(1,'Alice',20);")
    db.execute("INSERT INTO student VALUES(2,'Bob',17);")
    db.execute("INSERT INTO student VALUES(3,'Carol',22);")
    shell = _shell(db)
    shell.onecmd("SELECT id,name FROM student WHERE age > 18;")
    out = _capture(capsys)
    assert "id" in out and "name" in out          # 表头
    assert "-+-" in out or "+" in out             # 分隔线
    assert "Alice" in out and "Carol" in out
    assert "Bob" not in out                       # WHERE 过滤生效


def test_shell_multi_statement_line(capsys, db):
    shell = _shell(db)
    shell.onecmd(
        "CREATE TABLE t(a INT); INSERT INTO t VALUES(5); SELECT a FROM t;"
    )
    out = _capture(capsys)
    assert "OK" in out                      # CREATE
    assert "1 row inserted" in out          # INSERT
    assert "5" in out                       # SELECT


def test_shell_sql_error_prints_without_crash(capsys, db):
    shell = _shell(db)
    shell.onecmd("SELECT nope FROM ghost;")     # 不应抛出，仅打印错误
    out = _capture(capsys)
    assert "UnknownTable" in out or "does not exist" in out


def test_shell_engine_error_prints_without_crash(capsys, db):
    """引擎层错误（INT 溢出 → RowTooLarge）打印而非崩溃。"""
    db.execute("CREATE TABLE t(a INT);")
    shell = _shell(db)
    shell.onecmd("INSERT INTO t VALUES(2147483648);")
    out = _capture(capsys)
    assert "RowTooLarge" in out


def test_shell_blank_and_empty_lines(capsys, db):
    shell = _shell(db)
    shell.onecmd("   ")          # 空白行：直接返回
    shell.onecmd("")             # 空行
    shell.emptyline()            # 显式空行处理
    assert _capture(capsys) == ""


# ======================================================================
# MiniDBShell：辅助命令
# ======================================================================


def test_shell_tables_empty(capsys, db):
    _shell(db).onecmd("tables")
    assert "no tables" in _capture(capsys)


def test_shell_tables_lists_structure(capsys, db):
    db.execute("CREATE TABLE student(id INT, name VARCHAR);")
    _shell(db).onecmd("tables")
    out = _capture(capsys)
    assert "student" in out and "INT" in out and "VARCHAR" in out


def test_shell_stats_output(capsys, db):
    db.execute("CREATE TABLE t(a INT);")
    _shell(db).onecmd("stats")
    out = _capture(capsys)
    assert "hit_rate:" in out and "policy:" in out and "tables:" in out


def test_shell_quit_returns_true(capsys, db):
    shell = _shell(db)
    assert shell.do_quit("") is True
    assert "bye" in _capture(capsys)
    assert shell.do_exit("") is True      # 别名


def test_shell_does_not_close_db_when_constructed_externally(db):
    """外部传入 db 时，单条命令执行不自动关闭数据库。"""
    shell = _shell(db)
    db.execute("CREATE TABLE t(a INT);")
    shell.onecmd("SELECT * FROM t;")
    assert "t" in db.tables()             # db 仍可用


# ======================================================================
# run_sql_file：批处理脚本
# ======================================================================


def _write_sql(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_run_sql_file_success(tmp_path, capsys):
    db = Database(data_dir=str(tmp_path), log=False)
    path = _write_sql(
        tmp_path / "ok.sql",
        "CREATE TABLE t(a INT);\nINSERT INTO t VALUES(1);\nSELECT a FROM t;\n",
    )
    code = run_sql_file(db, path)
    out = _capture(capsys)
    assert code == 0
    assert "OK" in out
    assert "1 row inserted" in out
    assert "1" in out
    assert "1 statement" not in out and "3 statement" in out


def test_run_sql_file_missing_returns_1(tmp_path, capsys):
    db = Database(data_dir=str(tmp_path), log=False)
    code = run_sql_file(db, str(tmp_path / "nope.sql"))
    assert code == 1
    assert "cannot open" in _capture(capsys)


def test_run_sql_file_sql_error_returns_1(tmp_path, capsys):
    db = Database(data_dir=str(tmp_path), log=False)
    path = _write_sql(tmp_path / "bad.sql", "SELECT nope FROM ghost;")
    code = run_sql_file(db, path)
    assert code == 1
    assert "UnknownTable" in _capture(capsys) or "does not exist" in _capture(capsys)


def test_run_sql_file_echo_false_silent(tmp_path, capsys):
    db = Database(data_dir=str(tmp_path), log=False)
    path = _write_sql(tmp_path / "quiet.sql", "CREATE TABLE t(a INT);")
    code = run_sql_file(db, path, echo=False)
    out = _capture(capsys)
    assert code == 0
    assert "OK" not in out                 # 关闭逐条回显
    assert "statement" in out              # 汇总行仍在


# ======================================================================
# cli.main：参数解析
# ======================================================================


def test_main_batch_file(tmp_path, capsys):
    path = _write_sql(tmp_path / "demo.sql", "CREATE TABLE t(a INT);")
    code = cli_main(["-f", path, "--data-dir", str(tmp_path)])
    assert code == 0
    assert "OK" in _capture(capsys)


def test_main_invalid_policy_rejected(tmp_path):
    with pytest.raises(SystemExit):
        cli_main(["--data-dir", str(tmp_path), "--policy", "CLOCK"])


# ======================================================================
# 统一启动方法（P5）：开发者可直接运行本测试模块
#     python tests/test_cli.py
#     或编程调用 run_tests()（返回 pytest 退出码，0 = 全部通过）
# ======================================================================


def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本测试模块全部用例。

    用法:
        python tests/test_cli.py              # 命令行直接运行
        from runner import run_module         # 或编程调用(所有模块签名一致)
        run_module("tests/test_cli.py")
    """
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())

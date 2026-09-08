# -*- coding: utf-8 -*-
"""EchoSQL(MiniDB) 黑盒测试驱动器（P6：黑盒 / 系统测试）。

黑盒视角
--------
本模块只通过产品对外接口观察被测系统（SUT）行为，不引用内部结构：
    engine 层 —— Database 门面：SQL 文本进、ExecutionResult/错误出；
    cli    层 —— 子进程运行 `python main.py`（-f 批处理 / REPL 管道输入），
                只检查进程退出码与标准输出文本；
    web    层 —— Flask 测试客户端调用 REST API，只检查 HTTP 状态码与 JSON。
期望值全部来自 tests/blackbox_dataset.py 数据集（数据驱动），
数据集中每条记录 = 一个测试用例，按 layer 分别参数化执行。

规模审计
--------
test_dataset_requirement_audit 对数据集做硬断言：
    总用例数 >= 200 且 边界用例占比 >= 5%；
任一不满足即整套黑盒测试失败，保证规模要求可被机器持续校验。

运行方式（与项目统一启动约定一致）
----------------------------------
    python tests/test_blackbox.py                 # 运行全部黑盒用例
    pytest tests/test_blackbox.py -q
    python -m pytest tests/test_blackbox.py -k 'BB-K'   # 只跑边界/压力组
"""
import math
import os
import subprocess
import sys

# 直接运行(python tests/test_blackbox.py)时也能导入项目根包与数据集模块
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TESTS = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

import pytest  # noqa: E402

from blackbox_dataset import CASES, dataset_stats  # noqa: E402

ALL_CASES = CASES()
ENGINE_CASES = [c for c in ALL_CASES if c["layer"] == "engine"]
CLI_CASES = [c for c in ALL_CASES if c["layer"] == "cli"]
WEB_CASES = [c for c in ALL_CASES if c["layer"] == "web"]


# ======================================================================
# 通用断言辅助（期望行比较：浮点容差 + None 精确匹配）
# ======================================================================

def _cell_eq(expected, actual):
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return abs(float(expected) - float(actual)) < 1e-9
        except (TypeError, ValueError):
            return False
    return expected == actual


def _rows_eq(expected_rows, actual_rows):
    if len(expected_rows) != len(actual_rows):
        return False
    for er, ar in zip(expected_rows, actual_rows):
        if len(er) != len(ar):
            return False
        for e, a in zip(er, ar):
            if not _cell_eq(e, a):
                return False
    return True


def _json_has(data, subset):
    """断言 data 包含 subset 全部键且值相等（递归，浮点容差）。"""
    for key, want in subset.items():
        if key not in data:
            return False
        if not _value_eq(want, data[key]):
            return False
    return True


def _value_eq(want, got):
    if isinstance(want, dict):
        return isinstance(got, dict) and _json_has(got, want)
    if isinstance(want, (list, tuple)):
        if not isinstance(got, (list, tuple)) or len(want) != len(got):
            return False
        return all(_value_eq(w, g) for w, g in zip(want, got))
    if isinstance(want, float) or isinstance(got, float):
        try:
            return abs(float(want) - float(got)) < 1e-9
        except (TypeError, ValueError):
            return False
    return want == got


# ======================================================================
# engine 层：黑盒执行 + 断言
# ======================================================================

def _check_result(case, result, api_out):
    """对成功动作结果做断言（返回 None 表示跳过；错误则抛 AssertionError）。"""
    exp = case["expect"]
    if "api_return" in exp:
        assert api_out == exp["api_return"], (
            "api 返回不符: want %r got %r" % (exp["api_return"], api_out))
        return
    if exp.get("empty"):
        assert result is None, "期望空输入返回 None，实际 %r" % (result,)
        return
    assert result is not None, "动作无结果返回（用例未设置 empty/error/api）"
    if "kind" in exp:
        assert result.kind == exp["kind"], (
            "kind 不符: want %r got %r" % (exp["kind"], result.kind))
    if "columns" in exp:
        assert list(result.columns) == list(exp["columns"]), (
            "columns 不符: want %r got %r" % (exp["columns"], result.columns))
    if "rows" in exp:
        assert _rows_eq(exp["rows"], result.rows), (
            "rows 不符:\n want=%r\n got =%r" % (exp["rows"], result.rows))
    if "rows_affected" in exp:
        assert result.rows_affected == exp["rows_affected"], (
            "rows_affected 不符: want %r got %r"
            % (exp["rows_affected"], result.rows_affected))
    if "message_has" in exp:
        assert exp["message_has"] in (result.message or ""), (
            "message 应包含 %r，实际 %r" % (exp["message_has"], result.message))


def _check_error(case, exc):
    exp = case["expect"]
    want = exp["error"]
    got_kind = getattr(exc, "kind", None) or type(exc).__name__
    assert got_kind == want, (
        "错误类型不符: want %r got %r (%s)" % (want, got_kind, exc))
    if "error_has" in exp:
        assert exp["error_has"] in str(exc), (
            "错误文本应包含 %r，实际 %s" % (exp["error_has"], exc))


def _run_then_sql(db, case):
    """动作后的二次校验 SELECT（错误场景下也执行，验证副作用）。"""
    exp = case["expect"]
    if exp.get("then_sql"):
        r = db.execute(exp["then_sql"])
        if "then_columns" in exp:
            assert list(r.columns) == list(exp["then_columns"])
        if "then_rows" in exp:
            assert _rows_eq(exp["then_rows"], r.rows), (
                "then_sql 结果不符:\n want=%r\n got =%r"
                % (exp["then_rows"], r.rows))


def _check_current_db_checks(case, db, api_out):
    """动作后在当前数据库上的 API 级检查（check_* 字段）。"""
    # 兼容两种字段名（旧名 tables_after_extra / 新名 check_tables）
    tables_want = case.get("check_tables")
    if tables_want is None and "tables_after_extra" in case:
        tables_want = case["tables_after_extra"]
    if tables_want is not None:
        assert list(db.tables()) == list(tables_want), (
            "tables() 不符: want %r got %r"
            % (tables_want, db.tables()))
    if case.get("check_info_columns") is not None:
        infos = db.table_infos()
        assert infos, "table_infos 为空"
        cols = [c["name"] for c in infos[0]["columns"]]
        assert cols == list(case["check_info_columns"]), (
            "表列名不符: want %r got %r"
            % (case["check_info_columns"], cols))
    if case.get("check_info_types") is not None:
        infos = db.table_infos()
        types = [c["type"] for c in infos[0]["columns"]]
        assert types == list(case["check_info_types"]), (
            "表列类型不符: want %r got %r"
            % (case["check_info_types"], types))
    if case.get("check_stats_has"):
        stats = db.stats()
        missing = [k for k in case["check_stats_has"] if k not in stats]
        assert not missing, "stats 缺字段 %r，实际 %r" % (missing, stats)
    if case.get("check_stats_range") is not None:
        lo, hi = case["check_stats_range"]
        hit = db.stats()["hit_rate"]
        assert lo <= hit <= hi, "hit_rate=%r 不在 [%r, %r]" % (hit, lo, hi)
    if "api_return" in case["expect"]:
        assert api_out == case["expect"]["api_return"], (
            "api 返回不符: want %r got %r"
            % (case["expect"]["api_return"], api_out))


def _run_persist_case(tmp_path, case):
    """persist 场景：setup → 关闭 → 重开 → then 校验（→ 续写 → check2）。"""
    from engine import Database

    exp = case["expect"]
    cfg = exp.get("persist") or {}
    data_dir = str(tmp_path)
    db1 = Database(data_dir=data_dir, log=False)
    try:
        for sql in case.get("setup") or []:
            db1.execute(sql)
        pre = cfg.get("pre_close_api")
        if pre:
            getattr(db1, pre["api"])(*pre.get("args", []))
    finally:
        db1.close()

    db2 = Database(data_dir=data_dir, log=False)
    try:
        if case.get("check_tables_after_reopen") is not None:
            assert list(db2.tables()) == list(
                case["check_tables_after_reopen"]), (
                "重启后 tables() 不符: want %r got %r"
                % (case["check_tables_after_reopen"], db2.tables()))
        if exp.get("then_sql"):
            r = db2.execute(exp["then_sql"])
            if "then_rows" in exp:
                assert _rows_eq(exp["then_rows"], r.rows), (
                    "重启后 then_sql 结果不符:\n want=%r\n got =%r"
                    % (exp["then_rows"], r.rows))
        if cfg.get("reopen_insert"):
            db2.execute(cfg["reopen_insert"])
        if cfg.get("check2_sql"):
            r2 = db2.execute(cfg["check2_sql"])
            assert _rows_eq(cfg["check2_rows"], r2.rows), (
                "重启续写后结果不符:\n want=%r\n got =%r"
                % (cfg["check2_rows"], r2.rows))
    finally:
        db2.close()


def run_engine_case(case, tmp_path):
    """执行单条 engine 层黑盒用例。"""
    from engine import Database, EngineError
    from sql_compiler import SQLError

    exp = case["expect"]
    if "persist" in exp:
        _run_persist_case(tmp_path, case)
        return

    db = Database(data_dir=str(tmp_path), log=False)
    api_out = None
    try:
        # 1) 前置语句（须全部成功）
        for sql in case.get("setup") or []:
            db.execute(sql)

        # 2) 被测动作
        action = case["action"]
        error = None
        result = None
        executed = False
        if isinstance(action, dict):
            if "api" not in action:
                raise AssertionError("非法 action dict: %r" % action)
            api_out = getattr(db, action["api"])(*action.get("args", []))
        elif action is None:
            pass  # 纯 API / 目录检查场景，无 SQL 动作
        elif action == "" and not exp.get("empty"):
            pass  # 空动作字符串且不要求 empty -> 无动作（仅检查类用例）
        else:
            executed = True
            try:
                if case.get("mode") == "script":
                    results = db.execute_script(action)
                    result = results[-1] if results else None
                else:
                    result = db.execute(action)
            except (SQLError, EngineError) as exc:
                error = exc

        # 3) 期望断言
        if exp.get("error"):
            assert error is not None, "期望错误 %s 但动作成功" % exp["error"]
            _check_error(case, error)
        elif exp.get("empty"):
            assert error is None and result is None, "期望空输入返回 None"
        elif "api_return" in exp:
            assert error is None, "api 动作意外抛出错误: %s" % error
            assert api_out == exp["api_return"], (
                "api 返回不符: want %r got %r" % (exp["api_return"], api_out))
        elif executed:
            assert error is None, "动作意外抛出错误: %s" % error
            _check_result(case, result, api_out)
        # else：纯检查类用例（无动作），无结果断言

        # 4) 当前库 API 级检查
        _check_current_db_checks(case, db, api_out)

        # 5) 动作后的二次校验 SELECT（错误场景也执行，验证副作用保留）
        _run_then_sql(db, case)
    finally:
        db.close()


# ======================================================================
# cli 层：子进程运行 main.py（批处理 / REPL）
# ======================================================================

def _run_cli(case, tmp_path):
    main_py = os.path.join(_ROOT, "main.py")
    data_dir = str(tmp_path / "data")
    argv = [sys.executable, main_py, "--data-dir", data_dir]
    argv += list(case.get("extra_args") or [])
    stdin_text = None
    if case.get("repl"):
        stdin_text = case["action"]
    else:
        if case.get("file_missing"):
            script_path = str(tmp_path / "missing.sql")  # 不存在的文件
        else:
            script_path = str(tmp_path / "script.sql")
            with open(script_path, "w", encoding="utf-8") as fp:
                fp.write(case["action"])
        argv += ["-f", script_path]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        argv, input=stdin_text, capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=_ROOT, env=env, timeout=180,
    )
    out = proc.stdout or ""
    exp = case["expect"]
    assert proc.returncode == exp.get("rc", 0), (
        "进程退出码不符: want %r got %r\nstdout=%r\nstderr=%r"
        % (exp.get("rc", 0), proc.returncode, out, proc.stderr))
    for frag in exp.get("stdout_has", []):
        assert frag in out, "stdout 应包含 %r\n实际输出:\n%s" % (frag, out)
    for frag in exp.get("stdout_has_not", []):
        assert frag not in out, "stdout 不应包含 %r\n实际输出:\n%s" % (frag, out)


# ======================================================================
# web 层：Flask 测试客户端走 REST API
# ======================================================================

def _run_web(case, tmp_path, monkeypatch):
    import web.app as web_app
    from engine import Database

    db = Database(data_dir=str(tmp_path), log=False)
    try:
        monkeypatch.setattr(web_app, "get_db", lambda: db)
        app = web_app.create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        # 前置：每个 SQL 经 /api/sql 执行并须成功
        for sql in case.get("setup") or []:
            resp = client.post("/api/sql", json={"sql": sql})
            data = resp.get_json() or {}
            assert resp.status_code == 200 and data.get("ok") is True, (
                "web setup 失败: %r -> %s %s" % (sql, resp.status_code, data))

        # 被测 HTTP 动作
        action = case["action"]
        kw = {k: v for k, v in action.items()
              if k in ("method", "path", "json", "data", "content_type",
                       "headers")}
        method = kw.pop("method", "GET")
        path = kw.pop("path", "/")
        resp = client.open(path, method=method, **kw)

        # 断言
        exp = case["expect"]
        assert resp.status_code == exp.get("status", 200), (
            "HTTP 状态不符: want %r got %r body=%s"
            % (exp.get("status", 200), resp.status_code, resp.get_data()))
        data = resp.get_json()
        if "json_has" in exp:
            assert data is not None, "响应非 JSON"
            assert _json_has(data, exp["json_has"]), (
                "JSON 不符: want 子集 %r\ngot %r" % (exp["json_has"], data))
        if case.get("check_api_tables_names") is not None:
            names = sorted(t["name"] for t in data["tables"])
            assert names == sorted(case["check_api_tables_names"]), (
                "tables 名不符: want %r got %r"
                % (case["check_api_tables_names"], names))
        if case.get("check_stats_has"):
            missing = [k for k in case["check_stats_has"] if k not in data]
            assert not missing, "stats 缺字段 %r，实际 %r" % (missing, data)
    finally:
        db.close()


# ======================================================================
# 参数化黑盒用例（每条数据集记录 = 一条 pytest 用例）
# ======================================================================

@pytest.mark.parametrize("case", ENGINE_CASES, ids=lambda c: c["id"])
def test_blackbox_engine(case, tmp_path):
    """engine 层黑盒：SQL 文本进，可观察结果/错误出。"""
    run_engine_case(case, tmp_path)


@pytest.mark.parametrize("case", CLI_CASES, ids=lambda c: c["id"])
def test_blackbox_cli(case, tmp_path):
    """cli 层黑盒：子进程运行 main.py，检查退出码与 stdout。"""
    _run_cli(case, tmp_path)


@pytest.mark.parametrize("case", WEB_CASES, ids=lambda c: c["id"])
def test_blackbox_web(case, tmp_path, monkeypatch):
    """web 层黑盒：REST API 状态码与 JSON 断言。"""
    _run_web(case, tmp_path, monkeypatch)


# ======================================================================
# 规模审计：总用例 >= 200 且边界占比 >= 5%（硬性要求）
# ======================================================================

def test_dataset_requirement_audit():
    stats = dataset_stats()
    total = stats["total"]
    boundary = stats["boundary"]
    ratio = stats["boundary_ratio"]
    # 收集到的 pytest 用例数与数据集一致
    assert len(ALL_CASES) == total
    assert total >= 200, (
        "黑盒用例总数不满足要求: got %d, need >= 200" % total)
    assert boundary >= math.ceil(total * 0.05), (
        "边界用例数不满足要求: got %d, need >= %d (5%% of %d)"
        % (boundary, math.ceil(total * 0.05), total))
    ids = [c["id"] for c in ALL_CASES]
    assert len(ids) == len(set(ids)), "存在重复用例编号"
    # 摘要输出（-s 可见；亦见 blackbox_dataset_report.md）
    print("\n[blackbox dataset] total=%d boundary=%d ratio=%.2f%% layers=%s"
          % (total, boundary, ratio * 100, stats["by_layer"]))


# ======================================================================
# 统一启动方法（P5 约定）：开发者可直接运行本测试模块
# ======================================================================

def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本模块全部用例。

    用法:
        python tests/test_blackbox.py             # 命令行直接运行
        from runner import run_module             # 或编程调用(签名一致)
        run_module("tests/test_blackbox.py")
        python tests/test_blackbox.py --report <path>   # 额外生成数据集报告
    """
    if extra_args and "--report" in extra_args:
        from blackbox_dataset import write_dataset_report
        idx = extra_args.index("--report")
        out = extra_args[idx + 1] if idx + 1 < len(extra_args) else None
        target = out or os.path.join(_TESTS, "blackbox_dataset_report.md")
        print("dataset report ->", write_dataset_report(target))
        extra_args = [a for a in extra_args
                      if a != "--report" and a != target]
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    # 支持 python tests/test_blackbox.py [--report <path>]
    argv = sys.argv[1:]
    if "--report" in argv:
        from blackbox_dataset import write_dataset_report
        idx = argv.index("--report")
        out = argv[idx + 1] if idx + 1 < len(argv) else None
        target = out or os.path.join(_TESTS, "blackbox_dataset_report.md")
        print("dataset report ->", write_dataset_report(target))
        argv = [a for a in argv if a != "--report" and a != out]
    sys.exit(run_tests(extra_args=argv or None))

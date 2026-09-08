"""Web API 集成测试（FR-3.4 API 接口 + SRS 2.3）。

验证 Flask 层 /api/sql、/api/tables、/api/health 与引擎贯通，
以及错误 SQL 返回结构化错误而非崩溃。
"""
import os
import sys

# 直接运行(python tests/test_web_api.py)时也能导入项目根包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

import web.app as web_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """把 web 应用的共享数据库指向临时目录后返回测试客户端。"""
    from engine import Database
    db = Database(data_dir=str(tmp_path), log=False)
    monkeypatch.setattr(web_app, "get_db", lambda: db)
    app = web_app.create_app()
    app.config["TESTING"] = True
    yield app.test_client()
    db.close()


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "MiniDB Web Console"


def test_execute_create_insert_select(client):
    resp = client.post("/api/sql", json={"sql": "CREATE TABLE t(id INT, name VARCHAR);"})
    data = resp.get_json()
    assert data["ok"] is True and data["message"] == "OK"

    resp = client.post("/api/sql", json={"sql": "INSERT INTO t VALUES(1,'Alice');"})
    assert resp.get_json()["rows_affected"] == 1

    resp = client.post("/api/sql", json={"sql": "SELECT id,name FROM t;"})
    data = resp.get_json()
    assert data["ok"] is True
    assert data["kind"] == "SELECT"
    assert data["columns"] == ["id", "name"]
    assert data["rows"] == [[1, "Alice"]]


def test_execute_error_returns_400(client):
    resp = client.post("/api/sql", json={"sql": "SELECT nope FROM ghost;"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "error" in data and "kind" in data


def test_tables_api(client):
    client.post("/api/sql", json={"sql": "CREATE TABLE a(x INT);"})
    client.post("/api/sql", json={"sql": "CREATE TABLE b(y VARCHAR);"})
    resp = client.get("/api/tables")
    data = resp.get_json()
    names = sorted(t["name"] for t in data["tables"])
    assert names == ["a", "b"]


def test_empty_sql_ok(client):
    resp = client.post("/api/sql", json={"sql": "   "})
    data = resp.get_json()
    assert data["ok"] is True and data["kind"] == "EMPTY"


# ======================================================================
# 统一启动方法（P5）：开发者可直接运行本测试模块
#     python tests/test_web_api.py
#     或编程调用 run_tests()（返回 pytest 退出码，0 = 全部通过）
# ======================================================================


def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本测试模块全部用例。

    用法:
        python tests/test_web_api.py          # 命令行直接运行
        from runner import run_module         # 或编程调用(所有模块签名一致)
        run_module("tests/test_web_api.py")
    """
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())

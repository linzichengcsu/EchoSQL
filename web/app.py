"""MiniDB Flask Web 应用（P4：接入数据库引擎）。

提供 Web 控制台与 REST API（SRS 2.3「也可通过 API 调用」）：
    GET  /             Web 控制台（SQL 编辑 + 结果表格）
    GET  /api/health   健康检查（环境与依赖版本）
    POST /api/sql      执行 SQL，返回结果/错误（FR-3.4 API）
    GET  /api/tables   列出全部表及结构（FR-3.3 目录查询）
    GET  /api/stats    页缓存命中率等运行统计（FR-2.2）

启动方式：
    python -m web.app            # http://127.0.0.1:5000
"""
import platform
import sys

from flask import Flask, jsonify, render_template, request

from engine import Database, EngineError
from sql_compiler import SQLError

_db = None


def get_db() -> Database:
    """模块级共享数据库实例（数据目录 data/，重启后数据保留）。"""
    global _db
    if _db is None:
        _db = Database(data_dir="data")
    return _db


def create_app():
    """应用工厂：便于测试与后续扩展。"""
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html", env=collect_env())

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "MiniDB Web Console", **collect_env()})

    @app.post("/api/sql")
    def api_sql():
        """执行 SQL：返回结果（SELECT 表格 / 影响行数）或错误信息。"""
        payload = request.get_json(silent=True) or {}
        sql = payload.get("sql", "")
        try:
            result = get_db().execute(sql)
            if result is None:
                return jsonify({"ok": True, "kind": "EMPTY", "message": ""})
            return jsonify({"ok": True, **result.to_dict()})
        except SQLError as exc:
            return jsonify({
                "ok": False,
                "kind": exc.kind,
                "position": list(exc.position),
                "error": str(exc),
            }), 400
        except EngineError as exc:
            return jsonify({"ok": False, "kind": exc.kind, "error": str(exc)}), 400

    @app.get("/api/tables")
    def api_tables():
        return jsonify({"tables": get_db().table_infos()})

    @app.get("/api/stats")
    def api_stats():
        return jsonify(get_db().stats())

    return app


def collect_env():
    """收集环境信息，供首页与健康检查展示。"""
    try:
        from importlib.metadata import version as _version
        flask_version = _version("flask")
    except ImportError:  # pragma: no cover
        flask_version = "n/a"
    try:
        import pytest
        pytest_version = pytest.__version__
    except ImportError:  # pragma: no cover
        pytest_version = "n/a"
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "flask": flask_version,
        "pytest": pytest_version,
    }


app = create_app()

if __name__ == "__main__":
    # 开发服务器：host 127.0.0.1；debug 重载会双开进程争用数据文件，故关闭
    app.run(host="127.0.0.1", port=5000, debug=False)

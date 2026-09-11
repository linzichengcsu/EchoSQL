"""MiniDB Flask Web 应用（P4：接入数据库引擎；P7：接入 React 前端）。

提供 Web 控制台与 REST API（SRS 2.3「也可通过 API 调用」）：
    GET  /             Web 控制台（React + Ant Design 单页应用）
    GET  /api/health   健康检查（环境与依赖版本）
    POST /api/sql      执行 SQL，返回结果/错误（FR-3.4 API）
    GET  /api/tables   列出全部表及结构（FR-3.3 目录查询）
    GET  /api/stats    页缓存命中率等运行统计（FR-2.2）

前端：web/frontend/（Vite + React + Ant Design），构建产物输出到
web/static/react/，由本应用静态托管；前端源码未构建时首页给出构建指引。

启动方式：
    python -m web.app            # http://127.0.0.1:5000
"""
import platform
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from engine import Database, EngineError
from sql_compiler import SQLError

_db = None

# React 前端构建产物目录（vite build → web/static/react/）
_FRONTEND_DIST = Path(__file__).resolve().parent / "static" / "react"
_FRONTEND_ASSETS = _FRONTEND_DIST / "assets"


def collect_frontend_assets():
    """定位前端构建产物，返回 (js, css) 相对 static 的路径。

    未构建时返回 (None, None)，首页据此显示构建指引。
    以后若改为带 hash 的文件名，本函数仍能自动识别入口资源。
    """
    if not _FRONTEND_ASSETS.is_dir():
        return None, None
    names = sorted(p.name for p in _FRONTEND_ASSETS.iterdir() if p.is_file())

    def _pick(ext: str) -> str:
        exact = f"index{ext}"
        if exact in names:
            return exact
        return next((n for n in names if n.endswith(ext)), "")

    js, css = _pick(".js"), _pick(".css")
    return (
        f"react/assets/{js}" if js else None,
        f"react/assets/{css}" if css else None,
    )


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
        # 已构建：直接托管 Vite 产物入口（title 与资源引用由前端工程统一维护）
        if (_FRONTEND_DIST / "index.html").is_file():
            return send_from_directory(_FRONTEND_DIST, "index.html")
        # 未构建：返回带构建指引的页面骨架
        react_js, react_css = collect_frontend_assets()
        return render_template(
            "index.html", env=collect_env(), react_js=react_js, react_css=react_css
        )

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

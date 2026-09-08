"""MiniDB Flask Web 应用（开发环境骨架）。

启动方式（开发环境）：
    venv\\Scripts\\activate
    python -m web.app            # 或 flask --app web.app run
"""
import platform
import sys

from flask import Flask, jsonify, render_template


def create_app():
    """应用工厂：便于测试与后续扩展（注册 SQL / 统计蓝图）。"""
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html", env=collect_env())

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "MiniDB Web Console", **collect_env()})

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
    # 开发服务器：host 127.0.0.1，debug 便于热重载
    app.run(host="127.0.0.1", port=5000, debug=True)

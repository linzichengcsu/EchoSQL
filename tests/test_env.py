"""环境冒烟测试：验证开发环境与依赖可用（对应指导文档第 6 章环境验证）。"""
import subprocess
import sys
from importlib.metadata import version

import flask


def test_python_version_satisfies_srs():
    """SRS 2.3 / 指导文档 3.1：Python 3.9+。"""
    assert sys.version_info >= (3, 9)


def test_flask_installed():
    """Flask 开发环境依赖可用。"""
    assert version("flask")


def test_web_app_health():
    """Flask 应用可创建，健康检查返回 ok。"""
    from web.app import create_app
    client = create_app().test_client()
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["flask"] == version("flask")


def test_smoke_module_runs():
    """smoke_test.py 可直接运行且退出码为 0（指导文档 6.1 节）。"""
    result = subprocess.run(
        [sys.executable, "smoke_test.py"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0
    assert "Smoke test OK" in result.stdout

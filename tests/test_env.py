"""环境冒烟测试：验证开发环境与依赖可用（对应指导文档第 6 章环境验证）。"""
import os
import sys

# 直接运行(python tests/test_env.py)时也能导入项目根包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import subprocess
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
    # 用项目根绝对路径定位 smoke_test.py 并显式指定 cwd，
    # 使本用例与 pytest 启动目录（项目根 / tests/ 等）无关
    result = subprocess.run(
        [sys.executable, os.path.join(_ROOT, "smoke_test.py")],
        cwd=_ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0
    assert "Smoke test OK" in result.stdout


# ======================================================================
# 统一启动方法（P5）：开发者可直接运行本测试模块
#     python tests/test_env.py
#     或编程调用 run_tests()（返回 pytest 退出码，0 = 全部通过）
# ======================================================================


def run_tests(verbose=True, extra_args=None):
    """统一启动方法：以 pytest 运行本测试模块全部用例。

    用法:
        python tests/test_env.py              # 命令行直接运行
        from runner import run_module         # 或编程调用(所有模块签名一致)
        run_module("tests/test_env.py")
    """
    from runner import run_module
    return run_module(__file__, verbose=verbose, extra_args=extra_args)


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())

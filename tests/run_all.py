"""P5 测试总入口：一键运行全部测试用例（统一启动方法 run_all）。

用法（在项目根目录执行）：
    python tests/run_all.py                              # 全部测试（-v 逐用例）
    python tests/run_all.py -q                           # 静默（参数完全透传）
    python tests/run_all.py --cov=. --cov-report=term    # 附带覆盖率统计
等价于在项目根执行 `pytest tests`。

任意单个测试模块同样暴露统一启动方法 run_tests()，可直接运行：
    python tests/test_engine.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from runner import run_all as _run_all  # noqa: E402

if __name__ == "__main__":
    extra = sys.argv[1:]
    # 无附加参数时默认 -v；有参数时完全透传，避免 -v 与 -q 并存
    sys.exit(_run_all(verbose=not extra, extra_args=extra or None))

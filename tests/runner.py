"""P5 测试统一启动辅助（每个测试模块共用的统一启动方法）。

为完成 README P5「测试与优化」任务，所有测试模块（tests/test_*.py）
都暴露**同名**的统一启动方法 run_tests()，开发者可用同一方式运行任意模块：

    - 命令行一键运行单个模块：
          python tests/test_engine.py
    - 开发者编程调用（方法签名完全一致，均返回 pytest 退出码）：
          import sys; sys.path.insert(0, "tests")
          import test_engine as m
          sys.exit(m.run_tests(verbose=False, extra_args=["-q"]))
    - 一键运行全部测试（总入口，见 run_all.py）：
          python tests/run_all.py            # 等价于 pytest tests -v

设计约束：
    - pytest 一律延迟到函数体内导入，本文件被普通导入时零副作用；
    - 退出码 0 表示全部通过，非 0 表示存在失败/错误（pytest 语义），
      可直接 sys.exit() 透传给调用方 / 脚本 / CI。
"""
import os

__all__ = ["run_module", "run_all", "discover_test_files"]


def discover_test_files(root: str = None) -> list:
    """返回 tests 目录下全部测试模块（test_*.py）的绝对路径，按名称排序。

    辅助文件（runner.py / run_all.py / conftest.py）不以 test_ 开头，
    天然不会被当作测试模块收集。
    """
    root = root or os.path.dirname(os.path.abspath(__file__))
    return sorted(
        os.path.join(root, name)
        for name in os.listdir(root)
        if name.startswith("test_") and name.endswith(".py")
    )


def run_module(module_file: str, verbose: bool = True, extra_args: list = None) -> int:
    """统一启动方法：以 pytest 运行**单个**测试模块文件的全部用例。

    参数:
        module_file  测试模块文件路径（测试模块内通常传入 __file__）
        verbose      为 True 时加 -v 逐用例输出（默认 True）
        extra_args   追加透传给 pytest 的参数列表，如 ["--cov=.", "-q"]
    返回:
        pytest 退出码（0 = 全部通过）
    """
    import pytest

    argv = [os.path.abspath(module_file)]
    if verbose:
        argv.append("-v")
    if extra_args:
        argv.extend(extra_args)
    return pytest.main(argv)


def run_all(verbose: bool = True, extra_args: list = None) -> int:
    """统一启动方法：一次运行 tests 目录下**全部**测试模块（等价 pytest tests）。

    参数:
        verbose     为 True 时加 -v 逐用例输出（默认 True）
        extra_args  追加透传给 pytest 的参数列表
    返回:
        pytest 退出码（0 = 全部通过）
    """
    import pytest

    argv = []
    if verbose:
        argv.append("-v")
    argv.extend(discover_test_files())
    if extra_args:
        argv.extend(extra_args)
    return pytest.main(argv)

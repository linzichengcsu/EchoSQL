"""MiniDB 主程序入口（CLI）。

依据推荐技术栈指导文档第 5 章：main.py 为项目主入口。
开发环境阶段提供 `doctor` 子命令做环境自检；后续阶段接入完整 SQL REPL。

用法：
    python main.py doctor      # 环境自检（依赖版本）
    python main.py             # （规划）进入 MiniDB SQL 命令行
"""
import argparse
import sys


def cmd_doctor() -> int:
    from importlib.metadata import version as _pkg_version

    def _ver(pkg: str) -> str:
        try:
            return _pkg_version(pkg)
        except Exception:
            return "未安装"

    print("MiniDB 开发环境自检")
    print("  Python :", sys.version.split()[0])
    print("  Flask  :", _ver("flask"))
    print("  pytest :", _ver("pytest"))
    print("  graphviz(py):", _ver("graphviz"))
    print("自检完成。")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="minidb", description="MiniDB 数据库管理系统")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor", help="环境自检")
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return cmd_doctor()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

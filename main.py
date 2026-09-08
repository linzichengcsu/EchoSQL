"""MiniDB 主程序入口（CLI）。

依据推荐技术栈指导文档第 5 章：main.py 为项目主入口。
P4 阶段接入数据库引擎，提供完整 SQL 命令行：

用法：
    python main.py doctor               # 环境自检（依赖版本）
    python main.py                      # 进入 MiniDB SQL 命令行（REPL）
    python main.py -f demo.sql          # 执行 SQL 脚本文件（批处理）
    python main.py --data-dir tmp       # 指定数据目录（默认 data）
    python main.py --policy FIFO        # 页缓存替换策略（LRU/FIFO）
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

    # 非子命令选项：进入 REPL 或执行脚本（P4 引擎接入）
    parser.add_argument("-f", "--file", metavar="FILE",
                        help="执行 SQL 脚本文件后退出（批处理）")
    parser.add_argument("--data-dir", default="data",
                        help="数据文件目录（默认 data，页式存储落盘位置）")
    parser.add_argument("--policy", default="LRU", choices=["LRU", "FIFO"],
                        help="页缓存替换策略（默认 LRU）")
    parser.add_argument("--capacity", type=int, default=8,
                        help="页缓存容量（默认 8 页）")
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return cmd_doctor()

    # 数据库引擎（P4）：REPL 或脚本批处理
    from cli import run_repl, run_sql_file
    from engine import Database

    db = Database(data_dir=args.data_dir,
                  capacity=args.capacity, policy=args.policy)
    if args.file:
        return run_sql_file(db, args.file)
    return run_repl(db)


if __name__ == "__main__":
    raise SystemExit(main())

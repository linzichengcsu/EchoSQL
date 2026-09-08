"""命令行接口（CLI）模块（FR-3.4 / SRS 5.1）。

提供 MiniDB 交互式命令行（标准库 cmd，推荐技术栈指导文档第 5 章）：
输入 SQL 并返回执行结果或错误信息，支持多语句与 `-f file.sql` 批处理。

交互示例（SRS 5.1）：
    MiniDB> CREATE TABLE student(id INT, name VARCHAR, age INT);
    OK
    MiniDB> INSERT INTO student(id,name,age) VALUES(1,'Alice',20);
    1 row inserted
    MiniDB> SELECT id,name FROM student WHERE age > 18;
    id  | name
    ----+-------
    1   | Alice
    MiniDB> quit
"""

import cmd
import sys
from typing import Optional

from engine import Database, EngineError
from sql_compiler import SQLError

__all__ = ["MiniDBShell", "run_repl", "run_sql_file", "main"]

_INTRO = """\
MiniDB 数据库管理系统（中南大学《大型平台软件设计实习》）
支持语句：CREATE TABLE / INSERT / SELECT（WHERE）/ DELETE
辅助命令：tables(表列表)  stats(缓存统计)  help   quit/exit
输入 SQL 语句（以 ; 结束），quit 退出。"""


class MiniDBShell(cmd.Cmd):
    """交互式 SQL 命令行（cmd 框架）。"""

    def __init__(self, db: Optional[Database] = None):
        super().__init__()
        self.db = db if db is not None else Database()
        self.intro = _INTRO
        self.prompt = "MiniDB> "

    # ---------- 命令分发 ----------

    def default(self, line: str) -> None:
        """把非内建命令当作 SQL 执行(多语句逐条输出结果)。"""
        line = line.strip()
        if not line:
            return
        try:
            results = self.db.execute_script(line)
            for result in results:
                print(result.format())
        except SQLError as exc:
            print(exc)  # [错误类型, 行:列, 原因]
        except EngineError as exc:
            print(exc)  # [EngineError, 原因]

    def emptyline(self) -> None:
        pass

    # ---------- 辅助命令 ----------

    def do_tables(self, arg: str) -> None:
        """tables: 列出全部表及其结构"""
        infos = self.db.table_infos()
        if not infos:
            print("(no tables)")
            return
        for info in infos:
            cols = ", ".join(
                "%s %s" % (c["name"], c["type"]) for c in info["columns"]
            )
            print("%s(%s)" % (info["name"], cols))

    def do_stats(self, arg: str) -> None:
        """stats: 打印页缓存命中统计等运行状态"""
        for key, value in self.db.stats().items():
            print("%s: %s" % (key, value))

    def do_quit(self, arg: str) -> bool:
        """quit / exit: 保存并退出(刷盘统一在 cmdloop 结束时进行)"""
        print("bye")
        return True

    do_exit = do_quit
    do_q = do_quit

    # ---------- 生命周期兜底 ----------

    def cmdloop(self, intro=None):
        try:
            super().cmdloop(intro=intro if intro is not None else self.intro)
        finally:
            # 异常退出(Ctrl-C / EOF)也保证刷盘
            try:
                self.db.close()
            except Exception:  # pragma: no cover
                pass

    def postloop(self) -> None:
        pass  # 关闭动作统一在 cmdloop finally 中完成


def run_repl(db: Database) -> int:
    """进入交互式命令行,退出后返回 0。"""
    MiniDBShell(db).cmdloop()
    return 0


def run_sql_file(db: Database, path: str, echo: bool = True) -> int:
    """执行 SQL 脚本文件(逐条输出结果),返回 0;出错时返回 1。"""
    try:
        with open(path, "r", encoding="utf-8") as fp:
            sql = fp.read()
    except OSError as exc:
        print("cannot open %s: %s" % (path, exc))
        return 1
    try:
        results = db.execute_script(sql)
        for result in results:
            if echo:
                print(result.format())
    except SQLError as exc:
        print(exc)
        return 1
    except EngineError as exc:
        print(exc)
        return 1
    finally:
        db.close()
    print("-- %s: %d statement(s) executed" % (path, len(results)))
    return 0


def main(argv: Optional[list] = None) -> int:
    """命令行入口(由 main.py 调用)。

    python -m cli               # REPL(默认 data 目录)
    python -m cli -f demo.sql   # 批处理
    python -m cli --data-dir tmp --policy FIFO
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="minidb-cli", description="MiniDB 数据库管理系统命令行"
    )
    parser.add_argument("-f", "--file", metavar="FILE", help="执行 SQL 脚本文件后退出")
    parser.add_argument("--data-dir", default="data", help="数据文件目录(默认 data)")
    parser.add_argument("--policy", default="LRU", choices=["LRU", "FIFO"],
                        help="页缓存替换策略(默认 LRU)")
    parser.add_argument("--capacity", type=int, default=8, help="页缓存容量(默认 8)")
    args = parser.parse_args(argv)

    db = Database(
        data_dir=args.data_dir, capacity=args.capacity, policy=args.policy,
    )
    if args.file:
        return run_sql_file(db, args.file)
    return run_repl(db)


if __name__ == "__main__":
    sys.exit(main())
